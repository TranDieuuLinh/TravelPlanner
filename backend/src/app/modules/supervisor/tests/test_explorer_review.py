from app.modules.explorer.public import ExplorerReview
from app.modules.supervisor.explorer_review import (
    compose_explorer_review,
    parse_explorer_review_patch,
)


TAGS = {
    "giá rẻ": ["budget"],
    "thiên nhiên": ["nature"],
    "nightlife": ["nightlife"],
}


def missing_review() -> ExplorerReview:
    return ExplorerReview(
        kind="missing_fields",
        intakeId="missing-1",
        missingFields=["inputADM"],
    )


def defaults_review() -> ExplorerReview:
    return ExplorerReview.model_validate({
        "kind": "defaults_proposed",
        "intakeId": "defaults-1",
        "defaultedFields": ["budget", "people", "shortPreferences"],
        "tripContext": {
            "inputADM": "Hanoi",
            "days": 2,
            "budget": {
                "level": "low",
                "amountPerPerson": 1_172_432,
            },
            "people": {"adults": 2},
            "shortPreferences": ["giá rẻ", "thiên nhiên"],
        },
    })


def test_missing_destination_reply_becomes_patch() -> None:
    patch = parse_explorer_review_patch(
        "Hà Nội, 4 ngày", missing_review(), tag_definitions=TAGS
    )

    assert patch is not None
    assert patch.input_adm.value == "Hà Nội"
    assert patch.days.value == 4


def test_accepting_defaults_returns_empty_patch() -> None:
    for reply in ("OK", "Không", "Không cần chỉnh"):
        patch = parse_explorer_review_patch(
            reply, defaults_review(), tag_definitions=TAGS
        )

        assert patch is not None
        assert patch.model_dump(exclude_none=True) == {}


def test_edit_reply_uses_runtime_taxonomy_keys() -> None:
    patch = parse_explorer_review_patch(
        "Đi 4 ngày, 3 người, thích nature và không thích nightlife",
        defaults_review(),
        tag_definitions=TAGS,
    )

    assert patch.days.value == 4
    assert patch.people.value.adults == 3
    assert patch.short_preferences.operation == "replace"
    assert patch.short_preferences.values == ["giá rẻ", "thiên nhiên"]
    assert patch.short_avoids.values == ["nightlife"]


def test_supervisor_review_never_mentions_avoid_tags() -> None:
    response, clarification = compose_explorer_review(defaults_review())

    assert "1.172.432" in response
    assert "nightlife" not in response
    assert clarification == response


def test_place_and_item_edits_use_collection_operations() -> None:
    place_patch = parse_explorer_review_patch(
        "Thêm Văn Miếu - Quốc Tử Giám",
        defaults_review(),
        tag_definitions=TAGS,
    )
    item_patch = parse_explorer_review_patch(
        "Muốn ăn phở",
        defaults_review(),
        tag_definitions=TAGS,
    )

    assert place_patch.places.operation == "add"
    assert place_patch.places.values[0].name == "Văn Miếu - Quốc Tử Giám"
    assert item_patch.input_items.operation == "add"
    assert item_patch.input_items.values[0].item_type == "food"


def test_budget_delta_uses_increment_operation() -> None:
    patch = parse_explorer_review_patch(
        "Tăng ngân sách thêm 1 triệu",
        defaults_review(),
        tag_definitions=TAGS,
    )

    assert patch.budget.operation == "increment"
    assert patch.budget.value.amount_per_person == 1_000_000


def test_people_breakdown_and_child_delta_keep_structured_fields() -> None:
    breakdown = parse_explorer_review_patch(
        "2 người lớn, 1 trẻ em, 1 em bé",
        defaults_review(),
        tag_definitions=TAGS,
    )
    increment = parse_explorer_review_patch(
        "Thêm 1 trẻ em",
        defaults_review(),
        tag_definitions=TAGS,
    )

    assert breakdown.people.operation == "set"
    assert breakdown.people.value.model_dump() == {
        "adults": 2,
        "children": 1,
        "infants": 1,
    }
    assert increment.people.operation == "increment"
    assert increment.people.value.children == 1


def test_remove_preference_does_not_implicitly_add_an_avoid() -> None:
    patch = parse_explorer_review_patch(
        "Bỏ nightlife",
        defaults_review(),
        tag_definitions=TAGS,
    )

    assert patch.short_preferences.operation == "remove"
    assert patch.short_preferences.values == ["nightlife"]
    assert patch.short_avoids is None
