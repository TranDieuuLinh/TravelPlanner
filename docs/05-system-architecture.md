# Kiến trúc hệ thống

## Kiến trúc hiện tại

```text
Frontend Next.js
    |
    | HTTP /api
    v
Router FastAPI
    |
    +-- users: service -> SQLAlchemy repository -> PostgreSQL
    |
    +-- plans: service -> workflow -> domain service
    |                         |             |
    |                         |             +-- LLM gateway (Stub/Gemini)
    |                         |             +-- route gateway (Valhalla/OTP/fallback)
    |                         +-- PlanRepository trong bộ nhớ
    |
    +-- profiles/marketplace: endpoint placeholder
```

`docker-compose.yml` mặc định chạy backend và PostgreSQL. Profile `routing`
chạy thêm Valhalla và OpenTripPlanner sau khi dữ liệu OTP đã được build theo
`routing-data/README.md`. Frontend Next.js được chạy riêng trên host khi cần
phát triển hoặc kiểm thử giao diện.
PostgreSQL là database runtime duy nhất ở cả Docker và khi chạy backend trực
tiếp trên host. SQLite chỉ được tạo trong bộ nhớ bởi một số unit test cô lập,
không phải cấu hình ứng dụng. Container backend chạy Alembic trước khi khởi
động FastAPI; ứng dụng không dùng `create_all()` để âm thầm thay đổi schema.

`/api/plans/explore/full` và `/api/plans/explore/full/intake` chỉ hoạt động khi
Gemini được cấu hình và formatter được bật. Các luồng tạo Main/Backup Plan vẫn
có thể dùng `StubLLMClient` khi không có provider.

Finder dùng Valhalla tự vận hành qua interface route provider khi
`ROUTE_PROVIDER=valhalla`. Adapter lấy route pedestrian/auto, summary và
polyline6; lỗi theo từng leg fallback về ước tính địa lý. Khi trip có
`startDate`, adapter OpenTripPlanner GraphQL dùng OSM + GTFS/GTFS-RT để bổ sung
route theo lịch chạy và đưa vào lựa chọn chính hoặc
`transportLeg.alternatives` theo `preferredModes`/`avoidModes`.
Plan chưa có `startDate` dùng ngày hiện tại cùng giờ kết thúc item làm preview
lịch chạy; thứ tự itinerary vẫn được giữ nguyên.
Hai adapter tự host không dùng API key. Leaflet/OpenStreetMap vẫn là bản đồ nền.
Planner UI chỉ xin Geolocation khi user bấm “Vị trí của tôi”; thao tác này chỉ
định vị, xoay marker theo heading khi thiết bị cung cấp và đưa camera về user.
Khi một ngày cụ thể được chọn, `/api/plans/day-directions` nhận tọa độ tạm thời,
danh sách stop có tọa độ của ngày theo đúng thứ tự itinerary đã lưu. Backend
không gọi travel-time matrix và không giải shortest path cho thao tác chỉ đường;
nó chỉ lấy geometry/duration chi tiết từ vị trí hiện tại tới stop đầu tiên rồi
giữa các stop kế tiếp theo thứ tự cố định. Chặng đầu dùng thời điểm hiện tại;
các chặng itinerary tiếp theo dùng giờ kết thúc `timeWindow` của stop đầu chặng
để saved view và live-directions query cùng service period. Mọi timestamp được
chuẩn hóa về `Asia/Ho_Chi_Minh` trước khi lấy ngày/giờ gửi OTP; ISO UTC từ
browser không được dùng trực tiếp làm service time. Endpoint chỉ được gọi khi
user bấm “Chỉ đường” hoặc chủ động bấm “Tính lại”. Nút vị trí dùng một lần đọc
`getCurrentPosition`, chỉ đưa camera về user một lần và không dùng GPS watch;
đổi mode cũng không gọi route lại. Mỗi chặng trả tuyến đề xuất cùng các lựa chọn
đi bộ và ô tô; xe buýt chỉ được thêm khi OTP trả itinerary transit có geometry thật.
Mỗi itinerary transit giữ nguyên danh sách leg của OTP để UI trình bày rõ chặng
đi bộ tới trạm, chặng xe buýt giữa các trạm và chặng đi bộ tới điểm đến;
trên bản đồ, WALK được vẽ bằng nét chấm, BUS bằng nét liền và điểm lên/xuống xe
được đánh dấu riêng;
đổi lựa chọn chỉ thay geometry đã trả về ở client. Các lựa chọn đang chọn được
ghép trên cùng bản đồ. Backend không lưu tọa độ, lựa
chọn hoặc chặng điều hướng vào plan, database hay timing log.

