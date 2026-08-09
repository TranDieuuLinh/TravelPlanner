# ADR-020: Graph-backed research cho TripThemePlanner

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-05
- Cập nhật: chính sách chọn theme/minimum special experience đã được ADR-033
  thay thế; phần graph research và provenance vẫn giữ nguyên.

## Bối cảnh

TripThemePlanner từng dùng một lượt LLM để đề xuất research, một Place-database
tool để kiểm chứng, rồi thêm một lượt LLM tạo theme. Knowledge graph schema v7
đã có Activity, `SPECIAL_EXPERIENCE`, `TARGETS_PLACE`, provenance và priority,
nên research cũ tạo hai nguồn authority và không biểu diễn đúng direct anchor.

## Quyết định

- Runtime chạy `GraphResearchOrchestrator` và chiếu evidence thành bounded
  `graphCandidateCatalog` trước khi gọi TripTheme LLM đúng một lượt.
- Loại legacy research prompt và dependency khỏi runtime, nhưng giữ source file
  nếu module khác còn import.
- Claim không có hard conflict được chiếu vào catalog. Claim `unknown` được xếp
  sau `supported` và giữ warning; đây là chính sách tạm thời khi catalog vận
  hành chưa đủ dữ liệu để kết luận fit.
- Theo ontology v7, special experience trỏ tới Activity; `TARGETS_PLACE` cung
  cấp direct anchor. `OFFERS_ACTIVITY` vẫn cung cấp các Place cùng thực hiện một
  Activity.
- Output chỉ ở cấp toàn chuyến, không có day, route hoặc allocation. Chính sách
  output highlight-only và `tripThemes=[]` được định nghĩa tại ADR-033.
- Graph `must` không override intent hoặc hard constraint. ADR-033 cho phép
  không chọn special experience nào dù catalog có dữ liệu.
- `research-context` là CLI chỉ đọc, hiển thị research bundle và bounded catalog,
  không gọi LLM.
- Cutover ban đầu chưa truyền `requiredExperiences`; runtime hiện đã mở rộng
  `PlaceSelectionInput` để resolve required Place hoặc giữ requirement chưa
  resolve trong `UnscheduledPlace`.

## Hệ quả

Concrete IDs do LLM chọn đều phải tồn tại trong graph catalog và được backend
validate/repair. Empty coverage tạo catalog rỗng thay vì mở quyền bịa ID. Việc
PlaceSelector thực thi `requiredExperiences` cần một task và contract riêng.
