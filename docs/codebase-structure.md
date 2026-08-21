# Cấu trúc codebase hiện tại

Cập nhật lần cuối: 2026-08-21.

## Các ứng dụng cấp cao nhất

- `backend/`: backend FastAPI/LangGraph hiện tại.
- `frontend/`: giao diện Next.js cho người dùng.
- `admin-frontend/`: giao diện Next.js riêng cho quản trị viên.
- `packages/`: các package frontend dùng chung trong npm workspace; hiện có
  `api-client/` cho API error và request helper dùng chung.
- `docker-compose.yml`: cấu hình backend và routing services, không provision
  PostgreSQL. Backend dùng database local ngoài Compose hoặc database cloud qua
  `DATABASE_URL`; container dùng `host.docker.internal` để truy cập DB trên host.

## Cấu trúc backend

```text
backend/
├── pyproject.toml
├── requirements.txt  # snapshot pin đầy đủ của backend/.venv
├── Dockerfile
├── langgraph.json
├── src/app/
│   ├── main.py
│   ├── bootstrap.py
│   ├── api/
│   ├── core/
│   ├── orchestration/
│   ├── shared/
│   │   ├── contracts/
│   │   ├── persistence/
│   │   ├── llm/
│   │   └── tools/       # search, rating, daily/transport cost dùng chung
│   └── modules/
│       ├── supervisor/
│       ├── explorer/
│       ├── information_finder/
│       ├── place_checker/
│       ├── itinerary_planner/
│       ├── finisher/
│       ├── plan_editor/
│       ├── auth/
│       ├── conversation_memory/
│       ├── knowledge_graph/
│       └── observability/
└── tests/
```

`src/app/main.py` khởi tạo ứng dụng FastAPI. Thư mục `api/` định nghĩa ranh
giới HTTP. Thư mục `orchestration/` sở hữu root graph và ánh xạ các public
contract giữa các module. Business rule về du lịch không nên đặt trong
`orchestration/`.

`itinerary_planner` ưu tiên graph Beam Search trong runtime Valhalla và giữ
graph hybrid CP-SAT làm fallback khi Beam không tạo được itinerary hợp lệ.
Beam và fallback dùng chung `PreparedPlanningProblem` cùng global Valhalla
matrix trong một graph, nên fallback không chạy lại preprocessing/routing.
Valhalla adapter có bounded directed-pair cache theo graph version/profile và
chỉ gọi provider cho các pair còn thiếu khi cache overlap đủ lớn; cache này
không thay đổi database ownership.
Capability `itinerary_planner/day_repair/` xử lý riêng thao tác người dùng thay
địa điểm: tất cả stop của ngày là bắt buộc, các ngày khác không tham gia solve.
Fast path dồn lại timeline nhưng giữ nguyên thứ tự; nếu không khả thi, CP-SAT
chỉ được đổi thứ tự và giờ của đúng tập stop đó theo opening window, meal window,
Valhalla safe travel và transfer nơi lưu trú.
Beam chỉ cấm lặp `TravelPlace`; food và leisure được phép lặp khi cần, nhưng
thứ tự xếp hạng ưu tiên ít lặp hơn theo `Entertainment -> DrinkDessert ->
Restaurant`.

Module `observability` lưu bounded trace cục bộ và phát timing log an toàn cho
từng root graph stage cùng tổng request. Các dòng này dùng cùng `request_id` để
đối chiếu với trace mà không ghi nội dung prompt hoặc raw provider payload.

Knowledge Graph và Place Checker tách pool `Entertainment` khỏi `TravelPlace`.
`Entertainment` là node place-like cho các địa điểm giải trí/wellness; mapping
runtime dùng hint riêng và không đưa loại này vào hint tổng quát `travel place`.
Generic discovery còn bỏ qua entity có property
`generic_discovery_excluded=true`, trong khi named-place lookup vẫn cho phép
resolve entity đó khi user gọi đúng tên; night market tiếp tục là `TravelPlace`.
Candidate generation xếp top-K bằng Bayesian adjusted rating và review
reliability trước khi CandidateScoring chạy; downstream activity, food và
entertainment cũng dùng shared Bayesian policy. Category inference kiểm tra
Unicode gốc để phân biệt món `Phở` với từ `Phố` trong tên đường.

## Ranh giới module

Mỗi module dọc có cấu trúc sau:

```text
modules/<module>/
├── public.py       # API import được module khác hỗ trợ
├── contract.py     # Pydantic contract công khai
├── state.py        # graph state nội bộ
├── graph.py        # factory tạo subgraph
├── nodes.py        # node LangGraph mỏng
├── service.py      # business logic xác định được
├── ports.py        # interface cho provider nếu cần
├── adapters/       # implementation provider cụ thể nếu cần
└── tests/          # test riêng của module
```

Module khác chỉ nên import thông qua `public.py`, không truy cập trực tiếp
state, node hoặc service nội bộ. Provider bên ngoài phải được đặt sau port và
adapter.

Khi một vertical module đủ lớn, implementation có thể được nhóm thêm theo
capability mà không thay đổi public boundary. `place_checker` giữ contract,
graph, pipeline, port và output boundary tại root; phần triển khai được chia vào
`analysis/`, `evaluation/`, `resolution/`, `retrieval/`, `scoring/`,
`selection/` và `planning/`. Nhánh chọn nhà hàng nằm trong
`selection/food/`. Các package con này là nội bộ và module khác không được
import trực tiếp.

Module `conversation_memory` đã hoàn thành Phase 01–06. Module sở hữu public contract (`contract.py`), interfaces (`ports.py`), PostgreSQL asyncpg adapter (`adapters/postgres.py`), migration `009_conversation_memory.sql`, user-preference APIs, bounded rolling summary (`summary.py`), rule-based extractor (`extractor.py`), merge policy evaluator (`merge_policy.py`) và `ConversationMemoryService` (`service.py`). Reference resolution dùng hybrid Gemini + deterministic fallback: LLM hiểu tham chiếu theo transcript/memory, nhưng mọi fact ID đều được kiểm tra trước khi sử dụng. FastAPI runtime mặc định tắt root-graph checkpoint để không mở thêm connection trên cloud PostgreSQL giới hạn thấp; Conversation Memory/Trip Chat vẫn là nguồn state bền vững. Checkpointer PostgreSQL có thể bật bằng `CONVERSATION_GRAPH_CHECKPOINTER_ENABLED=true` khi database đã được cấu hình đủ connection. Trip Chat phát structured memory metrics, retry lỗi kết nối PostgreSQL tạm thời và có feature flag rollback.

