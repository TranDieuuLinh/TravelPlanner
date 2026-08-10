# Travel Planner Agents

Cập nhật lần cuối: 2026-08-10.

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

- The supervisor uses deterministic high-signal rules first, with an optional
  structured Gemini classifier for ambiguous requests and a truthful
  deterministic fallback. The baseline model and routing policy are not
  production-evaluated.
- Explorer currently parses destination and duration from simple text input.
- InformationFinder uses cache-first hybrid PostgreSQL/pgvector retrieval,
  optional Tavily Search, and an optional structured answer generator through
  the shared Gemini client. Without configuration it returns a truthful
  process-local extractive fallback.
- PlaceChecker uses `DevelopmentCatalog`, which creates deterministic placeholder
  suggestions. Placeholder places have `verified=false` and emit a warning.
- ItineraryPlanner uses estimated routing, not live road-network data.
- The checkpointer is in memory and must be replaced by durable storage in
  production.
- A shared Gemini REST client is available through `app.bootstrap.get_llm_client`.
  It reads one comma-separated `GEMINI_API_KEY` value and rotates keys when a
  request receives a quota, authorization, transport, or server error. Existing
  Supervisor classification can opt into the same client with
  `SUPERVISOR_CLASSIFIER_PROVIDER=gemini`; keep `rules` for offline development
  and tests. Missing Gemini configuration fails during composition, while
  runtime classifier failures use the configured safe fallback.

All external capabilities are behind module ports so real providers can be
added without changing public graph contracts.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,embeddings]'
psql "$DATABASE_URL" -f migrations/001_information_finder_source_cache.sql
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

Configure `DATABASE_URL` for the module-owned PostgreSQL cache and
`TAVILY_API_KEY` for web refreshes. See `.env.example` for thresholds, timeout,
search depth, model revision, and blocked domains. Docker initializes the SQL
migration only for a new PostgreSQL volume; run it manually for an existing
volume. Set `INFORMATION_FINDER_ANSWER_PROVIDER=gemini` and `GEMINI_API_KEY` to
enable structured claims. The module validates source IDs and only exposes cited
sources; provider failures use extractive fallback only when
`INFORMATION_FINDER_LLM_FALLBACK_ENABLED=true`. `gemini-2.5-flash` is a
configurable baseline, not a production-evaluated model. After eval, pin a model
version through `GEMINI_MODEL` and document the evaluated snapshot.

LangGraph Studio can load the graph declared in `langgraph.json` after the
LangGraph CLI is installed.

