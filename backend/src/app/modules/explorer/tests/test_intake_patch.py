import pytest

from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.contract import ExplorerBudget, ExplorerOutput, ExplorerPeople
from app.modules.explorer.intake_patch import (
    TripContextPatch,
    apply_trip_context_patch,
)


def output() -> ExplorerOutput:
    return ExplorerOutput(
        status="ready",
        intakeId="intake-patch",
        input_ADM="Hà Nội",
        days=3,
        budget=ExplorerBudget(
            level="low",
            targetAmount=2_500_000,
            source="raw_prompt",
            basis="per_person",
        ),
        people=ExplorerPeople(adults=2),
        shortPreferences=["Văn hóa", "nightlife"],
        shortAvoids=[],
        specialNotes=["mang ô"],
    )


def test_scalar_operations_apply_without_confirmation() -> None:
    patch = TripContextPatch.model_validate(
        {
            "inputADM": {"operation": "set", "value": "Huế"},
            "days": {"operation": "increment", "value": 1},
            "people": {
                "operation": "decrement",
                "value": {"adults": 1},
            },
            "budget": {
                "operation": "set",
                "value": {
                    "amountPerPerson": 3_000_000,
                    "currency": "VND",
                    "level": "medium",
                },
            },
        }
    )

    result = apply_trip_context_patch(
        output(), patch, raw_user_message="Đổi sang Huế, thêm một ngày"
    )

    assert result.input_adm == "Huế"
    assert result.days == 4
    assert result.people.adults == 1
    assert result.budget.target_amount == 3_000_000
    assert result.budget.basis == "per_person"


def test_collection_operations_and_avoid_conflict(tmp_path) -> None:
    tags = tmp_path / "tags-auto.yml"
    tags.write_text(
        "Văn hóa: [culture]\n"
        "thiên nhiên: [nature]\n"
        "nightlife: [nightlife]\n",
        encoding="utf-8",
    )
    patch = TripContextPatch.model_validate(
        {
            "places": {
                "operation": "add",
                "values": [{"name": "Văn Miếu - Quốc Tử Giám"}],
            },
            "shortPreferences": {
                "operation": "add",
                "values": ["nature"],
            },
            "shortAvoids": {
                "operation": "add",
                "values": ["nightlife"],
            },
            "specialNotes": {"operation": "clear"},
        }
    )

    result = apply_trip_context_patch(
        output(),
        patch,
        raw_user_message="Thêm Văn Miếu, thích thiên nhiên, không thích nightlife",
        tag_catalog=YamlTagCatalog(tags),
    )

    assert [place.name for place in result.places or []] == [
        "Văn Miếu - Quốc Tử Giám"
    ]
    assert result.short_preferences == ["Văn hóa", "thiên nhiên"]
    assert result.short_avoids == ["nightlife"]
    assert result.special_notes == []


def test_reset_adm_is_the_only_blocking_default() -> None:
    patch = TripContextPatch.model_validate(
        {
            "inputADM": {"operation": "reset_to_default"},
            "days": {"operation": "reset_to_default"},
            "people": {"operation": "reset_to_default"},
            "budget": {"operation": "reset_to_default"},
        }
    )

    result = apply_trip_context_patch(output(), patch, raw_user_message="Dùng mặc định")

    assert result.status == "clarification"
    assert result.input_adm is None
    assert result.days == 3
    assert result.people.adults == 2
    assert result.budget.level == "low"
    assert result.budget.target_amount is None


def test_invalid_patch_operation_is_rejected() -> None:
    with pytest.raises(ValueError):
        TripContextPatch.model_validate(
            {"inputADM": {"operation": "increment", "value": "Huế"}}
        )


def test_remove_item_only_requires_its_name() -> None:
    patch = TripContextPatch.model_validate(
        {
            "inputItems": {
                "operation": "remove",
                "values": [{"name": "phở"}],
            }
        }
    )

    assert patch.input_items.values[0].item_type is None


def test_adm_follow_up_applies_hidden_insight_defaults() -> None:
    class Insight:
        def enrich(self, **kwargs):
            assert kwargs["budget_level"] == "low"
            return ["giá rẻ", "địa phương", "Văn hóa"], ["sang trọng"]

    missing_adm = ExplorerOutput(
        status="clarification",
        intakeId="intake-adm-follow-up",
        input_ADM=None,
    )
    patch = TripContextPatch.model_validate(
        {"inputADM": {"operation": "set", "value": "Hà Nội"}}
    )

    result = apply_trip_context_patch(
        missing_adm,
        patch,
        raw_user_message="Hà Nội",
        insight_catalog=Insight(),
    )

    assert result.status == "ready"
    assert result.short_preferences == ["giá rẻ", "địa phương", "Văn hóa"]
    assert result.short_avoids == ["sang trọng"]
