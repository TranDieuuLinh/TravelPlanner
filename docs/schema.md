# Schema module, agent và tool

Cập nhật lần cuối: 2026-08-10.

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
| `supervisor` | `SupervisorInput` | `SupervisorDecision` |
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

Input của root graph là `RootGraphInput`; output là `RootGraphOutput`.

## Tool và provider adapter

Hiện chưa có standalone tool registry. Các tool/adapter đang có:

| Tool / adapter | Module | Input | Output |
|---|---|---|---|
| `TavilySearchProvider` | `information_finder` | query chuẩn hóa | kết quả tìm kiếm nội bộ có provenance |
| `PostgresSourceRepository` | `information_finder` | query/vector hoặc prepared sources | nguồn cache hybrid |
| `MultilingualE5EmbeddingProvider` | `information_finder` | query/passage | vector chuẩn hóa 384 chiều |
| `ExtractiveAnswerGenerator` | `information_finder` | query và nguồn | câu trả lời fallback có citation |
| `DevelopmentCatalog.resolve` | `place_checker` | `PlaceCandidate`, `TripIntent` | `VerifiedPlace \| None` |
| `DevelopmentCatalog.discover` | `place_checker` | `TripIntent`, `limit: int` | `list[VerifiedPlace]` |
| `EstimatedRoutingProvider.travel_minutes` | `itinerary_planner` | Hai giá trị `VerifiedPlace` | Số phút dạng `int` |
| `GeminiLlmClient.generate` | `shared/llm` | system/user prompt | Text response; xoay vòng key từ `GEMINI_API_KEY` |

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

Information Finder đã có repository nguồn riêng. Authentication, durable graph
checkpointer, tool import URL, tìm place live, routing live và agent Marketplace
chưa được triển khai.
