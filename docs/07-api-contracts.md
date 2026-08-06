# Giao ước API

Base URL: `/api`. Các field trong JSON response sử dụng camelCase.

## Điểm cuối hiện tại

### Nhóm du lịch

- `GET /api/travel-groups?query=`: danh sách nhóm quốc gia công khai; có thể xem
  khi chưa đăng nhập. Khi có session, mỗi item trả thêm `isMember` đúng với user.
- `PUT /api/travel-groups/{groupId}/membership`: tham gia nhóm công khai; yêu cầu
  đăng nhập và CSRF. Request lặp lại không tạo membership trùng.
- `GET /api/travel-groups/{groupId}`: xem thông tin nhóm và tối đa 50 bài viết
  mới nhất; nhóm công khai cho phép đọc khi chưa đăng nhập.
- `POST /api/travel-groups/{groupId}/posts`: đăng bài văn bản tối đa 2.000 ký tự;
  yêu cầu user đang hoạt động và CSRF, nhưng không bắt buộc đã tham gia nhóm.

Mỗi group trả `countryCode`, `countryName`, `name`, `photoUrl`, `memberCount`,
`isMember` và `isPublic`.

Group detail trả `group`, `posts` và `totalPosts`. Mỗi post trả `id`, `content`,
`createdAt` và `author` gồm `id`, `fullName`, `avatarUrl`.

### Kiểm tra trạng thái

`GET /health`

```json
{"message": "ok"}
```

### Authentication và hồ sơ

- `POST /api/auth/register`: tạo traveler và set access/refresh/CSRF cookie.
- `POST /api/auth/login`: xác minh email/password và set cookie.
- `POST /api/auth/refresh`: rotate refresh session; yêu cầu CSRF header.
- `POST /api/auth/logout`: thu hồi refresh session và xóa cookie.
- `GET /api/me`: lấy user hiện tại.
- `PATCH /api/me/profile`: sửa hồ sơ; yêu cầu CSRF header.
- `GET /api/me/traveler-profile`: xem preference dài hạn và provenance signals.
- `PATCH /api/me/traveler-profile`: thay danh sách preference do user xác nhận;
  yêu cầu CSRF header.
- `DELETE /api/me/traveler-profile`: xóa toàn bộ hồ sơ cá nhân hóa dài hạn;
  yêu cầu CSRF header.
- `GET /api/me/showcase`: lấy các địa điểm đã đi và bài viết của user hiện tại.
- `POST /api/me/posts`: multipart tạo `post` hoặc `reel`; yêu cầu CSRF và các
  field `contentType`, `caption`, `locationName`, `media`. `post` nhận JPEG/PNG/WebP
  tối đa 15 MB; `reel` nhận MP4/WebM/MOV tối đa 100 MB. Backend kiểm tra chữ ký
  file và tự sinh `mediaUrl`; client không gửi URL media.
- `GET /api/posts?limit=30&offset=0`: feed bài công khai mới nhất; không yêu cầu
  đăng nhập và trả thêm `authorName`, `authorAvatarUrl`.
- `POST /api/me/visited-places`: đánh dấu hoặc cập nhật một `placeId` đã đi; tên
  field được giữ tương thích nhưng giá trị là `knowledge_entities.id`. Yêu cầu
  CSRF header và KG entity phải có tọa độ hợp lệ.
- `POST /api/me/creator-application`: gửi yêu cầu creator; yêu cầu CSRF header.

Response showcase:

```json
{
  "visitedPlaces": [
    {
      "id": "visit_uuid",
      "placeId": "place_uuid",
      "name": "Phố cổ Hội An",
      "city": "Hội An",
      "country": "Việt Nam",
      "latitude": 15.8800584,
      "longitude": 108.3380469,
      "visitedAt": "2026-06-14",
      "note": "Một chiều trong phố cổ."
    }
  ],
  "posts": [
    {
      "id": "post_uuid",
      "contentType": "post",
      "caption": "Hội An ngày nắng",
      "mediaUrl": "https://example.com/hoi-an.jpg",
      "locationName": "Phố cổ Hội An",
      "createdAt": "2026-06-15T02:30:00Z"
    }
  ]
}
```

Request đăng ký:

```json
{
  "email": "traveler@example.com",
  "password": "MatKhauManh123",
  "fullName": "Nguyen An"
}
```

JWT không được trả trong JSON. Backend lưu access/refresh token trong HTTP-only
cookie và lưu refresh token dạng hash trong `auth_sessions`. Request thay đổi dữ
liệu gửi cookie phải đặt `X-CSRF-Token` bằng giá trị cookie `vsf_csrf`.

`GET /api/users` và `POST /api/users` được giữ cho quản trị; cả hai yêu cầu role
admin, và `POST` yêu cầu CSRF. Đăng ký public chỉ đi qua `/api/auth/register`,
client không được tự chọn role.

### Lịch trình

- `GET /api/plans/feature-map`
- `POST /api/plans/explore`
- `POST /api/plans/explore/full/intake`
- `POST /api/plans/main`
- `POST /api/plans/main/from-explorer`
- `POST /api/plans/main/from-context`
- `POST /api/plans/current-location-route`
- `POST /api/plans/day-directions`
- `GET /api/plans/places/search?query={text}&destination={destination}&topK={k}`:
  trả tối đa `topK` gợi ý có tọa độ từ Knowledge Graph canonical trong
  vùng đích; mặc định `K=5`, nhận giá trị từ 1 đến 10. Search không phân biệt dấu
  và đọc cả alias có cấu trúc; endpoint autocomplete này không gọi provider
  geocoding bên ngoài và không bị giới hạn bởi batch preload của Planner.
- `POST /api/plans/{planId}/backup`

### Trip chat và lịch sử chỉnh sửa

Các endpoint sau yêu cầu đăng nhập; mọi thao tác ghi yêu cầu CSRF:

- `POST /api/trip-chats`: tạo một chat riêng cho một chuyến đi.
- `GET /api/trip-chats`: liệt kê chat của user hiện tại, mới cập nhật trước.
- `DELETE /api/trip-chats`: xóa toàn bộ chat thuộc user hiện tại cùng message và
  snapshot revision; không ảnh hưởng chat của user khác và trả `204 No Content`.
- `GET /api/trip-chats/{chatId}`: lấy message history, TripIntent hiện hành,
  `tripIntentVersion`, `tripIntentPlanStatus`, candidate review, tối đa năm turn
  gần nhất và plan hiện tại.
- `DELETE /api/trip-chats/{chatId}`: xóa chat thuộc user hiện tại cùng toàn bộ
  message và snapshot revision của chat; trả `204 No Content`.
- `PATCH /api/trip-chats/{chatId}/trip-intent`: nhận `tripIntent` canonical đầy
  đủ, `expectedRevision` và `expectedTripIntentVersion`. Backend validate rồi ghi
  `trip_chats.current_trip_intent` ngay, tăng intent version, đặt trạng thái
  `queued` và trả về mà không chờ Planner. Durable worker tạo lại plan nền và
  sau khi thành công mới cập nhật `current_plan`, tăng plan revision, tạo snapshot
  `trip_revisions.trip_intent_payload/plan_payload` và đặt trạng thái `synced`.
  Nhiều edit liên tiếp được coalesce; output của intent version cũ bị loại bỏ.
  Đổi destination không mang candidate hoặc selected place cũ sang plan mới.
  Chat chưa có plan trả `TRIP_INTENT_NOT_READY`; revision/version cũ trả
  `VERSION_CONFLICT`.
