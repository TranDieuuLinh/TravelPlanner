# Phạm vi MVP

## Kết quả cần đạt

MVP phải chứng minh được hai hành trình hoàn chỉnh:

1. Traveler đưa URL video/nội dung tham khảo vào hệ thống và nhận một plan có
   nguồn, khả thi, chỉnh sửa được, có Main Plan và Backup Plan.
2. Creator tạo, xuất bản và bán plan; buyer thanh toán, nhận đúng phiên bản đã
   mua, tạo bản sao cá nhân và tiếp tục tùy chỉnh bằng Planner.

Marketplace và Planner đều thuộc MVP. Có thể phát triển theo các mốc khác nhau,
nhưng MVP chỉ hoàn thành khi cả hai hành trình vượt qua tiêu chí nghiệm thu.

## Trong phạm vi

### Nền tảng cơ bản

- Authentication bằng email và hồ sơ người dùng.
- Quyền traveler, host, creator, buyer và admin được kiểm tra phía server.
- Trip riêng tư, thành viên với quyền host/editor/viewer và audit cơ bản.
- Lưu plan, version, import, listing, order và entitlement trong PostgreSQL.
- Background job có retry giới hạn, tiến độ và khả năng khôi phục lỗi.

### Nhập URL và hiểu nguồn cảm hứng

- Nhập một hoặc nhiều URL cho cùng trip.
- Hỗ trợ end-to-end ít nhất một nguồn video ngắn ưu tiên và URL trang công khai
  thông thường; nguồn cụ thể phải được xác nhận bằng ADR về khả năng kỹ thuật,
  điều khoản và chi phí.
- Nhận diện nguồn, lấy metadata/nội dung được phép, caption hoặc transcript khi
  có và ghi nhận phần dữ liệu không truy cập được.
- Trích xuất place candidate, hoạt động, món ăn, thời điểm, thời lượng, giá được
  nhắc đến, mẹo và claim có bằng chứng.
- Place resolution, gộp trùng, độ tin cậy và provenance cho từng kết quả.
- Luồng intake hiện tại tự động lưu candidate và kết quả resolve mà không chặn
  để hỏi lại user; trạng thái `resolved`, `provisional` hoặc `unresolved` phải
  được giữ để UI/Planner không coi dữ liệu yếu là đã xác minh.
- Giữ kết quả từng phần và fallback thủ công khi URL không được hỗ trợ, riêng tư
  hoặc provider lỗi.
- Chống SSRF, giới hạn fetch và cô lập nội dung nguồn khỏi instruction của AI.

### Explorer và Planner

- Nhập điểm đến, ngày/số ngày, điểm xuất phát, nhóm đi, ngân sách, tiền tệ, nhịp
  độ, sở thích, phương tiện, nhu cầu tiếp cận và ràng buộc cứng.
- Câu hỏi làm rõ có giá trị cao, cập nhật cùng draft.
- Tạo `MacroPlan` và `DayBrief` trước khi điền lịch chi tiết.
- Tạo `Main Plan` theo ngày với item ổn định, khung giờ, thời lượng, place, chi
  phí, nguồn và ghi chú.
- Finder ưu tiên `SelectedPlaces`, gom khu vực hợp lý và đưa địa điểm chưa xếp
  được vào danh sách có lý do.
- Hiển thị marker, route, khoảng cách, thời gian và phương tiện giữa các item.
- Thêm khoảng đệm, bữa ăn/nghỉ và timezone địa phương.
- Structured output, schema validation và không dùng văn bản tự do làm dữ liệu
  vận hành duy nhất.

### Kiểm tra và Backup Plan

- Kiểm tra thời gian chồng lấn, mật độ, ngân sách, giờ hoạt động, place identity,
  route, dữ liệu cũ và ràng buộc cứng.
- Hiển thị issue theo mức độ, bằng chứng, item bị ảnh hưởng và hành động sửa.
- Làm mới dữ liệu vận hành trước khi chốt hoặc mở lại plan cũ.
- Tạo Backup Plan từ Main Plan và CheckOverall Report.
- Backup là plan riêng có `parentPlanId`, có thể dùng độc lập và không mutate
  Main Plan.
- Cho phép chấp nhận, bỏ qua có cảnh báo hoặc sửa từng issue có phạm vi.

### Editor và sử dụng trong chuyến đi

- Thêm, xóa, kéo thả, đổi ngày/giờ, khóa item và hoàn tác thay đổi gần nhất.
- AI revision theo ngày, khung giờ hoặc item chưa khóa; luôn bảo toàn item khóa.
- Version history cơ bản, optimistic concurrency và khôi phục version.
- Giao diện lịch trình và bản đồ responsive.
- Truy cập offline ở chế độ đọc cho plan đã chọn.
- Trạng thái hoàn thành/tiến độ đơn giản.

### Marketplace cho creator

