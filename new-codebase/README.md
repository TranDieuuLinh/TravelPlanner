# Travel Planner Agents

Greenfield modular backend for a LangGraph-based travel-planning workflow.

## Architecture

The codebase uses vertical feature modules. Each module owns its public
contract, graph state, nodes, services, ports, adapters, and unit tests.
Consumers may import a module only through its `public.py` file.

```text
Supervisor
├── InformationFinder -> END
├── PlanEditor        -> END
└── Explorer -> PlaceChecker -> ItineraryPlanner -> END
```

The root graph lives in `src/app/orchestration`. It maps data between public
module contracts and does not contain travel-planning rules.

## Module boundary

```text
modules/<module>/
├── public.py       # supported imports for other modules
├── contract.py     # Pydantic input/output contracts
├── state.py        # private LangGraph state
├── graph.py        # subgraph factory
├── nodes.py        # thin graph nodes
├── service.py      # deterministic business behavior
├── ports.py        # provider interfaces, when required
├── adapters/       # concrete provider implementations
└── tests/          # module-local tests
```

## Current implementation status

This is a working architecture scaffold, not a production travel-data system.

- The supervisor is a deterministic classifier baseline.
- Explorer currently parses destination and duration from simple text input.
- InformationFinder intentionally uses an unconfigured provider response.
- PlaceChecker uses `DevelopmentCatalog`, which creates deterministic placeholder
  suggestions. Placeholder places have `verified=false` and emit a warning.
- ItineraryPlanner uses estimated routing, not live road-network data.
- The checkpointer is in memory and must be replaced by durable storage in
  production.

All external capabilities are behind module ports so real providers can be
added without changing public graph contracts.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Call the API:

```bash
curl -X POST http://127.0.0.1:8000/v1/agent/invoke \
  -H 'content-type: application/json' \
  -d '{
    "thread_id": "demo-1",
    "message": "Lập kế hoạch ở Đà Nẵng trong 2 ngày",
    "supplied_candidates": [
      {
        "name": "Bảo tàng Đà Nẵng",
        "coordinates": {"latitude": 16.0678, "longitude": 108.2208}
      }
    ]
  }'
```

Run tests:

```bash
pytest
```

LangGraph Studio can load the graph declared in `langgraph.json` after the
LangGraph CLI is installed.

