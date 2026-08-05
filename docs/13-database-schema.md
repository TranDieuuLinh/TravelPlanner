# Database schema

Tài liệu này mô tả database mục tiêu cho VSF Travel dựa trên codebase hiện tại và
danh sách bảng chính đã chốt. Bảng trạng thái bên dưới phân biệt phần đã có
model/migration với schema mục tiêu chưa triển khai.

## Trạng thái triển khai

| Table | Status | Nguồn trong codebase |
| --- | --- | --- |
| `users` | Implemented | `backend/app/modules/users/model.py`, migration `20260727_0001_create_users_table.py` |
| `auth_sessions` | Implemented | `backend/app/modules/auth/model.py`, migration `20260727_0002_add_auth_and_profile.py` |
| `places` | Planned | Cần thêm module/model |
| `places` | Implemented | `backend/app/modules/places/model.py`, migration `20260727_0002_create_places_table.py` |
| `source_documents` | Implemented | Canonical URL + caption/STT/OCR + extracted context, migration `20260805_0037` |
| `knowledge_graph_imports` | Implemented | Job/intake/admin import envelope; processing và review status tách biệt |
| `knowledge_graph_import_nodes` | Implemented | Area/Venue proposal, evidence, note, Top K identity và provider snapshot |
| `knowledge_graph_import_edges` | Implemented | Quan hệ graph đề xuất, chỉ promote sau review |
| `trip_chats` | Implemented | Trạng thái hiện hành, gồm TripIntent draft/current JSON đã validate |
| `trip_chat_messages` | Implemented | Message và lifecycle turn dùng chung một row user request |
| `trip_revisions` | Implemented | Snapshot bất biến `trip_intent_payload + plan_payload + intake_id`, migration `20260805_0036` |
| `knowledge_graph_imports.explorer_timing`, `planner_timing` | Implemented | Snapshot timing riêng cho Explorer job |
| `place_external_refs` | Planned | Tham chiếu và độ mới dữ liệu từ place provider |
| `trips` | Planned | Liên quan module `plans` hiện đang dùng Pydantic/in-memory |
| `itinerary_items` | Planned | Nên dùng thay `trip_places` vì lưu được lịch trình chi tiết |
| `trip_members` | Planned | Cần cho chia sẻ trip |
| `marketplace_plans` | Implemented | Listing/sản phẩm ổn định của Marketplace, migration `20260727_0003_add_person_c_marketplace.py` |
| `marketplace_plan_versions` | Implemented | Snapshot bất biến của listing/version, migration `20260727_0003_add_person_c_marketplace.py` |
| `marketplace_plan_items` | Planned | Có thể thêm sau nếu cần lưu itinerary mẫu theo version |
| `orders` | Implemented | Đơn mua listing version, migration `20260727_0003_add_person_c_marketplace.py` |
| `order_items` | Implemented | Khóa marketplace plan version và giá mua, migration `20260727_0003_add_person_c_marketplace.py` |
| `payments` | Implemented | Giao dịch thanh toán của order, migration `20260727_0003_add_person_c_marketplace.py` |
| `payment_events` | Implemented | Event/IPN idempotent từ payment provider, migration `20260727_0003_add_person_c_marketplace.py` |
| `entitlements` | Implemented | Quyền truy cập sau thanh toán, migration `20260727_0003_add_person_c_marketplace.py` |
| `reviews` | Implemented | Review từ buyer cho marketplace plan, migration `20260727_0003_add_person_c_marketplace.py` |
| `reports` | Implemented | Báo cáo listing cho admin xử lý, migration `20260727_0003_add_person_c_marketplace.py` |
| `audit_events` | Implemented | Nhật ký hành động quan trọng, migration `20260727_0003_add_person_c_marketplace.py` |
| `favorites` | Implemented | User lưu marketplace plan yêu thích, migration `20260727_0003_add_person_c_marketplace.py` |
| `user_visited_places` | Implemented | FK user/place cho bản đồ thành tựu, migration `20260730_0013_add_profile_showcase.py` |
| `user_posts` | Implemented | Bài viết/media trên hồ sơ, migration `20260730_0013_add_profile_showcase.py` |
| `achievements` | Planned | Danh mục thành tựu |
| `user_achievements` | Planned | Tiến độ/thời điểm user đạt thành tựu |

