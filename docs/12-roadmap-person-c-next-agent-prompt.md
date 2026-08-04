# Prompt cho agent tiếp theo: triển khai tuần 3 Người C

Bạn đang làm trong repo `/home/suns/Desktop/VSF_TravelPlanner`.

Hãy đọc trước:

- `AGENTS.md`
- `docs/12-roadmap-person-c.md`
- `docs/13-database-schema.md`
- `backend/app/shared/contracts/plan_marketplace.py`
- `backend/app/modules/marketplace/model.py`
- `backend/migrations/versions/20260727_0003_add_person_c_marketplace.py`

## Bối cảnh hiện tại

Người C sở hữu Auth, Profile, phân quyền, Creator Marketplace, Buyer Marketplace,
Order/Entitlement, Review/Report và Admin/Audit. Không sửa thuật toán URL của
Người A và không sửa thuật toán Planner/Finder/Check/Backup của Người B.

Auth/Profile đã có code và test. Database PostgreSQL đã chạy tới Alembic head:

```text
20260727_0003
```

Migration `20260727_0003_add_person_c_marketplace.py` đã tạo schema Người C:

```text
marketplace_plans
marketplace_plan_versions
favorites
orders
order_items
payments
payment_events
entitlements
reviews
reports
audit_events
```

Không tạo thêm bảng `listings` hoặc `listing_versions`. Trong API có thể dùng
thuật ngữ listing, nhưng database phải map như sau:

```text
API listingId         -> marketplace_plans.id
API listingVersionId  -> marketplace_plan_versions.id
Planner planId        -> marketplace_plan_versions.source_plan_id
Planner planVersionId -> marketplace_plan_versions.source_plan_version_id
```

Người B chưa có plan persistence/version thật, nên phải dùng fake gateway theo
contract `PlanMarketplaceGateway`. Chỉ mock gateway của Planner; không mock
Marketplace database, service hoặc API.

## Nhiệm vụ chính

Triển khai tuần 3 Người C gồm C-12 đến C-18:

```text
C-12 Tạo listing draft
C-13 Metadata, preview, media, giá
C-14 Workflow moderation
C-15 Listing version bất biến
C-16 Search/filter/pagination
C-17 Explore dùng API thật
C-18 Favorite
```

## Backend cần làm

Tạo module Marketplace theo ranh giới router -> service -> repository:

```text
backend/app/modules/marketplace/
├── domain/
│   ├── enums.py
│   └── rules.py
├── gateways/
│   └── fake_plan_gateway.py
├── dependencies.py
├── repository.py
├── schema.py
├── service.py
├── creator_router.py
├── public_router.py
├── admin_router.py
└── router.py
```

Giữ `backend/app/modules/marketplace/model.py` hiện có, chỉ sửa khi thực sự cần.
Nếu sửa model làm đổi schema, phải tạo migration mới; không sửa migration đã
chạy trừ khi chắc chắn chưa chia sẻ cho nhóm.

### Fake Plan Gateway

Implement fake gateway cho tuần 3:

```text
plan_demo_valid       -> owner đúng, locked, valid
plan_demo_draft       -> owner đúng, draft, valid
plan_demo_invalid     -> owner đúng, locked, invalid
plan_demo_other_user  -> owner khác, locked, valid
```

Fake phải implement đúng `PlanMarketplaceGateway` và trả `PlanPublishInfo`,
`PlanPreview`. Có thể thêm helper `list_publishable_plans(actor_id)` trong
dependency/service nội bộ, nhưng không phá contract hiện có.

### API Creator

Triển khai:

```http
GET    /api/creator/publishable-plans
POST   /api/creator/listings
GET    /api/creator/listings
GET    /api/creator/listings/{listingId}
PATCH  /api/creator/listings/{listingId}
POST   /api/creator/listings/{listingId}/submit
POST   /api/creator/listings/{listingId}/publish
POST   /api/creator/listings/{listingId}/unpublish
```

Quy tắc:

