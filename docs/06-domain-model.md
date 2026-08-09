# Mô hình miền nghiệp vụ

## Travel Group

- `TravelGroup`: một nhóm công khai gắn duy nhất với `countryCode`, có tên quốc
  gia, tên nhóm, ảnh mặc định và visibility.
- `TravelGroupMembership`: liên kết duy nhất giữa user và group, lưu thời điểm
  tham gia. Thao tác tham gia là idempotent.
- `TravelGroupPost`: bài viết văn bản thuộc một group công khai và một user tác
  giả. Bất kỳ user đang hoạt động nào cũng có thể đăng; membership không phải
  điều kiện đăng bài. Khách chưa đăng nhập vẫn có thể đọc bảng tin công khai.

Danh mục ban đầu gồm 193 quốc gia thành viên Liên Hợp Quốc và hai quốc gia quan
sát viên, tổng cộng 195 nhóm. Việc là thành viên không cấp thêm role hệ thống.

## Mô hình đã triển khai

### Alias trong Knowledge Graph

`KnowledgeAlias` áp dụng cho `Area`, `TravelPlace`, `Restaurant`,
`DrinkDessert` và `Accommodation`. Mỗi alias giữ `aliasType`, `language`,
`source`, `provider`, `status`, `confidence` và `verifiedAt`. Các loại được hỗ
trợ gồm `english_name`, `transliteration`, `abbreviation`, `former_name`,
`short_name` và `alternate_name`.

Alias lấy trực tiếp từ provider có stable identity được đánh dấu `verified`;
alias không dấu sinh bằng quy tắc được đánh dấu `generated`; alias nhập từ dump
cũ giữ trạng thái `imported`. Không tạo tổ hợp `place + city + country` hoặc lỗi
chính tả thành alias. PostgreSQL dùng `pg_trgm` để fuzzy top-k trên
`normalized_name` và `normalized_alias`; region, entity type và provider
identity vẫn phải phân xử kết quả nhập nhằng.

Batch enrichment chạy bằng `scripts/enrich_knowledge_graph_aliases.py`, mặc
định dry-run và chỉ ghi khi có `--apply`. Script sửa mojibake của dump cũ, có
batch/checkpoint và idempotent. Catalog `places` legacy đã bị loại khỏi runtime.

Enrichment từ Google Maps locale Việt chạy riêng bằng
`scripts/enrich_knowledge_graph_aliases_google.py`. Script mở URL của chính
Google identity đã lưu, chỉ nhận localized title khi `place_id` hoặc `data_id`
khớp tuyệt đối, lưu cache JSONL để resume và không nhận fuzzy result, category,
địa chỉ hoặc description làm alias. Tên Việt từ identity khớp được đánh dấu
`verified`; bản không dấu tương ứng được đánh dấu `generated`.

### Người dùng

Entity SQLAlchemy được lưu bền vững, gồm danh tính, password hash, role, trạng
thái tài khoản, hồ sơ, trạng thái creator, portfolio và timestamp. Refresh
session được lưu riêng với token hash, JTI, hạn dùng và trạng thái thu hồi. Các
role hiện tại là `traveler`, `host`, `creator` và `admin`; `host` được giữ để
tương thích nhưng chưa có luồng Marketplace riêng.

### Place runtime trên Knowledge Graph

PlaceSelector, Resolver, Profile, plan mutation và autocomplete đều đọc
`knowledge_entities.id` làm danh tính địa điểm. Tên field API `placeId` được giữ
để tương thích client nhưng giá trị là KG entity ID. Thuộc tính vận hành gồm
`opening_hours`, `rating`, `review_count`, `region_key`, loại địa điểm, tọa độ
và provenance nằm trong `knowledge_properties`.

Gallery được giữ riêng trong `knowledge_entity_images` để hỗ trợ nhiều ảnh;
`reviews` giữ review text riêng. Hai bảng này cùng `user_visited_places` dùng
FK `entity_id` tới `knowledge_entities`. Các bảng `places`, `place_images`,
`place_opening_hours` và `place_amenities` không còn tồn tại.

