# Nguồn dữ liệu và tích hợp

## Nguyên tắc

- Category/tag vận hành của một địa điểm đã resolve lấy từ Places database hoặc
  Google Maps Playwright, không lấy từ phân loại của AI. Giữ raw provider type
  trong `place_type`, chuẩn hóa category riêng cho tìm kiếm/Planner; thiếu dữ
  liệu provider thì dùng `other` thay vì đoán từ nội dung nguồn.

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

Valhalla tự vận hành được chọn cho route từng leg của Finder. Finder gọi cả
`pedestrian` và `auto` cho mỗi mode không bị user loại trừ. Ngưỡng đi bộ 1.500 m
quyết định mode road được đề xuất ở backend, còn route road kia vẫn nằm trong
`PlanTransportLeg.alternatives`. UI Planner luôn giữ ô tô trong các route road
khả thi; đi bộ chỉ được thêm khi leg dưới 3.000 m. Tuyến public transit đã được
OpenTripPlanner xác minh được hiển thị thêm để người dùng chọn; lựa chọn
`mixed`/`unknown` không được đưa lên UI hoặc gắn nhãn trên bản đồ.
Summary distance/duration cùng polyline6 được chuẩn hóa vào
`PlanTransportLeg`; lỗi provider fallback theo từng leg. Kết quả không được mô
tả là traffic live nếu deployment chưa nạp dữ liệu traffic.

OpenTripPlanner dùng GTFS GraphQL API tại `/otp/gtfs/v1`, gửi ngày/giờ khởi
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
cảnh báo lịch cũ đã dịch ngày, nhưng vẫn giữ `verified=false`.

UI Planner dùng MapLibre GL JS với vector style dựa trên dữ liệu OpenStreetMap;
style URL được cấu hình bằng `NEXT_PUBLIC_PLANNER_MAP_STYLE_URL` và mặc định dùng
OpenFreeMap Bright cho môi trường prototype. UI ẩn các lớp POI không phục vụ
lịch trình, dùng bảng màu tương phản cao để phân biệt rõ đất, nước, công viên,
công trình, đường và nhãn, đồng thời giữ attribution OpenStreetMap luôn hiển
thị. Bản đồ dấu chân quốc gia trong Profile vẫn dùng Leaflet vì render GeoJSON
tĩnh và không cần vector basemap. Chỉ đường tạm thời từ vị trí
hiện tại giữ nguyên thứ tự stop của itinerary đã lưu, không gọi
`sources_to_targets` và không giải open path. Valhalla Routing và
OpenTripPlanner vẫn được gọi cho từng leg cố định để trả geometry, thời lượng và
chuyên chở bằng các mode khả thi, đồng thời trả chuỗi segment đa phương thức.
UI xem toàn tuyến ngày thêm điểm xuất phát trước chuỗi stop này. Chế độ tìm
đường nhanh là truy vấn point-to-point riêng: điểm đi có thể là vị trí thiết bị
hoặc place đã tìm, còn điểm đến có thể là stop trong plan, place đã tìm hoặc tọa
độ chọn trực tiếp trên bản đồ; kết quả không mutate itinerary.
Các ô tìm địa điểm của Planner dùng chung autocomplete Knowledge Graph và nhận
tối đa `topK` kết quả đã xếp hạng để người dùng chọn, mặc định `K=5` và API chỉ
chấp nhận từ 1 đến 10. Search chỉ trả canonical venue entity có tọa độ, thuộc
destination qua `LOCATED_IN`; không trả Area, Activity hoặc item. Khi graph
không đủ `topK`, Google Maps Playwright được gọi để bổ sung kết quả provisional.
Search không tự promote snapshot Google vào graph canonical. Chọn một option giữ
entity/provider place ID cùng tọa độ; nhập văn bản tự do không được coi là đã
xác nhận đúng place identity.
Segment được giữ theo đúng thứ tự OTP trả về
(`WALK` tới trạm, `BUS` giữa các trạm, rồi `WALK` tới điểm đến), kèm tên điểm
đầu/cuối, thời gian, khoảng cách, tuyến và hướng xe khi nguồn có dữ liệu.
Luồng Planner/Finder tạo plan ban đầu tiếp tục giữ policy thứ
tự riêng. Xem ADR-002.

