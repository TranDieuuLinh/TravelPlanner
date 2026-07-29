# ADR-002: Lựa chọn nhà cung cấp bản đồ và địa điểm

- Trạng thái: Đang đề xuất
- Ngày: 2026-07-27

## Bối cảnh

Bản đồ, chuẩn hóa địa điểm, tuyến đường, thời gian di chuyển và gợi ý phương tiện
là năng lực cốt lõi của MVP. Độ phủ và điều khoản provider có thể ảnh hưởng lớn
đến domain model, UX, chi phí vận hành và khả năng offline.

## Quyết định đề xuất

Không gắn chặt code sản phẩm trực tiếp với một provider. Trước tiên, thực hiện
benchmark ngắn với các provider ứng viên trên các chuyến đi đại diện tại Việt
Nam; sau đó ghi provider chính và fallback được chọn trong phiên bản đã chấp nhận
mới của ADR này.

Trong thời gian benchmark, Explorer được phép dùng HERE Discover như adapter
POI thử nghiệm với Nominatim làm fallback. Việc này không chấp nhận HERE làm
provider bản đồ hoặc định tuyến chính thức. Cấu hình phải cho phép quay về
Nominatim mà không đổi contract domain; thiếu HERE credential cũng phải dùng
Nominatim an toàn.

Gateway của provider phải cung cấp:

- tìm kiếm/chi tiết địa điểm và ánh xạ tới place nội bộ ổn định;
- ma trận tuyến đường và geometry tuyến;
- phương tiện được hỗ trợ cùng thời lượng/khoảng cách;
- attribution và metadata về độ mới;
- lỗi có type cho quota, timeout, not-found và phương tiện không hỗ trợ.

## Tiêu chí đánh giá

Chấm điểm ứng viên theo độ phủ tại Việt Nam, chất lượng transit/phương tiện địa
phương, độ chính xác khi đi bộ/lái xe, giá, quota, điều khoản cache/hiển thị, khả
năng tiếp cận, độ trễ và chất lượng SDK.

## Hệ quả

- Một interface nhỏ giúp giảm phụ thuộc provider và cho phép dùng fake khi test.
- Cần thực hiện benchmark trước khi triển khai bản đồ.
- Tính năng riêng của provider có thể tồn tại trong adapter nhưng không được rò
  rỉ vào plan entity hoặc contract API công khai.
- Hạn mức và pricing của plan provider là dữ liệu vận hành có thể thay đổi,
  không được hard-code quota thương mại vào domain hoặc tuyên bố thành SLA.