Giá vé TravelPlace được làm giàu theo batch bằng
`tool-crawl/crawl-price/enrich_travel_place_prices.py`. Kết quả có nguồn grounded hợp lệ được
lưu trong property JSON `admission_price`. Snapshot chỉ giữ giá vé vào cửa tiêu
chuẩn ban ngày cho một người lớn; `minAmount`, `maxAmount` và
`representativeAmount` cùng một giá, không trộn giá trẻ em/ưu tiên/VIP/tour đêm
hoặc dịch vụ phụ trợ. JSON còn giữ đơn vị tính, thời điểm lấy, model, confidence
và danh sách nguồn. Kết quả
không tìm thấy, nhập nhằng hoặc lỗi provider chỉ nằm trong cache resume, không
được ghi thành giá của entity. Script mặc định không thay đổi database và chỉ
ghi khi operator truyền `--apply`.

### Đối tượng giá trị của Planner

- `TripIntent`: aggregate bền vững có version cho một trip chat, gồm
  `destination`, `timing`, `travelParty`, `budget`, `notes`, `preferences` và
  `constraints`. Runtime truyền aggregate trực tiếp từ Explorer sang planning
  workflow. PostgreSQL chỉ lưu snapshot đã validate trong
  `trip_chats.current_trip_intent` và `trip_revisions.trip_intent_payload`.
- `BudgetEnvelope`: ngân sách đơn giản chỉ gồm số tiền gần đúng `targetAmount`,
  `currency` và mức `low`, `medium` hoặc `high`. Budget chỉ xuất hiện tại
  `tripSpec.budget`, không lặp lại trong `TravelIntent`.
- `TripThemeRequirement`: theme, focus tags, số activity tối thiểu và region mục
  tiêu ở cấp toàn chuyến; không chứa lịch theo ngày.
- `RequiredExperience` giữ Place/Activity/claim ID đã được graph xác thực. Backend
  hydrate `preferredTimeWindows` và `recommendedVisitMinutes` trực tiếp từ edge
  recommendation; đây là timing preference mềm có provenance, không phải giờ mở
  cửa và không tin giá trị timing do LLM tự trả.
- `PlanDay`: số thứ tự ngày, chủ đề và danh sách item.
- `MeetingPointQuery` là request đọc gồm ít nhất hai origin và loại venue. Origin
  chỉ là đầu vào định vị, không phải `SelectedPlace`. Kết quả giữ origin đã
  resolve, tâm địa lý, candidate venue và khoảng cách gần đúng; nó không tự sửa
  plan hoặc biến text trong `TripIntent.notes` thành stop.
- `Plan.regionStories`: câu chuyện/tip cấp destination từ creator, tách khỏi
  place note. Mỗi phần tử giữ text tiếng Việt, evidence span nguyên văn, URL và
  loại evidence; không có nội dung region-specific thì mảng rỗng.
- `PlanItem`: tên hiển thị, địa chỉ đã resolve khi có, tọa độ, khung giờ, loại
  địa điểm, source summary gộp trong `notes` chỉ để tương thích revision cũ,
  câu chuyện/mẹo chỉ đọc tách theo nguồn trong `noteSources` (gồm text tiếng
  Việt, URL, loại evidence và freshness), lời nhắc user trong `personalNotes`, ảnh catalog,
  rating/số lượt đánh giá khi có dữ liệu thật và `sourceDay` khi item bắt nguồn
  từ itinerary tham khảo. `notes` và `personalNotes` không ghi đè nhau; cả
  itinerary lẫn map popup đọc trực tiếp cùng snapshot này. Metadata provider
  như địa chỉ, rating và giờ mở cửa không được diễn đạt lại thành note.
  Khung giờ phải nằm trọn trong cùng ngày địa phương và không được đạt/vượt
  `24:00`.
  Mỗi ngày route-first giữ ba meal anchor sáng, trưa và tối. Quán ăn đã resolve
  từ URL được ưu tiên vào đúng anchor theo timing cue; anchor chưa có venue dùng
  item `finder_rule` tổng quát để giữ cấu trúc bữa ăn mà không giả mạo một địa
  điểm. Với intake URL, PlaceSelector tiếp tục thêm `finder_suggestion` vào mọi
  khoảng sáng, chiều và tối trước 21:00 còn đủ `duration + travel + buffer`,
  nhưng chỉ sau khi đã thử hết URL place tương thích và không được thay thế
  hoặc làm mất `SelectedPlace` có provenance URL.
- Candidate URL `needs_review` được giữ trong `UnscheduledPlace` với
  `reasonCode=identity_needs_review`, tên gốc, `candidateId`, URL nguồn và
  `topMatches`. Planner không tự tìm một venue khác để thay candidate chưa xác
  định danh tính.
