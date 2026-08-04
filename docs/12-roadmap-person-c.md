# Roadmap chi tiết Người C: Auth, Profile và Marketplace

## 1. Mục tiêu

Tài liệu này mô tả đầy đủ 31 task của Người C trong 6 tuần. Đây là kế hoạch
triển khai mục tiêu; các API và tính năng trong tài liệu chưa được xem là đã tồn
tại cho đến khi code, migration và test tương ứng được hoàn thành.

Người C sở hữu:

```text
Authentication
→ User/Profile
→ Phân quyền
→ Creator Marketplace
→ Buyer Marketplace
→ MoMo Sandbox
→ Order/Entitlement
→ Review/Report
→ Admin/Audit
```

Người C không sửa:

- Thu thập và phân tích URL của Người A.
- Explorer, Planner, Finder, Check và Backup Plan của Người B.
- Thuật toán tạo plan.
- Cấu trúc nội bộ của plan.

## 2. Quyết định kỹ thuật đã chốt

- Backend: FastAPI, SQLAlchemy, Alembic và PostgreSQL.
- Frontend: Next.js App Router.
- Auth: JWT trong HTTP-only cookie.
- Password: Argon2 qua `pwdlib`.
- JWT: `PyJWT`.
- Access token: 15 phút.
- Refresh token: 7 ngày, lưu hash session trong database và xoay vòng.
- Role: `traveler`, `creator`, `admin`.
- Traveler chính là buyer; creator vẫn có quyền mua plan.
- Payment: MoMo Sandbox, thanh toán một lần.
- Tiền được lưu bằng số nguyên VND.
- Published listing version là bất biến.
- API vẫn dùng thuật ngữ `listing`, nhưng database hiện dùng
  `marketplace_plans` cho listing ổn định và `marketplace_plan_versions` cho
  version bất biến.
- Plan version đã bán không thay đổi theo plan mới của creator.
- Refund thu hồi entitlement nhưng giữ bản plan buyer đã copy để không làm mất
  dữ liệu.
- Frontend gửi cookie bằng `credentials: "include"`.
- Request thay đổi dữ liệu phải có CSRF token, ngoại trừ IPN MoMo.

## 3. Quan hệ giữa ba thành viên

### Luồng tổng thể

```text
Người A                          Người B                         Người C
URL                              Planner                         Marketplace
 │                                  │                                │
 ├─ Import URL                      │                                │
 ├─ Trích xuất place candidate      │                                │
 ├─ User xác nhận địa điểm ────────>│                                │
 │                                  ├─ Tạo Main Plan                 │
 │                                  ├─ Check plan                    │
 │                                  ├─ Lưu Plan Version ────────────>│
 │                                  │                                ├─ Tạo listing
 │                                  │                                ├─ Publish
 │                                  │                                ├─ Buyer thanh toán
 │                                  │<──── Yêu cầu clone version ────┤
 │                                  ├─ Tạo plan copy ────────────────>│
 │                                  │                                └─ Trả plan copy cho buyer
```

Marketplace chỉ nhận kết quả plan đã chuẩn hóa. Nó không nhận URL, transcript,
raw provider payload hoặc place candidate từ Người A.

## 4. Phần cần thống nhất với Người A

### Người C cung cấp cho A

```python
get_current_user()
require_active_user()
require_role(...)
```

Thông tin user tối thiểu:

```json
{
  "id": 12,
  "email": "traveler@example.com",
  "fullName": "Nguyễn Minh Tuấn",
  "role": "traveler",
  "status": "active"
}
```

### Người A phải tuân thủ

- Mọi import riêng tư phải có `ownerId`.
- `ownerId` lấy từ JWT, không lấy từ request body.
- User không được đọc import của người khác.
- User bị `inactive` hoặc `banned` không được tạo import mới.
- Không tự xây thêm Auth hoặc giải mã JWT riêng.
- Không ghi URL riêng tư, token hoặc transcript đầy đủ vào audit log.
- Nếu import không thuộc user, trả `404` để không tiết lộ tài nguyên tồn tại.
- Nếu user đúng nhưng thiếu role, trả `403`.

