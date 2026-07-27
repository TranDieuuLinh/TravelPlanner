# VSF Travel Starter

Next.js + FastAPI starter for a travel planning marketplace. The initial codebase covers user management and leaves clean module boundaries for AI profile planning, creator plans, marketplace purchases, reviews, notifications, achievements, and payments.

## Structure

- `frontend/`: Next.js App Router, TypeScript, Zod, module-based UI.
- `backend/`: FastAPI, SQLAlchemy, Alembic, module-based API.
- `docker-compose.yml`: Postgres and backend runtime.

## Run Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API docs: `http://localhost:8000/docs`

## Run Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Frontend: `http://localhost:3000`

## Run Postgres With Docker

```bash
docker compose up postgres
cd backend
./scripts/migrate.sh
```

## Core Product Areas

- Accounts: registration, login integrations, profiles, travel preferences.
- Host planning: destination input, reference URLs, AI planner, budget estimates, route optimization.
- Profile editing: drag/drop itinerary, lock places, reschedule, offline progress.
- Marketplace: discover paid travel plans, favorites, checkout, purchased plan copying.
- Creator tools: plan editor, media, drafts, publishing, analytics, reviews.
- Platform: revenue sharing, achievements, admin user management.
