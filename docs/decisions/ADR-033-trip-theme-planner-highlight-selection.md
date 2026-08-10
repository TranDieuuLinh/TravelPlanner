# ADR-033: TripThemePlanner chỉ chọn điểm nhấn đặc trưng

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-09
- Ghi chú: chính sách số lượng/diversity được ADR-035 thay thế một phần.

## Bối cảnh

TripThemePlanner từng ép LLM tạo theme, diversity và số required experience tối
thiểu từ một graph catalog còn thưa và không đồng đều giữa destination. Output
thực tế cho thấy candidate thường hoặc inferred có thể lọt vào catalog, category
chưa ổn định và nhiều fit vẫn là `unknown`. Chính sách minimum khiến model phải
chọn dữ liệu yếu hoặc repair dù một plan không cần điểm nhấn graph để tiếp tục.

## Quyết định

- Giữ tên `TripThemePlanner` và field `tripThemes` để tương thích; output mới
  luôn trả `tripThemes=[]`.
- Graph projection chỉ tạo group có seed `SPECIAL_EXPERIENCE`. Claim
  `OFFERS_ACTIVITY` chỉ bổ sung Place cho cùng Activity đặc biệt, không tự tạo
  candidate.
- Mỗi candidate công khai `specialClaimIds`; highlight được chọn phải cite ít
  nhất một claim này cùng provenance của candidate.
- `requiredExperiences` chỉ biểu diễn highlight và được phép rỗng. Trần highlight
  là một cho 1–3 ngày, hai cho 4–6 ngày và ba cho chuyến từ 7 ngày.
- Không ép minimum, diversity hoặc category coverage. Graph priority `must` là
  tín hiệu destination, không phải hard constraint của user.
- PlaceSelector tiếp tục sở hữu Selected Place, gap filling, ngày, meal,
  capacity và route.

## Hệ quả

Destination chưa có special experience vẫn lập plan được mà không chọn candidate
suy diễn để lấp số. Highlight giữ exact graph identity và provenance. Các client
cũ vẫn đọc được schema, nhưng không được dùng `tripThemes` làm nguồn activity
quota cho dữ liệu mới.
