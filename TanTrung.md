* Role: Data Engineer

* Achievement:
    Trong dự án AI TravelPlanner này, em thất bại ở lần đầu khi chi mà db chỉnh là những table thuần.
    Cụ thể, với version 1:
        - Em chỉ có 1 cái table liệt kê các danh sách địa điểm (du lịch, nhà hàng, ...)
        - Sau đó, đưa 1 loại cái tên của các loại địa điểm và kêu LLM chọn dựa trên insight người dùng
    Vấn đề: 
        - Sau khi làm xong, kế hoạch sẽ khá tệ khi ngày thì thiếu vị trí tham quan, ngày thì ko có ăn.
        - Chưa kể đến việc liệt kê địa điểm xong thì làm gì.
    Do đó, em mới bắt đầu nghĩ tới việc xây lại database, là đập đi xây lại như tụi em đã nói trong lần thuyết trình.
    Với version 2:
        - Em xây dựng database theo kiến trúc Knowledge Graph (Đồ thị tri thức), mục tiêu là giải quyết được vấn đề:
            + Thiếu vị trí tham quan, ăn uống.
            + Không biết đi đâu, làm gì khi đến địa điểm nào đó.
        - Từ lúc này, em chỉ tập trung xử lý Knowledge Graph và xây dựng giao diện admin để quản lý và cải tiến cái này.
        - Đôi khi thì có cùng với chị Linh để chọn và tối ưu thuật toán.

* Next step:
    - Mở rộng và cải tiến Knowledge Graph:
        + Thêm dữ liệu.
        + Thêm các loại edge, node để phù hợp hơn.
    - Giao diện admin:
        + Màn hình để dễ quản lý, thao tác hơn.
        + Guideline để dùng AI hỗ trợ xử lý tạo node, edge và người dùng chỉ là người xác thực lại dữ liệu có đúng chưa.

* Why:
    - Chuyên ngành học của em là về Khoa học dữ liệu, chuyên về dữ liệu và AI, nên em đã có kinh nghiệm ít nhiều gì đó về xử lý dữ liệu.
    - Ngoài ra, theo em thấy vì với các ứng dụng AI, dữ liệu là cái quan trọng nhất.    