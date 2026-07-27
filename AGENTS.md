# AGENTS.md

Đây là điểm bắt đầu dành cho các coding agent làm việc với VSF Travel Planner.
Phải đọc file này trước khi thay đổi code.

## Tóm tắt sản phẩm

VSF Travel Planner có hai năng lực cùng nằm trong MVP. Năng lực cốt lõi là biến
URL video hoặc nội dung tham khảo thành địa điểm và ngữ cảnh có nguồn, để người
dùng xác nhận trước khi Planner tạo Main Plan, kiểm tra tính khả thi và tạo
Backup Plan riêng khi cần. Năng lực Marketplace cho phép creator xuất bản và bán
plan có version; buyer nhận một bản sao cá nhân rồi tiếp tục chỉnh sửa bằng cùng
Planner. Giá trị khác biệt của sản phẩm là chuỗi
`URL -> dữ liệu có cấu trúc -> plan khả thi`, không chỉ là một phản hồi AI dạng
văn bản.

## Hiện trạng cần ghi nhớ

Tầm nhìn sản phẩm rộng hơn phần đã được triển khai.

- Đã triển khai: tạo/xem danh sách người dùng, migration bảng user, khung luồng
  lập kế hoạch, điền plan theo quy tắc, kiểm tra plan, endpoint tạo plan dự phòng,
  health check và giao diện người dùng tối giản.
- Đang giả lập: phản hồi AI thông qua `StubLLMClient`.
- Tạm thời: plan được lưu trong bộ nhớ của tiến trình và mất khi khởi động lại.
- Placeholder: profile và Marketplace chỉ có endpoint preview/danh mục.
- Chưa triển khai: authentication, phân quyền, nhập URL, bản đồ, chỉnh sửa cộng
  tác, đồng bộ offline, listing, order, payment, review, achievement,
  notification, creator analytics và quy trình admin.

Không được mô tả một tính năng mục tiêu như thể nó đã được triển khai. Không
được thêm các tuyên bố chưa đúng về trạng thái production vào UI hoặc tài liệu
API.

## Tài liệu cần đọc theo công việc

| Công việc | Ngữ cảnh bắt buộc |
| --- | --- |
| Hành vi sản phẩm hoặc mức độ ưu tiên | `docs/01`, `docs/02`, `docs/03`, `docs/04` |
| Backend hoặc hạ tầng | `docs/05`, `docs/06`, `docs/07`, ADR-001 |
| Database hoặc migration | `docs/06`, ADR-001 |
| AI Planner | `docs/06`, `docs/08`, `docs/09`, ADR-003 |
| Bản đồ, định tuyến, địa điểm | `docs/04`, `docs/09`, ADR-002 |
| Marketplace hoặc thanh toán | `docs/01`, `docs/03`, `docs/06`, `docs/11` |
| Test hoặc CI | `docs/10` |
| Authentication hoặc dữ liệu người dùng | `docs/06`, `docs/11` |

## Quy tắc kiến trúc

- Giữ cấu trúc monorepo chia thành `frontend/` và `backend/`.
- Frontend sử dụng Next.js App Router, TypeScript, Zod và module theo tính năng.
- Backend sử dụng FastAPI với ranh giới router -> service/workflow -> repository.
- Quy tắc nghiệp vụ phải nằm trong
  `backend/app/modules/<module>/domain` hoặc service, không đặt trong router
  FastAPI.
- Các nhà cung cấp AI, bản đồ, thanh toán và nội dung bên ngoài phải được đặt sau
  interface.
- Importer không được truyền payload thô của nguồn vào domain Planner. Nội dung
  phải được chuẩn hóa thành source, claim và place candidate có provenance.
- JSON của API sử dụng camelCase ở bên ngoài và snake_case trong Python.
- Dữ liệu nghiệp vụ phải được lưu thông qua repository. Repository trong bộ nhớ
  chỉ phù hợp cho prototype và test.
- Plan đã mua phải tạo ra một bản sao cá nhân; chỉnh sửa bản sao không được thay
  đổi phiên bản creator đã xuất bản.
- Plan dự phòng là plan riêng được liên kết với plan chính; không được âm thầm
  ghi đè plan chính đã khóa.
- Phải lưu nguồn gốc và độ mới của dữ liệu du lịch lấy từ bên ngoài.

## Danh sách kiểm tra khi thay đổi

Trước khi sửa:

1. Xác định công việc thay đổi hành vi hiện tại, hành vi mục tiêu hay cả hai.
2. Kiểm tra module liên quan và ranh giới API/schema của nó.
3. Kiểm tra tài liệu và ADR tương ứng.

Trước khi hoàn thành:

1. Chạy các test sát nhất với thay đổi và typecheck nếu contract bị ảnh hưởng.
2. Kiểm tra luồng lỗi và phân quyền, không chỉ luồng thành công.
3. Cập nhật tài liệu API/domain/MVP khi contract hoặc phạm vi thay đổi.
4. Thêm ADR khi chọn provider hoặc đưa ra quyết định cấu trúc khó đảo ngược.
5. Không ghi secret, dữ liệu cá nhân, payload thô của bên thứ ba hoặc toàn bộ
   prompt vào log.

## Lệnh thường dùng

```bash
# Frontend
cd frontend
npm run typecheck
npm run build

# Backend
cd backend
python -m compileall app
uvicorn app.main:app --reload

# Toàn bộ môi trường trên máy cá nhân
docker compose up --build
```

Backend hiện chưa cấu hình bộ test tự động. Hãy thêm pytest cùng thay đổi backend
nghiệp vụ đầu tiên; xem `docs/10-testing-strategy.md`.
