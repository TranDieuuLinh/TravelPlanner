from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import (
    FoodVenueType,
    MealType,
    PlannerFoodCandidate,
)
from app.modules.itinerary_planner.policies import (
    MAX_DRINK_DESSERTS_PER_DAY,
    MEAL_POLICIES,
    MINIMUM_MEAL_START_GAPS,
    OVERNIGHT_END_MINUTE,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem

CandidateDay = tuple[str, int]
MealKey = tuple[str, int, MealType]
SourceMixKey = tuple[str, int, str]
MIN_PLACES_PER_DAY = 2
MAX_ENTERTAINMENT_PER_DAY = 1


@dataclass(slots=True)
class PlannerVariables:
    selected: dict[str, cp_model.IntVar] = field(default_factory=dict)
    assigned: dict[CandidateDay, cp_model.IntVar] = field(default_factory=dict)
    start: dict[CandidateDay, cp_model.IntVar] = field(default_factory=dict)
    end: dict[CandidateDay, cp_model.IntVar] = field(default_factory=dict)
    meal: dict[MealKey, cp_model.IntVar] = field(default_factory=dict)
    meal_start: dict[tuple[int, MealType], cp_model.IntVar] = field(
        default_factory=dict
    )
    intervals_by_day: dict[int, list[cp_model.IntervalVar]] = field(
        default_factory=dict
    )
    arc: dict[tuple[str, str, int], cp_model.IntVar] = field(default_factory=dict)
    night_arc: dict[tuple[str, str, int], cp_model.IntVar] = field(default_factory=dict)
    waiting: dict[tuple[str, str, int], cp_model.IntVar] = field(default_factory=dict)
    source_period: dict[SourceMixKey, cp_model.IntVar] = field(default_factory=dict)
    source_special: dict[SourceMixKey, cp_model.IntVar] = field(default_factory=dict)
    source_offer: dict[SourceMixKey, cp_model.IntVar] = field(default_factory=dict)
    accommodation_selected: dict[str, cp_model.IntVar] = field(default_factory=dict)
    accommodation_transfer: dict[tuple[str, str, int, str], cp_model.IntVar] = field(
        default_factory=dict
    )
    accommodation_night_transfer: dict[tuple[str, str, int, str], cp_model.IntVar] = (
        field(default_factory=dict)
    )
    first_start: dict[int, cp_model.IntVar] = field(default_factory=dict)
    last_end: dict[int, cp_model.IntVar] = field(default_factory=dict)
    total_cost: cp_model.IntVar | None = None
    budget_overage_units: cp_model.IntVar | None = None
    all_decision_vars: list[cp_model.IntVar] = field(default_factory=list)

    def remember(self, variable: cp_model.IntVar) -> cp_model.IntVar:
        self.all_decision_vars.append(variable)
        return variable


def create_schedule_variables(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
) -> PlannerVariables:
    variables = PlannerVariables(
        intervals_by_day={day: [] for day in range(1, problem.trip.days + 1)}
    )
    for accommodation in problem.accommodations:
        variables.accommodation_selected[accommodation.place_id] = variables.remember(
            model.NewBoolVar(f"accommodation:{accommodation.place_id}")
        )
    if variables.accommodation_selected:
        model.Add(sum(variables.accommodation_selected.values()) == 1)
        _exclude_dominated_accommodations(model, problem, variables)
    food_ids = {food.place_id for food in problem.valid_food}
    for candidate_id in sorted(problem.candidate_by_id):
        selected = variables.remember(model.NewBoolVar(f"selected:{candidate_id}"))
        variables.selected[candidate_id] = selected
        assignments = []
        for day in sorted(problem.feasible_days[candidate_id]):
            assigned = variables.remember(
                model.NewBoolVar(f"assigned:{candidate_id}:{day}")
            )
            start = variables.remember(
                model.NewIntVar(0, OVERNIGHT_END_MINUTE, f"start:{candidate_id}:{day}")
            )
            end = variables.remember(
                model.NewIntVar(0, OVERNIGHT_END_MINUTE, f"end:{candidate_id}:{day}")
            )
            variables.assigned[(candidate_id, day)] = assigned
            variables.start[(candidate_id, day)] = start
            variables.end[(candidate_id, day)] = end
            assignments.append(assigned)
            model.Add(start == 0).OnlyEnforceIf(assigned.Not())
            model.Add(end == 0).OnlyEnforceIf(assigned.Not())

            candidate = problem.candidate_by_id[candidate_id]
            if candidate_id in food_ids:
                _create_food_intervals(
                    model, problem, variables, candidate, day, assigned, start, end
                )
            else:
                _create_activity_interval(
                    model, problem, variables, candidate_id, day, assigned, start, end
                )
        model.Add(selected == sum(assignments))

    for day in range(1, problem.trip.days + 1):
        model.AddNoOverlap(variables.intervals_by_day[day])
        place_assignments = [
            variables.assigned[(candidate.place_id, day)]
            for candidate in problem.valid_places
            if (candidate.place_id, day) in variables.assigned
        ]
        model.Add(sum(place_assignments) >= MIN_PLACES_PER_DAY)
        entertainment_assignments = [
            variables.assigned[(candidate.place_id, day)]
            for candidate in problem.valid_entertainment
            if (candidate.place_id, day) in variables.assigned
        ]
        if entertainment_assignments:
            model.Add(sum(entertainment_assignments) <= MAX_ENTERTAINMENT_PER_DAY)
        for meal_type, policy in MEAL_POLICIES.items():
            choices = [
                variable
                for (food_id, meal_day, meal), variable in variables.meal.items()
                if meal_day == day and meal == meal_type
            ]
            model.Add(sum(choices) == 1)
            meal_start = variables.remember(
                model.NewIntVar(
                    policy.earliest_start,
                    policy.latest_start,
                    f"meal_start:{day}:{meal_type.value}",
                )
            )
            variables.meal_start[(day, meal_type)] = meal_start
            for (food_id, meal_day, meal), choice in variables.meal.items():
                if meal_day == day and meal == meal_type:
                    model.Add(
                        meal_start == variables.start[(food_id, day)]
                    ).OnlyEnforceIf(choice)
        for (earlier, later), minimum_gap in MINIMUM_MEAL_START_GAPS.items():
            model.Add(
                variables.meal_start[(day, later)]
                >= variables.meal_start[(day, earlier)] + minimum_gap
            )
        _add_drink_dessert_constraints(model, problem, variables, day)
    return variables


def _exclude_dominated_accommodations(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
) -> None:
    by_location: dict[tuple[float, float], list[str]] = {}
    for accommodation in problem.accommodations:
        location = (
            round(accommodation.coordinates.latitude, 6),
            round(accommodation.coordinates.longitude, 6),
        )
        by_location.setdefault(location, []).append(accommodation.place_id)
    for accommodation_ids in by_location.values():
        preferred = min(
            accommodation_ids,
            key=lambda accommodation_id: (
                problem.accommodation_cost_per_person_by_id[accommodation_id],
                accommodation_id,
            ),
        )
        for accommodation_id in accommodation_ids:
            if accommodation_id != preferred:
                model.Add(variables.accommodation_selected[accommodation_id] == 0)


def _add_drink_dessert_constraints(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    day: int,
) -> None:
    drink_food_ids = {
        food.place_id
        for food in problem.valid_food
        if food.venue_type == FoodVenueType.drink_dessert
    }
    drink_place_ids = {
        place.place_id
        for place in problem.valid_places
        if "drink_dessert" in place.tags
    }
    drink_ids = drink_food_ids | drink_place_ids
    daily_assignments = [
        variables.assigned[(food_id, day)]
        for food_id in drink_ids
        if (food_id, day) in variables.assigned
    ]
    if daily_assignments:
        model.Add(sum(daily_assignments) <= MAX_DRINK_DESSERTS_PER_DAY)

    for earlier, later in MINIMUM_MEAL_START_GAPS:
        adjacent_choices = [
            variable
            for (food_id, meal_day, meal), variable in variables.meal.items()
            if food_id in drink_food_ids
            and meal_day == day
            and meal in {earlier, later}
        ]
        if adjacent_choices:
            model.Add(sum(adjacent_choices) <= 1)


def _create_activity_interval(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    candidate_id: str,
    day: int,
    assigned: cp_model.IntVar,
    start: cp_model.IntVar,
    end: cp_model.IntVar,
) -> None:
    candidate = problem.candidate_by_id[candidate_id]
    model.Add(end == start + candidate.duration_minutes).OnlyEnforceIf(assigned)
    interval = model.NewOptionalIntervalVar(
        start,
        candidate.duration_minutes,
        end,
        assigned,
        f"interval:{candidate_id}:{day}",
    )
    variables.intervals_by_day[day].append(interval)
    window_choices = []
    for index, window in enumerate(problem.feasible_windows[(candidate_id, day)]):
        choice = variables.remember(
            model.NewBoolVar(f"window:{candidate_id}:{day}:{index}")
        )
        window_choices.append(choice)
        model.Add(start >= window.start_minute).OnlyEnforceIf(choice)
        model.Add(end <= window.end_minute).OnlyEnforceIf(choice)
    model.Add(sum(window_choices) == assigned)


def _create_food_intervals(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    candidate: PlannerFoodCandidate,
    day: int,
    assigned: cp_model.IntVar,
    start: cp_model.IntVar,
    end: cp_model.IntVar,
) -> None:
    meal_choices = []
    for meal_type in candidate.supported_meals:
        windows = problem.meal_eligibility.get((candidate.place_id, day, meal_type), ())
        if not windows:
            continue
        meal = variables.remember(
            model.NewBoolVar(f"meal:{candidate.place_id}:{day}:{meal_type.value}")
        )
        variables.meal[(candidate.place_id, day, meal_type)] = meal
        meal_choices.append(meal)
        duration = MEAL_POLICIES[meal_type].duration_minutes
        model.Add(end == start + duration).OnlyEnforceIf(meal)
        variables.intervals_by_day[day].append(
            model.NewOptionalIntervalVar(
                start,
                duration,
                end,
                meal,
                f"meal_interval:{candidate.place_id}:{day}:{meal_type.value}",
            )
        )
        uses_window = []
        for index, window in enumerate(windows):
            choice = variables.remember(
                model.NewBoolVar(
                    f"meal_window:{candidate.place_id}:{day}:{meal_type.value}:{index}"
                )
            )
            uses_window.append(choice)
            model.Add(start >= window.start_minute).OnlyEnforceIf(choice)
            model.Add(start <= window.end_minute).OnlyEnforceIf(choice)
        model.Add(sum(uses_window) == meal)
    model.Add(sum(meal_choices) == assigned)
