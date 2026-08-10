# Database schema

Last checked: 2026-08-10

## Current status

The current backend does not define any database tables. It is a FastAPI and
LangGraph scaffold using an in-memory checkpointer:

```text
backend/src/app/shared/persistence/checkpointer.py
└── InMemorySaver
```

There are currently no SQLAlchemy models, Alembic migrations, repository
implementations, or database connection settings in the new backend. The
previous backend's tables and migrations were removed and are not part of the
current runtime.

## Tables

No tables currently exist in the backend schema.

Therefore there are no table columns to document yet. The values held during a
graph run are runtime state, not database columns.

## Runtime state kept in memory

For clarity, the current root graph state contains these fields. This is not a
database table and is lost when the process is restarted:

| Field | Type | Short description |
|---|---|---|
| `request_id` | `str` | Unique id for the current API request. |
| `message` | `str` | User's planning or information request. |
| `supplied_candidates` | `list[PlaceCandidate]` | Places supplied by the caller. |
| `existing_itinerary` | `Itinerary \| None` | Existing itinerary used for editing. |
| `edit_operation` | `EditOperation \| None` | Requested structured edit. |
| `decision` | `SupervisorDecision` | Route selected by the supervisor. |
| `explorer_output` | `ExplorerOutput` | Parsed intent and candidate places. |
| `information_output` | `InformationFinderOutput` | Answer and source references. |
| `place_output` | `PlaceCheckerOutput` | Verified, rejected, and coverage results. |
| `intent` | `TripIntent` | Normalized destination and trip constraints. |
| `itinerary` | `Itinerary` | Generated or edited itinerary. |
| `response` | `str` | User-facing textual response. |
| `clarification_question` | `str \| None` | Question when more information is needed. |
| `warnings` | `list[str]` | Non-fatal warnings from the workflow. |

## Future database work

When durable persistence is introduced, add the database models, migrations,
repositories, and an ADR together. The database schema should not be inferred
from the in-memory state above without an explicit design decision.
