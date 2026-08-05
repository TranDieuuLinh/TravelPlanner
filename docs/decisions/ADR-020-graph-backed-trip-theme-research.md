# ADR-020: Graph-backed research cho TripThemePlanner

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-05

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
- Chỉ claim fit `supported` và không có hard conflict được chiếu vào catalog.
- Theo ontology v7, special experience trỏ tới Activity; `TARGETS_PLACE` cung
  cấp direct anchor. `OFFERS_ACTIVITY` vẫn cung cấp các Place cùng thực hiện một
  Activity.
- Output chỉ ở cấp toàn chuyến: `tripThemes`, `requiredExperiences`, assumptions,
  warnings và trace. Không có day, route hoặc allocation.
- Chọn theme theo thứ tự current-trip intent, confirmed Places, effective
  long-term profile, rồi destination special experiences. Graph `must` không
  được override intent hoặc hard constraint; khi không có tín hiệu cá nhân,
  planner phải lấy ít nhất một trusted special experience nếu catalog có.
- `research-context` là CLI chỉ đọc, hiển thị research bundle và bounded catalog,
  không gọi LLM.
- Cutover ban đầu chưa truyền `requiredExperiences`; runtime hiện đã mở rộng
  `PlaceSelectionInput` để resolve required Place hoặc giữ requirement chưa
  resolve trong `UnscheduledPlace`.

## Hệ quả

Concrete IDs do LLM chọn đều phải tồn tại trong graph catalog và được backend
validate/repair. Empty coverage tạo catalog rỗng thay vì mở quyền bịa ID. Việc
PlaceSelector thực thi `requiredExperiences` cần một task và contract riêng.
