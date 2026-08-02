# ADR-002: Ranh giới provider cho bản đồ và địa điểm

- Trạng thái: Đã thay thế phần routing bởi ADR-008
- Ngày: 2026-07-27
- Cập nhật: 2026-08-01

## Bối cảnh

Bản đồ, chuẩn hóa địa điểm, tuyến đường, thời gian di chuyển và gợi ý phương tiện
là năng lực cốt lõi của MVP. Độ phủ và điều khoản provider có thể ảnh hưởng lớn
đến domain model, UX, chi phí vận hành và khả năng offline.

## Quyết định

Không gắn trực tiếp domain hoặc contract API với payload của một provider.
Gateway provider phải cung cấp:

- tìm kiếm/chi tiết địa điểm và ánh xạ tới place nội bộ ổn định;
- ma trận tuyến đường và geometry tuyến;
- phương tiện được hỗ trợ cùng thời lượng/khoảng cách;
- attribution và metadata về độ mới;
- lỗi có type cho quota, timeout, not-found và phương tiện không hỗ trợ.

Domain chỉ nhận dữ liệu đã chuẩn hóa. Mỗi route phải giữ `source`, `verified`,
`fetchedAt`, geometry và chi tiết mode cần thiết. Provider lỗi phải fallback theo
từng leg và không làm hỏng toàn bộ plan. Public transit chỉ được hiển thị khi có
itinerary provider-backed với geometry thật; hệ thống không tạo tuyến transit từ
đường thẳng giữa hai tọa độ.

UI dùng Leaflet/OpenStreetMap làm bản đồ nền. Place resolution và routing nằm sau
các interface riêng để có thể thay implementation mà không đổi entity plan.
Quyết định provider routing hiện hành nằm trong ADR-008.

## Tiêu chí đánh giá

Chấm điểm ứng viên theo độ phủ tại Việt Nam, chất lượng transit/phương tiện địa
phương, độ chính xác khi đi bộ/lái xe, giá, quota, điều khoản cache/hiển thị, khả
năng tiếp cận, độ trễ và chất lượng SDK.

## Hệ quả

- Interface nhỏ giúp giảm phụ thuộc provider và cho phép dùng fake khi test.
- Tính năng riêng của provider có thể tồn tại trong adapter nhưng không được rò
  rỉ vào plan entity hoặc contract API công khai.
- Hạn mức và pricing là dữ liệu vận hành có thể thay đổi, không được hard-code
  quota thương mại vào domain hoặc tuyên bố thành SLA.
- `verified=true` chỉ xác nhận dữ liệu đến từ provider đã cấu hình; nó không mặc
  định có nghĩa là ETA live hoặc dữ liệu realtime.