## Core tables

### `users`

Lưu người dùng hệ thống.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | integer PK | Đã triển khai |
| `email` | varchar(255), unique | Đăng nhập/liên hệ |
| `full_name` | varchar(255) | Tên hiển thị |
| `role` | varchar(32) | `traveler`, `host`, `creator`, `admin` |
| `avatar_url` | varchar(500), nullable | Ảnh đại diện |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `traveler_profiles`

Hồ sơ cá nhân hóa dài hạn, một bản ghi cho mỗi user.

| Column | Type | Notes |
| --- | --- | --- |
| `user_id` | integer PK/FK | FK `users.id`, cascade delete |
| `version` | integer | Version contract profile |
| `observation_count` | integer | Tổng signal đủ điều kiện đã quan sát |
| `created_at`, `updated_at` | timestamptz | Audit thời gian |

### `traveler_preference_signals`

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string PK | Opaque signal ID |
| `user_id` | integer FK | Owner của profile |
| `dimension`, `value`, `label` | varchar | Preference chuẩn hóa và nhãn hiển thị |
| `score`, `confidence`, `observations` | numeric | Aggregate learning |
| `origin`, `status` | varchar | `explicit/inferred`, `active/rejected` |
| `scope`, `destination` | varchar | Global hoặc theo destination |
| `last_evidence_intake_id` | string nullable | Provenance tới Explorer import ID |
| `first_observed_at`, `last_observed_at` | timestamptz | Audit quan sát |

`traveler_preference_signal_sources` lưu các source type theo từng signal,
không dùng mảng JSON trong signal.

### `places`

Lưu địa điểm có thể xuất hiện trong lịch trình.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `name` | varchar | Tên địa điểm |
| `place_type` | varchar | attraction, restaurant, hotel, cafe, station, airport |
| `address` | text, nullable | Địa chỉ |
| `city` | varchar, nullable | Thành phố |
| `country` | varchar, nullable | Quốc gia |
| `country_code` | varchar(2), nullable | Mã quốc gia ISO, ví dụ `VN` |
| `region_key` | varchar(160), nullable | Khóa gom nhóm ổn định, ví dụ `vn,da-nang,hai-chau` |
| `primary_area` | varchar(160), nullable | Tên khu vực hiển thị |
| `latitude` | decimal, nullable | Tọa độ |
| `longitude` | decimal, nullable | Tọa độ |
| `status` | varchar(32) | `active`, `temporarily_closed`, `permanently_closed`, `unverified` |
| `opening_hours` | json, nullable | Giờ mở cửa đã chuẩn hóa |
| `typical_duration_minutes` | integer, nullable | Thời lượng ghé thăm điển hình |
| `data_confidence` | varchar(16) | `low`, `medium`, `high` |
| `source_fetched_at` | timestamptz, nullable | Thời điểm dữ liệu vận hành được lấy hoặc xác minh |
| `revision` | bigint | Tăng khi dữ liệu ảnh hưởng Planner thay đổi |
| `metadata` | json | Tags, mô tả ngắn và thuộc tính phụ không cần truy vấn thường xuyên |
| `deleted_at` | timestamptz, nullable | Soft delete để giữ toàn vẹn tham chiếu lịch trình |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

`city` và `country` vẫn được giữ để hiển thị và tương thích dữ liệu nhập, nhưng
không dùng làm khóa gom nhóm. Planner sử dụng `region_key`. Giờ mở cửa được đưa
ra khỏi `metadata`; ID của provider được lưu riêng trong `place_external_refs`.

### `source_documents`

Một record cho mỗi canonical URL. `artifacts` chứa caption/STT/OCR/webpage theo
language; `extracted_context` chứa observation chuẩn hóa. Hash, extractor
version và timestamps giữ provenance/freshness. Không lưu raw HTML hoặc raw
provider response.

