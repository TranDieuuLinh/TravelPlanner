# ADR-007: URL candidate một nguồn và persistence chỉ cho place đã resolve

- Trạng thái: Đã chấp nhận
- Ngày: 2026-07-30

## Bối cảnh

URL Extractor đã tạo place candidate có category, source order, activity và
evidence. Formatter trước đây đọc lại output này rồi sinh một mảng
`placeCandidates` thứ hai. Aggregator phải merge hai biểu diễn của cùng stop,
làm tăng prompt/output của Gemini và buộc Resolver chờ Formatter.

ADR-004 cũng lưu cả kết quả provisional/unresolved vào `user_must_place`, dù
Finder chỉ có thể dùng địa điểm đã xác minh có tọa độ.

## Quyết định

1. Với URL intake, Extractor là nguồn duy nhất tạo place candidate.
2. Code ứng dụng bổ sung source URL, priority và preference mặc định, sau đó gộp
   trùng trước khi resolve.
3. Formatter chỉ tạo intent, trip spec, constraint, assumption và preference từ
   request cùng summary extraction ngắn; không sinh lại URL candidate.
4. Formatter dùng provider structured output schema. Schema không được chép vào
   user payload như dữ liệu hội thoại.
5. Formatter và Resolver chạy song song sau extraction.
6. `user_must_place` chỉ lưu resolution có status `resolved`, đủ latitude và
   longitude, đồng thời đại diện một địa điểm cụ thể thay vì match rộng tới
   thành phố hoặc quốc gia.
7. Candidate provisional/unresolved hoặc thiếu tọa độ không được lưu vào
   `user_must_place` và không được bàn giao vào Planner/Finder.
8. Flow prompt/ảnh không có URL tiếp tục dùng Formatter để tạo candidate cho tới
   khi có adapter deterministic tương ứng.

## Hệ quả

- Gemini không lặp lại mảng URL candidate và structured output nhỏ hơn.
- Resolve không còn phải chờ Formatter nên giảm wall time của Explorer.
- Candidate name từ nguồn được giữ riêng với resolved name của provider.
- `user_must_place` chỉ chứa dữ liệu Planner/Finder có thể sử dụng trực tiếp.
- Candidate chưa resolve không còn provenance bền vững trong bảng này. Nếu sản
  phẩm cần UI review/retry cho candidate yếu, phải lưu chúng trong
  `SourceClaim`/`PlaceCandidate` hoặc `ImportJob` riêng thay vì dùng
  `user_must_place`.
