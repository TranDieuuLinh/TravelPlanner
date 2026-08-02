# ADR-010: Google Maps scraper làm fallback resolve địa điểm

- Trạng thái: Đã chấp nhận
- Ngày: 2026-07-31

## Bối cảnh

Explorer đã tra bảng `places` bằng tên gốc và alias song ngữ trước khi gọi
provider ngoài. Một số địa điểm địa phương có trên Google Maps nhưng không có
trong catalog nội bộ hoặc Nominatim, làm candidate thiếu latitude/longitude và
không đủ điều kiện lưu vào `user_must_place`.

Repo `gosom/google-maps-scraper` cung cấp Playwright CLI và output JSON có tên,
địa chỉ, latitude, longitude cùng Google place identity mà không cần API key.
Đây là nguồn scrape, không phải Google Maps Platform API chính thức, nên cần
được cô lập sau interface và chỉ bật khi operator đã xem xét điều khoản vận
hành.

## Quyết định

- Thứ tự resolve hiện hành là:
  `shared URL/place cache -> places DB -> google-maps-scraper (nếu cấu hình)
  -> Nominatim`.
  Cache dùng snapshot đã chuẩn hóa, không dùng lại payload thô. Playwright được
  ưu tiên sau catalog nội bộ để thu thập snapshot Google Maps đầy đủ hơn;
  Nominatim là fallback cuối khi scraper không resolve được.
- Gọi trực tiếp executable `google-maps-scraper`; không dùng API key.
- Tra tên gốc trước, luôn kèm `searchRegion` và address hint khi có. Chỉ khi
  kết quả đầu chưa đạt rule xác minh mới ghi tối đa số alias đã cấu hình vào
  job tiếp theo; đọc JSON output rồi xóa thư mục tạm.
- Chạy subprocess không qua shell, giới hạn concurrency/depth và kill process
  khi vượt timeout. Telemetry của CLI được tắt.
- Chỉ trả `resolved` khi kết quả khớp tên, không lệch vùng/category rõ ràng và
  có tọa độ trong miền hợp lệ.
- Chuẩn hóa output vào `PlaceResolution`; không đưa payload thô của scraper vào
  domain hoặc log.
- Worker Playwright thu thập các field tóm tắt đang hiển thị mà không mở review
  feed: rating, tổng số review, giờ mở cửa, plus code, website, điện thoại và mô
  tả. Field thiếu được để null; nội dung từng review không thuộc place resolver.
- Chấp nhận cả field `longitude` hiện tại và field legacy `longtitude` của
  upstream để tương thích version.
- Thiếu binary, timeout, process lỗi hoặc kết quả mismatch không làm hỏng
  Explorer; candidate giữ trạng thái unresolved. Có thể đặt executable rỗng
  để tắt provider.
- Giữ provenance `provider=google_maps_scraper`, external ID, `fetchedAt` và
  attribution trên record đã resolve.

## Cấu hình

- `GOOGLE_MAPS_SCRAPER_EXECUTABLE`
- `GOOGLE_MAPS_SCRAPER_WORK_DIR`
- `GOOGLE_MAPS_SCRAPER_TIMEOUT_SECONDS`
- `GOOGLE_MAPS_SCRAPER_MAX_ALIAS_QUERIES`

Trong Docker Compose, scraper chạy bằng image upstream v1.12.1 đã pin và nhận
job qua thư mục dùng chung. `PLAYWRIGHT_DRIVER_PATH` phải trỏ tới thư mục
version thực tế (`/opt/ms-playwright-go/1.57.0`); giá trị `/opt` mặc định trong
image làm Playwright cố tải lại driver đã bị CDN trả 404. Ngoài Compose, có thể
dùng executable trong `PATH` hoặc đường dẫn tuyệt đối tới binary đã build.

Sidecar Compose chạy Node worker liên tục, giữ một Chromium browser và mặc định
hai page slot (`GOOGLE_MAPS_SCRAPER_CONCURRENCY=2`). Mỗi slot claim job bằng
atomic rename, tái sử dụng page cho job tiếp theo và đưa job dở dang về queue khi
container khởi động lại. Không tăng concurrency quá 2 mặc định nếu chưa
kiểm tra RAM, throttling và CAPTCHA.

## Hệ quả

- Có thêm nguồn tọa độ cho alias địa phương mà không làm `PlaceResolver` phụ
  thuộc payload Google Maps.
- Cache hit và catalog hit không khởi động Playwright. Cache miss có thể chậm
  hơn vì Google Maps chạy trước Nominatim; timeout vẫn bảo vệ request Explorer.
- Operator chịu trách nhiệm tự host, quota/tài nguyên, proxy nếu cần, review
  điều khoản sử dụng, attribution và retention trước khi bật provider.
- Dữ liệu scrape không được mặc nhiên xem là chính xác; rule match và freshness
  vẫn áp dụng như các provider khác.
