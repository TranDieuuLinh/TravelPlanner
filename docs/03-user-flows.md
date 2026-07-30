# Luồng người dùng

## Luồng chính: từ URL video đến plan

Đây là hành trình tạo giá trị quan trọng nhất của sản phẩm.

### 1. Nhập nguồn cảm hứng

1. Người dùng tạo một trip mới.
2. Dán một hoặc nhiều URL video/nội dung tham khảo hoặc nhập địa điểm thủ công.
3. Hệ thống kiểm tra URL, nhận diện nền tảng và tạo import job.
4. UI giữ nguyên từng URL cùng trạng thái `đang chờ`, `đang xử lý`, `cần xác
   nhận`, `hoàn thành` hoặc `thất bại`.
5. Người dùng có thể tiếp tục bổ sung yêu cầu trong khi job chạy.

### 2. Trích xuất và xác minh nội dung

1. Importer lấy phần nội dung được phép truy cập như metadata, caption,
   transcript, khung hình hoặc văn bản trang.
2. Extraction pipeline tạo các claim có bằng chứng: tên địa điểm thô, hoạt động,
   món ăn, thời điểm nên đến, thời lượng, giá được nhắc đến và mẹo của nguồn.
3. Place Resolver tìm địa điểm chuẩn hóa cho từng ứng viên, bổ sung tọa độ,
   category, provider ID và độ mới.
4. Hệ thống gộp địa điểm trùng giữa nhiều URL nhưng vẫn giữ tất cả provenance.
5. UI hiển thị ứng viên theo ba nhóm:
   `đã khớp`, `cần chọn kết quả đúng`, `không xác định được`.
6. Người dùng xác nhận, sửa, loại bỏ hoặc thêm địa điểm. Chỉ địa điểm đã xác
   nhận mới trở thành `SelectedPlace` của Planner.
7. Import thất bại không được làm mất URL hoặc các kết quả đã trích xuất từ
   nguồn khác.

### 3. Explorer làm rõ chuyến đi

Explorer kết hợp `SelectedPlaces` với thông tin người dùng:

- ngày đi hoặc số ngày, điểm xuất phát và timezone;
- số người, thành phần nhóm và nhu cầu hỗ trợ tiếp cận;
- ngân sách, tiền tệ, nhịp độ và phong cách;
- sở thích, địa điểm bắt buộc, địa điểm tránh;
- thời gian cố định, phương tiện có thể dùng và ràng buộc cứng;
- mức ưu tiên của từng địa điểm lấy từ URL.

Nếu thiếu dữ liệu quan trọng, Explorer chỉ hỏi các câu có ảnh hưởng lớn tới khả
năng tạo plan. Câu trả lời cập nhật cùng một draft, không bắt đầu lại import.

### 4. Planner tạo Main Plan

```text
SelectedPlaces + UserState + TripConstraints
                    |
                    v
Explorer -> MacroPlan + DayBriefs
                    |
                    v
Finder Main Run -> TripDays + TripItems + Routes
                    |
                    v
CheckOverall -> Main Plan đã kiểm tra
```

1. Planner tạo `MacroPlan`: chủ đề, khu vực và mục tiêu của từng ngày.
2. Mỗi `DayBrief` mô tả khung giờ, loại hoạt động, nhịp độ và địa điểm ưu tiên.
3. Finder xếp địa điểm vào ngày và khung giờ, thêm bữa ăn, nghỉ, thời gian đệm và
   chặng di chuyển.
4. Địa điểm người dùng xác nhận được giữ lại trừ khi vi phạm ràng buộc cứng. Nếu
   không thể xếp, hệ thống phải đưa vào danh sách chưa xếp và giải thích lý do.
5. `CheckOverall` kiểm tra schema, thời gian chồng lấn, giờ hoạt động, tuyến
   đường, thời tiết khi phù hợp, mật độ, ngân sách và dữ liệu quá cũ.
6. Người dùng xem cảnh báo, giả định và bằng chứng trước khi chọn Main Plan.
7. Khi được chốt, Main Plan có version riêng; các lần chỉnh sửa tiếp theo tạo
   revision và không được thay đổi item đã khóa.

### 5. Tạo Backup Plan

```text
Original MacroPlan + Main Plan + CheckOverall Report
                         |
                         v
Backup Planner -> Backup Finder -> Validate Backup
                         |
                         v
                Backup Plan riêng biệt
```

Backup được tạo khi người dùng yêu cầu hoặc khi Main Plan có rủi ro đáng kể như
thời tiết, địa điểm đóng cửa hay tuyến đường không khả thi. Backup phải:

- có `parentPlanId` trỏ tới Main Plan;
- giải quyết các issue cụ thể trong `CheckOverall Report`;
- dùng được độc lập;
- không mutate, thay thế hoặc mở khóa Main Plan;
- giữ các ràng buộc cứng và item được người dùng yêu cầu giữ.

