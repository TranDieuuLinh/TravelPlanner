# Đặc tả AI Planner

## Mục tiêu

Biến nguồn cảm hứng và yêu cầu của user thành lịch trình có cấu trúc, giải thích
được, tôn trọng ràng buộc và có thể chỉnh sửa ở cấp từng item. Model hỗ trợ trích
xuất và đề xuất; code ứng dụng chịu trách nhiệm về source, ID, xác nhận của user,
kiểm tra, lưu trữ, phân quyền và dữ liệu thực tế.

Planner gồm hai pipeline nối tiếp:

```text
URL -> Import -> Extract -> Resolve -> Confirm
                                      |
                                      v
Explorer -> Planner -> Finder -> Check -> Main Plan
                                    |
                                    v
                              Backup Plan
```

`Confirm` là ranh giới quan trọng: claim do AI trích xuất không tự động trở thành
yêu cầu của user.

## Luồng xử lý hiện tại

1. `ExplorerService` chuẩn hóa ý định và tạo câu hỏi làm rõ.
2. `PlannerService` tạo mô tả cấp cao cho từng ngày.
3. `FinderService` điền khung giờ và địa điểm đã chọn.
4. `OverallChecker` báo cáo các rủi ro cơ bản.
5. `BackupPlanWorkflow` tạo và kiểm tra một phương án riêng.

`StubLLMClient` hiện chỉ trả văn bản placeholder. Phần lớn cấu trúc plan được tạo
bởi các domain service theo quy tắc, chưa phải model thật.

## Luồng mục tiêu của MVP

### Giai đoạn 1: Import

- kiểm tra URL và nhận diện connector;
- lấy nội dung được phép và ghi metadata/provenance;
- trả job có trạng thái thay vì giữ HTTP request mở;
- giữ kết quả từng phần để retry.

### Giai đoạn 2: Extract

Structured output của extraction gồm:

- `placeClaims`: tên thô, alias, khu vực được nhắc đến và evidence;
- `activityClaims`: hoạt động, món ăn hoặc trải nghiệm;
- `timingClaims`: thời điểm nên đến, thời lượng và thứ tự được gợi ý;
- `costClaims`: giá được nguồn nhắc tới, tiền tệ và thời điểm của claim;
- `adviceClaims`: mẹo, cảnh báo hoặc điều kiện;
- confidence riêng cho từng claim.

Extraction không được kết luận giờ mở cửa, giá hiện tại hay tọa độ chỉ từ lời nói
trong video. Đó là claim của nguồn cho đến khi provider xác minh.

### Giai đoạn 3: Resolve và Confirm

- tìm place phù hợp cho từng candidate;
- gộp candidate trùng nhưng giữ nhiều source ref;
- đánh dấu kết quả mơ hồ hoặc không tìm thấy;
- yêu cầu user xác nhận place, mức ưu tiên và mục bắt buộc;
- tạo `SelectedPlace` làm đầu vào Planner.

### Giai đoạn 4: Explorer

Explorer hợp nhất `SelectedPlaces`, `UserState` và `TripConstraints`, phát hiện
thông tin thiếu hoặc mâu thuẫn và chỉ hỏi câu có tác động cao. Kết quả gồm
`TravelIntent` đã chuẩn hóa, hard constraints, soft preferences và unresolved
questions.

### Giai đoạn 5: Planner

Planner tạo `MacroPlan` và `DayBriefs`:

- mỗi ngày có chủ đề, khu vực chính, nhịp độ và mục tiêu;
- phân bổ địa điểm bắt buộc trước, sau đó tối ưu sở thích;
- không gán giờ chính xác khi chưa có đủ dữ liệu route/place;
- ghi rõ địa điểm nào chưa thể phân bổ.

### Giai đoạn 6: Finder

Finder điền item cụ thể:

- chọn khung giờ theo giờ hoạt động và timing claim;
- thêm route leg, thời gian đệm, bữa ăn và nghỉ;
- giữ source ref từ `SelectedPlace` tới `TripItem`;
- chỉ thêm địa điểm mới từ place provider khi cần hoàn thiện ngày và phải đánh
  dấu đây là đề xuất của hệ thống;
- đưa địa điểm không xếp được vào `UnscheduledPlace` với reason code.

### Giai đoạn 7: CheckOverall

Check chạy theo lớp:

1. schema và ID;
2. domain rule: chồng lấn, ngày trống, mật độ, ngân sách, item khóa;
3. provider: place identity, giờ hoạt động, route và độ mới;
4. an toàn/nội dung;
5. tóm tắt issue, bằng chứng và hành động sửa.

Issue không chỉ là chuỗi văn bản; phải có code, severity, affected item,
evidence, `canAutoFix` và phạm vi sửa.

### Giai đoạn 8: Main Plan và Backup Plan

Main Plan được chốt từ một version đã kiểm tra. Backup Planner nhận Original
MacroPlan, Main Plan và CheckOverall Report để giải quyết rủi ro cụ thể. Backup
phải có `parentPlanId`, được validate độc lập và không mutate Main Plan.

## Đầu vào bắt buộc

