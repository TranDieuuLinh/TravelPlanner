import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy.orm import sessionmaker

from app.modules.plans.chat_model import TripChat, TripChatMessage
from app.modules.plans.url_job_model import UrlImportJob
from app.modules.plans.url_job_repository import UrlImportJobRepository
from app.modules.plans.url_job_worker import UrlImportJobWorker
from app.modules.plans import url_job_worker as worker_module
from tests.helpers import csrf_headers


def _create_chat(client) -> str:
    response = client.post(
        "/api/trip-chats",
        json={"title": "URL queue"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_multiple_urls_are_enqueued_as_individual_jobs(
    registered_client,
    db_session,
) -> None:
    chat_id = _create_chat(registered_client)
    urls = [
        "https://www.youtube.com/watch?v=queue01",
        "https://www.tiktok.com/@creator/video/2",
        "https://www.instagram.com/reel/3/",
    ]

    response = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": f"Dùng các nguồn này {' '.join(urls)}",
            "expectedRevision": "0",
            "urls": urls,
        },
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 202
    jobs = response.json()["jobs"]
    assert [job["url"] for job in jobs] == urls
    assert [job["status"] for job in jobs] == ["queued", "queued", "queued"]
    assert [job["phase"] for job in jobs] == ["queued", "queued", "queued"]
    assert sorted(job["queuePosition"] for job in jobs) == [1, 2, 3]
    chat = registered_client.get(f"/api/trip-chats/{chat_id}").json()
    assert len(chat["messages"]) == 1
    assert chat["messages"][0]["role"] == "user"
    assert chat["messages"][0]["content"] == f"Dùng các nguồn này {' '.join(urls)}"
    assert registered_client.get("/api/trip-chats/active-turns").json() == []
    turn = db_session.get(TripChatMessage, chat["messages"][0]["id"])
    assert turn is not None
    assert turn.status == "queued"
    persisted_jobs = [db_session.get(UrlImportJob, job["id"]) for job in jobs]
    assert {job.batch_id for job in persisted_jobs if job is not None} == {turn.id}


def test_force_refresh_job_is_persisted_and_returned(registered_client, db_session) -> None:
    chat_id = _create_chat(registered_client)

    response = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": "Phân tích lại https://www.tiktok.com/@creator/video/42",
            "expectedRevision": "0",
            "forceRefresh": "true",
        },
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 202
    payload = response.json()["jobs"][0]
    assert payload["forceRefresh"] is True
    persisted = db_session.get(UrlImportJob, payload["id"])
    assert persisted is not None
    assert persisted.force_refresh is True


