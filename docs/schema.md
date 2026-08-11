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

Supervisor áp dụng precedence: structured edit hợp lệ, deterministic intent
rules, structured LLM classification (nếu bật), rồi fallback an toàn. Route
`plan_editor` chỉ hợp lệ khi request có cả itinerary hiện tại và structured edit
operation; greeting/out-of-scope trả về `finish` với response có ý nghĩa.

Input của root graph là `RootGraphInput`; output là `RootGraphOutput`.

## Tool và provider adapter

Hiện chưa có standalone tool registry. Các tool/adapter đang có:

| Tool / adapter | Module | Input | Output |
|---|---|---|---|
| `TavilySearchProvider` | `information_finder` | query chuẩn hóa | kết quả tìm kiếm nội bộ có provenance |
| `PostgresSourceRepository` | `information_finder` | query/vector hoặc prepared sources | nguồn cache hybrid |
| `GeminiEmbeddingProvider` | `information_finder` | retrieval query/document | vector Gemini chuẩn hóa 384 chiều |
| `ExtractiveAnswerGenerator` | `information_finder` | query và nguồn | câu trả lời fallback có citation |
| `StructuredLlmAnswerGenerator` | `information_finder` | query và ranked sources | `GeneratedAnswer` gồm claim và source ID |
| `DevelopmentCatalog.resolve` | `place_checker` | `PlaceCandidate`, `TripIntent` | `VerifiedPlace \| None` |
| `DevelopmentCatalog.discover` | `place_checker` | `TripIntent`, `limit: int` | `list[VerifiedPlace]` |
| `EstimatedRoutingProvider.travel_minutes` | `itinerary_planner` | Hai giá trị `VerifiedPlace` | Số phút dạng `int` |
| `GeminiLlmClient.generate` | `shared/llm` | system/user prompt | Text response; xoay vòng key từ `GEMINI_API_KEY` |
| `SearchPlacesTool.search` | `shared/tools/search_places` | `PlaceSearchRequest` | `PlaceSearchResult` có status, selected, top matches, provider attempts và resolution reason |

`SearchPlacesTool` hỗ trợ hai mode: `named_place` để xác minh identity được nêu
tên và `requirement` để tìm venue phù hợp với món ăn, đồ uống hoặc hoạt động.
Với named place, policy mặc định chỉ nhận top-1 khi score lớn hơn `0.82` và
margin với top-2 ít nhất `0.08`. Match mạnh nhưng quá sát nhau trả
`needs_review` và không dùng external provider để đoán lại branch đã có trong
Knowledge Graph. KG miss hoặc toàn bộ match yếu mới được fallback khi caller
cho phép và adapter external đã được cấu hình.

Contract dùng chung của tool gồm `AdministrativeArea`, `PlaceSearchRequest`,
`PlaceProviderCandidate`, `PlaceSearchMatch`, `ProviderAttempt` và
`PlaceSearchResult`. Result phân biệt `resolved`, `needs_review`, `unresolved`
và `provider_error`; lỗi provider retryable không bị diễn giải thành no-match.
Package hiện chỉ có `InMemoryPlaceSearch` cho test/development và adapter này
không tự tạo place placeholder. PostgreSQL KG và Playwright production adapter
chưa được triển khai; PlaceChecker hiện vẫn dùng `DevelopmentCatalog`.

Các provider interface bên ngoài hiện có:

- `SearchProvider`
- `SourceRepository`
- `EmbeddingProvider`
- `AnswerGenerator`
- `PlaceResolver`
- `PlaceDiscovery`
- `RoutingProvider`
- `LlmClient`
- `KnowledgeGraphPlaceSearch`
- `ExternalPlaceSearch`

## Shared contract

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
