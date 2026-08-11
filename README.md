# TravelPlanner

Cập nhật lần cuối: 2026-08-11.

TravelPlanner is a travel-planning product with a Next.js user frontend, a
separate admin frontend, and a modular FastAPI/LangGraph backend.

The current backend is an architecture scaffold. It is designed around the
flow:

```text
user request -> supervisor -> explorer/place checker -> itinerary planner
                         -> information finder or plan editor
```

It is not yet a production travel-data system. Provider integrations,
Marketplace workflows, URL ingestion, and live routing still need to be
implemented behind the module interfaces. Authentication now has a durable
PostgreSQL-backed development flow; configure the auth migration before use.

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
├── database/          # Data assets used by supporting tools
├── routing-data/      # Optional routing engine data
└── docker-compose.yml # Local service orchestration
```

See [docs/codebase-structure.md](docs/codebase-structure.md) for the
detailed backend module boundaries.

## Backend API

The backend runs on port `8000`.

- `GET /health` returns the service health status.
- `POST /v1/agent/invoke` invokes the root planning graph.
- `POST /auth/login` and `POST /auth/register` create cookie sessions.
- `GET /me` reads the current session; `POST /auth/logout` revokes it.

The invoke request uses `thread_id`, `message`, `supplied_candidates`,
`existing_itinerary`, and `edit_operation`.

## Run locally

With Docker Compose:

```bash
docker compose up --build
```

Docker Compose loads backend environment variables from `backend/.env`.
`DATABASE_URL` is intentionally overridden for the Docker PostgreSQL service.

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