- `POST /api/trip-chats/{chatId}/messages`: gửi yêu cầu đầu tiên hoặc sửa plan
  hiện tại qua Conversation Supervisor. Mọi message đều tạo một
  `TripChatTurn` ở trạng thái `queued` rồi chạy `execute` ngay; trả
  `202 Accepted` với payload `TripChatTurnRead`. Client poll
  `GET /api/trip-chats/{chatId}/turns/{turnId}` cho tới khi status thuộc
  `{completed, awaiting_confirmation, failed, cancelled}`. Khi status là
  `awaiting_confirmation`, client phải gọi `POST .../turns/{turnId}/confirm`
  hoặc `POST .../turns/{turnId}/cancel`. `expectedRevision` được kiểm
  ở cả supervisor và mutation; nếu lệch sẽ trả `409 VERSION_CONFLICT`.
- `POST /api/trip-chats/{chatId}/turns`: tạo turn `queued` không execute.
  Dùng khi client muốn render placeholder trước khi gọi `/execute` riêng.
- `GET /api/trip-chats/{chatId}/turns/{turnId}`: đọc trạng thái hiện tại
  của một turn (queue, classifying, executing, awaiting_confirmation,
  completed, failed, cancelled). Endpoint này cũng tự động quét các
  turn `processing` quá thời gian (mặc định 300s) đánh dấu `failed`
  với `errorCode=TURN_STALE` để tránh treo supervisor.
- `GET /api/trip-chats/active-turns`: lấy các turn `queued`, `classifying` hoặc
  `executing` của user hiện tại. AppShell poll endpoint này cùng danh sách job
  URL để giữ bước và timer của Planner khi user chuyển route; turn của user
  khác không được trả về.
- `POST /api/trip-chats/{chatId}/turns/{turnId}/execute`: chạy
  supervisor cho turn đang `queued`. Idempotent: gọi lại với turn đã
  terminal sẽ trả về turn hiện tại mà không chạy lại LLM.
- `POST /api/trip-chats/{chatId}/turns/{turnId}/confirm`: áp dụng
  operation đang chờ xác nhận. Chỉ chấp nhận khi status là
  `awaiting_confirmation`; nếu `chat.revision != turn.baseRevision` trả
  `409 VERSION_CONFLICT`.
- `POST /api/trip-chats/{chatId}/turns/{turnId}/cancel`: hủy turn đang
  xử lý hoặc chờ xác nhận; turn đã `completed` trả `409 TURN_ALREADY_COMPLETED`.
- `POST /api/trip-chats/{chatId}/url-jobs`: tách URL thành các background job
  FIFO, lưu `content` thành một user turn `queued` trong cùng transaction và trả
  `202 Accepted` ngay. Các job trong batch dùng chung turn này; worker chỉ nối
  assistant response/plan khi hoàn tất. Field
  form `forceRefresh=true` tạo job phân tích lại, bỏ qua extraction cache.
- `POST /api/trip-chats/{chatId}/image-jobs`: lưu mỗi ảnh JPEG/PNG/WebP/HEIC/HEIF
  tối đa 15 MB thành một OCR background job và trả `202 Accepted`. Ảnh dùng chung
  FIFO, timeout, timing, retry/reprocess và stop/delete với URL.
- `GET /api/url-import-jobs`: lấy tối đa 40 job của user hiện tại để hiển thị
  notification toàn ứng dụng; user không đọc được job của tài khoản khác.
- `POST /api/url-import-jobs/{jobId}/retry`: đưa riêng một job thất bại về cuối
  hàng chờ và đặt `forceRefresh=true` để chạy lại toàn bộ từ media/STT/OCR. Job
  vượt deadline trả trạng thái `failed`, `errorCode` là `URL_IMPORT_TIMEOUT` và
  không chặn URL kế tiếp.
- `POST /api/url-import-jobs/{jobId}/reprocess`: tạo một job mới từ job đã
  kết thúc; URL dùng extraction cache, ảnh dùng lại file gốc đã lưu, rồi chạy
  aggregation/dedupe, resolve và Planner; giữ nguyên job cũ trong lịch sử và trả
  `202 Accepted`.
- `DELETE /api/url-import-jobs/{jobId}`: xóa job `queued`, hoặc dừng task và xóa
  job `running`, của user hiện tại; trả `204 No Content`. Khi dừng job đang chạy,
  worker giải phóng FIFO và nhận job kế tiếp ngay. Job `succeeded` hoặc `failed`
  cũng có thể được xóa khỏi lịch sử; revision plan đã tạo không bị ảnh hưởng.
- `POST /api/trip-chats/{chatId}/plan/items`: thêm item thủ công.
  Form Planner tra `GET /api/plans/places/search?query=...&destination=...` trên
  catalog Knowledge Graph và chỉ cho gửi item sau khi user chọn một kết quả
  có identity cùng tọa độ; nội dung gõ tự do không được xem là một địa điểm đã
  chọn.
- `PATCH /api/trip-chats/{chatId}/plan/days/{day}/items/{itemId}`: sửa item.
  Khi user chọn một kết quả từ place search, form gửi cùng `placeId`, `name`,
  `address`, `latitude` và `longitude`; backend lưu đồng bộ identity và tọa độ
  thay vì chỉ đổi tên hiển thị.
- `DELETE /api/trip-chats/{chatId}/plan/days/{day}/items/{itemId}`: xóa item.
- `DELETE /api/trip-chats/{chatId}/plan/unscheduled-places`: xóa một địa điểm
  khỏi danh sách chưa xếp. Request dùng `multipart/form-data` với
  `expectedRevision`, `name` và `placeId` tùy chọn; backend lưu một plan revision
  mới và chỉ cho phép chủ trip chat thao tác.
- `PUT /api/trip-chats/{chatId}/plan/days/{day}/items/reorder`: lưu thứ tự item
  mới của một ngày. Request dùng `multipart/form-data` với `expectedRevision`
  và các field `itemIds` lặp lại theo đúng thứ tự hiển thị mong muốn.
- `POST /api/trip-chats/{chatId}/plan/days/{day}/transport-legs/{legIndex}/retry`:
  tính lại riêng một chặng không có lựa chọn khả dụng, giữ nguyên thứ tự item và
  lưu revision mới. Request dùng `multipart/form-data` với `expectedRevision`.
  Nếu provider ô tô tạm lỗi trên một chặng đi bộ quá dài, response giữ fallback
  ô tô chưa xác minh thay vì để UI không còn lựa chọn nào.

Các thao tác trực tiếp trong editor (thêm, sửa, xóa, sắp xếp item và chọn
phương tiện) vẫn tạo plan revision nhưng không tạo `TripChatMessage`. Client
phản hồi thành công bằng toast tạm thời để lịch sử chat chỉ giữ hội thoại.

Request gửi message dùng `multipart/form-data`:

- `content`: yêu cầu mới của user;
- `expectedRevision`: revision client đang hiển thị;
- `urls`: URL lặp lại tùy chọn; URL trong `content` cũng được tự trích xuất;
- `images`: ảnh tùy chọn.

