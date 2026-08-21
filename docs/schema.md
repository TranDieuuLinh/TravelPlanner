# Schema module, agent và tool

Cập nhật lần cuối: 2026-08-21.

Backend dùng kiến trúc module hóa với LangGraph. Mỗi module expose public
contract qua `public.py`; state và node nội bộ không được module khác truy cập
trực tiếp.

Place Checker giữ provenance URL/direct input nhưng search identity thống nhất
trên cả năm entity type theo name/alias/address/ADM và lấy catalog top-1. Chỉ
catalog zero-result mới gọi Google Maps; Google draft được giữ `provisional`/
conditional với warning/constraint xác minh trước khi chốt lịch.
Retrieval/system provisional vẫn không planner-eligible.

Ontology có node place-like `Entertainment`, dùng cùng required/optional
properties với `TravelPlace` gồm tọa độ, địa chỉ, giờ mở cửa, style và các
quan hệ graph. Hint `entertainment` hoặc `wellness` chỉ truy vấn
`Entertainment`; hint `travel place` vẫn chỉ truy vấn `TravelPlace`.

Ontology admin có thêm node `SubPlace` để biểu diễn một khu/điểm con không trở
thành itinerary stop độc lập. `SubPlace` dùng cùng required/optional property
contract với `TravelPlace`, gồm tọa độ bắt buộc và toàn bộ metadata địa điểm.
Cạnh `Has_Subplace` chỉ cho phép `TravelPlace -> SubPlace`; `Offer_Item` từ
`SubPlace` chỉ trỏ tới `ActivityItem`, `FoodItem`, `DrinkItem` hoặc
`ProductItem`. Endpoint ontology trả thêm `relationshipEndpointRules` để
importer/admin biết ma trận endpoint. Endpoint read-only
`GET /v1/plans/places/subplaces?parentPlaceIds=` đọc trực tiếp
`Has_Subplace` sau khi itinerary đã có để frontend render; response này không
được ghi vào `PlanItem`, không qua optimizer và không tạo route. Batch curated v1 đã nạp năm
`SubPlace` `pending` cho Hanoi Old Quarter; mỗi node hiện có `latitude`,
`longitude` và `address` đại diện để frontend có thể đặt pin. Batch hiệu chỉnh
`kg_curated_hanoi_old_quarter_subplace_activities_v2_20260821` thay các item
trùng ý nghĩa bằng đúng một `ActivityItem` có provenance cho mỗi `SubPlace`;
batch v1 được đánh dấu `superseded_by_v2`. Dữ liệu chưa tự động tham gia output
runtime.

Batch `kg_curated_hoan_kiem_turtle_tower_subplace_v1_20260821` đã chuyển
`Turtle Tower` từ `TravelPlace` thành `SubPlace` của `Hoàn Kiếm Lake`, giữ tọa
độ hiện có và gắn một `ActivityItem` duy nhất.

`Offer_Item.recommendations` có thể giữ `action` và `displayTemplate` để LLM
sinh nhãn theo ngữ cảnh từ tên SubPlace và item chuẩn hóa; ví dụ `lụa` +
`buy` → “Mua lụa tại Phố Hàng Gai”.

Batch `kg_curated_top_hanoi_subplaces_v1_20260821` bổ sung 13 SubPlace có
tọa độ đại diện dưới Văn Miếu, Hoàng thành Thăng Long, Hỏa Lò, Trấn Quốc,
quần thể Hồ Chí Minh và Bảo tàng Dân tộc học; mỗi node có đúng một
`ActivityItem`.

Migration 019 chuyển 16 TravelPlace cấu thành đã review thành SubPlace, giữ
nguyên ID/property/alias/provenance, nối đúng một parent và bảo đảm có
`Offer_Item`. Hai synthetic duplicate được thay bằng entity provider-backed.
Migration 020 tiếp tục chuyển Lăng Chủ tịch Hồ Chí Minh thành SubPlace và gom
trực tiếp Lăng, Ao cá Bác Hồ, Nhà sàn Bác Hồ dưới TravelPlace Ba Đình Square;
không tạo tầng SubPlace lồng nhau. Migration 021 chỉ chuyển ba cặp gần nhau đã
có nguồn xác nhận quan hệ thành phần: Đại Trung Môn dưới Văn Miếu, Cổng làng
Mông Phụ dưới Làng cổ Đường Lâm và Chợ gốm dưới Làng gốm Bát Tràng. Các cặp
chỉ gần về tọa độ không bị chuyển. PlaceChecker/Planner không đọc
`Has_Subplace`; chỉ endpoint trình bày của frontend đọc child sau khi plan đã
được tạo.

## Ranh giới API

