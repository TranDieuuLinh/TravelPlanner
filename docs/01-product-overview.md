# Tổng quan sản phẩm

## Tầm nhìn

Xây dựng một nền tảng biến video và nội dung du lịch người dùng tìm thấy trên
mạng thành lịch trình cá nhân hóa, có nguồn, có thể kiểm tra và sử dụng thực tế.
Creator có thể dùng cùng năng lực này để đóng gói kinh nghiệm thành plan có
version, xuất bản và bán trên Marketplace.

Chuỗi giá trị chính của sản phẩm là:

```text
URL/nội dung tham khảo
-> trích xuất ngữ cảnh và địa điểm
-> xác minh với người dùng và provider
-> tạo Main Plan
-> kiểm tra tính khả thi
-> tạo Backup Plan khi cần
-> chỉnh sửa, lưu và sử dụng
```

## Vấn đề

Các công cụ AI Travel Planner hiện tại có thể tạo gợi ý, nhưng thường dừng lại
trước khi lịch trình trở thành một kế hoạch có thể sử dụng thực tế. Báo cáo
nghiên cứu chỉ ra các khoảng trống thường gặp:

- chỉ tạo một plan nên người dùng khó so sánh;
- lộ trình và thời gian di chuyển không rõ ràng hoặc chưa được tối ưu;
- thiếu phương tiện di chuyển cụ thể giữa các địa điểm;
- người dùng không thể kéo thả, khóa, xóa hoặc chỉnh sửa từng mục một cách tin
  cậy;
- chức năng đặt chỗ chỉ dừng ở hướng dẫn thay vì hoàn thành tác vụ;
- thiếu cộng tác nhóm và sử dụng offline;
- chưa chuyển được liên kết video mạng xã hội thành dữ liệu chuyến đi có cấu trúc;
- kiến thức của creator chưa có Marketplace, cơ chế cấp quyền và luồng cập nhật
  tích hợp sẵn.

Cơ hội của sản phẩm là nối hai thế giới hiện đang tách rời: nguồn cảm hứng dạng
video/nội dung phi cấu trúc và một kế hoạch có thể đi theo thật. Marketplace mở
rộng chuỗi giá trị đó bằng cách cho phép creator bán plan và cho buyer tiếp tục
cá nhân hóa bằng cùng Planner.

## Trụ cột sản phẩm

1. **Biến nguồn cảm hứng thành dữ liệu:** nhập URL video/nội dung, trích xuất
   địa điểm, hoạt động, thời điểm, claim và mẹo; giữ bằng chứng, nguồn và độ tin
   cậy để người dùng xác nhận.
2. **Lập kế hoạch nhiều giai đoạn:** kết hợp địa điểm đã xác nhận với ngày đi,
   ngân sách, nhịp độ, sở thích và ràng buộc để tạo MacroPlan, DayBrief, Main
   Plan và Backup Plan.
3. **Lịch trình có thể sử dụng thực tế:** hiển thị tuyến đường, thời gian di
   chuyển, phương tiện, chi phí và cảnh báo; cho phép chỉnh sửa thủ công hoặc bằng
   AI theo phạm vi cụ thể.
4. **Marketplace đáng tin cậy:** có preview, lịch sử phiên bản, độ mới, danh tính
   creator, đánh giá, báo cáo và chính sách hoàn tiền.
5. **Kinh tế creator:** hỗ trợ xuất bản, analytics, doanh thu giao dịch và tùy
   chọn cấp quyền remix thương mại một cấp.
6. **Đồng hành trong chuyến đi:** cộng tác, truy cập offline, theo dõi tiến độ và
   thành tựu sau chuyến đi.

## Lời hứa của Planner

Planner phải trả lời được ba câu hỏi:

1. Nội dung nguồn đang nói đến địa điểm hoặc trải nghiệm nào, và bằng chứng là
   gì?
2. Những địa điểm nào người dùng thực sự muốn giữ lại cho chuyến đi?
3. Có thể sắp xếp chúng thành lịch trình phù hợp thời gian, tuyến đường, ngân
   sách và điều kiện thực tế hay không?

Planner không được coi URL là prompt đáng tin cậy, không tự bịa địa điểm khi
không đủ bằng chứng và không âm thầm loại bỏ địa điểm người dùng đã xác nhận.
Khi có xung đột, hệ thống phải giải thích, đề xuất thay thế hoặc tạo Backup Plan
riêng.

## Nhóm người dùng

- **Traveler/host:** tự tổ chức chuyến đi hoặc lập kế hoạch cho nhóm.
- **Buyer:** khám phá và mua plan của creator, sau đó cá nhân hóa một bản sao.
- **Creator:** chuyển kinh nghiệm hoặc nội dung du lịch thành plan để bán.
- **Admin/operator:** quản lý người dùng, creator, nội dung, tranh chấp và thanh
  toán.

Một tài khoản có thể đồng thời là traveler, host, buyer và creator ở các thời
điểm khác nhau. Role nên đại diện cho quyền hạn, không phải các danh tính tách
biệt vĩnh viễn.

## Giả thuyết mô hình kinh doanh

- Phí giao dịch Marketplace: giả thuyết mục tiêu 15-20%.
- Remix thương mại: ví dụ chia 70% cho creator remix, 10% cho creator gốc và 20%
  cho nền tảng; chỉ hỗ trợ một cấp royalty.
- Gói sử dụng: miễn phí, trả tiền theo từng plan và thuê bao tháng/năm cho creator
  hoặc người dùng thường xuyên.
- Hoa hồng booking/đối tác từ lưu trú, hoạt động, phương tiện, bảo hiểm, eSIM và
  nhà hàng.

Đây là các giả thuyết cần kiểm chứng, chưa phải mức giá đã cam kết. Cần đo mức độ
sẵn sàng chi trả và lợi nhuận đóng góp trước khi mở rộng độ phức tạp của thanh
toán.

## Chỉ số thành công

- tỷ lệ URL được nhập thành công và có ít nhất một place candidate hữu ích;
- tỷ lệ place candidate được người dùng xác nhận;
- tỷ lệ từ URL đến Main Plan hợp lệ;
- thời gian từ lúc dán URL đến lúc có bản nháp plan đầu tiên;
- tỷ lệ plan vượt qua kiểm tra route, giờ hoạt động và ràng buộc cứng;
- tỷ lệ từ tạo plan đến lưu plan;
- tỷ lệ từ lịch trình đến booking;
- tỷ lệ plan được chỉnh sửa thủ công sau khi tạo;
- mức độ hoàn thành chuyến đi và sử dụng offline;
- tỷ lệ từ xem preview đến mua trên Marketplace;
- tỷ lệ hoàn tiền và báo cáo;
- tỷ lệ traveler và creator quay lại;
- độ mới và điểm đánh giá của plan creator;
- lợi nhuận đóng góp trên mỗi giao dịch.

## Nguồn và cách bảo trì

Tài liệu này tổng hợp từ `travel_plan_report.docx` do đội dự án cung cấp và trạng
thái kho mã được kiểm tra ngày 2026-07-27. Khi sản phẩm thay đổi, phải cập
nhật tài liệu này và phạm vi MVP nếu có liên quan.
