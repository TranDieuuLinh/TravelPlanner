# ADR-032: Phân bổ meal đặc trưng ở cấp toàn chuyến

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-07

## Bối cảnh

PlaceSelector từng gọi Gemini đồng bộ theo từng ngày để chọn FoodItem/DrinkItem,
sau đó retry khi item không có venue phù hợp. Luồng này vừa tăng latency theo số
ngày, vừa bỏ qua các dining `SPECIAL_EXPERIENCE` và `TARGETS_PLACE` đã có trong
Knowledge Graph. Catalog item toàn cục cũng quá tổng quát để đại diện đặc sản
của destination.

## Quyết định

- Xác định số ngày và cụm activity trước khi phân bổ meal.
- Tải một candidate pool bounded cho toàn chuyến từ
  `Area -> SPECIAL_EXPERIENCE -> Activity` có `activity_category=dining`.
- Ưu tiên `Activity -> TARGETS_PLACE -> Restaurant`.
- Với experience tổng quát, dùng `Activity -> INVOLVES_ITEM -> Item` và tìm
  restaurant trong scope qua `Restaurant -> OFFERS_ITEM -> Item`.
- Food/drink experience được canonical hóa theo loại món, không theo tên quán.
  `Restaurant`/`DrinkDessert` chỉ nối `OFFERS_ITEM` tới item; không tạo cạnh
  `OFFERS_ACTIVITY` để biểu diễn việc venue bán một món.
- Required food/drink Activity chưa có Place cụ thể được Mandatory Candidate
  Pool resolve bằng `INVOLVES_ITEM/OFFERS_ITEM`, nhận cả `Restaurant` và
  `DrinkDessert` trong destination. Text search chỉ là fallback khi graph không
  có venue materialize hợp lệ.
- Phân bổ deterministic cho toàn bộ meal slot, ưu tiên khung giờ experience,
  semantic relevance và dữ liệu chất lượng trước detour địa lý. Không lặp venue;
  meal key đã dùng bị cộng penalty ở cấp toàn chuyến để mọi món chưa dùng được
  ưu tiên trước. Đây là penalty mềm: món được phép lặp khi không còn lựa chọn
  phù hợp, tránh để trống meal chỉ vì destination có catalog nhỏ.
- Dùng catalog restaurant thông thường làm fallback. Không gọi Gemini trong
  đường chọn meal chính và không retry LLM theo slot.
- Không đưa toàn bộ restaurant catalog vào matrix. Tọa độ dùng để prefilter;
  final routing chỉ xử lý các stop đã chọn.

## Hệ quả

- Số LLM call chọn meal không tăng theo số ngày.
- Planner tận dụng đúng provenance đặc sản đã có trong graph và tránh chọn item
  không có venue trong destination.
- Query graph và candidate pool bị giới hạn; fallback thiếu dữ liệu giữ generic
  meal anchor cùng warning theo contract hiện tại.
- Đây vẫn là heuristic deterministic, không tuyên bố nghiệm tối ưu toàn cục.
