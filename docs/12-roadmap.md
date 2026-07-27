# Lộ trình 6 tuần cho nhóm 3 người

## 1. Mục tiêu và điều kiện thực hiện

Trong 6 tuần, nhóm phải hoàn thành toàn bộ phạm vi MVP đã xác định tại
`04-mvp-scope.md`:

1. Traveler đi từ URL video/nội dung tham khảo đến Main Plan, CheckOverall,
   Backup Plan, chỉnh sửa, cộng tác đơn giản và sử dụng offline.
2. Creator tạo, kiểm tra, xuất bản và bán plan.
3. Buyer tìm kiếm, thanh toán, nhận đúng plan version, tạo bản sao cá nhân, chỉnh
   sửa, review hoặc report.
4. Admin xử lý creator, listing, order, refund và report; hệ thống có audit,
   telemetry, retry và khôi phục lỗi cơ bản.

Đây là kế hoạch delivery cường độ cao, yêu cầu ba thành viên làm toàn thời gian,
provider được chốt trong tuần 1 và không thêm phạm vi ngoài
`04-mvp-scope.md`. MVP dùng một connector video ưu tiên, một LLM, một place/map
provider và một payment provider, nhưng phải hoàn thành đầy đủ hành trình
Planner và Marketplace.

## 2. Phân công cố định

| Thành viên | Vai trò chính | Phạm vi sở hữu |
| --- | --- | --- |
| Người 1 | Backend, database và vận hành | PostgreSQL, migration, auth, repository, job, Marketplace backend, payment, entitlement, admin, audit |
| Người 2 | AI Planner và tích hợp | URL connector, extraction, place resolution, LLM, Planner, route, CheckOverall, Backup, evaluation |
| Người 3 | Frontend và tích hợp sản phẩm | Toàn bộ Next.js UI, editor, map, offline, creator/buyer/admin UI, API integration và E2E |

Owner chịu trách nhiệm từ thiết kế đến test và tài liệu của phần mình. Các phần
giao nhau vẫn phải pair:

- Người 1 và Người 2 chốt schema/domain trước khi tạo migration.
- Người 1 công bố OpenAPI sớm để Người 3 làm bằng mock.
- Người 2 cung cấp fixture structured output để Người 1 và Người 3 không phụ
  thuộc provider thật.
- Người 3 báo lỗi contract ngay trong ngày, không tạo logic thay thế backend ở UI.

## 3. Giai đoạn 1 - Tuần 1: Nền tảng và contract

### Người 1 - Backend và database

- Thiết lập pytest, lint/typecheck backend, migration test và CI.
- Chốt UUID, chuẩn lỗi API, timestamp, money và idempotency.
- Tạo migration nền tảng cho `users`, profile/role, `trips`, `trip_members`,
  `trip_preferences`, `areas` và `places`.
- Triển khai authentication email, session/token và authorization cơ bản.
- Tạo repository base, transaction boundary, background job/outbox skeleton.
- Tạo OpenAPI skeleton cho import, places, plans, listings, orders và admin.

### Người 2 - AI và provider

- Chọn connector video, LLM, place/map, route và weather provider.
- Viết ADR cho connector/provider được chọn và giới hạn lưu dữ liệu.
- Hoàn thiện interface `SourceConnector`, `LLMClient`, `PlaceProvider`,
  `RouteProvider` và `WeatherProvider`.
- Chốt schema cho artifact, claim, candidate, `SelectedPlace`, MacroPlan,
  DayBrief, plan output và check issue.
- Tạo fake provider và fixture tiếng Việt cho toàn nhóm.
- Spike một URL thật thành caption/transcript và place candidate.

### Người 3 - Frontend

- Hoàn thiện app shell, routing, auth state, HTTP client và error boundary.
- Xây màn hình đăng ký/đăng nhập, tạo trip và dashboard trip.
- Xây component job progress, empty/error/retry và notification.
- Tạo mock server/schema cho import và Planner từ OpenAPI skeleton.
- Thiết lập component test, Playwright và responsive layout.

### Cổng nghiệm thu tuần 1

- CI chạy backend compile/test, frontend typecheck/build/test.
- User đăng nhập, tạo trip và mời thành viên với quyền cơ bản.
- Một URL mẫu chạy được qua connector spike.
- API contract và structured-output schema được khóa version `v1`.
- Frontend chạy được luồng tạo trip bằng mock API.

## 4. Giai đoạn 2 - Tuần 2: URL thành SelectedPlaces

### Người 1 - Backend và database

