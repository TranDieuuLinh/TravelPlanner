# Kiến trúc hệ thống

## Kiến trúc hiện tại

```text
Frontend Next.js
    |
    | HTTP /api
    v
Router FastAPI
    |
    +-- users: service -> SQLAlchemy repository -> SQLite/PostgreSQL
    |
    +-- plans: service -> workflow -> domain service
    |                         |             |
    |                         |             +-- LLM gateway (Stub/Gemini)
    |                         +-- PlanRepository trong bộ nhớ
    |
    +-- profiles/marketplace: endpoint placeholder
```

Frontend và backend là hai ứng dụng riêng trong cùng một kho mã. PostgreSQL và
backend được khai báo trong `docker-compose.yml`; khi chạy trên máy cá nhân,
backend mặc định dùng SQLite.

`/api/plans/explore/full` và `/api/plans/explore/full/intake` chỉ hoạt động khi
Gemini được cấu hình và formatter được bật. Các luồng tạo Main/Backup Plan vẫn
có thể dùng `StubLLMClient` khi không có provider.

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
    +-- có ảnh? --> ImageOcrService ------> image contexts ----+
    |                                                          |
    +-- có URL? --> UrlReelExtractionService -> URL results ----+--> ExploreResponseFormatter
    |                                                          |             |
    +-- không có ảnh/URL ---------------------------------------+             v
    |                                                                  Gemini JSON
    +-----------------------------------------------------------------------|
                                                                            v
                                                              ExploreResponse schema
                                                                            |
                                                                            v
                                                                    Planner result UI
```

`ExploreResponseFormatter` chỉ tổng hợp raw prompt và context đã được các
extractor tạo ra; formatter không tự điều phối download URL hoặc OCR. Nếu request
chỉ có raw prompt, `PlanService` bỏ qua cả hai extractor và gọi formatter trực
tiếp. Kết quả Explorer hiện được trả thẳng về client, chưa được lưu thành draft
trong database. Sau khi user xác nhận candidate trên UI, client gọi
`POST /api/plans/main/from-explorer` với `intent`, `tripSpec` và
`selectedPlaces`. Đây hiện là handoff theo request; persistence theo trip cho
`SelectedPlace` vẫn chưa được triển khai.

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
