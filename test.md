# Thành tựu nổi bật

Ban đầu, hệ thống phụ thuộc nhiều vào LLM trong cả ba khâu: phân tích yêu cầu của người dùng, tìm kiếm địa điểm và xây dựng lịch trình. Trong quá trình phát triển sản phẩm, em đã tham gia đề xuất và triển khai các hướng cải tiến sau:

## 1. Đề xuất hướng phát triển Knowledge Graph

Từ trải nghiệm du lịch thực tế, em nhận thấy người dùng không chỉ cần biết nên đi đâu mà còn quan tâm đến lộ trình trên bản đồ, chi phí dự kiến, phương tiện di chuyển và những trải nghiệm đặc trưng tại từng khu vực.

Từ đó, em đề xuất xây dựng Knowledge Graph để biểu diễn mối quan hệ giữa điểm đến, khu vực và trải nghiệm đặc trưng, đồng thời phối hợp với Trung trong quá trình triển khai. Ví dụ:

```text
Hà Nội
  → special_experience → 36 phố phường
  → special_experience → Hàng Gai
  → special_experience → mua lụa, vải và các sản phẩm may mặc
```

Cách tổ chức này giúp hệ thống hiểu rõ hơn đặc trưng của từng khu vực và tạo cơ sở dữ liệu có cấu trúc cho quá trình đề xuất lịch trình.

## 2. Xây dựng toàn bộ quy trình lập kế hoạch cá nhân hóa

Em thiết kế và xây dựng toàn bộ quy trình từ đầu: tìm hiểu nhu cầu của người dùng; thu thập và chuẩn hóa dữ liệu về địa điểm, hoạt động từ TikTok, YouTube và Instagram; tìm kiếm, kiểm tra các địa điểm và nhà hàng phù hợp; sau đó sắp xếp thành lịch trình riêng cho từng người.

Từ danh sách địa điểm tiềm năng, hệ thống sử dụng Beam Search để tạo nhiều phương án và chọn ra lịch trình có điểm cao nhất dựa trên các tiêu chí:

- thời gian di chuyển;
- ngân sách;
- giờ mở cửa của địa điểm;
- mức độ đầy đủ của các bữa ăn;
- chất lượng địa điểm;
- sự đa dạng của hoạt động.

## Kết quả

Quy trình trên giúp giảm mức độ phụ thuộc vào LLM khi ra quyết định, đồng thời góp phần tối ưu chi phí và thời gian xử lý của hệ thống.

# Định hướng nghề nghiệp

Qua quá trình làm việc, em nhận ra bản thân hứng thú nhất với những công việc đòi hỏi phân tích bài toán và thiết kế logic để hệ thống có thể tự động xử lý, thay vì chỉ triển khai các chức năng theo yêu cầu có sẵn.

Em đặc biệt quan tâm đến:

- phân tích nhu cầu thực tế của người dùng;
- thiết kế luồng xử lý và cách tổ chức dữ liệu;
- lựa chọn thuật toán phù hợp với từng bài toán;
- tối ưu hiệu năng và quy trình vận hành của hệ thống.

Vì vậy, em muốn tiếp tục phát triển theo định hướng Backend Engineer. Trong dài hạn, mục tiêu của em là trở thành Senior Backend Engineer có khả năng thiết kế và giải quyết các hệ thống với logic nghiệp vụ phức tạp.
