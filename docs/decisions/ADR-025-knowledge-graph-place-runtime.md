# ADR-025: Knowledge Graph là catalog địa điểm runtime duy nhất

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-05

## Bối cảnh

Ứng dụng từng giữ cùng một danh tính địa điểm ở `places` và
`knowledge_entities`. Hai ID khác nhau và chỉ có thể nối chính xác qua
`places.source_link = knowledge_properties(source_url)`. Planner, Profile và
gallery vì vậy có nguy cơ đọc hai catalog không đồng bộ.

## Quyết định

- Dùng `knowledge_entities.id` làm danh tính địa điểm duy nhất trong runtime.
- Giữ tên API `placeId` để tương thích client; giá trị là KG entity ID.
- Lưu thuộc tính scalar/JSON như giờ mở cửa, rating, review count, region và
  provenance trong `knowledge_properties`.
- Giữ dữ liệu một-nhiều ở bảng riêng: `knowledge_entity_images`, `reviews` và
  `user_visited_places`, tất cả tham chiếu `knowledge_entities.id`.
- PlaceSelector, Resolver, autocomplete, Profile, plan mutation và research
  tools chỉ dùng KG repository/projection.
- Xóa `places`, `place_opening_hours` và `place_amenities` sau khi kiểm tra mọi
  review/image/visit đều đã có exact entity mapping.

## Hệ quả

- Không còn đồng bộ hai catalog hoặc chuyển đổi ID trong Planner.
- Gallery nhiều ảnh và review text không làm phình một property JSON duy nhất.
- Migration drop catalog legacy là không thể tự dựng ngược; rollback dữ liệu
  cần database backup.
- Các script maintenance cũ còn nhập `SqlAlchemyPlaceRepository` không thuộc
  runtime và phải được thay bằng KG import/review workflow trước khi dùng lại.
