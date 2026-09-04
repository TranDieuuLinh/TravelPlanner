from __future__ import annotations

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.day_repair.models import (
    DayScheduleRepair,
    RepairAnchors,
    RepairedStop,
    RepairStop,
)
from app.modules.itinerary_planner.policies import (
    ITINERARY_START_MINUTE,
    MAX_INTER_STOP_WAIT_MINUTES,
    MINIMUM_MEAL_START_GAPS,
    OVERNIGHT_END_MINUTE,
)

TravelMinutes = dict[tuple[str, str], int]


def repair_fixed_order(
    stops: tuple[RepairStop, ...],
    travel: TravelMinutes,
    anchors: RepairAnchors,
) -> DayScheduleRepair | None:
    repaired: list[RepairedStop] = []
    previous_id: str | None = None
    previous_end = 0
    meal_starts: dict[str, int] = {}
    for stop in stops:
        earliest = max(ITINERARY_START_MINUTE, stop.original_start)
        if previous_id is not None:
            duration = travel.get((previous_id, stop.internal_id))
            if duration is None:
                return None
            arrival = previous_end + duration
            earliest = max(earliest, arrival)
        elif anchors.require_start and anchors.accommodation_id:
            duration = travel.get((anchors.accommodation_id, stop.internal_id))
            if duration is None:
                return None
            earliest = max(earliest, ITINERARY_START_MINUTE + duration)
            arrival = earliest
        else:
            arrival = earliest
        earliest = _meal_gap_floor(stop, meal_starts, earliest)
        start = _first_start(stop.start_ranges, earliest)
        if start is None:
            return None
        if previous_id is not None and start - arrival > MAX_INTER_STOP_WAIT_MINUTES:
            return None
        end = start + stop.duration_minutes
        repaired.append(RepairedStop(stop.internal_id, start, end))
        if stop.meal_type:
            meal_starts[stop.meal_type] = start
        previous_id = stop.internal_id
        previous_end = end
    if repaired and anchors.require_return and anchors.accommodation_id:
        duration = travel.get((repaired[-1].internal_id, anchors.accommodation_id))
        if duration is None or repaired[-1].end_minute + duration > OVERNIGHT_END_MINUTE:
            return None
    return DayScheduleRepair("fixed_order_reflow", tuple(repaired))