`shared/contracts/source_note.py` là contract dùng chung cho source note vì
Place Checker tạo note, Itinerary Planner truyền note và Trip Chat lưu snapshot.
Place Checker tách note đã liên kết với từng địa điểm thành hai vùng: chi tiết
từ raw prompt đi vào user-owned `personalNotes`; source-owned `notes` chỉ chọn
URL trước rồi mới fallback Google Maps/Knowledge Graph. Trip Chat chỉ mutation
trường `personalNotes` do người dùng sở hữu.

Module `finisher` nhận duy nhất `ItineraryPlannerOutput` đã chuẩn hóa, xếp note
URL trước các loại note khác và tạo phản hồi ngắn bằng tiếng Việt cho
`InvokeResponse.response`. Runtime dùng Gemini structured output khi có API key;
lỗi provider hoặc môi trường không cấu hình key dùng câu tiếng Việt
deterministic. Finisher không nhận raw prompt hay raw payload của provider.
Module `plan_editor` vẫn giữ graph legacy cho `Itinerary`, đồng thời expose
Natural Language Plan Editor dùng Gemini structured output trên compact view của
`currentPlannerOutput`. Trip Chat gọi capability này trước root graph, kiểm tra
day/item ID do Gemini trả về rồi dispatch sang chính các service thêm, sửa, xóa
và sắp xếp đang phục vụ UI thủ công. Module không có keyword classifier hoặc
deterministic edit fallback; message không phải edit tiếp tục qua root graph.
Trip Chat cũng sở hữu mutation accommodation trong planner snapshot: frontend
có thể sửa địa điểm lưu trú, lưu ghi chú cá nhân hoặc xóa nơi lưu trú; adapter
in-memory và PostgreSQL cùng kiểm tra revision trước khi cập nhật JSONB.


FinalItineraryPlanner đã bỏ scaffold round-robin/estimated routing. Graph của
module hiện chạy Phase 2 `prepare_problem` rồi Phase 3 global Valhalla matrix
được ghép từ các provider batch tối đa 2.500 source-target pairs,
fallback đường chim bay khi Valhalla unavailable, và
sparse arcs trên contract `trip + places + food + entertainment + accommodations + excludedCandidates`, sau đó chạy Phase 4 OR-Tools
hybrid planner gồm geographic day-domain, greedy shortlist, 2-opt/swap và
CP-SAT hai pass theo từng ngày: pass priority exact giữ thứ tự
`user_input > URL`, sau đó pass utility tối ưu chất lượng lịch.
PlaceChecker xếp tối đa ba accommodation quanh percentile ngân sách theo khoảng
cách tới tâm compact TravelPlace pool. Hybrid dùng candidate rẻ nhất làm anchor
khi có budget target, nếu không dùng candidate đầu tiên; endpoint ngày phải nối
được anchor và giữ đủ 7 giờ
nghỉ. Assembly không fallback sang global CP-SAT để đổi khách sạn và trả
diagnostic gồm top `placeId`/ngày/constraint khi anchor không khả thi.
Geographic day-domain không dùng solver phụ: heuristic chọn tâm theo normalized
KNN density (`K<=10`) và Bayesian quality, greedy gán ngày gần nhất rồi
rebalance một lần. Preferred pool
giữ reserve tổng Place + Entertainment cân bằng; hard preflight chỉ yêu cầu
full feasible pool còn hai Place/ngày. Mọi ngày khả thi khác vẫn là reserve
fallback, còn candidate user/URL giữ toàn bộ ngày khả thi.
Runtime composition đặt `ITINERARY_LOG_SEARCH_PROGRESS=true` để OR-Tools phát
search progress; test graph vẫn có thể truyền `SolverConfig` tắt log để tránh
output nhiễu.
Composition root inject Valhalla từ cấu hình cùng Xanh SM fare estimator;
fallback đường chim bay được gắn tại provider boundary và luôn phát warning.
Fare estimator thuộc `shared/tools/transport_cost.py` để city-cost estimation
và Planner dùng cùng một policy/version thay vì sở hữu hai bảng giá.
PlaceChecker dựng ngân sách ước lượng từ các candidate đã query trong cây ADM:
P25/P50/P80 tương ứng low/medium/high cho Accommodation, Restaurant và
TravelPlace. Transportation dùng cùng Xanh SM fare estimator cho các ADM Việt
Nam. Thiếu giá ở một nhóm bắt buộc thì giữ budget `unspecified`, không tạo số
tiền giả.
Phase 5 lấy detail cho selected arcs và accommodation transfers, thử repair có
timeline reflow trước khi duration thực tế phá lịch nhưng selection/order vẫn
có thể giữ nguyên. Nếu reflow không thỏa hard constraints, Planner thử day locks;
nếu repair `INFEASIBLE` hoặc `UNKNOWN`, Planner dùng baseline hint rồi
hybrid-replan compact pool theo ngày để thay/drop optional candidate. Route
detail được cache trong request. Mọi route detail gây overlap đều kích hoạt
correction/repair, kể cả chênh 1-2 phút; tolerance chỉ phân loại sai lệch khi
schedule slack vẫn giữ timeline hợp lệ. Repair tiếp tục khi có travel-time
correction mới cho đến khi timeline ổn định, không dùng wall-clock timeout mặc
định, rồi tạo public
`ItineraryPlannerOutput`, gồm cả `people` đã dùng để tính giá/người. Root/API trả nó
qua `plannerOutput`; legacy `itinerary` được giữ riêng cho PlanEditor. Root
orchestration không còn tạo lịch giả từ `VerifiedPlace` legacy.
Mỗi itinerary day có `costBreakdown` gồm accommodation, food, localTransport,
activities, misc và total trên một người. Planner điền giá stop, route và
Accommodation là top candidate trong tối đa ba phương án có giá và tọa độ do
PlaceChecker gửi; misc giữ 0 khi chưa có dữ liệu thật.
Mỗi ordered route leg trong `plannerOutput` cũng công bố `costPerPerson` để UI
quy đổi và hiển thị tổng giá xe của cả nhóm theo chặng; giá/người trong contract
vẫn là cùng estimate đã được cộng vào `localTransport`, không phải một phép tính
lại ở frontend. Route legacy chỉ có khoảng cách dùng fallback đã là giá cả xe
nên không nhân thêm theo số khách.
Khi intake chưa có số phòng, accommodation tạm suy ra một phòng cho mỗi hai
khách rồi chia lại thành giá/người/đêm; tổng số đêm là `days - 1`. Ngày còn
thuê phòng kết thúc ở accommodation và ngày tiếp theo bắt đầu tại đó. Transfer
trên 50 km bị phạt để ưu tiên đổi sang phương án gần hơn; transfer thiếu route
shape được giữ bằng matrix duration và phát warning rõ ràng.
Nếu Explorer không có số tiền cụ thể, PlaceChecker truyền tổng estimate/người
cho cả chuyến cùng daily breakdown và profile version. Số người dùng nhập luôn
được ưu tiên; estimate là soft target trong Planner.
TripChat lưu hai snapshot độc lập: `currentItinerary` cho PlanEditor legacy và
`currentPlannerOutput` cho frontend hiển thị output mới. Frontend map
`days[].stops` thành item và `days[].legs` thành transport leg; guest planner
cũng gọi trực tiếp `POST /v1/agent/invoke` thay vì adapter plan legacy.
`currentPlannerOutput.people` giữ quy mô nhóm xuyên suốt lúc lưu/tải lại; nếu
người dùng không nêu số khách, Explorer mặc định hai người, còn số được nêu rõ
luôn ghi đè mặc định này.
Thẻ ngân sách cộng `days[].costBreakdown` và hiển thị bốn nhóm riêng:
TravelPlace, Restaurant/ăn uống, Accommodation và transportation; trên màn
hình hẹp bốn nhóm tự xuống lưới hai cột. Tổng dự kiến và từng nhóm đều hiển thị
theo người; thẻ đồng thời hiển thị `budgetPerPerson` đã được PlaceChecker chuẩn
hóa hoặc ước tính để người dùng so sánh với chi phí của itinerary.
Frontend chỉ hiển thị đi bộ cho chặng ngắn hơn 1,5 km. Với chặng có nhiều
phương án hợp lệ, thao tác chọn option gọi Trip Chat mutation; backend lưu
`selectedTransport` vào đúng leg trong `currentPlannerOutput` với optimistic
revision để lựa chọn còn nguyên sau khi tải lại.
Các thao tác thêm, xóa và kéo thả ở frontend diff chuỗi địa điểm theo từng cặp
liền kề, giữ route leg không đổi và chỉ gọi `POST /v1/plans/day-directions` cho
leg mới. Riêng khi sửa sang một identity/tọa độ khác, frontend gọi day-repair
backend; backend ghi nguyên tử stop, timeline và toàn bộ leg của ngày sau khi
repair thành công. Cả hai flow đều không gọi Supervisor hoặc agent lập lịch.
Lệnh chỉnh lịch qua chat cũng tái sử dụng cùng các mutation này và optimistic
revision; Gemini chỉ chuyển ngôn ngữ tự nhiên thành action có cấu trúc, không tự
ghi PostgreSQL hoặc tự thay JSON snapshot.
Địa điểm URL/direct input được Place Checker tự chọn một canonical candidate tốt
nhất trước khi tạo Planner input; `addressHint` được ưu tiên nếu có. Frontend
không còn resolve identity bằng Top-K hoặc chèn match trực tiếp qua Trip Chat
mutation. `unscheduled` chỉ còn phản ánh candidate không xếp được do preflight,
giờ mở cửa, route hoặc constraint của Planner; menu vẫn cho phép bỏ entry.
Danh sách TripChat chỉ map contract summary và giữ `hasItinerary`; sau một
message, frontend áp dụng trực tiếp full chat snapshot vừa nhận để chuyển sang
itinerary mà không phụ thuộc vào một lượt GET đồng bộ thứ hai. Output không có
ngày hoặc có ngày không chứa stop không được coi là `TravelPlan` hợp lệ.

