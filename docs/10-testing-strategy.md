# Chiến lược kiểm thử

## Hiện trạng

Backend đã được kiểm thử tự động toàn diện với pytest và database SQLite cô lập (23+ test cases thuộc 7 test suite), bao gồm: Auth JWT cookie, refresh session, CSRF, RBAC, Profile, creator application, trọn bộ nghiệp vụ Marketplace (Creator listings, MoMo Sandbox IPN anti-replay, Entitlements, copy plan `copied_plan_id`, reviews, reports, refunds, audit logs), contract Planner–Marketplace, và bộ kiểm thử nghiệm thu E2E toàn trình (`backend/tests/test_person_c_e2e_week6.py`). Frontend hiện được bảo vệ bằng typecheck và production build.

## Các lớp kiểm thử

### Kiểm thử đơn vị backend

Sử dụng pytest cho domain và service:

- phân tích sở thích và tạo câu hỏi làm rõ;
- chuyển artifact thành claim/candidate và gộp địa điểm trùng;
- YouTube caption cache hit không gọi provider, request cùng video được dedupe,
  IP block thử worker, còn mọi trạng thái thiếu caption đều không tải media/STT;
- caption, STT và frame OCR thành công được upsert idempotent vào cùng retrieval
  store theo canonical URL và có thể lọc theo loại artifact;
- URL candidate chỉ được tạo bởi Extractor, không bị Formatter sinh lại;
- Formatter và Resolver bắt đầu song song với intake URL;
- timing report giữ cùng `intakeId`, có đủ stage chính và không ghi raw
  prompt/URL/transcript/OCR vào JSONL; timing từng URL phân biệt cache hit,
  cache miss và bypass;
- timing TripThemePlanner/PlaceSelector có tổng wall-clock, đủ stage Planner, PlaceSelector và
  CheckOverall, không chứa prompt hoặc payload provider;
- không persist candidate unresolved hoặc thiếu latitude/longitude;
- candidate `needs_review` không được xếp lịch, nhưng luôn được bàn giao vào
  `unscheduledPlaces` với `identity_needs_review`, tên gốc, URL, `candidateId`
  và `topMatches`; Planner không tạo venue thay thế;
- điều phối luồng tạo plan;
- TripThemePlanner trả requirement toàn chuyến và backend chỉ sinh bucket ngày trung
  tính; URL provenance không có `sourceDay` được phép đổi ngày theo tuyến;
- itinerary optimizer gom activity gần nhau giữa các ngày, giữ source-day anchor,
  dùng matrix khi có và bảo toàn thứ tự khi provider lỗi;
- route enrichment batch ordered stop theo ngày, ánh xạ đúng từng leg, dùng
  Haversine prefilter cho walking và chỉ gọi transit theo preference/constraint;
- route-first giữ ba meal anchor, cho phép hơn hai activity khi duration và
  transition còn vừa, đồng thời đưa activity tràn thời gian vào danh sách chưa xếp;
- Finder lấp timeline theo capacity phút thay vì quota activity theo pace, và
  Checker từ chối hai Restaurant liền nhau nếu không có activity hoặc
  DrinkDessert ở giữa;
- Finder chỉ chạy sau khi hết URL place phù hợp trong window, ưu tiên diversity,
  không thêm quá một coffee/ngày và không thêm coffee nếu ngày đã có cafe URL;
- record KG `catalog_status=merged` bị loại khỏi search, lookup ID cũ redirect
  sang `merged_into_entity_id` và duplicate cùng landmark không tạo ambiguity;
- URL chỉ có quán ăn vẫn ưu tiên ba source meal vào đúng anchor, dùng Finder bù
  ít nhất một activity giữa breakfast–lunch và lunch–dinner dù chế độ thay thế
  source bị tắt, đồng thời giữ provenance của toàn bộ source Place;
- meal venue không resolve vẫn giữ anchor tổng quát và warning, không giả mạo
  một Place đã được provider xác minh;
- route-first thử chuyển activity overflow sang đúng một ngày khả thi khác và
  không làm bật khỏi lịch một item đã xếp ở ngày đích;
- mọi selected place được xếp hoặc có lý do chưa xếp;
- bảo toàn item đã khóa và tính độc lập của plan dự phòng;
- trip chat giữ nguyên plan ID qua nhiều revision, nhớ user request trước và
  từ chối optimistic revision đã cũ;
- raw request chỉ thiếu destination lưu TripIntent nháp và không gọi planning
  workflow; thiếu duration/party/budget dùng default;
- required experience được PlaceSelector resolve thành required Place hoặc giữ
  trong `UnscheduledPlace`, không bị bỏ âm thầm;
- lifecycle turn nằm trên user message và revision chứa cùng TripIntent snapshot
- preference observation job được enqueue idempotent theo user message, chỉ
  claim turn hoàn tất, không chứa raw content và retry không cộng signal hai lần;
- structured intent edit trả sau khi persist, coalesce nhiều edit đang chờ và
  chỉ worker của intent version mới nhất được ghi plan/revision
  đã dùng để tạo plan;
- quy tắc thời gian, mật độ và validation;
- bất biến của order, entitlement, review và payment;
- chuyển đổi lỗi từ provider.

### Kiểm thử tích hợp backend

Chạy test FastAPI với database cô lập:

- validation request và contract camelCase;
- khả năng lưu trữ của repository và migration;
- ma trận authentication và authorization;
- isolation của trip chat theo user và contract camelCase của chat history;
- xử lý idempotent khi generate/checkout/webhook;
- vòng đời import job, retry từng bước và giữ kết quả từng phần;
- batch URL/ảnh OCR tạo đúng một job cho mỗi nguồn, chỉ claim job kế tiếp sau khi job đang
  chạy kết thúc, tự kết thúc job quá deadline, giữ thứ tự batch, retry riêng và
  cô lập danh sách theo user; xóa job `queued`, hủy/xóa job `running` rồi chạy
  ngay job kế tiếp, cập nhật lại vị trí hàng chờ và không cho user thao tác job
  của tài khoản khác; xóa job đã hoàn tất/thất bại mà không ảnh hưởng plan
  revision; phân tích lại job đã kết thúc phải tạo job mới có
  `forceRefresh=true` và không ghi đè lịch sử job cũ; ảnh giữ đúng MIME/file gốc
  cho retry/reprocess và từ chối định dạng không hỗ trợ;
- source connector, place resolution và provenance persistence;
- Explorer persistence phải chứng minh caption/STT/OCR/context cùng nằm trong
  một `source_documents`, evidence bám đúng import node và provider snapshot chỉ
  giữ một ảnh;
- note contract phải chứng minh import node không có display-note column; từng
  source note có text tiếng Việt và provenance riêng round-trip qua plan
  revision, mutation chỉ cho sửa `personalNotes`, và itinerary/map popup tạo
  cùng presentation từ `notes`, `noteSources`, `personalNotes`; finder từ
  provider không được mang nhãn video;
- Top-K Knowledge Graph phải test cả alias đã review, auto-resolve có margin và
  hai chi nhánh cùng tên. Case chi nhánh phải giữ `branch_ambiguous`, không gọi
  Google, rồi chuyển lựa chọn `route_proximity` vào plan item mà không sửa node;
- URL job test cả `processing_status` độc lập với `review_status`; migration
  graph phải chỉ có một head sau cutover `20260805_0037`;
- web-page connector tách main text/metadata, giữ functional query, chặn DNS
  private sau redirect, giới hạn response và trả cùng contract URL extraction;
- rollback transaction và xung đột dữ liệu.

Thay provider bên ngoài bằng fake tuân thủ đúng contract. Tạo một bộ test sandbox
provider nhỏ, tách khỏi quy trình trên máy cá nhân thông thường.

### Kiểm thử frontend

- Kiểm thử đơn vị cho chuyển đổi schema và reducer của editor.
- Component test form, trạng thái loading/empty/error, chỉnh sửa lịch trình và
  control phụ thuộc quyền hạn.
- End-to-end test các hành trình quan trọng nhất bằng Playwright.

`admin-frontend/` phải vượt qua `npm run typecheck` và `npm run build`. Backend
có test riêng cho RBAC, list/detail planning run, redaction và contract report
của golden dataset. Golden runner phải có test cho ít nhất một module thực thi
thành công không phụ thuộc provider (Checker), một input sai contract và việc
lưu execution thành planning run để điều tra lại.

### Đánh giá AI

Hành vi AI cần bộ evaluation có version bên cạnh test truyền thống. Xem
`08-ai-planner-spec.md`.

## Hành trình toàn trình của MVP

1. Đăng ký, tạo trip, dán URL, xác nhận place, generate, chỉnh sửa, lưu, tải lại
   và mở offline.
2. URL không hỗ trợ/thiếu transcript vẫn giữ draft và cho nhập place thủ công.
3. Hai URL nhắc cùng một place được gộp nhưng vẫn giữ cả hai provenance.
4. Selected place không xếp được xuất hiện với reason code, không bị mất.
5. Giữ một địa điểm đã khóa khi AI chỉnh sửa phần còn lại của ngày.
6. Tạo plan dự phòng sau cảnh báo route/place mà không thay đổi plan chính.
7. Creator tạo plan từ URL, preview, publish và version listing.
8. Buyer thanh toán, nhận quyền truy cập, tạo bản sao cá nhân và review sau khi
   sử dụng.
9. Buyer thêm URL vào bản sao và Planner không sửa plan đã publish của creator.
10. Payment thất bại không cấp quyền; webhook trùng chỉ cấp quyền một lần.
11. User không có quyền không thể chỉnh sửa plan riêng tư của người khác.
12. Admin xử lý report và tạo audit event.

## Cổng kiểm soát chất lượng trong CI

- Backend: format/lint, typecheck, unit test, integration test và kiểm tra
  migration.
- Frontend: lint, typecheck, component test và production build.
- End-to-end smoke test trên stack dùng một lần.
- Quét dependency và secret.

Test phải deterministic: cố định thời gian, seed random, không gọi provider thật
và dùng fixture timezone/tiền tệ rõ ràng.

## Evaluation TripThemePlanner/PlaceSelector cục bộ

Chạy bộ scenario deterministic từ planning context qua Planner, PlaceSelector, Main
Plan và Backup Plan:

```bash
cd backend
.\.venv\Scripts\python.exe scripts\evaluate_theme_selector.py
```

Có thể lưu report JSON để review thủ công:

```bash
.\.venv\Scripts\python.exe scripts\evaluate_theme_selector.py --output .runlogs/theme-selector-evaluation.json
```

Evaluator kiểm tra catalog fill, giới hạn thời gian/user status, ranh giới
selected/avoided/unscheduled, ID nhập tay, duration so với time window, source
provenance và bảo toàn selected Place trong Backup Plan. Evaluator không dùng
provider thật và không đánh giá chất lượng `CheckOverall`.
