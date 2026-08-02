import pytest

from app.modules.plans.router import (
    _default_trip_spec,
    _infer_destination_from_urls,
    _prepare_intake,
    _remove_urls,
)


def test_intake_extracts_urls_from_the_chat_message() -> None:
    raw_request = (
        "Lập lịch trình Đà Lạt từ https://example.com/reel/123 "
        "và https://example.com/blog."
    )

    effective_request, urls = _prepare_intake(
        raw_request,
        explicit_urls=[],
    )

    assert effective_request == raw_request
    assert urls == [
        "https://example.com/reel/123",
        "https://example.com/blog",
    ]
    assert _remove_urls(effective_request) == "Lập lịch trình Đà Lạt từ   và"


def test_intake_rejects_an_image_without_text() -> None:
    with pytest.raises(ValueError, match="prompt, URL, or image"):
        _prepare_intake("", explicit_urls=[])


def test_intake_accepts_image_only_for_ocr() -> None:
    assert _prepare_intake(
        "",
        explicit_urls=[],
        has_images=True,
    ) == ("Tạo lịch trình từ ảnh đính kèm.", [])


def test_intake_accepts_explicit_url_without_prompt_text() -> None:
    assert _prepare_intake(
        "",
        explicit_urls=["https://example.com/reel"],
    ) == ("Tạo lịch trình từ URL đã cung cấp.", ["https://example.com/reel"])


def test_intake_uses_plain_text_when_no_url_or_image_exists() -> None:
    assert _prepare_intake(
        "Hà Nội 3 ngày, ưu tiên ẩm thực",
        explicit_urls=[],
    ) == ("Hà Nội 3 ngày, ưu tiên ẩm thực", [])


def test_intake_rejects_an_empty_message() -> None:
    with pytest.raises(ValueError, match="prompt, URL, or image"):
        _prepare_intake("", explicit_urls=[])


def test_default_trip_spec_uses_requested_days_when_present() -> None:
    trip_spec = _default_trip_spec("Hà Nội 5 ngày, ăn ngon")

    assert trip_spec.days == 5


def test_default_trip_spec_keeps_missing_duration_unset() -> None:
    trip_spec = _default_trip_spec("https://example.com/reel?q=what+to+do+hanoi")

    assert trip_spec.days is None


def test_destination_can_be_inferred_from_tiktok_search_query() -> None:
    destination = _infer_destination_from_urls(
        [
            "https://www.tiktok.com/@creator/video/123"
            "?q=what%20to%20do%20in%20hanoi%3F"
        ]
    )

    assert destination == "Hanoi"


def test_destination_query_inference_remains_global() -> None:
    destination = _infer_destination_from_urls(
        ["https://example.com/video?q=things%20to%20do%20in%20paris%3F"]
    )

    assert destination == "Paris"