### `knowledge_graph_imports`

Envelope dùng chung cho `explorer_job`, `explorer_intake` và admin
`knowledge_graph` import. `processing_status` độc lập với `review_status`; record
còn giữ source/chat/document reference, timing, retry và lỗi an toàn.

### `knowledge_graph_import_nodes`

Area/Venue proposal giữ alias quan sát, evidence, source note, Top-K candidates,
nullable `selected_entity_id`, `identity_status` và provider snapshot tối giản.
`branch_ambiguous` được Planner chọn theo route trong plan snapshot, không bind
toàn cục vào import node.

### `knowledge_graph_import_edges`

Giữ quan hệ đề xuất như `Venue LOCATED_IN Area`. Edge chỉ được promote sang
`knowledge_relationships` sau admin approval.

### `place_external_refs`

Lưu định danh địa điểm theo provider mà không làm domain `Place` phụ thuộc vào
payload riêng của provider.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `place_id` | FK `places.id` | Địa điểm chuẩn hóa |
| `provider` | varchar(64) | Tên provider |
| `external_id` | varchar(255) | ID của địa điểm tại provider |
| `fetched_at` | timestamptz | Thời điểm lấy dữ liệu |
| `confidence` | varchar(16) | `low`, `medium`, `high` |
| `attributes` | json | Thuộc tính được phép lưu, không chứa payload thô |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### Thống kê vùng cho Planner

Planner tính thống kê vùng trực tiếp từ catalog `places`; không còn lưu
`place_region_snapshots` hoặc `place_region_catalog_state`. Contract runtime vẫn
trả `RegionSnapshotReference`, nhưng `snapshotId` và `catalogVersion` được suy ra
xác định từ fingerprint của dữ liệu Place hiện tại. Reference này dùng để truy
vết planning run, không phải khóa ngoại tới một bảng snapshot.

`metrics` có thể chứa:

- số lượng theo `place_type` và `status`;
- `tagCounts`: số Place theo tag chuẩn hóa; một Place chỉ được tính một lần cho
  mỗi tag;
- `placeGroupCounts`: phân bố theo nhóm hoạt động cấp cao;
- `tagTimeCoverage`: độ phủ sáng, trưa, chiều và tối của từng tag;
- `tagDurationProfile`: thời lượng trung vị và cỡ mẫu theo tag;
- `indoorOutdoorMix`, `weatherSensitivityCounts` và
  `bookingRequirementCounts`;
- độ phủ hoạt động buổi sáng, trưa, chiều và tối;
- thời lượng điển hình theo loại địa điểm;
- số Place thiếu tọa độ, giờ mở cửa hoặc có dữ liệu cũ;
- tâm khu vực và bounding box;
- `areaProfiles`: hồ sơ các khu vực con nổi bật;
- `plannerSignals`: tag nổi trội, buổi mạnh/yếu, khu vực ứng viên và mức đa dạng
  hoạt động để Planner tạo `MacroPlan`/`DayBrief`.

Tag phải được chuẩn hóa và gộp alias trước khi đếm, ví dụ
`cafe, coffee_shop -> coffee` và `restaurant, food_drink -> food`. Một Place chỉ
được tính một lần cho mỗi tag chuẩn hóa. Tag không có dạng semantic như số điện
thoại hoặc chuỗi địa chỉ phải bị loại khỏi thống kê Planner.

Thống kê không chứa route chính xác giữa mọi cặp Place, giao thông hiện tại, thời
tiết, booking hoặc giá hiện tại. Finder và CheckOverall phải kiểm tra các dữ liệu
động này khi điền và kiểm tra plan.

### Luồng tự động thống kê Place

1. `PlaceCatalogService` thêm, sửa, đóng hoặc chuyển khu vực của Place và tăng
   `places.revision`.
2. Khi Planner yêu cầu một `region_key`, repository tính fingerprint từ các
   Place thuộc đúng khu vực đó và mọi `region_key` con.