- Tạo bảng/repository cho `source_imports`, `source_artifacts`, `source_claims`,
  `place_candidates`, `place_candidate_matches`, import job và job attempt.
- Tạo bảng Place Database: aliases, area membership, provider refs, sources,
  opening/special hours, prices, tags và media cần thiết.
- Triển khai API tạo import, xem trạng thái, retry và xác nhận candidate.
- Chống SSRF, giới hạn URL/redirect/body/timeout và lưu kết quả từng phần.
- Thêm idempotency, authorization và audit cho import/confirmation.

### Người 2 - AI và provider

- Triển khai fetch metadata/caption/transcript/artifact theo chính sách nguồn.
- Trích xuất claim: place, activity, timing, price và advice bằng structured
  output.
- Resolve place, tìm candidate, gộp trùng và chấm confidence.
- Lưu provenance/evidence và phân biệt claim với dữ liệu provider xác minh.
- Xử lý thiếu transcript, URL riêng tư/không hỗ trợ, timeout và prompt injection.
- Tạo evaluation cho candidate mơ hồ, sai tên và nhiều URL cùng một place.

### Người 3 - Frontend

- Xây UI dán một/nhiều URL và hiển thị trạng thái từng import job.
- Xây màn hình evidence/candidate/match và confidence.
- Cho phép xác nhận, sửa, loại bỏ, retry hoặc thêm place thủ công.
- Hiển thị nguồn nào đóng góp cho một selected place sau khi dedup.
- Kết nối API thật và hoàn thiện loading/partial/error states.

### Cổng nghiệm thu tuần 2

- URL được hỗ trợ đi đến `SelectedPlaces` end-to-end.
- Candidate chưa xác nhận không tự động vào Planner.
- Retry không tạo import/candidate trùng và không làm mất kết quả từng phần.
- Nguồn không hỗ trợ có fallback nhập caption/place thủ công.
- Frontend, backend và worker chạy cùng nhau trên môi trường tích hợp.

## 5. Giai đoạn 3 - Tuần 3: Main Plan và lưu trữ bền vững

### Người 1 - Backend và database

- Tạo `plans`, `planning_jobs`, `plan_versions`, `plan_days`, `plan_items`,
  source links, route legs và unscheduled places.
- Chuyển PlanRepository từ memory sang PostgreSQL.
- Triển khai API Explorer, create planning job, progress, lấy plan và version.
- Thêm optimistic concurrency, version history và stable item ID.
- Tạo route snapshot/cache và API place/route cho frontend map.
- Thêm trip member authorization cho host/editor/viewer.

### Người 2 - AI và provider

- Hoàn thiện Explorer và câu hỏi làm rõ có giá trị cao.
- Tạo MacroPlan và DayBrief theo hard/soft constraints.
- Finder xếp `SelectedPlaces`, thời gian đệm, bữa ăn, nghỉ và route.
- Thêm địa điểm provider đề xuất khi cần và đánh dấu nguồn rõ ràng.
- Trả `UnscheduledPlace` kèm reason code khi không thể xếp.
- Tạo structured-output validation, timeout, retry và model/schema telemetry.

### Người 3 - Frontend

- Xây form ngày đi, nhóm, ngân sách, pace, phương tiện, accessibility và hard
  constraints.
- Xây UI câu hỏi làm rõ không làm mất draft/import.
- Hiển thị tiến độ Explorer -> Planner -> Finder -> Check.
- Xây timeline theo ngày, source badge, cost, route leg và unscheduled list.
- Tích hợp bản đồ marker/route và đồng bộ thứ tự map với timeline.
- Xây màn hình xem/lưu/mở lại plan.

### Cổng nghiệm thu tuần 3

- Traveler đi từ URL đến Main Plan có ngày/item/route/cost/source.
- Plan không mất sau backend restart.
- Mọi selected place được xếp hoặc có lý do chưa xếp.
- Map và timeline dùng cùng place ID, thứ tự và route.
- Authorization chặn user ngoài trip đọc/sửa plan riêng tư.

## 6. Giai đoạn 4 - Tuần 4: Editor, Check, Backup và nền Marketplace

### Người 1 - Backend và database

- Hoàn thiện API thêm, xóa, kéo thả, đổi ngày/giờ, khóa item và undo.
- Tạo plan check/check issue persistence và revision transaction.
- Tạo Backup Plan riêng với `parent_plan_id`, không mutate Main Plan.
- Tạo offline-read snapshot, completion progress và đồng bộ có version.
- Tạo migration Marketplace: creator profile, listing/version/media, favorite,
  order/order line, payment/event, refund, entitlement, review/report,
  moderation, creator metric và audit.
