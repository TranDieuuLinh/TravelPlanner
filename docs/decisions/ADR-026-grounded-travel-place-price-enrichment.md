# ADR-026: Làm giàu giá TravelPlace bằng Gemini Search grounding

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-06

## Bối cảnh

Knowledge Graph có hơn mười nghìn `TravelPlace` nhưng chưa có property giá. Một
API miễn phí duy nhất không phủ được giá vé hoạt động tại Việt Nam; tìm kiếm web
không có provenance hoặc cho LLM tự trả số sẽ tạo dữ liệu khó kiểm chứng và mau
lỗi thời. Repo đã có Gemini client với structured output, retry và pool API key.

## Quyết định

1. Thêm CLI batch, resumable, dry-run mặc định; không thêm request web dài vào
   luồng Planner của người dùng.
2. Dùng Gemini Google Search grounding sau interface `LLMClient`. Provider trả
   model JSON cùng danh sách `groundingChunks`; domain không nhận raw search
   payload.
3. Prompt mang canonical name, địa chỉ, vùng và source identity. Web content là
   untrusted data; model phải từ chối khi identity hoặc giá nhập nhằng.
4. Output bị ràng buộc bởi schema. Application kiểm tra amount, currency, range,
   exact-identity decision và source index. Giá/free không có grounded source
   không được apply.
5. Lưu snapshot đầy đủ trong `knowledge_properties.admission_price`; chiếu giá
   đại diện VND vào `admission_fee_vnd` để tương thích research tool hiện tại.
   Không quy đổi ngoại tệ.
6. Cache JSONL giữ kết quả tối thiểu để resume. Database chỉ nhận
   `verified_price`/`verified_free`; `not_found`, `ambiguous` và provider error
   không trở thành giá canonical.
7. `GEMINI_PRICE_API_KEYS` là pool riêng tùy chọn, fallback về
   `GEMINI_API_KEY`. Client round-robin sau request thành công, cooldown `429`
   và disable `401/403`; không ghi credential hoặc raw provider response vào log.
8. Không ghi đè giá có sẵn trừ khi operator truyền `--overwrite`.

## Hệ quả

- Có thể tăng coverage dần, ưu tiên địa điểm phổ biến và vẫn truy vết được nguồn,
  model cùng thời điểm lấy.
- Search grounding có thể tính phí và nhiều key cùng project không làm tăng
  quota; operator phải giới hạn batch và theo dõi chi phí.
- Citation xác nhận nguồn đã được search dùng, không đảm bảo giá còn hiệu lực
  tới ngày đi. Planner vẫn phải hiển thị freshness và làm mới trước chuyến đi.
- Trang không được index, paywall hoặc giá theo ngày/option phức tạp có thể giữ
  trạng thái chưa xác định; hệ thống không tự bịa fallback.