Explorer tạo tối đa hai alias lookup có cấu trúc trước khi resolve: tên chính
thức tiếng Việt và tên canonical tiếng Anh/tên gốc. Các field
`alternateNames` và alias catalog cũ vẫn được đọc để tương thích nhưng không
tạo thêm lookup provider. Input có thể ở bất kỳ ngôn ngữ nào; tên nguồn và
provenance luôn được giữ nguyên. LLM không được sinh tọa độ hoặc tự quyết định
place identity. Resolver lấy tối đa `top K` record `active` có tọa độ trong bảng
`places`, gồm metadata alias và tên có hậu tố chi nhánh, rồi xếp hạng theo độ
giống tên, `region_key`, evidence địa chỉ/landmark, category tương thích và
`data_confidence`. Top-1 chỉ được nhận khi đạt điểm tối thiểu và cách top-2 đủ
xa; mặc định `K=5`, điểm phải **lớn hơn** `0.82` và margin `0.08`. Điểm bằng
`0.82` vẫn bị loại. Route context chỉ phân xử giữa các match đã vượt ngưỡng;
không được nâng một match yếu thành `resolved`. Candidate tên món/venue chung
phải có địa chỉ nguồn khớp record mới được resolve tự động. Đây là score nội bộ
có thể hiệu chỉnh, không phải confidence do Google hay source cung cấp. Nhờ vậy
source tiếng Việt vẫn match được record DB chỉ có tên tiếng Anh và ngược lại,
đồng thời không đoán giữa các thương hiệu/địa điểm trùng tên. Catalog miss, toàn
bộ điểm thấp hoặc top-1/top-2 quá sát nhau đều fallback sang Playwright worker
của Google Maps.
Scraper nhận tên gốc và alias có cấu trúc qua file input tạm. Kết quả Google
được xếp hạng theo top-K score tổng hợp từ độ giống tên, vùng, category và tọa
độ; top-1 chỉ được nhận khi điểm **lớn hơn** `0.82`, không bị loại riêng chỉ vì
tên provider có thêm prefix mô tả như `Di tích`. Vùng/category mâu thuẫn rõ
hoặc tọa độ không hợp lệ vẫn là hard rejection; provider lỗi hoặc timeout không
làm hỏng intake. Alias catalog được lưu trong
`places.metadata.aliases`, hoặc tách theo `englishNames`, `vietnameseNames`,
`alternateNames`; `searchNames` tiếp tục được đọc để tương thích dữ liệu cũ.
Mỗi candidate chỉ giữ tối đa hai tên tra cứu: tên chính thức tiếng Việt và tên
canonical tiếng Anh, hoặc tên gốc từ source khi không có tên tiếng Anh chắc
chắn. Resolver dùng cùng hai tên này để tra `places` trước. Chỉ khi catalog
không resolve được, scraper tra tên tiếng Việt rồi fallback sang tên
Anh/tên gốc nếu kết quả đầu không đạt rule xác minh. Mặc định và giới hạn cứng
là hai query (`GOOGLE_MAPS_SCRAPER_MAX_ALIAS_QUERIES=2`); alias phụ không tạo
thêm request Playwright nhưng vẫn có thể tồn tại trong metadata catalog cũ để
kiểm tra tương thích.