| Endpoint | Input | Output |
|---|---|---|
| `GET /health` | Không có | `{ "status": "ok" }` |
| `POST /v1/explorer/invoke` | `ExplorerInput` | `ExplorerApiOutput` rút gọn |
| `POST /v1/plans/current-location-route` | `CurrentLocationRouteRequest` | Một `TransportLeg` có geometry Valhalla/fallback |
| `POST /v1/plans/day-directions` | `DayDirectionsRequest` | Danh sách `TransportLeg` nối origin với các điểm theo thứ tự |
| `POST /v1/agent/invoke` | `InvokeRequest` | `InvokeResponse` |
| `POST /v1/trip-chats/{chatId}/messages` | `SendTripChatMessageInput`; khi chat có `currentPlannerOutput`, Gemini nhận compact plan context để trả structured edit intent | `TripChatMessageResponse`; edit hợp lệ dùng cùng optimistic-revision mutation với UI thủ công |
| `GET /v1/plans/places/search?query=&destination=&topK=` | `Authorization: Bearer <accessToken>`, query text and optional destination; `topK` defaults to `5` | Tối đa năm địa điểm chuẩn hóa; name/alias tham gia xếp hạng, catalog match trả thêm opening hours, duration và estimated cost khi có |
| `GET /v1/plans/places/subplaces?parentPlaceIds=` | `Authorization: Bearer <accessToken>`; lặp `parentPlaceIds` tối đa 50 TravelPlace | Nhóm SubPlace trực tiếp theo parent, tối đa 50 child/parent, dùng riêng cho UI; không thay đổi planner output hoặc route |
| `POST /v1/trip-chats/{chatId}/plan/unscheduled-places/confirm` | Multipart địa điểm gốc, match đã chọn, ngày đích và `expectedRevision` | `TripChat` sau khi thêm stop và xóa entry chưa xếp nguyên tử |
| `DELETE /v1/trip-chats/{chatId}/plan/unscheduled-places` | Multipart địa điểm gốc và `expectedRevision` | `TripChat` sau khi xóa entry chưa xếp |
| `POST /v1/trip-chats/{chatId}/plan/items` | Multipart item fields và `expectedRevision` | `TripChat` sau khi thêm địa điểm vào ngày đã chọn |
| `PATCH /v1/trip-chats/{chatId}/plan/days/{day}/items/{itemId}` | Multipart các trường địa điểm cần sửa và `expectedRevision` | `TripChat` sau khi cập nhật item; route leg chạm vào vị trí đã đổi được bỏ để frontend tính lại |
| `POST /v1/trip-chats/{chatId}/plan/days/{day}/items/{itemId}/replace` | `ReplacePlanItemInput` gồm identity, tọa độ, opening hours, duration, cost và `expectedRevision` | `TripChat` sau fixed-order reflow hoặc CP-SAT repair đúng ngày; snapshot chỉ được ghi khi route/timeline khả thi |
| `DELETE /v1/trip-chats/{chatId}/plan/days/{day}/items/{itemId}` | Multipart `expectedRevision` | `TripChat` sau khi xóa item và các route leg trực tiếp liên quan |
| `PUT /v1/trip-chats/{chatId}/plan/days/{day}/items/reorder` | Multipart `itemIds` (lặp lại) và `expectedRevision` | `TripChat` với thứ tự địa điểm đã cập nhật; các item không có trong payload vẫn được giữ lại |
| `PATCH /v1/trip-chats/{chatId}/plan/days/{day}/items/{itemId}/personal-notes` | `expectedRevision`, `personalNotes` | `TripChat` với planner snapshot đã cập nhật |
| `PATCH /v1/trip-chats/{chatId}/plan/accommodation` | `expectedRevision` và các trường nơi lưu trú cần sửa, gồm `personalNotes` | `TripChat` với accommodation và route reference đã cập nhật |
| `DELETE /v1/trip-chats/{chatId}/plan/accommodation` | `expectedRevision` | `TripChat` đã bỏ accommodation, transfer leg và phần chi phí lưu trú |
| `PUT /v1/trip-chats/{chatId}/plan/days/{day}/transport-legs/{legIndex}/selection` | `expectedRevision` và transport option đã chuẩn hóa | `TripChat` với `selectedTransport` đã lưu trên leg |
| `POST /auth/login` | `LoginInput` | `LoginResponse` (`accessToken`, `refreshToken`) |
| `POST /auth/register` | `RegisterInput` | `LoginResponse` (`accessToken`, `refreshToken`) |
| `POST /auth/refresh` | `RefreshInput` body | Rotated `LoginResponse` with a new access/refresh pair |
| `GET /me` | `Authorization: Bearer <accessToken>` | `AuthUser` |
| `GET /v1/trip-chats?limit=&offset=` | `Authorization: Bearer <accessToken>` | Danh sách `TripChatSummary` phân trang, mặc định 30 |
| `GET /v1/trip-chats/bootstrap?chatId=` | `Authorization: Bearer <accessToken>` | `TripChatBootstrap` gồm recent summaries và full active chat |
| `POST /auth/logout` | `RefreshInput` body | `204 No Content` and refresh-session revocation |
| `GET /admin/observability/status` | Admin session | Local observability counters and retention limit |
| `GET /admin/observability/traces` | Admin session + `page`, `limit` | Recent agent requests; each summary includes `observationCount` and `entryPoint` |
| `GET /admin/observability/observations` | Admin session + `page`, `limit`, optional `traceId` | Recent chain, LLM, tool and database spans with bounded redacted summaries; `traceId` isolates one request |
| `GET /admin/observability/sessions` | Admin session + `page`, `limit` | Requests grouped by graph thread |
| `GET /admin/observability/traces/{traceId}` | Admin session | One request with its captured steps |
| `GET /admin/knowledge-graph/stats` | Admin session | Knowledge Graph counts |
| `GET /admin/knowledge-graph/ontology` | Admin session | Node types, property keys, and relationship types from the backend ontology mirror; the intended source is `trung-plans/plans-for-new-version/knowledge/schema.yml` |
| `GET /admin/knowledge-graph/entities` | Admin session + filters | Paginated entities; `search`, `excludeNames`, and `missingProperties` support comma-separated keywords |
| `GET /admin/knowledge-graph/entities/filters` | Admin session | Distinct entity types/statuses from `knowledge_entities`, property keys from `knowledge_properties`, and relationship types from `knowledge_relationships` |
| `GET /admin/knowledge-graph/relationships` | Admin session + filters | Paginated relationships |
| `GET/PATCH/DELETE /admin/knowledge-graph/entities/{id}` | Admin session | Entity detail or mutation |

`POST /v1/agent/invoke` chỉ trả `200` cho output hoặc clarification hợp lệ.
Planner validation/preflight failure trả `422`; provider, matrix hoặc solver
`UNKNOWN` có thể retry trả `503` với `detail.code`, `detail.message` và
`detail.retryable`. Observability ghi các response này là failure thay vì
`success=true` với `plannerOutput=null`.

Chỉ Explorer result có review `ready_for_execution` mới đi qua
`ExplorerHandoffProjector`. Thiếu `inputADM` hoặc còn field mặc định sẽ quay về
Supervisor review, chưa gọi PlaceChecker. Projector chuẩn hóa tag và validate;
Explorer/provider failure trở thành `error` có cấu trúc. Các nguồn lỗi/timeout
được giữ trong `warnings`; `ExplorerOutput` không còn phát aggregate
`completeness`/coverage diagnostic. Place Checker
`food[].venueType` luôn là `restaurant`
ngay cả khi category thô từ provider là `travel_place` nhưng policy theo tên,
tag, pool và provider note đã phân loại candidate đó là nhà hàng.

## Các module

| Module | Input | Output |
|---|---|---|
| `supervisor` | `SupervisorInput`, gồm compact `currentPlan` khi Trip Chat đã có lịch | `SupervisorDecision` (`route`, `confidence`, `reason`, tùy chọn `response`, `clarificationQuestion`, `warnings`, `planEdit`, `tripContextPatch`, `sourceAction`) |
| `explorer` | `ExplorerInput` | `ExplorerOutput` |
| `information_finder` | `InformationFinderInput` | `InformationFinderOutput` (`answer`, structured `facts`/`contentBlocks`, `sources`, `warnings`, `suggestions`, `metadata`) |
| `place_checker` | `PlaceCheckerInput` | `PlaceCheckerOutput` |
| `itinerary_planner` | `ItineraryPlannerInput` | `ItineraryPlannerOutput` |
| `plan_editor` | Legacy `PlanEditorInput`; contract `NaturalLanguagePlanEdit` dùng chung cho lệnh chat | Legacy `PlanEditorOutput`; helper kiểm tra reference của `NaturalLanguagePlanEdit` |
| `conversation_memory` | `WorkingMemoryState` | `WorkingMemoryState`, `MemoryFact`, `MemoryReference`, `UserPreferenceMemory`, `RootStateMemoryMapping` |

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
├── information_finder -> END (final response của Finder)
├── plan_editor
└── explorer
    ├── thiếu destination -> supervisor review -> chờ user
    ├── có field mặc định -> supervisor review -> chờ TripContextPatch
    └── ready_for_execution -> place_checker -> itinerary_planner
