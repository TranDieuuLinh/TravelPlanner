# Travel Planner Agents

Cập nhật lần cuối: 2026-08-11.

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

- The supervisor uses structured Gemini classification first when
  `SUPERVISOR_CLASSIFIER_PROVIDER=gemini`. The classifier also produces a short
  same-language response for greeting, assistant-meta, and out-of-scope
  `finish` requests. Deterministic rules remain the offline provider and runtime
  fallback. The baseline model and routing policy are not production-evaluated.
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
- Root graph checkpoints retain up to six recent user messages as internal
  conversation context for follow-up routing. This context is a routing hint,
  not a durable chat-history or production memory system.
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
pip install -e '.[dev]'
psql "$DATABASE_URL" -f migrations/001_information_finder_source_cache.sql
psql "$DATABASE_URL" -f migrations/002_auth.sql
psql "$DATABASE_URL" -f migrations/003_knowledge_graph.sql
psql "$DATABASE_URL" -f migrations/004_knowledge_auto_attach.sql
uvicorn app.main:app --reload
```

Call the API:

```bash
curl -X POST http://127.0.0.1:8000/v1/agent/invoke \
  -H 'content-type: application/json' \
  -d '{
    "thread_id": "demo-1",
    "message": "Lập kế hoạch ở Đà Nẵng trong 2 ngày, tham quan Cầu Rồng"
  }'
```

For Explorer-only contract testing, use `POST /v1/explorer/invoke` with
`rawPrompt`, `urls`, and/or `images`. This bypasses Supervisor, PlaceChecker,
and ItineraryPlanner and returns the complete `ExplorerOutput`.
For TikTok pages that require a logged-in session, export a Netscape-format
cookie file outside source control and set `EXPLORER_YTDLP_COOKIE_FILE` to its
absolute path. Cookie files are ignored by the backend `.gitignore`; never
commit or log them.

Run tests:

```bash
pytest
```

Authentication owns `auth_runtime_users` and `auth_runtime_sessions` through
`migrations/002_auth.sql`. Run that migration for an existing PostgreSQL
volume before using `/auth/login` or `/auth/register`. When `DATABASE_URL` is
empty, tests and local development use an in-memory fallback. The development
seed accounts are configured by `AUTH_DEV_SEED_USERS`; do not use those default
passwords outside local development.

The admin Knowledge Graph module owns the `knowledge_*` tables created by
`migrations/003_knowledge_graph.sql` and `migrations/004_knowledge_auto_attach.sql`.
It provides entity, alias, property, relationship, auto-attach rule, stats, and
ontology endpoints consumed by `admin-frontend`.
Apply the migration manually for an existing PostgreSQL volume; Docker only
applies init scripts when the volume is created.

With Docker, a fresh `travelplanner_postgres_data_v2` volume runs the migration
automatically because `docker-compose.yml` mounts it into PostgreSQL initdb.
For an existing volume, run the idempotent migration from the mounted file:

```powershell
docker compose up -d postgres
docker compose exec -T postgres psql -U travelplanner -d travelplanner -f /docker-entrypoint-initdb.d/003_knowledge_graph.sql
docker compose exec -T postgres psql -U travelplanner -d travelplanner -f /docker-entrypoint-initdb.d/004_knowledge_auto_attach.sql
```

Configure `BACKEND_CORS_ORIGINS` with comma-separated browser origins (the local
frontend and admin frontend use `http://localhost:3000` and
`http://localhost:3001`), and configure `DATABASE_URL` for the module-owned
PostgreSQL cache,
`GEMINI_API_KEY` for Gemini embeddings/answer generation, and `TAVILY_API_KEY`
for web refreshes. Gemini embeddings use `gemini-embedding-001` with 384 output
dimensions by default, matching the current pgvector schema; no local embedding
model is installed in the backend image. See `.env.example` for thresholds, timeout,
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
