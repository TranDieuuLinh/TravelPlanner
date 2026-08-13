# TravelPlanner

Cập nhật lần cuối: 2026-08-13.

TravelPlanner is a travel-planning product with a Next.js user frontend, a
separate admin frontend, and a modular FastAPI/LangGraph backend.

The current backend is an architecture scaffold. It is designed around the
flow:

```text
user request -> supervisor -> explorer/place checker -> itinerary planner
                         -> information finder or plan editor
```

It is not yet a production travel-data system. Production-grade provider
coverage, durable graph-state persistence, Marketplace workflows,
anti-bot-resilient URL ingestion, and live routing still need implementations
behind the module interfaces. Authentication now has a PostgreSQL-backed
development flow; configure the auth migration before use. Explorer currently
has bounded YouTube/social/website and image import adapters, but individual
third-party sources may still block automated downloads.

## Repository structure

```text
travelplanner/
├── backend/          # FastAPI + LangGraph backend
│   ├── src/app/
│   │   ├── api/       # HTTP schemas, dependencies, and routes
│   │   ├── core/      # Shared configuration and errors
│   │   ├── modules/   # Vertical feature modules
│   │   ├── orchestration/ # Root graph and cross-module mapping
│   │   └── shared/    # Contracts and persistence adapters
│   └── tests/         # Backend integration tests
├── frontend/         # User-facing Next.js application
├── admin-frontend/    # Admin/control Next.js application
│   ├── app/
│   │   ├── (dashboard)/
│   │   │   ├── observability/        # Langfuse embed (traces, sessions, playground, datasets, evaluations)
│   │   │   └── knowledge-graph/      # Self-built catalog (entity, alias, relationship)
│   │   ├── features/
│   │   │   ├── observability/        # Langfuse iframe module
│   │   │   └── knowledge-graph/      # Knowledge graph feature module
│   │   ├── components/               # Cross-feature UI primitives + Langfuse embed shell
│   │   ├── api/admin-session/        # Session probe used by the dashboard layout
│   │   ├── login/                    # TravelPlanner admin login
│   │   ├── layout.tsx                # Root metadata + globals
│   │   └── page.tsx                  # Redirects to /observability
│   └── lib/shared/                   # api-client, auth, format helpers
├── packages/          # Shared frontend workspace packages
│   └── api-client/    # Shared API errors and request helpers
├── docs/              # Current codebase documentation
├── routing-data/      # Optional routing engine data
└── docker-compose.yml # Backend and optional routing service orchestration
```

See [docs/codebase-structure.md](docs/codebase-structure.md) for the
detailed backend module boundaries.

## Backend API

The backend runs on port `8000`.

- `GET /health` returns the service health status.
- `POST /v1/explorer/invoke` runs Explorer extraction directly for testing.
- `POST /v1/agent/invoke` invokes the root planning graph.
- `POST /auth/login` and `POST /auth/register` create cookie sessions.
- `GET /me` reads the current session; `POST /auth/logout` revokes it.

The agent request uses camelCase fields `threadId`, `message`, `urls`, `images`,
optional `forceRefresh`, `existingItinerary`, and `editOperation`. Explorer
caches normalized URL artifacts in PostgreSQL `source_documents` when
`DATABASE_URL` is configured; `forceRefresh: true` bypasses the cache lookup.

## Run locally

With Docker Compose:

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

The Compose backend mounts `backend/src` directly into the container and runs
Uvicorn with reload enabled for development. After changing Python source,
the server reloads automatically; rebuild only when changing the Dockerfile,
Python dependencies, base image, or system packages.

Docker Compose loads backend environment variables from `backend/.env`; the
backend uses the cloud PostgreSQL connection in `DATABASE_URL` without a local
database service or URL override.

Run the backend directly:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

Run the user frontend:

```bash
cd frontend
npm install
npm run dev
```

Run the admin frontend:

```bash
cd admin-frontend
npm install
npm run dev
```

Run checks for both frontends from the repository root:

```bash
npm install
npm run typecheck
npm test
npm run build
```

## Admin frontend

The admin frontend now embeds Langfuse (self-hosted at `http://localhost:3005`)
for traces, sessions, playground, datasets and evaluations, and keeps a
self-built Knowledge Graph for the entity/alias/relationship catalog.

TravelPlanner admin session is still required to enter `/login`; Langfuse uses
its own login screen inside the iframe (separate login). The admin can open
any Langfuse view in a new browser tab via the `↗ Mở tab mới` button.

To target a different Langfuse instance, set `NEXT_PUBLIC_LANGFUSE_URL`.

## Verification

```bash
cd backend
pytest

cd ../frontend
npm run typecheck
npm run build

cd ../admin-frontend
npm run typecheck
```
