# Beam Search Planner Implementation Plan

> **For agentic workers:** Execute this plan task-by-task with test-first checkpoints. Keep the existing CP-SAT runtime unchanged.

**Goal:** Add a parallel Beam Search itinerary optimizer that enforces the agreed checklist, ranks complete plans, and can be exercised after PlaceChecker without replacing CP-SAT.

**Architecture:** Add a self-contained `beam_search/` package under `itinerary_planner`. It consumes `PreparedPlanningProblem` and `RoutingProblem`, uses the existing `SafeTravel` matrix, returns the existing `OptimizationResult`, and reuses route enrichment/finalization. The old hybrid/CP-SAT graph remains the default.

**Tech Stack:** Python 3.12, Pydantic contracts, existing Valhalla routing ports, pytest.

## Global Constraints

- Hard reject restaurant-to-restaurant transitions, duplicate candidate identities, invalid opening windows, excessive waiting, unreachable travel, missing meals, and explicit budget overflow.
- Convert Valhalla seconds to planner minutes before time arithmetic.
- Allow long transitions at or above the per-request Q3 distance only when the next candidate has rating >= 4.0 and review count >= the per-request Q3.
- Prefer plans that preserve three distinct restaurants; use this as a strong soft score after hard feasibility.
- Keep the existing CP-SAT implementation and tests intact.

### Task 1: Beam configuration and scoring

Create configuration, state, checklist, and final evaluation models. Add failing unit tests for transition rejection, waiting, Q3 exception, three-restaurant preference, and summary statistics.

### Task 2: Beam expansion and result conversion

Implement bounded day-by-day/global beam expansion with top-K pruning, complete-meal terminal handling, global used-node tracking, and conversion to `OptimizationResult`. Add tests for branching, stopping, duplicate pruning, and deterministic ordering.

### Task 3: Parallel graph factory

Add a Beam Search planner graph/factory that reuses preprocessing, routing matrix, route enrichment, and finalization. Preserve the current graph factory unchanged and test a complete one-day graph with a fake matrix.

### Task 4: Runtime evaluation

Run PlaceChecker-to-planner fixtures and multiple candidate pools, record planner timings and warnings, tune only Beam Search constants, and update module documentation with the non-production status and benchmark results.
