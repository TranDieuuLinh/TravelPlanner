# Đánh giá E2E lịch trình Hà Nội theo user insight

Cập nhật lần cuối: 2026-08-21.

File kết quả đầy đủ: `hanoi_user_insights_e2e.json`.

## Phạm vi

- Chạy 4 hồ sơ người dùng, tất cả chỉ yêu cầu địa điểm tại Hà Nội.
- Flow: Supervisor → Explorer → PlaceChecker PostgreSQL → ItineraryPlanner/Valhalla → finish.
- Gemini note translator của PlaceChecker được tắt trong benchmark để dữ liệu đọc từ
  PostgreSQL không được gửi ra provider ngoài. Supervisor và Explorer vẫn dùng Gemini.
- Đây là smoke E2E trên dữ liệu development hiện tại, không phải đánh giá production.

## Tổng hợp

| Case | Kết quả | Thời gian | Lịch | Chi phí/người | Nhận xét ngắn |
|---|---|---:|---:|---:|---|
| Một mình, ngân sách thấp | Không có lịch | 81,13s | 0 ngày | — | PlaceChecker chặn vì thiếu meal coverage và food query timeout |
| Cặp đôi, ngân sách cao | Thành công | 85,21s | 2 ngày, 17 điểm | 1.203.392 VND | Đủ 6 bữa, 3/4 điểm yêu cầu được xếp |
| Gia đình có trẻ em | Thành công | 69,94s | 2 ngày, 17 điểm | 1.241.940 VND | Insight trẻ em/avoid được giữ; Bảo tàng Dân tộc học bị unscheduled |
| Người lớn tuổi, tâm linh | Thành công | 132,62s | 2 ngày, 16 điểm | 1.587.917 VND | Lịch được tạo nhưng chưa giữ tốt các điểm bắt buộc và nhịp độ còn dày |

## Đánh giá

- Tỷ lệ tạo được lịch: **3/4 case (75%)**.
- Cả ba lịch thành công đều đủ 2 ngày, đủ 3 bữa/ngày và toàn bộ tọa độ điểm
  dừng nằm trong bounding box Hà Nội dùng cho phép kiểm tra.
- Explorer truyền đúng destination, số người, budget, preference và avoid tags
  sang Planner ở các case thành công.
- Case gia đình giữ được nhóm `Phù Hợp Với Trẻ Em`, `gia đình` và các avoid như
  nightlife/rượu bia/mạo hiểm; lịch không chứa tag xung đột trực tiếp.
- Chất lượng cá nhân hóa mới ở mức development: lịch còn khá dày, một số điểm
  người dùng yêu cầu bị unscheduled và candidate thay thế chưa luôn phù hợp hồ sơ.
- Các warning cho thấy dữ liệu hiện tại còn thiếu cost, duration, meal window,
  operating status và một số relationship. Vì vậy chưa nên xem các lịch này là
  chất lượng production.

## Hiệu năng

- Supervisor: khoảng 3,7–4,6 giây/case.
- Explorer: khoảng 2,6–8,4 giây/case.
- PlaceChecker là phần tốn thời gian nhất: khoảng 56,8–116,3 giây/case.
- Planner: khoảng 3,3–14,2 giây ở các case thành công.
- `finish` là deterministic mapping, khoảng 0,1 ms và không gọi LLM.

## Kết luận

Flow đã chạy xuyên suốt và xuất được lịch cho đa số hồ sơ. Điểm nghẽn/chất lượng
chính trong lần đo này nằm ở độ phủ dữ liệu PlaceChecker và food pool, không nằm
ở `finish`. Kết quả phù hợp để smoke-test và so sánh regression sau khi dữ liệu
Hà Nội được cải thiện.
