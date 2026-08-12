from decimal import Decimal, ROUND_HALF_UP

from app.modules.explorer.contract import ExplorerBudget, ExplorerPeople


def normalize_budget_per_person(
    budget: ExplorerBudget,
    people: ExplorerPeople,
) -> ExplorerBudget:
    """Convert a group-total budget to a conservative per-traveler amount."""
    if budget.target_amount is None or budget.basis == "per_person":
        return budget

    traveler_count = people.total
    amount = (
        Decimal(budget.target_amount) / Decimal(traveler_count)
    ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return budget.model_copy(
        update={"target_amount": int(amount), "basis": "per_person"}
    )