### Điểm tích hợp

Người A không cần gọi API Marketplace. Điểm bàn giao của A kết thúc khi địa điểm
đã được user xác nhận và chuyển sang Planner của B.

## 5. Phần cần thống nhất với Người B

### Tại sao Marketplace cần Người B

Listing không được chứa một bản plan tự chế. Nó phải tham chiếu đúng một version
do Planner quản lý.

Người C cần B cung cấp:

- Plan thuộc creator nào.
- Version nào đang được chọn.
- Plan đã qua CheckOverall chưa.
- Plan có được phép publish không.
- Preview công khai được phép hiển thị.
- Cách tạo bản sao cá nhân cho buyer.

### Interface dùng chung

Đặt contract trung lập trong shared contracts để hai module cùng sử dụng:

```python
class PlanMarketplaceGateway(Protocol):
    def get_publish_info(
        self,
        plan_id: str,
        actor_id: int,
    ) -> PlanPublishInfo: ...

    def get_preview(
        self,
        plan_version_id: str,
    ) -> PlanPreview: ...

    def clone_for_buyer(
        self,
        plan_version_id: str,
        buyer_id: int,
        source_listing_version_id: str,
    ) -> PlanCopyResult: ...
```

### `PlanPublishInfo`

```json
{
  "planId": "plan_01",
  "planVersionId": "plan_version_03",
  "ownerId": 12,
  "title": "Đà Nẵng và Hội An 4 ngày",
  "destination": "Đà Nẵng",
  "days": 4,
  "status": "locked",
  "checkStatus": "valid"
}
```

Tác dụng:

- Xác nhận creator thật sự sở hữu plan.
- Khóa đúng plan version vào listing.
- Ngăn publish plan đang lỗi hoặc chưa hoàn thành.
- Không cho client tự gửi `ownerId`, `status` hoặc `checkStatus`.

### `PlanPreview`

```json
{
  "planVersionId": "plan_version_03",
  "title": "Đà Nẵng và Hội An 4 ngày",
  "destination": "Đà Nẵng",
  "days": 4,
  "highlights": ["Sơn Trà", "Hội An", "Ẩm thực địa phương"],
  "daySummaries": [
    {
      "day": 1,
      "theme": "Biển và trung tâm thành phố"
    }
  ]
}
```

Tác dụng:

- Hiển thị đủ thông tin để buyer ra quyết định.
- Không lộ toàn bộ item, route, ghi chú hoặc nội dung trả phí.
- Preview được snapshot vào listing version lúc publish.

### `PlanCopyResult`

```json
{
  "planId": "buyer_plan_18",
  "planVersionId": "buyer_plan_version_01",
  "sourcePlanVersionId": "plan_version_03",
  "sourceListingVersionId": "listing_version_07"
}
```

Tác dụng:

- Buyer nhận plan cá nhân.
- Plan mới có lifecycle riêng.
- Buyer chỉnh sửa không ảnh hưởng creator.
- Có thể truy vết plan được mua từ listing/version nào.

Trong database hiện tại, `sourceListingVersionId` tương ứng với
`marketplace_plan_versions.id`. Tên field trong API vẫn giữ trung lập để frontend
không cần biết tên bảng nội bộ.

### Quy tắc tích hợp với B

- C không import trực tiếp `PlanRepository`.
- C chỉ gọi `PlanMarketplaceGateway`.
- B không kiểm tra payment hoặc MoMo.
- C kiểm tra entitlement trước khi gọi clone.
- Chỉ `locked + valid` được submit listing.
- Listing đã publish vẫn giữ version cũ khi creator cập nhật plan.
- Nếu order refund, C không xóa plan copy đã tồn tại.
- Refund chỉ chặn tạo thêm copy từ entitlement đã thu hồi.
- C và B phải có contract test dùng fake gateway.

