import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.modules.knowledge_graph.routes import admin_place_dedupe as route
from scripts.dedupe_knowledge_graph_places import PlaceRecord, _fingerprint
from tests.helpers import csrf_headers


def _record(entity_id: str, name: str) -> dict:
    return {
        "entityId": entity_id,
        "name": name,
        "aliases": [],
        "placeType": "Historical landmark",
        "category": "culture",
        "address": "Hà Nội",
        "regionKey": "vn,ha-noi",
        "latitude": 21.0,
        "longitude": 105.8,
        "reviewCount": 0,
        "revision": 1,
    }


def _group(group_id: str, name: str) -> dict:
    return {
        "groupId": group_id,
        "reasonCodes": ["same_name_but_too_far"],
        "records": [_record(f"{group_id}-1", name), _record(f"{group_id}-2", name)],
    }


def _report(groups: list[dict]) -> dict:
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-08-07T00:00:00+00:00",
        "databaseFingerprint": "fingerprint",
        "groupCount": len(groups),
        "groups": groups,
    }


def _place(entity_id: str, name: str) -> PlaceRecord:
    return PlaceRecord(
        id=entity_id,
        name=name,
        normalized_name=name.casefold(),
        entity_type="TravelPlace",
        place_type="Historical landmark",
        address="Hà Nội",
        city="Hà Nội",
        region_key="vn,ha-noi",
        latitude=21.0,
        longitude=105.8,
        data_confidence="medium",
        review_count=0,
        revision=1,
        aliases=(),
    )


def test_list_place_reviews_filters_before_pagination(monkeypatch) -> None:
    monkeypatch.setattr(
        route,
        "_read_review_report",
        lambda: _report([_group("one", "Văn Miếu"), _group("two", "Hồ Gươm")]),
    )
    monkeypatch.setattr(route, "_sync_completed_review_groups", lambda report, _db: report)

    response = route.list_place_reviews(object(), object(), offset=0, limit=1, query="hồ gươm")

    assert response.group_count == 1
    assert [group.group_id for group in response.groups] == ["two"]


def test_dismiss_removes_group_from_review_queue(monkeypatch, tmp_path: Path) -> None:
    review_path = tmp_path / "needs_review.json"
    review_path.write_text(json.dumps(_report([_group("one", "Văn Miếu")])), encoding="utf-8")
    monkeypatch.setattr(route, "_report_path", lambda: review_path)
    monkeypatch.setattr(route, "_persist_not_merged_decision", lambda *_args: None)

    response = route.dismiss_place_merge("one", SimpleNamespace(role="admin"), object())

    assert response.decision == "not_merged"
    assert json.loads(review_path.read_text(encoding="utf-8"))["groups"] == []


def test_dismiss_rejects_non_admin(registered_client: TestClient) -> None:
    response = registered_client.post(
        "/api/admin/knowledge-graph/place-dedupe/review/one/dismiss",
        headers=csrf_headers(registered_client),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "INSUFFICIENT_ROLE"


def test_sync_removes_groups_already_completed_in_graph(monkeypatch, tmp_path: Path) -> None:
    review_path = tmp_path / "needs_review.json"
    review_path.write_text(json.dumps(_report([_group("one", "Văn Miếu")])), encoding="utf-8")
    monkeypatch.setattr(route, "_report_path", lambda: review_path)

    class FakeDb:
        def scalars(self, _statement):
            return [SimpleNamespace(key="merged_into_entity_id", entity_id="one-2", value="canonical")]

    synced = route._sync_completed_review_groups(_report([_group("one", "Văn Miếu")]), FakeDb())

    assert synced["groups"] == []
    assert json.loads(review_path.read_text(encoding="utf-8"))["groups"] == []


def test_merge_reads_graph_once_and_returns_only_decision(monkeypatch, tmp_path: Path) -> None:
    canonical = _place("canonical", "Văn Miếu")
    secondary = _place("secondary", "Temple of Literature")
    records = [canonical, secondary]
    review = _report(
        [
            {
                "groupId": "review-one",
                "reasonCodes": ["identity_collision"],
                "records": [_record("canonical", canonical.name), _record("secondary", secondary.name)],
            }
        ]
    )
    review["databaseFingerprint"] = _fingerprint(records)
    review_path = tmp_path / "needs_review.json"
    review_path.write_text(json.dumps(review), encoding="utf-8")
    monkeypatch.setattr(route, "_report_path", lambda: review_path)
    monkeypatch.setattr(route, "_auto_report_path", lambda: tmp_path / "auto_merge.json")
    calls = 0

    def load_once(_db):
        nonlocal calls
        calls += 1
        return records

    monkeypatch.setattr(route, "load_records", load_once)
    monkeypatch.setattr(route, "apply_report", lambda _db, report, _records: 1)

    response = route.approve_place_merge(
        "review-one",
        route.ApprovePlaceMergeRequest(canonicalEntityId="canonical"),
        SimpleNamespace(role="admin"),
        object(),
    )

    assert calls == 1
    assert response.model_dump(by_alias=True) == {
        "groupId": "review-one",
        "decision": "merged",
    }
    updated = json.loads(review_path.read_text(encoding="utf-8"))
    assert updated["databaseFingerprint"] == _fingerprint([canonical])