3. Planner tính metrics trong memory và gắn fingerprint vào planning-run trace.
4. Thay đổi ở khu vực khác không đổi fingerprint của khu vực đang lập kế hoạch.

### `trips`

Lưu chuyến đi cá nhân do user tạo.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `owner_id` | FK `users.id` | Chủ trip |
| `title` | varchar | Tên trip |
| `destination` | varchar | Điểm đến chính |
| `start_date` | date, nullable | Ngày bắt đầu |
| `end_date` | date, nullable | Ngày kết thúc |
| `budget_amount` | integer, nullable | Số tiền theo đơn vị nhỏ nhất |
| `budget_currency` | varchar(3), nullable | ISO currency, ví dụ `VND` |
| `party_size` | integer | Số người |
| `status` | varchar | draft, generating, ready, archived |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `marketplace_plans`

Lưu listing/sản phẩm ổn định do creator đóng gói và bán. Nội dung hiển thị,
preview, giá và liên kết tới plan version của Planner nằm trong
`marketplace_plan_versions` để version đã publish hoặc đã bán không bị thay đổi.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `creator_id` | FK `users.id` | Người bán |
| `status` | varchar | draft, published, unpublished, retired |
| `current_published_version_id` | varchar, nullable | Version public hiện tại; service bảo vệ vì không tạo FK vòng |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `marketplace_plan_versions`

Snapshot bất biến của một listing. Đây là bảng quan trọng nhất cho Người C vì
checkout, entitlement và copy plan phải khóa đúng version đã mua.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Listing cha |
| `version` | integer | Số version theo từng listing |
| `source_plan_id` | varchar | Plan gốc do Planner quản lý; opaque vì Planner chưa có persistence |
| `source_plan_version_id` | varchar | Version plan gốc được publish |
| `title` | varchar | Tên listing/version |
| `description` | text | Nội dung mô tả public |
| `destination` | varchar | Điểm đến |
| `duration_days` | integer | Số ngày |
| `category` | varchar | Nhóm tìm kiếm/hiển thị |
| `price_amount` | integer | Giá theo đơn vị nhỏ nhất |
| `price_currency` | varchar(3) | ISO currency, mặc định `VND` |
| `media_urls` | json | URL ảnh/video public cho listing |
| `preview_snapshot` | json | Preview an toàn từ Planner tại thời điểm tạo version |
| `moderation_status` | varchar | draft, pending_review, approved, rejected, published |
| `rejection_reason` | text, nullable | Lý do admin từ chối |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |
| `published_at` | timestamptz, nullable | Thời điểm publish |

### `orders`

Lưu đơn mua plan.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `buyer_id` | FK `users.id` | Người mua |
| `total_amount` | integer | Tổng tiền |
| `currency` | varchar(3) | ISO currency |
| `status` | varchar | pending, paid, fulfilled, cancelled, refunded |
| `idempotency_key` | varchar, unique, nullable | Chống tạo checkout trùng |
| `provider_request_id` | varchar, unique, nullable | Request ID gửi tới provider thanh toán |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |
| `paid_at` | timestamptz, nullable | Thời điểm order được xác nhận paid |
| `refunded_at` | timestamptz, nullable | Thời điểm refund được xác nhận |

### `payments`

Lưu giao dịch thanh toán của order.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `order_id` | FK `orders.id` | Order được thanh toán |
| `provider` | varchar | Stripe, VNPay, Momo, manual |
| `method` | varchar | card, wallet, bank_transfer |
| `request_id` | varchar, unique, nullable | Request ID phía provider |
| `transaction_id` | varchar, unique | Mã giao dịch provider |
| `amount` | integer | Số tiền |
| `currency` | varchar(3) | ISO currency |
| `status` | varchar | pending, succeeded, failed, refunded |
| `payment_url` | text, nullable | URL redirect thanh toán sandbox/production |
| `paid_at` | timestamptz, nullable | Thời điểm thanh toán thành công |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `payment_events`

