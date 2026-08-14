# Travel Planner Agents

Cập nhật lần cuối: 2026-08-14.

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

- The supervisor delegates intent classification to the structured Gemini
  classifier. It handles greetings, assistant-meta questions, and routing to
  Explorer, InformationFinder, or PlanEditor through the same LLM decision.
  Only provider failure, low confidence, or invalid structured edit state uses
  a safe clarification response. The baseline model and routing policy are not
  production-evaluated.
- Explorer now uses a two-route LangGraph intake flow. Prompt-only extraction
  and parallel URL/image source import converge on normalization, ADM
  reconciliation, defaults, and separate ready/clarification/failure snapshot
  paths. With Gemini configured, raw images use OCR; TikTok/Instagram media use
  yt-dlp with curl-cffi Chrome impersonation, an Android Chrome fallback, and a
  small muxed MP4 preference. Analysis uses 1.5-second frame sampling capped at
  72 frames and 10 images per parallel Gemini batch, plus three parallel STT
  chunks. OCR uses
  `GEMINI_IMAGE_OCR_MODEL`, while STT uses `GEMINI_AUDIO_MODEL`; a failed media
  branch is logged and reported without discarding successful evidence from the
  other branch. YouTube is metadata-only. Generic websites use `httpx` plus
  `trafilatura`, trying Safari-impersonated `curl-cffi` and then a bounded
  Playwright Chromium fallback after HTTP block.
  Snapshots remain process-local, and
  anti-bot responses may require `EXPLORER_YTDLP_COOKIE_FILE` or remain a
  partial source failure. Source synthesis uses Gemini when available so
  `urlNotes` retain only useful evidence-backed details. Each source chunk uses
  one structured call for places, destination, and notes; three chunks run in
  parallel by default under a six-request synthesis limiter. Text, OCR, and
  audio clients share a key pool with one in-flight request per key and bounded
  key rotation that honors provider `Retry-After` responses.
  URL extraction is cached in Explorer-owned PostgreSQL `source_documents` by
  canonical URL, extractor version, and a seven-day default TTL. The adapter
  reads legacy `old_one` version-6 artifacts and writes normalized version 7.
  `forceRefresh=true` bypasses a hit; cache failures do not block extraction.
- The supervisor uses structured Gemini classification for every intent. The
  classifier also produces a short same-language response for greeting,
  assistant-meta, and out-of-scope `finish` requests. There is no keyword-based
  Supervisor routing provider. The baseline model and routing policy are not
  production-evaluated.
- Explorer currently parses destination and duration from simple text input.
- InformationFinder uses cache-first hybrid PostgreSQL/pgvector retrieval,
  optional Tavily Search, and an optional structured answer generator through
  the shared Gemini client. Without configuration it returns a truthful
  process-local extractive fallback.
- PlaceChecker uses `DevelopmentCatalog`, which creates deterministic placeholder
  suggestions. Placeholder places have `verified=false` and emit a warning.
- ItineraryPlanner preprocesses the compact PlaceChecker payload, builds a
  global Valhalla driving matrix with Xanh SM fare estimates, then runs a
  three-pass OR-Tools CP-SAT model. It enriches selected route legs, performs at
  most one affected-day repair, and returns the new plan in `plannerOutput`.
  Valhalla must be configured and available for production matrix routing;
  missing route geometry after a valid matrix is surfaced as a warning.
- The checkpointer is in memory and must be replaced by durable storage in
  production.
- Root graph checkpoints retain a bounded recent conversation context for the
  Supervisor LLM. This context is not a durable chat-history or production
  memory system.
- A shared Gemini REST client is available through `app.bootstrap.get_llm_client`.
  It reads one comma-separated `GEMINI_API_KEY` value, shares leases across
  Explorer text/image/audio clients, and rotates a bounded number of keys when a
  request receives a quota, authorization, transport, or server error. Supervisor
  classification uses the same client. Missing Gemini configuration fails during
  composition, while runtime classifier failures use the configured safe
  clarification response.

All external capabilities are behind module ports so real providers can be
added without changing public graph contracts.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
psql "$DATABASE_URL" -f migrations/001_information_finder_source_cache.sql
psql "$DATABASE_URL" -f migrations/002_explorer_source_document_cache.sql
psql "$DATABASE_URL" -f migrations/003_explorer_draft_cache.sql
psql "$DATABASE_URL" -f migrations/002_auth.sql
psql "$DATABASE_URL" -f migrations/003_knowledge_graph.sql
psql "$DATABASE_URL" -f migrations/004_knowledge_auto_attach.sql
psql "$DATABASE_URL" -f migrations/009_conversation_memory.sql
psql "$DATABASE_URL" -f migrations/009_trip_chat_planner_output.sql
psql "$DATABASE_URL" -f migrations/010_phase05_memory_durable.sql
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
`rawPrompt`, `urls`, and/or `images`. Send `forceRefresh: true` to bypass the
URL cache. This bypasses Supervisor, PlaceChecker,
and ItineraryPlanner and returns the complete `ExplorerOutput`.
For TikTok pages that require a logged-in session, export a Netscape-format
cookie file outside source control and set `EXPLORER_YTDLP_COOKIE_FILE` to its
absolute path. Cookie files are ignored by the backend `.gitignore`; never
commit or log them.
Docker Compose loads provider, Explorer, and cloud database settings from
`backend/.env` when that file exists; copy `.env.example` and set the cloud
`DATABASE_URL` before starting the stack.

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
Apply the migration directly against the cloud database before using the
Knowledge Graph or PlaceChecker catalog. The migration is idempotent.

Configure `BACKEND_CORS_ORIGINS` with comma-separated browser origins (the local
frontend and admin frontend use `http://localhost:3000` and
`http://localhost:3001`), and configure `DATABASE_URL` for the module-owned
PostgreSQL cache,
`GEMINI_API_KEY` for Gemini embeddings/answer generation, and `TAVILY_API_KEY`
for web refreshes. Gemini embeddings use `gemini-embedding-001` with 384 output
dimensions by default, matching the current pgvector schema; no local embedding
model is installed in the backend image. See `.env.example` for thresholds, timeout,
search depth, model revision, and blocked domains. Set
`INFORMATION_FINDER_ANSWER_PROVIDER=gemini` and `GEMINI_API_KEY` to
enable structured claims. The module validates source IDs and only exposes cited
sources; provider failures use extractive fallback only when
`INFORMATION_FINDER_LLM_FALLBACK_ENABLED=true`. `gemini-2.5-flash` is a
configurable baseline, not a production-evaluated model. After eval, pin a model
version through `GEMINI_MODEL` and document the evaluated snapshot.

LangGraph Studio can load the graph declared in `langgraph.json` after the
LangGraph CLI is installed.
