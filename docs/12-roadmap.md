# Lộ trình phát triển

## Giai đoạn 0: Nền tảng kỹ thuật

- Thêm test backend, lint/typecheck, test frontend và CI.
- Thêm file môi trường mẫu và quy trình chạy trên máy cá nhân đáng tin cậy.
- Lưu plan trong PostgreSQL và định nghĩa migration.
- Thêm authentication và authorization dựa trên quyền hạn.
- Chuẩn hóa lỗi API, ID, timestamp, tiền và idempotency.

**Điều kiện hoàn thành:** user và plan được lưu an toàn; CI bảo vệ contract cốt
lõi.

## Giai đoạn 1: Công cụ lập kế hoạch cốt lõi

- Xây LLM gateway thật với structured output và evaluation.
- Lưu entity trip, day, item, version, check và source.
- Triển khai thao tác editor và AI chỉnh sửa lại mà vẫn giữ nguyên item đã khóa.
- Chọn provider place/map; thêm marker, chặng đường và thời gian di chuyển.
- Thêm một luồng nhập URL có xác nhận.
- Hoàn thiện plan chính và plan dự phòng với kiểm tra vận hành.

**Điều kiện hoàn thành:** traveler có thể generate, chỉnh sửa, kiểm tra, lưu và
mở lại một plan hữu ích.

## Giai đoạn 2: Sử dụng trong chuyến đi và cộng tác

- Truy cập offline ở chế độ đọc và theo dõi tiến độ.
- Mời thành viên với quyền host/editor/viewer.
- Đồng bộ có xử lý xung đột.
- Làm mới dữ liệu trước chuyến đi.

**Điều kiện hoàn thành:** một nhóm nhỏ có thể dùng chung plan đáng tin cậy trong
chuyến đi.

## Giai đoạn 3: Chợ lịch trình MVP

- Creator profile, editor bản nháp, media, preview, publish và version.
- Khám phá listing, lọc, favorite và trang chi tiết.
- Một payment provider, order, entitlement, bản sao cá nhân và refund.
- Đánh giá từ giao dịch đã xác minh, báo cáo, creator dashboard và công cụ vận
  hành admin.

**Điều kiện hoàn thành:** một giao dịch plan trả phí có thể hoàn thành từ đầu đến
cuối, được vận hành và truy vết.

## Giai đoạn 4: Kiểm chứng và tăng trưởng

- Đo mức sẵn sàng chi trả, tỷ lệ giữ chân, tỷ lệ hoàn tiền và lợi nhuận đóng góp.
- Cải thiện chất lượng plan, recommendation ranking và công cụ creator.
- Thêm booking deep link/tích hợp đối tác.
- Thử nghiệm gói trả theo plan và subscription.

**Điều kiện hoàn thành:** dữ liệu chứng minh có thể mở rộng Marketplace và chi
phí provider.

## Giai đoạn sau

- Thêm nguồn nhập từ mạng xã hội/video.
- Cộng tác thời gian thực đầy đủ.
- Remix thương mại với royalty một cấp.
- Nhiều hành động booking và API đối tác hơn.
- Thành tựu và bản đồ du lịch nâng cao.

Thứ tự roadmap phản ánh rủi ro: Planner đáng tin cậy và lưu trữ bền vững phải có
trước độ phức tạp của Marketplace/payment. Ngày cụ thể và phân công nhân sự thuộc
kế hoạch triển khai, không nằm trong tài liệu ngữ cảnh sản phẩm này.