- điểm đến và ngày đi hoặc thời lượng;
- nơi xuất phát và quy mô/thành phần nhóm khi có liên quan;
- ngân sách và đơn vị tiền tệ;
- nhịp độ và phong cách du lịch;
- sở thích, địa điểm bắt buộc, địa điểm tránh, nhu cầu hỗ trợ tiếp cận và ràng
  buộc;
- URL/place tham khảo đã chọn kèm độ tin cậy khi trích xuất;
- source claim đã được user xác nhận và mức ưu tiên của từng `SelectedPlace`;
- item đã khóa và phạm vi được phép thay đổi khi chỉnh sửa lại.

Nếu thiếu thông tin quan trọng, chỉ hỏi một số câu có giá trị cao. Không buộc
người dùng bắt đầu lại sau khi trả lời.

## Giao ước đầu ra

Sử dụng structured output bị ràng buộc bởi schema. Một plan phải có:

- tên, điểm đến, timezone, giả định và độ tin cậy;
- chủ đề ngày và các item có thứ tự;
- ID item ổn định, giờ bắt đầu/kết thúc hoặc khung giờ địa phương và thời lượng;
- tham chiếu địa điểm đã chuẩn hóa nếu có;
- chặng di chuyển, thời gian ước tính và phương tiện gợi ý giữa các item;
- chi phí ước tính kèm tiền tệ và độ tin cậy;
- nguồn/provenance cho dữ liệu được nhập hoặc xác minh từ bên ngoài;
- danh sách địa điểm đã xác nhận nhưng chưa xếp được cùng lý do;
- cảnh báo và câu hỏi chưa được giải quyết;
- phương án thay thế hoặc plan dự phòng được liên kết riêng.

Văn bản tự do của model không được là biểu diễn duy nhất của thời gian, chi phí,
tuyến đường hoặc danh tính địa điểm.

## Quy tắc lập kế hoạch

- Ưu tiên ràng buộc cứng trước sở thích.
- Giữ nguyên item đã khóa khi chỉnh sửa lại.
- Không tự bịa giờ mở cửa, giá, trạng thái booking hoặc thời gian di chuyển chính
  xác.
- Gom các địa điểm gần nhau nhưng phải xét giờ hoạt động và nhịp độ người dùng.
- Thêm khoảng đệm thực tế cho di chuyển, ăn uống, check-in và nghỉ ngơi.
- Hiển thị rõ các giả định.
- Giữ địa điểm người dùng đã chọn trừ khi xung đột với ràng buộc cứng; khi đó
  phải giải thích.
- Không biến place candidate chưa xác nhận thành địa điểm bắt buộc.
- Không âm thầm bỏ địa điểm đã xác nhận; phải xếp hoặc trả về `UnscheduledPlace`.
- Phân biệt claim từ nguồn, dữ liệu provider xác minh và suy luận của model.
- Plan dự phòng phải dùng được độc lập và được liên kết với plan chính.

## Các lớp kiểm tra

1. Kiểm tra schema.
2. Kiểm tra domain theo quy tắc: ngày trống/trùng, thời gian chồng lấn, mật độ,
   tổng ngân sách và giữ nguyên item đã khóa.
3. Kiểm tra qua provider: danh tính địa điểm, giờ mở cửa, tính khả thi của tuyến
   đường và độ mới.
4. Kiểm tra an toàn/nội dung.
5. Tóm tắt vấn đề cho người dùng kèm hành động sửa có phạm vi.

## Đánh giá chất lượng

Duy trì bộ evaluation ưu tiên tiếng Việt và có version, bao gồm:

- yêu cầu thiếu thông tin hoặc mâu thuẫn;
- nhiều ngân sách, nhịp độ, loại nhóm và ràng buộc tiếp cận;
- địa điểm đóng cửa và tuyến đường không khả thi;
- nội dung độc hại/prompt injection trong URL được nhập;
- video không có transcript, địa điểm mơ hồ và nhiều URL nhắc cùng một place;
- source claim sai hoặc cũ nhưng provider có dữ liệu mới hơn;
- mọi `SelectedPlace` phải được xếp hoặc có lý do chưa xếp;
- lần chỉnh sửa lại phải giữ item đã khóa;
- tính độc lập của plan dự phòng;
- dữ liệu bịa đặt và mức độ tự tin không có nguồn.

Theo dõi độ hợp lệ của schema, tuân thủ ràng buộc cứng, bằng chứng cho dữ liệu,
tính khả thi của tuyến đường, bảo toàn chỉnh sửa, độ trễ và chi phí. Vẫn cần con
người đánh giá chất lượng lịch trình mang tính chủ quan.

## Vận hành câu lệnh và mô hình

- Version hóa prompt và output schema.
- Ghi model/provider/version và phiên bản evaluation, không ghi toàn bộ prompt
  riêng tư.
- Đặt timeout, retry có giới hạn và circuit breaker.
- Chỉ cache khi quyền riêng tư, độ mới và phạm vi user cho phép.
- Giữ provider call sau `LLMClient`; domain code không gọi trực tiếp SDK của
  provider.