## Ranh giới API hiện tại

Backend hiện chỉ expose:

- `GET /health`
- `POST /v1/agent/invoke`
- `GET/POST/DELETE /v1/trip-chats` và các endpoint message theo chat có auth
- `GET /v1/plans/places/search` tìm địa điểm chuẩn hóa trong Knowledge Graph cho thao tác thêm thủ công
- `POST /v1/trip-chats/{chatId}/plan/days/{day}/items/{itemId}/replace` thay
  địa điểm và repair nguyên tử đúng một ngày
- `GET /v1/trip-chats/bootstrap` trả tối đa 30 summary gần nhất cùng full chat
  đang mở để frontend không phải tải danh sách rồi mới tải chi tiết tuần tự

Endpoint agent nhận thread id, prompt tùy chọn, tối đa 20 URL, tối đa 20 ảnh,
`forceRefresh` tùy chọn, itinerary hiện có và edit operation tùy chọn. Mỗi
request phải có ít nhất một trong prompt, URL hoặc ảnh; riêng request có URL
phải kèm prompt không rỗng để xác định lập lịch hay tóm tắt. Frontend hiển thị
hai action tương ứng sau khi dán URL; click chỉ điền composer, không tự gửi, nên
user vẫn có thể bổ sung yêu cầu. Ảnh JSON có thể mang `ocrText`; adapter OCR cho
dữ liệu `dataBase64` thô dùng shared Gemini client khi có key.

