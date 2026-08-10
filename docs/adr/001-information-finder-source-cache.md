# ADR 001: Runtime source cache của Information Finder

Cập nhật lần cuối: 2026-08-10.

## Trạng thái

Accepted cho giai đoạn triển khai hiện tại; cần đánh giá lại migration runner và
answer generator trước production.

## Quyết định

Information Finder sở hữu các bảng có tiền tố `information_finder_` trong
PostgreSQL runtime `travelplanner` do Docker Compose cung cấp. Module không đọc
hoặc ghi các bảng legacy. pgvector lưu embedding 384 chiều tách khỏi document;
PostgreSQL full-text search cung cấp phần lexical của hybrid retrieval.

Repository dùng `asyncpg` và transaction cho mỗi lần ghi một search run cùng
document, snapshot, chunk và embedding. Tavily và embedding chạy trước
transaction. Migration ban đầu là SQL versioned tại
`backend/migrations/001_information_finder_source_cache.sql` vì backend mới chưa
có migration framework. Docker chỉ tự chạy file này khi khởi tạo volume mới;
volume đã tồn tại phải chạy migration thủ công.

`intfloat/multilingual-e5-small` là embedding adapter mặc định khi có
`DATABASE_URL`. Model được lazy-load một lần và query/passage dùng đúng prefix.
Khi không có database, development/test dùng cache trong process và hashing
embedding, không được coi là semantic retrieval production.

Chưa chọn LLM production. `ExtractiveAnswerGenerator` chỉ ghép snippet đã cấp
với citation ổn định và được ghi nhận rõ là fallback.

## Hệ quả

- Có ownership rõ, không phụ thuộc schema legacy.
- Model/revision/dimensions được ràng buộc trong retrieval nên không trộn vector.
- Cần bổ sung migration framework có tracking/rollback trước production.
- Cần chọn và đánh giá AnswerGenerator production trước khi tuyên bố câu trả lời
  là nội dung tổng hợp bằng AI.