### 6. Chỉnh sửa và sử dụng

1. Người dùng thêm, xóa, kéo thả, đổi thời gian hoặc khóa từng item.
2. Có thể yêu cầu AI sửa một ngày, một khung giờ hoặc các item chưa khóa.
3. Mỗi chỉnh sửa ảnh hưởng route/chi phí phải kích hoạt kiểm tra lại phần liên
   quan.
4. Người dùng lưu plan, mời thành viên, chọn bản dùng offline và theo dõi tiến độ
   trong chuyến đi.

## Luồng bắt đầu không có URL

Người dùng có thể bắt đầu bằng điểm đến và yêu cầu dạng văn bản. Explorer và
Planner vẫn hoạt động bình thường; địa điểm do Finder đề xuất phải có nguồn từ
place provider. Người dùng có thể thêm URL vào draft bất kỳ lúc nào trước khi
chốt Main Plan.

## Người du lịch khám phá qua Marketplace

1. Tìm kiếm/lọc plan theo điểm đến, thời lượng, ngân sách, phong cách, đánh giá
   và độ mới.
2. Có thể khám phá listing qua feed quảng bá hỗn hợp gồm video và bài post. Hai
   loại nội dung dùng cùng card dọc; video mở trong trình xem lướt dọc, còn bài
   post giữ ảnh và caption trong cùng format. Giá plan và thao tác thêm vào giỏ
   luôn hiện trong trình xem.
3. Mở listing và kiểm tra preview, creator, ngày cập nhật, nội dung bao gồm,
   license, review và chi phí dự kiến.
4. Thêm plan vào giỏ hoặc mua qua checkout. Checkout hiện xử lý từng listing
   version để giữ liên kết phiên bản rõ ràng.
5. Nền tảng xác minh payment phía server, ghi nhận order và cấp entitlement cho
   đúng `ListingVersion` và `TripPlanVersion`.
6. Buyer tạo một bản sao cá nhân có provenance trỏ về phiên bản đã mua.
7. Buyer dùng Planner để thay đổi ngày, ngân sách, thành phần nhóm, thêm URL hoặc
   chỉnh sửa item; plan đã publish của creator không thay đổi.
8. Buyer sử dụng plan, đánh giá hoặc báo cáo khi đủ điều kiện.
9. Nếu không có listing phù hợp, ngữ cảnh tìm kiếm được chuyển sang Explorer để
   tạo plan mới.

## Nhà sáng tạo tạo và xuất bản plan

1. Đăng nhập và hoàn tất hồ sơ/xác minh creator khi được yêu cầu.
2. Bắt đầu từ URL video của chính mình, plan đã đi, bản nháp cũ hoặc plan mới.
3. Dùng cùng Importer và Planner để tạo cấu trúc ban đầu.
4. Bổ sung kiến thức địa phương, media, tuyến đường, chi phí, bằng chứng và
   Backup Plan.
5. Khóa nội dung quan trọng rồi chạy CheckOverall.
6. Tạo `TripPlanVersion` bất biến và listing draft.
7. Thêm tên, ảnh/video bìa, mô tả, đối tượng phù hợp, giá, nội dung preview,
   license, ngày cập nhật và giới hạn sử dụng.
8. Xem trước chính xác những gì buyer thấy trước và sau khi mua.
9. Gửi kiểm duyệt, publish và theo dõi view, conversion, order, review, refund
   và doanh thu.
10. Phiên bản mới không làm thay đổi version gắn với order cũ.

## Các luồng ngoại lệ quan trọng

- URL không được hỗ trợ hoặc nội dung riêng tư: giữ URL, nêu lý do và cho phép
  nhập caption/địa điểm thủ công.
- Không truy cập được caption/transcript: xử lý phần metadata có sẵn và đánh dấu
  dữ liệu còn thiếu; không giả vờ đã hiểu toàn bộ video.
- Độ tin cậy thấp hoặc nhiều địa điểm trùng tên: yêu cầu người dùng chọn, không
  tự động commit vào plan.
- Nội dung chứa prompt injection: coi là dữ liệu nguồn, không phải instruction.
- Provider timeout: giữ draft và kết quả từng phần, cho phép retry riêng job.
- Địa điểm đóng cửa hoặc route không khả thi: chỉ rõ item, bằng chứng và phương
  án sửa có phạm vi.
- Không xếp được tất cả địa điểm: đưa vào `UnscheduledPlace`, không âm thầm bỏ.
- Payment chờ hoặc thất bại: không cấp entitlement trước xác nhận server.
- Webhook lặp: không tạo trùng order, payment hoặc entitlement.
- Chỉnh sửa offline xung đột: giữ thay đổi và yêu cầu host xử lý.
- Listing có version mới: giữ nguyên snapshot buyer đã mua và cung cấp lựa chọn
  cập nhật rõ ràng.
