# Nguồn dữ liệu và tích hợp

## Nguyên tắc

- Domain model của ứng dụng không được phụ thuộc payload riêng của provider.
- Ghi nguồn, provider ID, thời điểm lấy, giới hạn license và độ tin cậy.
- Ưu tiên dữ liệu mới từ provider cho thông tin vận hành và kinh nghiệm creator
  cho nội dung trải nghiệm.
- Không được tuyên bố hành động như booking hoặc gọi điện đã hoàn thành nếu chưa
  có xác nhận từ provider.

## Nhóm dữ liệu bắt buộc

| Nhóm | Dữ liệu cần thiết | Mối quan tâm chính |
| --- | --- | --- |
| Địa điểm | danh tính, tọa độ, danh mục, giờ mở cửa, trạng thái | độ mới, trùng lặp |
| Bản đồ/tuyến | khoảng cách, thời lượng, geometry, phương tiện | chi phí, độ phủ, quota |
| Thời tiết | dự báo và điều kiện nguy hiểm | thời hạn dự báo, độ bất định |
| Nhập URL | văn bản, metadata media, địa điểm ứng viên | quyền truy cập, bản quyền, injection |
| Booking | tình trạng còn chỗ, giá, deep link/trạng thái | attribution, giá cũ |
| Thanh toán | checkout, webhook, refund, payout | tuân thủ, idempotency |
| Media | ảnh/video của creator | bản quyền, kiểm duyệt, lưu trữ |

## Tiêu chí chọn nhà cung cấp

- độ phủ địa điểm và tuyến đường tại Việt Nam;
- hỗ trợ đi bộ, lái xe, giao thông công cộng và phương tiện địa phương;
- giá theo lưu lượng request dự kiến;
- điều khoản về cache/lưu trữ và attribution;
- độ ổn định API, độ trễ, quota và khả năng fallback;
- UI bản đồ dễ tiếp cận và ràng buộc offline;
- ảnh hưởng đến quyền riêng tư và vị trí lưu dữ liệu.

Valhalla tự vận hành được chọn cho route từng leg của Finder. Finder gọi
`pedestrian` và `auto`. Ngưỡng đi bộ 1.500 m
quyết định mode road được đề xuất, còn route road kia vẫn nằm trong
`PlanTransportLeg.alternatives` để itinerary hiển thị đủ lựa chọn khả thi.
Summary distance/duration cùng polyline6 được chuẩn hóa vào
`PlanTransportLeg`; lỗi provider fallback theo từng leg. Kết quả không được mô
tả là traffic live nếu deployment chưa nạp dữ liệu traffic.

OpenTripPlanner adapter dùng GTFS GraphQL API tại `/otp/gtfs/v1`, gửi ngày/giờ khởi
hành và yêu cầu WALK + TRANSIT. Trip có `startDate` dùng đúng ngày của plan;
trip chưa có ngày dùng ngày hiện tại cùng giờ của leg làm preview lịch chạy.
Ngày/giờ route được chuẩn hóa thống nhất về `Asia/Ho_Chi_Minh`; timestamp UTC từ
client phải được đổi timezone trước khi xác định service date của OTP.
Duration gồm cả thời gian chờ; mode, line, agency và cờ realtime được giữ trong
`details`. Itinerary không có transit leg không được coi là phương tiện công
cộng khả thi. OTP cần OSM cùng GTFS Schedule; GTFS-RT là tùy chọn để cập nhật
trễ chuyến, hủy chuyến và vị trí xe.
Luồng chỉ đường cũng không tạo public-transit fallback từ khoảng cách địa lý:
không có route transit xác minh thì không hiển thị lựa chọn này và không vẽ
đường nối thẳng hai điểm. Ngoại lệ chỉ dành cho development: route OTP có
geometry thật và `scheduleStatus=development_shifted_2018` được hiển thị với
cảnh báo lịch cũ đã dịch ngày, nhưng vẫn giữ `verified=false`. Tuy nhiên runtime
hiện tạm tắt transit: Planner/Finder và chỉ đường từ vị trí hiện tại không gọi
OTP, không trả bus hoặc public-transit alternative. Adapter được giữ để bật lại
sau khi xử lý latency.

