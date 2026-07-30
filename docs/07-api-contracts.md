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
- `POST /api/plans/explore/full/intake`
- `POST /api/plans/main`
- `POST /api/plans/main/from-explorer`
- `POST /api/plans/main/from-context`
- `POST /api/plans/{planId}/backup`

### Trip chat và lịch sử chỉnh sửa

Các endpoint sau yêu cầu đăng nhập; thao tác POST yêu cầu CSRF:

- `POST /api/trip-chats`: tạo một chat riêng cho một chuyến đi.
- `GET /api/trip-chats`: liệt kê chat của user hiện tại, mới cập nhật trước.
- `GET /api/trip-chats/{chatId}`: lấy message history, Explorer context và plan
  hiện tại.
- `POST /api/trip-chats/{chatId}/messages`: gửi yêu cầu đầu tiên hoặc sửa plan
  hiện tại.

Request gửi message dùng `multipart/form-data`:

- `content`: yêu cầu mới của user;
- `expectedRevision`: revision client đang hiển thị;
- `urls`: URL lặp lại tùy chọn; URL trong `content` cũng được tự trích xuất;
- `images`: ảnh tùy chọn.

Lần gửi đầu tạo plan revision 1. Các lần sau cung cấp lịch sử user request và
Explorer context hiện tại cho Planner, giữ các yêu cầu cũ trừ khi message mới
thay đổi chúng, và dùng item của plan hiện tại làm đầu vào cho revision. Kết quả
ghi đè con trỏ `currentPlan` nhưng giữ nguyên `currentPlan.id`; snapshot cũ vẫn
ở `trip_chat_plan_revisions`.

Response detail:

```json
{
  "id": "chat_uuid",
  "title": "Chuyến đi Hà Nội",
  "destination": "Hà Nội",
  "revision": 2,
  "hasPlan": true,
  "currentPlan": {},
  "currentExplorer": {},
  "messages": [
    {
      "id": "message_uuid",
      "role": "user",
      "content": "Thêm cà phê vào ngày 2",
      "attachmentNames": [],
      "planRevision": 2,
      "createdAt": "2026-07-30T07:00:00Z"
    }
  ],
  "createdAt": "2026-07-30T06:00:00Z",
  "updatedAt": "2026-07-30T07:00:00Z"
}
```

Nếu `expectedRevision` đã cũ, backend trả HTTP 409 với code
`VERSION_CONFLICT`. Lookup luôn lọc đồng thời `chatId + currentUser.id`; tài
khoản khác nhận `TRIP_CHAT_NOT_FOUND`.

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
- `userState`: tùy chọn; JSON object gồm locale, timezone, travelStyle và
  travelPreferences. Khi đã đăng nhập, backend tự lấy `userId` và preference
  profile từ session/database, không tin `userId` do client khai báo.
- `images`: tùy chọn; nhiều file ảnh JPEG, PNG, WebP, HEIC hoặc HEIF.

Input JSON của Explorer nhận `userState.travelStyle` để client truyền phong cách
du lịch người dùng, ví dụ `local`, `adventure`, `relaxation` hoặc một chuỗi mô
tả khác. Giá trị mặc định hiện tại là `local`.

Output công khai chỉ chứa `intakeId`, `userId` và JSON `explorer` với intent,
tripSpec, assumptions, missingInfoQuestions và `preferenceSnapshot`.
`preferenceSnapshot.signals` là tín hiệu ngắn hạn của intake;
`effectiveProfile` là profile đã merge để Planner dùng. `placeCandidates` là contract
nội bộ giữa extractor, aggregator, resolver và repository; không trả cho client.

Không công khai raw OCR, transcript, URL result hoặc debug. Backend tự động gộp
candidate trùng, giữ mọi source URL, resolve place và lưu toàn bộ kết quả chỉ
vào PostgreSQL table `user_must_place`. Flow này không ghi vào `places` và không
lưu Explorer context.

Mỗi phần tử địa điểm có `category` với một trong các giá trị `attraction`,
`food`, `cafe`, `hotel`, `transport`, `free_time`, `nature`, `culture`,
`shopping`, `nightlife`, `wellness`, `adventure`, `beach`, `family`, `other`.
Candidate có thể có `attributes` chuẩn hóa và mặc định
`preferenceLevel=preferred`. Khi evidence không
đủ để phân loại, backend dùng `other`:

