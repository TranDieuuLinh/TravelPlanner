from app.modules.plans.router import _infer_destination


def test_destination_inference_never_uses_the_whole_prompt_as_region() -> None:
    assert (
        _infer_destination(
            "Hãy lấy itinerary Hà Nội từ video này và đưa các địa điểm lên bản đồ"
        )
        == "Hanoi"
    )


def test_destination_inference_rejects_long_unknown_instruction() -> None:
    assert (
        _infer_destination(
            "Hãy lấy itinerary từ nguồn này rồi đưa tất cả địa điểm lên bản đồ"
        )
        == ""
    )


def test_destination_inference_keeps_compact_unknown_destination() -> None:
    assert _infer_destination("Tạo lịch trình Kyoto 3 ngày") == "Kyoto"
    assert _infer_destination("Tôi muốn đi Kyoto 3 ngày") == "Kyoto"


def test_destination_inference_rejects_short_non_destination_amendment() -> None:
    assert _infer_destination("thêm món địa phương") == ""
