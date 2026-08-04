# ADR-009: Caption-only transcript cho YouTube long-form

- Trạng thái: Accepted
- Ngày: 2026-07-31
- Cập nhật: 2026-08-03

## Bối cảnh

Pipeline URL video trước đây luôn tải media, tách audio rồi gửi audio tới Gemini
STT. Cách này tốn băng thông, tăng latency và dùng quota model dù nhiều video
YouTube đã có caption thủ công hoặc tự sinh. Gemini áp rate limit theo project,
vì vậy xoay nhiều API key không phải là cơ chế đảm bảo tăng quota.

`youtube-transcript-api` đọc caption từ web client không cần API key hay trình
duyệt headless. Đây là API YouTube không được công bố chính thức, có thể bị chặn
theo IP hoặc thay đổi mà không báo trước, nên không thể là đường xử lý duy nhất.

## Quyết định

1. URL YouTube long-form hợp lệ kiểm tra cache PostgreSQL theo
   `videoId + language`, sau đó
   thử caption bằng `youtube-transcript-api`, ưu tiên danh sách ngôn ngữ của
   intake và fallback sang caption khả dụng đầu tiên. Caption thành công được
   cache dài hạn; lỗi provider không được cache.
2. Request provider được giới hạn nhịp và request đồng thời cho cùng video được
   dedupe trong mỗi process. Nếu IP backend bị chặn hoặc provider unavailable,
   runtime có thể gọi HTTP transcript worker do operator tự vận hành trên kết
   nối dân dụng, xác thực bằng shared bearer token. Worker chỉ nhận video ID và
   language list; không nhận cookie người dùng.
3. `no_captions` của YouTube long-form trả HTTP 422
   `YOUTUBE_CAPTIONS_NOT_FOUND`. `blocked` và
   `unavailable` trả lỗi retryable `YOUTUBE_CAPTIONS_UNAVAILABLE` sau worker.
   Không trạng thái nào tải YouTube media hoặc gọi audio STT.
4. YouTube long-form không gọi `yt-dlp` để lấy metadata, không tải video và
   không gọi Gemini audio STT/frame vision. Runtime chỉ giữ URL chuẩn hóa cùng
   platform rồi đưa caption qua Gemini structured text extraction đa ngôn ngữ;
   tên riêng được giữ nguyên và entity được phân loại trước resolver. Việc thiếu
   title, description, chapter, thumbnail hoặc uploader không được chặn import.
   YouTube Shorts vẫn dùng metadata và media pipeline của Reel.
   Kết quả ghi `speechToText.source=youtube_captions`; cache hit ghi
   `source=youtube_captions_cache`.
5. URL YouTube có path `/shorts/{videoId}` được nhận diện là
   `youtube_shorts` và dùng pipeline media ngắn hiện có: audio STT song song với
   sampled-frame vision/OCR. URL `youtu.be/{videoId}` không mang tín hiệu Shorts
   nên được xử lý như YouTube long-form caption-only.
6. Không tự động cấu hình proxy hoặc cookie để vượt giới hạn truy cập của
   YouTube. Nội dung private, age-restricted hoặc cần đăng nhập vẫn được coi là
   unavailable và trả lỗi retryable.
7. Expected count từ title/caption được so với số venue authority cao/trung
   bình. Coverage dưới 40% dừng trước formatter/resolver/Planner; 40–70% tắt
   Finder và yêu cầu review; từ 70% tiếp tục tự động.

## Hệ quả

- YouTube long-form không dùng quota Gemini STT và không download media;
  YouTube Shorts dùng cùng quota và media pipeline với các Reel khác.
- Caption YouTube được cấu trúc thành travel observations bằng model text,
  không dùng metadata `yt-dlp`, audio STT hay media download.
- Video không có caption hoặc có thông tin chỉ xuất hiện trên hình không được
  import qua URL YouTube trong contract này.
- Cache caption dùng bảng `youtube_transcript_cache`.
- Limiter/dedupe là trong từng process. Triển khai nhiều worker cần limiter phân tán
  hoặc quota gateway nếu cần đảm bảo RPM toàn hệ thống.
- Cần theo dõi version `youtube-transcript-api` vì connector phụ thuộc endpoint
  web không được YouTube cam kết ổn định.
