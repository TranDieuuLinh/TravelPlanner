from __future__ import annotations

from math import ceil, floor

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.policies import (
    ITINERARY_START_MINUTE,
    MAX_INTER_STOP_WAIT_MINUTES,
    MINIMUM_OVERNIGHT_REST_MINUTES,
    OVERNIGHT_END_MINUTE,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem, SafeTravel

LATE_NIGHT_START_MINUTE = 22 * 60
MAX_MONEY = 10**15


def add_routing_and_budget_constraints(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    variables: PlannerVariables,
) -> None:
    arcs_by_pair = {
        (arc.origin_id, arc.destination_id): arc for arc in routing.sparse_arcs
    }
    candidate_ids = sorted(problem.candidate_by_id)
    food_ids = {food.place_id for food in problem.valid_food}
    node_index = {candidate_id: index for index, candidate_id in enumerate(candidate_ids)}
    start_index = len(candidate_ids)
    end_index = start_index + 1

    late_departure: dict[tuple[str, int], cp_model.IntVar] = {}
    for day in range(1, problem.trip.days + 1):
        variables.first_start[day] = variables.remember(
            model.NewIntVar(0, OVERNIGHT_END_MINUTE, f"first_start:{day}")
        )
        variables.last_end[day] = variables.remember(
            model.NewIntVar(0, OVERNIGHT_END_MINUTE, f"last_end:{day}")
        )
        circuit: list[tuple[int, int, cp_model.IntVar | int]] = []
        circuit.append((end_index, start_index, model.NewConstant(1)))
        for candidate_id in candidate_ids:
            assigned = variables.assigned.get((candidate_id, day))
            self_loop = variables.remember(
                model.NewBoolVar(f"self:{candidate_id}:{day}")
            )
            if assigned is None:
                model.Add(self_loop == 1)
            else:
                model.Add(self_loop + assigned == 1)
                late = variables.remember(
                    model.NewBoolVar(f"late_departure:{candidate_id}:{day}")
                )
                late_departure[(candidate_id, day)] = late
                model.Add(late <= assigned)
                model.Add(
                    variables.end[(candidate_id, day)] >= LATE_NIGHT_START_MINUTE
                ).OnlyEnforceIf(late)
                model.Add(
                    variables.end[(candidate_id, day)] < LATE_NIGHT_START_MINUTE
                ).OnlyEnforceIf([assigned, late.Not()])
            index = node_index[candidate_id]
            circuit.append((index, index, self_loop))

        for (origin_id, destination_id), sparse_arc in sorted(arcs_by_pair.items()):
            if day not in sparse_arc.feasible_days:
                continue
            origin_index = _node_index(origin_id, day, node_index, start_index, end_index)
            destination_index = _node_index(
                destination_id, day, node_index, start_index, end_index
            )
            if origin_index is None or destination_index is None:
                continue
            arc = variables.remember(
                model.NewBoolVar(f"arc:{origin_id}:{destination_id}:{day}")
            )
            variables.arc[(origin_id, destination_id, day)] = arc
            circuit.append((origin_index, destination_index, arc))
            if origin_id in node_index and destination_id in node_index:
                if origin_id in food_ids and destination_id in food_ids:
                    model.Add(arc == 0)
                _add_travel_precedence(
                    model,
                    variables,
                    origin_id,
                    destination_id,
                    day,
                    arc,
                    sparse_arc.travel,
                    late_departure[(origin_id, day)],
                )
            elif origin_id.startswith("__start__"):
                model.Add(
                    variables.first_start[day]
                    == variables.start[(destination_id, day)]
                ).OnlyEnforceIf(arc)
                if day > 1:
                    _add_accommodation_transfer(
                        model,
                        problem,
                        routing,
                        variables,
                        candidate_id=destination_id,
                        day=day,
                        direction="start",
                        endpoint_arc=arc,
                    )
            elif destination_id.startswith("__end__"):
                model.Add(
                    variables.last_end[day]
                    == variables.end[(origin_id, day)]
                ).OnlyEnforceIf(arc)
                if day < problem.trip.days:
                    _add_accommodation_transfer(
                        model,
                        problem,
                        routing,
                        variables,
                        candidate_id=origin_id,
                        day=day,
                        direction="end",
                        endpoint_arc=arc,
                        late_departure=late_departure[(origin_id, day)],
                    )
        model.AddCircuit(circuit)

    _add_overnight_rest(model, problem, routing, variables)
    _add_budget(model, problem, routing, variables)


def _add_accommodation_transfer(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    variables: PlannerVariables,
    *,
    candidate_id: str,
    day: int,
    direction: str,
    endpoint_arc: cp_model.IntVar,
    late_departure: cp_model.IntVar | None = None,
) -> None:
    for accommodation_id, selected in variables.accommodation_selected.items():
        pair = (
            (accommodation_id, candidate_id)
            if direction == "start"
            else (candidate_id, accommodation_id)
        )
        travel = routing.travel_by_candidate_pair.get(pair)
        if travel is None:
            model.Add(endpoint_arc + selected <= 1)
            continue
        transfer = variables.remember(
            model.NewBoolVar(
                f"accommodation_transfer:{direction}:{accommodation_id}:"
                f"{candidate_id}:{day}"
            )
        )
        variables.accommodation_transfer[
            (accommodation_id, candidate_id, day, direction)
        ] = transfer
        model.Add(transfer <= endpoint_arc)
        model.Add(transfer <= selected)
        model.Add(transfer >= endpoint_arc + selected - 1)
        if direction == "start":
            model.Add(
                variables.start[(candidate_id, day)]
                >= ITINERARY_START_MINUTE + travel.safe_minutes
            ).OnlyEnforceIf(transfer)
        else:
            model.Add(
                variables.end[(candidate_id, day)] + travel.safe_minutes
                <= OVERNIGHT_END_MINUTE
            ).OnlyEnforceIf(transfer)
            if late_departure is not None:
                night_transfer = variables.remember(
                    model.NewBoolVar(
                        f"accommodation_night_transfer:{accommodation_id}:"
                        f"{candidate_id}:{day}"
                    )
                )
                variables.accommodation_night_transfer[
                    (accommodation_id, candidate_id, day, direction)
                ] = night_transfer
                model.Add(night_transfer <= transfer)
                model.Add(night_transfer <= late_departure)
                model.Add(night_transfer >= transfer + late_departure - 1)


def _add_overnight_rest(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    variables: PlannerVariables,
) -> None:
    if not variables.accommodation_selected:
        for day in range(1, problem.trip.days):
            model.Add(
                variables.first_start[day + 1]
                + 1440
                - variables.last_end[day]
                >= MINIMUM_OVERNIGHT_REST_MINUTES
            )
        return

    travel_by_pair = routing.travel_by_candidate_pair
    for day in range(1, problem.trip.days):
        for accommodation_id in variables.accommodation_selected:
            end_transfers = [
                (key, variable)
                for key, variable in variables.accommodation_transfer.items()
                if key[0] == accommodation_id and key[2] == day and key[3] == "end"
            ]
            start_transfers = [
                (key, variable)
                for key, variable in variables.accommodation_transfer.items()
                if key[0] == accommodation_id
                and key[2] == day + 1
                and key[3] == "start"
            ]
            for end_key, end_transfer in end_transfers:
                end_candidate = end_key[1]
                return_minutes = travel_by_pair[
                    (end_candidate, accommodation_id)
                ].safe_minutes
                for start_key, start_transfer in start_transfers:
                    start_candidate = start_key[1]
                    departure_minutes = travel_by_pair[
                        (accommodation_id, start_candidate)
                    ].safe_minutes
                    model.Add(
                        variables.first_start[day + 1]
                        - departure_minutes
                        + 1440
                        - variables.last_end[day]
                        - return_minutes
                        >= MINIMUM_OVERNIGHT_REST_MINUTES
                    ).OnlyEnforceIf([end_transfer, start_transfer])


def _node_index(
    node_id: str,
    day: int,
    node_index: dict[str, int],
    start_index: int,
    end_index: int,
) -> int | None:
    if node_id == f"__start__:{day}":
        return start_index
    if node_id == f"__end__:{day}":
        return end_index
    return node_index.get(node_id)


def _add_travel_precedence(
    model: cp_model.CpModel,
    variables: PlannerVariables,
    origin_id: str,
    destination_id: str,
    day: int,
    arc: cp_model.IntVar,
    travel: SafeTravel,
    late_departure: cp_model.IntVar,
) -> None:
    origin_end = variables.end[(origin_id, day)]
    destination_start = variables.start[(destination_id, day)]
    model.Add(
        destination_start >= origin_end + travel.safe_minutes
    ).OnlyEnforceIf(arc)
    wait = variables.remember(
        model.NewIntVar(0, OVERNIGHT_END_MINUTE, f"waiting:{origin_id}:{destination_id}:{day}")
    )
    variables.waiting[(origin_id, destination_id, day)] = wait
    model.Add(
        wait == destination_start - origin_end - travel.safe_minutes
    ).OnlyEnforceIf(arc)
    model.Add(wait == 0).OnlyEnforceIf(arc.Not())
    model.Add(wait <= MAX_INTER_STOP_WAIT_MINUTES)
    night_arc = variables.remember(
        model.NewBoolVar(f"night_arc:{origin_id}:{destination_id}:{day}")
    )
    variables.night_arc[(origin_id, destination_id, day)] = night_arc
    model.Add(night_arc <= arc)
    model.Add(night_arc <= late_departure)
    model.Add(night_arc >= arc + late_departure - 1)


def _add_budget(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    variables: PlannerVariables,
) -> None:
    terms = []
    for accommodation_id, selected in variables.accommodation_selected.items():
        terms.append(
            selected
            * problem.accommodation_cost_per_person_by_id[accommodation_id]
            * problem.accommodation_nights
        )
    for candidate_id, candidate in problem.candidate_by_id.items():
        terms.append(variables.selected[candidate_id] * ceil(candidate.price.cost))
    sparse_by_pair = {
        (arc.origin_id, arc.destination_id): arc for arc in routing.sparse_arcs
    }
    for key, arc_var in variables.arc.items():
        origin_id, destination_id, _day = key
        if origin_id.startswith("__") or destination_id.startswith("__"):
            continue
        travel = sparse_by_pair[(origin_id, destination_id)].travel
        terms.append(arc_var * travel.transport_cost_per_person)
        terms.append(
            variables.night_arc[key] * travel.late_night_surcharge_per_person
        )
    for (accommodation_id, candidate_id, _day, direction), transfer in (
        variables.accommodation_transfer.items()
    ):
        pair = (
            (accommodation_id, candidate_id)
            if direction == "start"
            else (candidate_id, accommodation_id)
        )
        travel = routing.travel_by_candidate_pair[pair]
        terms.append(transfer * travel.transport_cost_per_person)
        night_transfer = variables.accommodation_night_transfer.get(
            (accommodation_id, candidate_id, _day, direction)
        )
        if night_transfer is not None:
            terms.append(
                night_transfer * travel.late_night_surcharge_per_person
            )
    total_cost = variables.remember(
        model.NewIntVar(0, MAX_MONEY, "total_cost_per_person")
    )
    variables.total_cost = total_cost
    model.Add(total_cost == sum(terms))
    budget = problem.trip.budget
    if budget.amount is None:
        return
    target = floor(budget.amount)
    if budget.source != "estimated_daily_cost":
        model.Add(total_cost <= target)
        return

    overage = variables.remember(
        model.NewIntVar(0, MAX_MONEY, "estimated_budget_overage")
    )
    model.AddMaxEquality(overage, [total_cost - target, 0])
    overage_units = variables.remember(
        model.NewIntVar(0, MAX_MONEY // 10_000, "estimated_budget_overage_10k")
    )
    model.AddDivisionEquality(overage_units, overage, 10_000)
    variables.budget_overage_units = overage_units