`searchRegion` được chuẩn hóa về `region_key` canonical trước khi tra catalog.
Tên thành phố/tỉnh có biến thể dấu, khoảng trắng hoặc tên quen dùng map về cùng
root; khu vực con như `Tây Hồ` được scope dưới destination thành
`vn,ha-noi,tay-ho`, trong khi stop thuộc root đã biết như `Ninh Bình` vẫn là
`vn,ninh-binh` để không phá day trip.
Khi catalog có nhiều chi nhánh cùng tên, resolver ưu tiên địa chỉ hoặc landmark
có evidence từ source. Nếu source không nêu rõ chi nhánh, resolver dùng stop đã
resolve ngay trước/sau trong cùng ngày và cùng URL để tính quãng đường vòng địa
lý. Chỉ tự chọn khi kết quả tốt nhất cách biệt đủ rõ (tối thiểu 0,75 km và 30%
so với kết quả thứ hai, đồng thời không lệch anchor quá 15 km); nếu không,
candidate tiếp tục unresolved trong bước DB và được chuyển sang provider sau.
Provider sau vẫn phải xác minh tên/vùng/category/toạ độ, không được chọn đại kết
quả đầu tiên; nếu provider cũng không xác minh được thì UI phải yêu cầu user
chọn. Candidate có địa chỉ/landmark từ source vẫn có thể đi qua provider sau để
xác minh evidence đó. Đây là heuristic chọn identity,
không phải route provider hay tối ưu lại thứ tự itinerary.
Valhalla và OpenTripPlanner không phải geocoder/POI search nên không thay vai
trò này. Candidate chỉ được nhận khi khớp tên/vùng, loại provider không mâu
thuẫn rõ và có tọa độ. Candidate không khớp catalog và không được Google Maps
Playwright xác minh sẽ giữ trạng thái unresolved để người dùng xử lý tiếp.

Google Maps scraper không cần API key. Trong Docker Compose, scraper chạy ở
sidecar `gosom/google-maps-scraper:v1.12.1` với Chromium/Playwright đóng gói
sẵn. Backend và sidecar trao đổi input/output JSON qua
`GOOGLE_MAPS_SCRAPER_WORK_DIR`; input được publish bằng atomic rename và mỗi
sidecar giữ một Chromium browser với hai page slot. Hai candidate có thể
resolve đồng thời mà không khởi động lại browser cho từng job. Job JSON mang
`createdAtMs` và `deadlineAtMs`; worker ghi status lúc claim để tách queue wait
khỏi execution time, kiểm tra cancellation/deadline khi chạy, đóng page của slot
khi bị hủy và dọn response/error/status/cancellation mồ côi theo TTL. Cách này cô lập image AMD64 của
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

## Nhập dữ liệu từ URL

Xem nội dung được nhập là dữ liệu không đáng tin cậy, không bao giờ là system
instruction.

### Pipeline

1. Chuẩn hóa URL, kiểm tra scheme và chặn địa chỉ mạng private/internal.
2. Nhận diện nguồn và chọn connector theo allowlist.
3. Fetch qua service được kiểm soát với giới hạn redirect, kích thước và timeout.
4. Lưu metadata cùng quyền truy cập, connector version và `fetchedAt`.
5. Với URL website công khai không thuộc platform video đã nhận diện, fetch trực
   tiếp bằng `httpx` sau khi kiểm tra DNS của host và từng redirect. Chỉ nhận
   HTML/XHTML/plain text, mặc định tối đa 5 MB, 5 redirect và 15 giây. Trafilatura
   loại navigation/footer và trả Markdown chính; text bị giới hạn 60.000 ký tự
   trước khi đi qua structured text extractor dùng chung. Trang cần JavaScript,
   đăng nhập, paywall hoặc CAPTCHA trả lỗi rõ ràng; MVP chưa tự bật browser để
   vượt giới hạn truy cập.