## 6. Quy ước API chung

### JSON

- Request/response bên ngoài dùng `camelCase`.
- Python nội bộ dùng `snake_case`.
- Thời gian dùng ISO 8601 UTC.
- Tiền dùng integer, ví dụ `149000`, không dùng `149.000`.
- ID là opaque string hoặc ID hiện có của user; frontend không tự phân tích ID.

### Response lỗi

```json
{
  "code": "LISTING_NOT_PUBLISHABLE",
  "message": "Plan chưa vượt qua kiểm tra.",
  "fieldErrors": {},
  "requestId": "req_01"
}
```

Mã HTTP:

- `400`: request không hợp lệ về luồng nghiệp vụ.
- `401`: chưa đăng nhập hoặc session hết hạn.
- `403`: đăng nhập nhưng không đủ quyền.
- `404`: tài nguyên không tồn tại hoặc không thuộc user.
- `409`: xung đột trạng thái/version/idempotency.
- `422`: payload sai schema.
- `429`: vượt rate limit.
- `502`: provider MoMo lỗi hoặc trả response không hợp lệ.

## 7. Giải thích API Auth và Profile

### `POST /api/auth/register`

Tác dụng:

- Tạo tài khoản traveler.
- Hash password.
- Tạo auth session.
- Set access, refresh và CSRF cookie.

Request:

```json
{
  "email": "user@example.com",
  "password": "MatKhauManh123!",
  "fullName": "Nguyễn Minh Tuấn"
}
```

Response `201`:

```json
{
  "user": {
    "id": 12,
    "email": "user@example.com",
    "fullName": "Nguyễn Minh Tuấn",
    "role": "traveler",
    "status": "active"
  }
}
```

Lỗi chính:

- `409 EMAIL_ALREADY_EXISTS`.
- `422 WEAK_PASSWORD`.
- `429 AUTH_RATE_LIMITED`.

### `POST /api/auth/login`

Tác dụng:

- Xác minh email/password.
- Tạo refresh session.
- Set cookie.
- Không trả JWT trong JSON.

Request:

```json
{
  "email": "user@example.com",
  "password": "MatKhauManh123!"
}
```

Lỗi email không tồn tại và sai password dùng chung `401 INVALID_CREDENTIALS` để
tránh lộ tài khoản.

### `POST /api/auth/refresh`

Tác dụng:

- Đọc refresh cookie.
- Kiểm tra session chưa bị thu hồi.
- Thu hồi refresh token cũ.
- Phát access và refresh token mới.
- Phát hiện token cũ bị tái sử dụng.

Không nhận request body.

### `POST /api/auth/logout`

Tác dụng:

- Thu hồi refresh session hiện tại.
- Xóa access, refresh và CSRF cookie.
- Gọi nhiều lần vẫn thành công.

Response: `204 No Content`.

### `GET /api/me`

Tác dụng:

- Frontend xác định user đang đăng nhập.
- Lấy role/status từ database.
- Không tin role cũ trong frontend.

### `PATCH /api/me/profile`

Tác dụng:

- Sửa `fullName`, `avatarUrl`, `bio`, `travelPreferences`.
- Không cho sửa role, status hoặc creator status.

### `POST /api/me/creator-application`

Tác dụng:

- Traveler gửi yêu cầu trở thành creator.
- Chuyển `creatorStatus` từ `none/rejected` sang `pending`.
- Không tự cấp role creator.

Request:

```json
{
  "bio": "Chuyên lịch trình ẩm thực miền Trung",
  "portfolioUrls": ["https://example.com/portfolio"]
}
```

## 8. Giải thích API Creator Marketplace

### `POST /api/creator/listings`

Tác dụng:

