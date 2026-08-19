from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from time import monotonic

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import CandidatePriority
from app.modules.itinerary_planner.optimizer.accommodation_anchor import (
    DailyAccommodationAnchor,
)
from app.modules.itinerary_planner.optimizer.config import (
    ObjectiveWeights,
    SolverConfig,
)
from app.modules.itinerary_planner.optimizer.hints import (
    InitialSolutionHint,
    apply_initial_hint,
)
from app.modules.itinerary_planner.optimizer.locks import (
    RepairLocks,
    apply_repair_locks,
)
from app.modules.itinerary_planner.optimizer.objective import build_objective
from app.modules.itinerary_planner.optimizer.result import (
    OptimizationResult,
    SolverPassResult,
    extract_result,
)
from app.modules.itinerary_planner.optimizer.routing_constraints import (
    add_routing_and_budget_constraints,
)
from app.modules.itinerary_planner.optimizer.variables import (
    PlannerVariables,
    create_schedule_variables,
)
from app.modules.itinerary_planner.preprocessing import PreparedPlanningProblem
from app.modules.itinerary_planner.routing_models import RoutingProblem


class OptimizationError(RuntimeError):
    def __init__(
        self,
        status: str,
        pass_name: str,
        detail: str | None = None,
    ) -> None:
        self.status = status
        self.pass_name = pass_name
        self.detail = detail
        prefix = "Hybrid" if pass_name.startswith("hybrid_") else "CP-SAT"
        message = f"{prefix} {pass_name} pass returned {status}."
        if detail:
            message = f"{message} {detail}"
        super().__init__(message)


def optimize_itinerary(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    config: SolverConfig | None = None,
    weights: ObjectiveWeights | None = None,
    repair_locks: RepairLocks | None = None,
    initial_hint: InitialSolutionHint | None = None,
    daily_accommodation_anchor: DailyAccommodationAnchor | None = None,
) -> OptimizationResult:
    selected_config = config or SolverConfig()
    selected_weights = weights or ObjectiveWeights()
    model = cp_model.CpModel()
    variables = create_schedule_variables(model, problem)
    add_routing_and_budget_constraints(
        model,
        problem,
        routing,
        variables,
        max_inter_stop_wait_minutes=(
            selected_config.max_inter_stop_wait_minutes
        ),
        daily_accommodation_anchor=daily_accommodation_anchor,
    )
    if repair_locks is not None:
        apply_repair_locks(model, problem, variables, repair_locks)
    if initial_hint is not None:
        apply_initial_hint(model, variables, initial_hint)
    objective = build_objective(model, problem, routing, variables, selected_weights)

    user_vars = [
        variables.selected[candidate_id]
        for candidate_id, candidate in problem.candidate_by_id.items()
        if candidate.priority == CandidatePriority.user_input
    ]
    url_vars = [
        variables.selected[candidate_id]
        for candidate_id, candidate in problem.candidate_by_id.items()
        if candidate.priority == CandidatePriority.url
    ]
    passes: list[SolverPassResult] = []

    user_count = sum(user_vars)
    url_count = sum(url_vars)
    priority_objective = user_count * (len(url_vars) + 1) + url_count
    model.Maximize(priority_objective)
    priority_solver, priority_pass = _solve(
        model,
        "priority",
        selected_config.priority_timeout_seconds,
        selected_config,
        priority_objective,
        relative_gap_limit=0,
        stop_after_first_solution=False,
    )
    passes.append(priority_pass)
    best_user_count = sum(priority_solver.Value(variable) for variable in user_vars)
    best_url_count = sum(priority_solver.Value(variable) for variable in url_vars)
    model.Add(user_count == best_user_count)
    model.Add(url_count == best_url_count)
    _add_hints(model, problem, variables, priority_solver)

    model.Maximize(objective.utility)
    final_solver, utility_pass = _solve_utility_with_incumbent(
        model,
        problem,
        variables,
        selected_config,
        objective.utility,
    )
    passes.append(utility_pass)
    return extract_result(
        final_solver,
        problem,
        variables,
        objective,
        selected_weights.policy_version,
        tuple(passes),
    )


