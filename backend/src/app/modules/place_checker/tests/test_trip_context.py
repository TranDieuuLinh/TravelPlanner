import asyncio

from app.modules.place_checker.contract import (
    AdmResolution,
    AdmResolutionStatus,
    BudgetMode,
    PlaceCheckerInput,
)
from app.modules.place_checker.service import TripContextBuilder
from app.modules.place_checker.tests.test_contract import sample_payload


class FakeAdmResolver:
    def __init__(self, result: AdmResolution) -> None:
        self.result = result
        self.calls: list[str] = []

    async def resolve(self, input_name: str) -> AdmResolution:
        self.calls.append(input_name)
        return self.result


def resolved_hanoi() -> AdmResolution:
    return AdmResolution(
        input_name="Hanoi",
        status=AdmResolutionStatus.resolved,
        adm_id="adm1_vn_ha_noi",
        canonical_name="Hà Nội",
        country_code="VN",
        region_key="vn,ha_noi",
    )


def test_builds_relative_budget_trip_context() -> None:
    raw = sample_payload()
    raw["input_ADM"] = "  Hanoi  "
    raw["short_preferences"] = [" Food ", "food"]
    resolver = FakeAdmResolver(resolved_hanoi())

    context = asyncio.run(
        TripContextBuilder(resolver).build(PlaceCheckerInput.model_validate(raw))
    )

    assert resolver.calls == ["Hanoi"]
    assert context.destination.adm_id == "adm1_vn_ha_noi"
    assert context.destination.canonical_name == "Hà Nội"
    assert context.budget_mode == BudgetMode.relative_level
    assert context.budget.target_amount is None
    assert context.capacity.minimum_minutes == 4 * 360
    assert context.capacity.typical_minutes == 4 * 480
    assert context.capacity.maximum_minutes == 4 * 600
    assert context.preferences == ["food"]
    assert context.avoids == ["nightlife"]


def test_target_amount_uses_monetary_mode() -> None:
    raw = sample_payload()
    raw["budget"]["target_amount"] = 2_000_000
    resolver = FakeAdmResolver(resolved_hanoi())

    context = asyncio.run(
        TripContextBuilder(resolver).build(PlaceCheckerInput.model_validate(raw))
    )

    assert context.budget_mode == BudgetMode.target_amount
    assert context.budget.target_amount == 2_000_000


def test_preserves_ambiguous_adm_for_later_clarification() -> None:
    resolver = FakeAdmResolver(
        AdmResolution(
            input_name="Springfield",
            status=AdmResolutionStatus.ambiguous,
            alternatives=["adm_us_il_springfield", "adm_us_ma_springfield"],
        )
    )
    raw = sample_payload()
    raw["input_ADM"] = "Springfield"

    context = asyncio.run(
        TripContextBuilder(resolver).build(PlaceCheckerInput.model_validate(raw))
    )

    assert context.destination.status == AdmResolutionStatus.ambiguous
    assert len(context.destination.alternatives) == 2