- Tạo listing draft từ plan hiện có.
- Gọi gateway của B để kiểm tra ownership.
- Tạo một dòng `marketplace_plans` nếu là listing mới.
- Tạo version draft trong `marketplace_plan_versions`.
- Snapshot `sourcePlanVersionId` và `previewSnapshot`.
- Chưa công khai listing.

Request:

```json
{
  "planId": "plan_01",
  "title": "Đà Nẵng và Hội An 4 ngày",
  "summary": "Lịch trình cân bằng giữa biển, phố cổ và ẩm thực.",
  "category": "food",
  "priceAmount": 149000,
  "currency": "VND",
  "mediaUrls": ["https://cdn.example.com/cover.jpg"]
}
```

Backend tự lấy:

- `ownerId`.
- `sourcePlanVersionId`.
- `checkStatus`.
- Preview từ Planner.

Mapping database:

- `marketplace_plans.creator_id` lấy từ JWT.
- `marketplace_plan_versions.source_plan_id` lấy từ request `planId`.
- `marketplace_plan_versions.source_plan_version_id` lấy từ Planner Gateway.
- `marketplace_plan_versions.preview_snapshot` lấy từ Planner Gateway.
- `marketplace_plan_versions.price_amount`, `price_currency`, `media_urls`,
  `category`, `title`, `description` lấy từ payload đã validate.

### `PATCH /api/creator/listings/{listingId}`

Tác dụng:

- Sửa draft listing.
- Chỉ owner được sửa.
- Không sửa trực tiếp published version.
- Nếu listing đã publish, tạo draft version mới.
- Draft version là dòng `marketplace_plan_versions` chưa published.

Request có `expectedVersion` để tránh hai tab ghi đè nhau.

Lỗi `409 VERSION_CONFLICT` khi dữ liệu đã được cập nhật ở nơi khác.

### `POST /api/creator/listings/{listingId}/submit`

Tác dụng:

- Kiểm tra creator đã verified.
- Kiểm tra đủ title, preview, category, media và giá.
- Gọi lại Planner gateway để bảo đảm plan vẫn publishable.
- Chuyển `marketplace_plan_versions.moderation_status` sang `pending_review`.

### `POST /api/creator/listings/{listingId}/publish`

Tác dụng:

- Creator phát hành version đã được admin approve.
- Listing xuất hiện trên Marketplace.
- Khóa listing version thành bất biến.
- Cập nhật `marketplace_plans.current_published_version_id`.
- Cập nhật `marketplace_plans.status=published`.

Chỉ được gọi khi trạng thái `approved`.

### `POST /api/creator/listings/{listingId}/unpublish`

Tác dụng:

- Ngừng bán listing.
- Không xóa order, entitlement hoặc version đã bán.
- Buyer cũ vẫn giữ quyền và plan copy.
- Cập nhật `marketplace_plans.status=unpublished`.

### `GET /api/creator/listings`

Tác dụng:

- Creator xem toàn bộ draft, pending, approved, published và rejected listing
  của mình.
- Trả số lượt xem, order và doanh thu gộp cơ bản.
- Response gom dữ liệu từ `marketplace_plans` và version mới nhất/current
  published trong `marketplace_plan_versions`.

## 9. Giải thích API Marketplace cho traveler

### `GET /api/listings`

Tác dụng:

- Tìm kiếm và lọc listing public.
- Chỉ trả `marketplace_plan_versions` được trỏ bởi
  `marketplace_plans.current_published_version_id`.
- Không trả nội dung plan đầy đủ.

Query:

```text
page
pageSize
query
category
minPrice
maxPrice
sort=newest|priceAsc|priceDesc|rating
```

### `GET /api/listings/{listingId}`

Tác dụng:

- Trả listing detail và preview.
- Nếu buyer có entitlement, response có thể thêm `hasAccess=true`.
- Không trả plan đầy đủ; plan được truy cập qua bản copy.
- `listingId` là `marketplace_plans.id`; `listingVersionId` là
  `marketplace_plan_versions.id`.

