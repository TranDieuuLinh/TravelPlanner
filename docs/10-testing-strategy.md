# Chiến lược kiểm thử

## Hiện trạng

Backend đã được kiểm thử tự động toàn diện với pytest và database SQLite cô lập (23+ test cases thuộc 7 test suite), bao gồm: Auth JWT cookie, refresh session, CSRF, RBAC, Profile, creator application, trọn bộ nghiệp vụ Marketplace (Creator listings, MoMo Sandbox IPN anti-replay, Entitlements, copy plan `copied_plan_id`, reviews, reports, refunds, audit logs), contract Planner–Marketplace, và bộ kiểm thử nghiệm thu E2E toàn trình (`backend/tests/test_person_c_e2e_week6.py`). Frontend hiện được bảo vệ bằng typecheck và production build.

## Các lớp kiểm thử

### Kiểm thử đơn vị backend

Sử dụng pytest cho domain và service:

- phân tích sở thích và tạo câu hỏi làm rõ;
- chuyển artifact thành claim/candidate và gộp địa điểm trùng;
- YouTube caption cache hit không gọi provider, request cùng video được dedupe,
  IP block thử worker, còn mọi trạng thái thiếu caption đều không tải media/STT;
- caption, STT và frame OCR thành công được upsert idempotent vào cùng retrieval
  store theo canonical URL và có thể lọc theo loại artifact;
- URL candidate chỉ được tạo bởi Extractor, không bị Formatter sinh lại;
- Formatter và Resolver bắt đầu song song với intake URL;
- timing report giữ cùng `intakeId`, có đủ stage chính và không ghi raw
  prompt/URL/transcript/OCR vào JSONL; timing từng URL phân biệt cache hit,
  cache miss và bypass;
- timing Planner/Finder có tổng wall-clock, đủ stage Planner, Finder và
  CheckOverall, không chứa prompt hoặc payload provider;
- không persist candidate unresolved hoặc thiếu latitude/longitude;
- candidate `needs_review` không được bàn giao vào Planner, kể cả khi provider
  trả tọa độ đại diện;
- điều phối luồng tạo plan;
- TripThemePlanner trả requirement toàn chuyến và backend chỉ sinh bucket ngày trung
  tính; URL provenance không có `sourceDay` được phép đổi ngày theo tuyến;
- itinerary optimizer gom activity gần nhau giữa các ngày, giữ source-day anchor,
  dùng matrix khi có và bảo toàn thứ tự khi provider lỗi;
- route-first tạo đúng hai activity và ba bữa mỗi ngày theo thứ tự cố định; meal selector
  chọn breakfast/lunch/dinner sau activity và không dùng khung giờ;
- mọi selected place được xếp hoặc có lý do chưa xếp;
- bảo toàn item đã khóa và tính độc lập của plan dự phòng;
- trip chat giữ nguyên plan ID qua nhiều revision, nhớ user request trước và
  từ chối optimistic revision đã cũ;
- quy tắc thời gian, mật độ và validation;
- bất biến của order, entitlement, review và payment;
- chuyển đổi lỗi từ provider.

### Kiểm thử tích hợp backend

Chạy test FastAPI với database cô lập:

- validation request và contract camelCase;
- khả năng lưu trữ của repository và migration;
- ma trận authentication và authorization;
- isolation của trip chat theo user và contract camelCase của chat history;
- xử lý idempotent khi generate/checkout/webhook;
- vòng đời import job, retry từng bước và giữ kết quả từng phần;
- batch URL/ảnh OCR tạo đúng một job cho mỗi nguồn, chỉ claim job kế tiếp sau khi job đang
  chạy kết thúc, tự kết thúc job quá deadline, giữ thứ tự batch, retry riêng và
  cô lập danh sách theo user; xóa job `queued`, hủy/xóa job `running` rồi chạy
  ngay job kế tiếp, cập nhật lại vị trí hàng chờ và không cho user thao tác job
  của tài khoản khác; xóa job đã hoàn tất/thất bại mà không ảnh hưởng plan
  revision; phân tích lại job đã kết thúc phải tạo job mới có
  `forceRefresh=true` và không ghi đè lịch sử job cũ; ảnh giữ đúng MIME/file gốc
  cho retry/reprocess và từ chối định dạng không hỗ trợ;
