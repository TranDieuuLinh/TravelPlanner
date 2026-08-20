# TravelPlanner

Cập nhật lần cuối: 2026-08-20.

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
│   │   │   ├── observability/        # Local request/step diagnostics
│   │   │   └── knowledge-graph/      # Self-built catalog (entity, alias, relationship)
│   │   ├── features/
│   │   │   ├── observability/        # Lightweight observability UI
│   │   │   └── knowledge-graph/      # Knowledge graph feature module
│   │   ├── components/               # Cross-feature UI primitives + observability shell
│   │   ├── api/admin-session/        # Session probe used by the dashboard layout
│   │   ├── login/                    # TravelPlanner admin login
│   │   ├── layout.tsx                # Root metadata + globals
│   │   └── page.tsx                  # Redirects to /observability
│   └── lib/shared/                   # api-client, auth, format helpers
├── packages/          # Shared frontend workspace packages
│   └── api-client/    # Shared API errors and request helpers
├── docs/              # Current codebase documentation
├── routing-data/      # Optional routing engine data
└── docker-compose.yml # Backend and routing service orchestration
```

See [docs/codebase-structure.md](docs/codebase-structure.md) for the
detailed backend module boundaries.

## Backend API

The backend runs on port `8000`.

- `GET /health` returns the service health status.
- `POST /v1/explorer/invoke` runs Explorer extraction directly for testing.
- `POST /v1/agent/invoke` invokes the root planning graph.
- `POST /auth/login` and `POST /auth/register` return a short-lived JWT
  access token and a rotating refresh token. The frontend sends the refresh
  token explicitly to rotate the pair.
- Protected endpoints use `Authorization: Bearer <accessToken>`;
  `POST /auth/refresh` rotates the pair and `POST /auth/logout` revokes the
  refresh session.

The agent request uses camelCase fields `threadId`, `message`, `urls`, `images`,
optional `forceRefresh`, `existingItinerary`, and `editOperation`. Explorer
caches normalized URL artifacts in PostgreSQL `source_documents` when
`DATABASE_URL` is configured; `forceRefresh: true` bypasses the cache lookup.

## Run locally

With Docker Compose:

```bash
cp backend/.env.example backend/.env
docker compose --env-file backend/.env up --build
```

The Compose backend mounts the entire `backend` working tree directly into the
container and runs Uvicorn with reload enabled for development. After changing
backend source or other files under `backend/`, the server sees the changes
without rebuilding; rebuild when changing the Dockerfile, Python dependencies,
base image, or system packages. This full-tree mount is for development only
and should be replaced by an image-only deployment setup for production.

Docker Compose loads all service environment variables from `backend/.env`.
The `--env-file backend/.env` flag also makes Compose port interpolation use the
same file. There are no service-level environment overrides; change values in
that file and restart the affected service.

PostgreSQL is an external dependency and Compose does not download or start a
database image. Select either a local or cloud database only by changing
`DATABASE_URL` in `backend/.env`:

```dotenv
# Backend running in Docker, PostgreSQL running locally on the host
DATABASE_URL=postgresql://USER:PASSWORD@host.docker.internal:5432/DBNAME

# Or use a cloud PostgreSQL endpoint
DATABASE_URL=postgresql://USER:PASSWORD@CLOUD_HOST:5432/DBNAME?sslmode=require
```

When the backend itself runs directly on the host, use `localhost` instead of
`host.docker.internal` for a local PostgreSQL server. The selected database must
already exist and have the required extensions and migrations applied.

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

The admin frontend provides a lightweight `/observability` console for local
request traces, LangGraph steps, tool input/output previews, durations and
errors. Records are kept in a bounded local JSON snapshot at
`backend/logs/observability/` (up to 500 requests); this is development/admin
diagnostics, not durable production monitoring. Tool previews are truncated and redact
common secret fields such as API keys, tokens and passwords.

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
