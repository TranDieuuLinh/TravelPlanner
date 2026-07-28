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
- `POST /api/plans/explore/full/intake`
- `POST /api/plans/main`
- `POST /api/plans/{planId}/backup`

Request Explorer intake dùng `multipart/form-data`. UI hiển thị một chat
composer duy nhất: người dùng nhập prompt hoặc dán URL vào cùng trường nội dung,
và đính kèm ảnh ngay trong composer. Backend chọn nhánh xử lý dựa trên dữ liệu
có mặt: OCR khi có ảnh, URL extraction khi tìm thấy URL, nếu không thì xử lý
prompt thường. Không dùng LLM để phân loại kiểu input.

Form fields:

- `rawRequest`: nội dung user nhập bắt buộc; có thể chứa prompt hoặc một hay
  nhiều URL. Ảnh là context bổ sung và không thay thế raw prompt.
- `destination`: tùy chọn; nếu thiếu backend suy luận từ `rawRequest`.
- `urls`: tùy chọn để tương thích client cũ; client mới dán URL trực tiếp vào
  `rawRequest` và backend tự trích xuất.
- `tripSpec`: tùy chọn; JSON object theo shape của Explorer `tripSpec`.
- `images`: tùy chọn; nhiều file ảnh JPEG, PNG, WebP, HEIC hoặc HEIF.

Input JSON của Explorer nhận `userState.travelStyle` để client truyền phong cách
du lịch người dùng, ví dụ `local`, `adventure`, `relaxation` hoặc một chuỗi mô
tả khác. Giá trị mặc định hiện tại là `local`.

Output tách địa điểm thành hai mảng. `placeCandidates` chứa điểm tham quan và
địa điểm không phải ăn uống; `foodPlaces` chứa item có category `food` hoặc
`cafe`. Backend chuẩn hóa lại hai mảng trước khi trả response để không trộn hai
nhóm. `ExploreResponse` không công khai dữ liệu chẩn đoán nội bộ `debug`.

Mỗi phần tử địa điểm có `category` với một trong các giá trị `attraction`,
`food`, `cafe`, `hotel`, `transport`, `free_time`, `other`. Khi evidence không
đủ để phân loại, backend dùng `other`:

```json
{
  "name": "Bánh mì Phượng",
  "category": "food",
  "placeId": null,
  "address": "Hội An",
  "source": "url_reel",
  "sourceUrl": "https://example.com/video",
  "confidence": 0.88,
  "priority": 1,
  "notes": "Được nhắc trong transcript"
}
```

`ExploreResponse.tripSpec.budget` dùng một envelope thống nhất cho cả mô tả định
tính và số tiền cụ thể. Các field include theo từng hạng mục không nằm trong
contract này:

```json
{
  "inputMode": "qualitative",
  "minAmount": 4300000,
  "targetAmount": 4800000,
  "maxAmount": 5400000,
  "currency": "VND",
  "isHardCap": false,
  "confidence": "medium",
  "calculationBasis": {
    "partySize": 2,
    "days": 3,
    "nights": 2,
    "destination": "Đà Nẵng",
    "priceTier": "budget"
  },
  "notes": "Ước tính từ mức chi tiêu thấp."
}
```

Nếu user chỉ nói thấp/trung bình/cao mà chưa có nguồn giá đủ tin cậy, Explorer
giữ `inputMode: "qualitative"` và để các amount là `null` thay vì bịa giá.
`isHardCap: true` bắt buộc có `maxAmount`.
`budgetLevel` và `calculationBasis.priceTier` chỉ nhận `budget`, `medium` hoặc
`high`; `balanced` chỉ dùng cho `pace`.

Request tạo plan chính:

```json
{
  "destination": "Ha Noi",
  "days": 3,
  "budget": "medium",
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