Explorer là LangGraph subgraph có hai route. Prompt-only trích xuất draft trực
tiếp. Source-import chạy URL và ảnh song song, đánh giá coverage trước khi tổng
hợp, rồi hai route hội tụ tại normalize, reconcile ADM và policy mặc định.
Khi source-import có raw prompt, prompt draft nhẹ và source synthesis chạy song
song rồi merge theo precedence để không làm mất tín hiệu rõ từ người dùng.
Prompt draft Gemini đọc `auto-attach/tags-auto.yml` ở từng request, nhận toàn bộ
taxonomy trong system prompt và chỉ được trả exact key qua JSON Schema enum cho
`shortPreferences`/`shortAvoids`; service kiểm tra lại output. Nhánh
deterministic resolve tín hiệu qua cùng file trong bước normalize, vì vậy cả
draft cache cũ cũng tuân theo taxonomy mới mà không cần restart.
Docker Compose mount toàn bộ `auto-attach/` read-only tại `/auto-attach` và đặt
rõ `EXPLORER_TAGS_AUTO_PATH=/auto-attach/tags-auto.yml` cùng
`EXPLORER_INSIGHT_USER_PATH=/auto-attach/insight-user.yml`; hai catalog đọc lại
file tại runtime nên chỉnh taxonomy/insight không cần build lại image.
Explorer giữ toàn bộ preference explicit theo thứ tự rồi bổ sung toàn bộ
`priority-tags` của các nhóm insight đang áp dụng; không lấy mẫu ngẫu nhiên và
không giới hạn bốn tag. Trước khi tạo `ExplorerOutput`, preference/avoid được
lọc theo giao của các tag khai báo trong `insight-user.yml` và key hiện có trong
`tags-auto.yml`, nên tag ngoài hai nguồn cấu hình không được chuyển tới
Supervisor hoặc module downstream.
Success, clarification và failure lưu ba loại snapshot riêng; repository mặc
định vẫn là in-memory. Mỗi source tạo `SourceArtifact` nội bộ có loại evidence,
URL, time hint và thời điểm quan sát trước khi Gemini tổng hợp output. YouTube
ưu tiên đúng một track subtitle/automatic caption (`vi` rồi `en`) bằng
`yt-dlp --skip-download`, giữ toàn bộ timeline mà không tải video. Trước khi tải
media, structured preflight đếm destination/place/travel detail trong transcript,
title, description, location và tags; policy local yêu cầu confidence tối thiểu,
semantic anchor và evidence hữu ích. Prompt yêu cầu đầy đủ/tất cả hoặc lỗi
preflight luôn fallback. Metadata-only đủ coverage được dùng trực tiếp. Nếu
primary thiếu, adapter tải audio stream, chia mặc định thành chunk 5 phút có
overlap 5 giây và transcribe song song qua Gemini; transcript vẫn thiếu mới tải
video để chạy riêng frame OCR, không STT lặp. Media tạm bị xóa sau request.
Timestamp `t=`/`start=` chỉ ưu tiên chunk gần mốc đó vào hàng đợi trước; toàn bộ
caption/audio vẫn được xử lý.
TikTok ưu tiên `curl-cffi` Safari đọc JSON
`__UNIVERSAL_DATA_FOR_REHYDRATION__` và đánh giá description/metadata trước;
chỉ khi coverage thiếu mới lấy URL CDN thuộc allowlist và stream MP4 với giới
hạn dung lượng. Lỗi HTML/media được trả cục bộ và không fallback sang `yt-dlp`.
Instagram áp dụng cùng gate trên metadata rồi mới dùng chuỗi tải `yt-dlp`
legacy. Không cần chuyển cookie từ frontend. OCR
lấy một frame mỗi 3 giây, giới hạn 48 frame và tối đa 10 ảnh trong mỗi batch
Gemini. Audio social dùng chunk động dài khoảng 60 giây và không vượt quá ba
chunk, nên clip ngắn chỉ tạo một STT request. Hai nhánh OCR/STT chạy đồng thời;
ffprobe bỏ qua OCR hoặc STT khi media không có video hoặc audio stream tương ứng.
Lỗi từng nhánh được giữ trong kết
quả source partial, ghi log theo code và đưa vào warning mà không làm mất
evidence của nhánh còn lại. Website dùng `curl-cffi` giả lập Safari để tải
HTML, fallback Playwright Chromium khi bị chặn hoặc nội dung rỗng, rồi dùng
`trafilatura` tạo Markdown. Nếu browser vẫn bị anti-bot
chặn, source thất bại cục bộ mà không làm hỏng source khác. Instagram có thể yêu
cầu cookie Netscape qua `EXPLORER_YTDLP_COOKIE_FILE`.

Mỗi source có wall-clock budget toàn extraction (mặc định 90 giây), không chỉ
socket timeout. Source synthesis có budget 105 giây và từng batch chunk có
budget 60 giây; chunk đã hoàn thành được giữ lại, chunk còn treo bị hủy. Hàng
đợi chunk chạy round-robin theo source để video dài không làm website hoặc clip
ngắn bị starvation. Khi semantic provider chậm hoặc partial, adapter
deterministic chỉ bổ sung các place nằm trong tiêu đề Markdown cấp hai được đánh
số; body prose, transcript và danh sách cấp thấp như khách sạn/món ăn không được
tự động nâng thành TravelPlace. Các budget cấu hình qua
`EXPLORER_SOURCE_EXTRACTION_TIMEOUT_SECONDS`,
`EXPLORER_SOURCE_SYNTHESIS_TIMEOUT_SECONDS` và
`EXPLORER_SOURCE_CHUNK_TIMEOUT_SECONDS`.

Trước khi tải URL, Explorer tra cache PostgreSQL do module sở hữu trong bảng
`source_documents`, theo canonical URL, extractor version và TTL
`EXPLORER_URL_CACHE_TTL_SECONDS` (mặc định 7 ngày). Cache đọc được artifact
legacy v6; TikTok/Instagram/Facebook bỏ toàn bộ query khi tạo cache key để URL
được chia sẻ từ frontend vẫn khớp cùng video. Adapter ghi contract chuẩn hóa
version 9 cùng metadata coverage transcript; vẫn đọc version 6/8 và không lưu raw
third-party payload. `forceRefresh=true` bỏ qua cache lookup và cập nhật record
sau extraction. Lỗi đọc/ghi cache chỉ được log và không chặn extractor. Khi
không có `DATABASE_URL`, development/test dùng cache in-memory theo process.
OCR ảnh base64 còn có LRU cache in-memory giới hạn 256 entry theo SHA-256 của
MIME type và bytes ảnh; cache không lưu raw ảnh và `forceRefresh=true` buộc OCR
lại.
Sau source extraction, Explorer cache `ExplorerDraft` đã tổng hợp trong bảng
`explorer_draft_cache`, keyed bằng prompt, evidence chuẩn hóa, namespace/model
và policy version. `EXPLORER_DRAFT_CACHE_TTL_SECONDS` mặc định 7 ngày;
`forceRefresh=true` bỏ qua và thay thế cả source cache lẫn draft cache.

Trong module Explorer, trách nhiệm được tách theo đúng lớp LangGraph:

- `graph.py` chỉ khai báo node, conditional edge và điểm hội tụ; factory nhận
  `ExplorerService` đã được inject, không khởi tạo adapter;
- `state.py` là `TypedDict` nội bộ, trong đó chỉ input ban đầu là bắt buộc;
- `nodes.py` là các hàm async mỏng: đọc/ghi state và gọi service;
- `service.py` sở hữu normalize, source-success gate, retry/error policy, precedence,
  completion gate và persistence policy;
- `intake_patch.py` định nghĩa operation set/add/remove/... và reducer cập nhật
  `ExplorerOutput` trước handoff; Supervisor chỉ phát structured patch;
- `ports.py` định nghĩa draft/source/cache/media/snapshot capability;
- `adapters/` triển khai provider cụ thể; composition mặc định chỉ diễn ra tại
  public boundary trong `public.py`.

