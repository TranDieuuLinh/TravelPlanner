# Giao ước API

Base URL: `/api`. Các field trong JSON response sử dụng camelCase.

## Điểm cuối hiện tại

### Kiểm tra trạng thái

`GET /health`

```json
{"message": "ok"}
```

### Authentication và hồ sơ

- `POST /api/auth/register`: tạo traveler và set access/refresh/CSRF cookie.
- `POST /api/auth/login`: xác minh email/password và set cookie.
- `POST /api/auth/refresh`: rotate refresh session; yêu cầu CSRF header.
- `POST /api/auth/logout`: thu hồi refresh session và xóa cookie.
- `GET /api/me`: lấy user hiện tại.
- `PATCH /api/me/profile`: sửa hồ sơ; yêu cầu CSRF header.
- `POST /api/me/creator-application`: gửi yêu cầu creator; yêu cầu CSRF header.

Request đăng ký:

```json
{
  "email": "traveler@example.com",
  "password": "MatKhauManh123",
  "fullName": "Nguyen An"
}
```

JWT không được trả trong JSON. Backend lưu access/refresh token trong HTTP-only
cookie và lưu refresh token dạng hash trong `auth_sessions`. Request thay đổi dữ
liệu gửi cookie phải đặt `X-CSRF-Token` bằng giá trị cookie `vsf_csrf`.

`GET /api/users` và `POST /api/users` được giữ cho quản trị; cả hai yêu cầu role
admin, và `POST` yêu cầu CSRF. Đăng ký public chỉ đi qua `/api/auth/register`,
client không được tự chọn role.

### Lịch trình

- `GET /api/plans/feature-map`
- `POST /api/plans/explore`
- `POST /api/plans/main`
- `POST /api/plans/{planId}/backup`

Request tạo plan chính:

```json
{
  "destination": "Ha Noi",
  "days": 3,
  "budget": "balanced",
  "travelStyle": "local",
  "pace": "balanced",
  "interests": ["food", "coffee"],
  "mustVisitPlaces": ["Hoan Kiem Lake"],
  "avoidPlaces": [],
  "constraints": ["not too dense"],
  "selectedPlaces": []
}
```

Plan hiện bị mất khi tiến trình backend khởi động lại. Request tạo plan dự phòng
chỉ hoạt động khi plan chính vẫn còn trong bộ nhớ của cùng tiến trình.

### Điểm cuối minh họa/tạm thời

- `GET /api/marketplace/categories`

Đây chưa phải contract production.

## Quy ước cho API mới

- Resource path dùng danh từ số nhiều.
- ID là chuỗi opaque, client không suy luận cấu trúc bên trong.
- Timestamp dùng ISO 8601 UTC; item trong lịch trình phải giữ thêm timezone địa
  phương.
- Tiền dùng dạng `{ "amount": 100000, "currency": "VND" }`.
- Phân trang dùng cursor và thứ tự ổn định.
- Lỗi validation chỉ rõ field và mã máy ổn định.
- Thao tác thay đổi dữ liệu có thể retry phải nhận `Idempotency-Key`.
- Job chạy lâu trả `202 Accepted` kèm job resource.
- Chỉnh sửa optimistic gửi version hoặc ETag và trả `409` khi xung đột.

Cấu trúc lỗi chuẩn của các module mới:

```json
{
  "code": "VERSION_CONFLICT",
  "message": "Dữ liệu đã được cập nhật bởi một phiên làm việc khác.",
  "fieldErrors": {},
  "requestId": "req_..."
}
```

Backend trả cùng request ID trong header `X-Request-ID`. Validation trả
`VALIDATION_ERROR`; chưa đăng nhập trả `AUTHENTICATION_REQUIRED`; sai role trả
`INSUFFICIENT_ROLE`.

## Contract liên module đã triển khai

`PlanMarketplaceGateway` là protocol Python dùng giữa module Planner và
Marketplace trong modular monolith. Đây không phải HTTP endpoint và không cho
Marketplace truy cập trực tiếp `PlanRepository`.

- `get_publish_info(planId, actorId)`: xác minh ownership, version và trạng thái
  publishable.
- `get_preview(planVersionId)`: trả snapshot preview an toàn.
- `clone_for_buyer(planVersionId, buyerId, sourceListingVersionId)`: tạo bản sao
  buyer độc lập.

Hiện protocol, schema và fake contract test đã có; implementation persistence và
version phía Planner vẫn là phần Người B cần hoàn thành trước Listing.

## Nhóm tài nguyên mục tiêu của MVP

- `/auth`, `/me`, `/users`
- `/trips`, `/trips/{id}/versions`, `/trips/{id}/members`
- `/imports`, `/imports/{id}/candidates`, `/planning-jobs`, `/places`, `/routes`
- `/listings`, `/creators`, `/favorites`
- `/checkout-sessions`, `/orders`, `/payments/webhooks`
- `/reviews`, `/reports`
- `/admin/*`

Mỗi endpoint phải được mô tả trong OpenAPI sinh tự động và có ví dụ
request/response. Khi contract thay đổi, phải cập nhật schema frontend và test
trong cùng thay đổi.

## Contract mục tiêu: nhập URL

