# Schema module, agent và tool

Cập nhật lần cuối: 2026-08-11.

Backend dùng kiến trúc module hóa với LangGraph. Mỗi module expose public
contract qua `public.py`; state và node nội bộ không được module khác truy cập
trực tiếp.

## Ranh giới API

| Endpoint | Input | Output |
|---|---|---|
| `GET /health` | Không có | `{ "status": "ok" }` |
| `POST /v1/agent/invoke` | `InvokeRequest` | `InvokeResponse` |
| `POST /auth/login` | `LoginInput` | `LoginResponse` + cookies |
| `POST /auth/register` | `RegisterInput` | `LoginResponse` + cookies |
| `GET /me` | Session cookie | `AuthUser` |
| `POST /auth/logout` | Session + CSRF cookie | `204 No Content` |
| `GET /admin/knowledge-graph/stats` | Admin session | Knowledge Graph counts |
| `GET /admin/knowledge-graph/ontology` | Admin session | Node types, property keys, and relationship types from `trung-plans/plans-for-new-version/knowledge/schema.yml` |
| `GET /admin/knowledge-graph/entities` | Admin session + filters | Paginated entities |
| `GET /admin/knowledge-graph/entities/filters` | Admin session | Distinct entity types/statuses from `knowledge_entities`, property keys from `knowledge_properties`, and relationship types from `knowledge_relationships` |
| `GET /admin/knowledge-graph/relationships` | Admin session + filters | Paginated relationships |
| `GET/PATCH/DELETE /admin/knowledge-graph/entities/{id}` | Admin session | Entity detail or mutation |

## Các module

| Module | Input | Output |
|---|---|---|
| `supervisor` | `SupervisorInput` | `SupervisorDecision` (`route`, `confidence`, `reason`, tùy chọn `response`, `clarificationQuestion`, `warnings`) |
| `explorer` | `ExplorerInput` | `ExplorerOutput` |
| `information_finder` | `InformationFinderInput` | `InformationFinderOutput` (`answer`, `sources`, `warnings`) |
| `place_checker` | `PlaceCheckerInput` | `PlaceCheckerOutput` |
| `itinerary_planner` | `ItineraryPlannerInput` | `ItineraryPlannerOutput` |
| `plan_editor` | `PlanEditorInput` | `PlanEditorOutput` |

## Các agent hiện có

Tên agent được định nghĩa trong `AgentName`:

- `supervisor`
- `explorer`
- `information_finder`
- `place_checker`
- `itinerary_planner`
- `plan_editor`

Root orchestration graph gọi các agent theo flow:

```text
supervisor
├── information_finder
├── plan_editor
└── explorer -> place_checker -> itinerary_planner
```

Khi provider là `gemini`, Supervisor dùng structured LLM classification trước
cho mọi message; deterministic rules chỉ được dùng khi chọn provider `rules`
hoặc làm runtime fallback. Route `plan_editor` chỉ hợp lệ khi request có cả
itinerary hiện tại và structured edit operation. Route `finish` có thể mang
response ngắn cùng ngôn ngữ cho greeting, câu hỏi về trợ lý hoặc yêu cầu ngoài
phạm vi.

Input của root graph là `RootGraphInput`; output là `RootGraphOutput`.

## Tool và provider adapter

Hiện chưa có standalone tool registry. Các tool/adapter đang có:

| Tool / adapter | Module | Input | Output |
|---|---|---|---|
| `TavilySearchProvider` | `information_finder` | query chuẩn hóa | kết quả tìm kiếm nội bộ có provenance |
| `PostgresSourceRepository` | `information_finder` | query/vector hoặc prepared sources | nguồn cache hybrid |
| `GeminiUrlSourceChunker` | `information_finder` | URL public từ Tavily | semantic chunks có fallback deterministic |
| `GeminiEmbeddingProvider` | `information_finder` | retrieval query/document | vector Gemini chuẩn hóa 384 chiều |
| `ExtractiveAnswerGenerator` | `information_finder` | query và nguồn | câu trả lời fallback có citation |
| `StructuredLlmAnswerGenerator` | `information_finder` | query và ranked sources | `GeneratedAnswer` gồm claim và source ID |
| `DevelopmentCatalog.resolve` | `place_checker` | `PlaceCandidate`, `TripIntent` | `VerifiedPlace \| None` |
| `DevelopmentCatalog.discover` | `place_checker` | `TripIntent`, `limit: int` | `list[VerifiedPlace]` |
| `EstimatedRoutingProvider.travel_minutes` | `itinerary_planner` | Hai giá trị `VerifiedPlace` | Số phút dạng `int` |
| `GeminiLlmClient.generate` | `shared/llm` | system/user prompt, tùy chọn tools | Text response; xoay vòng key từ `GEMINI_API_KEY` |

Các provider interface bên ngoài hiện có:

- `SearchProvider`
- `SourceRepository`
- `EmbeddingProvider`
- `AnswerGenerator`
- `PlaceResolver`
- `PlaceDiscovery`
- `RoutingProvider`
- `LlmClient`

## Shared contract

## Knowledge Graph admin contract

Knowledge Graph is a separate admin module. It owns `knowledge_entities`,
`knowledge_aliases`, `knowledge_properties`, and `knowledge_relationships`,
with PostgreSQL access behind its adapter. Mutating requests require the admin
session and CSRF header. Ontology definitions mirror the versioned knowledge
schema; they do not imply that all catalog data is production-verified. Entity type and
status filter options are queried from `knowledge_entities` at runtime; property
keys and relationship types are queried from their graph tables. A
relationship edit can set both `fromEntityId` and `toEntityId`; the current
entity remains the admin context for the mutation.

Các schema dùng chung chính:

- `TripIntent`
- `Coordinates`
- `PlaceCandidate`
- `VerifiedPlace`
- `ItineraryItem`
- `ItineraryDay`
- `Itinerary`
- `EditOperation`
- `AgentTrace`
- `AgentError`

## Schema request và response của API

- `InvokeRequest`: `thread_id`, `message`, `supplied_candidates`,
  `existing_itinerary`, `edit_operation`.
- `InvokeResponse`: `request_id`, `route`, `response`, `itinerary`,
  `clarification_question`, `warnings`, `sources`.

## Durable trip-chat API

The current frontend planner uses the authenticated `/v1/trip-chats` contract.
Each chat owns a LangGraph thread identifier and persists user/assistant
messages plus the latest itinerary snapshot in PostgreSQL.

`SourceReference` expose `sourceId`, `title`, `url`, `updatedAt`, `dateKind`,
`reviewStatus` và `publishedAt` tùy chọn. `dateKind` phân biệt ngày website tự
công bố cập nhật với ngày hệ thống lấy nguồn. Nguồn Tavily mới mặc định có
`reviewStatus=pending`; chưa có admin review UI.

Internal `GeneratedAnswer` gồm danh sách `AnswerClaim(text, source_ids)` và
`caveat` tùy chọn. Backend từ chối source ID ngoài context, deduplicate ID theo
thứ tự, render marker `[1]` và chỉ ánh xạ metadata cho nguồn thực sự được cite.

Information Finder đã có repository nguồn riêng. Authentication, durable graph
checkpointer, tool import URL, tìm place live, routing live và agent Marketplace
chưa được triển khai.
