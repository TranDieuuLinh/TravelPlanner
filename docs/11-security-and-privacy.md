# Bảo mật và quyền riêng tư

## Tài sản nhạy cảm

- thông tin đăng nhập và OAuth token;
- ngày đi, điểm đến, thành viên nhóm và URL plan riêng tư;
- danh tính creator và thông tin nhận tiền;
- hồ sơ payment/order/refund;
- nội dung được nhập riêng tư và prompt của user;
- dữ liệu vị trí/tiến độ có thể tiết lộ user đang hoặc sẽ ở đâu.

## Xác thực và phân quyền

- Dùng thuật toán hash mật khẩu tiêu chuẩn hoặc nhà cung cấp danh tính đáng tin.
- Khi phù hợp, lưu session trong cookie secure, HTTP-only và same-site.
- Backend phải kiểm tra quyền cho mọi private plan, listing draft, order,
  entitlement, review, creator metric và hành động admin.
- Mô hình hóa rõ quyền của thành viên trip.
- Yêu cầu xác thực bổ sung khi thay đổi payout, email, mật khẩu hoặc thực hiện
  thao tác tài khoản có tính phá hủy.

Trường role hiện tại không đủ để làm hệ thống phân quyền hoàn chỉnh.

## API và hạ tầng

- Validate payload và giới hạn kích thước request/body.
- Rate limit authentication, AI generation, nhập URL, search và checkout.
- Ngoài môi trường trên máy cá nhân, chỉ cho phép CORS từ origin đã biết.
- Lưu secret trong biến môi trường/secret manager, không đưa vào source control.
- Pin, quét dependency và container image.
- Backup database và kiểm tra quy trình restore.
- Dùng audit event cho kiểm duyệt, refund, entitlement và thay đổi đặc quyền.
- **Cơ chế bảo mật đã triển khai trong Backend MVP**:
  - Global Security Headers middleware (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection: 1; mode=block`, `Referrer-Policy`, `HSTS`).
  - In-memory Rate Limiting cho các endpoint nhạy cảm như Đăng ký (`/api/auth/register`), Đăng nhập (`/api/auth/login`), Tạo Checkout (`/api/checkout-sessions`).
  - Lọc thông tin nhạy cảm trong metadata nhật ký kiểm toán (`password`, `jwt`, `token`, `secret`, `authorization`).

## Nhập URL và AI

- Chống SSRF bằng cách chặn địa chỉ local, private, metadata và non-HTTP.
- Web-page connector resolve DNS và kiểm tra toàn bộ địa chỉ là public trước
  request đầu tiên và trước từng redirect; URL có userinfo bị từ chối.
- Giới hạn redirect, content type, response size và thời gian fetch.
- Chỉ dùng connector đã cho phép; không vượt qua đăng nhập, nội dung riêng tư
  hoặc cơ chế kiểm soát truy cập của nền tảng nguồn.
- Chỉ lưu artifact cần thiết và được phép. Ưu tiên source reference, claim và
  evidence ngắn thay vì sao chép toàn bộ video/transcript.
- Xem văn bản trang/video là nội dung không đáng tin và cô lập khỏi system
  prompt.
- Không để claim confidence thấp tự động trở thành `SelectedPlace`; lưu dấu vết
  xác nhận/sửa đổi của user.
- Không để lộ hidden prompt, secret, private plan hoặc nội dung của user khác cho
  model.
- Validate model output trước provider call hoặc trước khi lưu.
- Yêu cầu xác nhận cho hành động có hậu quả; không cho model tuyên bố
  booking/payment/liên hệ đã thành công.

## Chợ lịch trình và thanh toán

- Dùng trang thu thập thanh toán của provider; không lưu dữ liệu thẻ thô.
- Xác minh chữ ký webhook, event ID, số tiền, tiền tệ và order mapping.
- Xử lý webhook phải idempotent.
- Chỉ cấp entitlement sau xác nhận thanh toán phía server.
- Giữ phiên bản đã mua để xử lý tranh chấp và refund.
- Tách số dư creator thành pending, available, paid và reversed.
- Có luồng moderation, report, takedown và refund trước khi mở publish tự do.

## Quyền riêng tư

- Chỉ thu thập dữ liệu cần thiết cho tính năng.
- Bài `post`/`reel` trên Hồ sơ là nội dung công khai: giao diện phải báo rõ trước
  khi đăng; backend lấy tác giả từ session, yêu cầu CSRF, bắt buộc location tag,
  giới hạn kích thước, allowlist MIME, kiểm tra chữ ký file và thay tên gốc bằng
  UUID. Không suy diễn location tag thành vị trí thời gian thực.
- Giải thích lý do cần vị trí, contact, media hoặc URL được nhập.
- Mặc định plan và thành viên nhóm ở trạng thái riêng tư.
- Trip chat luôn được query bằng cả chat ID và authenticated user ID. Message
  history và plan snapshot là dữ liệu riêng tư; ảnh upload chỉ xử lý trong
  request, database chỉ lưu tên attachment chứ không lưu bytes.
- URL job của guest chỉ giữ URL, trạng thái, timing và kết quả plan trong memory
  của tab; không tạo trip chat hoặc job row trong database và bị xóa khi reload
  hoặc đóng tab. Endpoint intake vẫn phải áp dụng validation URL/SSRF như luồng
  authenticated.
- Xác định thời gian lưu prompt, nội dung nguồn, log, lịch sử trip và hồ sơ tài
  chính.
- Hỗ trợ export và xóa dữ liệu khi pháp luật cho phép.
- Không theo dõi vị trí chính xác trừ khi user chủ động bật và tính năng thực sự
  cần.
- Nút “Vị trí của tôi” chỉ gọi browser `getCurrentPosition` sau thao tác chủ
  động của user, cập nhật marker và đưa camera về user đúng một lần; Planner
  không dùng Geolocation watch. Tọa độ chỉ được chuyển tiếp cho route provider
  khi user bấm “Chỉ đường” hoặc “Tính lại” ở một ngày cụ thể. Vị trí và route
  điều hướng chỉ giữ trong memory của trang, không lưu vào plan/database/log.
- Điểm bắt đầu user tìm trong Places tuân theo cùng phạm vi tạm thời: tên và tọa
  độ chỉ dùng để tính/hiển thị tuyến trong phiên trang, không được thêm vào plan.
- Loại bỏ dữ liệu cá nhân khỏi log và analytics.
- Traveler Profile chỉ lưu preference du lịch đã chuẩn hóa, confidence, nguồn
  và intake reference; không lưu raw prompt/OCR/transcript trong signal. Trait
  nhạy cảm không được tự suy luận. User có API xem, sửa preference explicit và
  xóa toàn bộ profile dài hạn.
- Planning Control chỉ dành cho role `admin`. Snapshot planning run không lưu
  raw media, toàn bộ prompt/transcript, secret hay query string URL; raw request
  chỉ được biểu diễn bằng số ký tự và trạng thái có/không.

Phải thực hiện threat model trước khi phát hành authentication, URL fetching,
payment, collaboration hoặc nội dung creator công khai.