- `PlanTransportLeg`: điểm đầu/cuối, mode, distance, duration, geometry,
  `source`, `verified` và `fetchedAt`. Leg provider có provenance
  `valhalla_routing` hoặc `opentripplanner_transit`; fallback địa lý phải giữ
  `verified=false`. `alternatives` chứa các `PlanTransportOption` khả thi khác
  với cùng shape route và `details` có mode/tuyến public transit khi có.
  Public transit không có provider route xác minh không được tạo thành option
  ước tính và không được có geometry nối thẳng hai điểm.
  Chuỗi chặng từ vị trí thiết bị qua các stop của một ngày cũng dùng value
  object này nhưng là dữ liệu tạm thời, không được thêm vào snapshot plan hoặc
  revision.
- `CheckReport`: trạng thái, danh sách vấn đề và tóm tắt.
- `Plan`: loại main/backup, trạng thái vòng đời, intent, `tripThemes`, các ngày,
  liên kết plan cha và báo cáo kiểm tra.

Plan từ các endpoint độc lập hiện vẫn là object Pydantic được giữ trong bộ nhớ.
Plan tạo qua trip chat vẫn được lưu dưới dạng snapshot JSON có version trong
`trip_revisions`; mỗi revision chứa cả plan và đúng TripIntent snapshot đã dùng.
`trip_chats.current_plan` và `current_trip_intent` giữ trạng thái hiện hành.
Năm field intake có cấu trúc (`destination`, `timing`, `travelParty`, `budget`,
`notes`) đọc từ TripIntent hiện hành. Khi user lưu một field trên chat đã có
plan, backend validate rồi ghi ngay `current_trip_intent`, tăng
`trip_intent_version`, đặt `trip_intent_plan_status=queued` và trả response mà
không chờ Planner. Durable worker tạo lại plan theo version mới nhất; chỉ khi
thành công mới cập nhật `current_plan`, thêm `TripRevision` chứa đúng cặp
TripIntent/plan và đặt trạng thái `synced`. Nếu user sửa tiếp trong lúc worker
chạy, output của version cũ không được ghi và job được xếp lại cho version mới.

### Lịch sử hội thoại chuyến đi đã triển khai

- `TripChat`: thuộc đúng một user, đại diện cho một chuyến đi/điểm đến, giữ khóa
  TripIntent hiện tại, version/sync status của intent, plan hiện tại và số
  revision của plan. Không còn cột
  `current_explorer`.
- `TripChatMessage`: tin nhắn user/assistant theo thứ tự; user message đồng thời
  giữ lifecycle của turn (`queued/executing/completed/failed`), decision và lỗi
  an toàn. Một batch URL/ảnh dùng lifecycle ID của user message làm `batchId`
  chung cho các source job con, nên request được lưu trước khi worker chạy và
  assistant response không tạo lại user message. Không còn bảng
  `trip_chat_turns` sao chép lại content/attachment. Assistant message xác nhận
  thao tác tạo/sửa plan dùng `messageKind=plan_update`: vẫn được lưu để audit
  nhưng không hiển thị trong transcript Q&A của Planner.
- `TripRevision`: snapshot bất biến gồm `planPayload`, `tripIntentPayload` và
  `intakeId` sau mỗi lần tạo hoặc sửa plan thành công.
- `KnowledgeGraphImport`: envelope dùng chung cho URL/image job, Explorer intake
  durable trip-intent planning job và admin import. `processingStatus`
  (`queued/running/succeeded/failed`) tách
  khỏi `reviewStatus` (`not_required/pending/approved/rejected`). Job Explorer
  còn có `processing_phase` (`queued/exploring/planning/complete`), được trả dưới
  tên `phase` trong URL job API, để UI hiển thị bước hiện tại mà không thay đổi
  lifecycle chính.
- `SourceDocument`: canonical URL cùng caption/STT/OCR, extracted context,
  version/hash và freshness. Raw provider payload không đi qua boundary này.
- `KnowledgeGraphImportNode/Edge`: Area/Venue observation, evidence,
  `sourceActivity`, Top-K identity và quan hệ graph đề xuất. Import node không
  còn field display note. Admin review chỉ quyết định promotion vào graph chung;
  Planner vẫn được dùng snapshot provisional.

