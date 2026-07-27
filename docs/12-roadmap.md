# Lộ trình phát triển

## Nguyên tắc

Planner đầy đủ và Marketplace đều thuộc phạm vi MVP. Các giai đoạn dưới đây là
thứ tự giảm rủi ro kỹ thuật và sản phẩm, không phải các phiên bản sản phẩm độc
lập. MVP chỉ được công bố hoàn thành sau khi đạt điều kiện của giai đoạn 4.

## Giai đoạn 0: Nền tảng kỹ thuật

- Thêm test backend, lint/typecheck, test frontend và CI.
- Lưu user, import, place và plan trong PostgreSQL bằng migration.
- Thêm authentication và authorization dựa trên quyền hạn.
- Chuẩn hóa lỗi API, ID, timestamp, tiền, job và idempotency.
- Thiết lập background worker, object storage và telemetry cơ bản.

**Điều kiện hoàn thành:** dữ liệu cốt lõi được lưu bền vững, job có thể retry và
CI bảo vệ contract.

## Giai đoạn 1: URL thành ngữ cảnh chuyến đi

- Xây source connector cho nguồn video ngắn ưu tiên và URL công khai.
- Triển khai fetch an toàn, metadata, caption/transcript và artifact policy.
- Trích xuất claim/place candidate bằng structured output.
- Tích hợp place provider để resolve, gộp trùng và kiểm tra độ mới.
- Xây UI review để user xác nhận, sửa, loại bỏ hoặc thêm place.
- Giữ provenance, confidence, trạng thái từng phần và fallback thủ công.
- Tạo evaluation cho nội dung mơ hồ, thiếu transcript và prompt injection.

**Điều kiện hoàn thành:** traveler có thể dán URL và tạo danh sách
`SelectedPlaces` có nguồn mà không cần nhân sự hỗ trợ.

## Giai đoạn 2: Planner hoàn chỉnh

- Hoàn thiện Explorer, MacroPlan, DayBrief, Finder và structured output.
- Tạo Main Plan theo ngày với route, thời lượng, phương tiện, chi phí và timezone.
- Triển khai CheckOverall cho schema, domain, place, route và dữ liệu cũ.
- Tạo Backup Plan riêng từ CheckOverall Report.
- Xây editor: thêm/xóa/kéo thả/đổi giờ/khóa item và AI revision theo phạm vi.
- Lưu version, optimistic concurrency và danh sách địa điểm chưa xếp.
- Thêm bản đồ, offline read và tiến độ chuyến đi.

**Điều kiện hoàn thành:** traveler đi từ URL đến plan đã kiểm tra, chỉnh sửa,
lưu, mở lại và dùng offline; Backup Plan không thay đổi Main Plan.

## Giai đoạn 3: Marketplace hoàn chỉnh

- Creator profile, verification, plan từ URL, media, preview và listing editor.
- Publish/unpublish, moderation tối thiểu và version bất biến.
- Duyệt listing, tìm kiếm, lọc, favorite và trang chi tiết.
- Tích hợp một payment provider, checkout, order, entitlement và refund.
- Tạo bản sao cá nhân đúng version cho buyer và đưa vào Planner.
- Review đã xác minh, report, creator dashboard và công cụ admin.
- Audit event cho moderation, payment, entitlement và refund.

**Điều kiện hoàn thành:** giao dịch plan trả phí chạy end-to-end; buyer chỉnh bản
sao bằng Planner mà không thay đổi version của creator.

## Giai đoạn 4: Hardening và phát hành MVP

- Chạy toàn bộ hành trình E2E Planner và Marketplace.
- Threat model authentication, URL fetching, AI, payment và nội dung công khai.
- Load test job/import/generate/search/checkout và thiết lập rate limit.
- Hoàn thiện quan sát provider, retry, circuit breaker và cảnh báo.
- Đo chất lượng extraction, place confirmation, plan validity và payment.
- Chuẩn bị quy trình support, moderation, report, refund và khôi phục dữ liệu.

**Điều kiện hoàn thành:** toàn bộ tín hiệu nghiệm thu trong
`04-mvp-scope.md` đạt ngưỡng phát hành đã thống nhất.

## Sau MVP

- Thêm connector cho nhiều mạng xã hội/video hơn.
- Cộng tác thời gian thực đầy đủ.
- Remix thương mại với royalty một cấp.
- Nhiều payment/booking provider và hành động booking hơn.
- Recommendation, định giá và creator analytics nâng cao.
- Thành tựu và bản đồ du lịch nâng cao.

Ngày cụ thể và phân công nhân sự thuộc kế hoạch delivery. Khi nguồn lực thay đổi,
không được âm thầm bỏ Planner hoặc Marketplace khỏi định nghĩa MVP; phải cập nhật
quyết định phạm vi và tiêu chí nghiệm thu.
