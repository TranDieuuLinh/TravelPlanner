import pytest
from pydantic import ValidationError

from app.modules.plans.dto.agent_contracts import BudgetEnvelope, PlanningIntent
from app.modules.plans.explorer.response_formatter import _complete_budget_basis
from app.modules.plans.explorer.schema import ExploreResponse, ExploreTripSpecInput


def test_budget_envelope_serializes_explorer_json_shape() -> None:
    budget = BudgetEnvelope.model_validate(
        {
            "inputMode": "qualitative",
            "minAmount": 4_300_000,
            "targetAmount": 4_800_000,
            "maxAmount": 5_400_000,
            "currency": "vnd",
            "isHardCap": False,
            "confidence": "medium",
            "calculationBasis": {
                "partySize": 2,
                "days": 3,
                "nights": 2,
                "destination": "Đà Nẵng",
                "priceTier": "budget",
            },
            "notes": "Ước tính từ mức chi tiêu thấp.",
        }
    )

    payload = budget.model_dump(mode="json", by_alias=True)

    assert payload["inputMode"] == "qualitative"
    assert payload["targetAmount"] == 4_800_000
    assert payload["currency"] == "VND"
    assert payload["calculationBasis"]["priceTier"] == "budget"
    assert "includeHotel" not in payload
    assert "totalBudget" not in payload


def test_explorer_budget_input_accepts_partial_hard_cap() -> None:
    trip_spec = ExploreTripSpecInput.model_validate(
        {
            "days": 4,
            "partySize": 2,
            "budget": {
                "inputMode": "exact",
                "maxAmount": 5_000_000,
                "currency": "VND",
                "isHardCap": True,
                "confidence": "high",
            },
        }
    )

    assert trip_spec.budget.max_amount == 5_000_000
    assert trip_spec.budget.is_hard_cap is True


def test_explorer_completes_budget_calculation_basis() -> None:
    response = ExploreResponse.model_validate(
        {
            "intent": {
                "destination": "Đà Nẵng",
                "budgetLevel": "budget",
            },
            "tripSpec": {
                "days": 3,
                "partySize": 2,
                "budget": {
                    "inputMode": "qualitative",
                    "currency": "VND",
                    "confidence": "low",
                },
            },
        }
    )

    completed = _complete_budget_basis(response)

    assert completed.trip_spec.budget.calculation_basis is not None
    assert completed.trip_spec.budget.calculation_basis.nights == 2
    assert completed.trip_spec.budget.calculation_basis.price_tier.value == "budget"


@pytest.mark.parametrize("budget_level", ["budget", "medium", "high"])
def test_planning_intent_accepts_supported_budget_levels(budget_level: str) -> None:
    intent = PlanningIntent.model_validate(
        {"destination": "Đà Nẵng", "budgetLevel": budget_level}
    )

    assert intent.budget_level.value == budget_level


def test_planning_intent_rejects_legacy_balanced_budget_level() -> None:
    with pytest.raises(ValidationError):
        PlanningIntent.model_validate(
            {"destination": "Đà Nẵng", "budgetLevel": "balanced"}
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "inputMode": "range",
            "minAmount": 6_000_000,
            "targetAmount": 5_000_000,
            "maxAmount": 4_000_000,
        },
        {
            "inputMode": "exact",
            "targetAmount": 5_000_000,
            "isHardCap": True,
        },
    ],
)
def test_budget_envelope_rejects_invalid_limits(payload: dict) -> None:
    with pytest.raises(ValidationError):
        BudgetEnvelope.model_validate(payload)
