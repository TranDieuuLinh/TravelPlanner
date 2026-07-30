# ADR-004: Tự động resolve và lưu địa điểm từ Explorer

- Trạng thái: Được thay thế một phần bởi ADR-007
- Ngày: 2026-07-28

## Bối cảnh

Explorer nhận prompt, URL và ảnh. Context chuyến đi là output công khai; danh
sách place candidate là dữ liệu nội bộ. Yêu cầu UX hiện tại là không dừng luồng
để hỏi user xác nhận từng candidate.

ADR-003 trước đây yêu cầu user confirm trước khi candidate trở thành input bắt
buộc của Planner. Quyết định mới này thay đổi riêng ranh giới đó cho flow
Explorer intake.

## Quyết định

1. Mỗi source adapter chuẩn hóa output của mình đúng một lần.
2. `PlaceCandidateAggregator` gộp candidate từ prompt, OCR và URL, phân loại bằng
   category và giữ mọi source URL.
3. Explorer chỉ trả `intakeId`, `userId` và object `explorer`: intent, tripSpec,
   assumptions, missingInfoQuestions. Không trả candidate.
4. Resolver chạy tự động, không hỏi user. Mọi kết quả được ghi
   `resolved`, `provisional` hoặc `unresolved`.
5. Chỉ lưu candidate và toàn bộ dữ liệu resolve vào `user_must_place`. Không lưu
   Explorer context và không tạo/cập nhật record trong `places`.
6. Explorer không tự gọi Planner hoặc Finder. Planner downstream nhận nguyên
   envelope, dùng object `explorer` và chuyển tiếp `intakeId + userId`; Finder
   downstream đọc `user_must_place` bằng đúng cặp khóa đó.
7. Provider nằm sau `PlaceResolver`. Adapter Nominatim là adapter local/MVP có
   cấu hình và rate limit, không phải quyết định provider bản đồ/route cuối cùng
   của ADR-002.

## An toàn dữ liệu

- Không lưu raw OCR, transcript hoặc toàn bộ payload provider trong các bảng
  Explorer.
- Dữ liệu không chắc chắn vẫn được lưu nhưng không được đánh dấu verified.
- Lưu provider, external ID, attribution, confidence và `fetchedAt`.
- Adapter public Nominatim phải gửi User-Agent riêng, tối đa một request mỗi
  giây, cache kết quả đã lưu và có thể thay thế bằng cấu hình.

## Hệ quả

- UX không bị chặn bởi câu hỏi xác nhận.
- Finder có thể nhận nhầm candidate do OCR hoặc URL extraction; Finder và
  CheckOverall phải sử dụng resolution status/confidence để cảnh báo.
- Mỗi intake và candidate có provenance truy vết được.
- Endpoint Explorer có thể chậm theo số candidate vì public Nominatim không cho
  phép request song song; background job là bước nâng cấp tiếp theo khi tải tăng.
- Quyết định này thay thế yêu cầu confirm bắt buộc của ADR-003 trong flow
  Explorer intake, nhưng không thay đổi confirmation ở các nghiệp vụ khác.

ADR-007 thay thế quyết định lưu mọi trạng thái resolution ở mục 4-5. Phần
no-interruption, ranh giới `UserMustPlace`/`Place` và cách bàn giao
`intakeId + userId` vẫn còn hiệu lực.