```

Explorer không gọi PlaceChecker khi còn thiếu `inputADM` hoặc khi vừa áp dụng
`days`, `budget`, `people`, `shortPreferences` mặc định. Nó tạo
`ExplorerReview` dạng `missing_fields` hoặc `defaults_proposed`; Supervisor chỉ
dùng contract này để hỏi user. Reply tiếp theo được Supervisor chuyển thành
`TripContextPatch`, Explorer áp patch và chỉ đi PlaceChecker sau khi review đã
được chấp nhận hoặc sửa. Pending draft nằm trong root graph state theo
`threadId`, không phụ thuộc Conversation Memory.

## Observability contract

Mỗi lần gọi `POST /v1/agent/invoke`, gửi Trip Chat message hoặc gọi trực tiếp
`POST /v1/explorer/invoke` tạo một trace UUID riêng. `threadId` chỉ nhóm nhiều
trace thuộc cùng hội thoại; nó không phải trace identity. Mỗi observation có
`traceId` và `parentId` để admin UI dựng cây root graph, module, node và
provider/tool span.

Các capability không phải LangChain Runnable được bọc tại provider boundary.
Hiện local trace ghi span tóm tắt cho shared Gemini, Tavily, Information Finder
PostgreSQL cache, shared place search, Valhalla và OR-Tools CP-SAT. Input/output chỉ chứa số
lượng, trạng thái, model/provider và metadata an toàn; API key, raw provider
payload và toàn bộ prompt không được đưa vào span.

Ngoài snapshot trace, backend phát log `agent_stage_timing` khi mỗi root stage
kết thúc và `agent_request_timing` khi toàn request kết thúc. Log chỉ gồm
`request_id`, tên stage/route, status và `duration_ms`; không ghi prompt hoặc
provider payload. Có thể ghép các dòng theo `request_id` để tìm stage chậm ngay
trên terminal chạy Uvicorn.

Khi provider là `gemini`, Supervisor dùng đúng một structured LLM call cho mỗi
message. Nếu Trip Chat đã có lịch, input call này mang compact `currentPlan`;
output vừa chọn route vừa có thể trả `planEdit` (`add`, `update`, `delete`,
`reorder` hoặc `clarify`). Backend không dùng keyword/if-else để đoán lệnh sửa.
Reference ngày/item do model trả về phải khớp snapshot; provider lỗi không chạy
deterministic edit fallback. Structured `EditOperation` của API legacy vẫn được
hỗ trợ với `planEdit=null`.

Cùng structured call đó trả `tripContextPatch` khi đang chờ Explorer review và
`sourceAction` khi request có URL/ảnh. Slang, typo, budget level, destination và
ý định lập lịch/tóm tắt nguồn đều do model phân loại. Backend chỉ validate
schema, enum và invariant của patch/action; provider lỗi trả clarification an
toàn, không chạy keyword hoặc regex fallback để đoán intent.

Khi `planEdit` là mutation hợp lệ, Trip Chat gọi lại đúng primitive mà UI sửa
thủ công sử dụng. PostgreSQL khóa hàng theo optimistic revision, cập nhật
`currentPlannerOutput` và chèn cặp user/assistant trong cùng transaction; cả
lượt chỉ tăng revision một lần. `clarify` chỉ lưu câu hỏi làm rõ, không sửa
snapshot. Message không phải edit tiếp tục theo route Supervisor đã chọn mà
không phát sinh Gemini preflight thứ hai.

Input của root graph là `RootGraphInput`; output là `RootGraphOutput`.
Root state nội bộ có `conversation_context` gồm tối đa sáu message trước đó,
mỗi phần tử có tiền tố `User:` hoặc `Assistant:` để Supervisor xử lý follow-up.
Message hiện tại nằm riêng trong trường `message` và không bị lặp trong context.
API không nhận raw history riêng; Trip Chat dựng context từ transcript đã lưu.
Trong routing, ý định rõ ở `message` hiện tại có ưu tiên hơn context. Với câu nối
lược bỏ intent, Supervisor kế thừa tác vụ hỏi đáp hoặc lập kế hoạch từ các lượt
có role gần nhất; nếu không đủ căn cứ phân biệt thì route `finish` hỏi lại.

### Explorer

`ExplorerInput` nhận `rawPrompt` tùy chọn, `urls`, `images` và `forceRefresh`
tùy chọn. `forceRefresh=true` buộc URL extraction bỏ qua cache. Explorer output
không có `schemaVersion` và gồm:

Request có `urls` bắt buộc phải có `rawPrompt` không rỗng để thể hiện action.
Frontend chỉ điền một trong hai câu “Tạo lịch trình từ liên kết” hoặc “Tóm tắt
nội dung liên kết” vào composer; không tự gửi và user có thể sửa/viết thêm.
Action lập lịch chạy source extraction rồi qua destination/default review như
input thường. Action tóm tắt chạy extraction rồi trả nội dung qua Supervisor,
kết thúc trước PlaceChecker và Itinerary Planner.

- `intakeId`, `input_ADM`;
- `days`, `startDate`, `timezone`; nếu prompt không có ngày thì ngày bắt đầu là
  ngày mai, nếu không có duration thì `days=3`. Turn mới có URL/ảnh/địa điểm
  hoặc item mới cũng giữ default này; chỉ follow-up thuần tham chiếu lịch cũ
  mới kế thừa duration từ Conversation Memory;
- `places`, trong đó mỗi place public có `name` và `sourcePlaces` đã dedupe.
  `sourcePlaces` trả `evidenceType` cấp cao
  (`raw_prompt` hoặc `url`), `sourceUrl`, `sourceTimeHint`, `addressHint` và
  `urlNotes` liên quan; ảnh người dùng gửi trực tiếp thuộc nhóm `raw_prompt`.
  `tags`, confidence, origin, evidence, observed time, `platform`,
  extractor/model version và cache status không thuộc public output hoặc
  PlaceChecker input;
- `inputItems`, chỉ trả `name`, `itemType` và `relatedPlaceName` cho food, drink
  hoặc activity cụ thể được nêu rõ trong raw prompt; action, evidence và
  confidence vẫn là dữ liệu nội bộ; sở thích/chủ đề chung được đưa vào
  `shortPreferences`;
- `places[].sourcePlaces[].urlNotes` chỉ giữ `summary` cho chi tiết hữu ích từ
  URL/ảnh/OCR/STT/metadata. Note chỉ được xuất khi `placeName` khớp hoặc summary
  nhắc đúng tên place; top-level `urlNotes`, `placeName`, `evidenceType` và
  `sourceUrl` lặp lại trong nested note đã bị bỏ;
- `days`, `budget={amountPerPerson,currency,level}`, `people`,
  `shortPreferences`, `shortAvoids`, `specialNotes`; `ExplorerOutput` không có
  aggregate `completeness`; JSON public cũng không trả budget source,
  clarification, warnings hoặc structured `AgentError`. Với prompt provider Gemini, taxonomy mới nhất từ
  `tags-auto.yml` được đưa vào system prompt và JSON Schema enum; output được
  kiểm tra lại để hai danh sách chỉ chứa exact key trong file. Public boundary
  chỉ lọc key hợp lệ, không tự map lại semantic value. Public JSON cũng không
  trả `status`; trạng thái `ready`,
  `partial`, `clarification` hoặc `error` vẫn được `ExplorerService` và graph
  dùng nội bộ. Các field chẩn đoán vẫn được graph dùng nội bộ.

Tên place chỉ chứa tên riêng của địa điểm/cơ sở. Khi raw prompt nói một hành
động hoặc món gắn với cơ sở có tên, hành động/món nằm trong `inputItems`; liên
kết `relatedPlaceName` và evidence chỉ giữ nội bộ. Evidence từ source tương tự
nằm trong `sourcePlaces[].urlNotes`. Explorer không resolve place.

Policy mặc định: `days=3`, `people=2 adults`, budget level `low`, currency VND
và `specialNotes=[]`. Budget handoff luôn là tổng toàn chuyến cho một người;
group total do user nhập được chia đúng một lần. Khi user không nhập số tiền,
Explorer tính `amountPerPerson` bằng shared `DestinationDailyBudgetEstimator`
theo ADM/level/days/people trước khi tạo review và giữ `null` nếu chưa có
profile. Preference/avoid giữ toàn bộ dữ liệu user hợp lệ trước rồi bổ sung toàn
bộ `priority-tags` của các nhóm đang áp dụng từ `insight-user.yml`, theo thứ tự
ổn định, không random và không giới hạn bốn phần tử. Chỉ tag đồng thời được khai
báo trong `insight-user.yml` và là key của `tags-auto.yml` mới được giữ trong
output để chuyển tới Supervisor/downstream.
Giá vé/món riêng không phải whole-trip budget.

`ExplorerReview.tripContext` chỉ đưa cho Supervisor `inputADM`, `days`,
`budget={amountPerPerson,currency,level}`, `people` và `shortPreferences`, kèm
`defaultedFields`. Derived `shortAvoids` vẫn nằm trong pending Explorer output
để project sang PlaceChecker nhưng không được đưa vào review hoặc câu trả lời
mặc định của Supervisor.
Draft generator dùng structured Gemini cho cả prompt và source; hai provider
`EXPLORER_DRAFT_PROVIDER` và `EXPLORER_SOURCE_DRAFT_PROVIDER` chỉ nhận `gemini`.
Model trả cả `days`, `startDate`, `peopleExplicit` và `preferencesExplicit`.
Backend không dùng keyword/regex để suy đoán intent từ raw prompt; fallback an
toàn chỉ bảo toàn evidence đã có cấu trúc và báo lỗi retryable nếu prompt cần
LLM. `tags-auto.yml` được đọc lại ở mỗi lần tạo prompt draft và mỗi lần
normalize/output, nên thay đổi taxonomy có hiệu lực mà không restart backend;
draft lấy từ cache cũng được normalize bằng bản hiện tại.

`SourceArtifact` là contract nội bộ giữa importer và bước synthesis, không phải
field public của `ExplorerOutput`. Artifact phân biệt `url_metadata`, `caption`,
`transcript`, `stt`, `frame_ocr`, `web_text` và `image_ocr`, đồng thời giữ
URL/time hint. URL
cache canonicalize TikTok/Instagram/Facebook bằng cách bỏ toàn bộ query trước
khi tra `source_documents`, tương thích artifact cache legacy v6. URL và ảnh
trong cùng request được chạy song song. URL media đánh giá primary evidence từ
native transcript/caption, title, description, location và tags bằng structured
semantic preflight; model cũng trả `exhaustiveRequested`. Policy deterministic
chỉ kiểm tra các field có cấu trúc, confidence và ngưỡng coverage, không dò từ
khóa trong raw prompt. Primary chỉ đủ khi có destination hoặc named place và đủ
travel detail; lỗi preflight vẫn fallback tải media an toàn. YouTube ưu tiên
full subtitle/automatic caption mà không tải video;
metadata-only đủ coverage cũng không tải media. Nếu primary thiếu mới tải
audio-only để STT; transcript vẫn thiếu thì chạy riêng frame OCR, không STT lặp.
Audio được chia chunk có timestamp và mặc định chỉ transcribe một chunk Gemini
tại một thời điểm.
Transcript dài được extract place
theo từng chunk; mỗi chunk dùng một structured request trả đồng thời place, ADM
và note thay vì ba request provider riêng. Query `t=` hoặc
`start=` ưu tiên chunk gần timestamp nhưng không giới hạn phạm vi transcription;
text chunk mặc định 20.000 ký tự với tối đa 8.000 output token để tránh tạo quá
nhiều request khi transcript dài. Mặc định tối đa năm chunk được xử lý song
song và toàn bộ synthesis trong một Explorer service bị giới hạn sáu request
Gemini đang chạy; chunk thành công được giữ khi chỉ chunk khác cần retry.
TikTok ưu tiên Safari HTML: parse JSON nhúng và kiểm tra metadata trước; chỉ khi
primary coverage thiếu mới kiểm tra CDN allowlist rồi stream MP4 có giới hạn.
Lỗi source không fallback sang `yt-dlp`. Instagram cũng kiểm tra metadata
`yt-dlp` trước, rồi mới tải media theo thứ tự standard, Chrome và Chrome Android
nếu cần. ffprobe chỉ chạy OCR/STT cho
stream video/audio thực sự tồn tại; website dùng
HTTP, `curl-cffi` Safari, rồi fallback Playwright Chromium trước khi qua
trafilatura. Frame OCR lấy mẫu mỗi 3 giây, bị giới hạn 48 frame và 10 ảnh mỗi
Gemini batch; audio social chia động theo đoạn khoảng 60 giây, tối đa ba chunk.
OCR ảnh base64 được cache in-memory theo SHA-256 và `forceRefresh=true` buộc đọc
lại. `SourceExtractionResult` nội bộ
giữ lỗi riêng của nhánh `frame_ocr`/`stt`; source partial vẫn giữ artifact thành
công và đưa code nhánh lỗi vào `warnings`. Một source lỗi hoàn toàn cũng được
ghi trong `warnings`; batch vẫn đi tiếp nếu còn ít nhất một source dùng được.
Raw prompt tùy chọn trong source flow được parse song song với source synthesis;
các tín hiệu rõ từ prompt được merge theo precedence trước normalize.
Cache hit/miss/bypass được ghi log theo control flow, không được gắn vào source
result hoặc JSON handoff. Cache PostgreSQL vẫn dùng canonical URL, TTL và cột
extractor version để loại artifact không tương thích; adapter đọc artifact
version 6/8 và ghi version 9 theo `SourceArtifact` hiện tại, kèm
metadata coverage. Draft synthesis được cache riêng theo prompt,
artifact evidence, model namespace và policy version; draft cache không thuộc
public output và bị bypass khi `forceRefresh=true`.
Source result nội bộ còn giữ tín hiệu đủ/thiếu evidence để quyết định có cần
fallback tải media và có source nào dùng được. Tín hiệu này không được tổng hợp
thành coverage field trong `ExplorerOutput`. Chunk lỗi làm source `partial`
nhưng không xóa kết quả chunk thành công.

Đây là state machine LangGraph thực, không phải pipeline gọi tuần tự trong API:
`prepare_intake` dùng conditional edge chọn prompt-only hoặc source-import;
hai nhánh hội tụ trước normalize, ADM reconciliation, default policy và
completion gate. `graph.py` chỉ wiring, node chỉ chuyển state, còn validation,
source-success gate, retry/error, precedence và persistence policy thuộc
`ExplorerService`.
Mọi URL/image/media provider được inject qua port; adapter không phụ thuộc
graph, node hoặc state nội bộ.

`ExplorerHandoffProjector` vẫn là boundary duy nhất tạo `PlaceCheckerInput`,
nhưng chỉ được gọi sau Explorer review gate. Current
Explorer output được ưu tiên, Conversation Memory chỉ bổ sung context còn thiếu;
places được merge một lần, preferences/avoids được resolve bằng taxonomy hiện
tại trong `tags-auto.yml`, rồi toàn bộ `ExplorerOutput` và `PlaceCheckerInput`
được validate lại. Sau memory merge, Explorer final-dedupe theo tên đã chuẩn
hóa và gộp toàn bộ source evidence của các bản trùng. PlaceChecker nhận
`inputADM`, `places`, `inputItems`, `days`,
`budget`, `people`, `shortPreferences`, `shortAvoids` và `specialNotes`; không
nhận top-level `urlNotes` hoặc status `ready`/`partial` của Explorer.

Rich `PlaceCheckerResult` giữ evaluation, provenance và diagnostic. Sau đó
`PlaceCheckerPlannerOutputBuilder` tạo compact
`trip + places + food + entertainment + foodCoverage + accommodations + excludedCandidates`; root
validate payload này bằng `ItineraryPlannerInput` và giữ tại `planner_input`.
Retrieval/ranking dùng target `12 TravelPlace/ngày`, `6 Restaurant/ngày`,
`2 Entertainment/ngày`, `3 DrinkDessert/ngày` và tối đa 3 Accommodation/toàn
chuyến. Mỗi deficient pool có tối đa một Knowledge Graph query; runtime không
dùng external discovery để lấp pool.
Entertainment tự gợi ý phải đạt Bayesian rating điều chỉnh tối thiểu 4,2/5 và
qua tourist-suitability gate để loại cửa hàng/dịch vụ thương mại;
DrinkDessert phải có tín hiệu cafe/tea/bakery/dessert/bar/lounge và không được
là quán món chính gắn sai. Direct-user/URL được giữ. Entertainment optional phải
có window giao buổi tối từ 18:00; DrinkDessert dùng window ban ngày 07:00–18:00.
Hai quota được chọn riêng rồi gộp vào `entertainment[]` với `entityType`.
Food anchors là final TravelPlace và Entertainment có tọa độ. Một query food
trả cả nearby 5 km và city-wide candidates, hard-filter avoid, cân bằng FoodItem
và anchor, rồi kiểm tra `day × breakfast/lunch/dinner`. Target Restaurant là
`6 × days`; ba meal slot/ngày là coverage riêng, không phải target count.
Compact boundary chỉ đưa Restaurant vào `food`; DrinkDessert/Entertainment được
chuyển sang pool nullable `entertainment` và không chiếm meal slot hay quota Place.
PlaceChecker dựng slot cho từng
`day × breakfast/lunch/dinner` và chạy bipartite matching capacity một; vì vậy
đủ số lượng nhưng sai meal window vẫn không qua hard gate. Một matching thứ hai
dùng tập Restaurant rời nhau làm soft reserve, tối đa 60 candidate. Thiếu hard
matching làm PlaceChecker `blocked`; thiếu travel reserve không block và
candidate `user_input`/`url` không bị cắt trước khi Planner trả phần không xếp
được vào `unscheduled`;
thiếu relationship gần chỉ tạo warning và general food vẫn được phép. Một pool
Accommodation riêng chỉ nhận khách sạn đã xác minh có giá dương. Low/medium/high
chọn tối đa ba phương án quanh P25/P50/P80, sau đó xếp lại theo khoảng cách tới
tâm compact TravelPlace pool. Hybrid dùng candidate rẻ nhất làm accommodation
anchor khi có budget target, nếu không mới dùng candidate đầu tiên; các phương
án còn lại không kích hoạt global re-solve.
Compact Planner contract nhận food venue cùng `foodCoverage` meal feasibility;
HasStyle không tạo food diversity coverage.
Output planner giữ các entry thật sự không xếp được trong `unscheduled`. Với
URL/direct input có candidate hợp lệ nhưng identity nhập nhằng, Place Checker
tự chọn một canonical candidate tốt nhất trước khi tạo Planner input; frontend
không còn mở flow chọn Top-K để resolve identity.
Runtime pipeline không chạy Style candidate discovery. `Has_Style` chỉ enrich
time/duration còn thiếu trên entity/item.
Compact priority chỉ gồm `user_input`, `url`, `special_experience`,
`special_near`; food có `supportedMeals` và `venueType=restaurant`. Contract
vẫn nhận `drink_dessert` cho compatibility input cũ.
Địa điểm/quán được resolve từ `inputItems` mang priority `user_input`; quan hệ
Special Experience/Offer Item vẫn được giữ riêng trong source metadata và tags.
Mỗi place còn có `sourceKind` (`special_experience`, `offer_item`, `both` hoặc
`generic`), `offeredActivityIds` và `timeSource`. `Offer_Item` chỉ được tính là
nguồn activity khi target là `ActivityItem`; timing ActivityItem được truyền
qua relationship evidence, còn `Has_Style` chỉ kế thừa timing cụ thể còn thiếu
và không được giữ thành public tag. Travel reserve dùng một query canonical;
SpecialExperience, OfferItem và quality cùng tham gia core rank. Preference,
avoid và diversity chỉ dùng canonical key được resolve runtime từ
`auto-attach/tags-auto.yml`. Preference bằng số tag khớp chia tổng tag canonical
của candidate; avoid là hard filter. TravelPlace diversity lấy trung bình
`1 / (1 + số lần tag đã chọn)` rồi cộng với trọng số 5%, bên cạnh 10%
preference và 85% core. Quota giữ thứ tự rerank này và không làm PlaceChecker
phân ngày thay Planner. Popular bucket
chỉ tính candidate có ít nhất 500 review và popularity score từ 0,70. Semantic
category guard chuyển music box, karaoke, golf, billiard/bi-a, bowling, studio,
game center, massage/trị liệu, spa và retail store/souvenir bị gắn `TravelPlace`
sai sang `Entertainment` trước khi chia pool.
Candidate có `pool_category=shopping` cũng không được tính là landmark.
Generic discovery bỏ qua Knowledge Graph entity có property
`generic_discovery_excluded=true`, nhưng named-place lookup không áp dụng cờ này
để yêu cầu gọi đúng tên vẫn resolve được. Night market vẫn thuộc `TravelPlace`.
Generic top-K dùng Bayesian adjusted rating kết hợp review reliability theo prior
của scoped pool; các bước activity, food, entertainment và scoring downstream
tiếp tục dùng shared Bayesian policy. Vì vậy rating cao nhưng rất ít review không
còn đẩy landmark phổ biến ra khỏi cửa sổ retrieval trước khi scoring chạy.
Khi suy category từ tên, `Phở`/ASCII `Pho` được nhận diện trên Unicode gốc;
`Phố` không còn bị bỏ dấu thành `pho` rồi làm venue ở Phố Vọng thành Restaurant.
Named-place search dùng canonical name và alias đã chuẩn hóa không dấu. Batch
curation Hà Nội giữ alias hiển thị có dấu/ngôn ngữ, xóa chọn lọc alias mojibake
hoặc sai và thêm các tên gọi phổ biến như `36 phố phường`, `Hồ Gươm`, `Lăng
Bác`; entity pending trùng chính xác bị `rejected` thay vì xóa khỏi Knowledge
Graph.
Migration alias top 60 tiếp tục giữ boundary này: chỉ cập nhật alias theo đúng
identity hiện hữu, không tự đổi type/status hoặc dùng tên thay thế để che record
có địa chỉ, tọa độ hay provider identity sai.
Compact boundary dùng thêm provider note làm semantic context để chuyển source
category thương mại như art supply store, photo booth, garden center và plant
service khỏi TravelPlace; đây không thay đổi ontology lưu trữ.
Compact output giữ TravelPlace thiếu giá và mặc định `price.cost=0 VND`; food,
entertainment và accommodation vẫn phải có giá dùng được. User input bị loại vì
lý do khác được giữ trong `excludedCandidates` để Planner trả `unscheduled` cùng
reason. `price.cost` là trung bình
`price_min`/`price_max` khi có đủ khoảng, dùng giá trị duy nhất khi chỉ có một
đầu mút, bằng `0` cho tier `free`, hoặc bằng `0` khi TravelPlace thiếu giá.
Vì vậy `ItineraryPlannerInput.places[].price.cost` và
`ItineraryPlannerInput.food[].price.cost` là field bắt buộc, non-null và không âm.
Accommodation không phải activity stop và không cần duration; mỗi phương án có
tọa độ và `pricePerNight`.

Budget boundary ưu tiên số tiền người dùng nhập. Explorer chuẩn hóa
`group_total` thành `per_person`; PlaceChecker giữ nguyên amount này và đánh dấu
`source=explicit`. Khi không có amount, PlaceChecker tạo profile động từ các
candidate có giá đã query trong cây ADM. Low/medium/high lấy P25/P50/P80 riêng
cho Accommodation, Restaurant và TravelPlace; profile dùng ba bữa/ngày,
2/3/4 activities và 4/5/6 chặng Xanh SM 5 km. `dailyEstimate` bằng
`accommodation + food + localTransport + activities`; tổng chuyến tính ba nhóm
theo ngày nhưng accommodation theo `max(days - 1, 0)` đêm và gắn
`source=estimated_daily_cost`. TravelPlace thiếu giá đóng góp `0`; nếu thiếu giá
của pool food hoặc accommodation bắt buộc thì budget giữ `unspecified` thay vì
suy đoán bằng dữ liệu vùng khác.

`PlaceCheckerResult.foodRestaurantSelections` giữ mỗi Restaurant một lần sau
dedup, cùng mọi TravelPlace anchor liên quan. Adapter tính khoảng cách tối đa
5 km từ coordinates; `Special_Near` là provenance chứ không phải join gate.
SpecialExperience và OfferItem là hai evidence độc lập. Candidate phải có tọa
độ, duration, giá và meal window; nếu hard coverage vẫn thiếu thì adapter query
general ADM một lần, loại các Restaurant ID đã thấy và giới hạn theo deficit.
Fallback nhận đúng các meal type còn thiếu từ hard/reserve matching, sau đó
matching được chạy lại. `foodCoverage` gửi hard/reserve assignments và missing
slots sang Planner; thiếu reserve chỉ là trạng thái mềm, không tự block.
Bayesian prior/rating/review quality là capability dùng chung trong
`shared/tools/bayesian_rating.py`; PlaceChecker dùng nó trong pair score, còn
FinalItineraryPlanner dùng quality 0..1 cho objective `placeQualityValue`.

### FinalItineraryPlanner

Planner preprocess payload compact, lấy một global Valhalla driving matrix được
ghép đúng thứ tự từ các provider batch tối đa 2.500 source-target pairs,
giữ mười neighbor gần nhất theo safe travel time cho mỗi candidate rồi union
forced relationship, meal-access, priority và bridge arcs. CP-SAT mặc định dùng
một search worker trong từng pass do benchmark hiện tại chưa chứng minh
multi-worker giảm latency. Priority pass giữ exact search; activity-count pass
và mỗi utility attempt mặc định có 10 giây. Planner tạo geographic day-domain,
greedy shortlist và 2-opt/swap, rồi chạy OR-Tools CP-SAT ba pass cho từng
ngày. Greedy và CP-SAT dùng chung Bayesian review quality dựa trên rating,
review count và prior của pool. Hybrid cố định top accommodation trước khi solve
từng ngày; endpoint arc phải nối được anchor, về trước 03:00 và giữ tối thiểu 7
giờ nghỉ sau khi trừ hai transfer. Kết quả ghép ngày kiểm tra lại budget/rest/
transfer nhưng không gọi global CP-SAT để đổi khách sạn. Failure nêu top
`placeId`, ngày và nhóm constraint liên quan. Sau solver, module chỉ lấy
route detail cho selected arcs cùng accommodation transfers. Repair khóa ngày
không ảnh hưởng chỉ chạy sau khi timeline reflow không thể giữ nguyên
selection/order trong opening, meal, overnight và budget hard constraints.
Locked solve nhận baseline schedule làm solution hint; nếu `INFEASIBLE` hoặc
`UNKNOWN`, Planner hybrid-replan compact pool theo ngày để optional candidate có
thể được thay hoặc loại. Route detail được cache theo matrix-node pair trong
request. Nếu replan chọn arc mới dài hơn matrix, correction/repair tiếp tục khi
có correction mới đến lúc timeline ổn định; không có wall-clock timeout mặc
định cho chuỗi này. Route detail gây overlap luôn kích hoạt repair, kể cả lệch
1-2 phút; tolerance không nới lỏng hard timeline validity.
Entertainment bắt đầu trước 18:00 có target mềm 10% trên baseline bốn activity
ban ngày/ngày; phần vượt target bị trừ utility thay vì hard-fail để candidate
bắt buộc và
preflight vẫn khả thi. Mỗi ngày bắt buộc có activity xen giữa breakfast/lunch và lunch/dinner bằng
hard constraint cấm food-to-food arc. Planner bắt buộc ít nhất hai Place và
thưởng mọi Place khả thi không giới hạn bởi daily activity target;
Entertainment optional, tối đa một/ngày, được dịch meal trong policy window để
chèn activity. Waiting giữa hai stop liên tiếp bị giới hạn tối đa 90 phút ngoài
`safeTravel` đã gồm routing buffer; khi pool/opening
window không dựng được chuỗi liên tục, solver trả `INFEASIBLE` thay vì xuất
ngày chỉ có ba bữa ăn.
Trong số TravelPlace, candidate có ít nhất 500 review và Bayesian rating điều
chỉnh từ 4,2 được xem là popular. Shortlist cộng 6.000 điểm và objective đặt
target mềm hai popular TravelPlace/ngày, phạt 6.000 cho mỗi suất thiếu khả thi
để không dồn toàn bộ landmark vào một ngày chỉ nhằm giảm route ngắn hạn.
Planner còn cộng 4.000 utility cho mỗi TravelPlace thuộc Special Experience và
đặt target mềm hai điểm loại này/ngày, phạt 10.000 cho mỗi suất thiếu khả thi.
Candidate TravelPlace generic dưới 500 review và quán rating dưới 4,0/review
quá ít chịu cost chất lượng. Số stop và active minutes không chịu fatigue
penalty; phần lịch sau 23:00 vẫn chịu late penalty.
Trong hybrid solve, budget `estimated_daily_cost` có biên mềm 5%, được trừ tổng
lưu trú của accommodation anchor rồi chia phần còn lại theo số ngày. Overage
cost là 500 utility cho mỗi 10.000 VND; shortlist giữ tối đa sáu quán mỗi meal
slot để budget objective có đủ phương án rẻ, thay vì cho từng ngày dùng nhầm
toàn budget chuyến.
Hybrid shortlist tính thêm access cost hai chiều giữa accommodation anchor và
activity; budget thấp vì vậy ưu tiên cụm nội đô trước điểm xa tốn xe.
Với budget explicit/estimated, shortlist mở toàn bộ daily feasible reserve trước
khi rank thay vì chỉ dùng geographic preferred day.
Food reserve được rank theo tổng giá quán và corridor transport cost khi có
budget, trước travel-time/quality tie-break.
Nightlife và night-market bị clamp start từ 18:00; `Weekend Night Market` chỉ
khả thi vào Thứ Sáu-Chủ Nhật theo `trip.startDate`. Candidate place được đánh
dấu `drink_dessert` bị giới hạn tối đa hai điểm mỗi ngày.
Optional candidate của chuyến từ ba ngày được ưu tiên vào ngày gần nhất bằng
greedy và có thể thêm ngày gần thứ hai trong một lần rebalance. Tâm được chọn
theo normalized KNN density với tối đa 10 neighbor cùng Bayesian quality;
candidate cô lập không được chiếm một day center nếu neighborhood quanh nó quá
thưa. Ngày khả thi ngoài preferred pool
vẫn được giữ cho full-day fallback. User/URL không bị giới hạn và food liên kết
đi theo TravelPlace. Pass utility có relative gap 2%; pass priority khóa
user/URL và pass activity-count khóa số Place lớn nhất fit được trước utility.
Projected reserve được tính trên tổng Place + Entertainment. Preflight chỉ
hard-fail activity khi toàn bộ feasible pool của ngày có dưới hai Place; thiếu
Place trong preferred pool không chặn full-day fallback.
Sau day-domain projection, Planner ưu tiên khôi phục phép ghép ba bữa với ba
restaurant khác nhau từ pool gốc. Chỉ khi pool gốc không có unique matching,
Planner tạo meal-occurrence alias nội bộ để cùng venue có thể phục vụ nhiều bữa,
ánh xạ lại public `placeId`, tạo `itemId` theo meal và phát warning rõ ràng.
Planner vẫn dừng sớm nếu toàn bộ feasible pool thiếu hai Place separator,
thiếu hẳn meal window hoặc candidate-day mất opening window. Sau khi
dựng sparse arcs, gate thứ hai kiểm tra có route-connected component chứa tối
thiểu hai activity và ba meal occurrence khả thi.

Diversity Planner chỉ dùng nhóm tag cụ thể như spiritual, museum/history,
performance, photo/entertainment, shopping/nightlife và wellness. Tag ngữ cảnh
rộng vẫn dùng match preference nhưng không phạt lặp. Repetition cost chỉ áp khi
ngày đó còn một nhóm trải nghiệm khác khả thi; khi alternative cạn, tag cũ được
chọn lại không chịu penalty này.
Hybrid planner đồng thời giữ bộ đếm nhóm trải nghiệm đã chọn qua toàn chuyến:
ngày sau ưu tiên nhóm mới trong shortlist và chỉ quay lại nhóm cũ khi cần fill.

`ItineraryPlannerOutput` gồm `people`, accommodation đã chọn, số đêm,
ngày/stops/ordered route legs, cost và budget trên
một người, cùng `costBreakdown` mỗi ngày tách accommodation, food,
localTransport, activities và misc. Mỗi ordered route leg có `costPerPerson`
trên một người từ cùng fare estimator dùng cho `localTransport`.
Solver passes/objective metadata, priority `unscheduled`, optional
discard count, warnings, phase timings và `sourceMix` audit target/actual cho
morning 70/30 và evening 60/40. Quota source là soft penalty có fallback, còn
opening hours vẫn là hard constraint. `InvokeResponse.itinerary` vẫn là
contract legacy phục vụ PlanEditor; output mới được trả riêng qua
`plannerOutput` để biểu diễn overnight, geometry và solver metadata.
`people` được sao chép từ Planner input để Trip Chat lưu cùng snapshot; frontend
vì vậy vẫn hiển thị đúng quy mô nhóm sau khi tải lại chat.
Module ưu tiên factory hybrid CP-SAT trong runtime Valhalla và dùng Beam Search
làm fallback khi CP-SAT solver hoặc route enrichment/repair thất bại. Hai nhánh
dùng chung preprocessing và Valhalla matrix; fallback không query matrix lại.
Beam áp hard
rule không nối restaurant-to-restaurant,
kiểm tra distance Q3, rating tối thiểu 3.0, review count từ Q2/P50,
opening window và khoảng chờ tối đa 45 phút.
Khi dùng Beam, output có thêm `evaluation` gồm min/max/median adjusted Bayesian
rating, reviewCount, distanceMeters; counter tags/styles/items; và các count
restaurant, drinkDessert, entertainment, travelPlace cùng totalPrice.
Mỗi stop giữ rating gốc từ nguồn và thêm `bayesianRating`; solver dùng adjusted
Bayesian rating cho quality score, long-transition threshold và evaluation.
Trip Chat cho phép user sửa/xóa accommodation và lưu `personalNotes` trên
chính accommodation trong snapshot. Đổi `placeId` cập nhật các ordered route
leg tham chiếu nơi lưu trú; xóa nơi lưu trú đồng thời bỏ transfer leg và phần
chi phí accommodation khỏi tổng chi phí snapshot.
Budget `explicit` vẫn là hard cap; `estimated_daily_cost` là soft target và có
`budgetOverageCost`, nên plan khả thi có thể vượt estimate và phải phát warning.
Root chỉ công bố `plannerOutput` thành công khi output chứa đúng toàn bộ số ngày
được yêu cầu và mỗi ngày có ít nhất một stop. Output thiếu ngày hoặc ngày rỗng
được trả thành planning failure và không thay thế snapshot TripChat trước đó.

## Tool và provider adapter

Hiện chưa có standalone tool registry. Các tool/adapter đang có:

| Tool / adapter | Module | Input | Output |
|---|---|---|---|
| `TavilySearchProvider` | `information_finder` | query chuẩn hóa | kết quả tìm kiếm nội bộ có provenance |
| `LlmSearchQueryPlanner` | `information_finder` | câu hỏi và top 5 nguồn local có điểm semantic cao nhất | quyết định `shouldSearch` và tối đa 3 truy vấn Tavily; chỉ search khi nguồn local thiếu dữ kiện; lỗi thì fallback có điều kiện |
| `PostgresSourceRepository` | `information_finder` | query/vector hoặc prepared sources | nguồn cache hybrid |
| `GeminiUrlSourceChunker` | `information_finder` | URL public từ Tavily | semantic chunks có fallback deterministic |
| `GeminiEmbeddingProvider` | `information_finder` | retrieval query/document | vector Gemini chuẩn hóa 384 chiều |
| `ExtractiveAnswerGenerator` | `information_finder` | query và nguồn | tối đa ba excerpt ngắn đã lọc nhiễu phổ biến, có citation; không giả lập tổng hợp LLM |
| `StructuredLlmAnswerGenerator` | `information_finder` | query và ranked sources | `GeneratedAnswer` tiếng Việt gồm grounded claim, format Markdown linh hoạt, source ID và `entityCandidates` |
| `KnowledgeGraphEntityResolver` | `information_finder` | `entityCandidates` gồm tên hiển thị và aliases | thử từng tên để xác nhận node rồi mới gắn `travel-entity://entity` |
| `DevelopmentCatalog.resolve` | `place_checker` | `PlaceCandidate`, `TripIntent` | `VerifiedPlace \| None` |
| `DevelopmentCatalog.discover` | `place_checker` | `TripIntent`, `limit: int` | `list[VerifiedPlace]` |
| `ValhallaAdapter.matrix` | `itinerary_planner` | Candidate coordinates + profile | Global asymmetric driving matrix; fallback Haversine khi provider unavailable |
| `ValhallaAdapter.route` | `itinerary_planner` | Selected route legs | Duration, distance và encoded polyline; fallback polyline điểm đầu/cuối khi provider unavailable |
| `XanhSmTransportCostEstimator` | `shared/tools` (dùng bởi `itinerary_planner`) | Distance/profile/people | Giá di chuyển, phụ phí đêm và fare metadata trên một người |
| `DailyCostCalculator` | `shared/tools` (dùng bởi `itinerary_planner`) | Accommodation/food/local transport/activities/misc | Breakdown và tổng chi phí/người/ngày trong một currency |
| `GeminiLlmClient.generate` / `generate_media` | `shared/llm` | system/user prompt, tùy chọn tools hoặc inline image/audio | Text response; dùng key pool chung, tối đa một request đang chạy trên mỗi key |
| `UrlSourceRouter` | `explorer` | URL YouTube/TikTok/Instagram/website | `SourceExtractionResult` chứa artifact có provenance |
| `PostgresUrlSourceCache` | `explorer` | canonical URL, TTL, extractor version | artifact URL chuẩn hóa từ `source_documents` |
| `GeminiPrimaryEvidenceEvaluator` | `explorer` | transcript/caption/metadata đã chuẩn hóa | semantic facts; policy local quyết định đủ coverage hay fallback media |
| `GeminiMediaAnalyzer` | `explorer` | video/audio/ảnh và nhánh tùy chọn | OCR frame, STT chunk hoặc chỉ OCR cho YouTube đã có transcript |
| `WebsiteSourceExtractor` | `explorer` | URL website public | HTTP, curl-cffi Safari, Playwright, rồi Markdown trafilatura |
| `SearchPlacesTool.search` | `shared/tools/search_places` | `PlaceSearchRequest` | `PlaceSearchResult` có status, selected, top matches, provider attempts và resolution reason |
| `GoogleMapsPlaywrightSearch.search` | `shared/tools/search_places` | Query, canonical ADM, type hint và limit | Candidate Google Maps chuẩn hóa, lưu `pending` với provenance trước khi trả |
| Bayesian rating tool | `shared/tools/bayesian_rating.py` | rating, review count và candidate observations | prior, adjusted rating, reliability và quality chuẩn hóa |

