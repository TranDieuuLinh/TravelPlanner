# Information Finder Structured Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add typed semantic answer blocks to Information Finder, persist them beside legacy text in TripChat, and render resolved entities safely in the frontend.

**Architecture:** Information Finder owns the discriminated block contracts, source validation, boilerplate filtering, fallback shaping, and entity-span materialization. TripChat transports the public output and stores `content_blocks` as JSONB beside `content`; frontend selects structured rendering when blocks exist and otherwise keeps Markdown compatibility. The LLM never creates source URLs or entity IDs; the backend resolves both citations and entity spans.

**Tech Stack:** Python 3, Pydantic v2, FastAPI/LangGraph, PostgreSQL JSONB migrations, React/TypeScript, ReactMarkdown, Vitest/Node frontend tests, pytest.

## Global Constraints

- JSON API fields use camelCase; Python fields use snake_case.
- `AnswerBlock` is a Pydantic discriminated union and must not become `dict[str, Any]`.
- Runtime persistence target is `agent_trip_chat_messages`; legacy `trip_chat_messages` is unchanged.
- Existing uncommitted Information Finder, Knowledge Graph entity-linking, and MarkdownMessage changes must be preserved.
- Boilerplate filtering is generic and cannot be hard-coded for one website.
- `content` remains a readable Markdown/text compatibility field; structured data is stored separately in `content_blocks`.
- Backend source/test files stay below 400 lines where splitting by responsibility is practical.
- No renderer uses `dangerouslySetInnerHTML`.
- Every production behavior change begins with a test that is run and observed failing.

---

### Task 1: Define public structured block contracts and entity spans

**Files:**
- Create: `backend/src/app/modules/information_finder/structured_blocks.py`
- Modify: `backend/src/app/modules/information_finder/contract.py`
- Modify: `backend/src/app/modules/information_finder/public.py`
- Test: `backend/src/app/modules/information_finder/tests/test_structured_contract.py`

**Interfaces:**
- Produces `AnswerBlock`, `InlineSpan`, `EntitySpan`, `InformationFinderOutput.content_blocks`, and `GeneratedAnswer.blocks`.
- `InlineSpan` is a discriminated union: `TextSpan(type="text", text)` or `EntitySpan(type="entity", text, entity_id)`.
- Text-bearing block/item models expose `inline_spans: list[InlineSpan]` with default `[]`; spans are backend output, not LLM-created IDs.

- [ ] **Step 1: Write failing contract tests.**

```python
def test_fact_list_and_verse_serialize_with_camel_case_and_entity_span():
    output = InformationFinderOutput(
        answer="Hồ Gươm ở Hà Nội.",
        content_blocks=[
            FactListBlock(
                type="factList",
                title="Thông tin nổi bật",
                items=[FactItem(
                    label="Địa điểm",
                    text="Hồ Gươm ở Hà Nội.",
                    highlights=["Hà Nội"],
                    source_ids=["source-1"],
                    inline_spans=[
                        TextSpan(type="text", text="Hồ Gươm ở "),
                        EntitySpan(type="entity", text="Hà Nội", entity_id="place-1"),
                        TextSpan(type="text", text="."),
                    ],
                )],
            ),
            VerseBlock(type="verse", title="Bài thơ", author="Tác giả", lines=["Dòng một", "Dòng hai"], source_ids=["source-2"]),
        ],
    )
    payload = output.model_dump(by_alias=True)
    assert payload["contentBlocks"][0]["items"][0]["inlineSpans"][1]["entityId"] == "place-1"
    assert payload["contentBlocks"][1]["lines"] == ["Dòng một", "Dòng hai"]
```

- [ ] **Step 2: Run the focused test and verify the expected import/validation failure.**

Run: `cd backend; $env:PYTHONPATH='K:\VSF\VSF_TravelPlanner-clean\backend\src'; pytest src/app/modules/information_finder/tests/test_structured_contract.py -q`

Expected: FAIL because the structured block models and `contentBlocks` field do not yet exist.

- [ ] **Step 3: Implement the smallest typed models.**

Use `Literal` discriminators and `Field(discriminator="type")`. Keep source IDs and entity IDs as strings with non-empty validation. Add all eight block types, typed item models, `GeneratedAnswer.blocks`, and `InformationFinderOutput.content_blocks`.

- [ ] **Step 4: Run the focused test and verify it passes.**

Run the same pytest command. Expected: PASS with camelCase serialization and no internal snake_case fields in the JSON payload.

- [ ] **Step 5: Export only supported public types.**

