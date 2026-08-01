# ADR-009: Caption-first transcript cho YouTube

- Trạng thái: Accepted
- Ngày: 2026-07-31

## Bối cảnh

Pipeline URL video trước đây luôn tải media, tách audio rồi gửi audio tới Gemini
STT. Cách này tốn băng thông, tăng latency và dùng quota model dù nhiều video
YouTube đã có caption thủ công hoặc tự sinh. Gemini áp rate limit theo project,
vì vậy xoay nhiều API key không phải là cơ chế đảm bảo tăng quota.

`youtube-transcript-api` đọc caption từ web client không cần API key hay trình
duyệt headless. Đây là API YouTube không được công bố chính thức, có thể bị chặn
theo IP hoặc thay đổi mà không báo trước, nên không thể là đường xử lý duy nhất.

## Quyết định

1. URL YouTube hợp lệ thử caption bằng `youtube-transcript-api` trước, ưu tiên
   danh sách ngôn ngữ của intake và fallback sang caption khả dụng đầu tiên.
2. Caption rỗng, bị tắt, không tồn tại, video không truy cập được hoặc request bị
   chặn đều trả quyền điều khiển về pipeline hiện có:
   `yt-dlp -> ffmpeg -> Gemini Audio STT`.
3. Khi caption thành công, không tải video và không gọi Gemini STT/frame vision.
   Kết quả ghi `speechToText.source=youtube_captions`; fallback Gemini ghi
   `source=gemini_audio`.
4. Media chỉ nằm trong thư mục tạm và bị xóa sau request như trước.
5. Gemini STT fallback mặc định một request đồng thời và khoảng cách khởi chạy
   sáu giây trong mỗi tiến trình. `429` dùng `Retry-After` với trần 60 giây.
   Concurrency có thể cấu hình tăng sau khi operator xác minh quota project.
6. Không tự động cấu hình proxy hoặc cookie để vượt giới hạn truy cập của
   YouTube. Nội dung private, age-restricted hoặc cần đăng nhập vẫn được coi là
   unavailable và dùng fallback hợp lệ/manual input.

## Hệ quả

- Video có caption không dùng quota Gemini STT và không cần download media.
- Caption YouTube không có structured travel observations; Extractor chỉ dùng
  nó như transcript evidence. Structured observations vẫn đến từ Gemini khi
  chạy audio fallback.
- Video có thông tin chỉ xuất hiện trên hình có thể cần screenshot do user tải
  lên khi caption-first đã đủ để bỏ qua media.
- Limiter là trong từng process. Triển khai nhiều worker cần limiter phân tán
  hoặc quota gateway nếu cần đảm bảo RPM toàn hệ thống.
- Cần theo dõi version `youtube-transcript-api` vì connector phụ thuộc endpoint
  web không được YouTube cam kết ổn định.