`SearchPlacesTool` hỗ trợ hai mode: `named_place` để xác minh identity được nêu
tên và `requirement` để tìm venue phù hợp với món ăn, đồ uống hoặc hoạt động.
PlaceChecker named place dùng unified catalog SQL theo name/alias/address/ADM
trên năm entity type và yêu cầu `topK=1`. Có catalog row thì chọn row đó trước;
chỉ zero-result mới gọi external khi adapter được cấu hình. Catalog error hoặc
row conflict không được diễn giải thành zero-result. Caller khác dùng top-K lớn
hơn vẫn theo policy score/margin chung của shared tool.

Contract dùng chung của tool gồm `AdministrativeArea`, `PlaceSearchRequest`,
`PlaceProviderCandidate`, `PlaceSearchMatch`, `ProviderAttempt` và
`PlaceSearchResult`. Result phân biệt `resolved`, `needs_review`, `unresolved`
và `provider_error`; lỗi provider retryable không bị diễn giải thành no-match.

`PlaceSearchRequest.providerScope` cho phép retrieval gọi riêng Knowledge Graph
hoặc external provider. Candidate/match có `verificationStatus`; chỉ entity
Google Maps mang note `verification=not_verified` mới bị chiếu thành
`not_verified`, thay vì coi toàn bộ dữ liệu legacy có `status=draft` là chưa
đáng tin. Google provider không tự tạo `Special_Experience`, `Offer_Item` hoặc
`Has_Style`; nó chỉ tạo `Located_In` pending tới ADM đã resolve. Package vẫn có
`InMemoryPlaceSearch` cho test/development; runtime có database dùng PostgreSQL
KG cùng Playwright external recovery cho named-place zero-result.