Luồng compile hiện tại là `prepare_intake`, conditional edge sang prompt-only
hoặc source-import, rồi hội tụ tại `normalize_and_validate`,
`reconcile_input_adm`, `apply_defaults_and_precedence`, `completion_gate` và
snapshot kết quả tương ứng. Source-import chỉ gọi synthesis nếu batch coverage
còn evidence dùng được; mỗi source chỉ retry tối đa một lần.

Explorer chỉ trích xuất và giữ provenance, không resolve place. Sau Explorer,
root luôn chạy đúng một `ExplorerHandoffProjector`; không còn gate theo status
`ready`/`partial` hoặc `input_ADM`. Projector ưu tiên dữ liệu rõ của turn hiện
tại, dùng Conversation Memory để lấp context còn thiếu, merge place một lần,
resolve preferences/avoids theo `auto-attach/tags-auto.yml`, validate lại
canonical `ExplorerOutput`, lồng note vào source tương ứng, bỏ place tags,
confidence và provenance nội bộ rồi tạo `PlaceCheckerInput`. Budget tại boundary
luôn là tổng toàn chuyến cho một người. Final dedupe chạy sau memory merge, giữ
display name đầu tiên và gộp source evidence của mọi bản trùng. Thiếu destination
thành failure `blocked` có
cấu trúc; Explorer/provider/exception runtime thành `error` có code và cờ
retryable phù hợp. Chỉ PlaceChecker success/conditional/partial mới sang Planner.
Explorer output mang `days`, `startDate` và `timezone`; mặc định duration là 3
ngày và ngày bắt đầu là ngày mai khi prompt không chỉ định. Shared `TripIntent`
cũng dùng mặc định 3 ngày để các luồng legacy không âm thầm quay về plan 1 ngày.
Khi turn mới có URL/ảnh/địa điểm hoặc item mới mà không ghi số ngày, root giữ
default 3 ngày thay vì kế thừa duration cũ; chỉ follow-up thuần tham chiếu lịch
cũ mới dùng duration từ Conversation Memory.
Khi một nguồn có destination chính cùng một điểm day-trip, Explorer ưu tiên
`input_adm` nếu evidence của destination chính mạnh hơn; chỉ yêu cầu làm rõ khi
nhiều destination mạnh ngang nhau hoặc không xác định được destination chính.
Nếu confidence bằng nhau, số mention độc lập được dùng làm tie-break; evidence
trùng hệt nhau không được tính lặp.

Với rich PlaceChecker pipeline, root giữ `PlaceCheckerResult` cho diagnostic,
đồng thời dùng compact builder tạo `trip + places + food` và validate bằng
`ItineraryPlannerInput`. Payload nằm trong state `planner_input`; Planner runtime
tiêu thụ payload qua preprocessing, routing matrix, hybrid daily repair, route enrichment và
finalization.
Compact builder giữ TravelPlace thiếu giá và gửi `0 VND`; food, entertainment
và accommodation vẫn cần giá dùng được. `typical_cost` được lấy từ trung bình
khoảng min/max, một đầu mút có sẵn, `0` cho tier `free`, hoặc `0` theo mặc định
TravelPlace tại boundary sang Planner.
Khi policy đa tín hiệu đã xếp một candidate vào food pool, projector luôn phát
`venueType=restaurant`; category provider tổng quát như `travel_place` không
được phép rò sang contract food hẹp và gây lỗi validation.
Ngược lại, restaurant label sai cho public-space có marker tổng quát như
`phố đi bộ`/`walking street` được trả về TravelPlace trước khi dựng meal pool.
Internal `places[].sourcePlaces` vẫn phân biệt nguồn `input`, `url` và `system`.
Public handoff rút gọn thành `evidenceType=raw_prompt|url`; `sourceTimeHint` và
`addressHint` được giữ, còn `origin`, `evidence`, `observedAt`, confidence và
place tags không đi qua PlaceChecker boundary.
`place_checker/handoff_adapter.py` chuyển contract compact này sang evidence
model giàu dùng nội bộ; scoring/audit của PlaceChecker không phụ thuộc vào JSON
metadata đã bị loại ở boundary.
Draft generator nằm sau port; prompt-only và source-import có provider cấu hình
riêng. Source-import chia từng source/artifact dài thành chunk khoảng 20.000 ký
tự; mỗi chunk gọi một structured Gemini request trả đồng thời place, ADM và
note. Mặc định năm chunk chạy song song, còn limiter dùng chung của Explorer giữ
tối đa sáu synthesis request đang chạy. Chunk thành công được giữ
khi chunk khác lỗi. Consolidation exact chạy deterministic trước; Gemini chỉ
được gọi khi còn ít nhất hai place khác tên để merge alias/dịch thuật và lọc
mention không phải place.
Chunk structured-output lỗi lặp lại được chia đôi tối đa hai cấp; quota/cooldown
được retry có chờ. Explorer giữ warning/source status nội bộ nhưng không phát
aggregate coverage trong `ExplorerOutput`.
Khi có source và Gemini key, structured Gemini synthesis lọc `urlNotes` chỉ giữ
chi tiết hữu ích có evidence như access/timing/price/caution, hoạt động cụ thể,
trải nghiệm đặc trưng hoặc fun fact; lời quảng cáo chung chung bị loại. Shared Gemini client xoay key
cho các lời gọi song song. Source synthesis dùng `GEMINI_MODEL`, frame/ảnh OCR
dùng `GEMINI_IMAGE_OCR_MODEL`, còn STT dùng `GEMINI_AUDIO_MODEL`.

Endpoint Explorer nhận trực tiếp `ExplorerInput`, bỏ qua root Supervisor,
PlaceChecker và Planner, rồi chiếu internal `ExplorerOutput` thành
`ExplorerApiOutput` rút gọn. Public output không có status/diagnostic nội bộ,
không có `places[].tags`, chỉ giữ exact taxonomy key trong `shortPreferences`
và `shortAvoids`, đồng thời lồng note đã liên kết vào
`places[].sourcePlaces[].urlNotes`. Endpoint vẫn chạy cùng graph và provider
configuration với runtime.

Authentication is implemented as a vertical `auth` module. It owns the
`auth_runtime_users` and `auth_runtime_sessions` tables, uses PostgreSQL when `DATABASE_URL` is
configured, and uses an in-memory repository only for tests or development
without a database. Protected requests use a short-lived HS256 JWT access token
in `Authorization: Bearer`; refresh tokens are rotated, hashed in
`auth_runtime_sessions`. The raw refresh token is sent explicitly in the
refresh/logout request body and is never stored in the database. No auth
cookie or CSRF token is required.