- Chỉ role `creator` được tạo/sửa listing.
- `creator_id` lấy từ JWT, không lấy từ body.
- Client gửi `planId`; backend gọi gateway để lấy owner/status/check/version.
- `marketplace_plans` là listing ổn định.
- `marketplace_plan_versions` là snapshot bất biến.
- Tạo listing mới thì tạo `marketplace_plans` và version draft `version=1`.
- Sửa listing published thì tạo version draft mới, không sửa version published.
- `submit` chỉ cho plan `locked + valid`, đủ title/description/category/media/price/preview.
- `submit` set `marketplace_plan_versions.moderation_status=pending_review`.
- `publish` chỉ khi version `approved`; set version `published`, set
  `published_at`, set `marketplace_plans.current_published_version_id`, set
  `marketplace_plans.status=published`.
- `unpublish` set `marketplace_plans.status=unpublished`, không xóa version,
  order hoặc entitlement.

### API Public Marketplace

Triển khai:

```http
GET /api/listings
GET /api/listings/{listingId}
```

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

Public API chỉ trả current published version, không trả toàn bộ plan trả phí.
Search đọc từ `marketplace_plan_versions` được trỏ bởi
`marketplace_plans.current_published_version_id`.

### Favorite

Triển khai:

```http
PUT    /api/listings/{listingId}/favorite
DELETE /api/listings/{listingId}/favorite
GET    /api/me/favorites
```

`favorites.marketplace_plan_id` trỏ tới `marketplace_plans.id`.
PUT/DELETE phải idempotent.

### Admin moderation tối thiểu

Triển khai phần tối thiểu cho tuần 3:

```http
GET  /api/admin/listings/pending
POST /api/admin/listings/{listingVersionId}/review
```

Request:

```json
{
  "decision": "approve",
  "reason": "Nội dung hợp lệ"
}
```

Approve set `marketplace_plan_versions.moderation_status=approved`.
Reject set `rejected` và lưu `rejection_reason`. Admin không sửa nội dung
creator.

## Frontend cần làm

Frontend dùng Next.js App Router. Dùng `apiFetch` trong `frontend/src/lib/api.ts`
để giữ cookie, refresh và CSRF.

Tạo:

```text
frontend/src/lib/marketplace.ts
frontend/src/types/marketplace.ts
frontend/src/app/creator/listings/page.tsx
frontend/src/app/creator/listings/new/page.tsx
frontend/src/app/creator/listings/[listingId]/edit/page.tsx
frontend/src/app/listings/[listingId]/page.tsx
frontend/src/app/admin/listings/page.tsx
```

Cập nhật:

```text
frontend/src/app/explore/page.tsx
frontend/src/components/AppShell.tsx
frontend/src/app/globals.css
```

Yêu cầu frontend:

- Explore bỏ dữ liệu demo từ `frontend/src/data/demo.ts` và gọi API thật.
- Có loading, error, empty state.
- Có search/filter/sort/pagination.
- Detail listing hiển thị preview snapshot, giá, media, creator.
- Favorite hoạt động với user đã đăng nhập; nếu chưa đăng nhập điều hướng login.
- Creator Studio cho chọn fake publishable plan, tạo draft, sửa metadata, submit,
  publish/unpublish.
- Admin page duyệt pending listing versions.
- Chưa làm checkout MoMo trong tuần 3; nút mua có thể disabled hoặc hiển thị
  trạng thái tuần 4.

## Test bắt buộc

Backend pytest:

- Traveler tạo listing nhận `403`.
- Creator tạo draft từ `plan_demo_valid`.
- Không tạo/sửa listing của creator khác.
- Draft/invalid plan không submit được.
- Submit chuyển pending review.
- Admin approve/reject được pending version.
- Creator publish version approved.
- Published version không bị update trực tiếp.
- Sửa listing published tạo draft version mới.
- Public search chỉ trả current published version.
- Favorite PUT/DELETE idempotent.
- Response JSON dùng camelCase.

Frontend:

- `npm run typecheck`
- `npm run build`

Backend:

```bash
cd backend
DATABASE_URL='postgresql+psycopg://vsf:vsf@localhost:5432/vsf_travel' /tmp/vsf-travel-auth-venv/bin/alembic current
/tmp/vsf-travel-auth-venv/bin/pytest -q
```

## Không làm trong task này

- Không triển khai MoMo checkout.
- Không triển khai order copy plan.
- Không triển khai payout/subscription/coupon.
- Không tạo bảng `listings` hoặc `listing_versions`.
- Không migrate Place/Trip/Planner persistence.
- Không sửa thuật toán URL hoặc Planner.

Khi hoàn thành, báo lại rõ các file đã sửa, API đã có, cách chạy backend/frontend
và các test đã pass.
