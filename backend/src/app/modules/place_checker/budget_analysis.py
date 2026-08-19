from dataclasses import dataclass
from decimal import Decimal

from app.modules.place_checker.analysis_contract import (
    AmountRangeAnalysis,
    BudgetAnalysis,
    CostGroupAnalysis,
)
from app.modules.place_checker.contract import TripEvaluationContext
from app.modules.place_checker.enums import (
    BudgetAssessmentStatus,
    BudgetMode,
    CostTier,
    ItemResolutionStatus,
    PlaceLifecycleState,
)
from app.modules.place_checker.evaluation_contract import PlaceEvaluationBatch
from app.modules.place_checker.item_contract import ItemResolutionBatch


@dataclass(frozen=True)
class _CostRecord:
    place_id: str
    tier: CostTier
    currency: str | None
    minimum: Decimal | None
    typical: Decimal | None
    maximum: Decimal | None


class BudgetAnalysisService:
    def analyze(
        self,
        places: PlaceEvaluationBatch,
        items: ItemResolutionBatch,
        context: TripEvaluationContext,
    ) -> BudgetAnalysis:
        mandatory, optional = self._records(places, items)
        all_records = [*mandatory, *optional]
        currency = self._analysis_currency(all_records, context)
        mandatory_analysis = self._group(mandatory, currency)
        optional_analysis = self._group(optional, currency)
        total_analysis = self._group(all_records, currency)
        status = self._status(total_analysis, context)
        warnings: list[str] = []
        if total_analysis.unknown_amount_count:
            warnings.append(
                f"{total_analysis.unknown_amount_count} place(s) chưa đủ amount/currency."
            )
        currencies = {record.currency for record in all_records if record.currency}
        if len(currencies) > 1:
            warnings.append("Có nhiều currency; amount khác currency không được cộng chung.")
        return BudgetAnalysis(
            mode=context.budget_mode,
            status=status,
            target_amount=context.budget.target_amount,
            currency=currency,
            mandatory=mandatory_analysis,
            optional=optional_analysis,
            total=total_analysis,
            warnings=warnings,
        )

    @classmethod
    def _records(
        cls,
        places: PlaceEvaluationBatch,
        items: ItemResolutionBatch,
    ) -> tuple[list[_CostRecord], list[_CostRecord]]:
        mandatory: list[_CostRecord] = []
        optional: list[_CostRecord] = []
        seen_ids: set[str] = set()
        for index, evaluation in enumerate(places.places):
            place = evaluation.place
            if not place.mandatory and evaluation.state == PlaceLifecycleState.rejected:
                continue
            identity = place.place_id or f"unresolved:{index}"
            seen_ids.add(identity)
            record = cls._place_record(identity, place.metadata)
            (mandatory if place.mandatory else optional).append(record)
        for item in items.items:
            if (
                item.status != ItemResolutionStatus.resolved
                or item.selected is None
                or item.selected.place_id in seen_ids
            ):
                continue
            seen_ids.add(item.selected.place_id)
            optional.append(
                _CostRecord(
                    place_id=item.selected.place_id,
                    tier=item.selected.cost_tier,
                    currency=None,
                    minimum=None,
                    typical=None,
                    maximum=None,
                )
            )
        return mandatory, optional

    @staticmethod
    def _place_record(place_id, metadata) -> _CostRecord:
        if metadata is None:
            return _CostRecord(place_id, CostTier.unknown, None, None, None, None)
        free = metadata.cost_tier == CostTier.free
        return _CostRecord(
            place_id=place_id,
            tier=metadata.cost_tier,
            currency=metadata.cost_currency,
            minimum=BudgetAnalysisService._amount(metadata.minimum_cost, free),
            typical=BudgetAnalysisService._amount(metadata.typical_cost, free),
            maximum=BudgetAnalysisService._amount(metadata.maximum_cost, free),
        )

    @staticmethod
    def _amount(value: float | None, free: bool) -> Decimal | None:
        if value is not None:
            return Decimal(str(value))
        return Decimal("0") if free else None

    @staticmethod
    def _analysis_currency(
        records: list[_CostRecord],
        context: TripEvaluationContext,
    ) -> str | None:
        if context.budget.currency:
            return context.budget.currency
        currencies = {record.currency for record in records if record.currency}
        return next(iter(currencies)) if len(currencies) == 1 else None

    @classmethod
    def _group(
        cls,
        records: list[_CostRecord],
        currency: str | None,
    ) -> CostGroupAnalysis:
        tiers = {tier.value: 0 for tier in CostTier}
        for record in records:
            tiers[record.tier.value] += 1
        valid = [
            record
            for record in records
            if record.tier == CostTier.free
            or (currency is not None and record.currency == currency)
        ]
        complete_records = [
            record
            for record in valid
            if None not in (record.minimum, record.typical, record.maximum)
        ]
        complete = len(complete_records) == len(records)
        return CostGroupAnalysis(
            place_count=len(records),
            known_amount_count=len(complete_records),
            unknown_amount_count=len(records) - len(complete_records),
            amount_range=AmountRangeAnalysis(
                minimum=cls._sum(record.minimum for record in valid),
                typical=cls._sum(record.typical for record in valid),
                maximum=cls._sum(record.maximum for record in valid),
                currency=currency,
                complete=complete,
            ),
            tier_distribution=tiers,
        )

    @staticmethod
    def _sum(values) -> Decimal | None:
        known = [value for value in values if value is not None]
        return sum(known, Decimal("0")) if known else None

    @staticmethod
    def _status(
        total: CostGroupAnalysis,
        context: TripEvaluationContext,
    ) -> BudgetAssessmentStatus:
        amount = total.amount_range
        target = context.budget.target_amount
        if total.place_count == 0:
            return BudgetAssessmentStatus.unknown
        if context.budget_mode == BudgetMode.target_amount and target is not None:
            if amount.minimum is not None and amount.minimum > target:
                return BudgetAssessmentStatus.over
            if not amount.complete:
                return BudgetAssessmentStatus.unknown
            if amount.maximum is not None and amount.maximum <= target:
                return BudgetAssessmentStatus.within
            return BudgetAssessmentStatus.at_risk

        tiers = total.tier_distribution
        known_tier_count = total.place_count - tiers.get(CostTier.unknown.value, 0)
        if total.place_count == 0 or known_tier_count == 0:
            return BudgetAssessmentStatus.unknown
        if tiers.get(CostTier.unknown.value, 0):
            return BudgetAssessmentStatus.at_risk
        if context.budget.level == "low" and (
            tiers.get(CostTier.medium.value, 0)
            + tiers.get(CostTier.high.value, 0)
            + tiers.get(CostTier.premium.value, 0)
        ):
            return BudgetAssessmentStatus.at_risk
        if context.budget.level == "medium" and (
            tiers.get(CostTier.high.value, 0)
            + tiers.get(CostTier.premium.value, 0)
        ):
            return BudgetAssessmentStatus.at_risk
        return BudgetAssessmentStatus.within
