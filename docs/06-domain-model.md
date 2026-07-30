# Mô hình miền nghiệp vụ

## Mô hình đã triển khai

### Người dùng

Entity SQLAlchemy được lưu bền vững, gồm danh tính, password hash, role, trạng
thái tài khoản, hồ sơ, trạng thái creator, portfolio và timestamp. Refresh
session được lưu riêng với token hash, JTI, hạn dùng và trạng thái thu hồi. Các
role hiện tại là `traveler`, `host`, `creator` và `admin`; `host` được giữ để
tương thích nhưng chưa có luồng Marketplace riêng.

### Đối tượng giá trị của Planner

- `TravelIntent`: điểm đến, số ngày, ngân sách, phong cách, nhịp độ, sở thích,
  địa điểm bắt buộc, địa điểm tránh, ràng buộc và câu hỏi làm rõ.
- `BudgetEnvelope`: ngân sách đơn giản chỉ gồm số tiền gần đúng `targetAmount`,
  `currency` và mức `low`, `medium` hoặc `high`. Budget chỉ xuất hiện tại
  `tripSpec.budget`, không lặp lại trong `TravelIntent`.
- `MacroPlan`: tên plan, điểm đến và mô tả cấp cao cho từng ngày.
- `PlanDay`: số thứ tự ngày, chủ đề và danh sách item.
- `PlanItem`: tên hiển thị, địa chỉ đã resolve khi có, tọa độ, khung giờ, loại
  địa điểm, ghi chú và `sourceDay` khi item bắt nguồn từ itinerary tham khảo.
  Khung giờ phải nằm trọn trong cùng ngày địa phương và không được đạt/vượt
  `24:00`.
- `PlanTransportLeg`: điểm đầu/cuối, mode, distance, duration, geometry,
  `source`, `verified` và `fetchedAt`. Leg HERE có provenance
  `here_routing_v8` hoặc `here_transit_v8`; fallback địa lý phải giữ
  `verified=false`. `alternatives` chứa các `PlanTransportOption` khả thi khác
  với cùng shape route và `details` có mode/tuyến public transit khi có.
- `CheckReport`: trạng thái, danh sách vấn đề và tóm tắt.
- `Plan`: loại main/backup, trạng thái vòng đời, intent, macro plan, các ngày,
  liên kết plan cha và báo cáo kiểm tra.

Plan từ các endpoint độc lập hiện vẫn là object Pydantic được giữ trong bộ nhớ.
Plan tạo qua trip chat được lưu dưới dạng snapshot JSON có version trong
`trip_chat_plan_revisions`; `trip_chats.current_plan` luôn trỏ tới snapshot mới
nhất và giữ nguyên plan ID khi user yêu cầu AI sửa tiếp.

### Lịch sử hội thoại chuyến đi đã triển khai

- `TripChat`: thuộc đúng một user, đại diện cho một chuyến đi/điểm đến, giữ
  Explorer context hiện tại, plan hiện tại và số revision.
- `TripChatMessage`: tin nhắn user/assistant theo thứ tự, attachment chỉ lưu tên
  file; không lưu bytes ảnh.
- `TripChatPlanRevision`: snapshot plan và Explorer context bất biến sau mỗi lần
  tạo hoặc sửa thành công, kèm `intakeId` đã sinh ra snapshot đó.
- `ExplorerIntake`: identity bền vững cho mỗi lần Explorer xử lý input; là
  parent của các record `UserMustPlace`, kể cả khi intake không resolve được
  địa điểm nào.

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
- `SourceClaim`: một thông tin được trích xuất như địa điểm, hoạt động, thời điểm,
  giá hoặc mẹo, kèm evidence span, confidence và trạng thái xác nhận.
- `PlaceCandidate`: tên thô từ nguồn, `searchRegion` của stop và các kết quả
  chuẩn hóa có thể tương ứng. `searchRegion` không đồng nhất với điểm lưu trú
  chính; ví dụ trip base Hà Nội nhưng stop Day 2 có thể tìm trong Ninh Bình.
