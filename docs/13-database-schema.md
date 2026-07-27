# Database schema

Tài liệu này mô tả database mục tiêu cho VSF Travel dựa trên codebase hiện tại và
danh sách bảng chính đã chốt. Trạng thái hiện tại: codebase mới triển khai thật
bảng `users` qua SQLAlchemy/Alembic; các bảng còn lại là schema mục tiêu để thêm
migration và model trong các bước tiếp theo.

## Trạng thái triển khai

| Table | Status | Nguồn trong codebase |
| --- | --- | --- |
| `users` | Implemented | `backend/app/modules/users/model.py`, migration `20260727_0001_create_users_table.py` |
| `places` | Planned | Cần thêm module/model |
| `trips` | Planned | Liên quan module `plans` hiện đang dùng Pydantic/in-memory |
| `itinerary_items` | Planned | Nên dùng thay `trip_places` vì lưu được lịch trình chi tiết |
| `trip_members` | Planned | Cần cho chia sẻ trip |
| `marketplace_plans` | Planned | Module marketplace hiện mới có endpoint placeholder |
| `marketplace_plan_items` | Planned | Lưu itinerary mẫu của plan bán |
| `orders` | Planned | Cần cho checkout |
| `order_items` | Planned | Cho phép một order mua nhiều plan |
| `payments` | Planned | Giao dịch thanh toán của order |
| `reviews` | Planned | Review từ buyer cho marketplace plan |
| `favorites` | Planned | User lưu marketplace plan yêu thích |
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
| `travel_preferences` | json | Sở thích du lịch |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

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
| `latitude` | decimal, nullable | Tọa độ |
| `longitude` | decimal, nullable | Tọa độ |
| `metadata` | json | Giờ mở cửa, provider IDs, tags |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

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

Lưu plan do creator đóng gói và bán.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `creator_id` | FK `users.id` | Người bán |
| `title` | varchar | Tên listing/plan |
| `description` | text | Nội dung mô tả |
| `destination` | varchar | Điểm đến |
| `duration_days` | integer | Số ngày |
| `price_amount` | integer | Giá theo đơn vị nhỏ nhất |
| `price_currency` | varchar(3) | ISO currency |
| `status` | varchar | draft, published, paused, retired |
| `version` | integer | Version publish |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `orders`

Lưu đơn mua plan.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `buyer_id` | FK `users.id` | Người mua |
| `total_amount` | integer | Tổng tiền |
| `currency` | varchar(3) | ISO currency |
| `status` | varchar | pending, paid, fulfilled, cancelled, refunded |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

### `payments`

Lưu giao dịch thanh toán của order.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `order_id` | FK `orders.id` | Order được thanh toán |
| `provider` | varchar | Stripe, VNPay, Momo, manual |
| `method` | varchar | card, wallet, bank_transfer |
| `transaction_id` | varchar, unique | Mã giao dịch provider |
| `amount` | integer | Số tiền |
| `currency` | varchar(3) | ISO currency |
| `status` | varchar | pending, succeeded, failed, refunded |
| `paid_at` | timestamptz, nullable | Thời điểm thanh toán thành công |
| `created_at` | timestamptz | Tạo lúc |

### `reviews`

Review của buyer cho marketplace plan.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `user_id` | FK `users.id` | Buyer viết review |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Plan được review |
| `order_id` | FK `orders.id`, nullable | Order chứng minh quyền review |
| `rating` | integer | 1 đến 5 |
| `content` | text | Nội dung review |
| `creator_reply` | text, nullable | Phản hồi của creator |
| `created_at` | timestamptz | Tạo lúc |
| `updated_at` | timestamptz | Cập nhật lúc |

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

### `order_items`

Liên kết order với marketplace plans.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | uuid/string PK | Opaque ID |
| `order_id` | FK `orders.id` | Order |
| `marketplace_plan_id` | FK `marketplace_plans.id` | Plan được mua |
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

users 1--N marketplace_plans
marketplace_plans 1--N marketplace_plan_items
places 1--N marketplace_plan_items

users 1--N orders
orders 1--N order_items
marketplace_plans 1--N order_items
orders 1--N payments

users 1--N reviews
marketplace_plans 1--N reviews
users N--N marketplace_plans through favorites

users N--N achievements through user_achievements
```

## Index và constraint nên có

- `users.email` unique.
- `places` nên index theo `place_type`, `city`, và nếu dùng Postgres thì cân nhắc
  geo index cho tọa độ.
- `trips.owner_id`, `itinerary_items.trip_id`, `itinerary_items.place_id`.
- `itinerary_items`: unique mềm trên `trip_id, day_number, sort_order`.
- `trip_members`: primary key `trip_id, user_id`.
- `marketplace_plans.creator_id`, `marketplace_plans.status`.
- `marketplace_plan_items`: unique mềm trên `marketplace_plan_id, day_number, sort_order`.
- `orders.buyer_id`, `orders.status`.
- `order_items.order_id`, `order_items.marketplace_plan_id`.
- `payments.order_id`, `payments.transaction_id` unique.
- `reviews`: cân nhắc unique `user_id, marketplace_plan_id` hoặc
  `user_id, order_id, marketplace_plan_id` tùy business rule.
- `favorites`: primary key `user_id, marketplace_plan_id`.
- `achievements.code` unique.
- `user_achievements`: primary key `user_id, achievement_id`.

## Migration plan đề xuất

1. Thêm `places`.
2. Thêm `trips`, `trip_members`, `itinerary_items`.
3. Chuyển module `plans` từ in-memory repository sang SQLAlchemy repository.
4. Thêm `marketplace_plans`, `marketplace_plan_items`, `favorites`.
5. Thêm `orders`, `order_items`, `payments`.
6. Thêm `reviews`.
7. Thêm `achievements`, `user_achievements`.

Trong code hiện tại, bước 3 là điểm chuyển quan trọng nhất: `PlanRepository` đang
lưu trong memory, vì vậy dữ liệu plan sẽ mất khi backend restart.