- Tạo API creator/listing skeleton để Người 3 tích hợp sớm.

### Người 2 - AI và provider

- Triển khai CheckOverall cho schema, overlap, density, budget và locked item.
- Kiểm tra place identity, opening/special hours, route, weather và freshness.
- Trả issue code, severity, evidence, affected item và scoped fix.
- Triển khai AI revision theo ngày/khung giờ/item chưa khóa.
- Triển khai Backup Planner/Finder/Validator từ Main Plan và CheckOverall report.
- Xây publish-quality check dùng lại check pipeline.

### Người 3 - Frontend

- Hoàn thiện editor: add/delete/reorder/time/lock/undo và version conflict UI.
- Hiển thị warning, evidence, refresh, accept/ignore/fix action.
- Xây màn hình so sánh/chọn Main Plan và Backup Plan.
- Thêm completion progress, trip member UI và offline read.
- Xây creator profile, verification form, listing editor và media upload bằng
  API skeleton/mock.

### Cổng nghiệm thu tuần 4

- Main Plan chỉnh sửa được, revision giữ item khóa.
- CheckOverall phát hiện và xử lý được issue thuộc phạm vi MVP.
- Backup dùng độc lập và không thay đổi Main Plan.
- Plan đã chọn mở được offline ở chế độ đọc.
- Creator tạo được listing draft từ plan version đã check.

## 7. Giai đoạn 5 - Tuần 5: Marketplace hoàn chỉnh

### Người 1 - Backend và database

- Hoàn thiện creator verification, listing preview, publish/unpublish và version.
- Triển khai search/filter/favorite và quyền xem preview/full content.
- Tích hợp payment provider: checkout, order, webhook signature/idempotency.
- Triển khai entitlement, personal copy, refund và ledger/revenue cơ bản.
- Triển khai review đủ điều kiện, report, moderation và admin API.
- Thêm creator metrics: view, conversion, order, review, refund và revenue.

### Người 2 - AI và provider

- Bảo đảm chỉ plan version pass check mới được publish.
- Tạo metadata/tóm tắt tìm kiếm từ plan nhưng không lộ nội dung trả phí.
- Hoàn thiện clone đúng `ListingVersion`/`PlanVersion` và provenance cho buyer.
- Cho phép buyer đưa personal copy vào Planner, thêm URL và đổi constraints.
- Tạo evaluation cho creator publish và buyer personalization.
- Hỗ trợ Người 1 kiểm tra retry/payment side effect không bị model/provider tác
  động.

### Người 3 - Frontend

- Hoàn thiện creator flow: draft, media, preview trước/sau mua, giá, license,
  submit, publish/unpublish và version.
- Xây Marketplace browse, search, filter, favorite và listing detail.
- Xây checkout, order status, payment failure/retry và thư viện đã mua.
- Tạo personal copy và mở trong Planner.
- Xây review/report, creator dashboard và admin tối thiểu cho user, creator,
  listing, order, report và refund.
- Kiểm tra quyền: buyer chưa thanh toán không thấy nội dung full.

### Cổng nghiệm thu tuần 5

- Creator publish và phát hành version mới mà không đổi giao dịch cũ.
- Buyer thanh toán, nhận entitlement đúng một lần và tạo personal copy.
- Payment fail/pending không cấp quyền; webhook trùng không tạo dữ liệu trùng.
- Buyer chỉnh copy bằng Planner mà không sửa plan creator.
- Review/report/refund/admin và creator dashboard chạy end-to-end.

## 8. Giai đoạn 6 - Tuần 6: Hardening, tích hợp và phát hành

Từ cuối ngày thứ hai của tuần 6 đóng băng tính năng. Chỉ sửa lỗi làm hỏng tiêu
chí nghiệm thu, bảo mật, dữ liệu hoặc khả năng phát hành.

### Người 1 - Backend, dữ liệu và vận hành

- Rà migration, transaction, FK/index, authorization và idempotency.
- Test webhook, refund, entitlement, audit và financial record retention.
- Rate limit auth/import/generate/search/checkout.
- Chạy backup/restore, migration upgrade và rollback/forward-fix rehearsal.
- Thiết lập staging/production config, health check, telemetry và alert cơ bản.
- Thực hiện threat-model action cho auth, URL, payment và nội dung công khai.

### Người 2 - AI, dữ liệu và độ tin cậy