```json
{
  "name": "Bánh mì Phượng",
  "category": "food",
  "addressHint": "Hội An",
  "searchRegion": "Hội An",
  "sources": [
    {
      "type": "url",
      "url": "https://example.com/video"
    }
  ],
  "confidence": 0.88,
  "priority": 1,
  "preferenceLevel": "preferred",
  "attributes": ["local", "budget"],
  "notes": "Được nhắc trong transcript",
  "sourceEvidence": {
    "stt": "On day two, we ate here.",
    "ocr": "Bánh mì Phượng"
  }
}
```

`destination`/trip base và `searchRegion` có nghĩa khác nhau. Một itinerary có
thể giữ trip base là Hà Nội nhưng gán `searchRegion=Ninh Bình` cho toàn bộ stop
Day 2 sau khi STT nói rõ đây là day trip Ninh Bình. Resolver tìm theo
`candidateName + addressHint + searchRegion`, lưu riêng `resolvedName` và
`resolutionReason`; tên provider không ghi đè tên nguồn của stop URL.

Response tổng quát:

```json
{
  "intakeId": "uuid",
  "userId": "user-uuid",
  "explorer": {
    "intent": {},
    "tripSpec": {},
    "assumptions": [],
    "missingInfoQuestions": [],
    "preferenceSnapshot": {
      "version": 1,
      "signals": [],
      "effectiveProfile": {
        "version": 1,
        "explicit": [],
        "scores": {},
        "observationCount": 0
      }
    }
  }
}
```

`explorer.tripSpec.budget` là vị trí duy nhất chứa ngân sách:

```json
{
  "targetAmount": 6000000,
  "currency": "VND",
  "level": "medium"
}
```

`targetAmount` luôn là số tiền gần đúng; khi user không nêu số tiền, giá trị là
`null`. `currency` là mã ISO 4217 gồm ba chữ cái viết hoa. `level` chỉ nhận
`low`, `medium` hoặc `high`. Contract không có `inputMode`, khoảng min/max,
hard-cap, confidence hay calculation
basis, và không lặp `budgetLevel` trong `intent`.

`POST /api/plans/main/from-explorer` nối kết quả Explorer vào Planner/Finder.
Request gồm `intent`, `tripSpec`, `intakeId`, `userId`, `selectedPlaces` và
`allowFinderSuggestions`.
Service merge `selectedPlaces` explicit với các candidate đã tự động lưu theo
đúng `intakeId + userId`. Candidate chưa được user xác nhận vẫn giữ
`preferenceLevel=preferred`, confidence và provenance; không được đổi thành
`mustVisit` ngầm.

Explorer trả `allowFinderSuggestions=false` khi intake có URL/ảnh/OCR và nguồn
đã phủ duration hiệu lực. Nếu user nói rõ số ngày dài hơn coverage nguồn,
Explorer trả `true`; Finder vẫn chỉ tìm catalog cho ngày trống, không thêm vào
ngày đã có stop URL/OCR. Prompt thuần trả `true` cho mọi ngày.

Nếu intake URL/OCR không có `tripSpec.days` explicit, Explorer suy ra số ngày từ
`sourceDay`; nếu nguồn không gán ngày, dùng số ngày tối thiểu theo số stop và
pace để không làm mất stop. Giá trị user nói rõ luôn được giữ nguyên.

Với itinerary từ URL, phần tử `selectedPlaces` có thể có `sourceOrder`,
`sourceDay`, `sourceTimeHint`, `sourceActivity` và
`sourceDurationMinutes`; khi resolve được còn có `address`, `latitude` và
`longitude`. `PlanItem` trả lại cùng địa chỉ/tọa độ để UI hiển thị và đặt marker.
Planner/Finder ưu tiên blueprint URL và giữ thứ tự nguồn. Hard constraint
explicit vẫn thắng; timing cue không được mô tả như giờ hoạt động đã xác minh.

