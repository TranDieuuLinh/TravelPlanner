from __future__ import annotations

from math import ceil, floor

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.optimizer.variables import PlannerVariables
from app.modules.itinerary_planner.policies import (
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
            elif destination_id.startswith("__end__"):
                model.Add(
                    variables.last_end[day]
                    == variables.end[(origin_id, day)]
                ).OnlyEnforceIf(arc)
        model.AddCircuit(circuit)

    for day in range(1, problem.trip.days):
        model.Add(
            variables.first_start[day + 1]
            + 1440
            - variables.last_end[day]
            >= MINIMUM_OVERNIGHT_REST_MINUTES
        )
    _add_budget(model, problem, routing, variables)


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
    total_cost = variables.remember(
        model.NewIntVar(0, MAX_MONEY, "total_cost_per_person")
    )
    variables.total_cost = total_cost
    model.Add(total_cost == sum(terms))
    if problem.trip.budget.amount is not None:
        model.Add(total_cost <= floor(problem.trip.budget.amount))