Các provider interface bên ngoài hiện có:

- `SearchProvider`
- `SearchQueryPlanner`
- `SourceRepository`
- `EmbeddingProvider`
- `AnswerGenerator`
- `PlaceResolver`
- `PlaceDiscovery`
- `SourceNoteTranslator`
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
entity remains the admin context for the mutation. Updating an entity type in
the admin UI also sends the synchronized entity ID; the backend moves child
records and relationship endpoints transactionally when that ID changes.

Chat có public read-only endpoint `GET
/v1/knowledge-graph/entities/{entity_id}/preview` để lấy `EntityPreview` chính
xác theo ID của entity link. Endpoint tương thích
`GET /v1/knowledge-graph/entity-preview?name=...` vẫn được giữ cho caller cũ;
UI chat không dùng lookup theo tên cho link mới.

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

- `InvokeRequest`: `thread_id`, `message`, `urls`, `images`, `force_refresh`,
  `existing_itinerary`, `edit_operation`.
- `InvokeResponse`: `request_id`, `route`, `response`, legacy `itinerary`,
  `planner_output`, `clarification_question`, `warnings`, `sources`.

## Durable trip-chat API

Mỗi `currentPlannerOutput.days[].stops[]` có `itemId` ổn định, source-owned
`notes={text,sourceType,sourceUrl}` và user-owned `personalNotes`. Place Checker
đưa note đã liên kết từ raw prompt vào `personalNotes`. `notes` không chứa raw
prompt: module chọn URL note trước, nếu không có mới dùng mô tả Google
Maps/Knowledge Graph. Google Maps/Knowledge Graph note đã chọn được Việt hóa
trong Place Checker trước compact handoff; `sourceType` và `sourceUrl` không đổi.
Nếu provider dịch lỗi hoặc output không đạt guard tiếng Việt, field note nguồn
đó bị bỏ thay vì trả nội dung tiếng Anh. Frontend áp cùng nguyên tắc ẩn source
note chưa Việt hóa; `personalNotes` không đi qua bước dịch này.
Endpoint personal-notes chỉ cập nhật `personalNotes` với revision check, không
được sửa source note.

