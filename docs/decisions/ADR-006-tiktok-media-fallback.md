# ADR-006: TikTok extraction không dùng proxy media

- Trạng thái: Thử nghiệm cho local/MVP
- Ngày: 2026-07-29

## Bối cảnh

TikTok thường thay đổi challenge và dữ liệu rehydration. `yt-dlp` có thể đọc
metadata nhưng thất bại khi tải media, làm STT và video OCR không được gọi dù
video công khai. Đội sản phẩm không muốn gửi URL qua TikWM hoặc một proxy scraper
media tương tự.

## Quyết định

1. Không gọi TikWM và không giữ cấu hình TikWM.
2. Video thử `yt-dlp` chuẩn trước.
3. Nếu request đầu thất bại, retry `yt-dlp` bằng desktop Chrome rồi Android
   Chrome impersonation do `curl_cffi` cung cấp. Đây vẫn là request trực tiếp
   từ backend tới TikTok/CDN.
4. Photo carousel chưa có connector trực tiếp đã được duyệt nên trả
   `needsImageUpload=true`; user có thể upload screenshot để chạy OCR ảnh.
5. Video URL được trích audio cho STT và frame lấy mẫu cho OCR bằng
   `gemini-3.5-flash-lite`. Video, audio và frame chỉ tồn tại trong thư mục tạm
   và luôn bị xoá khi thành công hoặc lỗi.
6. Cookie người dùng không được thu thập mặc định; nếu sau này hỗ trợ cookie thì
   phải có secret storage, consent và ADR riêng.

## Hệ quả

- Không phụ thuộc TikWM hoặc chuyển URL/media qua proxy scraper.
- Browser impersonation cải thiện một số challenge/TLS fingerprint nhưng không
  bảo đảm mọi TikTok URL công khai đều tải được. Khi TikTok chặn mọi request,
  UI phải báo cần screenshot/caption thay vì trả plan 0 địa điểm như thể đã xử
  lý thành công.
- `curl_cffi` làm image backend lớn hơn và phải được cập nhật cùng `yt-dlp`.
- Domain Planner chỉ nhận claim/candidate chuẩn hóa, không nhận payload TikTok
  thô.
