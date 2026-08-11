# ADR 003: Gemini URL Context cho semantic chunking

Cập nhật lần cuối: 2026-08-11.

## Quyết định

Khi Information Finder phải refresh nguồn, Tavily vẫn chịu trách nhiệm tìm
nguồn và trả provenance. Mỗi URL public được gửi cho Gemini URL Context để tạo
semantic chunks trước khi Gemini Embedding Provider tạo vector và lưu vào
PostgreSQL/pgvector.

Nếu URL Context không truy cập được hoặc trả structured output không hợp lệ,
module dùng deterministic chunking hiện tại làm fallback. Cache vẫn là
cache-first; chunking Gemini chỉ chạy khi local sources không đủ hoặc query
buộc refresh.

`source_snapshots.extractor_version` lưu phiên bản chunking. Khi snapshot có
cùng content hash nhưng phiên bản chunking thay đổi, repository thay thế chunks
và embeddings của snapshot trong cùng transaction.

## Lý do

Semantic chunks có thể giữ trọn một chủ đề tốt hơn giới hạn từ cố định. Dữ liệu
raw từ Tavily vẫn được lưu làm snapshot để provenance, fallback và tái xử lý.
URL Context chỉ nhận URL public; không được coi là nguồn duy nhất khi trang yêu
cầu đăng nhập, paywall hoặc không thể fetch.

## Hệ quả

- Cache miss/refresh có thêm một lượt gọi Gemini cho mỗi nguồn được chấp nhận.
- Gemini URL Context và structured output có thể lỗi theo URL/model, nên phải có
  fallback deterministic.
- Thay đổi prompt/model chunking có thể re-chunk và re-embed snapshot hiện có.