Sau khi FinalItineraryPlanner tạo output đủ ngày, route giữ response
deterministic do module tạo trong `InvokeResponse.response`. Node `finish` chỉ
ánh xạ response có sẵn và không gọi Gemini hoặc đọc raw prompt/provider payload.
JSON plan vẫn giữ nguyên structured note để frontend hiển thị tại card, map
popup và màn sửa note; response text không thay thế dữ liệu note trong plan.
Transport selection endpoint cập nhật nguyên tử `selectedTransport` trên đúng
leg và tăng revision. UI áp policy hậu xử lý: khoảng cách dưới 1,5 km chỉ hiện
đi bộ; các option khác chỉ hiện khi chặng không thuộc ngưỡng này và provider
data đạt điều kiện availability.

## Auto-attach Style rules

The admin Knowledge Graph exposes `/admin/knowledge-graph/auto-attach/rules` for the persisted `attach_auto.yml` rule catalog. Each rule maps normalized entity names or aliases to a `Style` candidate through `Has_Style`. Default `time_duration` and `time_windows` are read from the target Style node; direct place timing overrides those defaults. Relationship properties remain a compatible per-attachment override. Rules store entity types, keywords, exact names, exclusions, default timing, override count, status, and source. Writes require admin authentication and default to `pending` review status.