def test_multiple_images_are_enqueued_as_persistent_ocr_jobs(
    registered_client,
    db_session,
) -> None:
    chat_id = _create_chat(registered_client)

    response = registered_client.post(
        f"/api/trip-chats/{chat_id}/image-jobs",
        data={
            "content": "Tạo lịch trình từ các ảnh này",
            "expectedRevision": "0",
        },
        files=[
            ("images", ("menu.png", b"first-image", "image/png")),
            ("images", ("sign.jpg", b"second-image", "image/jpeg")),
        ],
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 202
    jobs = response.json()["jobs"]
    assert [job["sourceType"] for job in jobs] == ["image", "image"]
    assert [job["sourceLabel"] for job in jobs] == ["menu.png", "sign.jpg"]
    assert [job["status"] for job in jobs] == ["queued", "queued"]
    assert sorted(job["queuePosition"] for job in jobs) == [1, 2]
    persisted = db_session.get(UrlImportJob, jobs[0]["id"])
    assert persisted is not None
    assert persisted.url == ""
    assert persisted.image_mime_type == "image/png"
    assert persisted.image_data == b"first-image"


def test_image_job_rejects_unsupported_media_type(registered_client) -> None:
    chat_id = _create_chat(registered_client)

    response = registered_client.post(
        f"/api/trip-chats/{chat_id}/image-jobs",
        data={"content": "Đọc ảnh", "expectedRevision": "0"},
        files={"images": ("notes.txt", b"not-an-image", "text/plain")},
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "UNSUPPORTED_IMAGE_TYPE"


def test_finished_image_job_reprocesses_with_original_image(
    registered_client,
    db_session,
) -> None:
    chat_id = _create_chat(registered_client)
    created = registered_client.post(
        f"/api/trip-chats/{chat_id}/image-jobs",
        data={"content": "Đọc biển hiệu", "expectedRevision": "0"},
        files={"images": ("place.webp", b"image-to-reuse", "image/webp")},
        headers=csrf_headers(registered_client),
    ).json()["jobs"][0]
    repository = UrlImportJobRepository(db_session)
    repository.succeed(created["id"], revision=1)

    response = registered_client.post(
        f"/api/url-import-jobs/{created['id']}/reprocess",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 202
    replay = response.json()
    assert replay["id"] != created["id"]
    assert replay["sourceType"] == "image"
    persisted = db_session.get(UrlImportJob, replay["id"])
    assert persisted is not None
    assert persisted.image_data == b"image-to-reuse"
    assert persisted.image_mime_type == "image/webp"


def test_worker_sends_persisted_image_through_trip_chat_pipeline(
    registered_client,
    db_session,
    monkeypatch,
) -> None:
    chat_id = _create_chat(registered_client)
    created = registered_client.post(
        f"/api/trip-chats/{chat_id}/image-jobs",
        data={"content": "Đọc địa điểm trong ảnh", "expectedRevision": "0"},
        files={"images": ("street.png", b"ocr-source-bytes", "image/png")},
        headers=csrf_headers(registered_client),
    ).json()["jobs"][0]
    captured: dict[str, object] = {}

    async def fake_amend(_service, _chat_id, _user, **kwargs):
        captured.update(kwargs)
        kwargs["on_explore_complete"](None)
        return SimpleNamespace(revision=1)

    monkeypatch.setattr(worker_module, "get_plan_service", lambda _db: object())
    monkeypatch.setattr(worker_module, "get_plan_mutation_service", lambda _db: object())
    monkeypatch.setattr(worker_module.TripChatService, "amend", fake_amend)
    worker = UrlImportJobWorker(lambda: db_session)
    claimed = UrlImportJobRepository(db_session).claim_next()
    assert claimed is not None
    assert claimed.id == created["id"]

    revision = asyncio.run(worker._process(db_session, created["id"]))

    assert revision == 1
    assert captured["urls"] == []
    images = captured["images"]
    assert isinstance(images, list)
    assert len(images) == 1
    assert images[0].file_name == "street.png"
    assert images[0].mime_type == "image/png"
    assert images[0].data == b"ocr-source-bytes"
    chat = registered_client.get(f"/api/trip-chats/{chat_id}").json()
    assert captured["turn_id"] == chat["messages"][0]["id"]
    persisted = db_session.get(UrlImportJob, created["id"])
    assert persisted is not None
    assert persisted.processing_phase == "planning"


def test_queue_claims_only_one_job_until_it_finishes(
    registered_client,
    db_session,
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    chat_id = _create_chat(registered_client)
    registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": "https://example.com/one https://example.com/two",
            "expectedRevision": "0",
        },
        headers=csrf_headers(registered_client),
    )
    repository = UrlImportJobRepository(db_session)

    first = repository.claim_next()
    assert first is not None
    assert first.status == "running"
    assert repository.read(first).phase == "exploring"
    assert first.url == "https://example.com/one"
    assert repository.claim_next() is None

    chat = db_session.get(TripChat, chat_id)
    assert chat is not None
    chat.latest_explorer_timing = {
        "intakeId": "intake-url-one",
        "status": "succeeded",
        "totalSeconds": 3.5,
        "stages": [],
        "sources": [],
        "urlCount": 1,
        "imageCount": 0,
        "candidateCount": 2,
        "resolvedCount": 2,
        "persistedCount": 2,
        "providerCounts": {"database": 2},
        "resolvedProviderCounts": {"database": 2},
    }
    chat.latest_planner_timing = {
        "status": "succeeded",
        "totalSeconds": 4.25,
        "stages": [],
        "dayCount": 2,
        "itemCount": 4,
        "transportLegCount": 2,
        "unscheduledCount": 0,
        "warningCount": 0,
    }
    db_session.commit()
    repository.succeed(first.id, revision=1)
    completed = repository.read(first)
    assert completed.phase == "complete"
    assert completed.explorer_timing is not None
    assert completed.explorer_timing.total_seconds == 3.5
    assert completed.planner_timing is not None
    assert completed.planner_timing.total_seconds == 4.25
    UrlImportJobWorker._log_terminal_timing(
        db_session,
        job_id=first.id,
        processing_started_at=time.perf_counter(),
    )
    terminal_lines = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("TRAVELPLANNER_TIMING url_job ")
    ]
    assert len(terminal_lines) == 1
    timing_payload = json.loads(
        terminal_lines[0].removeprefix("TRAVELPLANNER_TIMING url_job ")
    )
    assert timing_payload["event"] == "url_job_timing"
    assert timing_payload["status"] == "succeeded"
    assert timing_payload["explorerSeconds"] == 3.5
    assert timing_payload["plannerSeconds"] == 4.25
    assert timing_payload["accountedSeconds"] == 7.75
    second = repository.claim_next()
    assert second is not None
    assert second.id != first.id
    assert second.status == "running"
    repository.succeed(second.id, revision=2)
    turn = db_session.get(TripChatMessage, second.batch_id)
    assert turn is not None
    assert turn.status == "completed"
    assert turn.plan_revision == 2


def test_stale_running_job_fails_and_releases_next_job(
    registered_client,
    db_session,
) -> None:
    chat_id = _create_chat(registered_client)
    registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": "https://example.com/stale https://example.com/next",
            "expectedRevision": "0",
        },
        headers=csrf_headers(registered_client),
    )
    repository = UrlImportJobRepository(db_session)
    stale = repository.claim_next()
    assert stale is not None
    stale.started_at = datetime.now(UTC) - timedelta(minutes=30)
    db_session.commit()

    assert repository.fail_stale_running(timeout_seconds=60) == 1
    db_session.refresh(stale)
    assert stale.status == "failed"
    assert stale.error_code == "URL_IMPORT_TIMEOUT"
    assert repository.claim_next() is not None


