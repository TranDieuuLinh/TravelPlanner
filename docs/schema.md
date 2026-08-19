# Schema module, agent và tool

Cập nhật lần cuối: 2026-08-18.

Backend dùng kiến trúc module hóa với LangGraph. Mỗi module expose public
contract qua `public.py`; state và node nội bộ không được module khác truy cập
trực tiếp.

Place Checker phân biệt identity `provisional` có nguồn URL/direct input với
retrieval provisional. Loại đầu được tự chọn từ candidate tốt nhất khi có
canonical ID, tọa độ và đúng ADM; `addressHint` được ưu tiên khi có, còn không
thì dùng ranking đầu tiên. Output là `conditional`, có warning/constraint xác
minh trước khi chốt lịch.
Retrieval/system provisional vẫn không planner-eligible.

Ontology có node place-like `Entertainment`, dùng cùng required/optional
properties với `TravelPlace` gồm tọa độ, địa chỉ, giờ mở cửa, style và các
quan hệ graph. Hint `entertainment` hoặc `wellness` chỉ truy vấn
`Entertainment`; hint `travel place` vẫn chỉ truy vấn `TravelPlace`.

## Ranh giới API

| Endpoint | Input | Output |
|---|---|---|
| `GET /health` | Không có | `{ "status": "ok" }` |
| `POST /v1/plans/current-location-route` | `CurrentLocationRouteRequest` | Một `TransportLeg` có geometry Valhalla/fallback |
| `POST /v1/plans/day-directions` | `DayDirectionsRequest` | Danh sách `TransportLeg` nối origin với các điểm theo thứ tự |
| `POST /v1/agent/invoke` | `InvokeRequest` | `InvokeResponse` |
| `GET /v1/plans/places/search?query=&destination=&topK=` | `Authorization: Bearer <accessToken>`, query text and optional destination | Danh sách địa điểm chuẩn hóa để thêm thủ công vào lịch trình |
| `POST /v1/trip-chats/{chatId}/plan/unscheduled-places/confirm` | Multipart địa điểm gốc, match đã chọn, ngày đích và `expectedRevision` | `TripChat` sau khi thêm stop và xóa entry chưa xếp nguyên tử |
| `DELETE /v1/trip-chats/{chatId}/plan/unscheduled-places` | Multipart địa điểm gốc và `expectedRevision` | `TripChat` sau khi xóa entry chưa xếp |
| `POST /v1/trip-chats/{chatId}/plan/items` | Multipart item fields và `expectedRevision` | `TripChat` sau khi thêm địa điểm vào ngày đã chọn |
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

Explorer output `partial` vẫn được phép đi tiếp sang Place Checker khi có
`input_ADM`; các nguồn lỗi/timeout được giữ trong `warnings` và
`completeness.sources`. Place Checker `food[].venueType` luôn là `restaurant`
ngay cả khi category thô từ provider là `travel_place` nhưng policy theo tên,
tag, pool và provider note đã phân loại candidate đó là nhà hàng.

## Các module