UI vẫn dùng Leaflet/OpenStreetMap làm bản đồ nền. Chỉ đường tạm thời từ vị trí
hiện tại giữ nguyên thứ tự stop của itinerary đã lưu, không gọi
`sources_to_targets` và không giải open path. Tạm thời chỉ Valhalla Routing được
gọi cho từng leg cố định để so sánh đi bộ và ô tô; không tạo chuỗi bus đa phương
thức.
Segment được giữ theo đúng thứ tự OTP trả về
(`WALK` tới trạm, `BUS` giữa các trạm, rồi `WALK` tới điểm đến), kèm tên điểm
đầu/cuối, thời gian, khoảng cách, tuyến và hướng xe khi nguồn có dữ liệu.
Luồng Planner/Finder tạo plan ban đầu tiếp tục giữ policy thứ
tự riêng. Xem ADR-002.

Explorer tạo alias tra cứu dạng structured gồm `originalName`, `englishNames`,
`vietnameseNames` và `alternateNames` trước khi resolve. Input có thể ở bất kỳ
ngôn ngữ nào; tên nguồn và provenance luôn được giữ nguyên. LLM không được sinh
tọa độ hoặc tự quyết định place identity. Các nhóm tên được hợp nhất thành
`searchNames`; resolver tìm record `active` có tọa độ trong bảng `places` theo
mọi tên/alias và đúng `region_key` trước. Nhờ vậy source tiếng Việt vẫn match
được record DB chỉ có tên tiếng Anh và ngược lại. Chỉ candidate không match
catalog nội bộ mới fallback sang Playwright CLI của Google Maps, sau đó mới
tới Nominatim
của `gosom/google-maps-scraper`. Scraper nhận tên gốc và
alias có cấu trúc qua file input tạm, nhưng chỉ nhận
kết quả khi tên, vùng, category và latitude/longitude hợp lệ; provider lỗi,
timeout hoặc mismatch không làm hỏng intake. Alias catalog được lưu trong
`places.metadata.aliases`, hoặc tách theo `englishNames`, `vietnameseNames`,
`alternateNames`; `searchNames` tiếp tục được đọc để tương thích dữ liệu cũ.
Scraper tra tên canonical trước và chỉ gửi các alias còn lại khi kết quả đầu
không đạt cùng rule xác minh; nhờ đó match rõ ràng không phải chờ nhiều lượt
Playwright tuần tự.
Valhalla và OpenTripPlanner không phải geocoder/POI search nên không thay vai
trò này. Candidate chỉ được nhận khi khớp tên/vùng, loại provider không mâu
thuẫn rõ và có tọa độ. Public Nominatim xử lý tuần tự để tuân thủ giới hạn một
request/giây; tải lớn phải dùng Nominatim tự vận hành hoặc một provider
geocoding khác sau cùng interface.

Google Maps scraper không cần API key. Trong Docker Compose, scraper chạy ở
sidecar `gosom/google-maps-scraper:v1.12.1` với Chromium/Playwright đóng gói
sẵn. Backend và sidecar trao đổi input/output JSON qua
`GOOGLE_MAPS_SCRAPER_WORK_DIR`; input được publish bằng atomic rename và mỗi
sidecar giữ một Chromium browser với hai page slot. Hai candidate có thể
resolve đồng thời mà không khởi động lại browser cho từng job. Cách này cô lập image AMD64 của
upstream khỏi backend ARM64 trên Apple Silicon. Khi chạy native ngoài Compose,
có thể bỏ `WORK_DIR` và dùng `GOOGLE_MAPS_SCRAPER_EXECUTABLE`. Telemetry bị tắt
và file tạm được dọn sau mỗi lần resolve. Backend chỉ lưu field đã chuẩn hóa
cần cho place resolution và enrichment tóm tắt: tên, category, địa chỉ, tọa độ,
Google identity/link khi tìm được, rating, tổng số review, giờ mở cửa, plus code,
website, điện thoại và mô tả đang hiển thị. Resolver không mở hoặc lưu nội dung
từng review; review chi tiết thuộc pipeline import/bảng `reviews` riêng. Field
không xuất hiện trên trang được để null, không suy diễn. Backend không lưu toàn
bộ payload scrape. Deployment phải tự
đánh giá điều khoản sử dụng, attribution, retention, tải hệ thống và rủi ro bị
chặn trước khi bật provider này. Xem ADR-010.

