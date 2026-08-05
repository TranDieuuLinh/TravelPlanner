# ADR-018: Activity, Item và Special Experience trong Knowledge Graph

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-05

## Bối cảnh

Planner cần phân biệt hành động như `Ăn phở` với đối tượng như `Phở`, đồng thời
cần biểu diễn trải nghiệm đặc trưng của một khu vực, ví dụ `Đà Lạt` phải đi
`Săn mây`. Property cũng cần ghi chú vận hành mà không làm mất provenance.

## Quyết định

- Giữ `Activity` cho hành động hoặc trải nghiệm.
- Thêm abstract node `Item` với các concrete node `FoodItem`, `DrinkItem` và
  `ProductItem`.
- Dùng `INVOLVES_ITEM: Activity -> Item` và `OFFERS_ITEM: Place -> Item`.
- Dùng duy nhất `SPECIAL_EXPERIENCE: LocationEntity -> Activity` cho hoạt động
  được đề xuất, từ gợi ý phù hợp đến trải nghiệm must-do. Edge phải có source;
  trường `recommendations` lưu `priority` (`optional`, `recommended`, `must`),
  lý do và khung giờ.
- Thêm cột `note` tùy chọn sau `source` trong `properties.csv` và bảng
  PostgreSQL `knowledge_properties`. `note` không thay thế `source`.
- Tăng schema contract lên version 7.

## Hệ quả

Planner có thể truy vấn riêng hành động và item, đồng thời giải thích vì sao một
trải nghiệm được coi là đặc trưng. Dataset cũ cần đổi header của properties và
chuẩn hóa các edge `SPECIAL_EXPERIENCE` không trỏ đến `Activity`.