Một user có nhiều `TripChat`, ví dụ Hà Nội, TP.HCM và Paris. Follow-up trong
cùng chat luôn tạo revision mới cho cùng plan ID và cập nhật `current_plan`;
không tạo một trip chat hay plan identity mới. Request sửa dùng optimistic
`expectedRevision`; client cũ nhận `VERSION_CONFLICT` thay vì ghi đè thay đổi
mới hơn. Khi user xóa một `TripChat`, các `TripChatMessage` và
`TripChatPlanRevision` thuộc chat đó cũng bị xóa theo.

## Cụm thực thể nghiệp vụ mục tiêu của MVP

### Tài khoản và hồ sơ

- `User`
- `UserProfile`
- `CreatorProfile`
- `TripMembership` với quyền host/editor/viewer

Không dùng một trường role duy nhất làm toàn bộ mô hình authorization vì một user
có thể đồng thời mua plan, tổ chức chuyến đi và tạo nội dung.

### Lập kế hoạch chuyến đi

- `TripPlan`: chủ sở hữu, trạng thái, nguồn, phiên bản hiện tại, ngày đi, timezone
  và tiền tệ.
- `TripPlanVersion`: snapshot bất biến dùng khi publish và mua.
- `TripDay`: ngày địa phương/số thứ tự ngày, chủ đề và ghi chú.
- `TripItem`: ID ổn định, tham chiếu place, thời gian, thời lượng, chi phí,
  phương tiện, trạng thái khóa, nguồn và trạng thái thực hiện.
- `Place`: danh tính địa điểm chuẩn hóa, độc lập với provider và tọa độ.
- `PlanCheck`: vấn đề và bằng chứng được tạo cho một phiên bản plan.
- `PlanSource`: nguồn từ prompt, URL, plan creator hoặc nhập thủ công kèm
  provenance.
- `UnscheduledPlace`: địa điểm đã xác nhận nhưng chưa thể xếp, kèm lý do và
  ràng buộc gây xung đột.

### Nhập nội dung và chuẩn hóa địa điểm

- `SourceImport`: URL gốc, loại nguồn, chủ sở hữu, trạng thái, quyền truy cập,
  connector, thời điểm lấy và chính sách lưu.
- `SourceArtifact`: metadata, caption, transcript, frame reference hoặc văn bản
  được phép lưu; không đồng nhất artifact với instruction cho model.
- `SourceDocument`: phần `SourceArtifact` đã triển khai, lưu theo canonical URL.
  JSON `artifacts` chứa `webpage`/`caption`/`stt`/`ocr` theo language; JSON
  `extractedContext` giữ observation đã chuẩn hóa. YouTube caption dùng cùng
  document này thay vì một transcript cache riêng.
- `SourceClaim`: một thông tin được trích xuất như địa điểm, hoạt động, thời điểm,
  giá hoặc mẹo, kèm evidence span, confidence và trạng thái xác nhận.
- Observation từ URL phân loại `entityType` thành venue, sub-place, address,
  city, person, activity, food hoặc unknown. Chỉ venue/sub-place có evidence đủ
  authority mới trở thành `PlaceCandidate`; address được giữ làm `addressHint`,
  còn sub-place có `parentPlace` được gộp về venue cha.
- `ExtractedContext` giữ `expectedPlaceCount`, `extractionCoverage` và
  `coverageStatus`. Coverage thấp dừng trước alias enrichment, provider resolve
  và Planner; coverage cần review tắt PlaceSelector để không âm thầm thay stop nguồn.
- `PlaceCandidate`: tên thô từ nguồn, `searchRegion` của stop và các kết quả
  chuẩn hóa có thể tương ứng. `searchRegion` không đồng nhất với điểm lưu trú
  chính; ví dụ trip base Hà Nội nhưng stop Day 2 có thể tìm trong Ninh Bình.
  Candidate giữ `extractionConfidence` riêng cho chất lượng evidence; kết quả
  provider giữ `resolutionConfidence` riêng cho độ chắc chắn identity. Trường
  `confidence` cũ vẫn là extraction confidence trong thời gian tương thích API.
  Candidate tách `observedAliases` có provenance metadata/caption/STT/OCR khỏi
  `generatedLookupAliases` do normalizer/LLM tạo. Metadata có authority cao làm
  anchor khi nhiều observation nói về cùng place; alias sinh ra chỉ phục vụ
  lookup và không được trình bày như evidence của URL.