Lần gửi đầu tạo plan revision 1. Các lần sau cung cấp lịch sử user request và
TripIntent hiện tại đọc từ PostgreSQL cho Explorer, giữ các yêu cầu cũ trừ khi message mới
thay đổi chúng, và dùng item của plan hiện tại làm đầu vào cho revision. Kết quả
ghi đè con trỏ `currentPlan` nhưng giữ nguyên `currentPlan.id`; snapshot cũ vẫn
ở `trip_revisions` cùng TripIntent snapshot đã dùng.

Response detail:

Hai timing report gần nhất được lưu cùng trip chat, vì vậy `GET` detail vẫn trả
chúng sau khi URL job chạy nền hoàn tất hoặc khi user mở lại lịch sử. UI dùng
`totalSeconds` cho timer của Explorer và Planner + Finder, còn `stages` cho nhật
ký thời gian chi tiết.

```json
{
  "id": "chat_uuid",
  "title": "Chuyến đi Hà Nội",
  "destination": "Hà Nội",
  "revision": 2,
  "tripIntentVersion": 3,
  "tripIntentPlanStatus": "synced",
  "hasPlan": true,
  "currentPlan": {},
  "currentTripIntent": {},
  "candidateReviews": [],
  "latestExplorerTiming": {},
  "latestPlannerTiming": {},
  "messages": [
    {
      "id": "message_uuid",
      "role": "user",
      "content": "Thêm cà phê vào ngày 2",
      "attachmentNames": [],
      "planRevision": 2,
      "createdAt": "2026-07-30T07:00:00Z"
    }
  ],
  "createdAt": "2026-07-30T06:00:00Z",
  "updatedAt": "2026-07-30T07:00:00Z"
}
```

Hai timing field chỉ có trong response vừa xử lý message; khi đọc lại lịch sử
chúng có thể là `null` vì report debug không được lưu vào snapshot nghiệp vụ.

Nếu `expectedRevision` đã cũ, backend trả HTTP 409 với code
`VERSION_CONFLICT`. Lookup luôn lọc đồng thời `chatId + currentUser.id`; tài
khoản khác nhận `TRIP_CHAT_NOT_FOUND`.

Request tạo background URL job dùng `multipart/form-data` với `content`,
`expectedRevision`, `forceRefresh` tùy chọn và các field `urls` lặp lại. Backend
cũng nhận URL nằm trong `content`, loại trùng và giới hạn 20 URL/lần. Mỗi URL
tạo một resource riêng:

Request tạo background OCR job cũng dùng `multipart/form-data`, gồm `content`,
`expectedRevision` và tối đa 20 field `images`. Mỗi ảnh tạo một resource riêng.

```json
{
  "jobs": [
    {
      "id": "job_uuid",
      "chatId": "chat_uuid",
      "sourceType": "url",
      "sourceLabel": "https://www.youtube.com/watch?v=...",
      "url": "https://www.youtube.com/watch?v=...",
      "forceRefresh": false,
      "status": "queued",
      "phase": "queued",
      "queuePosition": 1,
      "attemptCount": 0,
      "resultRevision": null,
      "errorCode": null,
      "errorMessage": null,
      "createdAt": "2026-08-01T08:00:00Z",
      "startedAt": null,
      "finishedAt": null
    }
  ]
}
```

Worker xử lý một URL hoặc ảnh mỗi lần trên toàn hàng chờ của deployment. User có thể gửi
prompt thường, thêm batch nguồn khác hoặc điều hướng sang route khác trong khi job
chạy. `phase` có các giá trị `queued`, `exploring`, `planning`, `complete` để UI
hiển thị ba bước thân thiện “Chuẩn bị”, “Lấy dữ liệu” và “Tạo lịch trình” theo
tiến độ thật, không suy đoán từ elapsed time. Tiến độ chỉ hiển thị trong panel task toàn ứng dụng, không chèn message
trạng thái vào transcript và không disable chat composer. Mỗi task có thể mở để
xem thời điểm bắt đầu, tổng elapsed, attempt và timing stage có sẵn. Job thành
công lưu và trả riêng `explorerTiming` cùng `plannerTiming`, để UI đặt toàn bộ
nhật ký timing dưới đúng URL thay vì hiển thị trong cột chat Planner. Khi job thành công,
`resultRevision` trỏ tới revision chat mới; khi thất
bại, các URL sau vẫn tiếp tục và UI cho retry riêng. URL mạng nội bộ/private bị
từ chối trước khi enqueue.

Guest không gọi các endpoint `/url-import-jobs`: AppShell giữ queue trong memory
và lần lượt gọi Explorer intake rồi `main/from-explorer`. Kết quả/timing chỉ nằm
trong runtime trình duyệt, không tạo trip chat, job row hoặc plan revision trong
database. Queue sống qua điều hướng client-side nhưng không sống qua reload/đóng
tab. Khi user đăng nhập, client tiếp tục dùng contract job bền vững phía trên.

UI chỉ hiển thị **Chạy lại** và không bắt user chọn stage kỹ thuật. Job thành
công được reprocess từ extraction cache; job thất bại được retry toàn bộ với
`forceRefresh=true`. Endpoint retry resolution riêng vẫn tồn tại cho workflow
nội bộ/advanced nhưng không phải control chính trên danh sách job. Cache hiện
tại không bị xóa trước; chỉ khi intake mới lưu thành công thì kết quả extraction
mới ghi đè cache, nên job lỗi không làm mất fallback cũ.

Request Explorer intake dùng `multipart/form-data`. UI hiển thị một chat
composer duy nhất: người dùng nhập prompt hoặc dán URL vào cùng trường nội dung,
và đính kèm ảnh ngay trong composer. Backend chọn nhánh xử lý dựa trên dữ liệu
có mặt: OCR khi có ảnh, URL extraction khi tìm thấy URL, nếu không thì xử lý
prompt thường. Không dùng LLM để phân loại kiểu input.

Form fields:

- `rawRequest`: nội dung user nhập bắt buộc; có thể chứa prompt hoặc một hay
  nhiều URL. Ảnh là context bổ sung và không thay thế raw prompt.
- `destination`: tùy chọn; nếu thiếu backend suy luận từ `rawRequest`.
- `urls`: tùy chọn để tương thích client cũ; client mới dán URL trực tiếp vào
  `rawRequest` và backend tự trích xuất.
- `tripSpec`: tùy chọn; JSON object theo shape của Explorer `tripSpec`.
- `userState`: tùy chọn; JSON object gồm locale, timezone, travelStyle và
  travelPreferences. Khi đã đăng nhập, backend tự lấy `userId` và preference
  profile từ session/database, không tin `userId` do client khai báo.
- `forceRefresh`: boolean tùy chọn; khi `true`, URL intake bỏ qua extraction
  cache và chạy lại media/STT/OCR. Nút **Chạy lại** của phiên khách tự đặt field
  này theo trạng thái: `true` sau lỗi và `false` sau lượt thành công.
- `images`: tùy chọn; nhiều file ảnh JPEG, PNG, WebP, HEIC hoặc HEIF.