### Pipeline Explorer intake hiện tại

Raw prompt luôn là ngữ cảnh gốc của request. `PlanService` điều phối các nhánh
làm giàu dữ liệu trước khi gọi formatter:

```text
Planner UI
    |
    | raw prompt + URL tìm thấy + ảnh đính kèm
    v
FastAPI intake router
    |
    v
PlanService
    |
    +-- có ảnh? --> ImageOcrService --------+
    |                                       |
    +-- có URL? --> UrlReelExtractionService+--> ExploreResponseFormatter
    |                                       |             |
    +-- raw prompt -------------------------+             v
    |                                            ExploreBundleDraft
    |                                              /           \
    |                                             v             v
    |                                  ExplorerContext    PlaceCandidates
    |                                                           |
    |                                                           v
    |                                              PlaceCandidateAggregator
    |                                                           |
    |                                                           v
    |                                                PlaceResolver interface
    |                                                           |
    |                                                           v
    +----------------------------------------------> PostgreSQL persistence
                                                        | user_must_place
                                                        v
                                                  ExplorerIntakeResponse
                                        (intakeId + userId + explorer + timing)
```

`ExploreResponseFormatter` chỉ tổng hợp raw prompt và context đã được các
extractor tạo ra; formatter không tự điều phối download URL hoặc OCR. Với URL,
Extractor là nguồn duy nhất tạo candidate; Formatter chỉ tạo intent/trip spec/
preference và chạy song song với Resolver. Aggregator gộp trùng nhưng giữ
provenance. Resolver chạy tự động, không dừng luồng để hỏi user. Chỉ kết quả
resolved có tọa độ hợp lệ được lưu vào `user_must_place`; Explorer intake không
ghi vào `places` và không lưu raw transcript/OCR.

`UrlReelExtractionService` định tuyến theo loại nguồn trước khi chuẩn hóa chung:

- YouTube long-form (`watch`, `youtu.be`, `live`, `embed`) chỉ dùng caption công
  khai/cache/worker; không tải media và không fallback STT/OCR.
- YouTube Shorts có path `/shorts/{videoId}`, TikTok video, Instagram Reels và
  Facebook Reels dùng media tạm thời để chạy Gemini Audio STT song song với
  frame vision/OCR. Facebook được nhận diện explicit nhưng khả năng tải vẫn phụ
  thuộc URL công khai và connector `yt-dlp`.

Hai nhánh đều trả cùng `ExtractedContext`, candidate, provenance và đi qua cùng
Aggregator -> Resolver -> Planner/Finder. URL rút gọn `youtu.be/{videoId}` không
chứa tín hiệu Shorts nên giữ nhánh YouTube caption-only an toàn.

Response trả `intakeId`, `userId`, Explorer context và `timingReport`.
`timingReport` dùng cho debug latency trên UI và được append dạng JSONL vào
`backend/var/explorer-timings.jsonl`. Log chỉ giữ duration/status/count, không
giữ prompt, URL đầy đủ, transcript, OCR text hoặc credential. Explorer không tự
gọi Planner/Finder. Planner downstream đọc context và chuyển tiếp hai khóa;
Finder downstream đọc `user_must_place` bằng `intakeId + userId`.
Timing của mỗi URL phân biệt số địa điểm thô do OCR/STT trích xuất, số candidate
sau dedupe, số resolve thành công, số candidate từng provider đã xử lý và số
resolve thành công theo provider. Candidate có provenance từ nhiều URL được tính
cho từng URL liên quan nên tổng theo URL có thể lớn hơn tổng candidate toàn
intake. Timing source còn trả số STT chunk, duration audio, duration từng chunk
và retry count. `cacheStatus` cùng `cacheLookupSeconds` phân biệt cache hit,
cache miss và lần chủ động bypass cache mà không ghi URL vào timing log; đây là
status/count/duration an toàn, không chứa transcript hoặc audio.
`providerAttempts` ghi từng lần resolve bằng tên candidate đã chuẩn hóa,
provider, số alias query, thời gian chờ queue, thời gian thực thi, outcome và lý
do từ chối/timeout. `providerCounts` vì vậy đếm provider thực sự được gọi thay
vì chỉ provider cuối cùng. Timing không ghi query đầy đủ hoặc provider payload.