- Creator profile và trạng thái xác minh.
- Tạo plan từ URL, Planner, plan cũ hoặc nhập thủ công.
- Listing draft, media, preview trước/sau mua, giá, license và metadata.
- Check trước publish, moderation tối thiểu, publish/unpublish và version.
- Version đã publish là bất biến; update tạo version mới.
- Dashboard cơ bản: view, conversion, order, review, refund và doanh thu.

### Marketplace cho buyer

- Duyệt, tìm kiếm, lọc, favorite và xem listing detail.
- Preview đủ để ra quyết định nhưng không lộ toàn bộ nội dung trả phí.
- Checkout qua một payment provider.
- Order, payment webhook idempotent, refund và entitlement.
- Bản sao cá nhân từ đúng plan version đã mua.
- Buyer có thể đưa bản sao vào Planner để đổi ràng buộc hoặc thêm URL.
- Rating/review từ buyer đủ điều kiện và luồng report.

### Vận hành

- Admin quản lý user, creator, listing, order, report và refund.
- Audit trail cho publish, moderation, payment, entitlement và hành động admin.
- Rate limit, telemetry job/provider và cảnh báo lỗi tích hợp.
- Quy trình xử lý nội dung lỗi thời, vi phạm hoặc tranh chấp.
- **Trạng thái triển khai MVP Marketplace (Người C - Tuần 1 đến Tuần 6)**: Toàn bộ backend đã được triển khai hoàn chỉnh (Auth JWT HTTP-Only, Creator Application, Marketplace Listings & Versioning bất biến, Thanh toán MoMo Sandbox IPN Anti-replay, Cấp quyền Entitlement & Copy Plan cá nhân, Đánh giá Review, Báo cáo Report, Hoàn tiền Refund bảo toàn bản copy, và Nhật ký kiểm toán Audit Logs tự động che giấu thông tin nhạy cảm).

## Ngoài phạm vi MVP

- Cam kết hỗ trợ mọi URL TikTok/Reels/Facebook bất kể quyền truy cập hoặc thay đổi
  nền tảng; MVP chỉ cam kết các connector đã công bố.
- Tự động hiểu hoàn hảo mọi chi tiết hình ảnh/âm thanh khi không có đủ bằng
  chứng.
- Chỉnh sửa nhiều người theo thời gian thực; MVP dùng đồng bộ có version.
- Tự động gọi điện, nhắn tin, đặt bàn hoặc hoàn thành booking.
- Tổng hợp booking từ nhiều provider.
- Remix thương mại và chia royalty tự động.
- Subscription phức tạp và nhiều payment provider.
- Tối ưu tuyến đường toàn cục cho mọi loại phương tiện.
- Định giá động và recommendation cá nhân hóa nâng cao.
- Thành tựu, điểm thưởng và mạng xã hội nâng cao.

## Tín hiệu nghiệm thu Planner

- URL hợp lệ tạo import job có trạng thái và không làm mất dữ liệu khi retry.
- Mỗi địa điểm trích xuất có source/evidence/confidence. Intake tự động lưu mọi
  candidate, nhưng địa điểm không chắc chắn giữ trạng thái
  `provisional`/`unresolved` và không được mô tả như dữ liệu provider đã xác minh.
- Traveler có thể đi từ URL đến Main Plan hợp lệ mà không cần nhân sự hỗ trợ.
- Địa điểm đã xác nhận được xếp vào plan hoặc xuất hiện trong danh sách chưa xếp
  kèm lý do.
- Plan vượt qua schema/domain check; issue từ provider có bằng chứng và hành
  động sửa.
- Chỉnh sửa được lưu và item đã khóa không bị AI thay đổi.
- Bản đồ và lịch trình dùng cùng place ID và cùng thứ tự route.
- Backup Plan dùng được độc lập và không thay đổi Main Plan.
- Plan đã chọn vẫn mở được ở chế độ đọc khi thiết bị mất kết nối.

## Tín hiệu nghiệm thu Marketplace

- Creator có thể tạo plan, preview, publish và phát hành version mới.
- Buyer không thể truy cập nội dung trả phí trước khi payment được xác nhận.
- Order luôn trỏ tới `ListingVersion` và `TripPlanVersion` bất biến.
- Mỗi payment event chỉ cấp entitlement một lần.
- Buyer nhận bản sao cá nhân, có thể chỉnh bằng Planner mà không sửa plan creator.
- Chỉ buyer đủ điều kiện mới được review; report/refund tạo audit event.
- Admin có thể truy vết một giao dịch và xử lý listing bị báo cáo.

## Quy tắc phạm vi

“Làm đầy đủ Planner và Marketplace trong MVP” nghĩa là hoàn thành các hành trình
và bất biến trên, không đồng nghĩa với hỗ trợ mọi provider hoặc mọi khả năng nâng
cao ngay phiên bản đầu. Mọi bổ sung phải nêu rõ tiêu chí nghiệm thu nào được phục
vụ và chi phí/phạm vi nào bị thay thế.