Relationship contract accepts `recommendations` as either an object or an
array of evidence objects, matching the runtime Knowledge Graph. PlaceChecker
chỉ đọc quan hệ khoảng cách `Special_Near`; `Near` legacy và `Must_Visit` không
còn tham gia retrieval, evidence hoặc planning projection.

The current frontend planner uses the authenticated `/v1/trip-chats` contract.
Bootstrap tải một lần tối đa 30 summary và full chat được chọn; query summary
chỉ chiếu boolean `hasItinerary`, không đọc hai JSON plan snapshot. Chi tiết
message và plan chỉ được đọc cho active chat.
Each chat owns a LangGraph thread identifier and persists user/assistant
messages plus two independent snapshots in PostgreSQL: `currentItinerary` for
the PlanEditor legacy contract and `currentPlannerOutput` for the new planner
contract. A response without a new snapshot preserves the previous value.
Frontend mapping prefers `currentPlannerOutput.days[].stops/legs` and falls back
to legacy `currentItinerary.days[].items` only for old chats. Guest planning
calls `/v1/agent/invoke` directly and uses the same new-output mapper. Mỗi stop
có `imageUrls`; Place Checker chuẩn hóa giá trị từ các property `image`,
`imageUrl`, `image_url`, `images` hoặc `imageUrls` của Knowledge Graph trước khi
truyền qua planner.