Request còn nhận `preferenceProfile` từ
`explorer.preferenceSnapshot.effectiveProfile`. Plan day trả `transportLegs`
với thứ tự đã tối ưu nearest-neighbour + 2-opt. Finder lấy route pedestrian/car
từ HERE Routing v8 cho từng cặp stop. Leg thành công có
`source=here_routing_v8`, `verified=true`, `fetchedAt` và geometry theo đường;
provider lỗi hoặc thiếu credential fallback thành `source=geodesic_estimate`,
`verified=false`. Route HERE hiện dùng `departureTime=any`, vì vậy
`verified=true` không được mô tả là dữ liệu traffic live.

Khi `tripSpec.startDate` có giá trị, Finder còn gọi HERE Public Transit theo
ngày của `PlanDay` và giờ kết thúc item đầu. Route có ít nhất một transit section
mới được nhận; route chỉ đi bộ do Transit API trả thêm bị loại. Nếu
`tripSpec.transport.preferredModes` chứa `bus` hoặc `train`, transit khả thi trở
thành leg chính. Nếu không, nó xuất hiện trong `transportLeg.alternatives`.
`avoidModes` loại mode tương ứng trước khi chọn. Transit option có
`source=here_transit_v8`, geometry, duration gồm cả thời gian chờ và
`details.transitModes`/`details.lines`.

Request tạo plan chính:

```json
{
  "intakeId": "uuid-từ-explorer",
  "userId": "user-uuid",
  "explorer": {
    "intent": {},
    "tripSpec": {},
    "assumptions": [],
    "missingInfoQuestions": []
  }
}
```

Khi upstream đã có output chuẩn hóa từ Explorer, Planner có thể nhận trực tiếp
phần context mà không chạy lại Explorer qua
`POST /api/plans/main/from-context`:

```json
{
  "intent": {
    "destination": "Hà Nội",
    "travelStyle": "local",
    "pace": "balanced",
    "interests": ["food", "culture"],
    "mustVisitPlaces": [],
    "avoidPlaces": [],
    "constraints": [],
    "clarifyingQuestions": []
  },
  "tripSpec": {
    "days": 3,
    "partySize": 2,
    "budget": {
      "targetAmount": 6000000,
      "currency": "VND",
      "level": "medium"
    }
  },
  "regionKey": "vn,ha-noi",
  "selectedPlaces": [
    {
      "placeId": "place_123",
      "name": "Văn Miếu",
      "mustVisit": true,
      "sourceRefs": ["source_123"]
    }
  ],
  "userStatus": {}
}
```

`selectedPlaces` vẫn là ranh giới xác nhận: endpoint không tự chuyển
`placeCandidates` hoặc `foodPlaces` chưa xác nhận thành yêu cầu bắt buộc.

Nếu cả catalog vùng và `selectedPlaces` đều trống, endpoint trả lỗi
`PLANNER_INPUT_INSUFFICIENT` với HTTP 422. Plan chỉ có trạng thái `locked` khi
`CheckOverall.status` là `passed`; khi có warning cần backup, plan giữ trạng thái
`draft`; lỗi kiểm tra mức `error` tạo plan `failed`.

Plan tạo qua trip chat và lịch sử revision không bị mất khi tiến trình backend
khởi động lại. Plan tạo qua các endpoint `/plans/main*` độc lập và request tạo
backup vẫn chỉ hoạt động khi plan chính còn trong bộ nhớ của cùng tiến trình.

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
- `GET /api/me/plans`: lấy thư viện các plan đã mua của buyer kèm `copiedPlanId` và trạng thái entitlement (`active` / `revoked`).
- `POST /api/admin/creator-applications/{id}/approve`: admin duyệt creator application.
- `POST /api/admin/listings/{versionId}/review`: admin duyệt/từ chối phiên bản listing (`decision`: `approve` | `reject`).
- `POST /api/admin/reports/{reportId}/resolve`: admin xử lý báo cáo vi phạm (`decision`: `unpublish` | `dismiss`).
- `POST /api/admin/orders/{orderId}/refund`: admin hoàn tiền đơn hàng, thu hồi quyền (`revoked`) nhưng bảo toàn bản sao `copiedPlanId`.
- `GET /api/admin/audit-events`: tra cứu nhật ký kiểm toán quản trị viên (có ẩn dữ liệu nhạy cảm).

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