- `UserMustPlace`: candidate của intake đã được provider resolve tới một địa
  điểm cụ thể có đủ latitude/longitude; giữ source URL, address, description,
  provider, `searchRegion`, `sourceEvidence` tách theo
  `stt`/`ocr`/`caption` và độ mới ngay trên record. Candidate
  provisional/unresolved, thiếu tọa độ hoặc chỉ match rộng tới thành phố/quốc
  gia không được lưu vào bảng này. `candidateName` luôn là nhãn từ nguồn;
  `resolvedName` là kết quả provider riêng, không tự ghi đè nhãn nguồn của stop
  URL. Flow Explorer không tạo hoặc cập nhật `Place`.
- `PlaceMatch`: lựa chọn giữa candidate và `Place`, do hệ thống đề xuất hoặc user
  xác nhận.
- `SelectedPlace`: place đã được user chọn cho trip, mức ưu tiên, source claim và
  ghi chú; đây là đầu vào chính thức của Planner. Với place lấy từ một itinerary
  URL, context còn giữ thứ tự, ngày, timing cue, hoạt động và duration được nguồn
  nói rõ để Planner/Finder có thể bám blueprint mà không coi đó là dữ liệu vận
  hành đã xác minh. Stop URL luôn giữ tên candidate đã tổng hợp từ evidence;
  provider chỉ bổ sung identity, địa chỉ và tọa độ khi match đã resolve.
- `PreferenceSnapshot`: JSON ngắn hạn của một Explorer intake, chỉ giữ tín hiệu
  chuẩn hóa (`dimension`, `value`, `score`, `confidence`, `scope`,
  `sourceTypes`), không giữ raw prompt/OCR/transcript.
- `LongTermPreferenceProfile`: hồ sơ có version được aggregate vào duy nhất cột
  JSON `users.travel_preferences`; gồm explicit preference, score, confidence,
  số lần quan sát và thời điểm cập nhật.
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
- `UserVisitedPlace`: dấu mốc riêng của user cho một `Place` đã chuẩn hóa, gồm
  ngày đi và ghi chú; một user chỉ có một dấu mốc hiện tại trên mỗi place.
- `UserPost`: bài viết/media do user đăng và hiển thị trong lưới hồ sơ cá nhân.
- `CreatorMetric` hoặc analytics event được tổng hợp
- `AuditEvent`

## Bất biến nghiệp vụ chính

- Số thứ tự ngày trong một version phải duy nhất và có thứ tự.
- Plan dự phòng có đúng một plan chính làm cha và không được tự động thay thế nó.
- AI không được thay đổi `TripItem` đã khóa khi chỉnh sửa theo phạm vi.
- Mỗi trip chat chỉ thuộc một user; user khác không được đọc hoặc sửa chat.
- Revision của trip chat tăng đúng một đơn vị sau mỗi lần Planner hoàn thành.
- Follow-up giữ nguyên plan ID hiện tại; snapshot revision trước không bị sửa.
- Follow-up yêu cầu tăng số ngày được phép suy ra duration tối thiểu từ toàn bộ
  địa điểm cũ và mới sau khi merge. Follow-up không yêu cầu tăng ngày phải giữ
  duration hiện tại và đưa phần vượt sức chứa vào `UnscheduledPlace`.
- Intake hiện chạy ở chế độ không hỏi lại user. Candidate chỉ được commit vào
  `UserMustPlace` khi đã resolve tới danh tính cụ thể và có đủ latitude,
  longitude. Candidate provisional/unresolved hoặc thiếu tọa độ bị loại trước
  persistence và không được chuyển thành `SelectedPlace`.
- Caption, danh sách nhiều venue bị gộp hoặc match rộng chỉ tới thành phố không
  được lưu hay đưa vào timeline; Finder được phép bổ sung địa điểm đã chuẩn hóa
  thay thế.
- Planner downstream nhận trực tiếp Explorer context và không đọc
  `UserMustPlace`. Finder downstream dùng cả `intakeId + userId` để đọc đúng
  record `UserMustPlace`; Explorer không điều phối hai module này.
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
Import:   queued -> fetching -> extracting -> resolving -> needs_review -> ready
             \-------------------------------------------------------> failed
TripPlan: draft -> generating -> editable -> checking -> ready -> archived
Listing:  draft -> review -> published -> paused -> retired
Order:    pending -> paid -> fulfilled
                    \-> refunded / disputed
```

Chuyển trạng thái phải đi qua domain service rõ ràng. Không cho phép payload API
tùy ý cập nhật trạng thái.