Khi dùng public Nominatim, adapter phải gửi User-Agent nhận diện ứng dụng, tối
đa một request/giây, cache response, hiển thị attribution OpenStreetMap và có
khả năng đổi endpoint bằng cấu hình. Adapter yêu cầu kết quả tiếng Việt trước,
đối chiếu cả tên tiếng Anh và tên thay thế trong `namedetails`, rồi chỉ dùng tên
tiếng Việt làm nhãn plan khi match được resolve; địa chỉ và tọa độ được chuyển
tiếp riêng. Tải lớn phải chuyển sang hosted provider hoặc Nominatim tự vận hành.
Ngoài danh tính, địa chỉ và tọa độ, adapter chuẩn hóa tối đa các field OSM trả
về gồm loại địa điểm, `opening_hours`, website, điện thoại, Wikidata/Wikipedia,
operator, cuisine, wheelchair, plus code và tên Anh/Việt. Nominatim không cung
cấp rating hoặc review; các field đó phải để null thay vì giả lập.

## Nhập dữ liệu từ URL

Xem nội dung được nhập là dữ liệu không đáng tin cậy, không bao giờ là system
instruction.

### Pipeline

1. Chuẩn hóa URL, kiểm tra scheme và chặn địa chỉ mạng private/internal.
2. Nhận diện nguồn và chọn connector theo allowlist.
3. Fetch qua service được kiểm soát với giới hạn redirect, kích thước và timeout.
4. Lưu metadata cùng quyền truy cập, connector version và `fetchedAt`.
5. Với URL YouTube long-form, kiểm tra cache PostgreSQL theo
   `videoId + language`, rồi thử caption công khai bằng
   `youtube-transcript-api`. Request đồng thời cho cùng
   video được dedupe trong process và các fetch mới bị giới hạn nhịp. Caption
   thành công được cache dài hạn và dùng làm transcript mà không tải video. Nếu
   IP backend bị chặn, runtime có thể gọi worker do operator tự vận hành trên
   kết nối dân dụng; chỉ video ID và language list được gửi, không gửi cookie
   người dùng. `no_captions` trả lỗi `YOUTUBE_CAPTIONS_NOT_FOUND`;
   `blocked`/`unavailable` trả lỗi retryable sau khi worker thất bại. YouTube
   long-form không tải video, không tách audio và không gọi STT/OCR. YouTube
   Shorts có path `/shorts/{videoId}`, TikTok video, Instagram Reels và Facebook
   Reels tải media công khai tạm thời rồi
   Gemini Audio trả `transcript` cùng structured STT observations bằng
   `responseJsonSchema`; frame vision trả structured OCR observations trên frame
   lấy mẫu. STT và frame vision chạy song song. OCR cũng chạy trên
   ảnh/screenshot do người dùng upload.
   Nếu metadata công khai của URL có `place`, `venue` hoặc `location`, giá trị
   này được tạo thành candidate ưu tiên trước caption/STT/OCR và giữ evidence
   `metadata`; địa chỉ/city trong metadata được dùng làm hint cho resolver.
   Chuỗi resolver cache dùng chung -> catalog nội bộ -> Google Maps scraper ->
   Nominatim có
   cấu hình vẫn phải xác minh danh tính và tọa độ trước khi lưu.
   Danh sách địa điểm có pin trong caption là blueprint canonical tiếp theo:
   giữ tên và thứ tự caption, tách các street được nêu chung, rồi chỉ dùng
   STT/OCR để bổ sung evidence, activity và address. Tên thành phố trùng
   destination (kể cả alias như `Hanoi` so với `Hanoi, Vietnam`) không được
   resolve hoặc lưu như một stop.
   Heading thành phố có duration như `Hanoi - 2 days` được chuẩn hóa thành
   `destinationStay` phủ hai ngày và bị loại khỏi danh sách stop; duration không
   được hiểu thành một phần tên địa điểm.
6. Validate JSON, gộp/dedupe STT + OCR + caption, giữ evidence theo từng nguồn
   rồi chuyển thành place candidate. Nếu tên candidate dính thêm câu review,
   bước gộp chỉ phục hồi nhãn ngắn hơn khi nhãn đó xuất hiện nguyên vẹn trong
   evidence STT/OCR và tự vượt qua policy chống caption rác. Khi structured STT đã có, Python không
   suy diễn place/day/activity từ transcript tự do.