- Chạy evaluation tiếng Việt cho extraction, planning, revision và backup.
- Sửa hallucination, hard-constraint violation và mất locked item.
- Kiểm tra timeout/retry/circuit breaker cho mọi provider.
- Kiểm tra freshness, provenance, prompt injection và unsafe model output.
- Đo latency/token/cost và đặt ngưỡng cảnh báo.
- Chuẩn bị fallback vận hành khi connector/LLM/place/route provider lỗi.

### Người 3 - Frontend, E2E và phát hành

- Chạy Playwright cho toàn bộ hành trình Planner, creator, buyer và admin.
- Hoàn thiện responsive mobile/desktop, accessibility và offline read.
- Kiểm tra mọi loading/empty/error/permission/conflict/payment state.
- Sửa lỗi tích hợp, lỗi text overflow và map/timeline không đồng bộ.
- Deploy frontend, chạy smoke test trên staging và production candidate.
- Chuẩn bị checklist demo và hướng dẫn xử lý lỗi cho nhóm.

### Cổng phát hành cuối tuần 6

Toàn bộ tiêu chí trong `04-mvp-scope.md` phải pass:

- `URL -> SelectedPlaces -> Main Plan -> Edit -> Check -> Backup -> Offline`.
- `Creator -> Listing -> Preview -> Publish -> New Version`.
- `Buyer -> Search -> Checkout -> Entitlement -> Personal Copy -> Planner`.
- `Review/Report -> Admin/Moderation -> Refund/Audit`.
- Không có lỗi P0/P1, không mất dữ liệu khi restart/retry và không truy cập chéo
  dữ liệu riêng tư.

## 9. Nhịp làm việc bắt buộc

### Hằng ngày

- 09:00: sync 15 phút về blocker, contract và bàn giao trong ngày.
- Trước 12:00: owner backend/AI công bố schema hoặc fixture thay đổi.
- Merge ít nhất một lần mỗi ngày; branch không sống quá hai ngày.
- 16:30: chạy smoke test tích hợp trên nhánh chính.
- Mỗi người dành tối thiểu 20% thời gian cho test, review và sửa lỗi.

### Hằng tuần

- Thứ Hai: khóa mục tiêu tuần và API/schema cần dùng.
- Thứ Tư: demo giữa tuần trên môi trường tích hợp, xử lý dependency trễ.
- Thứ Sáu: demo cổng nghiệm thu bằng dữ liệu thật hoặc sandbox provider.
- Không chuyển issue chưa hoàn thành sang tuần sau mà không chỉ rõ công việc nào
  bị đổi thứ tự để bù.

## 10. Quy tắc ưu tiên khi có blocker

Không bỏ âm thầm tính năng thuộc MVP. Xử lý theo thứ tự:

1. Giữ bất biến dữ liệu, bảo mật và hai hành trình end-to-end.
2. Dùng fallback thủ công đã thiết kế khi provider ngoài không ổn định.
3. Giảm độ bóng UI hoặc quy mô dữ liệu demo trước khi giảm hành vi nghiệp vụ.
4. Nếu một owner bị chặn hơn nửa ngày, thành viên có dependency gần nhất phải
   pair ngay trong ngày.
5. Mọi thay đổi provider, contract hoặc phạm vi phải được ghi vào ADR/docs trước
   khi triển khai.

## 11. Ma trận phụ thuộc chính

| Đầu ra | Owner | Người phụ thuộc | Hạn cuối |
| --- | --- | --- | --- |
| API/error/auth contract v1 | Người 1 | Người 2, Người 3 | Tuần 1, ngày 3 |
| AI/import/plan schema và fixture v1 | Người 2 | Người 1, Người 3 | Tuần 1, ngày 3 |
| Import/confirmation API thật | Người 1 + Người 2 | Người 3 | Tuần 2, ngày 3 |
| Plan persistence/generation API | Người 1 + Người 2 | Người 3 | Tuần 3, ngày 3 |
| Check/Backup/revision API | Người 1 + Người 2 | Người 3 | Tuần 4, ngày 3 |
| Listing/payment/admin API | Người 1 | Người 2, Người 3 | Tuần 5, ngày 2 |
| Personal-copy contract | Người 1 + Người 2 | Người 3 | Tuần 5, ngày 2 |
| E2E release report | Người 3 | Cả nhóm | Tuần 6, ngày 5 |

Kế hoạch này là delivery contract của nhóm trong 6 tuần. Mọi task trên board phải
gắn với một tuần, một owner, tiêu chí nghiệm thu và tài liệu/API liên quan.