Nếu YouTube chặn caption ở cả backend và worker fallback, response trả HTTP 503
với code `YOUTUBE_CAPTIONS_UNAVAILABLE` để client cho phép retry; lỗi truy cập
không được coi nhầm là video không có caption. Nếu provider xác nhận video không
có public caption, response trả HTTP 422 `YOUTUBE_CAPTIONS_NOT_FOUND`. YouTube
long-form không có fallback tải media hoặc STT. URL YouTube có path
`/shorts/{videoId}` được nhận diện là `youtube_shorts` và chạy cùng pipeline
media STT + frame vision/OCR của TikTok video, Instagram Reels và Facebook
Reels. URL `youtu.be/{videoId}` không mang tín hiệu loại nội dung nên giữ contract
caption-only.

Nếu nguồn công bố expected count (ví dụ `Top 10`) nhưng extractor chỉ tạo được
dưới 40% venue authority cao/trung bình, response trả HTTP 422
`URL_EXTRACTION_LOW_COVERAGE` trước formatter, place provider và Planner.
Timing từng source có thêm `speechSource`, `expectedPlaceCount`,
`extractionCoverage` và `coverageStatus`; client hiển thị `YouTube caption`
thay vì gắn nhãn STT cho caption. Coverage 40–70% vẫn trả Explorer nhưng
không cho phép thay source URL; Finder vẫn được bù activity còn thiếu.

Input JSON của Explorer nhận `userState.travelStyle` để client truyền phong cách
du lịch người dùng, ví dụ `local`, `adventure`, `relaxation` hoặc một chuỗi mô
tả khác. Giá trị mặc định hiện tại là `local`.

Output công khai chứa `intakeId`, `userId` và JSON `explorer` với một
`tripIntent` canonical, assumptions, missingInfoQuestions và
`preferenceSnapshot`. Không còn hai object `intent`/`tripSpec` ở contract
Explorer.
`preferenceSnapshot.signals` là tín hiệu ngắn hạn của intake;
`effectiveProfile` là profile đã merge để Planner dùng. `placeCandidates` là contract
`candidateReviews` an toàn để hiển thị, và timing. Raw payload vẫn chỉ lưu hành
nội bộ giữa extractor, aggregator, resolver và repository; không trả cho client.

Không công khai raw OCR, transcript, URL result hoặc debug. Caption/STT/OCR và
`ExtractedContext` dùng chung một `source_documents` theo canonical URL.
Area/Venue candidate, evidence, `sourceActivity` và provenance được stage trong
`knowledge_graph_import_nodes`; display note không được lưu ở import node. Flow
không ghi vào `places` hay graph canonical trước admin review. Review không chặn
TripIntent/itinerary provisional.

`explorer.candidateReviews[]` giữ candidate có evidence sau aggregation kể cả
khi place provider chưa resolve được. Mỗi item có `candidateId`, `name`,
`category`, `status` (`resolved | needs_review | merged | ignored`),
`resolutionReason`, provider/nhãn/address/toạ độ đã xác minh khi có,
`hasRepresentativeLocation`, `searchRegion`, canonical `sourceUrls`, source
order/day/time/activity/duration, `entityType` (`venue | sub_place`) và
`authority` (`high | medium | low`),
`extractionConfidence`, `resolutionConfidence`, confidence tương thích cũ và
`retryable`. Contract còn có `observedAliases`, `generatedLookupAliases`, tối đa
năm `topMatches`, `verifiedAliases` và `verifiedVietnameseAliases`. Frontend ưu
tiên alias tiếng Việt đã xác minh cho `resolvedName`; alias do LLM sinh không
được coi là verified nếu chưa map tới stable identity. Field này không chứa raw
transcript/OCR. Chỉ item `resolved` có đủ
danh tính và tọa độ được đưa vào Planner. Item `needs_review`, kể cả khi có
`hasRepresentativeLocation = true`, chỉ phục vụ review/retry và không được xếp
vào plan.

`POST /api/trip-chats/{chatId}/candidate-resolutions/retry` nhận
`{"expectedRevision": N}`. Endpoint chỉ chạy alias enrichment + place resolver
cho item `needs_review`; không tải lại URL, không chạy STT/OCR. Khi có item mới
resolve, service tạo revision chat mới và dựng lại plan hiện tại để đưa các
địa điểm vừa xác minh vào lịch trình. Endpoint yêu cầu đăng nhập, CSRF và kiểm
tra optimistic revision; response là `TripChatRead` mới nhất.

Explorer response có thêm `timingReport` để debug latency. Report dùng cùng
`intakeId`, gồm `totalSeconds`, các stage cấp Explorer, timing chi tiết theo từng
URL và số candidate/resolved/persisted. Mỗi source URL còn có
`extractedPlaceCount`, `candidateCount`, `resolvedCount`, `providerCounts` và
`resolvedProviderCounts`, cùng `sttChunkCount`, `sttAudioDurationSeconds`,
`sttChunkDurationSeconds` và `sttChunkRetryCount`. Hai field
`cacheStatus` (`hit`, `miss`, `bypassed`) và `cacheLookupSeconds` cho biết source
dùng extraction đã lưu, phải chạy extraction mới, hay chủ động bỏ qua cache;
`providerCounts` là số candidate provider đã xử lý,
không đồng nghĩa tất cả đã resolve thành công. Report cấp intake cũng có
`resolvedProviderCounts` với cùng ý nghĩa. `providerAttempts` ghi từng attempt
thực tế với `candidate`, `provider`, `attemptedQueries`, `aliasQueryCount`, `queueWaitSeconds`,
`executionSeconds`, `outcome` và `rejectionReason`; cache hit dùng
`provider=cache`, `outcome=cache_hit`. Các stage chạy song song giữ duration
riêng và phải so theo wall time, không cộng STT với frame vision hoặc Formatter
với place resolution. `attemptedQueries` là các keyword địa điểm đã thực sự gửi
đến Knowledge Graph DB hoặc Google Maps Playwright để phục vụ panel chẩn đoán; terminal
log chủ động loại field này cùng tên candidate. Report không chứa raw prompt,
URL đầy đủ, transcript, OCR text, provider payload hay credential. Runtime nối mỗi report thành một dòng JSON tại
`backend/var/explorer-timings.jsonl`; dùng
`cd backend && python scripts/show_explorer_timing.py` để xem lần gần nhất.
Dropdown tác vụ URL hiển thị các stage theo thứ tự, duration và `details` an toàn;
đồng thời tách `processed` từ `resolved` cho từng provider ở cấp intake và từng
URL. Trong khi HTTP Explorer vẫn đang chạy, UI chỉ hiển thị tổng timer và trạng
thái đang thu thập; timing chi tiết xuất hiện sau khi Explorer trả report, không
suy đoán provider hoặc duration trung gian ở client.

Panel giữ job thành công và toàn bộ timing cho tới khi user bấm **Xóa tác vụ**;
mở plan không tự ẩn job trong giai đoạn kiểm thử hiện tại.

Mỗi phần tử địa điểm có `category` với một trong các giá trị `attraction`,
`food`, `cafe`, `hotel`, `transport`, `free_time`, `nature`, `culture`,
`shopping`, `nightlife`, `wellness`, `adventure`, `beach`, `family`, `other`.
Candidate có thể có `attributes` chuẩn hóa và mặc định
`preferenceLevel=preferred`. Khi evidence không
đủ để phân loại, backend dùng `other`:

```json
{
  "name": "Bánh mì Phượng",
  "category": "food",
  "addressHint": "Hội An",
  "searchRegion": "Hội An",
  "sources": [
    {
      "type": "url",
      "url": "https://example.com/video"
    }
  ],
  "confidence": 0.88,
  "priority": 1,
  "preferenceLevel": "preferred",
  "attributes": ["local", "budget"],
  "notes": "Được nhắc trong transcript",
  "sourceEvidence": {
    "stt": "On day two, we ate here.",
    "ocr": "Bánh mì Phượng"
  }
}
```

`destination`/trip base và `searchRegion` có nghĩa khác nhau. Một itinerary có
thể giữ trip base là Hà Nội nhưng gán `searchRegion=Ninh Bình` cho toàn bộ stop
Day 2 sau khi STT nói rõ đây là day trip Ninh Bình. Resolver tìm theo
`candidateName + addressHint + searchRegion`, lưu riêng `resolvedName` và
`resolutionReason`. Plan/UI hiển thị `resolvedName` đã xác minh và ưu tiên nhãn
Việt; `candidateName` vẫn được giữ trong record provenance, không bị mất.

Heading cấp thành phố có duration không nằm trong `placeCandidates`. Explorer
trả nó trong `tripIntent.timing.destinationStays`, ví dụ:

```json
{
  "name": "Hanoi",
  "durationDays": 2,
  "startDay": 1,
  "endDay": 2,
  "sourceRefs": ["https://www.instagram.com/reel/example"]
}
```

Planner phải áp `targetArea=Hanoi` cho cả Ngày 1 và Ngày 2. Nếu intake chỉ có
city stay và chưa có venue cụ thể, Finder được phép bổ sung activity và meal
venue theo cùng planning pipeline của raw prompt.

Response tổng quát:

```json
{
  "intakeId": "uuid",
  "userId": "user-uuid",
  "explorer": {
    "tripIntent": {
      "destination": "Hà Nội",
      "timing": {"days": 3, "flexibility": "unknown"},
      "travelParty": {"type": "couple", "adults": 2},
      "budget": {"targetAmount": 6000000, "currency": "VND", "level": "medium"},
      "notes": [],
      "preferences": {},
      "constraints": {"items": [], "policy": {}}
    },
    "assumptions": [],
    "missingInfoQuestions": [],
    "preferenceSnapshot": {
      "version": 1,
      "signals": [],
      "effectiveProfile": {
        "version": 1,
        "explicit": [],
        "scores": {},
        "observationCount": 0
      }
    }
  }
}
```

`explorer.tripIntent.budget` là vị trí duy nhất chứa ngân sách:

```json
{
  "targetAmount": 6000000,
  "currency": "VND",
  "level": "medium"
}
```

`targetAmount` luôn là số tiền gần đúng; khi user không nêu số tiền, giá trị là
`null`. `currency` là mã ISO 4217 gồm ba chữ cái viết hoa. `level` chỉ nhận
`low`, `medium` hoặc `high`. Contract không có `inputMode`, khoảng min/max,
hard-cap, confidence hay calculation
basis, và không có `budgetLevel` ở vị trí khác.

`POST /api/plans/main/from-explorer` nối kết quả Explorer vào Planner/Finder.
Response bọc plan trong `{ "plan": ..., "timingReport": ... }`.
`timingReport` gồm tổng wall-clock và các stage
`preparePlanningContext`, `tripThemePlanner`, `placeSelector`, `assemblePlan`,
`checkOverall`; report còn trả số ngày, item, chặng di chuyển, địa điểm chưa
xếp và cảnh báo để UI hiển thị chi tiết latency. Mỗi stage có `dataSource` để
phân biệt Explorer snapshot, Knowledge Graph DB + LLM, Knowledge Graph DB + deterministic
rules, plan assembly và checker. Timing không chứa prompt,
selected-place payload hay dữ liệu provider thô.
Stage `tripThemePlanner` còn có `subStages` để tách `regionStatistics`,
`graphResearch`, `graphProjection`, `llmGenerate`, `validateThemeDraft` và các
lần sửa hiếm `llmRepairN`/`validateThemeRepairN`. Chi tiết chỉ giữ trạng thái,
số lượng candidate, kích thước response và loại lỗi validation; không giữ raw
prompt, model response hoặc graph evidence.
Request gồm `tripIntent`, `intakeId`, `userId`, `selectedPlaces`,
`candidateReviews`, `allowFinderGapFill`, `allowReplaceSourcePlaces` và cờ nội bộ
`expandDaysToFitSelectedPlaces`. `candidateReviews` cho phép bước hậu xử lý đọc
activity URL chưa resolve sau khi Finder đã chốt route; field này không tự biến
candidate thành selected place. Trip chat
bật cờ mở rộng khi user chưa từng khóa số ngày/khoảng ngày, hoặc khi amendment
yêu cầu thêm ngày; số ngày được giới hạn tối đa 30 và được tính lại sau khi merge
địa điểm cũ với intake mới. Khi cờ là `false`, service giữ duration hiện tại và
trả phần vượt sức chứa trong `plan.unscheduledPlaces`. UI Planner hiển thị danh
sách này với thao tác thêm thủ công vào một ngày hoặc điền prompt yêu cầu AI xếp.
Item có `reasonCode=activity_fallback_recommendation` mang place/location,
popularity và `sourceProvider=route_aware_activity_fallback`; đây là gợi ý của
hệ thống gần route, không phải venue được URL xác nhận.
Route-first giữ ít nhất một activity giữa breakfast–lunch, ít nhất một activity
giữa lunch–dinner và ba meal anchor mỗi ngày; restaurant/food URL ưu tiên thay
meal suggestion, còn cafe/coffee dùng activity slot.
Service merge `selectedPlaces` explicit với các candidate đã tự động lưu theo
đúng `intakeId + userId`. Candidate chưa được user xác nhận vẫn giữ
`preferenceLevel=preferred`, confidence và provenance; không được đổi thành
`mustVisit` ngầm.

Explorer trả `allowFinderGapFill=true` và `allowReplaceSourcePlaces=false` cho
cả prompt thuần lẫn intake URL/ảnh/OCR. Finder chỉ lấp slot activity/meal còn
thiếu; không được xóa, thay thế hoặc đổi provenance của source Place. Request cũ
dùng `allowPlaceSuggestions` hoặc `allowFinderSuggestions` vẫn được nhận như
alias của `allowFinderGapFill`, nhưng response chỉ xuất hai policy mới.

Nếu intake URL/OCR không có `tripIntent.timing.days` explicit, Explorer suy ra số ngày từ
`sourceDay`; nếu nguồn không gán ngày, dùng số ngày tối thiểu theo số stop và
pace để không làm mất stop. Giá trị user nói rõ luôn được giữ nguyên.

Với intake URL, nếu destination trong prompt/trip hiện tại xung đột với vùng
đồng thuận từ `searchRegion` hoặc thành phố của các stop URL đã resolve, endpoint
trả HTTP `409`, code `DESTINATION_CLARIFICATION_REQUIRED`, kèm
`requestedDestination`, `sourceDestination` và ba choice
`keep_prompt_destination`, `create_separate_reel_trip` hoặc
`follow_reel_destination`. Planner không chạy và plan hiện tại không bị thay đổi
trước khi user làm rõ. Chỉ khi prompt và reel cùng
vùng nhưng formatter trả sai, backend mới tự sửa formatter output và ghi
`explorer.trace.destinationGuardrail`. Itinerary nhiều vùng không đủ đồng thuận
không tự động đổi trip base theo một day trip.