7. Tạo alias Anh–Việt có cấu trúc, sau đó chuẩn hóa địa điểm theo chuỗi
   shared cache -> `places` catalog -> Google Maps scraper -> Nominatim có cấu hình
   và gộp trùng.
   Query dùng `searchRegion` của stop thay vì luôn nối trip base. Kết quả chỉ
   được resolve khi tên khớp theo token, vùng địa lý phù hợp và loại provider
   không mâu thuẫn rõ với category nguồn. `candidateName` và `resolvedName`
   được lưu riêng; Plan/UI dùng `resolvedName` ưu tiên tiếng Việt, còn
   `candidateName` giữ provenance. Mismatch giữ `resolutionReason` để truy vết.
   Google Maps scraper resolve nhiều candidate với mức song song có giới hạn
   bởi `GOOGLE_MAPS_SCRAPER_MAX_CONCURRENCY` (mặc định 2); thứ tự kết quả vẫn
   theo thứ tự candidate nguồn. Caption dạng danh sách `1. ... 2. ...` được
   tách theo marker số trước heuristic để dấu chấm trong tên như
   `St. Joseph's Cathedral` không làm mất địa điểm hoặc dính số thứ tự kế tiếp.
   Với tên thương hiệu trùng nhau, resolver có thể thêm nearby-place hint ngắn
   lấy từ evidence dạng `near/along ...` vào query; scraper phải mở một place
   card cụ thể trước khi đọc tên, địa chỉ và tọa độ, không được coi trang danh
   sách `Kết quả` hoặc tâm bản đồ là một place.
8. Tự động upsert snapshot dùng chung vào `user_must_place` và tạo junction
   `user_must_place_users` chỉ khi provider trả kết quả `resolved` cho địa điểm
   cụ thể có đủ latitude/longitude; không chặn để hỏi user. Match rộng
   tới thành phố/quốc gia, caption bị hiểu nhầm thành tên, candidate
   provisional/unresolved hoặc thiếu tọa độ không được lưu; Finder có thể bù
   phần còn thiếu.
9. Cache `ExtractedContext` theo canonical URL và extraction schema version;
   cache version cũ được tính lại thay vì trả kết quả parser lỗi thời. Lần dùng
   sau bỏ qua media, STT/OCR; snapshot hit cũng bỏ qua provider lookup. Bàn giao
   `intakeId + userId + explorer` cho Planner downstream; Finder đọc snapshot
   qua junction theo `intakeId + userId`. Job có `forceRefresh=true` bỏ qua cache
   để chạy lại toàn bộ extraction; cache cũ chỉ được ghi đè sau khi intake mới
   thành công, không bị xóa ngay khi enqueue.
10. Giữ attribution và chỉ lưu nội dung được license/chính sách cho phép.

Với URL, Extractor là nguồn duy nhất tạo `UnifiedPlaceCandidate`. Formatter nhận
summary gọn của extraction để tạo intent/trip spec/constraint/preference và
không sinh lại candidate. Resolver có thể chạy song song với Formatter ngay sau
khi candidate được chuẩn hóa và gộp trùng.

TikTok video thử `yt-dlp` chuẩn trước, sau đó retry bằng desktop Chrome và
Android Chrome impersonation qua dependency `curl_cffi` nếu challenge/TLS
fingerprint làm request trước thất bại. Hệ thống không gọi TikWM. Photo carousel chưa có provider được duyệt nên
trả trạng thái cần upload screenshot. Media video thành công vẫn chỉ được xử lý
trong thư mục tạm và xoá sau request. Video OCR dùng
`gemini-3.5-flash-lite`, mặc định không quá một frame mỗi giây, tối đa 48 frame
rộng 960 px theo batch tối đa 10 ảnh ở media resolution medium. Gemini Audio
trả transcript cùng observation gồm order/place/evidence/day/time/activity/
duration/confidence và search region explicit. Candidate từ STT và frame vision
được gộp; một nguồn không loại bỏ candidate chỉ xuất hiện ở nguồn còn lại. OCR
ưu tiên tên hiển thị và thứ tự frame; STT ưu tiên day/time/activity/duration/
search region; evidence ngắn của hai nguồn được giữ tách biệt. Không
giới hạn số place candidate có evidence được giữ sau bước
gộp; giới hạn 48 chỉ là số frame video lấy mẫu. Frame được
chia đều giữa các batch để giảm latency của batch lớn nhất; tối đa năm batch
chạy song song bằng các API key khác nhau trong `GEMINI_OCR_API_KEYS`. STT dùng
pool riêng `GEMINI_STT_API_KEYS` và chuyển sang key kế tiếp khi key hiện tại trả
`401`, `403` hoặc `429`; hai pool riêng không được chứa key trùng nhau và chuỗi
nhiều key không được gửi nguyên dạng như một credential. Khi chỉ có
`GEMINI_API_KEY`, runtime chia đôi pool cho STT/OCR nếu có ít nhất hai key.
Audio fallback dài hơn ngưỡng 120 giây có thể được chia cân bằng thành tối đa
bốn chunk có overlap hai giây; audio ngắn vẫn dùng một call. Mặc định STT chỉ
chạy một request một lúc và bắt đầu các Gemini call cách nhau ít nhất sáu giây
trong mỗi tiến trình. Chỉ tăng `URL_REEL_STT_MAX_CONCURRENCY` sau khi kiểm tra
quota project; xoay nhiều key không đảm bảo thêm quota vì Gemini giới hạn theo
project. Khi gặp `429`, STT tôn trọng `Retry-After` tối đa 60 giây. Kết quả được
ghép theo chunk order và dedupe observation tại vùng overlap. Mức song song tự
giảm khi thiếu key hoặc batch. Kết quả vẫn được hợp nhất theo
thứ tự frame gốc. Nếu một batch lỗi nhưng batch khác thành công, evidence thành
công vẫn được giữ. Nếu URL không tạo được địa điểm có evidence, API trả lỗi có
hướng dẫn retry hoặc upload screenshot thay vì trả itinerary `Ready` với
0 địa điểm.