Add the block union and output model to `public.py`; do not make other modules import `structured_blocks.py` internals directly.

### Task 2: Normalize source noise and build structured extractive fallback

**Files:**
- Create: `backend/src/app/modules/information_finder/structured_content.py`
- Modify: `backend/src/app/modules/information_finder/normalization.py`
- Modify: `backend/src/app/modules/information_finder/adapters/development.py`
- Test: `backend/src/app/modules/information_finder/tests/test_structured_content.py`
- Test: `backend/src/app/modules/information_finder/tests/test_extractive_answer_generator.py`

**Interfaces:**
- Produces `clean_source_sentences(content, query, title) -> list[str]`.
- Produces `fallback_blocks(query, sources) -> list[AnswerBlock]` and a bounded `GeneratedAnswer`.
- Existing `select_relevant_excerpt` remains usable by search prompts and is updated to reject generic navigation/footer fragments before truncating.

- [ ] **Step 1: Add failing tests for generic boilerplate removal.**

```python
def test_clean_source_sentences_removes_navigation_footer_and_company_copy():
    text = "Di tích được xếp hạng năm 2013. Previous Next Liên kết website. Công ty ABC Tuyển dụng Văn phòng."
    sentences = clean_source_sentences(text, "xếp hạng", "Hồ Hoàn Kiếm")
    assert sentences == ["Di tích được xếp hạng năm 2013."]
```

```python
def test_extractive_fallback_returns_short_fact_blocks_not_raw_snippet():
    generated = asyncio.run(ExtractiveAnswerGenerator().generate("xếp hạng", [source(long_noisy_content)]))
    assert len(generated.blocks) <= 5
    assert generated.blocks[0].type == "factList"
    assert "Previous" not in generated.model_dump_json()
    assert len(generated.blocks[0].items[0].text.split()) <= 25
```

- [ ] **Step 2: Run the tests and confirm they fail for missing cleaner/blocks.**

Run: `cd backend; $env:PYTHONPATH='K:\VSF\VSF_TravelPlanner-clean\backend\src'; pytest src/app/modules/information_finder/tests/test_structured_content.py src/app/modules/information_finder/tests/test_extractive_answer_generator.py -q`

Expected: FAIL because the generic cleaner and structured fallback output are absent.

- [ ] **Step 3: Implement generic noise filtering and sentence boundaries.**

Add normalized marker rules for navigation (`Previous`, `Next`, `Trang chủ`, breadcrumb), footer/contact/company/recruitment/branch/promotional patterns, malformed fragments, and encoding artifacts. Score remaining sentences by query/title overlap, keep at most five, and cut only at sentence or word boundaries.

- [ ] **Step 4: Implement fallback block shaping.**

Create one `factList` block with short labeled items and `source_ids` from the source that supplied each sentence. If no clean sentence remains, create one short `paragraph` explaining that suitable information is unavailable and cite the first source. Preserve entity candidates from the fallback path.

- [ ] **Step 5: Run focused tests and all existing normalization/fallback tests.**

Run: `cd backend; $env:PYTHONPATH='K:\VSF\VSF_TravelPlanner-clean\backend\src'; pytest src/app/modules/information_finder/tests/test_structured_content.py src/app/modules/information_finder/tests/test_normalization.py src/app/modules/information_finder/tests/test_extractive_answer_generator.py -q`

Expected: PASS; update old assertions only where they describe the intentionally changed structured fallback contract.

### Task 3: Make the LLM generator and answer pipeline produce/validate blocks

**Files:**
- Modify: `backend/src/app/modules/information_finder/prompts.py`
- Modify: `backend/src/app/modules/information_finder/adapters/llm_answer_generator.py`
- Modify: `backend/src/app/modules/information_finder/answering.py`
- Modify: `backend/src/app/modules/information_finder/entity_linking.py`
- Test: `backend/src/app/modules/information_finder/tests/test_llm_answer_generator.py`
- Test: `backend/src/app/modules/information_finder/tests/test_answer_validation.py`
- Test: `backend/src/app/modules/information_finder/tests/test_entity_linking.py`

**Interfaces:**
- `validate_and_render_answer` returns `(answer_text, content_blocks, cited_sources)`.
- `materialize_entity_spans(blocks, entity_names, entity_candidates, resolver)` returns blocks with only resolved `EntitySpan` entries.
- `generate_and_render_answer` returns `(answer_text, content_blocks, cited_sources, warnings)`.

- [ ] **Step 1: Add failing LLM and validation tests.**