Với itinerary từ URL, phần tử `selectedPlaces` có thể có `sourceOrder`,
`sourceDay`, `sourceTimeHint`, `sourceActivity` và
`sourceDurationMinutes`; khi resolve được còn có `address`, `latitude` và
`longitude`. Khi dữ liệu đã tồn tại trong Knowledge Graph hoặc import snapshot,
`selectedPlaces` và `PlanItem` còn có thể trả `imageUrls`,
`rating` và `reviewCount`. Field thiếu được để rỗng/null; API không tạo ảnh hoặc
rating giả. `PlanItem.notes` chỉ còn để đọc revision cũ.
`PlanItem.noteSources[]` có shape
`{ type, text?, evidence?, ref?, evidenceTypes?, fetchedAt? }` và chỉ chứa câu
chuyện/mẹo source-owned có ích; Google/provider metadata không được tạo thành
note. `Plan.regionStories[]` dùng cùng shape cho nhận xét/tip áp dụng cho cả
destination và chỉ xuất hiện khi `evidence` là span có thật trong source.
`PlanItem.personalNotes` là lời nhắc user
chỉnh sửa qua mutation endpoint. Ba field được giữ trong cùng trip-chat revision
và itinerary/map popup phải đọc cùng `PlanItem`. `PlanItem` trả lại cùng địa
chỉ/tọa độ để UI hiển thị và đặt marker.
Mutation thêm/sửa item không nhận `notes` hoặc `noteSources`; text do user nhập
chỉ đi qua `personalNotes`, vì source summary và provenance là read-only.
`sourceProvider` giữ adapter đã resolve candidate (`knowledge_graph`,
`google_maps_scraper`, ...). Giá trị `database` chỉ có thể còn xuất hiện trong
snapshot/cache legacy và cũng được UI hiển thị là Knowledge Graph DB.
và được chuyển tiếp vào `PlanItem` cùng `sourceRefs`; UI dùng hai field này để
hiển thị URL nguồn chính xác dưới dạng liên kết, kèm provider resolve như
`https://www.tiktok.com/... · GOOGLE MAPS · PLAYWRIGHT`. Card không có URL provenance được phân
biệt bằng `Finder gợi ý` hoặc `Địa điểm đã chọn`. `PlanItem` cũng trả lại `sourceDay`
để lần sửa tiếp theo không làm mất phân ngày của nguồn.
Planner/Finder ưu tiên blueprint URL và giữ thứ tự nguồn. Hard constraint
explicit vẫn thắng; timing cue không được mô tả như giờ hoạt động đã xác minh.

Sức chứa activity tối đa theo pace hiện là 2 cho `relaxed`, 3 cho `balanced` và
5 cho `packed`. Stop vượt sức chứa hoặc khiến timeline đạt/vượt `24:00` được
trả trong `unscheduledPlaces` với reason code tương ứng; API không trả khung giờ
như `24:07-25:07`.

Request còn nhận `preferenceProfile` từ
`explorer.preferenceSnapshot.effectiveProfile`. Plan day trả `transportLegs`
với thứ tự đã tối ưu nearest-neighbour + 2-opt. Finder batch ordered stop của
từng ngày qua Valhalla rồi tách response thành từng adjacent leg. Haversine chỉ
là prefilter pedestrian; leg thành công có
`source=valhalla_routing`, `verified=true`, `fetchedAt` và geometry theo đường;
provider lỗi fallback thành `source=geodesic_estimate`, `verified=false`.
`verified=true` không được mô tả là dữ liệu traffic live.

Khi preference/constraint cần transit, Finder gọi OpenTripPlanner theo ngày của
`PlanDay` và giờ kết thúc item đầu. Route có ít nhất một transit section
mới được nhận; itinerary chỉ đi bộ bị loại. Nếu
`tripSpec.transport.preferredModes` chứa `bus` hoặc `train`, transit khả thi trở
thành leg chính. Planner không gọi OTP mặc định chỉ để tạo
`transportLeg.alternatives` khi user không có transit preference.
`avoidModes` loại mode tương ứng trước khi chọn. Transit option có
`source=opentripplanner_transit`, geometry, duration gồm cả thời gian chờ và
`details.transitModes`/`details.lines`/`details.agencies`. `details.segments`
giữ thứ tự từng leg do OTP trả về; mỗi segment có `mode`, `fromPlace`, `toPlace`,
`distanceMeters`, `estimatedDurationMinutes`, `geometryCoordinates` và có thể
có `line`/`headsign`.
Tên điểm đầu và cuối của toàn hành trình được chuẩn hóa theo stop trong plan,
còn tên trạm trung gian lấy từ OTP.

`POST /api/plans/current-location-route` nhận tọa độ tạm thời từ Geolocation API
cùng stop đang chọn trên bản đồ, hoặc stop đầu tiên của ngày nếu chưa chọn.
Endpoint không lưu vị trí vào plan hoặc
database. Response là một `PlanTransportLeg` camelCase dùng chung với itinerary,
gồm mode, distance, duration, geometry, `source`, `verified`, `fetchedAt` và
`alternatives`. Khi Valhalla/OTP được cấu hình, backend thử pedestrian/car và public
transit theo preference; khi provider không khả dụng, response giữ
`source=geodesic_estimate` và `verified=false`.

```json
{
  "origin": {"latitude": 10.7769, "longitude": 106.7009},
  "destination": {
    "itemId": "stop-1",
    "name": "Bưu điện Thành phố",
    "latitude": 10.7798,
    "longitude": 106.699
  },
  "departureTime": "2026-07-30T09:00:00+07:00",
  "preferredModes": [],
  "avoidModes": []
}
```

`POST /api/plans/day-directions` chỉ dùng khi UI đang chọn một ngày cụ thể.
Request chứa điểm bắt đầu tạm thời (vị trí thiết bị hoặc địa điểm user tìm), toàn
bộ stop có tọa độ của ngày theo thứ tự lịch
trình và `timeWindow` của từng stop. Backend không tối ưu lại thứ tự; nó trả mảng
`PlanTransportLeg` theo chuỗi cố định
`origin -> stop 1 -> ... -> stop N`. `origin.name` là tùy chọn; khi bỏ trống,
backend dùng nhãn “Vị trí của bạn” để tương thích với client cũ. Mỗi leg có tuyến đề xuất làm primary và
các lựa chọn đi bộ, ô tô trong `alternatives`; xe buýt chỉ xuất hiện khi
provider trả route transit có geometry. Chặng `origin -> stop 1` dùng
`departureTime` của request; mỗi chặng sau dùng giờ kết thúc `timeWindow` của
stop đầu chặng trên cùng ngày để khớp saved itinerary. Backend chuẩn hóa cả
`departureTime` và `timeWindow` về `Asia/Ho_Chi_Minh` (`UTC+07:00`) trước khi
gọi provider. Endpoint chỉ được gọi sau thao tác “Chỉ đường”/“Tính lại”; chọn alternative chỉ đổi geometry ở client
và không gọi provider lại. `requestedMode=walk|car|bus` vẫn được hỗ trợ để ép
đồng nhất mọi chặng khi cần. Nếu ép `bus` nhưng một chặng không có route
transit, endpoint trả HTTP 422 thay vì tạo tuyến ước tính hoặc geometry đường
chim bay.