Information Finder hiện có service cache-first, các port `SearchProvider`,
`SearchQueryPlanner`, `SourceRepository`, `EmbeddingProvider`, `SourceChunker`,
`AnswerGenerator`, adapter Tavily, LLM lập truy vấn tìm kiếm, Gemini URL Context
chunker, Gemini embeddings và PostgreSQL/pgvector.
Các bảng do module sở hữu có tiền tố
`information_finder_`; module không dùng bảng legacy. Khi thiếu database hoặc
API key, development/test dùng fallback trung thực trong process.

Answer generator của Information Finder có thể nhận `LlmClient` dùng chung qua
dependency injection. Prompt, structured claim contract, source budget,
citation validation, structured block rendering và fallback policy vẫn thuộc module Information Finder;
shared client chỉ sở hữu transport Gemini và key rotation. Service lấy năm nguồn
local có điểm semantic cao nhất rồi truyền cho `LlmSearchQueryPlanner`; LLM chỉ
đặt `shouldSearch=true` và tạo tối đa ba truy vấn Tavily khi các nguồn này thiếu
dữ kiện cần thiết. Nếu planner lỗi, service chỉ dùng truy vấn deterministic khi
không có nguồn local hoặc cần refresh.
Structured answer prompt (mặc định dùng provider Gemini; có thể chọn `extractive` cho development/test) yêu cầu các block semantic như `paragraph`, `factList`,
`verse`, `quote`, `recommendations`, `steps`, `comparison` và `notice`, chỉ tạo
block khi có đủ dữ kiện. Extractive fallback không tổng hợp bằng LLM; nó trả
structured facts ngắn, tối đa ba đến năm item có citation và loại các segment
quảng cáo, navigation/footer và lời dẫn SEO phổ biến trước khi render.
Answer generator trả về `entityCandidates` gồm tên hiển thị và các tên tra cứu,
bao gồm alias hoặc tên tiếng Anh khi có căn cứ. `KnowledgeGraphEntityResolver`
thử từng tên qua public Knowledge Graph contract và backend tự gắn
`travel-entity://entity/<encoded_entity_id>` trong answer legacy và tạo
`inlineSpans` có `entityId` trong content blocks sau khi node tồn tại. Entity
không resolve được giữ plain text, không bị gắn link giả. Chat preview đọc node bằng ID qua
`GET /v1/knowledge-graph/entities/{entity_id}/preview`; lookup theo tên chỉ còn
là endpoint tương thích cho các caller cũ. TripChat lưu `content` và
`content_blocks` riêng trong cùng assistant message; message cũ được đọc với
`contentBlocks=[]`.

Supervisor là intent classifier có provider cấu hình được. Khi provider là
`gemini`, mọi message được structured Gemini phân loại trước qua `shared/llm/`;
route `finish` có thể kèm phản hồi ngắn cùng ngôn ngữ cho greeting, câu hỏi về
trợ lý hoặc yêu cầu ngoài phạm vi. Rule deterministic chỉ là provider offline
hoặc runtime fallback. Supervisor hiện được cấu hình
`SUPERVISOR_CLASSIFIER_PROVIDER=gemini`; provider này yêu cầu `GEMINI_API_KEY`.
Routing baseline chưa được production-evaluated. Trip Chat truyền tối đa sáu
message trước đó với tiền tố `User:` hoặc `Assistant:`; root graph giữ nguyên
role và không lặp message hiện tại trong context của Supervisor. Durable memory
được truyền riêng dưới dạng structured state và rolling summary.
Supervisor ưu tiên intent rõ trong message hiện tại. Với câu nối lược bỏ intent,
Supervisor đọc các lượt có role gần nhất: tiếp tục hỏi đáp/khám phá thì đi
`information_finder`, tiếp tục phiên đang thu thập ràng buộc để tạo plan thì đi
`explorer`, còn context không đủ rõ thì hỏi lại.
Riêng planning intake đang chờ Explorer review không dựa vào transcript hoặc
Conversation Memory: root state giữ `pending_explorer_review` và
`pending_explorer_output`. Explorer thiếu destination trả `missing_fields` về
Supervisor. Sau khi destination được bổ sung, Explorer vẫn chạy default policy,
tính budget bằng shared estimator, enrich preferences bằng `insight-user.yml`
và trả `defaults_proposed`. Supervisor chuyển reply thành `TripContextPatch`;
Explorer áp patch rồi mới đi PlaceChecker, không hỏi xác nhận lần hai.
`shortAvoids` suy ra từ insight chỉ nằm trong pending output và handoff nội bộ,
không nằm trong JSON review gửi Supervisor.
Với nguồn URL, action lập lịch chạy extraction rồi đi qua cùng review gate này.
Action tóm tắt chạy Explorer extraction, để Supervisor dựng câu trả lời từ
output chuẩn hóa, rồi kết thúc mà không gọi PlaceChecker hoặc Planner.
Itinerary Planner subgraph không kế thừa root checkpointer vì state tính toán
tạm thời chứa dataclass và immutable mappings; root chỉ checkpoint public input,
output và conversation state sau khi subgraph hoàn tất.

`shared/llm/` cung cấp port và Gemini REST adapter dùng chung, bao gồm tùy chọn
URL Context tool cho module cần Gemini đọc URL public. `GEMINI_API_KEY`
là một chuỗi chứa nhiều key phân tách bằng dấu phẩy. Text, OCR và audio client
dùng chung key pool với tối đa một request đang chạy trên mỗi key; mỗi request
chỉ thử tối đa ba key. Adapter vô hiệu hóa key bị từ chối, đọc `Retry-After`
cho lỗi 429, thêm jitter và cooldown lỗi có thể thử lại. Các agent hiện có chưa
được chuyển business behavior sang LLM ngoài Supervisor và Information Finder
theo cấu hình của từng module.

