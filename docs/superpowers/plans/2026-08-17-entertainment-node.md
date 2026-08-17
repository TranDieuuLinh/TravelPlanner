# Entertainment Node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the `Entertainment` node type and reclassify the identified non-travel entertainment/wellness places without changing their IDs or graph references.

**Architecture:** Keep the existing entity IDs and relationships intact; change only `knowledge_entities.entity_type` for the approved candidate set. Expose `Entertainment` through the knowledge-graph ontology and place-search type mapping, while leaving the generic `TravelPlace` query restricted to `TravelPlace`.

**Tech Stack:** Python, FastAPI/LangGraph ontology payloads, PostgreSQL, pytest, SQL migration.

## Global Constraints

- Use `Entertainment` exactly as the node type spelling.
- Preserve all existing entity IDs and relationship rows.
- Candidate filter is the previously reviewed name-based set matching spa, massage, billiard/billard, bida, karaoke, gym, fitness, or nail.
- Do not include `Entertainment` in the `travel place` hint; its dedicated hint maps to `Entertainment`.
- Update `Cập nhật lần cuối` to `2026-08-17` in touched non-numbered documentation.

### Task 1: Add the node type to ontology and runtime mapping

**Files:**
- Modify: `backend/src/app/modules/knowledge_graph/ontology.py`
- Modify: `backend/src/app/modules/place_checker/adapters/postgres_catalog_mapping.py`
- Test: `backend/src/app/modules/knowledge_graph/tests/test_service.py`
- Test: `backend/src/app/modules/place_checker/tests/test_postgres_catalog_policy.py`

- [x] Add `Entertainment` to `NODE_TYPES` and give it the same place-required and place-optional properties as `TravelPlace`.
- [x] Add `Entertainment` to place-type mapping with canonical type `entertainment`; map the `entertainment` hint only to this type.
- [x] Keep the `travel place` hint mapped only to `TravelPlace`.
- [x] Add assertions for ontology exposure and hint mapping.
- [x] Run the focused knowledge-graph and place-checker tests.

### Task 2: Document the schema and data migration

**Files:**
- Modify: `docs/schema.md`
- Modify: `docs/database-schema.md`
- Modify: `docs/codebase-structure.md`
- Create: `backend/migrations/011_entertainment_node.sql`

- [x] Document `Entertainment` as a place-like node with coordinates, address, opening hours, style, and relationship support.
- [x] Document that `TravelPlace` retrieval excludes `Entertainment`, while an explicit entertainment type can retrieve it.
- [x] Add an idempotent SQL migration that updates only `TravelPlace` rows matching the approved keyword predicate to `Entertainment`, preserving IDs and relationships.
- [x] Include pre/post count checks in migration comments without embedding secrets or raw external payloads.

### Task 3: Apply and verify the cloud data migration

**Files:**
- Use: `backend/migrations/011_entertainment_node.sql`

- [x] Confirm the candidate count and unresolved relationship references in a read-only preflight.
- [x] Run the migration in one transaction against the Aiven database.
- [x] Verify the converted count, zero matching candidates remaining as `TravelPlace`, unchanged IDs, and unchanged relationship row count for converted entities.
- [x] Verify `travel place` search remains restricted to `TravelPlace` and `entertainment` search resolves to `Entertainment` in the runtime mapping.

### Task 4: Final verification

**Files:**
- No additional files.

- [x] Run focused tests and `python -m compileall src` from `backend`.
- [x] Review the final diff and file sizes.
- [x] Report the exact converted count and any limitation caused by the absent source `trung-plans/plans-for-new-version/knowledge/schema.yml` file.