Lưu event/IPN từ provider để xử lý idempotent và phục vụ đối soát.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `payment_id` | FK `payments.id`, nullable | Payment liên quan nếu đã match được |
| `order_id` | FK `orders.id`, nullable | Order liên quan nếu đã match được |
| `provider` | varchar | momo, stripe, vnpay, manual |
| `provider_event_id` | varchar | Mã event hoặc khóa idempotency từ provider |
| `request_id` | varchar, nullable | Request ID trong payload |
| `transaction_id` | varchar, nullable | Transaction ID trong payload |
| `event_type` | varchar | Loại event |
| `payload` | json | Payload đã được kiểm tra và được phép lưu |
| `received_at` | timestamptz | Thời điểm nhận event |

### `reviews`

Review của buyer cho marketplace plan.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `reviewer_id` | FK `users.id` | Buyer viết review |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Plan được review |
| `marketplace_plan_version_id` | FK `marketplace_plan_versions.id`, nullable | Version được review |
| `order_id` | FK `orders.id`, nullable | Order chứng minh quyền review |
| `rating` | integer | 1 đến 5 |
| `comment` | text | Nội dung review |
| `status` | varchar | published, hidden, flagged |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `entitlements`

Quyền truy cập được cấp sau khi order/payment hợp lệ. Refund thu hồi entitlement
nhưng không xóa bản plan buyer đã copy.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `user_id` | FK `users.id` | Buyer sở hữu quyền |
| `order_id` | FK `orders.id` | Order cấp quyền |
| `order_item_id` | FK `order_items.id`, unique | Mỗi order item cấp tối đa một entitlement |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Listing đã mua |
| `marketplace_plan_version_id` | FK `marketplace_plan_versions.id` | Version đã mua |
| `status` | varchar | active, revoked, refunded |
| `copied_plan_id` | varchar, nullable | Plan copy do Planner tạo cho buyer |
| `copied_plan_version_id` | varchar, nullable | Version copy của buyer |
| `created_at` | timestamptz | Tạo lúc |
| `revoked_at` | timestamptz, nullable | Thời điểm thu hồi quyền |

### `reports`

Nội dung user báo cáo để admin xử lý.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `reporter_id` | FK `users.id` | Người báo cáo |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Listing bị báo cáo |
| `marketplace_plan_version_id` | FK `marketplace_plan_versions.id`, nullable | Version bị báo cáo |
| `reason` | varchar | Lý do báo cáo |
| `description` | text | Mô tả chi tiết |
| `status` | varchar | pending, reviewed, dismissed, resolved |
| `resolution` | text, nullable | Kết quả xử lý |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `audit_events`

Nhật ký hành động quan trọng như publish, payment, refund và admin review.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `actor_id` | FK `users.id`, nullable | User thực hiện hành động |
| `action` | varchar | Tên hành động |
| `resource_type` | varchar | Loại tài nguyên |
| `resource_id` | varchar, nullable | ID tài nguyên |
| `request_id` | varchar, nullable | Request ID để truy vết |
| `metadata` | json | Metadata an toàn, không chứa secret/token |
| `created_at` | timestamptz | Tạo lúc |

### `achievements`

Danh mục thành tựu/huy hiệu.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `code` | varchar, unique | Mã máy ổn định |
| `name` | varchar | Tên hiển thị |
| `description` | text | Mô tả |
| `badge_icon_url` | varchar, nullable | Icon huy hiệu |
| `criteria` | json | Điều kiện đạt được |
| `created_at` | timestamptz | Tạo lúc |

## Link tables

### `itinerary_items`

Liên kết `trips` với `places`, đồng thời lưu chi tiết lịch trình. Nên dùng bảng
này thay cho `trip_places` vì nó không chỉ nói "trip có place", mà còn mô tả
place nằm ở ngày nào, giờ nào, thứ tự nào.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `trip_id` | FK `trips.id` | Trip sở hữu item |
| `place_id` | FK `places.id`, nullable | Có thể null cho free-text item |
| `day_number` | integer | Ngày thứ mấy trong trip |
| `start_time` | time, nullable | Giờ bắt đầu local |
| `end_time` | time, nullable | Giờ kết thúc local |
| `sort_order` | integer | Thứ tự trong ngày |
| `cost_amount` | integer, nullable | Chi phí dự kiến |
| `cost_currency` | varchar(3), nullable | ISO currency |
| `notes` | text, nullable | Ghi chú |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `marketplace_plan_items`

