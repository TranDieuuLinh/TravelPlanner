from app.modules.explorer.contract import ExplorerBudget, ExplorerPeople
from app.modules.explorer.tools import normalize_budget_per_person


def test_group_total_is_divided_across_all_travelers() -> None:
    result = normalize_budget_per_person(
        ExplorerBudget(targetAmount=10_000_000, source="raw_prompt"),
        ExplorerPeople(adults=2, children=1, infants=1),
    )

    assert result.target_amount == 2_500_000
    assert result.basis == "per_person"


def test_explicit_per_person_budget_is_not_divided_again() -> None:
    result = normalize_budget_per_person(
        ExplorerBudget(
            targetAmount=2_000_000,
            source="raw_prompt",
            basis="per_person",
        ),
        ExplorerPeople(adults=4),
    )

    assert result.target_amount == 2_000_000
    assert result.basis == "per_person"


def test_amount_rounds_to_nearest_currency_unit() -> None:
    result = normalize_budget_per_person(
        ExplorerBudget(targetAmount=10, currency="USD", source="raw_prompt"),
        ExplorerPeople(adults=3),
    )

    assert result.target_amount == 3
