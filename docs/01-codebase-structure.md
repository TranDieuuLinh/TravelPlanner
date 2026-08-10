# Current codebase structure

Updated 2026-08-10.

## Top-level applications

- `backend/`: the current FastAPI/LangGraph runtime.
- `frontend/`: the user-facing Next.js application.
- `admin-frontend/`: the separate admin/control Next.js application.
- `docker-compose.yml`: local container configuration.

## Backend layout

```text
backend/
├── pyproject.toml
├── Dockerfile
├── langgraph.json
├── src/app/
│   ├── main.py
│   ├── bootstrap.py
│   ├── api/
│   ├── core/
│   ├── orchestration/
│   ├── shared/
│   │   ├── contracts/
│   │   └── persistence/
│   └── modules/
│       ├── supervisor/
│       ├── explorer/
│       ├── information_finder/
│       ├── place_checker/
│       ├── itinerary_planner/
│       └── plan_editor/
└── tests/
```

`src/app/main.py` creates the FastAPI application. `api/` exposes the HTTP
contract. `orchestration/` owns the root graph and maps public contracts
between modules. It must not contain feature-specific travel rules.

## Module boundary

Each vertical module follows this shape:

```text
modules/<module>/
├── public.py       # supported imports for other modules
├── contract.py     # public Pydantic contracts
├── state.py        # private graph state
├── graph.py        # graph factory
├── nodes.py        # thin LangGraph nodes
├── service.py      # deterministic business behavior
├── ports.py        # provider interfaces, when needed
├── adapters/       # concrete provider implementations, when needed
└── tests/          # module-local tests
```

Consumers should import a module through `public.py`, not reach into another
module's private state, nodes, or services. External providers must be added
behind a port and adapter.

## Current API boundary

The current runtime intentionally exposes only:

- `GET /health`
- `POST /v1/agent/invoke`

The agent endpoint accepts a thread id, a user message, optional place
candidates, an existing itinerary, and an optional edit operation. Its response
contains the selected route, a textual response, an itinerary when available,
clarification information, and warnings.

Authentication, Marketplace, URL import, durable storage, live place data, and
live routing are not part of the current scaffold. Add them as explicit
modules or adapters instead of reintroducing the removed legacy backend
structure.