def repair_with_cp_sat(
    stops: tuple[RepairStop, ...],
    travel: TravelMinutes,
    anchors: RepairAnchors,
    *,
    timeout_seconds: float = 3.0,
) -> DayScheduleRepair | None:
    if not stops:
        return None
    model = cp_model.CpModel()
    starts: dict[str, cp_model.IntVar] = {}
    ends: dict[str, cp_model.IntVar] = {}
    deviations: list[cp_model.IntVar] = []
    by_id = {stop.internal_id: stop for stop in stops}
    for stop in stops:
        domain = cp_model.Domain.FromIntervals(
            [[lower, upper] for lower, upper in stop.start_ranges]
        )
        start = model.NewIntVarFromDomain(domain, f"start:{stop.internal_id}")
        end = model.NewIntVar(0, OVERNIGHT_END_MINUTE, f"end:{stop.internal_id}")
        model.Add(end == start + stop.duration_minutes)
        deviation = model.NewIntVar(0, OVERNIGHT_END_MINUTE, f"deviation:{stop.internal_id}")
        model.AddAbsEquality(deviation, start - stop.original_start)
        starts[stop.internal_id] = start
        ends[stop.internal_id] = end
        deviations.append(deviation)

    ids = [stop.internal_id for stop in stops]
    index = {stop_id: offset + 1 for offset, stop_id in enumerate(ids)}
    arcs: list[tuple[int, int, cp_model.IntVar]] = []
    arc_vars: dict[tuple[str | None, str | None], cp_model.IntVar] = {}
    for destination in ids:
        arc = model.NewBoolVar(f"first:{destination}")
        arcs.append((0, index[destination], arc))
        arc_vars[(None, destination)] = arc
        if anchors.require_start and anchors.accommodation_id:
            minutes = travel.get((anchors.accommodation_id, destination))
            if minutes is None:
                model.Add(arc == 0)
            else:
                model.Add(
                    starts[destination] >= ITINERARY_START_MINUTE + minutes
                ).OnlyEnforceIf(arc)
    for origin in ids:
        arc = model.NewBoolVar(f"last:{origin}")
        arcs.append((index[origin], 0, arc))
        arc_vars[(origin, None)] = arc
        if anchors.require_return and anchors.accommodation_id:
            minutes = travel.get((origin, anchors.accommodation_id))
            if minutes is None:
                model.Add(arc == 0)
            else:
                model.Add(ends[origin] + minutes <= OVERNIGHT_END_MINUTE).OnlyEnforceIf(arc)
        for destination in ids:
            if origin == destination:
                continue
            arc = model.NewBoolVar(f"arc:{origin}:{destination}")
            arcs.append((index[origin], index[destination], arc))
            arc_vars[(origin, destination)] = arc
            minutes = travel.get((origin, destination))
            if minutes is None:
                model.Add(arc == 0)
                continue
            model.Add(
                starts[destination] >= ends[origin] + minutes
            ).OnlyEnforceIf(arc)
            model.Add(
                starts[destination]
                <= ends[origin] + minutes + MAX_INTER_STOP_WAIT_MINUTES
            ).OnlyEnforceIf(arc)
    model.AddCircuit(arcs)

    for (earlier, later), gap in MINIMUM_MEAL_START_GAPS.items():
        earlier_ids = [item.internal_id for item in stops if item.meal_type == earlier.value]
        later_ids = [item.internal_id for item in stops if item.meal_type == later.value]
        if len(earlier_ids) == 1 and len(later_ids) == 1:
            model.Add(starts[later_ids[0]] >= starts[earlier_ids[0]] + gap)

    original_pairs = {
        (None, ids[0]),
        (ids[-1], None),
        *((ids[offset], ids[offset + 1]) for offset in range(len(ids) - 1)),
    }
    changed_arcs = [
        variable
        for pair, variable in arc_vars.items()
        if pair not in original_pairs
    ]
    travel_cost = sum(
        travel[pair] * variable
        for pair, variable in arc_vars.items()
        if pair[0] is not None and pair[1] is not None and pair in travel
    )
    model.Minimize(
        10_000 * sum(changed_arcs) + 10 * travel_cost + sum(deviations)
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(0.1, timeout_seconds)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 42
    status = solver.Solve(model)
    if status not in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return None

    outgoing = {
        origin: destination
        for (origin, destination), variable in arc_vars.items()
        if solver.Value(variable)
    }
    ordered: list[RepairedStop] = []
    current = outgoing.get(None)
    while current is not None and len(ordered) < len(stops):
        stop = by_id[current]
        ordered.append(
            RepairedStop(
                current,
                solver.Value(starts[current]),
                solver.Value(ends[current]),
            )
        )
        current = outgoing.get(current)
    if len(ordered) != len(stops):
        return None
    return DayScheduleRepair("cp_sat_reorder", tuple(ordered))


def _first_start(ranges: tuple[tuple[int, int], ...], earliest: int) -> int | None:
    for lower, upper in ranges:
        value = max(lower, earliest)
        if value <= upper:
            return value
    return None


def _meal_gap_floor(
    stop: RepairStop,
    meal_starts: dict[str, int],
    earliest: int,
) -> int:
    if not stop.meal_type:
        return earliest
    for (earlier, later), gap in MINIMUM_MEAL_START_GAPS.items():
        if later.value == stop.meal_type and earlier.value in meal_starts:
            earliest = max(earliest, meal_starts[earlier.value] + gap)
    return earliest
