# ADR-022: Hợp nhất Explorer vào Knowledge Graph staging

## Trạng thái

Accepted — 2026-08-05.

## Bối cảnh

Explorer từng tách job, intake, transcript cache, extraction cache, source
artifact và must-place snapshot thành nhiều bảng. Evidence bị sao chép qua các
boundary, còn `places` vừa đóng vai catalog vừa có nguy cơ nhận dữ liệu Google
chưa được con người kiểm tra.

## Quyết định

1. `source_documents` là boundary duy nhất theo canonical URL cho caption/STT,
   OCR, extracted context, hash, version và freshness.
2. `knowledge_graph_imports` dùng chung cho URL/image worker, Explorer intake và
   admin graph import. `processing_status` độc lập với `review_status`; review
   không phải trạng thái chạy job.
3. Area/Venue proposal, note và evidence nằm trong
   `knowledge_graph_import_nodes`; quan hệ đề xuất nằm trong
   `knowledge_graph_import_edges`. Chỉ quyết định admin được phép promote chúng
   sang graph canonical.
4. Identity lookup dùng Top K từ `knowledge_entities + knowledge_aliases`.
   Exact name chỉ là một tín hiệu. Alias phải là alias đã review hoặc tên quan
   sát thật từ nguồn; Explorer không sinh alias bằng LLM.
5. Nhiều chi nhánh cùng tên giữ `identity_status=branch_ambiguous`. Explorer
   không gọi Google để phân xử. Planner chọn entity gần các route anchor nhất và
   chỉ lưu lựa chọn đó trong plan revision/item bằng
   `selection_method=route_proximity`; import node không bị sửa thành một
   identity toàn cục.
6. Google Playwright chỉ là fallback khi graph không có identity phù hợp, tối đa
   hai query. Snapshot cho phép lưu gồm external ID, tên/type, địa chỉ, tọa độ,
   Maps URL, một ảnh, opening hours, rating/review count và `fetched_at`; không
   giữ raw HTML/review/phone/website.
7. Planner có thể dùng proposal/snapshot trước admin review. Review bảo vệ dữ
   liệu dùng chung, không chặn itinerary tạm thời.
8. Migration `20260805_0037` backfill dữ liệu trước khi bỏ
   `url_import_jobs`, `explorer_intakes`, `user_must_place*`,
   `url_source_artifacts`, `url_extraction_cache` và
   `youtube_transcript_cache`. `places` chưa bị xóa vì module ngoài Explorer còn
   phụ thuộc.

## Hệ quả

- Evidence và note có một owner rõ ràng, truy ngược được tới source document.
- Job lifecycle và human review không còn dùng chung một enum.
- Itinerary có thể hiển thị dữ liệu provisional mà không làm nhiễu graph.
- Cutover xóa bảng là không downgrade tự động; phải backup/restore khi rollback.

