# Phạm vi MVP

## Kết quả cần đạt

Người dùng có thể tạo hoặc mua một lịch trình đáng tin cậy, chỉnh sửa, xem địa
điểm trên bản đồ và lưu để sử dụng trong chuyến đi. Creator có thể xuất bản và
bán plan. Nhân sự vận hành có thể quản lý các rủi ro Marketplace tối thiểu.

## Trong phạm vi

### Nền tảng cơ bản

- Authentication bằng email và hồ sơ người dùng.
- Quyền traveler và creator với authorization phía server.
- Nhập điểm đến/yêu cầu và hỗ trợ một loại URL tham khảo.

### Công cụ lập kế hoạch

- Lịch trình AI có cấu trúc theo ngày và từng mục.
- Các phương án cơ bản hoặc một plan chính kèm plan dự phòng rõ ràng.
- Chỉnh sửa thủ công: thêm, xóa, đổi thứ tự, đổi thời gian và khóa địa điểm.
- Lưu plan trong PostgreSQL.
- Hiển thị marker và tuyến đường trên bản đồ.
- Gợi ý thời gian và phương tiện di chuyển.
- Cảnh báo cơ bản về tính khả thi.

### Sử dụng trong chuyến đi

- Giao diện lịch trình responsive.
- Truy cập offline ở chế độ đọc cho một plan đã chọn.
- Trạng thái hoàn thành/tiến độ đơn giản.

### Chợ lịch trình

- Creator tạo bản nháp, preview, listing, publish/unpublish và snapshot phiên bản.
- Duyệt listing, tìm kiếm, lọc và xem preview chi tiết.
- Checkout qua một nhà cung cấp thanh toán.
- Order và tạo bản sao cá nhân từ plan đã mua.
- Rating/review từ buyer đủ điều kiện.
- Creator dashboard cơ bản: lượt xem, lượt mua, đánh giá và doanh thu.

### Vận hành

- Giao diện admin cho user, creator, listing, order, report và refund.
- Trạng thái xác minh creator.
- Audit trail cơ bản và xử lý báo cáo nội dung.

## Ngoài phạm vi MVP

- Hỗ trợ nhiều mạng xã hội và hiểu đầy đủ nội dung video.
- Chỉnh sửa nhiều người theo thời gian thực; ban đầu chỉ cần mời thành viên và
  đồng bộ đơn giản.
- Tự động gọi điện, nhắn tin, đặt bàn hoặc thực hiện booking.
- Tổng hợp booking từ nhiều provider.
- Remix thương mại và chia royalty tự động.
- Subscription phức tạp và nhiều phương thức thanh toán.
- Bản đồ thành tựu nâng cao, nền kinh tế điểm và xếp hạng xã hội.
- Tối ưu hoàn toàn tuyến đường cho mọi phương tiện.
- Định giá động, xếp hạng gợi ý và phân khúc người xem của creator.

## Tín hiệu nghiệm thu MVP

- Traveler mới có thể lưu một plan hợp lệ mà không cần nhân sự hỗ trợ.
- Chỉnh sửa được lưu và địa điểm đã khóa không bị thay đổi khi AI sửa plan.
- Bản đồ và lịch trình dùng cùng ID địa điểm và cùng thứ tự.
- Buyer không thể truy cập nội dung trả phí trước khi thanh toán được xác nhận.
- Order luôn trỏ tới phiên bản listing/plan bất biến.
- Creator có thể xuất bản phiên bản mới mà không thay đổi giao dịch cũ.
- Plan đã chọn vẫn mở được sau khi thiết bị mất kết nối.
- Admin có thể truy vết và xử lý listing bị báo cáo hoặc giao dịch thất bại.

## Quy tắc phạm vi

Các tính năng trong báo cáo nguồn là tầm nhìn sản phẩm nếu không nằm trong mục
“Trong phạm vi”. Mọi bổ sung vào MVP phải chỉ ra hạng mục nào bị thay thế hoặc lý
do cần thay đổi ranh giới phát triển.
