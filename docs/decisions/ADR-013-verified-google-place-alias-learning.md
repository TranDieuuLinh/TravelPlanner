# ADR-013: Học alias Places từ Google identity đã xác minh

- Trạng thái: Đã thay thế bởi ADR-025
- Ngày: 2026-08-03

## Bối cảnh

Resolver hiện ưu tiên Knowledge Graph rồi mới fallback sang Google Maps
Playwright. Quyết định bên dưới mô tả catalog `places` legacy và không còn là
wiring runtime sau ADR-025; kết quả Explorer hiện được stage để review trước khi
promotion thành `KnowledgeAlias` canonical.
Một source spelling hoặc lỗi OCR có thể làm catalog miss dù Google xác định được
identity ổn định. Nếu không học kết quả này, URL khác tiếp tục trả cùng miss và
phải trả latency Playwright lặp lại.

ADR-004 và ADR-007 trước đây không cho Explorer tạo hoặc cập nhật `Place`, nhằm
tránh đưa candidate yếu và dữ liệu riêng tư vào catalog dùng chung. Quy tắc đó
quá rộng đối với kết quả provider đã đạt toàn bộ identity policy.

## Quyết định

1. Chỉ học từ Google resolution có status `resolved`, stable `externalId`,
   canonical provider name, latitude/longitude hợp lệ và `fetchedAt`.
2. Source candidate name và `originalName` được lưu như verified alias. Alias
   được chuẩn hóa accent/case/punctuation để update idempotent.
3. Nếu `places.id == externalId` đã tồn tại, repository chỉ bổ sung
   `metadata.aliases`, `metadata.verifiedAliases` và tăng `revision` khi có thay
   đổi thực tế.
4. Nếu identity chưa tồn tại, repository tạo `Place` tối thiểu từ normalized
   provider result, đặt `status=active`, `data_confidence=medium` và
   `source_platform=google_maps_scraper`.
5. Catalog không lưu raw provider payload, transcript, OCR, user ID, intake ID
   hoặc source URL của user. `verifiedAliases` chỉ giữ alias, provider,
   external ID và thời điểm xác minh.
6. Learning là side effect opportunistic: lỗi ghi catalog không được làm hỏng
   resolution đã thành công. Repository rollback transaction learning khi ghi
   lỗi.
7. Không học từ kết quả chỉ trùng tọa độ, thiếu external ID, mismatch,
   provisional, unresolved hoặc nhóm `duplicate_provider_identity`.

## Hệ quả

- Lookup lặp lại có thể resolve từ Places DB thay vì chạy Playwright.
- Catalog trở thành tập dữ liệu tăng dần có provenance ngắn và revision rõ ràng.
- Alias sai có thể ảnh hưởng mọi user, nên điều kiện stable ID và identity policy
  là bắt buộc; việc user tự nhập tên không đủ để ghi alias.
- Thay đổi dùng metadata JSON hiện có nên không cần migration schema.

ADR này tạo ngoại lệ hẹp cho ranh giới `UserMustPlace`/`Place` của ADR-004 và
ADR-007. Snapshot hành trình và provenance riêng tư vẫn chỉ thuộc
`UserMustPlace`.
