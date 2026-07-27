# AGENTS.md

Đây là điểm bắt đầu dành cho các coding agent làm việc với VSF Travel Planner.
Phải đọc file này trước khi thay đổi code.

## Tóm tắt sản phẩm

VSF Travel Planner kết hợp công cụ tạo lịch trình bằng AI với Marketplace dành
cho nhà sáng tạo. Người đi du lịch có thể bắt đầu từ một điểm đến/URL tham khảo
hoặc khám phá plan của creator, sau đó chỉnh sửa và sử dụng một bản sao cá nhân.
Creator có thể xây dựng, bổ sung nội dung, xuất bản và bán plan. Điểm khác biệt
của sản phẩm là lịch trình vẫn hữu ích sau khi được AI tạo ra: có nhiều phương
án, bản đồ và phương tiện di chuyển, chỉnh sửa thủ công, kiểm tra tính khả thi,
cộng tác, dùng offline và nội dung Marketplace đáng tin cậy.

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
