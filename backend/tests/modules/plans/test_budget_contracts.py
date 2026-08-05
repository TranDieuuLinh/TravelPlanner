import pytest
from pydantic import ValidationError

from app.modules.plans.dto.agent_contracts import BudgetEnvelope, PlanningIntent
from app.modules.plans.explorer.schema import ExploreBundleDraft, ExploreTripSpecInput


def test_budget_envelope_has_only_target_amount_and_level() -> None:
    budget = BudgetEnvelope.model_validate(
        {
            "targetAmount": 6_000_000,
            "currency": "vnd",
            "level": "medium",
        }
    )

    assert budget.model_dump(mode="json", by_alias=True) == {
        "targetAmount": 6_000_000,
        "currency": "VND",
        "level": "medium",
    }
    assert set(budget.model_json_schema()["properties"]) == {
        "targetAmount",
        "currency",
        "level",
    }


def test_explorer_budget_input_uses_same_simple_shape() -> None:
    trip_spec = ExploreTripSpecInput.model_validate(
        {
            "days": 3,
            "partySize": 2,
            "budget": {
                "targetAmount": 6_000_000,
                "currency": "VND",
                "level": "medium",
            },
        }
    )

    assert trip_spec.budget.model_dump(mode="json", by_alias=True) == {
        "targetAmount": 6_000_000,
        "currency": "VND",
        "level": "medium",
    }


def test_explore_bundle_keeps_budget_only_under_trip_intent() -> None:
    response = ExploreBundleDraft.model_validate(
        {
            "explorer": {
                "tripIntent": {
                    "destination": "Hà Nội",
                    "timing": {"days": 3},
                    "travelParty": {"type": "couple", "adults": 2},
                    "budget": {
                        "targetAmount": 6_000_000,
                        "currency": "VND",
                        "level": "medium",
                    },
                },
            },
            "places": {"placeCandidates": []},
        }
    )

    payload = response.model_dump(mode="json", by_alias=True)

    assert "intent" not in payload["explorer"]
    assert "tripSpec" not in payload["explorer"]
    assert payload["explorer"]["tripIntent"]["budget"] == {
        "targetAmount": 6_000_000,
        "currency": "VND",
        "level": "medium",
    }


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_budget_envelope_accepts_supported_levels(level: str) -> None:
    budget = BudgetEnvelope.model_validate({"level": level})

    assert budget.level.value == level


def test_budget_envelope_rejects_legacy_budget_level_name() -> None:
    with pytest.raises(ValidationError):
        BudgetEnvelope.model_validate({"level": "budget"})


def test_planning_intent_has_no_budget_field() -> None:
    intent = PlanningIntent.model_validate(
        {
            "destination": "Hà Nội",
            "budgetLevel": "high",
        }
    )

    payload = intent.model_dump(mode="json", by_alias=True)
    assert "budgetLevel" not in payload
    assert "budget" not in payload