URL gửi từ trip chat đã đăng nhập không còn giữ HTTP request mở. Router tách mỗi
URL thành một `UrlImportJob` bền vững và trả `202 Accepted`; worker trong cùng
deployment lấy FIFO đúng một job tại một thời điểm rồi chạy Explorer, resolve,
Planner/Finder và lưu revision mới của chat. Job đang `running` được đưa lại về
`queued` khi worker khởi động lại. Mỗi job có deadline cấu hình; job vượt
deadline chuyển sang `failed` để không khóa FIFO và có thể được user retry
riêng. User có thể dừng và xóa job `running`; worker hủy task đang xử lý, giải
phóng slot FIFO rồi claim job `queued` kế tiếp ngay. Prompt chat không có URL
vẫn đi theo request đồng bộ hiện tại. UI poll tài nguyên job ở AppShell nên
trạng thái tiếp tục hiện khi user chuyển từ Planner sang Khám phá hoặc route
khác. Tiến độ không được chèn vào transcript Planner; trạng thái gọn nằm trong
header và mặc định không che nội dung. User có thể mở dropdown để xem timer,
timing Explorer/Planner chi tiết hoặc xóa các job đã kết thúc.
Composer không bị khóa bởi URL job nên user vẫn gửi prompt chat bình thường.

Guest dùng hàng chờ FIFO trong memory của AppShell và gọi cùng endpoint Explorer
-> Planner/Finder mà không tạo trip chat hay `url_import_jobs`. Vì queue nằm ở
client, nó tiếp tục chạy khi điều hướng trong SPA nhưng biến mất khi reload,
đóng tab hoặc runtime trình duyệt bị dừng. Đây là hành vi có chủ đích: guest
không có owner để lưu job riêng tư bền vững trong PostgreSQL. User đăng nhập vẫn
dùng worker/database ở trên để phục hồi job sau reload hoặc backend restart.

```text
Trip chat URL message -> url_import_jobs (queued) -> single worker
                              |                         |
                              v                         v
                    global collapsible UI      Explorer -> Planner
                                                        |
                                                        v
                                               TripChat revision
```

## Ranh giới backend

- `app/main.py`: khởi tạo ứng dụng, middleware và health endpoint.
- `app/api_router.py`: kết hợp các router cấp cao dưới `/api`.
- `app/modules/<module>/router.py`: chỉ chuyển đổi HTTP.
- `service.py` và `workflows/`: use case và điều phối nghiệp vụ.
- `domain/`: entity, enum và validation độc lập với provider.
- `repository.py`: ranh giới lưu trữ.
- `app/integrations/`: provider bên ngoài được đặt sau interface của ứng dụng.
- `app/db/` và `migrations/`: cấu hình database và thay đổi schema.

## Ranh giới frontend

- `src/app/`: route, layout và kết hợp page.
- `src/modules/<feature>/`: component, API client, schema và type do từng tính
  năng sở hữu.
- `src/lib/`: hạ tầng dùng chung như HTTP transport.
- `src/config/`: cấu hình môi trường đã được kiểm tra.

Server state phải nằm trong API/query boundary của feature; trạng thái tạm thời
của trình chỉnh sửa nằm trong editor feature. Không được sao chép validation của
backend thành logic UI không có type; khi API lớn hơn nên dùng contract chung
hoặc client được sinh tự động.

## Thành phần mục tiêu của MVP

- Authentication và authorization.
- Repository lưu bền vững cho import/source/place/plan/listing/order.
- Background job runner cho nhập URL, trích xuất nội dung, tạo plan AI, bổ sung
  route, xử lý media và notification.
