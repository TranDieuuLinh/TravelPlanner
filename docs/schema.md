# Schema module, agent và tool

Cập nhật lần cuối: 2026-08-12.

Backend dùng kiến trúc module hóa với LangGraph. Mỗi module expose public
contract qua `public.py`; state và node nội bộ không được module khác truy cập
trực tiếp.

## Ranh giới API

| Endpoint | Input | Output |
|---|---|---|
| `GET /health` | Không có | `{ "status": "ok" }` |
| `POST /v1/explorer/invoke` | `ExplorerInput` | `ExplorerOutput` |
| `POST /v1/agent/invoke` | `InvokeRequest` | `InvokeResponse` |
| `POST /auth/login` | `LoginInput` | `LoginResponse` + cookies |
| `POST /auth/register` | `RegisterInput` | `LoginResponse` + cookies |
| `GET /me` | Session cookie | `AuthUser` |
| `POST /auth/logout` | Session + CSRF cookie | `204 No Content` |
| `GET /admin/knowledge-graph/stats` | Admin session | Knowledge Graph counts |
| `GET /admin/knowledge-graph/ontology` | Admin session | Node types, property keys, and relationship types from `trung-plans/plans-for-new-version/knowledge/schema.yml` |
| `GET /admin/knowledge-graph/entities` | Admin session + filters | Paginated entities; `search`, `excludeNames`, and `missingProperties` support comma-separated keywords |
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
Root state nội bộ có `conversation_context` gồm tối đa sáu user message gần
nhất để Supervisor xử lý follow-up. API không nhận raw history riêng; context
được giữ theo `thread_id` trong checkpointer hiện tại.

### Explorer

`ExplorerInput` nhận `rawPrompt` tùy chọn, `urls`, `images` và `forceRefresh`
tùy chọn. `forceRefresh=true` buộc URL extraction bỏ qua cache. Explorer output
không có `schemaVersion` và gồm:

- `status`: `ready`, `clarification` hoặc `error`;
- `intakeId`, `input_ADM`;
- `places`, trong đó mỗi place có `sourcePlaces`, `sourceTimeHint` và
  `addressHint`; không có `sourceOrder`/`sourceDay`;
- `inputItems`, chỉ lấy food, drink hoặc activity được nêu rõ trong raw prompt;
- `urlNotes`, giữ chi tiết hữu ích có evidence từ URL/ảnh/OCR/STT/metadata,
  gồm access/timing/price/caution, hoạt động cụ thể tại địa điểm, trải nghiệm
  đặc trưng và fun fact; loại lời quảng cáo chung chung;
- `days`, `budget`, `people`, `shortPreferences`, `shortAvoids`;
- clarification, warnings hoặc structured `AgentError` khi phù hợp.

Tên place chỉ chứa tên riêng của địa điểm/cơ sở. Khi raw prompt nói một hành
động hoặc món gắn với cơ sở có tên, hành động/món nằm trong `inputItems` và có
thể liên kết bằng `relatedPlaceName`; evidence từ source tương tự nằm trong
`urlNotes`. Explorer không resolve place.

Policy mặc định: `days=3` và chỉ raw prompt được ghi đè; `people=1 adult` và
chỉ raw prompt được ghi đè; budget ưu tiên raw prompt, whole-trip image,
whole-trip URL, rồi `low`. Giá vé/món riêng không phải whole-trip budget.
Draft generator có adapter deterministic và structured Gemini; provider được
chọn bằng `EXPLORER_DRAFT_PROVIDER`.