### `PUT /api/listings/{listingId}/favorite`

Tác dụng:

- Lưu listing vào danh sách yêu thích.
- Idempotent: gọi lại không tạo record trùng.

### `DELETE /api/listings/{listingId}/favorite`

Tác dụng:

- Bỏ yêu thích.
- Gọi khi chưa favorite vẫn trả thành công.

### `GET /api/me/favorites`

Tác dụng:

- Hiển thị danh sách listing user đã lưu.
- Chỉ trả listing còn public; record của listing bị ẩn vẫn được giữ nội bộ.
- `favorites.marketplace_plan_id` trỏ tới `marketplace_plans.id`, không trỏ tới
  từng version.

## 10. Giải thích API Order và MoMo

### `POST /api/checkout-sessions`

Tác dụng:

- Tạo order.
- Khóa listing version và giá từ database.
- Tạo `requestId` và chữ ký HMAC-SHA256.
- Gọi MoMo Sandbox.
- Trả `payUrl` cho frontend redirect.

Header bắt buộc:

```text
Idempotency-Key: checkout_...
```

Request:

```json
{
  "listingId": "listing_01",
  "listingVersionId": "listing_version_07"
}
```

Response:

```json
{
  "orderId": "order_01",
  "status": "pending",
  "amount": 149000,
  "currency": "VND",
  "paymentUrl": "https://test-payment.momo.vn/...",
  "expiresAt": "2026-08-01T10:15:00Z"
}
```

Client không được gửi amount, currency hoặc buyer ID.

Mapping database:

- `orders` lưu buyer, tổng tiền, idempotency key và provider request ID.
- `order_items.marketplace_plan_id` lưu listing gốc.
- `order_items.marketplace_plan_version_id` khóa version đã mua.
- `order_items.unit_amount` và `currency` được copy từ
  `marketplace_plan_versions`, không lấy từ client.

### `POST /api/payments/webhooks/momo`

Tác dụng:

- Nhận IPN server-to-server từ MoMo.
- Xác minh HMAC-SHA256.
- Đối chiếu `orderId`, `requestId`, `amount`, `partnerCode`.
- Lưu payment event.
- Chuyển order sang `paid` hoặc `failed`.
- Tạo entitlement đúng một lần.
- Dùng `payment_events` để chống xử lý IPN trùng.
- Dùng `entitlements.order_item_id` unique để chống cấp quyền trùng.

Endpoint:

- Không dùng JWT.
- Không dùng CSRF.
- Chỉ tin payload sau khi signature hợp lệ.
- Xử lý idempotent theo `requestId` và `transId`.
- Trả nhanh sau khi transaction database hoàn tất.

Redirect browser từ MoMo không được dùng để xác nhận order paid.

