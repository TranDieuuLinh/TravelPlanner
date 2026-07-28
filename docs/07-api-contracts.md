# Giao ước API

Base URL: `/api`. Các field trong JSON response sử dụng camelCase.

## Điểm cuối hiện tại

### Kiểm tra trạng thái

`GET /health`

```json
{"message": "ok"}
```

### Người dùng

- `GET /api/users`
- `POST /api/users`

Request tạo user:

```json
{
  "email": "traveler@example.com",
  "fullName": "Nguyen An",
  "role": "traveler",
  "avatarUrl": null,
  "travelPreferences": ["food", "local"]
}
```

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

- `POST /api/profiles/planner-preview`
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

Cấu trúc lỗi chuẩn:

```json
{
  "error": {
    "code": "PLAN_VERSION_CONFLICT",
    "message": "Plan đã được cập nhật bởi một phiên làm việc khác.",
    "details": {"currentVersion": 7},
    "requestId": "req_..."
  }
}
```

## Nhóm tài nguyên mục tiêu của MVP

- `/auth`, `/me`, `/users`
- `/trips`, `/trips/{id}/versions`, `/trips/{id}/members`
- `/imports`, `/planning-jobs`, `/places`, `/routes`
- `/listings`, `/creators`, `/favorites`
- `/checkout-sessions`, `/orders`, `/payments/webhooks`
- `/reviews`, `/reports`
- `/admin/*`

Mỗi endpoint phải được mô tả trong OpenAPI sinh tự động và có ví dụ
request/response. Khi contract thay đổi, phải cập nhật schema frontend và test
trong cùng thay đổi.
