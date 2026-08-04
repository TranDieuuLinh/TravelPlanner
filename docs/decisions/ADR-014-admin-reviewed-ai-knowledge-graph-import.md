# ADR-014: AI Knowledge Graph import phải qua admin review

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-03

## Bối cảnh

Knowledge Graph prototype dùng các file CSV/YAML trong
`knowledge-graph-real-v2`. Admin cần gửi nội dung nguồn để AI đề xuất node và
edge theo schema/ontology, tìm record đã tồn tại, chỉnh sửa kết quả và quyết định
những thay đổi nào được ghi vào graph.

Cho LLM ghi trực tiếp vào graph sẽ làm mất ranh giới provenance, validation và
quyết định của admin. Matching chỉ bằng fuzzy score cũng có thể merge nhầm địa
điểm hoặc chi nhánh có tên gần giống.

## Quyết định

1. LLM chỉ tạo structured `GraphProposal`; không được ghi file hoặc quyết định
   merge.
2. Source được coi là dữ liệu không tin cậy. Prompt không thực hiện instruction
   nằm trong source và output bị ràng buộc bởi JSON Schema.
3. Matcher chạy rule xác định trước: ID chính xác, canonical name, alias, type
   conflict và name similarity. Fuzzy score chỉ tạo candidate cho admin.
4. Node có quyết định `approve_create`, `approve_existing` hoặc `reject`. Edge
   chỉ được apply khi hai endpoint đã được duyệt.
5. Mỗi proposal giữ hash của dataset. Apply trả `DATASET_VERSION_CONFLICT` nếu
   graph đã đổi trong lúc review.
6. Apply mới ghi `entities.csv`, `aliases.csv` và `relationships.csv`; ghi qua
   file tạm rồi rename. Edge đã tồn tại được bổ sung source thay vì tạo cạnh
   trùng.
7. MVP nhận text cùng source label/URL provenance; không tự fetch URL. Connector
   URL/file sẽ được bổ sung sau khi có validation và SSRF policy phù hợp.
8. Proposal prototype được lưu trong `backend/var/knowledge-graph-imports.json`.
   Đây chưa phải persistence production; migration PostgreSQL là bước tiếp theo.
9. Gemini dùng pool `GEMINI_API_KEY` phân tách bằng dấu phẩy. Client round-robin
   giữa các request thành công và giữ cooldown/disable cho `429/401/403`.

## Hệ quả

- Admin xem được evidence, match rule, candidate và chỉnh sửa trước khi apply.
- AI output sai không tự làm bẩn graph dùng chung.
- File storage phù hợp UI-first nhưng chưa hỗ trợ nhiều process hoặc audit bền
  vững như PostgreSQL.
- URL fetching, rich provenance, background worker, rebase proposal và rollback
  graph version chưa nằm trong MVP này.
