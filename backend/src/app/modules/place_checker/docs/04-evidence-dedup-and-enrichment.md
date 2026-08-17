# Task 04: Evidence, chống trùng và làm giàu

## Mục tiêu

Gộp các mention lặp lại mà không làm mất provenance, sau đó lấy metadata tối
thiểu cần thiết để lập kế hoạch an toàn.

## Phụ thuộc

Task 03.

## Gộp evidence

- Bảo toàn mọi source record và raw evidence excerpt.
- Nhận diện URL provenance qua `source_places[].origin == "url"`.
- Chỉ gắn URL note vào place khi tên place match với candidate đã resolve hoặc
  đủ mạnh; nếu không thì giữ dưới dạng unattached note.
- Giữ các assertion STT/OCR xung đột và expose conflict.
- Source protection mạnh nhất thắng: direct user trên URL, rồi item/system.

## Thứ tự chống trùng

1. Canonical KG entity ID.
2. Verified alias hoặc provider ID.
3. Tên, category tương thích và geographic proximity.

Không merge hai canonical ID khác nhau chỉ vì ở gần nhau. Sau merge phải giữ
source order sớm nhất và toàn bộ provenance.

## Các field cần làm giàu

Tọa độ, address, category, ontology type, tag, duration range, cost range/tier,
opening hours, operational status, reservation, accessibility, children/infant
suitability, source, confidence và freshness.

Giá trị unknown vẫn được giữ là unknown trong KG và rich PlaceChecker output.
Chỉ tại compact boundary sang Planner, TravelPlace thiếu giá được chiếu thành
`0 VND`; food, entertainment và accommodation không áp dụng mặc định này.
Không suy diễn unknown opening thành always open hoặc không cần reservation.

## Chiến lược dữ liệu

Đọc KG properties trước, sau đó đến normalized internal metadata. External
enrichment tốn chi phí được hoãn tới Task 08 và chỉ chạy cho field quan trọng
còn thiếu.

## Test và điều kiện hoàn thành

Test merge user+URL, duplicate alias, place khác nhau nhưng ở gần, unattached
note, STT/OCR conflict, unknown metadata và bảo toàn provenance. Hoàn thành khi
record sau dedup giữ đủ evidence và không chứa raw provider payload.