- `POST /api/imports`: tạo import job cho một URL thuộc trip.
- `GET /api/imports/{importId}`: lấy trạng thái, tiến độ và lỗi.
- `GET /api/imports/{importId}/candidates`: lấy claim/place candidate.
- `POST /api/imports/{importId}/candidates/{candidateId}/confirm`: xác nhận place.
- `POST /api/imports/{importId}/retry`: retry từ bước lỗi phù hợp.
- `DELETE /api/imports/{importId}`: bỏ nguồn khỏi draft theo quy tắc provenance.

Request:

```json
{
  "tripId": "trip_...",
  "url": "https://www.tiktok.com/@creator/video/...",
  "clientRequestId": "client_..."
}
```

Response `202 Accepted`:

```json
{
  "importId": "imp_...",
  "status": "queued",
  "sourceType": "tiktok",
  "progress": {"stage": "queued", "percent": 0},
  "createdAt": "2026-07-27T08:00:00Z"
}
```

Place candidate không được chỉ trả tên tự do:

```json
{
  "id": "candidate_...",
  "rawName": "Tiệm cà phê Túi Mơ To",
  "claimType": "place",
  "confidence": 0.86,
  "evidence": {
    "artifactType": "transcript",
    "excerpt": "đoạn bằng chứng ngắn được phép hiển thị",
    "timestampSeconds": 42
  },
  "matches": [
    {
      "placeId": "place_...",
      "displayName": "Tiệm cà phê Túi Mơ To",
      "address": "Đà Lạt, Lâm Đồng",
      "confidence": 0.92
    }
  ],
  "reviewStatus": "needsConfirmation"
}
```

Xác nhận candidate phải nhận `placeId`, lựa chọn loại bỏ hoặc dữ liệu sửa thủ
công. API không được coi candidate đầu tiên là lựa chọn của user.

## Contract mục tiêu: tạo và chỉnh sửa plan

- `POST /api/trips/{tripId}/explore`: xác định câu hỏi còn thiếu.
- `POST /api/trips/{tripId}/plans`: tạo planning job từ input đã xác nhận.
- `GET /api/planning-jobs/{jobId}`: trạng thái từng stage.
- `GET /api/trips/{tripId}/plans/{planId}`: lấy plan, source và check report.
- `PATCH /api/trips/{tripId}/plans/{planId}/items/{itemId}`: sửa/khóa item.
- `POST /api/trips/{tripId}/plans/{planId}/revisions`: AI sửa theo phạm vi.
- `POST /api/trips/{tripId}/plans/{planId}/checks`: kiểm tra lại plan/version.
- `POST /api/trips/{tripId}/plans/{planId}/backups`: tạo Backup Plan riêng.
- `POST /api/trips/{tripId}/plans/{planId}/versions`: tạo snapshot.

Request tạo planning job tham chiếu ID, không gửi lại payload nguồn thô:

```json
{
  "selectedPlaceIds": ["selected_place_1", "selected_place_2"],
  "startDate": "2026-10-20",
  "days": 3,
  "timezone": "Asia/Ho_Chi_Minh",
  "budget": {"amount": 5000000, "currency": "VND"},
  "pace": "balanced",
  "interests": ["food", "coffee"],
  "hardConstraints": ["avoidStairs"],
  "lockedItemIds": []
}
```

Planning job phải công bố stage như `exploring`, `planning`, `finding`,
`checking` và `creatingBackup`. Kết quả plan phải phân biệt:

- `selectedPlaces`: địa điểm user đã xác nhận;
- `scheduledItems`: item đã được xếp;
- `unscheduledPlaces`: địa điểm chưa xếp cùng reason code;
- `assumptions` và `warnings`;
- `checkReport`;
- `sourceRefs` thay vì sao chép toàn bộ nội dung nguồn.

## Contract mục tiêu: Marketplace

- `POST /api/creator/listings`: tạo listing draft từ một plan version đã kiểm tra.
- `POST /api/creator/listings/{listingId}/submit`: gửi kiểm duyệt.
- `POST /api/creator/listings/{listingId}/publish`: publish version bất biến.
- `GET /api/listings`: tìm kiếm, lọc và phân trang listing.
- `GET /api/listings/{listingId}`: trả preview theo quyền hiện tại.
- `POST /api/checkout-sessions`: tạo checkout cho listing version cụ thể.
- `POST /api/payments/webhooks/{provider}`: nhận và xác minh payment event.
- `GET /api/orders/{orderId}`: lấy trạng thái order/entitlement.
- `POST /api/orders/{orderId}/copy`: tạo TripPlan cá nhân từ version đã mua.
- `POST /api/listings/{listingId}/reviews`: review từ buyer đủ điều kiện.
- `POST /api/listings/{listingId}/reports`: báo cáo listing/version.

Checkout request phải khóa version và số tiền phía server:

```json
{
  "listingId": "listing_...",
  "listingVersionId": "listing_version_...",
  "returnUrl": "https://app.example.com/orders/order_..."
}
```

Client không được quyết định `amount`, `currency`, plan version hoặc entitlement.
Sau payment, bản sao cá nhân phải giữ `sourceListingVersionId` và
`sourcePlanVersionId`, nhưng có lifecycle/version riêng để Planner chỉnh sửa.