`SourceReference` expose `sourceId`, `title`, `url`, `updatedAt`, `dateKind`,
`reviewStatus` và `publishedAt` tùy chọn. `dateKind` phân biệt ngày website tự
công bố cập nhật với ngày hệ thống lấy nguồn. Nguồn Tavily mới mặc định có
`reviewStatus=pending`; chưa có admin review UI.

Internal `GeneratedAnswer` gồm danh sách `AnswerClaim(text, source_ids)` và
`caveat` tùy chọn. JSON schema gửi cho LLM dùng camelCase (`sourceIds`,
`entityNames`, `entityCandidates`); Pydantic ánh xạ về tên Python tương ứng.
Backend từ chối source ID ngoài context, deduplicate ID theo thứ tự, render
marker `[1]` và chỉ ánh xạ metadata cho nguồn thực sự được cite. Structured
answer public dùng `contentBlocks` với discriminated union cho paragraph,
factList, verse, quote, recommendations, steps, comparison và notice. Entity
interaction trong block dùng `inlineSpans`; chỉ span có `entityId` do backend
resolve mới được frontend render thành Knowledge Graph preview.
`InformationFinderOutput.metadata` công bố `generationMode`,
`validationStatus`, `confidence`, `fallbackUsed`, `claimCount` và
`citedSourceCount`. Các giá trị được suy ra deterministic sau citation
validation; không chứa prompt hoặc raw provider payload. Root route trả trực
tiếp `answer`, blocks, sources và warnings của Finder, không gọi response
composer tại `finish`.

Information Finder đã có repository nguồn riêng. Module `conversation_memory` dùng `MemoryRepository` port, PostgreSQL asyncpg adapter, migration `009_conversation_memory.sql`, optimistic concurrency control và atomic `save_memory_and_facts`. Fact extraction giữ rule deterministic; reference resolution mặc định dùng hybrid Gemini với transcript/memory có cấu trúc và `RuleBasedReferenceResolver` fallback. Target do LLM trả về chỉ hợp lệ khi trùng active fact ID, vì vậy provider không thể tự tạo địa điểm. Fact insert idempotent theo `fact_id` giúp retry cùng message không làm hỏng lượt chat. `MergePolicyEvaluator` bảo vệ confirmed facts và giữ lịch sử superseded.
