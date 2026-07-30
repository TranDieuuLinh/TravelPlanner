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
2. `PlannerService` gọi LLM bằng structured output để tạo mô tả cấp cao cho
   từng ngày từ Explorer context và snapshot thống kê khu vực nhỏ.
3. `FinderService` điền khung giờ và địa điểm đã chọn.
4. `OverallChecker` báo cáo các rủi ro cơ bản.
5. `BackupPlanWorkflow` tạo và kiểm tra một phương án riêng.

UI Planner đã có trip chat bền vững theo user. Mỗi chat giữ một Explorer context
và plan hiện tại. Message đầu tạo plan; follow-up gửi context hiện tại cùng tối
đa tám user request gần nhất vào Explorer, sau đó Planner/Finder tạo revision
hoàn chỉnh. Backend giữ nguyên plan ID, tăng revision và lưu snapshot cũ thay vì
trả một plan identity mới. Các địa điểm của plan hiện tại được chuyển thành
`SelectedPlace` cho lần sửa, còn địa điểm user yêu cầu tránh được loại qua
`avoidPlaces`/constraint của Explorer.

Planner hiện dùng hai lượt LLM. Lượt research đề xuất journey shape và các
capability cần kiểm chứng; backend query Place active và vùng lân cận, sau đó
lượt Macro Planner tạo `MacroPlan`/`DayBriefs` từ evidence đã xác minh. Code ứng
dụng validate số ngày, region key, journey phase và việc phân bổ mọi
`selectedPlace`. Nếu model bỏ sót một `selectedPlace`, backend giữ địa điểm đó
trong danh sách chưa phân bổ kèm reason code và cảnh báo thay vì làm mất dữ liệu
hoặc làm hỏng toàn bộ request. Với các lỗi contract khác, backend yêu cầu model
sửa lại output tối đa ba lần với feedback validation mới ở từng lượt trước khi
trả lỗi provider. Nếu model tạo `allocatedSelectedPlaceRef` không tồn tại trong
input `selectedPlaces`, backend loại ref đó và thêm cảnh báo; ref do model bịa
không được truyền sang Finder. Finder vẫn tạo lịch
chi tiết bằng domain rule deterministic.
Khi không cấu hình LLM, runtime Planner không tự rơi về kế hoạch template.

Khi intake có URL video, Explorer dùng transcript STT, metadata và frame vision
để trích từng stop theo thứ tự. Candidate URL giữ `sourceOrder`,
`sourceDay`, `sourceTimeHint`, `sourceActivity` và `sourceDurationMinutes` khi
nguồn có nói rõ. STT chịu trách nhiệm chính cho day/order/activity và
`searchRegion`; OCR chịu trách nhiệm chính cho chữ trên bảng hiệu, địa chỉ và
giá; caption bổ sung bối cảnh. Evidence ngắn được giữ riêng trong
`sourceEvidence.stt`, `sourceEvidence.ocr` và `sourceEvidence.caption`.
Planner ưu tiên blueprint này; Finder tạo skeleton
`source_itinerary` và route optimizer không đảo thứ tự nguồn. Hard constraint
của user vẫn được ưu tiên hơn URL, và stop bị loại phải xuất hiện trong
`UnscheduledPlace`/warning thay vì bị thay thế âm thầm.

Video frame vision dùng `gemini-3.5-flash-lite` với media resolution `high`.
Frame được lấy thích nghi theo toàn bộ duration, không quá một frame mỗi giây,
tối đa 48 frame và xử lý theo
batch tối đa 10 ảnh; frame được chia đều giữa các batch để giảm thời gian chờ
batch lớn nhất. Tối đa năm batch frame vision được gọi song song bằng năm API key
khác nhau, ưu tiên các key cuối trong pool `GEMINI_API_KEY`; mức song song tự
giảm khi thiếu key hoặc batch. Kết quả được hợp nhất lại theo thứ tự frame gốc.
STT và frame vision chạy song song; candidate từ hai nguồn được gộp thay vì để
một nguồn loại bỏ nguồn còn lại. Marker ngày rõ ràng trong STT được dùng để sửa
day label OCR mâu thuẫn trong cùng chuỗi itinerary. Khi STT chuyển một ngày sang
day trip vùng khác, vùng đó trở thành `searchRegion` cho các stop của ngày mà
không thay đổi trip base. Observation thành công được
giữ lại nếu một batch khác lỗi. OCR ảnh/screenshot người dùng upload dùng cùng
model cấu hình. Không áp dụng giới hạn số place candidate có evidence sau bước
gộp; giới hạn 48 chỉ áp dụng cho số frame video được lấy mẫu.
TikTok photo post vẫn không được tải tự động và yêu cầu upload screenshot.

