# Luồng người dùng

## Luồng chính: từ URL video đến plan

Đây là hành trình tạo giá trị quan trọng nhất của sản phẩm.

### 1. Nhập nguồn cảm hứng

1. Mỗi lần người dùng mở Planner, UI bắt đầu ở một chat mới và không tự mở lại
   nội dung chat gần nhất. Lịch sử vẫn nằm trong sidebar để người dùng chủ động
   chọn khi muốn tiếp tục một trip cũ.
2. Chat mới chỉ mở bằng một lời mời ngắn để người dùng kể về chuyến đi hoặc nhập
   URL, không bắt đầu bằng bộ câu hỏi tuần tự. Người dùng trả lời tự nhiên trong
   ô chat; Explorer chỉ hỏi làm rõ những khoảng trống có giá trị cao khi cần.
   Thông tin đã hiểu xuất hiện ở thanh tóm tắt phía trên để user quay lại sửa
   nhanh.
3. Màn hình đầu giữ chat ở bên trái và feed **Khám phá** gồm reel/bài viết không
   có giá ở bên phải. Đây là nội dung cảm hứng, không mặc định là listing
   Marketplace. Composer của màn hình này chỉ hiển thị nhập URL; upload ảnh OCR
   không được đưa vào entry UI hiện tại.
4. Người dùng dán một hoặc nhiều URL video/nội dung tham khảo hoặc nhập địa
   điểm thủ công.
   Trong chat mới, URL được giữ cùng các câu trả lời intake rồi gửi vào cùng
   draft để hệ thống có cả nguồn địa điểm lẫn ràng buộc chuyến đi.
5. Hệ thống kiểm tra từng URL/ảnh và tạo một import job nền cho mỗi nguồn. Job
   ảnh dùng cùng hàng đợi FIFO, timeout, retry, reprocess, stop/delete và timing
   như job URL; dữ liệu ảnh không được ghi vào log.
   Ngay khi batch được chấp nhận, chat và user message đã được lưu; các job nguồn
   là tác vụ con của cùng turn nên rời màn hình không làm URL biến mất khỏi lịch sử.
6. Khi job URL chạy, chat hiển thị timer, tiến độ và nhóm mascot; feed Khám phá
   vẫn dùng được. Job tiếp tục chạy khi user rời màn hình. User có thể hủy job
   hiện tại để mở chat mới; lịch sử luôn mở được từ thanh trên hoặc itinerary.
   Dock tác vụ toàn cục mở lại đúng `/planner?chatId=...` và giữ thông báo kết
   quả cho tới khi user chọn xem.
7. UI giữ nguyên từng URL hoặc tên ảnh cùng trạng thái `đang chờ`, `đang xử lý`, `cần xác
   nhận`, `hoàn thành` hoặc `thất bại`.
8. Người dùng có thể tiếp tục bổ sung yêu cầu trong khi job chạy. Khi plan sẵn
   sàng, feed Khám phá được thay bằng itinerary và map; chatbot chuyển thành cửa
   sổ nhỏ để chỉnh sửa plan.

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
8. UI hiển thị riêng số candidate đã xác minh và candidate `needs_review`.
   Candidate chưa resolve vẫn giữ tên nguồn và lý do nhưng không được đưa vào
   Planner. Chỉ candidate `resolved` có danh tính và tọa độ đã xác minh mới được
   xếp vào lịch trình.
9. Tác vụ URL hoặc ảnh đã kết thúc chỉ hiển thị một thao tác **Chạy lại**. Dù
   lượt trước thành công hay thất bại, hệ thống chạy lại toàn bộ từ đầu với
   `forceRefresh=true`: URL bỏ qua extraction cache để chạy lại media/STT/OCR;
   ảnh dùng file gốc đã lưu để chạy lại OCR; sau đó đều chạy lại
   aggregation/dedupe, resolve và Planner. UI không yêu cầu user chọn bước kỹ
   thuật cần retry.

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
   không thể xếp, hệ thống tự tăng số ngày khi user chưa khóa duration/date.
   Khi user đã nói rõ số ngày hoặc khoảng ngày đi, hệ thống giữ duration và đưa
   phần dư vào danh sách chưa xếp; user có thể kéo card vào một ngày, mở biểu
   mẫu thêm thủ công hoặc tạo prompt yêu cầu AI xếp.
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
2. UI tách ghi chú thành hai cấp: ghi chú khu vực đặt dưới tiêu đề điểm đến
   (tổng quan, ràng buộc và giả định áp dụng cho cả hành trình) và khối ghi chú
   mở rộng dưới từng hoạt động. Trong hoạt động, một source summary chỉ đọc
   (`notes`) đi cùng nhãn provenance (`noteSources`) và hiển thị riêng với
   `personalNotes` do user chỉnh sửa. Itinerary và map popup đọc cùng ba field
   từ `PlanItem`; sửa lời nhắc cá nhân không ghi đè source summary và không ghép
   toàn bộ transcript/OCR vào note.
3. Có thể yêu cầu AI sửa một ngày, một khung giờ hoặc các item chưa khóa.
4. Mỗi chỉnh sửa ảnh hưởng route/chi phí phải kích hoạt kiểm tra lại phần liên
   quan.
5. Người dùng lưu plan, mời thành viên, chọn bản dùng offline và theo dõi tiến độ
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

## Người dùng chia sẻ bài viết du lịch

1. Từ Hồ sơ, user đang đăng nhập mở trình tạo bài và chọn `post` (ảnh) hoặc
   `reel` (video), sau đó chọn file từ thư viện điện thoại hoặc máy tính.
2. User nhập caption và bắt buộc gắn tên địa điểm. Request thiếu media, hoặc địa
   điểm chỉ có khoảng trắng, bị từ chối cả phía client và server.
3. Bài được lưu dưới danh tính user hiện tại; client không được tự khai báo tác
   giả.
4. Backend kiểm tra loại, chữ ký và kích thước file, đổi sang tên ngẫu nhiên rồi
   lưu qua media storage adapter. Sau khi đăng, nội dung xuất hiện trong lưới Hồ
   sơ và feed Khám phá công khai,
   mới nhất trước. Feed luôn hiển thị loại nội dung, tác giả và location tag.
5. Nội dung cộng đồng không mặc nhiên là listing Marketplace và không hiển thị
   giá hay tuyên bố đã được kiểm chứng như một plan creator.

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
  retry hoặc thêm địa điểm qua flow chỉnh sửa plan.
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