Chi tiết tích hợp phải bám
[MoMo Collection Link](https://developers.momo.vn/v3/vi/docs/payment/api/collection-link/)
và
[quy trình tích hợp chính thức](https://developers.momo.vn/v3/vi/docs/payment/onboarding/integration-process/).

### `GET /api/orders`

Tác dụng:

- Buyer xem lịch sử mua.
- Creator không dùng endpoint này để xem doanh thu listing của người khác.

### `GET /api/orders/{orderId}`

Tác dụng:

- Trang redirect sau MoMo dùng endpoint này để kiểm tra trạng thái thật.
- Chỉ buyer sở hữu order hoặc admin được xem.

### `POST /api/orders/{orderId}/copy`

Tác dụng:

- Kiểm tra order `paid`.
- Kiểm tra entitlement còn hiệu lực.
- Gọi `clone_for_buyer` của Người B.
- Lưu `copiedPlanId`.
- Gọi lại trả cùng plan copy, không tạo bản trùng.
- Lấy `source_plan_version_id` từ `marketplace_plan_versions`.
- Lưu kết quả copy vào `entitlements.copied_plan_id` và
  `entitlements.copied_plan_version_id`.

Response:

```json
{
  "planId": "buyer_plan_18",
  "sourcePlanVersionId": "plan_version_03",
  "sourceListingVersionId": "listing_version_07"
}
```

## 11. Giải thích API Review và Report

### `POST /api/listings/{listingId}/reviews`

Tác dụng:

- Cho buyer đã mua đánh giá listing.
- Mỗi buyer chỉ có một review cho một listing.
- Buyer có thể cập nhật review của mình.
- Order refunded không được tạo review mới.

Request:

```json
{
  "rating": 5,
  "comment": "Lịch trình rõ ràng và dễ sử dụng."
}
```

### `POST /api/listings/{listingId}/reports`

Tác dụng:

- Báo nội dung sai, vi phạm, lỗi thời hoặc lừa đảo.
- Tạo report cho admin xử lý.
- Không tự động gỡ listing chỉ vì có một report.

## 12. Giải thích API Admin

### `GET /api/admin/creator-applications`

Liệt kê creator application theo `pending`, `verified`, `rejected`.

### `POST /api/admin/creator-applications/{id}/review`

Tác dụng:

- Approve: đổi user thành creator và `creatorStatus=verified`.
- Reject: giữ traveler và lưu lý do.
- Tạo audit event.

### `GET /api/admin/listings/pending`

Trả listing đang chờ moderation và preview plan an toàn.

### `POST /api/admin/listings/{id}/review`

Request:

```json
{
  "decision": "approve",
  "reason": "Nội dung hợp lệ"
}
```

Tác dụng:

- Approve chuyển listing version sang `approved`.
- Reject chuyển sang `rejected` và lưu lý do.
- Admin không sửa nội dung creator.
- Cập nhật trên `marketplace_plan_versions.moderation_status`, không update trực
  tiếp nội dung version đã published.

### `GET /api/admin/reports`

Cho admin lọc report theo trạng thái, reason và listing.

### `POST /api/admin/reports/{id}/resolve`

Tác dụng:

- `dismiss`: đóng report.
- `unpublish`: ẩn listing.
- `requestChanges`: yêu cầu creator sửa.
- Luôn tạo audit event.

### `POST /api/admin/orders/{id}/refund`

Tác dụng:

- Kiểm tra order đang paid.
- Gọi refund adapter MoMo.
- Chỉ đánh dấu `refunded` sau xác nhận provider.
- Thu hồi entitlement.
- Không xóa plan copy buyer đã tạo.
- Chống refund lặp bằng idempotency key.

### `GET /api/admin/audit-events`

Tác dụng:

- Tìm hành động theo actor, action, resource và request ID.
- Không trả password, JWT, cookie hoặc secret MoMo.

## 13. Schema tối thiểu

| Thành phần | Tác dụng |
|---|---|
| `users` | Danh tính, password hash, role, trạng thái và hồ sơ |
| `auth_sessions` | Quản lý refresh token, logout và thu hồi session |
| `marketplace_plans` | Danh tính ổn định của listing/sản phẩm Marketplace |
| `marketplace_plan_versions` | Snapshot nội dung, plan version, preview và giá tại từng lần publish |
| `favorites` | Quan hệ user lưu `marketplace_plans` |
| `orders` | Buyer mua chính xác listing version nào với giá bao nhiêu |
| `order_items` | Khóa `marketplace_plan_version_id`, giá và currency tại thời điểm mua |
| `payments` | Giao dịch thanh toán cho order |
| `payment_events` | Chống xử lý IPN MoMo trùng và phục vụ đối soát |
| `entitlements` | Quyền truy cập được cấp sau payment |
| `reviews` | Rating/comment từ buyer đủ điều kiện |
| `reports` | Nội dung user báo cáo và trạng thái xử lý |
| `audit_events` | Truy vết publish, payment, refund và admin |

Các bảng trên đã có migration `20260727_0003_add_person_c_marketplace.py` và
SQLAlchemy model trong `backend/app/modules/marketplace/model.py`. Các bảng
`places`, `trips`, `itinerary_items` và plan persistence vẫn thuộc phần mục tiêu
của Người A/B, chưa phải điều kiện để triển khai API Listing tuần 3.

Các ràng buộc quan trọng:

- Unique email.
- Unique refresh `jti`.
- Unique favorite `(user_id, marketplace_plan_id)`.
- Unique listing version `(marketplace_plan_id, version)`.
- Unique provider event `(provider, provider_event_id)`.
- Unique payment `request_id` và `transaction_id`.
- Một entitlement cho một `order_item_id`.
- Một review cho `(reviewer_id, marketplace_plan_id)`.
- Published `marketplace_plan_versions` không update nội dung.
- `order_items.marketplace_plan_version_id` là version buyer đã mua; không suy
  luận lại từ `marketplace_plans.current_published_version_id`.

Mapping thuật ngữ:

```text
API listingId         -> marketplace_plans.id
API listingVersionId  -> marketplace_plan_versions.id
Planner planId        -> marketplace_plan_versions.source_plan_id
Planner planVersionId -> marketplace_plan_versions.source_plan_version_id
```

## 14. Thứ tự 31 task

> Tiến độ ngày 27/07/2026: C-01 đến C-11 đã được triển khai và kiểm tra. Migration
> `20260727_0003` đã tạo sẵn schema cho C-12 đến C-31. Service/API/FE cho C-12
> trở đi vẫn là kế hoạch mục tiêu, chưa được xem là tính năng đã tồn tại.

### Tuần 1: Auth

| ID | Task | Phụ thuộc | Kết quả |
|---|---|---|---|
| C-01 | Cấu hình pytest và database test | Không | Có test backend tự động |
| C-02 | Chốt Auth, role, error và ID contract | Cả nhóm | A/B dùng cùng quy ước |
| C-03 | Migration nâng cấp user | C-02 | Có password/status/profile |
| C-04 | Register/login/refresh/logout/me | C-03 | Auth backend hoàn chỉnh |
| C-05 | Dependency Auth/RBAC | C-04 | Bảo vệ endpoint dùng chung |
| C-06 | Test Auth và session | C-04, C-05 | Phủ happy/error flow |
| C-07 | Frontend Auth | C-04 | Đăng nhập và duy trì phiên |

### Tuần 2: Profile và contract

| ID | Task | Phụ thuộc | Kết quả |
|---|---|---|---|
| C-08 | Profile thật | C-05 | Loại bỏ profile demo |
| C-09 | Creator application | C-08 | Có onboarding creator |
| C-10 | Bàn giao Auth cho A/B | C-05 | Hai module dùng chung dependency |
| C-11 | Plan Marketplace Gateway | Người B | Khóa contract publish/copy |

### Tuần 3: Listing

| ID | Task | Phụ thuộc | Kết quả |
|---|---|---|---|
| C-12 | Tạo listing draft | C-09, C-11 | Draft gắn plan version |
| C-13 | Metadata, preview, media, giá | C-12 | Listing đủ dữ liệu bán |
| C-14 | Workflow moderation | C-13 | Transition trạng thái hợp lệ |
| C-15 | Listing version bất biến | C-14 | Không sửa version đã bán |
| C-16 | Search/filter/pagination | C-15 | API Marketplace public |
| C-17 | Explore dùng API thật | C-16 | Loại bỏ marketplace demo |
| C-18 | Favorite | C-16 | User lưu/bỏ lưu listing |

### Tuần 4: Payment

| ID | Task | Phụ thuộc | Kết quả |
|---|---|---|---|
| C-19 | Order và khóa giá | C-15 | Client không sửa amount/version |
| C-20 | MoMo provider adapter | C-19 | Tạo được payUrl sandbox |
| C-21 | IPN, query và idempotency | C-20 | Xử lý payment an toàn |
| C-22 | Entitlement | C-21 | Cấp quyền đúng một lần |
| C-23 | Copy plan đã mua | C-11, C-22 | Buyer có plan cá nhân |

### Tuần 5: Vận hành Marketplace

| ID | Task | Phụ thuộc | Kết quả |
|---|---|---|---|
| C-24 | Dashboard buyer/creator | C-19–C-23 | Không còn transaction demo |
| C-25 | Review | C-22 | Chỉ buyer hợp lệ đánh giá |
| C-26 | Report | C-15 | User báo cáo được listing |
| C-27 | Admin moderation/refund | C-09, C-14, C-21, C-26 | Admin xử lý được nghiệp vụ |
| C-28 | Audit | C-27 | Truy vết hành động quan trọng |

### Tuần 6: Hoàn thiện

| ID | Task | Phụ thuộc | Kết quả |
|---|---|---|---|
| C-29 | CSRF, rate limit, CORS và log | Các API chính | Hardening MVP |
| C-30 | Integration/E2E test | C-01–C-29 | Luồng Marketplace chạy tự động |
| C-31 | Docs, env, seed và demo | C-30 | Thành viên khác chạy được |

## 15. Kế hoạch test

- Register email trùng.
- Login sai password.
- Refresh token rotation và reuse.
- Logout nhiều lần.
- User banned không dùng API riêng tư.
- Traveler không tạo listing.
- Creator pending không submit listing.
- Creator không sửa listing người khác.
- Plan không valid không được publish.
- Published version không bị sửa.
- Search không lộ nội dung trả phí.
- Checkout không nhận giá từ client.
- MoMo signature sai không cập nhật order.
- IPN lặp không tạo entitlement trùng.
- Redirect giả không cấp quyền.
- Buyer chưa mua không copy được plan.
- Copy hai lần trả cùng plan.
- Buyer chưa mua không review được.
- Refund thu hồi entitlement nhưng giữ plan copy.
- Admin action luôn tạo audit.
- E2E toàn luồng creator → listing → MoMo → copy.

## 16. Tiêu chí nghiệm thu cuối

```text
Traveler đăng ký và đăng nhập
→ gửi creator application
→ admin duyệt creator
→ creator chọn plan valid của Người B
→ tạo listing draft
→ submit moderation
→ admin approve
→ creator publish
→ traveler khác tìm listing
→ tạo checkout MoMo Sandbox
→ backend nhận IPN hợp lệ
→ order chuyển paid
→ entitlement được cấp đúng một lần
→ buyer copy đúng plan version
→ mở plan copy trong Planner
→ creator update plan không làm đổi bản buyer đã mua
```

## 17. Ngoài phạm vi

- OAuth và social login.
- Email verification/quên mật khẩu qua email.
- Upload media; MVP chỉ nhận media URL hợp lệ.
- Payment production.
- Subscription và coupon.
- Tự động payout/disbursement cho creator.
- Notification realtime.
- Analytics nâng cao.
- Xóa plan copy sau refund.
- Thay đổi thuật toán URL hoặc Planner.

## 18. Rủi ro và phương án

- Người B chưa có plan persistence/version: C-11, C-12 và C-23 dùng fake gateway
  để phát triển song song.
- Chưa có credential MoMo: dùng fake payment provider trong test; sandbox smoke
  test chạy riêng.
- IPN local không truy cập được: dùng HTTPS tunnel và ghi hướng dẫn trong C-31.
- Tiến độ trễ: cắt dashboard nâng cao trước; không cắt Auth, authorization,
  signature, idempotency hoặc entitlement.
- Conflict giữa các nhánh: contract Auth và Plan Gateway phải được merge trước
  khi ba người phát triển module phụ thuộc.
