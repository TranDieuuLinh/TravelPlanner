# ADR-035: Tag có provenance và fallback hoạt động buổi tối

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-10
- Thay thế một phần: ADR-033

## Bối cảnh

Place catalog có gần mười nghìn record nhưng tag runtime trước đây chủ yếu được
suy ra tạm thời từ category. Các Activity buổi tối như chợ đêm, live music hoặc
city walk cũng rơi vào `shopping`, `sightseeing` và `entertainment` quá rộng.
Đồng thời, chính sách highlight rất thấp và cho phép model bỏ toàn bộ catalog,
nên phần giới thiệu Hà Nội có thể chỉ còn các finder suggestion thiếu đa dạng.

## Quyết định

- Lưu controlled tag vocabulary, assertion và scan result trong các bảng riêng.
  Mỗi assertion có status, confidence, evidence/source, rule version, run và
  expiry; mỗi Place được scan đều có kết quả kể cả khi không gắn được tag.
- Backfill chỉ dùng category/type/metadata/giờ mở cửa đã lưu và quy tắc tên bảo
  thủ. Không tự gắn audience, accessibility, giá, `family_friendly` hoặc tag
  nhạy cảm khi không có bằng chứng.
- Tạo chín Activity buổi tối có identity riêng. Place chỉ trở thành candidate
  qua `Place -> OFFERS_ACTIVITY -> Activity`; Activity này không nhận
  `SPECIAL_EXPERIENCE`.
- PlaceSelector chỉ dùng pool trên khi cửa sổ 19:00–21:00 còn trống, tối đa một
  optional item mỗi ngày, sau selected/special Place. Constraint, duplicate,
  opening hours đã biết và geographic scope vẫn được kiểm tra.
- Xóa riêng các cạnh `SPECIAL_EXPERIENCE` tổng quát của Hà Nội như coffee,
  shopping, walk và nightlife; giữ các experience cụ thể có target Place.
- Với catalog special có Place cụ thể, TripThemePlanner tạo phần giới thiệu
  bounded tối đa một highlight mỗi ngày, không quá năm, và ưu tiên khác Activity
  và category. Catalog rỗng vẫn cho phép plan tiếp tục không có highlight.

## Hệ quả

Tag trở thành dữ liệu audit được thay vì metadata không rõ nguồn. Nightlife có
ngữ nghĩa thời gian riêng nhưng không làm loãng special experience. Highlight
có thể tăng số mandatory candidate đưa vào capacity solver; nếu không fit,
PlaceSelector phải báo `UnscheduledPlace` thay vì âm thầm chen quá lịch.