def test_worker_times_out_job_instead_of_blocking_queue(
    registered_client,
    db_session,
) -> None:
    chat_id = _create_chat(registered_client)
    created = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={"content": "https://example.com/slow", "expectedRevision": "0"},
        headers=csrf_headers(registered_client),
    ).json()["jobs"][0]
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )
    worker = UrlImportJobWorker(session_factory, job_timeout_seconds=0.01)

    async def slow_process(_db, _job_id: str) -> int:
        await asyncio.sleep(1)
        return 1

    worker._process = slow_process  # type: ignore[method-assign]

    assert asyncio.run(worker.run_once()) is True
    timed_out = db_session.get(UrlImportJob, created["id"])
    assert timed_out is not None
    db_session.refresh(timed_out)
    assert timed_out.status == "failed"
    assert timed_out.error_code == "URL_IMPORT_TIMEOUT"


def test_worker_rolls_back_failed_batch_transaction_without_replanning_sibling(
    registered_client,
    db_session,
) -> None:
    chat_id = _create_chat(registered_client)
    jobs = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": "https://example.com/broken https://example.com/next",
            "expectedRevision": "0",
        },
        headers=csrf_headers(registered_client),
    ).json()["jobs"]
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )
    worker = UrlImportJobWorker(session_factory)

    async def fail_first_transaction(db, job_id: str) -> int:
        if job_id == jobs[0]["id"]:
            current = db.get(UrlImportJob, job_id)
            assert current is not None
            db.add(
                UrlImportJob(
                    id=current.id,
                    user_id=current.user_id,
                    chat_id=current.chat_id,
                    url=current.url,
                    request_content=current.request_content,
                    force_refresh=False,
                    batch_position=0,
                    status="running",
                )
            )
            db.flush()
        return 2

    worker._process = fail_first_transaction  # type: ignore[method-assign]

    assert asyncio.run(worker.run_once()) is True
    assert asyncio.run(worker.run_once()) is False

    db_session.expire_all()
    failed = db_session.get(UrlImportJob, jobs[0]["id"])
    sibling = db_session.get(UrlImportJob, jobs[1]["id"])
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_code == "URL_IMPORT_FAILED"
    assert sibling is not None
    assert sibling.status == "failed"
    assert sibling.error_code == "URL_IMPORT_FAILED"


