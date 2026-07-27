# Luồng người dùng

## Người du lịch đã có điểm đến hoặc URL tham khảo

1. Đăng nhập và tạo chuyến đi.
2. Nhập điểm đến/yêu cầu và tùy chọn dán một hoặc nhiều URL nguồn.
3. Kiểm tra các địa điểm/nội dung được trích xuất; xử lý các mục có độ tin cậy
   thấp hoặc không được nguồn hỗ trợ.
4. Cung cấp ngày/số ngày, nơi xuất phát, nhóm đi, ngân sách, nhịp độ, sở thích,
   địa điểm bắt buộc, nhu cầu hỗ trợ tiếp cận và các ràng buộc.
5. So sánh các phương án được tạo.
6. Mở một plan trong trình chỉnh sửa.
7. Thêm, xóa, đổi thứ tự, đổi thời gian hoặc khóa từng mục; yêu cầu AI chỉ sửa
   phần chưa khóa.
8. Kiểm tra tuyến đường trên bản đồ, thời gian di chuyển, phương tiện gợi ý, chi
   phí và cảnh báo.
9. Lưu plan và mời thành viên cộng tác khi cần.
10. Cho phép truy cập plan offline.
11. Trong chuyến đi, xem lịch trình và đánh dấu tiến độ.
12. Sau chuyến đi, ghi nhận thành tựu và tùy chọn xuất bản hoặc đánh giá.

## Người du lịch khám phá qua Marketplace

1. Tìm kiếm/lọc plan theo điểm đến, thời lượng, ngân sách, phong cách, đánh giá
   và độ mới.
2. Mở listing và kiểm tra preview, creator, ngày cập nhật, nội dung bao gồm,
   license, review và chi phí dự kiến.
3. Mua plan.
4. Nền tảng ghi nhận order và cấp quyền truy cập đúng phiên bản đã mua.
5. Tạo một bản sao cá nhân để tùy chỉnh.
6. Tiếp tục luồng chỉnh sửa, kiểm tra, offline và sử dụng như plan do AI tạo.
7. Đánh giá hoặc báo cáo plan đã mua khi đủ điều kiện.
8. Nếu không có listing phù hợp, chuyển sang AI Planner và giữ lại ngữ cảnh tìm
   kiếm.

## Nhà sáng tạo xuất bản plan

1. Đăng nhập và hoàn tất xác minh creator khi được yêu cầu.
2. Bắt đầu từ AI Planner, bản nháp cũ hoặc nội dung được nhập.
3. Chỉnh sửa ngày, địa điểm, tuyến đường, chi phí, media, mẹo địa phương và
   phương án dự phòng.
4. Thêm dữ liệu listing: tên, ảnh/video bìa, mô tả, đối tượng phù hợp, giá, nội
   dung bao gồm, lưu ý, ngày cập nhật và thiết lập license/remix.
5. Xem trước chính xác những gì buyer thấy trước và sau khi mua.
6. Gửi kiểm tra tự động/thủ công và xuất bản.
7. Theo dõi lượt xem, tỷ lệ chuyển đổi, lượt mua, đánh giá, hoàn tiền và doanh
   thu.
8. Xuất bản phiên bản mới mà không thay đổi phiên bản lịch sử gắn với order cũ.
9. Phản hồi review và xử lý nội dung cũ hoặc bị báo cáo.

## Luồng AI Planner

```text
Khám phá -> Lập khung từng ngày -> Tìm/điền địa điểm -> Kiểm tra tổng thể
    |                                                   |
    +-- cần hỏi thêm                                   +-- phát hiện rủi ro
                                                            |
                                                            v
                                                  Tạo plan dự phòng
```

Backend hiện tại phản ánh các ranh giới này. `MainPlanWorkflow` tạo và khóa plan
chính sau khi kiểm tra. `BackupPlanWorkflow` tạo một plan riêng có
`parentPlanId`; không được thay đổi plan chính.

## Các luồng ngoại lệ quan trọng

- Không truy cập được URL: giữ lại URL, giải thích lỗi và cho phép nhập địa điểm
  thủ công.
- Độ tin cậy của nguồn thấp: yêu cầu xác nhận thay vì tự bịa thông tin.
- Provider timeout: giữ bản nháp/đầu vào và cho phép thử lại.
- Địa điểm đóng cửa hoặc tuyến đường không khả thi: chỉ rõ mục bị lỗi và đưa ra
  phương án thay thế có phạm vi.
- Thanh toán đang chờ/thất bại: không cấp quyền truy cập trước khi nhận được xác
  nhận phía server đã được kiểm chứng.
- Chỉnh sửa offline bị xung đột: giữ cả hai phiên bản thay đổi và yêu cầu host
  xử lý.
- Plan đã xuất bản thay đổi: giữ nguyên snapshot buyer đã mua và cung cấp luồng
  cập nhật rõ ràng.