```json
{
  "origin": {
    "name": "Khách sạn trung tâm",
    "latitude": 10.7769,
    "longitude": 106.7009
  },
  "destinations": [
    {
      "itemId": "stop-1",
      "name": "Bưu điện Thành phố",
      "timeWindow": "08:00-10:00",
      "latitude": 10.7798,
      "longitude": 106.699
    }
  ],
  "departureTime": "2026-07-31T09:00:00+07:00"
}
```

Request tạo plan chính:

```json
{
  "intakeId": "uuid-từ-explorer",
  "userId": "user-uuid",
  "tripIntent": {
    "destination": "Hà Nội",
    "timing": {"days": 3, "flexibility": "unknown"},
    "travelParty": {"type": "couple", "adults": 2},
    "budget": {"targetAmount": 6000000, "currency": "VND", "level": "medium"},
    "notes": [],
    "preferences": {},
    "constraints": {"items": [], "policy": {}}
  }
}
```

Khi upstream đã có output chuẩn hóa từ Explorer, Planner có thể nhận trực tiếp
phần context mà không chạy lại Explorer qua
`POST /api/plans/main/from-context`:

```json
{
  "intent": {
    "destination": "Hà Nội",
    "travelStyle": "local",
    "pace": "balanced",
    "interests": ["food", "culture"],
    "mustVisitPlaces": [],
    "avoidPlaces": [],
    "constraints": [],
    "constraintPolicy": {
      "excludedPlaceTypes": ["cemetery"],
      "geographicScope": {
        "type": "coastal"
      }
    },
    "clarifyingQuestions": []
  },
  "tripSpec": {
    "days": 3,
    "partySize": 2,
    "budget": {
      "targetAmount": 6000000,
      "currency": "VND",
      "level": "medium"
    }
  },
  "regionKey": "vn,ha-noi",
  "selectedPlaces": [
    {
      "placeId": "place_123",
      "name": "Văn Miếu",
      "mustVisit": true,
      "sourceRefs": ["source_123"]
    }
  ],
  "userStatus": {}
}
```

`selectedPlaces` vẫn là ranh giới xác nhận: endpoint không tự chuyển
`placeCandidates` hoặc `foodPlaces` chưa xác nhận thành yêu cầu bắt buộc.

Nếu cả catalog vùng và `selectedPlaces` đều trống, endpoint trả lỗi
`PLANNER_INPUT_INSUFFICIENT` với HTTP 422. Plan chỉ có trạng thái `locked` khi
`CheckOverall.status` là `passed`; khi có warning cần backup, plan giữ trạng thái
`draft`; lỗi kiểm tra mức `error` tạo plan `failed`.

Plan tạo qua trip chat và lịch sử revision không bị mất khi tiến trình backend
khởi động lại. Plan tạo qua các endpoint `/plans/main*` độc lập và request tạo
backup vẫn chỉ hoạt động khi plan chính còn trong bộ nhớ của cùng tiến trình.

### Điểm cuối minh họa/tạm thời

- `GET /api/marketplace/categories`

Đây chưa phải contract production.

### Planning Control dành cho admin

- `GET /api/admin/planning-runs`: danh sách run; hỗ trợ `status`, `stage`,
  `query`, `limit`, `offset`.
- `GET /api/admin/planning-runs/{runId}`: chi tiết run và snapshot input/output
  đã redaction theo từng stage.
- `GET /api/admin/planning-runs/golden/cases`: đọc golden cases theo `module`
  và trả thêm kết quả kiểm tra contract ở `validation`.
- `POST /api/admin/planning-runs/golden/cases/{caseId}/run`: thực thi case bằng
  module runtime thật, lưu một planning run có `source=golden_dataset`, rồi trả
  `effectiveInput`, `actualOutput`, thời gian chạy, adaptation minh bạch và
  mismatch so với golden projection. Input sai contract trả execution
  `status=failed` cùng `GOLDEN_INPUT_INVALID` để UI vẫn điều tra được thay vì
  che lỗi dưới response 500.

Bốn endpoint đều yêu cầu JWT cookie hợp lệ và role `admin`. API không trả raw
media, toàn bộ prompt, transcript tự do, secret hoặc query string URL.
Case Extractor/Explorer/Planner/full pipeline có thể gọi provider thật và phát
sinh độ trễ hoặc chi phí; case có URL/asset giả sẽ trả lỗi execution tương ứng.

## Quy ước cho API mới

- Resource path dùng danh từ số nhiều.
- ID là chuỗi opaque, client không suy luận cấu trúc bên trong.
- Timestamp dùng ISO 8601 UTC; item trong lịch trình phải giữ thêm timezone địa
  phương.
- Tiền dùng dạng `{ "amount": 100000, "currency": "VND" }`.
- Phân trang dùng cursor và thứ tự ổn định.
- Lỗi validation chỉ rõ field và mã máy ổn định.
- Thao tác thay đổi dữ liệu có thể retry phải nhận `Idempotency-Key`.
- Job chạy lâu trả `202 Accepted` kèm job resource.
- Chỉnh sửa optimistic gửi version hoặc ETag và trả `409` khi xung đột.

Cấu trúc lỗi chuẩn của các module mới:

```json
{
  "code": "VERSION_CONFLICT",
  "message": "Dữ liệu đã được cập nhật bởi một phiên làm việc khác.",
  "fieldErrors": {},
  "requestId": "req_..."
}
```

Backend trả cùng request ID trong header `X-Request-ID`. Validation trả
`VALIDATION_ERROR`; chưa đăng nhập trả `AUTHENTICATION_REQUIRED`; sai role trả
`INSUFFICIENT_ROLE`.

## Contract liên module đã triển khai

`PlanMarketplaceGateway` là protocol Python dùng giữa module Planner và
Marketplace trong modular monolith. Đây không phải HTTP endpoint và không cho
Marketplace truy cập trực tiếp `PlanRepository`.

- `get_publish_info(planId, actorId)`: xác minh ownership, version và trạng thái
  publishable.
- `get_preview(planVersionId)`: trả snapshot preview an toàn.
- `clone_for_buyer(planVersionId, buyerId, sourceListingVersionId)`: tạo bản sao
  buyer độc lập.

Hiện protocol, schema và fake contract test đã có; implementation persistence và
version phía Planner vẫn là phần Người B cần hoàn thành trước Listing.

## Nhóm tài nguyên mục tiêu của MVP

- `/auth`, `/me`, `/users`
- `/trips`, `/trips/{id}/versions`, `/trips/{id}/members`
- `/imports`, `/imports/{id}/candidates`, `/planning-jobs`, `/places`, `/routes`
- `/listings`, `/creators`, `/favorites`
- `/checkout-sessions`, `/orders`, `/payments/webhooks`
- `/reviews`, `/reports`
- `/admin/*`

Mỗi endpoint phải được mô tả trong OpenAPI sinh tự động và có ví dụ
request/response. Khi contract thay đổi, phải cập nhật schema frontend và test
trong cùng thay đổi.

## Contract mục tiêu: nhập URL