def test_queue_can_claim_different_chats_but_serializes_each_chat(
    registered_client,
    db_session,
) -> None:
    first_chat = _create_chat(registered_client)
    second_chat = _create_chat(registered_client)
    first_jobs = registered_client.post(
        f"/api/trip-chats/{first_chat}/url-jobs",
        data={
            "content": "https://example.com/a1 https://example.com/a2",
            "expectedRevision": "0",
        },
        headers=csrf_headers(registered_client),
    ).json()["jobs"]
    second_job = registered_client.post(
        f"/api/trip-chats/{second_chat}/url-jobs",
        data={"content": "https://example.com/b1", "expectedRevision": "0"},
        headers=csrf_headers(registered_client),
    ).json()["jobs"][0]
    repository = UrlImportJobRepository(db_session)

    first = repository.claim_next(max_concurrency=3)
    second = repository.claim_next(max_concurrency=3)

    assert first is not None and first.id == first_jobs[0]["id"]
    assert second is not None and second.id == second_job["id"]
    assert repository.claim_next(max_concurrency=3) is None


def test_worker_combines_source_batch_into_one_planning_call(
    registered_client,
    db_session,
    monkeypatch,
) -> None:
    chat_id = _create_chat(registered_client)
    jobs = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": "Dùng cả hai nguồn",
            "expectedRevision": "0",
            "urls": ["https://example.com/one", "https://example.com/two"],
        },
        headers=csrf_headers(registered_client),
    ).json()["jobs"]
    captured: list[dict[str, object]] = []

    async def fake_amend(_service, _chat_id, _user, **kwargs):
        captured.append(kwargs)
        kwargs["on_explore_complete"](None)
        return SimpleNamespace(revision=1)

    monkeypatch.setattr(worker_module, "get_plan_service", lambda _db: object())
    monkeypatch.setattr(worker_module, "get_plan_mutation_service", lambda _db: object())
    monkeypatch.setattr(worker_module.TripChatService, "amend", fake_amend)
    worker = UrlImportJobWorker(lambda: db_session)

    assert asyncio.run(worker.run_once()) is True
    assert len(captured) == 1
    assert captured[0]["urls"] == [
        "https://example.com/one",
        "https://example.com/two",
    ]
    db_session.expire_all()
    assert [db_session.get(UrlImportJob, job["id"]).status for job in jobs] == [
        "succeeded",
        "succeeded",
    ]


def test_worker_loop_survives_iteration_failure(db_session) -> None:
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )
    worker = UrlImportJobWorker(session_factory, poll_interval_seconds=0.001)

    async def scenario() -> None:
        calls = 0
        continued = asyncio.Event()

        async def run_once() -> bool:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("terminal-state write failed")
            continued.set()
            return False

        worker.run_once = run_once  # type: ignore[method-assign]
        task = asyncio.create_task(worker.run_forever())
        await asyncio.wait_for(continued.wait(), timeout=1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert calls >= 2

    asyncio.run(scenario())


def test_user_only_sees_their_own_url_jobs(registered_client) -> None:
    chat_id = _create_chat(registered_client)
    registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={"content": "https://example.com/private", "expectedRevision": "0"},
        headers=csrf_headers(registered_client),
    )
    registered_client.post("/api/auth/logout", headers=csrf_headers(registered_client))
    registered_client.post(
        "/api/auth/register",
        json={
            "email": "queue-second@example.com",
            "password": "MatKhauManh123",
            "fullName": "Queue Second",
        },
    )

    response = registered_client.get("/api/url-import-jobs")

    assert response.status_code == 200
    assert response.json() == {"jobs": []}