`shared/tools/search_places/` cung cấp engine async dùng chung để module gọi
qua dependency injection. Tool chuẩn hóa query, xếp hạng top-K, áp ngưỡng
identity/margin, chặn ADM/type/toạ độ không hợp lệ, giữ kết quả nhập nhằng để
review và điều phối external theo caller policy. PlaceChecker named-place dùng
một SQL identity riêng để search name/alias/address trong ADM trên cả
TravelPlace, Restaurant, DrinkDessert, Entertainment và Accommodation, lấy
top-1; chỉ zero row mới gọi Google Maps. Optional discovery tạo tối đa một SQL
cho mỗi deficient pool và không cấu hình external source. Generic pool query
dùng `Special_Experience`, direct tags, `Offer_Item`, metadata và rating/review
làm signal trong cùng result set. `Has_Style` chỉ kế thừa
`time_duration`/`time_windows` còn thiếu, không tạo tag hoặc discovery.
Compact PlaceChecker-to-Planner contract giữ `sourceKind`, ActivityItem IDs và
timing source. URL ảnh từ các property ảnh của place trong Knowledge Graph được
chuẩn hóa thành `imageUrls`, giữ qua Itinerary Planner output và được frontend
dùng cho ảnh thẻ lịch trình. Planner phân period theo giờ stop thực tế, áp largest-remainder
70/30 cho morning và 60/40 cho evening bằng soft source-mix penalty, đồng thời
trả target/actual/fallback audit. Bayesian review quality tiếp tục xếp hạng độ
nổi tiếng trong objective sau các hard feasibility constraints.
Planner cấm food-to-food arc để mỗi cặp bữa liên tiếp có ít nhất một activity,
giới hạn tối đa hai `drink_dessert` mỗi ngày kể cả khi loại này nằm trong
`places`, và không cho hai meal slot legacy liền nhau cùng dùng loại venue này.
Hybrid projection áp biên mềm 5%, trừ tổng chi phí accommodation anchor khỏi
cả budget `explicit` và `estimated_daily_cost` rồi chia phần còn lại theo ngày,
nên budget penalty tác
động ngay lúc chọn food/place thay vì chỉ cảnh báo sau khi ghép lịch.
Budget-aware shortlist mở toàn bộ candidate khả thi trong ngày, trừ access cost
hai chiều từ accommodation và rank food theo `price + corridor transport cost`;
geographic preferred day không còn ép chuyến tiết kiệm vào cụm xa.
Nightlife/night-market bắt đầu từ 18:00; Weekend Night Market chỉ nhận
Thứ Sáu-Chủ Nhật. Hybrid shortlist giữ history nhóm trải nghiệm của các ngày đã
chọn, ưu tiên nhóm mới nhưng cho chọn lại nhóm cũ khi alternative cạn. Food
contract giữ `venueType` rõ ràng. Waiting
giữa hai stop bị hard-cap 150 phút ngoài safe-travel buffer; objective bắt đầu
phạt phần waiting vượt 15 phút.
Sparse-arc policy giữ meal-access theo từng ngày và hai chiều để pruning không
làm mất đường activity vào/ra meal. Graph cơ bản giữ mười neighbor gần nhất theo
safe travel time có hướng từ matrix; forced relationship/priority/bridge arcs
vẫn được bảo toàn. Mỗi daily CP-SAT repair mặc định giữ một search worker cho hai pass sau khi
benchmark local cho thấy multi-worker làm model hiện tại chậm hơn đáng kể.
Hai pass không đặt solver timeout mặc định; deployment có SLA phải inject giới
hạn qua `SolverConfig`.
Preprocessing giới hạn optional candidate vào tối đa hai ngày thuộc geographic
center gần nhất; user/URL giữ toàn bộ feasible days và food relationship đi
cùng TravelPlace. Meal coverage được repair bằng unique matching sau projection;
nếu cả pool gốc không có ba restaurant khác nhau, meal-occurrence alias nội bộ
cho phép lặp venue, còn finalization trả `placeId` thật, `itemId` riêng theo meal
và warning fallback. Pass utility dùng relative gap 5%, còn pass priority vẫn
tối ưu exact trước khi khóa riêng count
user input và URL.
PlaceChecker optional retrieval chỉ mở pool canonical đang thiếu. Quota là
12 TravelPlace/ngày, 6 Restaurant/ngày, 2 Entertainment/ngày,
3 DrinkDessert/ngày và tối đa 3 Accommodation/toàn chuyến. Entertainment tự
gợi ý phải đạt Bayesian rating điều chỉnh từ 4,2/5 và có window giao buổi tối
từ 18:00; DrinkDessert dùng window ban ngày 07:00–18:00. Hai pool được cap riêng
rồi gộp vào `entertainment[]`. Direct-user/URL bypass optional cap và giữ
provenance. Planner vẫn sở hữu source-mix, day assignment và tối ưu cuối.
Breakfast phải kết thúc trước mọi activity trong ngày.
Semantic guard chuyển music box, karaoke, golf, billiard/bi-a, bowling, studio,
game center, massage/trị liệu, spa và retail store/souvenir bị gắn TravelPlace
sai sang Entertainment trước scoring/quota/compact output. Food dùng target `6/ngày`:
Compact boundary còn dùng provider note làm semantic context để nhận art supply
store, photo booth, garden center và plant service bị gắn sai TravelPlace.
DrinkDessert/cafe/coffee/tea/bakery/dessert luôn được chuẩn hóa vào pool
Entertainment ở compact boundary, kể cả khi raw prompt/URL upstream gắn nhãn
Restaurant hoặc TravelPlace; duplicate food/place candidate cũng được chuyển pool
trước khi Planner nhận dữ liệu.
FoodItem diversity không dùng HasStyle. Food anchors là final TravelPlace và
Entertainment có tọa độ; một query trả cả nearby 5 km và city-wide candidate.
Food hard feasibility vẫn là unique matching cho từng slot
`day × breakfast/lunch/dinner`, tối đa 60 candidate. PlaceChecker còn thử một
reserve matching rời hard set và gửi cả feasibility qua `foodCoverage`.
Core query over-fetch có giới hạn để bù candidate thiếu metadata; scoring chốt
quota sau dedupe và quality gate. Travel reserve là quota mềm để tăng chất
lượng lựa chọn, không phải điều kiện chặn. PlaceChecker chỉ block khi hard meal
coverage hoặc candidate bắt buộc không hợp lệ; candidate `user_input`/`url`
được giữ nguyên qua compact boundary để FinalItineraryPlanner tự xếp lịch và
đưa phần không xếp được vào `unscheduled`. Thiếu pairing gần chỉ tạo warning;
Restaurant được đưa vào `food`, không trộn thành activity place.
Compatibility graph không database vẫn dùng `DevelopmentCatalog`. Khi có
`DATABASE_URL` và `GOOGLE_MAPS_SCRAPER_ENABLED=true`, gap retrieval chỉ gọi
`GoogleMapsPlaywrightSearch` sau khi Knowledge Graph không đủ candidate đã
xác minh. Kết quả được upsert vào Knowledge Graph với `status=pending`; property
giữ Google Maps URL, `fetch_at` và note
`provider=google_maps_playwright;verification=not_verified`. Candidate này là
provisional tới khi admin đổi entity sang `verified`; `rejected` không được đọc.
`shared/tools/bayesian_rating.py` cung cấp prior, adjusted rating, review
reliability và quality 0..1 dùng chung cho PlaceChecker và
FinalItineraryPlanner; module vẫn tự sở hữu cách đưa quality vào business score.
Candidate contract của tool giữ relationship evidence chuẩn hóa ở dạng dữ liệu
trung lập. PlaceChecker PostgreSQL adapter diễn giải `Special_Near`,
`Special_Experience`, `Offer_Item` và `Has_Style`, duyệt ADM đệ quy và chuyển
evidence có provenance sang scoring/output. Adapter không còn đọc `Near` legacy
hoặc `Must_Visit`. Timing mặc định của `Has_Style` được đọc từ properties của
node Style đích; timing riêng của place được ưu tiên.
Knowledge Graph ontology còn khai báo `SubPlace` và cạnh cấu trúc
`TravelPlace --Has_Subplace--> SubPlace`; `SubPlace --Offer_Item--> Item` nhận
bốn item type hiện có. PlaceChecker chưa duyệt nhánh nested này nên SubPlace
chưa tham gia output hoặc itinerary runtime.
Nhánh food query `FoodItem`/`DrinkItem` có `Has_Style` rồi reverse `Offer_Item`
sang Restaurant/DrinkDessert trong bán kính tọa độ 5 km quanh tối đa 8-12 anchor
đại diện. SpecialNear là evidence. Service giữ Style/Item provenance, gộp
anchor, ưu tiên Item/quán chưa dùng theo vùng,
validate metadata, rồi chạy unique meal-slot matching. Service chỉ query general
ADM một lần cho các meal type còn thiếu ở hard/reserve matching và match lại.
Logic nằm trong `place_checker/selection/food/meal_matching.py`; pool selection bắt buộc
giữ mọi Restaurant ID đã được hard hoặc reserve matching chọn.
Selector Style tổng quát resolve `shortPreferences` sang Style ID và tên
`inputItems` sang canonical Item ID trước khi query. Với Style có Item, adapter
đi `Has_Style` từ Item rồi reverse `Offer_Item` sang `TravelPlace`, `Restaurant`
hoặc `DrinkDessert`; chỉ Style không có Item mới fallback direct `Has_Style`.
Mỗi Style active có target `2 × days`. Bộ đếm Style, Item và tag chỉ tồn tại
trong request; output giữ provenance và shortfall theo từng Style.
Identity acceptance mềm dành riêng
cho URL/direct input nằm trong `place_checker/resolution/policy.py`; policy này
không áp dụng cho system/retrieval candidate.

