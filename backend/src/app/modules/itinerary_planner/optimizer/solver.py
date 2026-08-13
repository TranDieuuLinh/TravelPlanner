from __future__ import annotations

from time import monotonic

from ortools.sat.python import cp_model

from app.modules.itinerary_planner.contract import CandidatePriority
from app.modules.itinerary_planner.optimizer.config import (
    ObjectiveWeights,
    SolverConfig,
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
    def __init__(self, status: str, pass_name: str) -> None:
        self.status = status
        self.pass_name = pass_name
        super().__init__(f"CP-SAT {pass_name} pass returned {status}.")


def optimize_itinerary(
    problem: PreparedPlanningProblem,
    routing: RoutingProblem,
    *,
    config: SolverConfig | None = None,
    weights: ObjectiveWeights | None = None,
    repair_locks: RepairLocks | None = None,
) -> OptimizationResult:
    selected_config = config or SolverConfig()
    selected_weights = weights or ObjectiveWeights()
    model = cp_model.CpModel()
    variables = create_schedule_variables(model, problem)
    add_routing_and_budget_constraints(model, problem, routing, variables)
    if repair_locks is not None:
        apply_repair_locks(model, problem, variables, repair_locks)
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

    model.Maximize(sum(user_vars))
    pass1_solver, pass1 = _solve(
        model, "user_input", selected_config.pass1_timeout_seconds, selected_config
    )
    passes.append(pass1)
    best_user_count = sum(pass1_solver.Value(variable) for variable in user_vars)
    model.Add(sum(user_vars) == best_user_count)
    _add_hints(model, variables, pass1_solver)

    model.Maximize(sum(url_vars))
    pass2_solver, pass2 = _solve(
        model, "url", selected_config.pass2_timeout_seconds, selected_config
    )
    passes.append(pass2)
    best_url_count = sum(pass2_solver.Value(variable) for variable in url_vars)
    model.Add(sum(url_vars) == best_url_count)
    _add_hints(model, variables, pass2_solver)

    model.Maximize(objective.utility)
    final_solver, pass3 = _solve(
        model, "utility", selected_config.pass3_timeout_seconds, selected_config
    )
    passes.append(pass3)
    return extract_result(
        final_solver,
        problem,
        variables,
        objective,
        selected_weights.policy_version,
        tuple(passes),
    )


def _solve(
    model: cp_model.CpModel,
    name: str,
    timeout_seconds: float,
    config: SolverConfig,
) -> tuple[cp_model.CpSolver, SolverPassResult]:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = timeout_seconds
    solver.parameters.num_search_workers = config.num_search_workers
    solver.parameters.random_seed = config.random_seed
    solver.parameters.log_search_progress = config.log_search_progress
    started = monotonic()
    status_code = solver.Solve(model)
    elapsed_ms = round((monotonic() - started) * 1000)
    status = solver.StatusName(status_code)
    if status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise OptimizationError(status, name)
    return solver, SolverPassResult(
        name=name,
        status=status,
        objective_value=round(solver.ObjectiveValue()),
        wall_time_ms=elapsed_ms,
        optimality_proven=status_code == cp_model.OPTIMAL,
    )


def _add_hints(
    model: cp_model.CpModel,
    variables: PlannerVariables,
    solver: cp_model.CpSolver,
) -> None:
    model.ClearHints()
    for variable in variables.all_decision_vars:
        model.AddHint(variable, solver.Value(variable))