Cover a valid `factList`, valid `verse` line order, invalid source ID rejection, source IDs in every block/item, no URL/entity ID generation in the prompt schema, and entity span output for a resolved node while unresolved text remains plain.

- [ ] **Step 2: Run the focused tests and observe failures.**

Run: `cd backend; $env:PYTHONPATH='K:\VSF\VSF_TravelPlanner-clean\backend\src'; pytest src/app/modules/information_finder/tests/test_llm_answer_generator.py src/app/modules/information_finder/tests/test_answer_validation.py src/app/modules/information_finder/tests/test_entity_linking.py -q`

Expected: FAIL because the schema still expects claims and entity linking only rewrites Markdown text.

- [ ] **Step 3: Update prompt/schema and parse `GeneratedAnswer`.**

Tell the model to choose 3–5 useful facts, use `verse` only for identified poem/song structure, omit boilerplate, return only supplied source IDs, return entity candidates without IDs, and preserve verse line order. Keep source excerpts bounded.

- [ ] **Step 4: Implement validation, compatibility text rendering, and block entity spans.**

Validate every block/item source ID against `available_sources`. Render blocks into concise Markdown/text for legacy `answer`. Link entities structurally by walking each text-bearing field and resolving candidate names; never inject raw HTML or guessed IDs. Keep the current Markdown entity-linking behavior for the legacy `answer` string so old chat remains functional.

- [ ] **Step 5: Run the focused tests and existing answer tests.**

Expected: PASS with citations mapped from backend source order, preserved verse lines, and structured fallback on provider errors.

### Task 4: Thread structured output through Information Finder and root API

**Files:**
- Modify: `backend/src/app/modules/information_finder/service.py`
- Modify: `backend/src/app/modules/information_finder/state.py` only if state serialization requires it
- Modify: `backend/src/app/orchestration/nodes.py` only to preserve the public output unchanged
- Modify: `backend/src/app/api/schemas.py`
- Modify: `backend/src/app/api/router.py`
- Test: `backend/src/app/modules/information_finder/tests/test_service.py`
- Test: `backend/tests/api/test_invoke.py`

**Interfaces:**
- `InformationFinderService.find()` returns `InformationFinderOutput(answer, content_blocks, sources, warnings)`.
- `InvokeResponse` exposes `contentBlocks` with default `[]` for non-Information-Finder routes.

- [ ] **Step 1: Add failing service/API assertions.**

Assert that a successful Information Finder result includes blocks, that an empty-source response includes `contentBlocks=[]`, and that API serialization uses `contentBlocks` rather than `content_blocks`.

- [ ] **Step 2: Run focused service/API tests and observe missing field failures.**

- [ ] **Step 3: Pass blocks through service and API boundary.**

Keep orchestration as mapping only; do not move filtering or rendering rules into `api/` or orchestration.

- [ ] **Step 4: Run Information Finder graph/service and API tests.**

Also run `python -c "import app; print(app.__file__)"` from `backend` with the clean repo `PYTHONPATH` and verify it contains `K:\VSF\VSF_TravelPlanner-clean\backend\src`.

### Task 5: Persist `content_blocks` in runtime TripChat

**Files:**
- Create: `backend/migrations/008_trip_chat_content_blocks.sql`
- Modify: `backend/src/app/modules/trip_chat/contract.py`
- Modify: `backend/src/app/modules/trip_chat/adapters/postgres.py`
- Modify: `backend/src/app/modules/trip_chat/adapters/in_memory.py`
- Modify: `backend/src/app/modules/trip_chat/service.py`
- Modify: `backend/src/app/modules/trip_chat/router.py` only if response mapping needs it
- Test: `backend/src/app/modules/trip_chat/tests/test_postgres_repository.py`
- Test: `backend/src/app/modules/trip_chat/tests/test_service.py`
- Test: `backend/tests/api/test_trip_chat_memory_api.py`
- Modify: `docs/schema.md`
- Modify: `docs/database-schema.md`

**Interfaces:**
- `TripChatMessage.content_blocks: list[AnswerBlock | dict]` is public JSON-compatible data with default `[]`.
- `TripChatRepository.append_exchange(..., assistant["content_blocks"])` persists one assistant row with separate text/JSON fields.

- [ ] **Step 1: Add failing tests for one-row persistence and legacy reads.**

Assert `content_blocks` is included in the insert, is read back as a list, and missing/null legacy values become `[]`; user messages also return `[]`.

- [ ] **Step 2: Run TripChat tests and observe expected missing-column/field failures.**

- [ ] **Step 3: Add the additive migration.**