Authentication, Marketplace, URL import chịu được mọi anti-bot, dữ liệu place
live và routing live chưa nằm trong scaffold hiện tại. Checkpointer của root
graph vẫn chưa bền vững.

## Cấu trúc style frontend

`frontend/src/app/globals.css` giữ style shell dùng chung. CSS lớn chỉ thuộc một
route như landing, profile, group, Leaflet và MapLibre được import tại page tương
ứng để không nằm trong payload của mọi route. CSS theo vùng chức năng còn lại
nằm trong `frontend/src/styles/global/`; style riêng của Planner nằm trong
`frontend/src/features/planner/styles/`. Bản đồ và các widget planner toàn cục
được tách thành dynamic chunk.

The existing planner UI remains the active entrypoint. The compatibility facade
in `frontend/src/features/planner/api/plans.ts` maps the current
`/v1/trip-chats` contract to the existing view models without changing the
planner layout. Transport contracts live in `features/planner/contracts/`;
directions, reviews and place search use capability-specific adapters in
`features/planner/api/`. Pure guided-intake policy and formatting live in
`features/planner/model/` with colocated tests. Planner không còn hiển thị thanh
metadata Điểm đến/Thời gian/Nhóm đi/Ngân sách/Lưu ý; intake người dùng cũng
không hỏi nhóm đi. Thẻ ngân sách của điểm đến so sánh tổng dự kiến với ngân
sách ở hàng tiêu đề. Thẻ tách tổng địa điểm/ăn uống trên đầu người với tổng
nhóm gồm chi phí khách sạn theo số đêm và di chuyển, sau đó hiển thị chi tiết
cùng lưu ý chuyến đi hoặc trạng thái chưa có lưu ý.

`admin-frontend/app/globals.css` cũng chỉ giữ các import. Style admin được chia
theo shell/run, responsive, Knowledge Graph và AI import trong
`admin-frontend/styles/`; các panel Knowledge Graph nằm trong
`admin-frontend/app/components/knowledge-graph/`.

Observability admin tách danh sách tại `/observability/traces` và detail có URL
ổn định tại `/observability/traces/[traceId]`. Trang detail dựng execution tree
từ `parentId`; trang Steps luôn hiển thị `traceId` và liên kết về request sở hữu
step đó. Frontend dùng contract `TraceSummary`, `TraceDetail` và
`TraceObservation` thay cho một record không định kiểu cho trace detail.

`shared/observability/` là capability kỹ thuật dùng chung, không chứa business
rule. Module cung cấp `ObservabilityManager`, `TraceCallbackHandler`, và adapter
`LangfuseObservabilityAdapter` tích hợp Langfuse Cloud (`https://cloud.langfuse.com`).
Mọi request LLM qua shared Gemini client đều ghi nhận model, latency, status, token
usage (`usageMetadata` input/output/total) và retry attempts. Khi tắt hoặc không có
credentials, hệ thống hoàn toàn no-op và không gọi network SDK. Dữ liệu nhạy cảm
(API key, Bearer token, password trong connection string, credential keys) luôn được
tự động redact và truncate có giới hạn độ dài trước khi gửi. Local adapter trong
module `observability` tiếp tục phục vụ JSON store và admin API.

Để bật Langfuse Cloud, đặt `LANGFUSE_ENABLED=true`,
`LANGFUSE_BASE_URL=https://cloud.langfuse.com`, `LANGFUSE_PUBLIC_KEY` và
`LANGFUSE_SECRET_KEY` trong môi trường deploy. `LANGFUSE_HOST` vẫn được hỗ trợ
để tương thích cấu hình cũ. Có thể đặt
`LANGFUSE_SAMPLE_RATE`, `LANGFUSE_RELEASE`, `LANGFUSE_ENVIRONMENT` và
`LANGFUSE_MAX_CAPTURED_CHARS`; `LANGFUSE_CAPTURE_INPUT_OUTPUT` mặc định là `false`
để không gửi prompt/response. Trace ghi nhận request ID, route, session/thread,
thời gian, trạng thái, warning/source counts; các generation ghi model/provider,
structured-output, temperature, retry attempts, HTTP status và Gemini token usage.