- `KnowledgeGraphImportNode`: thay `UserMustPlace`. Node giữ candidate name,
  alias quan sát, evidence, source note, Top K entity, provider snapshot tối
  giản và `selectedEntityId` nullable. Node mới không tự ghi vào `places` hay
  graph canonical; promotion cần admin review.
- `PlaceMatch`: lựa chọn giữa candidate và `Place`, do hệ thống đề xuất hoặc user
  xác nhận. Catalog resolver chỉ tự nhận record top-1 khi điểm tổng hợp vượt
  ngưỡng tuyệt đối và cách top-2 đủ xa; điểm thấp hoặc sát nhau giữ trạng thái
  unresolved để provider kế tiếp xác minh, không biến ranking nội bộ thành bằng
  chứng identity. Explorer trả tối đa năm `topMatches` có rank, score component,
  provider và rejection reason; frontend mặc định chỉ cần ba lựa chọn đầu cho
  candidate `needs_review`.
  Alias chỉ trở thành `verifiedAliases` sau khi cùng stable provider identity đã
  vượt policy. `verifiedVietnameseAliases` là tập con tiếng Việt an toàn để UI
  ưu tiên làm nhãn hiển thị.
  Nếu Top K là các chi nhánh cùng tên, node giữ
  `identityStatus=branch_ambiguous`; Planner chọn chi nhánh gần route anchor và
  lưu lựa chọn theo plan revision, không gọi Google và không sửa identity toàn
  cục của node.
- `SelectedPlace`: place đã được user chọn cho trip, mức ưu tiên, source claim và
  ghi chú; đây là đầu vào chính thức của Planner. Với place lấy từ một itinerary
  URL, context còn giữ thứ tự, ngày, timing cue, hoạt động và duration được nguồn
  nói rõ để TripThemePlanner/PlaceSelector có thể bám blueprint mà không coi đó là dữ liệu vận
  hành đã xác minh. `sourceProvider` giữ provider đã resolve candidate để UI có
  thể phân biệt provenance URL với Google Maps Playwright mà không suy đoán từ tên. Stop URL
  hiển thị nhãn Việt đã resolve; tên candidate gốc vẫn được giữ trên
  `KnowledgeGraphImportNode` cùng evidence.
- `DestinationStay`: phân bổ một khoảng ngày cho thành phố/khu vực từ heading
  của nguồn (ví dụ `Hanoi - 2 days`). Đây là context cấp hành trình, không phải
  `Place` hay `SelectedPlace`; PlaceSelector dùng stay hai ngày làm target area
  cho hai day slot tương ứng và có thể để trống item để người dùng bổ sung sau.
- `PreferenceSnapshot`: context ngắn hạn của một Explorer intake, chỉ giữ tín
  hiệu chuẩn hóa (`dimension`, `value`, `score`, `confidence`, `scope`,
  `origin`, `sourceTypes`), không giữ raw prompt/OCR/transcript.
- `TravelerProfile`: hồ sơ du lịch dài hạn theo user, được lưu trong
  `traveler_profiles` và `traveler_preference_signals`. Mỗi signal có nguồn,
  explicit/inferred, confidence, số lần quan sát, trạng thái và intake evidence
  gần nhất. Signal suy luận phải được quan sát lặp lại trước khi ảnh hưởng plan.
  Mỗi user turn tạo một `PreferenceObservationJob` idempotent theo message ID
  trong cùng transaction. Worker chỉ claim sau khi turn hoàn tất, dùng
  `PreferenceExtractor` structured-output rồi áp policy trước khi merge profile.
  Job chỉ tham chiếu message, không sao chép raw chat; profile chỉ giữ signal đã
  chuẩn hóa và message ID gần nhất làm provenance. Preference giới hạn cho một
  chuyến không được thăng cấp thành preference global.
- `ImportJob`: tiến độ, bước hiện tại, lỗi có thể retry và kết quả từng phần.

Quan hệ chính:

```text
SourceImport -> SourceArtifact -> SourceClaim -> PlaceCandidate
                                             -> PlaceMatch -> Place
                                                            |
                                                            v
                                                     SelectedPlace
                                                            |
                                                            v
                                                        TripPlan
```

Một `SelectedPlace` có thể có nhiều claim từ nhiều URL. Gộp trùng không được làm
mất provenance. Xóa URL khỏi draft phải có chính sách rõ ràng với địa điểm đã
được user xác nhận thay vì âm thầm xóa item khỏi plan.

