# ADR-011: Cache URL dùng chung và quan hệ nhiều-nhiều User–MustPlace

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-01

## Bối cảnh

`user_must_place` trước đây chứa một bản sao địa điểm cho từng Explorer intake.
Hai user dán cùng URL phải chạy lại connector, STT/OCR và place resolver, đồng
thời tạo các row địa điểm trùng nhau. `intake_id` có `ON DELETE CASCADE` cũng
làm vòng đời dữ liệu resolve bị gắn với intake đầu tiên.

Thông tin vận hành của địa điểm, ghi chú trích từ nội dung URL và lựa chọn của
user có vòng đời khác nhau. Transcript/OCR là claim của URL, không phải sự thật
canonical để ghi đè `places`.

## Quyết định

- `user_must_place` trở thành snapshot URL/place dùng chung. Bảng có các column
  tương ứng `places`, thêm `source_url` và `notes`, đồng thời giữ các column
  provenance/itinerary cũ trong giai đoạn tương thích.
- `place_id` nullable liên kết snapshot với `places` khi catalog nội bộ match.
  Dữ liệu thiếu từ provider được phép để null.
- `user_must_place_users` là junction table giữa snapshot, user và Explorer
  intake. Một user có nhiều must-place và một snapshot có thể thuộc nhiều user.
- `url_extraction_cache` cache `ExtractedContext` đã chuẩn hóa theo canonical
  URL cho TikTok, YouTube và nguồn URL khác. Không cache media, frame, raw
  provider payload hay toàn bộ transcript.
- Cache hit bỏ qua media/STT/OCR. Snapshot hit bỏ qua place resolver. Cache miss
  resolve theo `places DB -> Google Maps Playwright -> Nominatim`.
- `notes` chỉ giữ evidence/mẹo ngắn đã chuẩn hóa từ caption/STT/OCR; dữ liệu vận
  hành mới hơn vẫn lấy từ `places` hoặc resolver.

## Hệ quả

- URL đã xử lý có thể được tái sử dụng giữa nhiều user và intake.
- Xóa một intake chỉ xóa junction rows của intake đó, không xóa snapshot đang
  được user/intake khác dùng.
- Dữ liệu cũ được backfill vào junction table rồi gộp theo
  `source_url + candidate_key`; mọi liên kết intake cũ được giữ.
- Cần chính sách refresh/TTL riêng khi nguồn hoặc dữ liệu địa điểm trở nên cũ;
  revision hiện chỉ chuẩn bị cho việc cập nhật snapshot có kiểm soát.
