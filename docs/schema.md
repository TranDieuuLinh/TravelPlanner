# Backend module and agent schemas

Last checked: 2026-08-10

The backend follows a modular LangGraph design. Each module exposes its public
contract through `public.py`; its internal graph state and nodes are private.

## API boundary

| Endpoint | Input | Output |
|---|---|---|
| `GET /health` | None | `{ "status": "ok" }` |
| `POST /v1/agent/invoke` | `InvokeRequest` | `InvokeResponse` |

## Modules

| Module | Input | Output |
|---|---|---|
| `supervisor` | `SupervisorInput` | `SupervisorDecision` |
| `explorer` | `ExplorerInput` | `ExplorerOutput` |
| `information_finder` | `InformationFinderInput` | `InformationFinderOutput` |
| `place_checker` | `PlaceCheckerInput` | `PlaceCheckerOutput` |
| `itinerary_planner` | `ItineraryPlannerInput` | `ItineraryPlannerOutput` |
| `plan_editor` | `PlanEditorInput` | `PlanEditorOutput` |

## Agents

The current agent names are defined by `AgentName`:

- `supervisor`
- `explorer`
- `information_finder`
- `place_checker`
- `itinerary_planner`
- `plan_editor`

The root orchestration graph calls these agents in this flow:

```text
supervisor
├── information_finder
├── plan_editor
└── explorer -> place_checker -> itinerary_planner
```

The root graph input is `RootGraphInput` and the root graph output is
`RootGraphOutput`.

## Tools and provider adapters

There is no separate standalone tool registry yet. The current provider tools
and adapters are:

| Tool / adapter | Module | Input | Output |
|---|---|---|---|
| `UnconfiguredInformationProvider` | `information_finder` | `query: str` | `InformationFinderOutput` |
| `DevelopmentCatalog.resolve` | `place_checker` | `PlaceCandidate`, `TripIntent` | `VerifiedPlace \| None` |
| `DevelopmentCatalog.discover` | `place_checker` | `TripIntent`, `limit: int` | `list[VerifiedPlace]` |
| `EstimatedRoutingProvider.travel_minutes` | `itinerary_planner` | Two `VerifiedPlace` values | `int` minutes |

These are development implementations. The external-provider interfaces are:

- `InformationProvider`
- `PlaceResolver`
- `PlaceDiscovery`
- `RoutingProvider`

## Shared contracts

The main shared schema names are:

- `TripIntent`
- `Coordinates`
- `PlaceCandidate`
- `VerifiedPlace`
- `ItineraryItem`
- `ItineraryDay`
- `Itinerary`
- `EditOperation`
- `AgentTrace`
- `AgentError`

## API request and response names

- `InvokeRequest`: `thread_id`, `message`, `supplied_candidates`,
  `existing_itinerary`, `edit_operation`.
- `InvokeResponse`: `request_id`, `route`, `response`, `itinerary`,
  `clarification_question`, `warnings`.

This file records the current scaffold only. Authentication, database-backed
repositories, URL import tools, live place search, live routing, and
Marketplace agents are not currently implemented.
