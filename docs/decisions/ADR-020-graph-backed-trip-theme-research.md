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
- `research-context` là CLI chỉ đọc, hiển thị research bundle và bounded catalog,
  không gọi LLM.
- PlaceSelector chưa nhận `requiredExperiences` trong quyết định này.

## Hệ quả

Concrete IDs do LLM chọn đều phải tồn tại trong graph catalog và được backend
validate/repair. Empty coverage tạo catalog rỗng thay vì mở quyền bịa ID. Việc
PlaceSelector thực thi `requiredExperiences` cần một task và contract riêng.