Lưu itinerary mẫu của plan được bán.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Plan bán |
| `place_id` | FK `places.id`, nullable | Địa điểm trong mẫu |
| `day_number` | integer | Ngày thứ mấy |
| `start_time` | time, nullable | Giờ bắt đầu |
| `end_time` | time, nullable | Giờ kết thúc |
| `sort_order` | integer | Thứ tự trong ngày |
| `notes` | text, nullable | Ghi chú creator |

### `trip_members`

Liên kết user với trip.

| Column | Type | Notes |
| --- | --- | --- |
| `trip_id` | FK `trips.id` | Composite key |
| `user_id` | FK `users.id` | Composite key |
| `role` | varchar | owner, editor, viewer |
| `joined_at` | timestamptz | Thời điểm tham gia |

### `user_achievements`

Liên kết user với achievement.

| Column | Type | Notes |
| --- | --- | --- |
| `user_id` | FK `users.id` | Composite key |
| `achievement_id` | FK `achievements.id` | Composite key |
| `progress` | integer | Tiến độ hiện tại |
| `achieved_at` | timestamptz, nullable | Thời điểm đạt được |

### `user_visited_places`

Đánh dấu các địa điểm user xác nhận đã đi. Tọa độ hiển thị luôn lấy từ
`places`, không sao chép sang bảng liên kết.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string PK | Opaque ID |
| `user_id` | FK `users.id` | Chủ sở hữu dấu mốc |
| `place_id` | FK `places.id` | Địa điểm chuẩn hóa |
| `visited_at` | date | Ngày user đã đến |
| `note` | text, nullable | Ghi chú ngắn |
| `created_at` | timestamptz | Tạo lúc |

Unique `(user_id, place_id)`.

### `user_posts`

Bài viết dạng ảnh trên hồ sơ.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | string PK | Opaque ID |
| `user_id` | FK `users.id` | Tác giả |
| `caption` | text | Nội dung bài viết |
| `media_url` | varchar | URL media |
| `location_name` | varchar, nullable | Nhãn địa điểm hiển thị |
| `created_at` | timestamptz | Tạo lúc |

### `order_items`

Liên kết order với marketplace plan version đã mua. Đây là nơi khóa giá và
version tại thời điểm checkout.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `order_id` | FK `orders.id` | Order |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Plan được mua |
| `marketplace_plan_version_id` | FK `marketplace_plan_versions.id` | Version được mua |
| `unit_amount` | integer | Giá tại thời điểm mua |
| `currency` | varchar(3) | ISO currency |
| `quantity` | integer | Mặc định 1 |

### `favorites`

User lưu marketplace plan yêu thích.

| Column | Type | Notes |
| --- | --- | --- |
| `user_id` | FK `users.id` | Composite key |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Composite key |
| `created_at` | timestamptz | Tạo lúc |

## Quan hệ chính

```text
users 1--N trips
users N--N trips through trip_members
trips 1--N itinerary_items
places 1--N itinerary_items
places 1--N place_external_refs

users 1--N marketplace_plans
marketplace_plans 1--N marketplace_plan_versions
marketplace_plans 1--N marketplace_plan_items (planned)
places 1--N marketplace_plan_items (planned)

users 1--N orders
orders 1--N order_items
marketplace_plans 1--N order_items
marketplace_plan_versions 1--N order_items
orders 1--N payments
orders 1--N payment_events
orders 1--N entitlements

users 1--N reviews
marketplace_plans 1--N reviews
marketplace_plan_versions 1--N reviews
users N--N marketplace_plans through favorites
users 1--N reports
users 1--N audit_events

users N--N achievements through user_achievements
users N--N places through user_visited_places
users 1--N user_posts
```