def test_failed_job_can_be_retried_individually(registered_client, db_session) -> None:
    chat_id = _create_chat(registered_client)
    created = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={"content": "https://example.com/retry", "expectedRevision": "0"},
        headers=csrf_headers(registered_client),
    ).json()["jobs"][0]
    repository = UrlImportJobRepository(db_session)
    repository.fail(created["id"], code="SOURCE_UNAVAILABLE", message="Nguồn tạm lỗi")

    response = registered_client.post(
        f"/api/url-import-jobs/{created['id']}/retry",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert response.json()["errorMessage"] is None
    assert response.json()["forceRefresh"] is True


def test_finished_job_reprocesses_from_the_beginning_without_extraction_cache(
    registered_client,
    db_session,
) -> None:
    chat_id = _create_chat(registered_client)
    created = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={"content": "https://example.com/reprocess", "expectedRevision": "0"},
        headers=csrf_headers(registered_client),
    ).json()["jobs"][0]
    repository = UrlImportJobRepository(db_session)
    repository.succeed(created["id"], revision=1)

    response = registered_client.post(
        f"/api/url-import-jobs/{created['id']}/reprocess",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 202
    replay = response.json()
    assert replay["id"] != created["id"]
    assert replay["status"] == "queued"
    assert replay["forceRefresh"] is True
    original = db_session.get(UrlImportJob, created["id"])
    assert original is not None
    assert original.status == "succeeded"
    assert original.force_refresh is False


def test_active_job_cannot_be_reprocessed(registered_client) -> None:
    chat_id = _create_chat(registered_client)
    created = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={"content": "https://example.com/active", "expectedRevision": "0"},
        headers=csrf_headers(registered_client),
    ).json()["jobs"][0]

    response = registered_client.post(
        f"/api/url-import-jobs/{created['id']}/reprocess",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 409
    assert response.json()["code"] == "URL_IMPORT_JOB_NOT_FINISHED"


def test_queued_job_can_be_deleted_and_positions_are_updated(registered_client) -> None:
    chat_id = _create_chat(registered_client)
    jobs = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": "https://example.com/remove https://example.com/keep",
            "expectedRevision": "0",
        },
        headers=csrf_headers(registered_client),
    ).json()["jobs"]

    response = registered_client.delete(
        f"/api/url-import-jobs/{jobs[0]['id']}",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 204
    remaining = registered_client.get("/api/url-import-jobs").json()["jobs"]
    assert [job["id"] for job in remaining] == [jobs[1]["id"]]
    assert remaining[0]["queuePosition"] == 1


def test_finished_jobs_can_be_deleted(registered_client, db_session) -> None:
    chat_id = _create_chat(registered_client)
    jobs = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": "https://example.com/done https://example.com/failed",
            "expectedRevision": "0",
        },
        headers=csrf_headers(registered_client),
    ).json()["jobs"]
    repository = UrlImportJobRepository(db_session)
    repository.succeed(jobs[0]["id"], revision=1)
    repository.fail(jobs[1]["id"], code="SOURCE_UNAVAILABLE", message="Nguồn tạm lỗi")

    for job in jobs:
        response = registered_client.delete(
            f"/api/url-import-jobs/{job['id']}",
            headers=csrf_headers(registered_client),
        )
        assert response.status_code == 204

    assert registered_client.get("/api/url-import-jobs").json()["jobs"] == []