6. Với URL YouTube long-form, kiểm tra cache PostgreSQL theo
   `videoId + language`, rồi thử caption công khai bằng
   `youtube-transcript-api`. Request đồng thời cho cùng
   video được dedupe trong process và các fetch mới bị giới hạn nhịp. Caption
   thành công được cache dài hạn và dùng làm transcript mà không tải video. Nếu
   IP backend bị chặn, runtime có thể gọi worker do operator tự vận hành trên
   kết nối dân dụng; chỉ video ID và language list được gửi, không gửi cookie
   người dùng. `no_captions` trả lỗi `YOUTUBE_CAPTIONS_NOT_FOUND`;
   `blocked`/`unavailable` trả lỗi retryable sau khi worker thất bại. YouTube
   long-form không tải video, không tách audio, không gọi audio STT/OCR và không
   gọi `yt-dlp` để lấy metadata. Title, description, chapter, thumbnail và
   uploader không nằm trong critical path của YouTube long-form; pipeline dùng
   URL chuẩn hóa cùng caption để tránh metadata làm tác vụ bị treo. Caption được
   cấu trúc đa ngôn ngữ bằng model text hiện có, giữ nguyên proper name và phân
   loại venue/sub-place/address/city/person/activity/food. Caption text
   dùng `GEMINI_CAPTION_API_KEYS` khi được cấu hình; nếu không, nó mượn toàn bộ
   key trong pool STT + OCR vì YouTube long-form không chạy hai workload media
   đó. Key được chọn round-robin, mỗi call chỉ failover tối đa hai key cho lỗi
   credential/quota và chịu một deadline tổng mặc định 60 giây; timeout mạng
   không được nhân lên qua toàn bộ pool. YouTube
   Shorts có path `/shorts/{videoId}`, TikTok video, Instagram Reels và Facebook
   Reels tải media công khai tạm thời rồi
   Gemini Audio trả `transcript` cùng structured STT observations bằng
   `responseJsonSchema`; frame vision trả structured OCR observations trên frame
   lấy mẫu. STT và frame vision chạy song song. OCR cũng chạy trên
   ảnh/screenshot do người dùng upload.
   Nếu metadata công khai của URL có `place`, `venue` hoặc `location`, giá trị
   này được tạo thành candidate ưu tiên trước caption/STT/OCR và giữ evidence
   `metadata`; địa chỉ/city trong metadata được dùng làm hint cho resolver.
   Chuỗi resolver cache dùng chung -> catalog nội bộ -> Google Maps Playwright
   vẫn phải xác minh danh tính và tọa độ trước khi lưu.
   STT cũng giữ món/hoạt động địa phương cụ thể được nói rõ nhưng không kèm
   venue (ví dụ “cà phê trứng”) dưới dạng activity-only candidate. Candidate
   này phải đi qua resolver như bình thường và thường giữ trạng thái unresolved
   để bước gợi ý gần route xử lý; các động từ mơ hồ như “ăn”, “uống”, “đi chơi”
   không được tạo candidate.
   Danh sách địa điểm có pin trong caption là blueprint canonical tiếp theo:
   giữ tên và thứ tự caption, tách các street được nêu chung, rồi chỉ dùng
   STT/OCR để bổ sung evidence, activity và address. Tên thành phố trùng
   destination (kể cả alias như `Hanoi` so với `Hanoi, Vietnam`) không được
   resolve hoặc lưu như một stop.
   Heading thành phố có duration như `Hanoi - 2 days` được chuẩn hóa thành
   `destinationStay` phủ hai ngày và bị loại khỏi danh sách stop; duration không
   được hiểu thành một phần tên địa điểm.
7. Metadata và nhánh media chạy song song; khi trip chưa có destination, nhánh
   media chỉ chờ metadata đủ để tạo location hint rồi mới gọi STT/Vision. Validate
   JSON, gộp/dedupe metadata + STT + OCR + caption, giữ evidence theo từng nguồn
   rồi chuyển thành place candidate. Metadata location cụ thể làm anchor; tên
   STT/OCR khác spelling được giữ trong `observedAliases`. Nếu tên candidate dính thêm câu review,
   bước gộp chỉ phục hồi nhãn ngắn hơn khi nhãn đó xuất hiện nguyên vẹn trong
   evidence STT/OCR và tự vượt qua policy chống caption rác. Khi structured STT đã có, Python không
   suy diễn place/day/activity từ transcript tự do.
   Address/person/city không được chuyển thành stop. Address được gắn vào venue;
   sub-place có parent rõ ràng được gộp về venue cha. Parser fallback nhận marker
   `number/no.` và `số/thứ` bằng chữ hoặc số.