def _solve_utility_with_incumbent(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    config: SolverConfig,
    objective: cp_model.LinearExpr,
) -> tuple[cp_model.CpSolver, SolverPassResult]:
    """Keep the best utility solution until configured parallel rounds stagnate."""
    best_solver: cp_model.CpSolver | None = None
    best_pass: SolverPassResult | None = None
    attempt_count = 0
    round_count = 0
    no_improvement_rounds = 0
    last_error: OptimizationError | None = None
    started = monotonic()
    worker_count = max(1, config.utility_parallel_workers)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        while (
            best_solver is None
            or no_improvement_rounds < config.max_utility_no_improvement_rounds
        ):
            round_count += 1
            seeds = range(
                config.random_seed + attempt_count,
                config.random_seed + attempt_count + worker_count,
            )
            futures = [
                executor.submit(
                    _solve,
                    model.clone(),
                    "utility",
                    config.utility_timeout_seconds,
                    config,
                    objective,
                    relative_gap_limit=config.utility_relative_gap_limit,
                    stop_after_first_solution=(
                        config.utility_timeout_seconds is None
                    ),
                    random_seed=seed,
                )
                for seed in seeds
            ]
            attempt_count += worker_count
            outcomes: list[tuple[cp_model.CpSolver, SolverPassResult]] = []
            for future in futures:
                try:
                    outcomes.append(future.result())
                except OptimizationError as exc:
                    last_error = exc

            if not outcomes:
                if best_solver is None:
                    if last_error is not None:
                        raise last_error
                    raise OptimizationError("UNKNOWN", "utility")
                no_improvement_rounds += 1
                continue

            round_solver, round_pass = max(
                outcomes,
                key=lambda item: (
                    item[1].objective_value,
                    item[1].optimality_proven,
                ),
            )
            if (
                best_pass is None
                or round_pass.objective_value > best_pass.objective_value
                or (
                    round_pass.objective_value == best_pass.objective_value
                    and round_pass.optimality_proven
                    and not best_pass.optimality_proven
                )
            ):
                best_solver = round_solver
                best_pass = round_pass
                no_improvement_rounds = 0
            else:
                no_improvement_rounds += 1

            if round_pass.optimality_proven:
                break

    if best_solver is None or best_pass is None:
        if last_error is not None:
            raise last_error
        raise OptimizationError("UNKNOWN", "utility")
    return best_solver, SolverPassResult(
        name="utility",
        status=best_pass.status,
        objective_value=best_pass.objective_value,
        wall_time_ms=round((monotonic() - started) * 1000),
        optimality_proven=best_pass.optimality_proven,
        attempt_count=attempt_count,
        round_count=round_count,
        no_improvement_rounds=no_improvement_rounds,
    )


def _solve(
    model: cp_model.CpModel,
    name: str,
    timeout_seconds: float | None,
    config: SolverConfig,
    reported_objective: cp_model.LinearExpr,
    *,
    relative_gap_limit: float,
    stop_after_first_solution: bool,
    random_seed: int | None = None,
) -> tuple[cp_model.CpSolver, SolverPassResult]:
    solver = cp_model.CpSolver()
    if timeout_seconds is not None:
        solver.parameters.max_time_in_seconds = timeout_seconds
    if relative_gap_limit:
        solver.parameters.relative_gap_limit = relative_gap_limit
    solver.parameters.num_search_workers = config.num_search_workers
    solver.parameters.random_seed = (
        config.random_seed if random_seed is None else random_seed
    )
    solver.parameters.log_search_progress = config.log_search_progress
    solver.parameters.stop_after_first_solution = stop_after_first_solution
    started = monotonic()
    status_code = solver.Solve(model)
    elapsed_ms = round((monotonic() - started) * 1000)
    status = solver.StatusName(status_code)
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise OptimizationError(status, name)
    return solver, SolverPassResult(
        name=name,
        status=status,
        objective_value=solver.Value(reported_objective),
        wall_time_ms=elapsed_ms,
        optimality_proven=(status_code == cp_model.OPTIMAL and relative_gap_limit == 0),
    )


def _add_hints(
    model: cp_model.CpModel,
    problem: PreparedPlanningProblem,
    variables: PlannerVariables,
    solver: cp_model.CpSolver,
) -> None:
    model.ClearHints()
    accommodation_indexes = {
        variable.Index() for variable in variables.accommodation_selected.values()
    }
    for variable in variables.all_decision_vars:
        if variable.Index() in accommodation_indexes:
            continue
        model.AddHint(variable, solver.Value(variable))
    if variables.accommodation_selected:
        cheapest = min(
            variables.accommodation_selected,
            key=lambda accommodation_id: (
                problem.accommodation_cost_per_person_by_id[accommodation_id],
                accommodation_id,
            ),
        )
        for accommodation_id, variable in variables.accommodation_selected.items():
            model.AddHint(variable, int(accommodation_id == cheapest))
