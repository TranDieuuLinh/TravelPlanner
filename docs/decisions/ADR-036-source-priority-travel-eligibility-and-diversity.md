# ADR-036: Source priority, travel eligibility và trip-wide diversity

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-10
- Bổ sung: ADR-034

## Bối cảnh

Mandatory pool trước đây chỉ có cờ Boolean. `sourceOrder` vô tình quyết định
thứ tự giữa user Place, URL Place và required experience. Capacity preflight có
thể bỏ một URL Place rồi PlaceSelector lại lấp slot bằng suggestion. Bộ lọc
catalog exact-match chưa bao phủ clinic/consulting và diversity Boolean cấp ngày
không ngăn spa, beer hoặc food/drink lặp qua nhiều ngày.

## Quyết định

Planner dùng bốn priority tier nội bộ:

1. user intent/must-visit;
2. URL/OCR source Place;
3. required experience do TripThemePlanner resolve;
4. optional finder suggestion.

`sourceOrder` chỉ phá hòa bên trong cùng tier URL. Capacity chỉ đề xuất day
allocation; mọi mandatory Place vẫn được exact timeline thử xếp. Detailed route
overflow phải loại unlocked suggestion trước. CheckOverall phát
`optional_displaced_mandatory` khi optional và mandatory overflow cùng tồn tại.

Gap-fill dùng centralized default travel eligibility. Operational/service venue
không được tự đề xuất nhưng explicit user selection được phép. Ranking thêm
count-based trip-wide diversity penalty và checker không cho food/drink stops
liền nhau. Time-sensitive market chỉ được suy ra từ structured type/tag, không
từ generic name.

Với fixed-duration trip, global matrix chỉ được bỏ qua khi mọi mandatory Place
đã pin vào ngày hợp lệ. Nếu còn Place chưa pin, matrix vẫn phục vụ clustering và
day allocation dù solver không được tăng số ngày.

## Hệ quả

- User choice và URL provenance không bị suggestion chiếm chỗ.
- Catalog có thể over-sample một pool nhỏ trước eligibility filtering, nhưng chỉ
  thử tối đa bounded candidate count cho mỗi gap.
- Explicit practical stop như clinic vẫn hoạt động khi user chọn; nó không thể
  xuất hiện như gợi ý du lịch ngẫu nhiên.
- Diversity là soft score nên intent chuyên biệt vẫn có thể cho phép lặp; hard
  checker chỉ bảo vệ food/drink adjacency và time-sensitive windows.
