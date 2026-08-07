# ADR-026: Làm giàu giá TravelPlace có nguồn

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-06
- Cập nhật: 2026-08-07, Selenium thay Playwright và trở thành search provider
  mặc định cho price crawler.

## Bối cảnh

Knowledge Graph có hơn mười nghìn `TravelPlace` nhưng chưa có property giá. Một
API miễn phí duy nhất không phủ được giá vé hoạt động tại Việt Nam; tìm kiếm web
không có provenance hoặc cho LLM tự trả số sẽ tạo dữ liệu khó kiểm chứng và mau
lỗi thời. Repo đã có Gemini client với structured output, retry và pool API key.

## Quyết định

1. Thêm CLI batch, resumable, dry-run mặc định; không thêm request web dài vào
   luồng Planner của người dùng.
2. Search nằm sau `WebSearchProvider`, extraction nằm sau `LLMClient`. Mặc định
   Selenium tìm `giá vé của <canonical name>`, mở kết quả organic đầu tiên và
   chuyển text đã render cùng URL sang Gemini structured output. Gemini Search
   grounding và Tavily vẫn là provider tùy chọn; domain không nhận raw provider
   payload.
3. Prompt mang canonical name, địa chỉ, vùng và source identity. Web content là
   untrusted data; model phải từ chối khi identity hoặc giá nhập nhằng.
4. Output bị ràng buộc bởi schema. Application kiểm tra amount, currency, range,
   exact-identity decision và source index. Giá/free không có grounded source
   không được apply.
5. Chỉ lưu giá vé vào cửa tiêu chuẩn ban ngày cho một người lớn trong snapshot
   `knowledge_properties.admission_price`. `minAmount`, `maxAmount` và
   `representativeAmount` cùng một giá; không trộn giá trẻ em/ưu tiên/VIP/tour
   đêm, combo, phương tiện hoặc dịch vụ phụ trợ. Không quy đổi ngoại tệ.
6. Cache JSONL giữ kết quả tối thiểu để resume. Mỗi outcome được cache và commit
   riêng ngay khi request hoàn tất thay vì chờ toàn bộ batch. Database chỉ nhận
   `verified_price`/`verified_free`; `not_found`, `ambiguous` và provider error
   không trở thành giá canonical.
7. `GEMINI_PRICE_API_KEYS` là pool riêng tùy chọn, fallback về
   `GEMINI_API_KEY`. Client round-robin sau request thành công, cooldown `429`
   và disable `401/403`; không ghi credential hoặc raw provider response vào log.
8. Không ghi đè giá có sẵn trừ khi operator truyền `--overwrite`.
9. Worker pool giữ tối đa bốn request đồng thời. Tầng repository kiểm tra lại
   grounded source HTTP(S), kể cả outcome đọc từ cache, trước khi upsert.
10. Price request mặc định được giãn bốn giây giữa lần bắt đầu. Khi client đã
    thử pool mà outcome vẫn quota-limited, worker ngừng claim entity mới và hoãn
    phần còn lại. Summary cuối lệnh đếm trực tiếp số `admission_price` trong DB.
11. CLI mặc định dùng `gemini-3.5-flash-lite`. Model inference và Search
    grounding có quota riêng; price research chỉ hoạt động khi project có quota
    cho Google Search grounding. Stable Gemini 2.5 không được xem là fallback
    cho project mới khi provider trả `model no longer available to new users`.
12. Google Selenium adapter chạy tuần tự, không bypass consent, CAPTCHA, paywall
    hoặc block và không apply kết quả khi search bị chặn. Page content được giới
    hạn trước khi gửi LLM và luôn là dữ liệu không tin cậy. Credential Gemini
    chỉ đọc từ environment, không được hard-code hoặc log.
13. Thêm Tavily basic search sau `WebSearchProvider` làm fallback có key. Adapter
    không yêu cầu answer/raw content, chỉ trả title/URL/snippet; Gemini chạy
    structured output không-grounding và application vẫn kiểm tra source index.
    Thiếu `TAVILY_API_KEY` phải fail-fast. Free quota chỉ dùng cho batch nhỏ;
    operator phải đánh giá chi phí trước khi chạy toàn catalog.

## Hệ quả

- Có thể tăng coverage dần, ưu tiên địa điểm phổ biến và vẫn truy vết được nguồn,
  model cùng thời điểm lấy.
- Search grounding có thể tính phí và nhiều key cùng project không làm tăng
  quota; operator phải giới hạn batch và theo dõi chi phí.
- Citation xác nhận nguồn đã được search dùng, không đảm bảo giá còn hiệu lực
  tới ngày đi. Planner vẫn phải hiển thị freshness và làm mới trước chuyến đi.
- Trang không được index, paywall hoặc giá theo ngày/option phức tạp có thể giữ
  trạng thái chưa xác định; hệ thống không tự bịa fallback.