Preference learning chỉ lưu tín hiệu chuẩn hóa và source type. Không sao chép
raw prompt, toàn bộ transcript, raw OCR hoặc frame bytes vào
`users.travel_preferences`.

### Ma trận trạng thái nguồn

| Trạng thái | Hành vi |
| --- | --- |
| Được hỗ trợ và công khai | Chạy toàn bộ pipeline |
| YouTube long-form xác nhận không có caption | Trả `YOUTUBE_CAPTIONS_NOT_FOUND`; không tải media/STT |
| Caption provider long-form bị chặn/unavailable | Thử worker riêng, sau đó trả lỗi retryable |
| TikTok/Instagram/Facebook Reel hoặc URL `/shorts/` công khai | Chạy STT + frame vision/OCR rồi chuẩn hóa chung |
| Riêng tư hoặc cần đăng nhập | Không vượt quyền truy cập; báo unavailable |
| Không được hỗ trợ | Giữ URL và cho thêm place bằng flow chỉnh sửa plan |
| Provider timeout | Giữ kết quả từng phần và retry |
| Nội dung bị xóa | Giữ provenance tối thiểu theo chính sách, đánh dấu unavailable |

### Phạm vi connector của MVP

MVP hỗ trợ end-to-end ít nhất một nguồn video ngắn ưu tiên và URL trang công
khai thông thường. TikTok là use case sản phẩm ưu tiên, nhưng connector cụ thể
chỉ được công bố sau ADR xác nhận cách truy cập hợp lệ, độ ổn định và chi phí.
Không hứa “mọi URL Reel/TikTok/Facebook đều hoạt động”; UI phải công bố rõ nguồn
được hỗ trợ; người dùng vẫn có thể thêm place qua flow chỉnh sửa plan.

### Xung đột dữ liệu

- Caption/video là claim của nguồn, không phải dữ liệu vận hành hiện tại.
- Place provider quyết định danh tính/tọa độ; user quyết định candidate nào là
  địa điểm họ muốn.
- Giờ hoạt động, giá và route mới hơn được ưu tiên cho kiểm tra plan, nhưng claim
  gốc vẫn được giữ để giải thích khác biệt.
- Nhiều URL có thể củng cố một place; confidence tổng hợp không được xóa dấu vết
  từng nguồn.

## Độ mới dữ liệu

- Trạng thái hoạt động, giờ mở cửa, thời gian tuyến đường, tình trạng còn chỗ và
  giá phải có thời điểm lấy.
- Kiểm tra lại dữ liệu vận hành khi mở plan cũ và trước chuyến đi.
- Mẹo của creator có thể được giữ dưới dạng nội dung có version nhưng phải hiển
  thị ngày cập nhật plan.
- Nếu không thể làm mới dữ liệu, phải hiển thị trạng thái cũ thay vì che giấu.

## Tích hợp đặt dịch vụ

Bắt đầu bằng deep link hoặc một tích hợp đối tác. Tách nội dung lịch trình khỏi
xếp hạng thương mại, công khai nội dung tài trợ và đo tỷ lệ chuyển đổi từ lịch
trình
đến booking mà không âm thầm thay đổi tuyến đường của user.
