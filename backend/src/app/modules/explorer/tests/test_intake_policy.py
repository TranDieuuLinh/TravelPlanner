from app.modules.explorer.contract import RequestedItem
from app.modules.explorer.intake_policy import normalize_intake_items
from app.modules.explorer.service import ExplorerService


def item(name: str, evidence: str, *, related_place_name: str | None = None):
    return RequestedItem(
        name=name,
        itemType="activity" if name != "phở" else "food",
        action="visit" if name != "phở" else "eat",
        relatedPlaceName=related_place_name,
        evidence=evidence,
        confidence=0.9,
    )


def test_semantic_item_categories_are_preserved_from_llm_output() -> None:
    prompt = "Thích văn hóa và ẩm thực, buổi tối đi dạo; muốn ăn phở"

    items, preferences = normalize_intake_items(
        [
            item("văn hóa", "Thích văn hóa"),
            item("ẩm thực", "ẩm thực"),
            item("đi dạo", "buổi tối đi dạo"),
            item("phở", "muốn ăn phở"),
        ],
        ["culture", "local_food", "walking"],
        prompt,
        normalize=ExplorerService._key,
    )

    assert [value.name for value in items] == ["văn hóa", "ẩm thực", "đi dạo", "phở"]
    assert preferences == ["culture", "local_food", "walking"]


def test_named_venue_request_is_not_demoted() -> None:
    request = item(
        "văn hóa",
        "thích trải nghiệm văn hóa tại Văn Miếu",
        related_place_name="Văn Miếu",
    )

    items, preferences = normalize_intake_items(
        [request],
        [],
        request.evidence,
        normalize=ExplorerService._key,
    )

    assert items == [request]
    assert preferences == []