Địa điểm tự động từ Explorer mặc định có `preferenceLevel=preferred` và
`mustVisit=false`. Chỉ input nói rõ hoặc thao tác xác nhận/khóa tương đương mới
tạo `must_visit`.

### Chợ lịch trình

- `MarketplaceListing`: sản phẩm do creator sở hữu, trỏ tới phiên bản plan đã
  publish.
- `ListingVersion`: tên, media, mô tả, quy tắc preview, giá, license, độ mới và
  trạng thái kiểm duyệt.
- `Favorite`
- `Order` và `OrderLine`
- `Payment` và `Refund`
- `PlanEntitlement`: quyền truy cập được cấp bởi order đã xác nhận.
- `Review` và `Report`
- **Triển khai DB Backend MVP**:
  - `marketplace_plans`: id, creator_id, status, current_published_version_id.
  - `marketplace_plan_versions`: id, marketplace_plan_id, version, source_plan_id, source_plan_version_id, title, description, destination, duration_days, category, price_amount, media_urls, preview_snapshot, moderation_status, published_at (Bất biến sau khi published).
  - `orders` & `order_items`: Lưu thông tin đơn hàng, số tiền, buyer, status (`pending` -> `paid` / `refunded`).
  - `payments` & `payment_events`: Ghi nhận giao dịch thanh toán MoMo Sandbox.
  - `entitlements`: Cấp quyền truy cập duy nhất cho buyer sau khi order `paid`, liên kết với `copied_plan_id` của bản sao cá nhân.
  - `reviews` & `reports`: Lưu đánh giá từ buyer đã mua (`active` entitlement) và báo cáo vi phạm listing.
  - `audit_events`: Lưu nhật ký kiểm toán cho toàn bộ hành động quản trị viên (`action`, `resource_id`, `actor_id`, `metadata` ẩn từ khóa nhạy cảm).

Order phải tham chiếu đến phiên bản listing và plan bất biến. Buyer chỉnh sửa một
`TripPlan` cá nhân mới, không bao giờ sửa aggregate đã publish của creator.

### Nền tảng

- `Notification`
- `Achievement` và `UserAchievement`
- `UserVisitedPlace`: dấu mốc riêng của user cho một Knowledge Graph entity đã
  chuẩn hóa, gồm
  ngày đi và ghi chú; một user chỉ có một dấu mốc hiện tại trên mỗi place.
- `UserPost`: bài viết/media công khai do user đăng, gồm `contentType` (`post` hoặc
  `reel`), caption, URL media do storage adapter tạo, location tag bắt buộc và thời điểm tạo. Nội dung
  hiển thị trong lưới hồ sơ cá nhân và feed Khám phá; tác giả luôn lấy từ session.
- `CreatorMetric` hoặc analytics event được tổng hợp
- `AuditEvent`

## Bất biến nghiệp vụ chính

- Số thứ tự ngày trong một version phải duy nhất và có thứ tự.
- Plan dự phòng có đúng một plan chính làm cha và không được tự động thay thế nó.
- AI không được thay đổi `TripItem` đã khóa khi chỉnh sửa theo phạm vi.
- Mỗi trip chat chỉ thuộc một user; user khác không được đọc hoặc sửa chat.
- Revision của trip chat tăng đúng một đơn vị sau mỗi lần Planner hoàn thành.
- Tại một thời điểm worker URL chỉ claim một job; URL trong cùng batch được claim
  theo thứ tự user đã dán. Lỗi một job không xóa hoặc chặn retry riêng các job
  còn lại. User được xóa job `queued` hoặc dừng và xóa job `running` của chính
  mình; worker phải hủy xử lý và giải phóng FIFO trước khi endpoint xác nhận.
  User được xóa job `succeeded` hoặc `failed` của chính mình khỏi lịch sử hiển
  thị; thao tác này không xóa revision plan mà job đã tạo.
- Follow-up giữ nguyên plan ID hiện tại; snapshot revision trước không bị sửa.
- Follow-up yêu cầu tăng số ngày được phép suy ra duration tối thiểu từ toàn bộ
  địa điểm cũ và mới sau khi merge. Follow-up không yêu cầu tăng ngày phải giữ
  duration hiện tại và đưa phần vượt sức chứa vào `UnscheduledPlace`.
