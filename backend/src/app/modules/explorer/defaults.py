from app.modules.explorer.contract import (
    ExplorerBudget,
    ExplorerPeople,
)
from app.modules.explorer.review_types import ExplorerDefaultedField
from app.shared.tools.daily_budget import DestinationDailyBudgetEstimator


def defaulted_fields(
    *,
    days: int | None,
    budget: ExplorerBudget,
    people: ExplorerPeople,
    people_explicit: bool,
    preferences_explicit: bool,
) -> list[ExplorerDefaultedField]:
    fields: list[ExplorerDefaultedField] = []
    if days is None:
        fields.append("days")
    if budget.source == "default":
        fields.append("budget")
    if not people_explicit and people == ExplorerPeople():
        fields.append("people")
    if not preferences_explicit:
        fields.append("shortPreferences")
    return fields


def estimate_budget_if_needed(
    budget: ExplorerBudget,
    *,
    destination: str | None,
    days: int,
    people: ExplorerPeople,
    estimator: DestinationDailyBudgetEstimator,
    force: bool = False,
) -> ExplorerBudget:
    if not destination or (budget.target_amount is not None and not force):
        return budget
    estimate = estimator.estimate(
        destination=destination,
        level=budget.level,
        people=people.total,
        days=days,
    )
    if estimate is None:
        return budget
    return budget.model_copy(
        update={
            "target_amount": estimate.total_per_person,
            "currency": estimate.daily_cost.currency,
            "basis": "per_person",
        }
    )
