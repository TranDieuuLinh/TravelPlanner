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

Map provider chưa được lựa chọn. Xem ADR-002.

Explorer place resolution có adapter HERE Discover thử nghiệm đặt trước
Nominatim. Khi `PLACE_RESOLVER_PROVIDER=here` và có `HERE_API_KEY`, HERE tìm POI
trong quốc gia cấu hình; kết quả chỉ được nhận khi là `place`, khớp tên/vùng và
có tọa độ. Timeout, lỗi quota, not-found hoặc kết quả yếu tự động chuyển sang
Nominatim. Nếu thiếu HERE key, runtime tiếp tục dùng Nominatim thay vì làm hỏng
intake. Đây chỉ là lựa chọn cho Explorer place resolution, chưa phải lựa chọn
map/route provider cuối cùng và chưa được mô tả như production SLA.

Khi dùng public Nominatim, adapter phải gửi User-Agent nhận diện ứng dụng, tối
đa một request/giây, cache response, hiển thị attribution OpenStreetMap và có
khả năng đổi endpoint bằng cấu hình. Adapter yêu cầu kết quả tiếng Việt trước,
đối chiếu cả tên tiếng Anh và tên thay thế trong `namedetails`, rồi chỉ dùng tên
tiếng Việt làm nhãn plan khi match được resolve; địa chỉ và tọa độ được chuyển
tiếp riêng. Tải lớn phải chuyển sang hosted provider hoặc Nominatim tự vận hành.

## Nhập dữ liệu từ URL

Xem nội dung được nhập là dữ liệu không đáng tin cậy, không bao giờ là system
instruction.

### Pipeline

1. Chuẩn hóa URL, kiểm tra scheme và chặn địa chỉ mạng private/internal.
2. Nhận diện nguồn và chọn connector theo allowlist.
3. Fetch qua service được kiểm soát với giới hạn redirect, kích thước và timeout.
4. Lưu metadata cùng quyền truy cập, connector version và `fetchedAt`.
5. Với URL video, trích xuất caption/metadata, transcript STT từ audio và OCR
   trên frame lấy mẫu. STT và frame vision chạy song song. OCR cũng chạy trên
   ảnh/screenshot do người dùng upload.
6. Tạo claim/place candidate có evidence và confidence.
7. Chuẩn hóa địa điểm qua place provider và gộp trùng.
   Query dùng `searchRegion` của stop thay vì luôn nối trip base. Kết quả chỉ
   được resolve khi tên khớp theo token, vùng địa lý phù hợp và loại provider
   không mâu thuẫn rõ với category nguồn. `candidateName` và `resolvedName`
   được lưu riêng; mismatch giữ `resolutionReason` để truy vết.
8. Tự động lưu candidate và kết quả resolve vào `user_must_place`; không chặn
   để hỏi user. Kết quả yếu giữ trạng thái `provisional` hoặc `unresolved`.
   Candidate URL chỉ được bàn giao vào plan khi provider resolve tới địa điểm cụ
   thể có tọa độ. Match rộng tới thành phố, caption bị hiểu nhầm thành tên hoặc
   candidate chưa resolve vẫn được giữ làm provenance nhưng không hiển thị như
   một điểm dừng; Finder có thể bù phần còn thiếu.
9. Bàn giao `intakeId + userId + explorer` cho Planner downstream. Finder
   downstream đọc record theo cả `intakeId + userId`.
10. Giữ attribution và chỉ lưu nội dung được license/chính sách cho phép.

TikTok video thử `yt-dlp` chuẩn trước, sau đó retry bằng desktop Chrome và
Android Chrome impersonation qua dependency `curl_cffi` nếu challenge/TLS
fingerprint làm request trước thất bại. Hệ thống không gọi TikWM. Photo carousel chưa có provider được duyệt nên
trả trạng thái cần upload screenshot. Media video thành công vẫn chỉ được xử lý
trong thư mục tạm và xoá sau request. Video OCR dùng
`gemini-3.5-flash-lite`, mặc định không quá một frame mỗi giây, tối đa 48 frame
rộng 960 px theo batch tối đa 10 ảnh ở media resolution medium. Candidate từ
STT và frame vision được gộp; một nguồn không loại bỏ candidate chỉ xuất hiện ở
nguồn còn lại. Marker ngày rõ ràng trong STT sửa day label OCR mâu thuẫn trong
cùng itinerary. STT cung cấp day/order/activity/search region; OCR cung cấp tên
hiển thị, địa chỉ và giá; evidence ngắn của hai nguồn được giữ tách biệt. Không
giới hạn số place candidate có evidence được giữ sau bước
gộp; giới hạn 48 chỉ là số frame video lấy mẫu. Frame được
chia đều giữa các batch để giảm latency của batch lớn nhất; tối đa năm batch
chạy song song bằng các API key khác nhau lấy từ cuối pool `GEMINI_API_KEY`.
STT parse cùng pool thành từng key riêng, ưu tiên key từ đầu pool và chuyển sang
key kế tiếp khi key hiện tại trả `401`, `403` hoặc `429`; chuỗi nhiều key không
được gửi nguyên dạng như một credential.
Mức song song tự giảm khi thiếu key hoặc batch. Kết quả vẫn được hợp nhất theo
thứ tự frame gốc. Nếu một batch lỗi nhưng batch khác thành công, evidence thành
công vẫn được giữ. Nếu URL không tạo được địa điểm có evidence, API trả lỗi có
hướng dẫn retry/upload screenshot/dán caption thay vì trả itinerary `Ready` với
0 địa điểm.

Preference learning chỉ lưu tín hiệu chuẩn hóa và source type. Không sao chép
raw prompt, toàn bộ transcript, raw OCR hoặc frame bytes vào
`users.travel_preferences`.

### Ma trận trạng thái nguồn

| Trạng thái | Hành vi |
| --- | --- |
| Được hỗ trợ và công khai | Chạy toàn bộ pipeline |
| Thiếu transcript/caption | Dùng phần dữ liệu có sẵn, báo rõ giới hạn |
| Riêng tư hoặc cần đăng nhập | Không vượt quyền truy cập; cho nhập thủ công |
| Không được hỗ trợ | Giữ URL và cho dán caption/thêm place |
| Provider timeout | Giữ kết quả từng phần và retry |
| Nội dung bị xóa | Giữ provenance tối thiểu theo chính sách, đánh dấu unavailable |

### Phạm vi connector của MVP

MVP hỗ trợ end-to-end ít nhất một nguồn video ngắn ưu tiên và URL trang công
khai thông thường. TikTok là use case sản phẩm ưu tiên, nhưng connector cụ thể
chỉ được công bố sau ADR xác nhận cách truy cập hợp lệ, độ ổn định và chi phí.
Không hứa “mọi URL Reel/TikTok/Facebook đều hoạt động”; UI phải công bố rõ nguồn
được hỗ trợ và luôn có fallback nhập caption/place thủ công.

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