- Intake hiện chạy ở chế độ không hỏi lại user. Mọi candidate có evidence được
  stage trong import node; chỉ candidate có representative coordinates mới
  được chuyển thành `SelectedPlace`. Graph canonical vẫn chờ admin review.
- Mọi `SelectedPlace` đã resolve có provenance URL là input bắt buộc của plan.
  Khi user chưa khóa số ngày hoặc khoảng ngày đi, Planner tự tăng số ngày, tối
  đa giới hạn schema, để tạo đủ capacity. Khi duration/date đã được user nêu rõ,
  Planner giữ nguyên duration và đưa overflow vào `UnscheduledPlace`; UI phải
  cho thêm thủ công hoặc tạo prompt yêu cầu AI xếp lại. Stop nhà hàng/quán ăn
  thuộc node `Restaurant` dùng tối đa ba meal anchor mỗi ngày và không chiếm
  ngân sách thời gian activity; node `DrinkDessert` không được lấp meal. Với
  place chưa qua graph, bằng chứng món chính được dùng làm fallback. `food` chỉ
  là category trình bày để UI dùng chung icon cho các stop ăn uống, không phải
  node type và không đủ điều kiện lấp meal;
  cafe/coffee vẫn là activity. PlaceSelector suggestion chỉ dùng capacity còn trống và
  không được chiếm chỗ của URL place. Revision URL tiếp theo phải phục hồi cả
  URL place đã resolve từ Explorer history, kể cả khi revision cũ chưa xếp được.
  Finder ưu tiên category chưa xuất hiện; riêng coffee do Finder thêm tối đa một
  lần mỗi ngày và không thêm nếu ngày đó đã có coffee từ URL, trừ khi user yêu
  cầu rõ coffee tour/cafe hopping.
- Meal venue do Planner bổ sung được chọn ở cấp toàn chuyến sau khi số ngày và
  cụm activity đã có. Candidate ưu tiên đường
  `Area -> SPECIAL_EXPERIENCE -> Activity -> TARGETS_PLACE -> Restaurant`;
  experience dining tổng quát được mở rộng qua
  `Activity -> INVOLVES_ITEM -> Item` và
  `Restaurant -> OFFERS_ITEM -> Item`. Catalog được tải bounded một lần, venue
  và món đã dùng bị loại trên toàn chuyến; Gemini không nằm trong đường chọn
  meal chính.
- Caption, danh sách nhiều venue bị gộp hoặc match rộng chỉ tới thành phố không
  được đưa vào timeline; candidate có nguồn được giữ để review và PlaceSelector
  không bổ sung địa điểm khác như một bản thay thế của candidate đó.
- Heading dạng `thành phố - N ngày` được giữ thành `DestinationStay`, không
  resolve thành stop. Khi URL chỉ có stay và chưa có venue cụ thể, PlaceSelector không
  tự thêm place; plan giữ các ngày trống trong đúng thành phố.
- Planner downstream nhận TripIntent hiện tại và đọc proposal theo `intakeId`
  từ `knowledge_graph_import_nodes`. Lựa chọn chi nhánh theo route chỉ tồn tại
  trong plan revision.
- Địa điểm đã xác nhận phải được xếp hoặc xuất hiện trong `UnscheduledPlace` kèm
  lý do, không được âm thầm bỏ.
- Source claim luôn trỏ tới import và evidence; dữ liệu provider bổ sung phải có
  `fetchedAt`.
- Version đã publish là bất biến.
- Nội dung trả phí yêu cầu entitlement còn hiệu lực.
- Chỉ giao dịch mua đã xác minh mới được tạo review của buyer.
- Payment webhook phải idempotent và kiểm tra số tiền/đơn vị tiền tệ.
- Dữ liệu địa điểm/tuyến đường phải thể hiện độ mới/provenance khi cần.
- Xóa user phải tuân theo nghĩa vụ lưu giữ hồ sơ tài chính và dữ liệu.

## Vòng đời khái quát

```text
Processing: queued -> running -> succeeded
                   \------------> failed
Review:     not_required | pending -> approved | rejected
TripPlan: draft -> generating -> editable -> checking -> ready -> archived
Listing:  draft -> review -> published -> paused -> retired
Order:    pending -> paid -> fulfilled
                    \-> refunded / disputed
```

Chuyển trạng thái phải đi qua domain service rõ ràng. Không cho phép payload API
tùy ý cập nhật trạng thái.
