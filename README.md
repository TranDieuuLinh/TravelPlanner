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
durable persistence, authentication, Marketplace workflows, anti-bot-resilient
URL ingestion, and live routing still need production implementations behind
the module interfaces. Explorer currently has bounded YouTube/social/website
and image import adapters, but individual third-party sources may still block
automated downloads.

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
- `POST /v1/explorer/invoke` runs Explorer extraction directly for testing.
- `POST /v1/agent/invoke` invokes the root planning graph.

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