```sql
BEGIN;
ALTER TABLE agent_trip_chat_messages
  ADD COLUMN IF NOT EXISTS content_blocks jsonb NOT NULL DEFAULT '[]'::jsonb;
COMMIT;
```

- [ ] **Step 4: Update contract, service, in-memory adapter, and PostgreSQL adapter.**

Select `content_blocks` with the message, serialize JSONB separately from `content`, and use `or []` on read. Do not alter `007_legacy_runtime_schema.sql`.

- [ ] **Step 5: Update docs and run TripChat/API tests.**

Document the new runtime column and compatibility behavior with `Cập nhật lần cuối: 2026-08-17` in non-numbered docs.

### Task 6: Render structured blocks and preserve entity interactions in frontend

**Files:**
- Create: `frontend/src/features/planner/components/AnswerBlockRenderer.tsx`
- Create: `frontend/src/features/planner/components/answer-blocks.tsx` if splitting renderers improves focus
- Create: `frontend/src/features/planner/lib/answer-blocks.ts`
- Modify: `frontend/src/features/planner/api/plans.ts`
- Modify: `frontend/src/features/planner/lib/trip-chat-mapping.ts`
- Modify: `frontend/src/features/planner/components/PlannerChatUI.tsx`
- Modify: `frontend/src/features/planner/components/MarkdownMessage.tsx` only to reuse entity preview safely
- Modify: `frontend/src/features/planner/styles/planner-shell.css`
- Test: `frontend/src/features/planner/lib/answer-blocks.test.mjs`
- Test: component tests using the repository’s configured frontend test runner

**Interfaces:**
- `AnswerBlockRenderer({ blocks, sources })` renders all eight block types.
- `InlineSpan` with `type="entity"` calls the existing entity preview/modal interaction using `entityId`; `type="text"` renders a normal React text node.
- `PlannerChatUI` chooses structured rendering when `message.contentBlocks?.length` is non-zero, otherwise `MarkdownMessage`.

- [ ] **Step 1: Add failing renderer/helper tests.**

Cover all block discriminators, verse line breaks, labels/highlights, citation URL mapping, entity hover/click wiring, plain-text unresolved entities, Markdown fallback, XSS strings rendered as text, and mobile-safe comparison layout class names.

- [ ] **Step 2: Run frontend tests and observe missing renderer failures.**

- [ ] **Step 3: Implement typed frontend block models and safe span/highlight helpers.**

Use React nodes for escaping. Match highlights by text segments without raw HTML, do not overlap spans, ignore missing highlights, and cap rendered highlights at three per item.

- [ ] **Step 4: Implement the eight small renderers and integrate message selection.**

Use a blockquote for quote, ordered list for steps, compact cards for comparison, and lightweight emphasis for notice. Citation indices resolve only through the supplied `sources` array. Entity spans reuse the existing `InteractiveEntityLink` behavior and never fall back to name-based links when no ID exists.

- [ ] **Step 5: Fix Markdown list whitespace and run frontend tests/typecheck/lint.**

Add `.markdownMessage { white-space: normal; }`, list item padding, and paragraph margin rules without changing user bubbles. Run `npm run lint`, `npm run typecheck`, and `npm run test:planner` from `frontend`.

### Task 7: Integration verification and UI smoke test

**Files:**
- Modify only files required by failing integration tests or documented schema changes.
- Test: existing Information Finder, TripChat, Knowledge Graph/entity-linking, API, and frontend suites.

- [ ] **Step 1: Verify clean-repo imports before backend tests.**

Run from `backend`: `$env:PYTHONPATH='K:\VSF\VSF_TravelPlanner-clean\backend\src'; python -c "import app; print(app.__file__)"`. Stop and correct environment if the path is not the clean repo.

- [ ] **Step 2: Run focused backend suites.**

Run Information Finder tests, TripChat tests, Knowledge Graph/entity-linking tests, and changed API tests. Record failures with their first failing boundary before changing code.

- [ ] **Step 3: Run compile and frontend checks.**

Run `python -m compileall src` from `backend`, then the frontend typecheck/lint/test scripts from `frontend`.

- [ ] **Step 4: Run the full relevant verification set.**

Exercise one `factList`, one `verse`, one fallback answer, one resolved entity, and one unresolved entity through the API/UI if the local dev server and browser tooling are available. Check desktop and narrow mobile viewport for overflow.

- [ ] **Step 5: Review diff scope and file sizes.**

Run `git status --short`, `git diff --check`, inspect only intended module/API/persistence/frontend/doc files, and verify backend changed files are below 400 lines where practical. Do not reset or overwrite existing user changes.
