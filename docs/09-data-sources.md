# Nguồn dữ liệu và tích hợp

## Nguyên tắc

- Domain model của ứng dụng không được phụ thuộc payload riêng của provider.
- Ghi nguồn, provider ID, thời điểm lấy, giới hạn license và độ tin cậy.
- Ưu tiên dữ liệu mới từ provider cho thông tin vận hành và kinh nghiệm creator
  cho nội dung trải nghiệm.
- Không được tuyên bố hành động như booking hoặc gọi điện đã hoàn thành nếu chưa
  có xác nhận từ provider.

## Nhóm dữ liệu bắt buộc

| Nhóm | Dữ liệu cần thiết | Mối quan tâm chính |
| --- | --- | --- |
| Địa điểm | danh tính, tọa độ, danh mục, giờ mở cửa, trạng thái | độ mới, trùng lặp |
| Bản đồ/tuyến | khoảng cách, thời lượng, geometry, phương tiện | chi phí, độ phủ, quota |
| Thời tiết | dự báo và điều kiện nguy hiểm | thời hạn dự báo, độ bất định |
| Nhập URL | văn bản, metadata media, địa điểm ứng viên | quyền truy cập, bản quyền, injection |
| Booking | tình trạng còn chỗ, giá, deep link/trạng thái | attribution, giá cũ |
| Thanh toán | checkout, webhook, refund, payout | tuân thủ, idempotency |
| Media | ảnh/video của creator | bản quyền, kiểm duyệt, lưu trữ |

## Tiêu chí chọn nhà cung cấp

- độ phủ địa điểm và tuyến đường tại Việt Nam;
- hỗ trợ đi bộ, lái xe, giao thông công cộng và phương tiện địa phương;
- giá theo lưu lượng request dự kiến;
- điều khoản về cache/lưu trữ và attribution;
- độ ổn định API, độ trễ, quota và khả năng fallback;
- UI bản đồ dễ tiếp cận và ràng buộc offline;
- ảnh hưởng đến quyền riêng tư và vị trí lưu dữ liệu.

Map provider chưa được lựa chọn. Xem ADR-002.

## Nhập dữ liệu từ URL

Xem nội dung được nhập là dữ liệu không đáng tin cậy, không bao giờ là system
instruction.

1. Kiểm tra scheme và chặn địa chỉ mạng private/internal.
2. Fetch qua service được kiểm soát với giới hạn kích thước, redirect và timeout.
3. Phát hiện loại nguồn và tuân thủ điều khoản/quyền truy cập của nền tảng.
4. Trích xuất địa điểm ứng viên, caption, ngày và các claim.
5. Chuẩn hóa địa điểm qua place provider.
6. Hiển thị độ tin cậy và yêu cầu user xác nhận kết quả không chắc chắn.
7. Giữ attribution và chỉ lưu nội dung được license/chính sách cho phép.

MVP bắt đầu với một loại nguồn hợp pháp, khả thi về kỹ thuật và các trang web
công khai thông thường. “Dán bất kỳ URL Reel/TikTok/Facebook nào” là khả năng mục
tiêu, không phải lời hứa đáng tin cậy của MVP.

## Độ mới dữ liệu

- Trạng thái hoạt động, giờ mở cửa, thời gian tuyến đường, tình trạng còn chỗ và
  giá phải có thời điểm lấy.
- Kiểm tra lại dữ liệu vận hành khi mở plan cũ và trước chuyến đi.
- Mẹo của creator có thể được giữ dưới dạng nội dung có version nhưng phải hiển
  thị ngày cập nhật plan.
- Nếu không thể làm mới dữ liệu, phải hiển thị trạng thái cũ thay vì che giấu.

## Tích hợp đặt dịch vụ

Bắt đầu bằng deep link hoặc một tích hợp đối tác. Tách nội dung lịch trình khỏi
xếp hạng thương mại, công khai nội dung tài trợ và đo tỷ lệ chuyển đổi từ lịch
trình
đến booking mà không âm thầm thay đổi tuyến đường của user.