- source connector, place resolution và provenance persistence;
- rollback transaction và xung đột dữ liệu.

Thay provider bên ngoài bằng fake tuân thủ đúng contract. Tạo một bộ test sandbox
provider nhỏ, tách khỏi quy trình trên máy cá nhân thông thường.

### Kiểm thử frontend

- Kiểm thử đơn vị cho chuyển đổi schema và reducer của editor.
- Component test form, trạng thái loading/empty/error, chỉnh sửa lịch trình và
  control phụ thuộc quyền hạn.
- End-to-end test các hành trình quan trọng nhất bằng Playwright.

`admin-frontend/` phải vượt qua `npm run typecheck` và `npm run build`. Backend
có test riêng cho RBAC, list/detail planning run, redaction và contract report
của golden dataset. Golden runner phải có test cho ít nhất một module thực thi
thành công không phụ thuộc provider (Checker), một input sai contract và việc
lưu execution thành planning run để điều tra lại.

### Đánh giá AI

Hành vi AI cần bộ evaluation có version bên cạnh test truyền thống. Xem
`08-ai-planner-spec.md`.

## Hành trình toàn trình của MVP

1. Đăng ký, tạo trip, dán URL, xác nhận place, generate, chỉnh sửa, lưu, tải lại
   và mở offline.
2. URL không hỗ trợ/thiếu transcript vẫn giữ draft và cho nhập place thủ công.
3. Hai URL nhắc cùng một place được gộp nhưng vẫn giữ cả hai provenance.
4. Selected place không xếp được xuất hiện với reason code, không bị mất.
5. Giữ một địa điểm đã khóa khi AI chỉnh sửa phần còn lại của ngày.
6. Tạo plan dự phòng sau cảnh báo route/place mà không thay đổi plan chính.
7. Creator tạo plan từ URL, preview, publish và version listing.
8. Buyer thanh toán, nhận quyền truy cập, tạo bản sao cá nhân và review sau khi
   sử dụng.
9. Buyer thêm URL vào bản sao và Planner không sửa plan đã publish của creator.
10. Payment thất bại không cấp quyền; webhook trùng chỉ cấp quyền một lần.
11. User không có quyền không thể chỉnh sửa plan riêng tư của người khác.
12. Admin xử lý report và tạo audit event.

## Cổng kiểm soát chất lượng trong CI

- Backend: format/lint, typecheck, unit test, integration test và kiểm tra
  migration.
- Frontend: lint, typecheck, component test và production build.
- End-to-end smoke test trên stack dùng một lần.
- Quét dependency và secret.

Test phải deterministic: cố định thời gian, seed random, không gọi provider thật
và dùng fixture timezone/tiền tệ rõ ràng.

## Evaluation Planner/Finder cục bộ

Chạy bộ scenario deterministic từ planning context qua Planner, Finder, Main
Plan và Backup Plan:

```bash
cd backend
.\.venv\Scripts\python.exe scripts\evaluate_planner_finder.py
```

Có thể lưu report JSON để review thủ công:

```bash
.\.venv\Scripts\python.exe scripts\evaluate_planner_finder.py --output .runlogs/planner-finder-evaluation.json
```

Evaluator kiểm tra catalog fill, giới hạn thời gian/user status, ranh giới
selected/avoided/unscheduled, ID nhập tay, duration so với time window, source
provenance và bảo toàn selected Place trong Backup Plan. Evaluator không dùng
provider thật và không đánh giá chất lượng `CheckOverall`.