- `POST /api/imports`: tạo import job cho một URL thuộc trip.
- `GET /api/imports/{importId}`: lấy trạng thái, tiến độ và lỗi.
- `GET /api/imports/{importId}/candidates`: lấy claim/place candidate.
- `POST /api/imports/{importId}/candidates/{candidateId}/confirm`: xác nhận place.
- `POST /api/imports/{importId}/retry`: retry từ bước lỗi phù hợp.
- `DELETE /api/imports/{importId}`: bỏ nguồn khỏi draft theo quy tắc provenance.

Request:

```json
{
  "tripId": "trip_...",
  "url": "https://www.tiktok.com/@creator/video/...",
  "clientRequestId": "client_..."
}
```

Response `202 Accepted`:

```json
{
  "importId": "imp_...",
  "status": "queued",
  "sourceType": "tiktok",
  "progress": {"stage": "queued", "percent": 0},
  "createdAt": "2026-07-27T08:00:00Z"
}
```

Place candidate không được chỉ trả tên tự do:

```json
{
  "id": "candidate_...",
  "rawName": "Tiệm cà phê Túi Mơ To",
  "claimType": "place",
  "confidence": 0.86,
  "evidence": {
    "artifactType": "transcript",
    "excerpt": "đoạn bằng chứng ngắn được phép hiển thị",
    "timestampSeconds": 42
  },
  "matches": [
    {
      "placeId": "place_...",
      "displayName": "Tiệm cà phê Túi Mơ To",
      "address": "Đà Lạt, Lâm Đồng",
      "confidence": 0.92
    }
  ],
  "reviewStatus": "needsConfirmation"
}
```

Xác nhận candidate phải nhận `placeId`, lựa chọn loại bỏ hoặc dữ liệu sửa thủ
công. API không được coi candidate đầu tiên là lựa chọn của user.

## Contract mục tiêu: tạo và chỉnh sửa plan

- `POST /api/trips/{tripId}/explore`: xác định câu hỏi còn thiếu.
- `POST /api/trips/{tripId}/plans`: tạo planning job từ input đã xác nhận.
- `GET /api/planning-jobs/{jobId}`: trạng thái từng stage.
- `GET /api/trips/{tripId}/plans/{planId}`: lấy plan, source và check report.
- `PATCH /api/trips/{tripId}/plans/{planId}/items/{itemId}`: sửa/khóa item.
- `POST /api/trips/{tripId}/plans/{planId}/revisions`: AI sửa theo phạm vi.
- `POST /api/trips/{tripId}/plans/{planId}/checks`: kiểm tra lại plan/version.
- `POST /api/trips/{tripId}/plans/{planId}/backups`: tạo Backup Plan riêng.
- `POST /api/trips/{tripId}/plans/{planId}/versions`: tạo snapshot.

Request tạo planning job tham chiếu ID, không gửi lại payload nguồn thô:

```json
{
  "selectedPlaceIds": ["selected_place_1", "selected_place_2"],
  "startDate": "2026-10-20",
  "days": 3,
  "timezone": "Asia/Ho_Chi_Minh",
  "budget": {"amount": 5000000, "currency": "VND"},
  "pace": "balanced",
  "interests": ["food", "coffee"],
  "hardConstraints": ["avoidStairs"],
  "lockedItemIds": []
}
```

Planning job phải công bố stage như `exploring`, `planning`, `finding`,
`checking` và `creatingBackup`. Kết quả plan phải phân biệt:

- `selectedPlaces`: địa điểm user đã xác nhận;
- `scheduledItems`: item đã được xếp;
- `unscheduledPlaces`: địa điểm chưa xếp cùng reason code;
- `assumptions` và `warnings`;
- `checkReport`;
- `sourceRefs` thay vì sao chép toàn bộ nội dung nguồn.

## Admin review place dedupe

- `GET /api/admin/knowledge-graph/place-dedupe/review`: trả các nhóm
  `needs_review` theo trang với `offset`, `limit` (mặc định 50) và bộ lọc
  `query` tùy chọn để admin so sánh bản ghi và chọn canonical entity.
- `POST /api/admin/knowledge-graph/place-dedupe/review/{groupId}/merge`:
  nhận `{ "canonicalEntityId": "..." }`, yêu cầu JWT role `admin` và CSRF.
  Hệ thống gộp mềm các entity còn lại về canonical, giữ alias và đánh dấu
  `merged_into_entity_id`; không xóa entity gốc. Response chỉ trả quyết định
  vừa xử lý thay vì tải lại toàn bộ hàng chờ.
- `POST /api/admin/knowledge-graph/place-dedupe/review/{groupId}/dismiss`:
  yêu cầu JWT role `admin` và CSRF, ghi nhận quyết định không merge bằng cách
  lưu quyết định vào Knowledge Graph, bỏ nhóm khỏi hàng chờ hiện tại và trả
  quyết định vừa xử lý. GET và script regenerate tự loại các nhóm đã merge hoặc
  đã có quyết định này khỏi `needs_review.json`.

## Contract mục tiêu: Marketplace

- `POST /api/creator/listings`: tạo listing draft từ một plan version đã kiểm tra.
- `POST /api/creator/listings/{listingId}/submit`: gửi kiểm duyệt.
- `POST /api/creator/listings/{listingId}/publish`: publish version bất biến.
- `GET /api/listings`: tìm kiếm, lọc và phân trang listing.
- `GET /api/listings/{listingId}`: trả preview theo quyền hiện tại.
- `POST /api/checkout-sessions`: tạo checkout cho listing version cụ thể.
- `POST /api/payments/webhooks/{provider}`: nhận và xác minh payment event.
- `GET /api/orders/{orderId}`: lấy trạng thái order/entitlement.
- `POST /api/orders/{orderId}/copy`: tạo TripPlan cá nhân từ version đã mua.
- `POST /api/listings/{listingId}/reviews`: review từ buyer đủ điều kiện.
- `POST /api/listings/{listingId}/reports`: báo cáo listing/version.
- `GET /api/me/plans`: lấy thư viện các plan đã mua của buyer kèm `copiedPlanId` và trạng thái entitlement (`active` / `revoked`).
- `POST /api/admin/creator-applications/{id}/approve`: admin duyệt creator application.
- `POST /api/admin/listings/{versionId}/review`: admin duyệt/từ chối phiên bản listing (`decision`: `approve` | `reject`).
- `POST /api/admin/reports/{reportId}/resolve`: admin xử lý báo cáo vi phạm (`decision`: `unpublish` | `dismiss`).
- `POST /api/admin/orders/{orderId}/refund`: admin hoàn tiền đơn hàng, thu hồi quyền (`revoked`) nhưng bảo toàn bản sao `copiedPlanId`.
- `GET /api/admin/audit-events`: tra cứu nhật ký kiểm toán quản trị viên (có ẩn dữ liệu nhạy cảm).

Checkout request phải khóa version và số tiền phía server:

```json
{
  "listingId": "listing_...",
  "listingVersionId": "listing_version_...",
  "returnUrl": "https://app.example.com/orders/order_..."
}
```

Client không được quyết định `amount`, `currency`, plan version hoặc entitlement.
Sau payment, bản sao cá nhân phải giữ `sourceListingVersionId` và
`sourcePlanVersionId`, nhưng có lifecycle/version riêng để Planner chỉnh sửa.
