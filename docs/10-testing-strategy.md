# Chiến lược kiểm thử

## Khoảng trống hiện tại

Repository chưa cấu hình bộ test tự động. `npm run typecheck` và các bước
build/compile chỉ cung cấp mức bảo vệ giới hạn, chưa kiểm tra hành vi.

## Các lớp kiểm thử

### Kiểm thử đơn vị backend

Sử dụng pytest cho domain và service:

- phân tích sở thích và tạo câu hỏi làm rõ;
- chuyển artifact thành claim/candidate và gộp địa điểm trùng;
- không commit candidate chưa được user xác nhận;
- điều phối luồng tạo plan;
- mọi selected place được xếp hoặc có lý do chưa xếp;
- bảo toàn item đã khóa và tính độc lập của plan dự phòng;
- quy tắc thời gian, mật độ và validation;
- bất biến của order, entitlement, review và payment;
- chuyển đổi lỗi từ provider.

### Kiểm thử tích hợp backend

Chạy test FastAPI với database cô lập:

- validation request và contract camelCase;
- khả năng lưu trữ của repository và migration;
- ma trận authentication và authorization;
- xử lý idempotent khi generate/checkout/webhook;
- vòng đời import job, retry từng bước và giữ kết quả từng phần;
- source connector, place resolution và provenance persistence;
- rollback transaction và xung đột dữ liệu.

Thay provider bên ngoài bằng fake tuân thủ đúng contract. Tạo một bộ test sandbox
provider nhỏ, tách khỏi quy trình trên máy cá nhân thông thường.

### Kiểm thử frontend

- Kiểm thử đơn vị cho chuyển đổi schema và reducer của editor.
- Component test form, trạng thái loading/empty/error, chỉnh sửa lịch trình và
  control phụ thuộc quyền hạn.
- End-to-end test các hành trình quan trọng nhất bằng Playwright.

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
