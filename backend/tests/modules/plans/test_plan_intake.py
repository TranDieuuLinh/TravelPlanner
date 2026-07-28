import pytest

from app.modules.plans.router import _prepare_intake, _remove_urls


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
    with pytest.raises(ValueError, match="prompt or URL"):
        _prepare_intake("", explicit_urls=[])


def test_intake_uses_plain_text_when_no_url_or_image_exists() -> None:
    assert _prepare_intake(
        "Hà Nội 3 ngày, ưu tiên ẩm thực",
        explicit_urls=[],
    ) == ("Hà Nội 3 ngày, ưu tiên ẩm thực", [])


def test_intake_rejects_an_empty_message() -> None:
    with pytest.raises(ValueError, match="prompt or URL"):
        _prepare_intake("", explicit_urls=[])