Số ngày dùng mặc định sản phẩm là 3 ngày khi user không nói rõ:

- nếu user nói rõ số ngày, số đó luôn thắng;
- nếu URL/OCR phủ ít hơn 3 ngày, giữ plan 3 ngày và Finder bổ sung catalog vào
  ngày trống hoặc ngày có ít stop hơn mức tối thiểu theo pace; stop URL/OCR vẫn
  được giữ nguyên và địa điểm bổ sung phải mang source `finder_suggestion`;
- nếu URL/OCR cần hơn 3 ngày, dùng cấu trúc `sourceDay` hoặc suy ra số ngày tối
  thiểu theo pace để xếp hết stop;
- nếu user yêu cầu nhiều ngày hơn số ngày nguồn phủ được, áp dụng cùng quy tắc:
  bổ sung catalog vào ngày trống hoặc ngày nguồn còn thưa;
- nếu user yêu cầu ít ngày hơn, toàn bộ stop không có `sourceDay` được phân bổ
  lại theo thứ tự trong đúng số ngày user yêu cầu. Stop có ngày nguồn rõ ràng
  vượt ngoài phạm vi vẫn đi vào `UnscheduledPlace`, không bị âm thầm đổi ngày.

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

### Giai đoạn 3: Resolve và lưu tự động

- tìm place phù hợp cho từng candidate;
- gộp candidate trùng nhưng giữ nhiều source ref;
- lưu kết quả dưới trạng thái `resolved`, `provisional` hoặc `unresolved`;
- không chặn intake để hỏi user;
- lưu dữ liệu resolve đầy đủ chỉ vào `UserMustPlace`, không ghi `Place`;
- Explorer bàn giao `intakeId + userId + explorer` nhưng không tự gọi Planner.
- Planner downstream dùng context và chuyển tiếp hai khóa; Finder downstream
  đọc `UserMustPlace` theo cả `intakeId + userId`.

### Giai đoạn 4: Explorer

Explorer hợp nhất `SelectedPlaces`, `UserState` và `TripConstraints`, phát hiện
thông tin thiếu hoặc mâu thuẫn và chỉ hỏi câu có tác động cao. Kết quả gồm
`TravelIntent` đã chuẩn hóa, hard constraints, soft preferences và unresolved
questions.

Explorer còn tạo `PreferenceSnapshot` cho intake hiện tại. Nếu có authenticated
user, signal đủ confidence được aggregate vào cột JSON
`users.travel_preferences`; raw prompt, OCR và transcript không đi vào profile.
Planner nhận `effectiveProfile`, nhưng explicit constraint của chuyến hiện tại
luôn ưu tiên hơn profile dài hạn.

### Giai đoạn 5: Planner

Planner tạo `MacroPlan` và `DayBriefs`:

- mỗi ngày có chủ đề, khu vực chính, nhịp độ và mục tiêu;
- ưu tiên profile ở cấp khu vực nhỏ nhất đang có trong `regionKey`;
- hiểu travel style là nhịp và hình dạng hành trình, không lặp cùng một hoạt
  động cho mọi ngày;
- chuyến dài có thể tạo `journeyPhases` và mở rộng sang region lân cận đã được
  tool kiểm chứng;
- theme sáng tạo như biển, hải sản, hiking hoặc camping phải có capability
  evidence từ Place active trước khi được mô tả như một khả năng có thật;
- phân bổ địa điểm bắt buộc trước, sau đó tối ưu sở thích;
- không gán giờ chính xác khi chưa có đủ dữ liệu route/place;
- ghi rõ địa điểm nào chưa thể phân bổ.
- khi có URL itinerary, giữ thứ tự/ngày/timing cue của nguồn; không biến timing
  cue mơ hồ thành giờ chính xác do nguồn xác nhận.

### Giai đoạn 6: Finder

Finder điền item cụ thể:

- với intake có URL hoặc ảnh/OCR, xếp candidate từ nguồn trước; Finder chỉ bổ
  sung catalog khi ngày trống hoặc số stop nguồn thấp hơn mức tối thiểu theo
  pace (`relaxed=2`, `balanced=3`, `packed=4`);
- Finder dùng theme, day-part goal, region và constraint do Planner tạo để chọn
  địa điểm bù; stop nguồn không bị thay thế và suggestion phải được đánh dấu;
- chọn khung giờ theo giờ hoạt động và timing claim;
- rank Place bằng mô tả theo theme/goal của ngày trước, sau đó rerank bằng
  category, tags, region, confidence và các dữ liệu có cấu trúc;