`SourceArtifact` là contract nội bộ giữa importer và bước synthesis, không phải
field public của `ExplorerOutput`. Artifact phân biệt `url_metadata`, `caption`,
`stt`, `frame_ocr`, `web_text` và `image_ocr`, đồng thời giữ URL/time hint. URL
cache canonicalize TikTok/Instagram/Facebook bằng cách bỏ toàn bộ query trước
khi tra `source_documents`, tương thích artifact cache legacy v6. URL và ảnh
trong cùng request được chạy song song. YouTube chỉ dùng metadata;
TikTok ưu tiên Safari HTML: parse JSON nhúng, kiểm tra CDN allowlist rồi stream
MP4 có giới hạn; nếu thất bại mới dùng `yt-dlp` legacy. Instagram dùng `yt-dlp`
theo thứ tự standard, Chrome và Chrome Android. ffprobe chỉ chạy OCR/STT cho
stream video/audio thực sự tồn tại; website dùng
HTTP, `curl-cffi` Safari, rồi fallback Playwright Chromium trước khi qua
trafilatura. Frame OCR bị
giới hạn 72 frame và 10 ảnh mỗi Gemini batch. `SourceExtractionResult` nội bộ
giữ lỗi riêng của nhánh `frame_ocr`/`stt`; source partial vẫn giữ artifact thành
công và đưa code nhánh lỗi vào `warnings`. Một source lỗi hoàn toàn cũng được
ghi trong `warnings`; batch vẫn đi tiếp nếu còn ít nhất một source dùng được.
Raw prompt tùy chọn trong source flow được parse song song với source synthesis;
các tín hiệu rõ từ prompt được merge theo precedence trước normalize.
Kết quả source nội bộ có `cacheStatus` (`hit`, `miss`, `bypassed`) để quan sát
luồng cache, nhưng field này không được gửi cho Gemini synthesis và không thuộc
`ExplorerOutput` public. Cache PostgreSQL dùng canonical URL, TTL và extractor
version; adapter tương thích đọc artifact version 6 của `old_one` và ghi version
7 theo `SourceArtifact` hiện tại. Draft synthesis được cache riêng theo prompt,
artifact evidence, model namespace và policy version; draft cache không thuộc
public output và bị bypass khi `forceRefresh=true`.

Đây là state machine LangGraph thực, không phải pipeline gọi tuần tự trong API:
`prepare_intake` dùng conditional edge chọn prompt-only hoặc source-import;
hai nhánh hội tụ trước normalize, ADM reconciliation, default policy và
completion gate. `graph.py` chỉ wiring, node chỉ chuyển state, còn validation,
coverage, retry/error, precedence và persistence policy thuộc `ExplorerService`.
Mọi URL/image/media provider được inject qua port; adapter không phụ thuộc
graph, node hoặc state nội bộ.

`PlaceCheckerInput` nhận trực tiếp `input_ADM`, `places`, `inputItems`,
`urlNotes`, `days`, `budget`, `people`, `shortPreferences` và `shortAvoids` từ
Explorer qua root orchestration. Chỉ output `ready` được chuyển tiếp.

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
| `GeminiLlmClient.generate` / `generate_media` | `shared/llm` | system/user prompt, tùy chọn tools hoặc inline image/audio | Text response; xoay vòng key từ `GEMINI_API_KEY` |
| `UrlSourceRouter` | `explorer` | URL YouTube/TikTok/Instagram/website | `SourceExtractionResult` chứa artifact có provenance |
| `PostgresUrlSourceCache` | `explorer` | canonical URL, TTL, extractor version | artifact URL chuẩn hóa từ `source_documents` |
| `GeminiMediaAnalyzer` | `explorer` | video/audio/ảnh | OCR frame và STT chunk chạy song song |
| `WebsiteSourceExtractor` | `explorer` | URL website public | HTTP, curl-cffi Safari, Playwright, rồi Markdown trafilatura |
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

## Knowledge Graph admin contract

Knowledge Graph is a separate admin module. It owns `knowledge_entities`,
`knowledge_aliases`, `knowledge_properties`, and `knowledge_relationships`,
with PostgreSQL access behind its adapter. Mutating requests require the admin
session and CSRF header. Ontology definitions mirror the versioned knowledge
schema; they do not imply that all catalog data is production-verified. Entity type and
status filter options are queried from `knowledge_entities` at runtime; property
keys and relationship types are queried from their graph tables. A
relationship edit can set both `fromEntityId` and `toEntityId`; the current
entity remains the admin context for the mutation. Updating an entity type in
the admin UI also sends the synchronized entity ID; the backend moves child
records and relationship endpoints transactionally when that ID changes.

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

- `InvokeRequest`: `thread_id`, `message` tùy chọn, `urls`, `images`,
  `existing_itinerary`, `edit_operation`.
- `InvokeResponse`: `request_id`, `route`, `response`, `itinerary`,
  `clarification_question`, `warnings`, `sources`.

## Durable trip-chat API

## Auto-attach Style rules

The admin Knowledge Graph exposes `/admin/knowledge-graph/auto-attach/rules` for the persisted `attach_auto.yml` rule catalog. Each rule maps normalized entity names or aliases to a `Style` candidate through `Has_Style`. Rules store entity types, keywords, exact names, exclusions, default timing, override count, status, and source. Writes require admin authentication and default to `pending` review status.

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