8. Canonicalization tạo alias Anh–Việt có cấu trúc ngay trong candidate fusion,
   lưu riêng trong `generatedLookupAliases`, sau đó chuẩn hóa địa điểm theo chuỗi
   shared cache -> `places` catalog -> Google Maps Playwright
   và gộp trùng.
   Places DB và external provider giữ tối đa năm match option kèm score component;
   top-1 chỉ được nhận khi đủ score/margin. Stable identity đã xác minh mới cho
   phép học `verifiedAliases`; alias Việt được trả riêng cho frontend.
   Query dùng `searchRegion` của stop thay vì luôn nối trip base. Khi candidate
   có `addressHint`, Google fallback thử thêm một query chỉ gồm địa chỉ và vùng
   sau các query tên + địa chỉ. Kết quả có tổng score không vượt ngưỡng vẫn giữ
   trạng thái unresolved;
   tọa độ đại diện chỉ được dùng làm anchor cho gợi ý gần route, không được lưu
   như provider-verified source place. Kết quả chỉ
   được resolve khi top-1 vượt ngưỡng score, vùng địa lý phù hợp và loại provider
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
   Placeholder `unspecified`/`unknown` được coi như thiếu region và không được
   gửi tới provider. Background URL job bảo toàn destination của chat hoặc suy
   luận bảo thủ từ query URL, title/caption và vùng chiếm ưu thế trong candidate.
   Candidate OCR-only bị loại khi evidence không chứa chính tên logo. Heading
   itinerary tổng quát như `FULL DAY ITINERARY IN ...` bị loại trước resolver.
   Nhiều candidate khác tên nhưng trùng Google identity/tọa độ chỉ được gộp
   thành alias khi canonical provider name cũng giống nhau; nếu provider name
   khác nhau, cả nhóm bị trả về `duplicate_provider_identity` thay vì persist.
   Sau catalog miss, Google result `resolved` chỉ được học vào catalog khi có
   stable `externalId` cùng latitude/longitude hợp lệ. Nếu `places.id` đã tồn
   tại, resolver thêm source spelling vào `metadata.aliases` và provenance ngắn
   vào `metadata.verifiedAliases`; nếu chưa tồn tại, repository tạo record
   `Place` tối thiểu với `source_platform=google_maps_scraper` và confidence
   `medium`. Không học từ coordinate-only identity, mismatch, provisional hoặc
   unresolved result. Alias update idempotent và tăng `revision` đúng một lần
   khi metadata thực sự thay đổi.
9. Tự động upsert snapshot dùng chung vào `user_must_place` và tạo junction
   `user_must_place_users` chỉ khi provider trả kết quả `resolved` cho địa điểm
   cụ thể có đủ latitude/longitude; không chặn để hỏi user. Match rộng
   tới thành phố/quốc gia, caption bị hiểu nhầm thành tên, candidate
   provisional/unresolved hoặc thiếu tọa độ không được lưu; Finder có thể bù
   phần còn thiếu. Các biến thể chính tả cùng resolve về một identity được
   canonical-dedupe trước persistence; `candidateCount`, `resolvedCount` và
   `persistedCount` của Explorer phản ánh tập sau dedupe, còn danh sách attempt
   vẫn giữ toàn bộ lượt provider để debug.
10. Cache `ExtractedContext` theo canonical URL và extraction schema version;
   cache version cũ được tính lại thay vì trả kết quả parser lỗi thời. Lần dùng
   sau bỏ qua media, STT/OCR; snapshot hit cũng bỏ qua provider lookup. Bàn giao
   `intakeId + userId + explorer` cho Planner downstream; Finder đọc snapshot
   qua junction theo `intakeId + userId`. Job có `forceRefresh=true` bỏ qua cache
   để chạy lại toàn bộ extraction; cache cũ chỉ được ghi đè sau khi intake mới
   thành công, không bị xóa ngay khi enqueue.
   Schema cache version 5 loại snapshot trước web-page connector, entity
   authority và extraction coverage. Snapshot resolved cũ không thay thế
   extraction cache vì thiếu contract mới.
11. Giữ attribution và chỉ lưu nội dung được license/chính sách cho phép.

Với URL, Extractor là nguồn duy nhất tạo `UnifiedPlaceCandidate`. Formatter nhận
summary gọn của extraction để tạo TripIntent canonical và
không sinh lại candidate. Resolver có thể chạy song song với Formatter ngay sau
khi candidate được chuẩn hóa và gộp trùng.