def test_running_job_can_be_stopped_deleted_and_releases_next_job(
    registered_client,
    db_session,
) -> None:
    chat_id = _create_chat(registered_client)
    jobs = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": "https://example.com/running https://example.com/next",
            "expectedRevision": "0",
        },
        headers=csrf_headers(registered_client),
    ).json()["jobs"]
    repository = UrlImportJobRepository(db_session)
    claimed = repository.claim_next()
    assert claimed is not None

    class CancellingWorker:
        async def cancel(self, job_id: str) -> bool:
            return repository.delete_running(job_id)

    previous_worker = getattr(
        registered_client.app.state,
        "url_import_worker",
        None,
    )
    registered_client.app.state.url_import_worker = CancellingWorker()
    try:
        response = registered_client.delete(
            f"/api/url-import-jobs/{jobs[0]['id']}",
            headers=csrf_headers(registered_client),
        )
    finally:
        if previous_worker is None:
            del registered_client.app.state.url_import_worker
        else:
            registered_client.app.state.url_import_worker = previous_worker

    assert response.status_code == 204
    assert db_session.get(UrlImportJob, jobs[0]["id"]) is None
    next_job = repository.claim_next()
    assert next_job is not None
    assert next_job.id == jobs[1]["id"]


def test_worker_cancels_active_process_before_claiming_next(
    registered_client,
    db_session,
) -> None:
    chat_id = _create_chat(registered_client)
    jobs = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={
            "content": "https://example.com/slow https://example.com/after-stop",
            "expectedRevision": "0",
        },
        headers=csrf_headers(registered_client),
    ).json()["jobs"]
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=db_session.get_bind(),
    )
    worker = UrlImportJobWorker(session_factory)

    async def scenario() -> None:
        first_started = asyncio.Event()

        async def process(_db, job_id: str) -> int:
            if job_id == jobs[0]["id"]:
                first_started.set()
                await asyncio.Event().wait()
            return 2

        worker._process = process  # type: ignore[method-assign]
        first_run = asyncio.create_task(worker.run_once())
        await first_started.wait()
        assert await worker.cancel(jobs[0]["id"]) is True
        assert await first_run is True
        assert await worker.run_once() is True

    asyncio.run(scenario())

    db_session.expire_all()
    assert db_session.get(UrlImportJob, jobs[0]["id"]) is None
    completed = db_session.get(UrlImportJob, jobs[1]["id"])
    assert completed is not None
    assert completed.status == "succeeded"


def test_deleting_queued_job_requires_csrf(registered_client) -> None:
    chat_id = _create_chat(registered_client)
    created = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={"content": "https://example.com/csrf", "expectedRevision": "0"},
        headers=csrf_headers(registered_client),
    ).json()["jobs"][0]

    response = registered_client.delete(f"/api/url-import-jobs/{created['id']}")

    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_VALIDATION_FAILED"


def test_user_cannot_delete_another_users_queued_job(registered_client) -> None:
    chat_id = _create_chat(registered_client)
    created = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={"content": "https://example.com/private-delete", "expectedRevision": "0"},
        headers=csrf_headers(registered_client),
    ).json()["jobs"][0]
    registered_client.post("/api/auth/logout", headers=csrf_headers(registered_client))
    registered_client.post(
        "/api/auth/register",
        json={
            "email": "queue-delete-second@example.com",
            "password": "MatKhauManh123",
            "fullName": "Queue Delete Second",
        },
    )

    response = registered_client.delete(
        f"/api/url-import-jobs/{created['id']}",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "URL_IMPORT_JOB_NOT_FOUND"


def test_internal_url_is_rejected_before_enqueue(registered_client) -> None:
    chat_id = _create_chat(registered_client)

    response = registered_client.post(
        f"/api/trip-chats/{chat_id}/url-jobs",
        data={"content": "http://127.0.0.1/private", "expectedRevision": "0"},
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "UNSAFE_URL"