| Module | Input | Output |
|---|---|---|
| `supervisor` | `SupervisorInput` | `SupervisorDecision` (`route`, `confidence`, `reason`, tùy chọn `response`, `clarificationQuestion`, `warnings`) |
| `explorer` | `ExplorerInput` | `ExplorerOutput` |
| `information_finder` | `InformationFinderInput` | `InformationFinderOutput` (`answer`, `sources`, `warnings`) |
| `place_checker` | `PlaceCheckerInput` | `PlaceCheckerOutput` |
| `itinerary_planner` | `ItineraryPlannerInput` | `ItineraryPlannerOutput` |
| `plan_editor` | `PlanEditorInput` | `PlanEditorOutput` |
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
├── information_finder
├── plan_editor
└── explorer -> place_checker -> itinerary_planner
```

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

Khi provider là `gemini`, Supervisor dùng structured LLM classification trước
cho mọi message; deterministic rules chỉ được dùng khi chọn provider `rules`
hoặc làm runtime fallback. Route `plan_editor` chỉ hợp lệ khi request có cả
itinerary hiện tại và structured edit operation. Route `finish` có thể mang
response ngắn cùng ngôn ngữ cho greeting, câu hỏi về trợ lý hoặc yêu cầu ngoài
phạm vi.

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

- `status`: `ready`, `clarification` hoặc `error`;
- `intakeId`, `input_ADM`;
- `days`, `startDate`, `timezone`; nếu prompt không có ngày thì ngày bắt đầu là
  ngày mai, nếu không có duration thì `days=3`. Turn mới có URL/ảnh/địa điểm
  hoặc item mới cũng giữ default này; chỉ follow-up thuần tham chiếu lịch cũ
  mới kế thừa duration từ Conversation Memory;
- `places`, trong đó mỗi place có `sourcePlaces`, `sourceTimeHint` và
  `addressHint`; `sourcePlaces` phân biệt nguồn `input` (người dùng chọn trực tiếp),
  `url` (nguồn URL do người dùng cung cấp) và `system` (gợi ý từ assistant/information-finder
  hoặc transcript cũ, mang tính tùy chọn, không bắt buộc; chỉ khi lượt người dùng hiện tại
  tham chiếu rõ ràng qua current-turn explicit reference promotion mới được chuyển sang `input`);
  mỗi source có thể mang `platform`, `extractorVersion`, `modelVersion`, `cacheStatus` và
  các field provenance này được Place Checker giữ nguyên; không có `sourceOrder`/`sourceDay`;
- `inputItems`, chỉ lấy food, drink hoặc activity cụ thể, có thể resolve được và
  được nêu rõ trong raw prompt; sở thích/chủ đề chung được đưa vào
  `shortPreferences`;
- `urlNotes`, giữ chi tiết hữu ích có evidence từ URL/ảnh/OCR/STT/metadata,
  gồm access/timing/price/caution, hoạt động cụ thể tại địa điểm, trải nghiệm
  đặc trưng và fun fact; loại lời quảng cáo chung chung;
- `days`, `budget`, `people`, `shortPreferences`, `shortAvoids`;
- clarification, warnings hoặc structured `AgentError` khi phù hợp.

Tên place chỉ chứa tên riêng của địa điểm/cơ sở. Khi raw prompt nói một hành
động hoặc món gắn với cơ sở có tên, hành động/món nằm trong `inputItems` và có
thể liên kết bằng `relatedPlaceName`; evidence từ source tương tự nằm trong
`urlNotes`. Explorer không resolve place.

Policy mặc định: `days=3` và chỉ raw prompt được ghi đè; `people=2 adults` và
chỉ raw prompt được ghi đè; budget ưu tiên raw prompt, whole-trip image,
whole-trip URL, rồi `low`. Giá vé/món riêng không phải whole-trip budget.
Draft generator có adapter deterministic và structured Gemini; prompt provider
được chọn bằng `EXPLORER_DRAFT_PROVIDER`, source provider bằng
`EXPLORER_SOURCE_DRAFT_PROVIDER`.

`SourceArtifact` là contract nội bộ giữa importer và bước synthesis, không phải
field public của `ExplorerOutput`. Artifact phân biệt `url_metadata`, `caption`,
`stt`, `frame_ocr`, `web_text` và `image_ocr`, đồng thời giữ URL/time hint. URL
cache canonicalize TikTok/Instagram/Facebook bằng cách bỏ toàn bộ query trước
khi tra `source_documents`, tương thích artifact cache legacy v6. URL và ảnh
trong cùng request được chạy song song. YouTube ưu tiên full subtitle/automatic
caption mà không tải video; nếu không có caption mới tải audio-only, chia chunk
có timestamp và mặc định chỉ transcribe một chunk Gemini tại một thời điểm.
Transcript dài được extract place
theo từng chunk; mỗi chunk dùng một structured request trả đồng thời place, ADM
và note thay vì ba request provider riêng. Query `t=` hoặc
`start=` ưu tiên chunk gần timestamp nhưng không giới hạn phạm vi transcription;
text chunk mặc định 20.000 ký tự với tối đa 8.000 output token để tránh tạo quá
nhiều request khi transcript dài. Mặc định tối đa năm chunk được xử lý song
song và toàn bộ synthesis trong một Explorer service bị giới hạn sáu request
Gemini đang chạy; chunk thành công được giữ khi chỉ chunk khác cần retry.
TikTok ưu tiên Safari HTML: parse JSON nhúng, kiểm tra CDN allowlist rồi stream
MP4 có giới hạn; lỗi source không fallback sang `yt-dlp`. Instagram dùng `yt-dlp`
theo thứ tự standard, Chrome và Chrome Android. ffprobe chỉ chạy OCR/STT cho
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
Kết quả source nội bộ có `cacheStatus` (`hit`, `miss`, `bypassed`) để quan sát
luồng cache, nhưng field này không được gửi cho Gemini synthesis và không thuộc
`ExplorerOutput` public. Cache PostgreSQL dùng canonical URL, TTL và extractor
version; adapter tương thích đọc artifact version 6 của `old_one` và ghi version
8 theo `SourceArtifact` hiện tại, kèm metadata coverage. Draft synthesis được cache riêng theo prompt,
artifact evidence, model namespace và policy version; draft cache không thuộc
public output và bị bypass khi `forceRefresh=true`.
Source result còn theo dõi duration/coverage transcript, tổng số synthesis
chunk, số chunk thành công và synthesis coverage. Chunk lỗi làm source
`partial` nhưng không xóa kết quả chunk thành công.

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

Rich `PlaceCheckerResult` giữ evaluation, provenance và diagnostic. Sau đó
`PlaceCheckerPlannerOutputBuilder` tạo compact
`trip + places + food + entertainment + foodCoverage + accommodations + excludedCandidates`; root
validate payload này bằng `ItineraryPlannerInput` và giữ tại `planner_input`.
Retrieval/ranking dùng target `22 TravelPlace/ngày`, `16 Restaurant/ngày` và
`6 DrinkDessert/Entertainment/ngày`. Core TravelPlace retrieval có query riêng
cho famous/must-see, historic landmark/museum/temple/old quarter và authentic
local cultural special experience.
Entertainment tự gợi ý phải đạt Bayesian rating điều chỉnh tối thiểu 4,2/5 và
qua tourist-suitability gate để loại cửa hàng/dịch vụ thương mại;
DrinkDessert phải có tín hiệu cafe/tea/bakery/dessert/bar/lounge và không được
là quán món chính gắn sai. Direct-user/URL được giữ. Compact selector
chỉ dùng `8 TravelPlace/ngày` làm hard handoff minimum; phần thiếu so với target
22/ngày là reserve shortfall, không tự chặn Planner. Selector chỉ giới hạn
Entertainment chỉ mở buổi sáng ở tối đa một candidate/ngày; candidate có thể
xếp chiều/tối vẫn nằm trong quota toàn ngày và làm fallback cho Planner. Ba
Style breakfast/lunch/dinner active
mặc định; Style food/drink khác chỉ active khi request resolve tới Style đó.
Mỗi Style active có target mềm `2 × days`; PlaceChecker chọn Item trước, reverse
`Offer_Item` sang Restaurant/DrinkDessert và cân bằng
Item/quán theo anchor region. Food hard minimum vẫn là `days * 3` venue duy nhất.
Nếu pool từ URL/direct input hoặc special-near food chưa đủ, PlaceChecker vẫn
chạy targeted retrieval theo cùng cơ chế gap/pool của special experience để bù
độc lập các nhóm `TravelPlace`, `Restaurant` và `Entertainment` trước khi qua
Planner; food coverage không bị tắt chỉ vì food-selection adapter đã được bật.
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
Rich PlaceChecker result trả `foodStyleCoverage[]` gồm Style ID/tên, target,
số quán đã chọn, số Item phân biệt và trạng thái complete. Compact Planner
contract vẫn nhận food venue cùng `foodCoverage` meal feasibility.
Output planner giữ các entry thật sự không xếp được trong `unscheduled`. Với
URL/direct input có candidate hợp lệ nhưng identity nhập nhằng, Place Checker
tự chọn một canonical candidate tốt nhất trước khi tạo Planner input; frontend
không còn mở flow chọn Top-K để resolve identity.
Rich result còn trả `styleCandidateSelections[]` với place/entity type,
Style/Item ID và tên, `relationshipSource`, cùng
`styleCandidateCoverage[]` và các input Style/Item không resolve được. Selector
tổng quát chỉ kích hoạt Style resolve từ `shortPreferences` hoặc `inputItems`,
dedup toàn pool theo place ID và không ghi bộ đếm diversity xuống database.
Compact priority chỉ gồm `user_input`, `url`, `special_experience`,
`special_near`; food có `supportedMeals` và `venueType=restaurant`. Contract
vẫn nhận `drink_dessert` cho compatibility input cũ.
Địa điểm/quán được resolve từ `inputItems` mang priority `user_input`; quan hệ
Special Experience/Offer Item vẫn được giữ riêng trong source metadata và tags.
Mỗi place còn có `sourceKind` (`special_experience`, `offer_item`, `both` hoặc
`generic`), `offeredActivityIds` và `timeSource`. `Offer_Item` chỉ được tính là
nguồn activity khi target là `ActivityItem`; timing ActivityItem được truyền
qua relationship evidence, còn `Has_Style` là fallback khi thiếu timing cụ thể
và được giữ thành tag `style:*` cho diversity coverage. Travel reserve chạy
thematic query cho culture, nature, shopping, nightlife, workshop, performance,
outdoor, family và local activity, giữ một candidate mỗi theme/style khả dụng
trước khi bù theo 8/14 Special Experience có evidence/provenance đã duyệt và
4/14 popular;
popular kết hợp Bayesian quality với log review count, bucket thiếu được ranking
diversity bù và không làm PlaceChecker phân ngày thay Planner. Popular bucket
chỉ tính candidate có ít nhất 500 review và popularity score từ 0,70. Semantic
category guard chuyển music box, karaoke, golf, billiard/bi-a, bowling, studio,
game center, massage/trị liệu, spa và retail store/souvenir bị gắn `TravelPlace`
sai sang `Entertainment` trước khi chia pool.
Candidate có `pool_category=shopping` cũng không được tính là landmark.
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
multi-worker giảm latency. Default không đặt solver timeout; runtime cần SLA
phải inject giới hạn riêng qua `SolverConfig`. Planner tạo geographic day-domain,
greedy shortlist và 2-opt/swap, rồi chạy OR-Tools CP-SAT hai pass cho từng
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
thưởng đến ba Place/ngày; Entertainment optional, tối đa một/ngày,
được dịch meal trong policy window để chèn activity; nếu shortlist chưa đạt ba
activity thì mở reserve khả thi và solve refill. Waiting giữa hai stop liên tiếp bị giới hạn tối đa 150 phút ngoài
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
quá ít chịu cost chất lượng; stop vượt nhịp ngày hợp lý chịu cost 800 để tránh
lịch dày máy móc.
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
đi theo TravelPlace. Pass utility có relative gap 5%, trong khi hai pass
priority vẫn exact.
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
Module ưu tiên factory Beam Search trong runtime Valhalla và dùng graph hybrid
CP-SAT làm fallback khi Beam thất bại hoặc trả lịch không đầy đủ. Beam áp hard
rule không nối restaurant-to-restaurant,
kiểm tra distance Q3, rating tối thiểu 3.0, review count từ Q2/P50,
opening window và khoảng chờ tối đa 60 phút.
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
| `GeminiMediaAnalyzer` | `explorer` | video/audio/ảnh | OCR frame và STT chunk chạy song song |
| `WebsiteSourceExtractor` | `explorer` | URL website public | HTTP, curl-cffi Safari, Playwright, rồi Markdown trafilatura |
| `SearchPlacesTool.search` | `shared/tools/search_places` | `PlaceSearchRequest` | `PlaceSearchResult` có status, selected, top matches, provider attempts và resolution reason |
| `GoogleMapsPlaywrightSearch.search` | `shared/tools/search_places` | Query, canonical ADM, type hint và limit | Candidate Google Maps chuẩn hóa, lưu `pending` với provenance trước khi trả |
| Bayesian rating tool | `shared/tools/bayesian_rating.py` | rating, review count và candidate observations | prior, adjusted rating, reliability và quality chuẩn hóa |

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

`PlaceSearchRequest.providerScope` cho phép retrieval gọi riêng Knowledge Graph
hoặc external provider. Candidate/match có `verificationStatus`; chỉ entity
Google Maps mang note `verification=not_verified` mới bị chiếu thành
`not_verified`, thay vì coi toàn bộ dữ liệu legacy có `status=draft` là chưa
đáng tin. Google provider không tự tạo `Special_Experience`, `Offer_Item` hoặc
`Has_Style`; nó chỉ tạo `Located_In` pending tới ADM đã resolve. Package vẫn có
`InMemoryPlaceSearch` cho test/development; runtime có database dùng PostgreSQL
KG cùng Playwright external fallback.

Các provider interface bên ngoài hiện có:

- `SearchProvider`
- `SearchQueryPlanner`
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
chọn URL note trước; nếu không có thì dùng mô tả Google Maps/Knowledge Graph.
Endpoint personal-notes chỉ cập nhật `personalNotes` với revision check, không
được sửa source note.
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

Information Finder đã có repository nguồn riêng. Module `conversation_memory` dùng `MemoryRepository` port, PostgreSQL asyncpg adapter, migration `009_conversation_memory.sql`, optimistic concurrency control và atomic `save_memory_and_facts`. Fact extraction giữ rule deterministic; reference resolution mặc định dùng hybrid Gemini với transcript/memory có cấu trúc và `RuleBasedReferenceResolver` fallback. Target do LLM trả về chỉ hợp lệ khi trùng active fact ID, vì vậy provider không thể tự tạo địa điểm. Fact insert idempotent theo `fact_id` giúp retry cùng message không làm hỏng lượt chat. `MergePolicyEvaluator` bảo vệ confirmed facts và giữ lịch sử superseded.