- fallback có kiểm soát lên region cha khi locality nhỏ thiếu Place, nhưng không
  dùng hotel/restaurant/transport để lấp activity sai chủ đề;
- thêm route leg, thời gian đệm, bữa ăn và nghỉ;
- giữ source ref từ `SelectedPlace` tới `TripItem`;
- tối ưu thứ tự item có tọa độ bằng nearest-neighbour rồi 2-opt;
- lấy route pedestrian/car từ HERE Routing v8 sau khi xếp stop; leg HERE có
  geometry, `fetchedAt`, `source=here_routing_v8`, `verified=true`, còn lỗi
  provider fallback về ước tính địa lý `verified=false`;
- với trip có `startDate`, lấy thêm HERE Public Transit theo giờ kết thúc stop;
  chọn transit khi user ưu tiên bus/train, nếu không giữ làm alternative; không
  gọi timetable hiện tại cho trip chưa có ngày;
- chỉ thêm địa điểm mới từ place provider khi cần hoàn thiện ngày và phải đánh
  dấu đây là đề xuất của hệ thống;
- đưa địa điểm không xếp được vào `UnscheduledPlace` với reason code.

Adapter Finder dùng `RepositoryFinderPlaceTool` trong runtime để tìm Place đang
active theo `regionKey` và `focusTags`. Nếu catalog vùng trống nhưng có
`SelectedPlace`, Finder vẫn có thể lập plan giới hạn trong danh sách đã xác
nhận; cảnh báo giới hạn phải xuất hiện trong output.

### Giai đoạn 7: CheckOverall

Check chạy theo lớp:

1. schema và ID;
2. domain rule: chồng lấn, ngày trống, mật độ, ngân sách, item khóa;
3. provider: place identity, giờ hoạt động, route và độ mới;
4. an toàn/nội dung;
5. tóm tắt issue, bằng chứng và hành động sửa.

Issue không chỉ là chuỗi văn bản; phải có code, severity, affected item,
evidence, `canAutoFix` và phạm vi sửa.

Trong implementation hiện tại, các check schema/allocation deterministic được
chạy thật. Check route chỉ báo issue `info` cho leg fallback chưa xác minh.
Giờ hoạt động, availability và thời tiết live chưa có provider thì vẫn được trả
thành issue `info`, không được mô tả như đã xác minh. Warning làm
Main Plan ở trạng thái `draft` để sửa hoặc tạo backup; chỉ report `passed` mới
khóa plan.

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
- source claim/candidate đã được intake tự động lưu kèm confidence, provenance
  và resolution status;
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
- Candidate được tự động lưu theo lựa chọn sản phẩm no-interruption, nhưng phải
  giữ confidence và resolution status để Finder/Check có thể cảnh báo.
- Không chuyển caption/câu quảng bá/danh sách nhiều venue thành một PlanItem.
  URL place chưa resolve được danh tính cụ thể và tọa độ phải ở lại lớp
  provenance, không xuất hiện trong plan; phần thiếu được Finder điền bằng Place
  đã chuẩn hóa khi policy cho phép.
- `sourceActivity` là mô tả hành động ngắn có evidence, không phải nơi sao chép
  nguyên caption hoặc transcript.
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
- Đặt timeout và retry có giới hạn. Gemini runtime hiện retry tối đa ba lần với
  backoff cho lỗi mạng, `429`, `500`, `502`, `503` và `504`; lỗi provider được
  chuyển thành lỗi API có kiểm soát mà không ghi response hoặc API key vào log.
  Không áp dụng khoảng chờ cố định giữa các call thành công. Khi Gemini trả
  `Retry-After` hoặc `google.rpc.RetryInfo.retryDelay`, limiter dùng thời gian
  provider yêu cầu (tối đa 60 giây) trước khi retry. `GEMINI_API_KEY` nhận một
  key hoặc nhiều key phân tách bằng dấu phẩy. Client dùng chung pool key trong
  tiến trình; khi key hiện tại trả `429`, key đó được cooldown theo chỉ dẫn của
  provider và call chuyển sang key kế tiếp ngay. Key trả `401/403` bị loại khỏi
  pool cho đến khi tiến trình khởi động lại. API key không được ghi vào log.
  Circuit breaker vẫn là phần chưa triển khai.
- Chỉ cache khi quyền riêng tư, độ mới và phạm vi user cho phép.
- Giữ provider call sau `LLMClient`; domain code không gọi trực tiếp SDK của
  provider.
