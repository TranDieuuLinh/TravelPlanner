import asyncio
from datetime import datetime, timedelta

from app.modules.explorer.public import build_explorer_graph
from app.modules.explorer.errors import ExplorerOperationError
from app.modules.explorer.retry import run_with_one_retry


def invoke(payload: dict):
    return asyncio.run(build_explorer_graph().ainvoke({"payload": payload}))["output"]


def test_prompt_only_extracts_adm_and_prompt_days() -> None:
    output = invoke({"rawPrompt": "Lập kế hoạch ở Huế trong 4 ngày"})

    assert output.status == "ready"
    assert output.input_adm == "Huế"
    assert output.days == 4
    assert output.start_date == datetime.now().astimezone().date() + timedelta(days=1)
    assert output.timezone == "Asia/Ho_Chi_Minh"


def test_prompt_without_days_defaults_to_three_day_plan() -> None:
    output = invoke({"rawPrompt": "Lập kế hoạch ở Huế"})

    assert output.status == "ready"
    assert output.days == 3
    assert output.people.adults == 2


def test_destination_only_records_and_calculates_review_defaults() -> None:
    output = invoke({"rawPrompt": "Lập kế hoạch Hà Nội"})

    assert output.defaulted_fields == [
        "days",
        "budget",
        "people",
        "shortPreferences",
    ]
    assert output.budget.level == "low"
    assert output.budget.target_amount == 1_923_284


def test_explicit_required_fields_do_not_create_default_review() -> None:
    output = invoke({
        "rawPrompt": (
            "Lập kế hoạch Hà Nội 4 ngày cho 3 người, "
            "budget 6 triệu/người, thích văn hóa"
        )
    })

    assert output.defaulted_fields == []
    assert output.days == 4
    assert output.people.adults == 3
    assert output.budget.target_amount == 6_000_000


def test_explicit_solo_party_overrides_two_person_default() -> None:
    output = invoke({"rawPrompt": "Lập kế hoạch ở Huế cho 1 người"})

    assert output.people.adults == 1


def test_prompt_date_overrides_tomorrow_default() -> None:
    output = invoke({"rawPrompt": "Đi Hà Nội ngày 20/08/2026 trong 5 ngày"})

    assert output.start_date.isoformat() == "2026-08-20"
    assert output.days == 5


def test_group_budget_is_normalized_per_person_before_output() -> None:
    output = invoke({
        "rawPrompt": "Lập kế hoạch ở Huế 4 ngày cho 4 người, budget 8 triệu"
    })

    assert output.budget.target_amount == 2_000_000
    assert output.budget.basis == "per_person"


def test_explicit_per_person_budget_is_preserved() -> None:
    output = invoke({
        "rawPrompt": "Lập kế hoạch ở Huế cho 4 người, budget 2 triệu/người"
    })

    assert output.budget.target_amount == 2_000_000
    assert output.budget.basis == "per_person"


def test_defaults_do_not_infer_days_from_image() -> None:
    output = invoke({
        "images": [{
            "fileName": "capture.png", "mimeType": "image/png",
            "ocrText": "Du lịch ở Đà Nẵng, tham quan Cầu Rồng trong 7 ngày",
        }]
    })

    assert output.status == "ready"
    assert output.days == 3
    assert output.budget.level == "low"
    assert output.people.adults == 2
    assert output.places[0].source_places[0].evidence_type == "image_ocr"
    assert output.url_notes[0].evidence_type == "image_ocr"


def test_source_flow_preserves_explicit_prompt_preferences() -> None:
    output = invoke({
        "rawPrompt": "Đi Hà Nội, ưu tiên văn hóa, cà phê và trải nghiệm địa phương",
        "images": [{
            "fileName": "capture.png",
            "mimeType": "image/png",
            "ocrText": "Hà Nội, tham quan Văn Miếu",
        }],
    })

    assert output.short_preferences == [
        "Văn hóa",
        "đồ uống",
        "địa phương",
        "hoạt động",
    ]


def test_general_preferences_do_not_become_input_items() -> None:
    output = invoke({
        "rawPrompt": (
            "Du lịch Hà Nội 2 ngày, thích văn hóa và ẩm thực, "
            "buổi tối đi dạo"
        )
    })

    assert output.input_items is None
    assert output.short_preferences == [
        "Văn hóa",
        "địa phương",
        "ẩm thực",
        "giá rẻ",
    ]


def test_unmatched_trip_styles_are_dropped_by_runtime_taxonomy() -> None:
    output = invoke({"rawPrompt": "Du lịch Hà Nội 3 ngày kiểu chill và đi chậm"})

    assert len(output.short_preferences) == 4
    assert output.short_preferences[0] == "giá rẻ"
    assert set(output.short_preferences) <= {
        "giá rẻ", "địa phương", "ẩm thực", "Văn hóa", "thiên nhiên",
        "biển", "núi", "cảnh quan",
    }
    assert output.short_avoids == ["sang trọng"]


def test_named_venue_keeps_only_proper_name_and_links_prompt_item() -> None:
    output = invoke({
        "rawPrompt": (
            "Tôi muốn ăn phở ở Phở Gia Truyền Bát Đàn "
            "tại Hà Nội trong 2 ngày"
        )
    })

    assert output.places[0].name == "Phở Gia Truyền Bát Đàn"
    assert output.input_items[0].name == "phở"
    assert output.input_items[0].related_place_name == "Phở Gia Truyền Bát Đàn"


def test_visit_place_name_excludes_adm_context() -> None:
    output = invoke({
        "rawPrompt": "Tôi muốn tham quan Văn Miếu tại Hà Nội trong 2 ngày"
    })

    assert output.places[0].name == "Văn Miếu"


def test_missing_adm_uses_clarification_path() -> None:
    output = invoke({"rawPrompt": "Lập kế hoạch 3 ngày"})

    assert output.status == "clarification"
    assert output.input_adm is None
    assert output.budget.level == "low"
    assert output.clarification_question == "Bạn muốn đi tỉnh hoặc thành phố nào?"


def test_source_action_is_not_part_of_place_name() -> None:
    output = invoke({
        "images": [{
            "fileName": "capture.png", "mimeType": "image/png",
            "ocrText": "Du lịch ở Đà Nẵng, tham quan Cầu Rồng và uống cà phê",
        }]
    })

    assert output.places[0].name == "Cầu Rồng"
    assert any(note.summary == "uống cà phê" for note in output.url_notes)


def test_unconfigured_url_returns_failure_after_retry_policy() -> None:
    output = invoke({"urls": ["https://example.com/video"]})

    assert output.status == "error"
    assert output.error.code == "SOURCE_UNAVAILABLE"


def test_retryable_operation_runs_at_most_twice() -> None:
    attempts = 0

    async def operation():
        nonlocal attempts
        attempts += 1
        raise ExplorerOperationError("TEMPORARY", "temporary", retryable=True)

    try:
        asyncio.run(run_with_one_retry(operation))
    except ExplorerOperationError:
        pass

    assert attempts == 2


def test_embedded_url_routes_to_source_import() -> None:
    output = invoke({"rawPrompt": "Xem https://example.com/post để lên lịch ở Huế"})

    assert output.status == "error"