TikTok video thử `yt-dlp` chuẩn trước, sau đó retry bằng desktop Chrome và
Android Chrome impersonation qua dependency `curl_cffi` nếu challenge/TLS
fingerprint làm request trước thất bại. Hệ thống không gọi TikWM. Photo carousel chưa có provider được duyệt nên
trả trạng thái cần upload screenshot. Media video thành công vẫn chỉ được xử lý
trong thư mục tạm và xoá sau request. Video OCR dùng
`gemini-3.5-flash-lite`, mặc định không quá một frame mỗi giây, tối đa 72 frame
rộng 960 px theo batch tối đa 10 ảnh ở media resolution medium. Gemini Audio
trả transcript cùng observation gồm order/place/evidence/day/time/activity/
duration/confidence và search region explicit. Candidate từ STT và frame vision
được gộp; một nguồn không loại bỏ candidate chỉ xuất hiện ở nguồn còn lại. OCR
ưu tiên tên hiển thị và thứ tự frame; STT ưu tiên day/time/activity/duration/
search region; evidence ngắn của hai nguồn được giữ tách biệt. Mỗi stop giữ
extraction confidence riêng theo evidence; place resolution tạo resolution
confidence riêng theo provider và chất lượng match, không sao chép một
confidence chung của cả video cho mọi stop. Không
giới hạn số place candidate có evidence được giữ sau bước
gộp; giới hạn 72 chỉ là số frame video lấy mẫu. Frame được chia đều giữa các
batch để giảm latency của batch lớn nhất; tối đa năm batch
chạy song song bằng các API key khác nhau trong `GEMINI_OCR_API_KEYS`. STT dùng
pool riêng `GEMINI_STT_API_KEYS` và chuyển sang key kế tiếp khi key hiện tại trả
`401`, `403` hoặc `429`; hai pool riêng không được chứa key trùng nhau và chuỗi
nhiều key không được gửi nguyên dạng như một credential. Khi chỉ có
`GEMINI_API_KEY`, runtime chia đôi pool cho STT/OCR nếu có ít nhất hai key.
Caption text có thể mượn hợp của hai pool nhưng vẫn chỉ gửi một key cho mỗi
request và giới hạn số failover; không fan-out cùng nội dung qua mọi key.
Audio fallback dài hơn ngưỡng 60 giây có thể được chia cân bằng thành tối đa
ba chunk có overlap hai giây; audio ngắn vẫn dùng một call. Mặc định STT chạy
tối đa ba request đồng thời và bắt đầu các Gemini call cách nhau ít nhất hai giây
trong mỗi tiến trình. Cấu hình cần được theo dõi theo quota project; xoay nhiều
key không đảm bảo thêm quota vì Gemini giới hạn theo project. Khi gặp `429`, STT
tôn trọng `Retry-After` tối đa 60 giây. Kết quả được
ghép theo chunk order và dedupe observation tại vùng overlap. Mức song song tự
giảm khi thiếu key hoặc batch. Kết quả vẫn được hợp nhất theo
thứ tự frame gốc. Nếu một batch lỗi nhưng batch khác thành công, evidence thành
công vẫn được giữ. Nếu URL không tạo được địa điểm có evidence, API trả lỗi có
hướng dẫn retry hoặc upload screenshot thay vì trả itinerary `Ready` với
0 địa điểm.

Preference learning chỉ lưu tín hiệu chuẩn hóa và source type. Không sao chép
raw prompt, toàn bộ transcript, raw OCR hoặc frame bytes vào
Traveler Profile. Dữ liệu dài hạn nằm trong các bảng quan hệ
`traveler_profiles`, `traveler_preference_signals` và
`traveler_preference_signal_sources`; intake ID gần nhất được giữ làm
provenance mà không lưu lại nội dung chat thô trong signal.

### Ma trận trạng thái nguồn

| Trạng thái | Hành vi |
| --- | --- |
| Được hỗ trợ và công khai | Chạy toàn bộ pipeline |
| YouTube long-form xác nhận không có caption | Trả `YOUTUBE_CAPTIONS_NOT_FOUND`; không tải media/STT |
| Caption provider long-form bị chặn/unavailable | Thử worker riêng, sau đó trả lỗi retryable |
| TikTok/Instagram/Facebook Reel hoặc URL `/shorts/` công khai | Chạy STT + frame vision/OCR rồi chuẩn hóa chung |
| Website HTML/XHTML/plain text công khai | Fetch có giới hạn, Trafilatura lấy nội dung chính, structured text extraction rồi chuẩn hóa chung |
| Website cần JavaScript/đăng nhập/paywall/CAPTCHA | Không vượt quyền truy cập; báo unavailable hoặc cho thêm place thủ công |
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