- Object storage cho media của creator.
- Media `UserPost` đi qua `PostMediaStorage`; adapter MVP lưu file tên ngẫu nhiên
  trong `backend/var/user-post-media` (volume `/app/var` khi chạy Docker) và phục
  vụ ở `/media/posts`. Khi deploy nhiều instance phải thay adapter này bằng object
  storage dùng chung, không để module Hồ sơ tự phụ thuộc filesystem.
- Kho cache/rate limit khi mức dùng provider yêu cầu.
- LLM gateway có structured output, retry, telemetry và chuyển đổi provider.
- Gateway cho source connector, speech/vision extraction, place/map và payment.
- Chiến lược cache offline và đồng bộ trong web client.

Bắt đầu bằng modular monolith. Chỉ tách service khi có bằng chứng rõ ràng về nhu
cầu scale, ownership hoặc reliability.

## Pipeline từ URL đến Planner

```text
Web client
   |
   | POST /imports
   v
Import API -> Import Job -> Source Connector
                           |
                           v
                  Content Extraction
             caption / transcript / frames
                           |
                           v
                 Claim + PlaceCandidate
                           |
                           v
                    Place Resolver
                           |
                           v
                User Confirmation UI
                           |
                           v
                    SelectedPlaces
                           |
                           v
Explorer -> Planner -> Finder -> Check -> Main/Backup Plan
```

Ranh giới trách nhiệm:

- `imports`: vòng đời URL, connector, nội dung được phép lưu, trạng thái job và
  provenance.
- `extraction`: chuyển nội dung nguồn không đáng tin thành claim/place candidate
  có schema; không gọi trực tiếp domain Planner.
- `places`: chuẩn hóa danh tính, gộp trùng và lưu ánh xạ provider.
- `planning`: chỉ nhận source/claim/place đã chuẩn hóa cùng ràng buộc của trip.
- `checks`: kết hợp rule engine với dữ liệu place/route/weather có thời điểm lấy.
- `marketplace`: chỉ publish version đã kiểm tra; buyer clone version vào trip
  riêng trước khi chỉnh sửa.

Connector của từng nền tảng phải nằm sau interface và trả về mô hình nội bộ.
Không để payload riêng của TikTok, YouTube hoặc provider khác lan vào domain.

## Quy tắc dữ liệu và request

- Idempotency key do client tạo bảo vệ thao tác retry khi tạo plan và checkout.
- Tác vụ nhập/generate kéo dài phải trở thành job với trạng thái rõ ràng:
  `queued`, `running`, `succeeded`, `failed`, `cancelled`.
- Import phải lưu kết quả từng bước để retry extraction hoặc resolution mà không
  fetch lại nguồn khi không cần thiết.
- Dữ liệu thực tế từ bên ngoài phải có nguồn, thời điểm lấy và độ tin cậy.
- Nội dung đã publish và đã mua phải có version.
- Giá tiền dùng số nguyên theo đơn vị nhỏ nhất và mã tiền ISO; không dùng số thực
  dấu phẩy động.
- Ngày giờ phải giữ timezone và ý nghĩa ngày tại địa phương.

## Khả năng quan sát

Sử dụng structured log có request/job ID, độ trễ provider, số token/chi phí và mã
kết quả. Không ghi access token, thông tin thanh toán, toàn bộ prompt, URL riêng
tư hoặc dữ liệu cá nhân không cần thiết.

### Planning Control đã triển khai

`admin-frontend/` là ứng dụng Next.js độc lập chạy mặc định tại cổng `3001`.
Ứng dụng dùng cùng JWT cookie của backend nhưng mọi API quan sát đều kiểm tra
role `admin` ở server.

Backend lưu `PlanningRun` và các `PlanningRunStage` theo chuỗi
Explorer–Planner–Finder–Checker. Snapshot được tạo ở ranh giới workflow, không
thay đổi business rule của từng module. Trước khi ghi JSON, backend loại secret,
media bytes, query string URL, payload thô và thay `rawRequest` bằng metadata độ
dài. Golden dataset được đọc ở chế độ chỉ đọc và mỗi case được kiểm tra độ phù
hợp với contract hiện tại trước khi hiển thị.