## Index và constraint nên có

- `users.email` unique.
- `places`: index `region_key, status`; index `region_key, place_type, status`;
  index `source_fetched_at`; và nếu dùng Postgres thì cân nhắc geo index cho tọa
  độ.
- `place_external_refs`: unique `provider, external_id`; index `place_id`.
- `trips.owner_id`, `itinerary_items.trip_id`, `itinerary_items.place_id`.
- `itinerary_items`: unique mềm trên `trip_id, day_number, sort_order`.
- `trip_members`: primary key `trip_id, user_id`.
- `marketplace_plans.creator_id`, `marketplace_plans.status`,
  `marketplace_plans.current_published_version_id`.
- `marketplace_plan_versions`: unique `marketplace_plan_id, version`; index
  category, destination, price, moderation status, `source_plan_id` và
  `source_plan_version_id`.
- `marketplace_plan_items`: planned; nếu triển khai nên unique mềm trên
  `marketplace_plan_version_id, day_number, sort_order`.
- `orders.buyer_id`, `orders.status`.
- `order_items.order_id`, `order_items.marketplace_plan_id`,
  `order_items.marketplace_plan_version_id`.
- `payments.order_id`, `payments.request_id` unique,
  `payments.transaction_id` unique.
- `payment_events`: unique `provider, provider_event_id`; index `order_id`,
  `request_id`, `transaction_id`.
- `entitlements.order_item_id` unique; index user, order, status và version.
- `reviews`: unique `reviewer_id, marketplace_plan_id`.
- `reports`: index reporter, reason và status.
- `audit_events`: index actor, action, resource và request ID.
- `favorites`: primary key `user_id, marketplace_plan_id`.
- `achievements.code` unique.
- `user_achievements`: primary key `user_id, achievement_id`.

## Migration plan đề xuất

1. Thêm `places` và `place_external_refs`.
2. Tính thống kê vùng trực tiếp từ catalog `places` theo fingerprint.
3. Thêm `trips`, `trip_members`, `itinerary_items`.
4. Chuyển module `plans` từ in-memory repository sang SQLAlchemy repository và
   lưu snapshot Place đã dùng trong lần lập plan.
5. Đã thêm cụm Người C trong migration `20260727_0003`: `marketplace_plans`,
   `marketplace_plan_versions`, `favorites`, `orders`, `order_items`,
   `payments`, `payment_events`, `entitlements`, `reviews`, `reports` và
   `audit_events`.
6. Nếu cần query itinerary mẫu bằng SQL, thêm `marketplace_plan_items` theo
   `marketplace_plan_versions`, không theo listing gốc.
7. Thêm `achievements`, `user_achievements`.

Trong code hiện tại, bước 4 là điểm chuyển quan trọng nhất: `PlanRepository` đang
lưu trong memory, vì vậy dữ liệu plan sẽ mất khi backend restart.

## Công cụ thống kê Place hiện tại

Module `backend/app/modules/places/auto_statistics` dùng
`SqlAlchemyPlaceRepository` để đọc `places` từ PostgreSQL. Import CSV chỉ nằm ở
script biên `backend/scripts/import_places_to_postgres.py`, không phải repository
runtime. Create/update Place qua `PlaceCatalogService` chỉ tăng `revision` và
commit. Khi Planner yêu cầu một `region_key`, `auto_statistics` tính fingerprint
và metrics trực tiếp từ Place thuộc đúng khu vực đó và các vùng con. Thay đổi ở
khu vực khác không đổi fingerprint đang được yêu cầu.

Planner workflow đã gọi trực tiếp `get_for_planner(region_key)`. Contract nhận
`regionKey` chuẩn hóa; để tương thích request cũ, backend có thể chuẩn hóa
destination Việt Nam, ví dụ `Hà Nội` thành `vn,ha-noi`. Snapshot ID và version
được suy ra từ fingerprint và giữ trong internal trace/log của Planner; chúng
không tham chiếu row PostgreSQL.
