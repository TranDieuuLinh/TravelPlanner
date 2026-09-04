import logging

from app.modules.explorer.contract import ExplorerBudget, ExplorerOutput
from app.modules.explorer.defaults import defaulted_fields, estimate_budget_if_needed
from app.modules.explorer.models import (
    BatchCoverage,
    ExplorerDraft,
    SourceExtractionResult,
)
from app.modules.explorer.ports import InsightCatalog
from app.modules.explorer.source_warnings import source_warnings
from app.modules.explorer.tools import normalize_budget_per_person
from app.modules.explorer.trip_defaults import timezone_for_destination, tomorrow
from app.shared.tools.daily_budget import DestinationDailyBudgetEstimator

logger = logging.getLogger(__name__)


def finalize_explorer_output(
    *,
    intake_id: str,
    draft: ExplorerDraft,
    input_adm: str | None,
    adm_conflict: bool,
    coverage: BatchCoverage | None,
    source_results: list[SourceExtractionResult] | None,
    insight_catalog: InsightCatalog | None,
    budget_estimator: DestinationDailyBudgetEstimator,
) -> ExplorerOutput:
    warnings = source_warnings(coverage, source_results)
    timezone = timezone_for_destination(input_adm)
    start_date = draft.start_date or tomorrow()
    budget = draft.budget
    review_defaulted_fields = defaulted_fields(
        days=draft.days,
        budget=budget,
        people=draft.people,
        people_explicit=draft.people_explicit,
        preferences_explicit=draft.preferences_explicit,
    )
    if budget.source == "default":
        budget = ExplorerBudget(level="low", source="default")
    budget = normalize_budget_per_person(budget, draft.people)
    days = draft.days or 3
    budget = estimate_budget_if_needed(
        budget,
        destination=input_adm,
        days=days,
        people=draft.people,
        estimator=budget_estimator,
    )
    preference_inputs = list(draft.short_preferences)
    avoid_inputs = list(draft.short_avoids)
    if input_adm and insight_catalog is not None:
        try:
            preferences, avoids = insight_catalog.enrich(
                budget_level=budget.level,
                children=draft.people.children,
                infants=draft.people.infants,
                preferences=draft.short_preferences,
                avoids=draft.short_avoids,
                seed=f"{intake_id}:{input_adm}:{budget.level}",
            )
            draft = draft.model_copy(
                update={
                    "short_preferences": preferences,
                    "short_avoids": avoids,
                }
            )
        except (OSError, ValueError):
            logger.warning("Explorer user-insight catalog is unavailable", exc_info=True)
            warnings.append(
                "Không thể áp dụng nhóm sở thích mặc định từ insight-user.yml."
            )
    common = {
        "intakeId": intake_id,
        "places": draft.places or None,
        "inputItems": draft.input_items or None,
        "urlNotes": draft.url_notes or None,
        "days": days,
        "startDate": start_date,
        "timezone": timezone,
        "budget": budget,
        "people": draft.people,
        "shortPreferences": draft.short_preferences,
        "shortAvoids": draft.short_avoids,
        "preferenceInputs": preference_inputs,
        "avoidInputs": avoid_inputs,
        "specialNotes": draft.special_notes,
        "defaultedFields": review_defaulted_fields,
        "warnings": warnings,
    }
    if not input_adm:
        question = (
            "Các nguồn có địa điểm hành chính mâu thuẫn. Bạn muốn đi đâu?"
            if adm_conflict
            else "Bạn muốn đi tỉnh hoặc thành phố nào?"
        )
        return ExplorerOutput(
            status="clarification",
            input_ADM=None,
            clarificationQuestion=question,
            **common,
        )
    status = "partial" if coverage == "partial" else "ready"
    return ExplorerOutput(
        status=status,
        input_ADM=input_adm,
        **common,
    )
