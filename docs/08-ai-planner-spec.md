# Đặc tả AI Planner

## Mục tiêu

- AI/Extractor chỉ trích xuất tên, alias, vùng tìm kiếm, evidence và ngữ cảnh
  hoạt động của place candidate. Category cuối cùng không được suy diễn từ
  prompt, caption, STT, OCR hoặc tên địa điểm; phải lấy từ `places.place_type`
  khi catalog match, hoặc category do Google Maps Playwright trả về, rồi mới
  chuẩn hóa và lưu làm tag. Provider không trả category thì dùng `other`.

Biến nguồn cảm hứng và yêu cầu của user thành lịch trình có cấu trúc, giải thích
được, tôn trọng ràng buộc và có thể chỉnh sửa ở cấp từng item. Model hỗ trợ trích
xuất và đề xuất; code ứng dụng chịu trách nhiệm về source, ID, xác nhận của user,
kiểm tra, lưu trữ, phân quyền và dữ liệu thực tế.

Planner gồm hai pipeline nối tiếp:

```text
URL -> Import -> Extract -> Resolve -> Confirm
                                      |
                                      v
Explorer -> TripThemePlanner -> PlaceSelector -> Check -> Main Plan
                                    |
                                    v
                              Backup Plan
```

`Confirm` là ranh giới quan trọng: claim do AI trích xuất không tự động trở thành
yêu cầu của user.

## Luồng xử lý hiện tại

1. `ExplorerService` chuẩn hóa ý định và tạo câu hỏi làm rõ.
2. `TripThemePlannerService` chạy graph research deterministic, chiếu kết quả
   thành catalog hữu hạn rồi gọi LLM structured-output một lần để tạo yêu cầu
   trải nghiệm ở cấp toàn chuyến.
3. `PlaceSelectorService` tự tạo đủ số ngày, chọn địa điểm và tối ưu tuyến.
4. `OverallChecker` báo cáo các rủi ro cơ bản.
5. `BackupPlanWorkflow` tạo và kiểm tra một phương án riêng.

UI Planner đã có trip chat bền vững theo user. Mỗi chat giữ TripIntent hiện hành
dạng snapshot đã validate và plan hiện tại. Message đầu tạo plan; follow-up đọc
TripIntent hiện tại từ PostgreSQL rồi gửi cùng tối
đa tám user request gần nhất vào Explorer, sau đó TripThemePlanner/PlaceSelector tạo revision
hoàn chỉnh. Backend giữ nguyên plan ID, tăng revision và lưu snapshot cũ thay vì
trả một plan identity mới. Các địa điểm của plan hiện tại được chuyển thành
`SelectedPlace` cho lần sửa, còn địa điểm user yêu cầu tránh được loại qua
`avoidPlaces`/constraint của Explorer.

Message có URL của user đã đăng nhập được tách thành một job bền vững cho từng
URL và trả về ngay. Worker FIFO chỉ chạy một job mỗi lần, gọi lại chính workflow
Explorer–TripThemePlanner/PlaceSelector rồi ghi revision hoàn chỉnh vào trip chat. Vì vậy user
có thể tiếp tục chat hoặc rời Planner; AppShell poll trạng thái job độc lập với
page. Nếu một prompt thường cập nhật chat trong lúc URL đang chạy, worker nạp
revision mới nhất và retry optimistic conflict có giới hạn thay vì ghi đè.
Mỗi revision phải giữ toàn bộ URL place đã resolve từ các revision trước và gộp
trùng theo identity/provenance. Nếu user chưa khóa duration/date, service tự tăng
duration để xếp hết; nếu user đã khóa, phần dư được giữ trong
`UnscheduledPlace` để UI cho thêm thủ công hoặc yêu cầu AI xếp lại. Địa điểm
PlaceSelector đề xuất không được làm URL place rơi vào `UnscheduledPlace`; PlaceSelector chỉ
bổ sung khi còn capacity sau khi phân bổ source places.
Sau mỗi lần tạo plan, backend hậu kiểm bất biến coverage: từng URL place đã
resolve phải có đúng một đại diện trong item đã xếp với `sourceRefs`, hoặc trong
`UnscheduledPlace` với `reasonCode` và provenance. Nếu downstream vô tình bỏ
sót, backend phục hồi nó vào `UnscheduledPlace` thay vì trả kết quả mất dữ liệu.

Candidate selection xếp hạng semantic relevance, category và chất lượng dữ liệu
trước khi xét route. Khoảng cách chỉ phá hòa giữa các candidate có cùng điểm
relevance; nguyên tắc này áp dụng cho activity và meal. Route optimizer chỉ phân
bổ/thứ tự các Place đã qua bước chọn, không được biến một Place kém phù hợp hơn
thành lựa chọn chính chỉ vì nó gần hơn.

TripThemePlanner không còn dùng research LLM hoặc Place-database research tool.
Backend chạy `GraphResearchOrchestrator` một lần, loại hard conflict và chiếu
evidence theo ontology v7 thành `graphCandidateCatalog`; sau đó LLM tạo
`TripThemeDraft` trong một lượt. Output có `tripThemes`, `requiredExperiences`,
assumption, warning và trace; không có ngày, route hoặc allocation. Backend yêu
cầu model sửa output lỗi tối đa ba lần. PlaceSelector chịu toàn bộ trách nhiệm
phân bổ Place, capacity và `UnscheduledPlace` bằng domain rule deterministic.
Khi không cấu hình LLM, runtime Planner không tự rơi về kế hoạch template.

Khi intake có URL YouTube long-form, runtime bỏ qua metadata `yt-dlp` và thử
caption công khai bằng `youtube-transcript-api`, sau khi kiểm tra cache
PostgreSQL. Request cùng
video được dedupe trong process và bị giới hạn nhịp; khi IP backend bị chặn,
runtime có thể gọi transcript worker do operator tự vận hành trên kết nối dân
dụng. Caption thủ công hoặc tự sinh được cache dài hạn, dùng trực tiếp làm
transcript và video không bị tải xuống. `no_captions` trả
`YOUTUBE_CAPTIONS_NOT_FOUND`; `blocked`/`unavailable` trả lỗi retryable. Runtime
không tải media và không gọi audio STT/OCR cho YouTube long-form. Pipeline chỉ
giữ URL chuẩn hóa cùng platform rồi đưa caption qua structured multilingual text
extraction để tạo observation có entity type, tên gốc, alias, address hint,
parent place và authority; không dịch toàn bộ caption hay tên riêng sang tiếng
Anh. Parser marker Anh–Việt chỉ là fallback. YouTube Shorts có
path `/shorts/{videoId}`, TikTok video, Instagram Reels và Facebook Reels dùng
pipeline media hiện tại. URL rút gọn `youtu.be/{videoId}` không chứa tín hiệu
Shorts nên giữ nhánh caption-only. Gemini Audio trả đồng thời `transcript` và danh sách STT observation
bị ràng buộc bởi `responseJsonSchema`. Mỗi observation giữ
`order`, `placeName`, evidence ngắn, day/time/activity, `searchRegion`, duration
và confidence. Explorer dùng structured caption/STT observations, metadata và structured
frame vision observations để tạo từng stop; Python không suy diễn candidate,
day hay activity từ transcript tự do khi structured STT đã có. Candidate URL giữ `sourceOrder`,
`sourceDay`, `sourceTimeHint`, `sourceActivity` và `sourceDurationMinutes` khi
nguồn có nói rõ. Heading cấp thành phố/khu vực dạng `Hanoi - 2 days` được
trích thành `destinationStay(startDay=1,endDay=2,durationDays=2)`, không phải
place candidate. Planner áp cùng `targetArea` cho toàn bộ khoảng ngày; nếu
nguồn chưa nêu venue thì các ngày được giữ trống để người dùng thêm sau. STT
chịu trách nhiệm chính cho day/order/activity và
`searchRegion`; OCR chịu trách nhiệm chính cho chữ trên bảng hiệu, địa chỉ và
giá; caption bổ sung bối cảnh. Evidence ngắn được giữ riêng trong
`sourceEvidence.stt`, `sourceEvidence.ocr` và `sourceEvidence.caption`.
Title/caption dạng `Top N` tạo expected coverage. Coverage dưới 40% trả
`URL_EXTRACTION_LOW_COVERAGE` trước formatter/resolver; coverage 40–70% giữ
review state và tắt PlaceSelector; từ 70% được coi là đủ để tiếp tục tự động.
Planner ưu tiên blueprint này; PlaceSelector tạo skeleton
`source_itinerary` và route optimizer không đảo thứ tự nguồn. Hard constraint
của user vẫn được ưu tiên hơn URL, và stop bị loại phải xuất hiện trong
`UnscheduledPlace`/warning thay vì bị thay thế âm thầm.

Với intake URL, địa lý có evidence từ reel là guardrail của destination. Nếu
prompt hoặc trip hiện tại ghi một destination khác nhưng `searchRegion` hoặc
thành phố của các stop URL đã resolve tạo thành một vùng đồng thuận rõ ràng,
Explorer dừng trước Planner và trả `DESTINATION_CLARIFICATION_REQUIRED`. Câu hỏi
phải cho user chọn giữ destination hiện tại và chỉ dùng reel làm tham khảo, tạo
một trip riêng cho destination của reel, hoặc đổi trip hiện tại sang destination
của reel; hệ thống không tự chọn thay user. Nếu prompt
và reel cùng vùng nhưng formatter trả sai vùng, code được tự sửa formatter output
và ghi `explorer.trace.destinationGuardrail`. Resolver dùng vùng nguồn làm hint
khi extraction đã có đồng thuận. Itinerary nhiều vùng không đạt ngưỡng đồng
thuận không được tự động đổi trip base chỉ vì một day trip.

Giá trị placeholder như `unspecified` không phải geographic evidence và không
được nối vào provider query hoặc dùng để reject region. URL-only background job
bảo toàn destination của chat hoặc suy luận bảo thủ từ query URL, title/caption
và vùng chiếm ưu thế trong candidate trước khi resolve.

Video frame vision dùng `gemini-3.5-flash-lite` với media resolution `medium`.
Frame được lấy thích nghi theo toàn bộ duration, không quá một frame mỗi giây,
tối đa 72 frame và xử lý theo
batch tối đa 10 ảnh; frame được chia đều giữa các batch để giảm thời gian chờ
batch lớn nhất. Tối đa năm batch frame vision được gọi song song bằng năm API key
khác nhau trong pool `GEMINI_OCR_API_KEYS`; STT dùng pool riêng
`GEMINI_STT_API_KEYS`. Hai pool riêng không được có key trùng nhau. Khi chỉ cấu
hình pool chung `GEMINI_API_KEY` có ít nhất hai key, runtime chia pool làm hai
nửa không giao nhau cho STT và OCR. Mức song song tự giảm khi thiếu key hoặc
batch. Kết quả được hợp nhất lại theo thứ tự frame gốc.
YouTube long-form không chạy audio STT/frame OCR nên caption structurer dùng
`GEMINI_CAPTION_API_KEYS` riêng khi có, hoặc mượn hợp của hai pool trên. Nó chọn
key round-robin, failover tối đa hai credential cho lỗi `401`/`403`/`429` và có
deadline tổng mặc định 60 giây; không thử tuần tự toàn bộ pool khi mạng timeout.
STT và frame vision chạy song song; candidate từ hai nguồn được gộp thay vì để
một nguồn loại bỏ nguồn còn lại. Khi hai observation trùng địa điểm, OCR được
ưu tiên cho tên hiển thị và thứ tự frame; structured STT được ưu tiên cho day,
time hint, activity, duration và `searchRegion`. Evidence của cả hai nguồn vẫn
được giữ tách biệt. Khi STT chuyển một ngày sang day trip vùng khác, vùng đó
trở thành `searchRegion` cho các stop của ngày mà không thay đổi trip base.
Biến thể tên chỉ khác hậu tố destination, như `Phố đường tàu` và
`Phố đường tàu Hà Nội`, được coi là cùng identity ngay cả khi STT/OCR
gán `sourceOrder` khác nhau. Khi merge revision, selected place cùng URL và tên
tương đương, hoặc có tọa độ gần nhau, chỉ được xếp một lần.
Observation thành công được
giữ lại nếu một batch khác lỗi. OCR ảnh/screenshot người dùng upload dùng cùng
model cấu hình. Không áp dụng giới hạn số place candidate có evidence sau bước
gộp; giới hạn 48 chỉ áp dụng cho số frame video được lấy mẫu.
TikTok photo post vẫn không được tải tự động và yêu cầu upload screenshot.

STT fallback probe duration bằng `ffprobe`. Audio không quá 60 giây hoặc chỉ có
một STT key vẫn dùng một request. Audio dài hơn có thể được chia cân bằng thành
tối đa ba chunk theo thứ tự thời gian, overlap mặc định hai giây ở biên. Mặc
định `URL_REEL_STT_MAX_CONCURRENCY=3` và mỗi request Gemini STT được bắt đầu cách
nhau tối thiểu hai giây trong một tiến trình. Cấu hình này vẫn phải được theo dõi
theo quota thực tế của project; nhiều API key không mặc nhiên tạo quota độc lập
vì Gemini áp rate limit theo project. Mỗi key chỉ thuộc một chunk trong wave
đầu; chunk lỗi chỉ retry sau khi toàn bộ wave kết thúc để không tranh key đang
chạy. `429` tôn trọng `Retry-After` với trần 60 giây trước lần thử tiếp theo.
Transcript
được ghép theo chunk order; observation overlap được dedupe theo tên place và
source day rồi đánh lại order toàn cục. Nếu `ffprobe`/`ffmpeg` không khả dụng,
runtime fallback về một request toàn audio.

Số ngày dùng mặc định sản phẩm là 3 ngày khi user không nói rõ:

- ngoại lệ: duration ghi rõ trên heading `thành phố - N ngày` là coverage
  explicit của nguồn. Khi user chưa nêu duration, dùng coverage của các
  `destinationStay` thay vì mặc định 3 ngày; stay-only không bật PlaceSelector tự bù;
- nếu không có URL/OCR, số ngày user nói rõ được giữ nguyên;
- nếu URL/OCR phủ ít hơn 3 ngày, giữ plan 3 ngày và PlaceSelector chỉ bổ sung catalog
  vào ngày hoàn toàn chưa có stop nguồn; ngày đã có stop URL/OCR không bị pad
  thêm theo quota và địa điểm bổ sung phải mang source `finder_suggestion`;
- nếu URL/OCR cần hơn 3 ngày, dùng cấu trúc `sourceDay` hoặc suy ra số ngày tối
  thiểu theo pace để xếp hết stop;
- dedupe candidate dùng danh tính/tên địa điểm đã chuẩn hóa; `sourceOrder` chỉ
  giữ trình tự từ nguồn và không bao giờ là khóa định danh, vì STT/OCR/caption
  có thể gán cùng order cho nhiều địa điểm độc lập;
- nếu user yêu cầu nhiều ngày hơn số ngày nguồn phủ được, PlaceSelector chỉ bổ sung các
  ngày trống;
- nếu user đã yêu cầu số ngày cụ thể, duration đó là ranh giới cứng. URL có
  nhiều stop hơn sức chứa không tự tăng số ngày; stop vượt sức chứa được giữ ở
  `UnscheduledPlace`. Chỉ amendment nói rõ muốn thêm/kéo dài ngày mới được phép
  suy ra duration lớn hơn sau khi merge địa điểm cũ và mới.

## Luồng mục tiêu của MVP

### Giai đoạn 1: Import

- kiểm tra URL và nhận diện connector;
- lấy nội dung được phép và ghi metadata/provenance;
- trả job có trạng thái thay vì giữ HTTP request mở;
- giữ kết quả từng phần để retry.

### Giai đoạn 2: Extract

Structured output của extraction gồm:

- `transcript` cùng structured STT `observations`; transcript phục vụ hiển thị
  hoặc formatter context, còn candidate được tạo từ observations đã validate;
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
- fusion chọn metadata cụ thể làm anchor, giữ alias quan sát được tách khỏi alias
  lookup Anh–Việt sinh có kiểm soát; không chạy một bước alias enrichment thứ
  hai có cùng trách nhiệm;
- resolver giữ top-K option và chỉ auto-resolve top-1 khi vượt cả ngưỡng tuyệt
  đối, margin với top-2 và hard identity policy;
- stage mọi candidate có evidence; chỉ chuyển candidate có representative
  coordinates sang đầu vào PlaceSelector;
- không chặn intake để hỏi user;
- lưu proposal/evidence/note trong `knowledge_graph_import_nodes`; không tự
  upsert `places` hoặc graph canonical;
- Explorer bàn giao `intakeId + userId + explorer` nhưng không tự gọi Planner.
- Explorer vẫn giữ mọi candidate sau aggregation trong
  `explorer.candidateReviews`; item chưa xác minh có status `needs_review` và
  reason/provider riêng thay vì biến mất khỏi UI. Retry từ trip chat chỉ gọi
  lại alias enrichment + resolver cho nhóm này, không chạy lại media/STT/OCR;
  Planner chỉ nhận item `resolved` có danh tính và tọa độ đã xác minh. Candidate
  `needs_review` không được xếp lịch dù provider có trả tọa độ đại diện.
- `extractionConfidence` đo evidence riêng của candidate;
  `resolutionConfidence` đo identity từ provider. `confidence` cũ tạm giữ nghĩa
  extraction để tương thích client cũ.
- Kết quả resolved trả `verifiedAliases` và `verifiedVietnameseAliases`; frontend
  dùng alias Việt đã xác minh trước nhãn provider ngôn ngữ khác.
- Candidate khác tên cùng map tới một Google identity/tọa độ chỉ được gộp khi
  Google trả cùng canonical provider name; resolver giữ các spelling/OCR variant
  làm alias và gộp provenance trước persistence. Nếu provider name khác nhau,
  cả nhóm bị trả về `duplicate_provider_identity`, không được persist.
- Planner downstream dùng TripIntent hiện tại và đọc import nodes theo
  `intakeId`. Chi nhánh cùng tên được chọn theo route proximity, không gọi Google.

### Giai đoạn 4: Explorer

Explorer hợp nhất `SelectedPlaces`, `UserState` và `TripConstraints`, phát hiện
thông tin thiếu hoặc mâu thuẫn và chỉ hỏi câu có tác động cao. Kết quả gồm
`TripIntent` đã chuẩn hóa với `destination`, `timing`, `travelParty`, `budget`,
`notes`, `preferences`, `constraints` và unresolved questions. Boundary
Explorer không còn tách hai object `intent`/`tripSpec`.

Explorer còn tạo `PreferenceSnapshot` cho intake hiện tại. Nếu có authenticated
user, signal đủ confidence được aggregate vào các bảng quan hệ
`traveler_profiles`, `traveler_preference_signals` và
`traveler_preference_signal_sources`; raw prompt, OCR và transcript không đi vào
profile. Signal suy luận chỉ thành preference hiệu lực sau ít nhất hai lần quan
sát. Các trait nhạy cảm không được tự suy luận hoặc lưu. Planner nhận
`effectiveProfile`, nhưng explicit constraint của chuyến hiện tại luôn ưu tiên
hơn profile dài hạn.

Với intake chỉ có `rawRequest` (không URL, ảnh OCR hoặc `placeCandidates`),
Explorer chỉ chặn khi chưa có điểm đến cụ thể. Khi thiếu destination, TripChat
lưu `TripIntent` nháp và hỏi đúng một câu về điểm đến, không chạy planning
workflow. Khi đã có destination, duration, nhóm đi, ngân sách và các trường còn
lại dùng default domain nếu user không cung cấp; Explorer đánh dấu
`mode=confirmed`. Contract vẫn trả `inputCompleteness`, `missingFields`,
`assumptions` và `trace`.

Với intake có URL, source adapter tạo candidate đúng một lần. Code ứng dụng bổ
sung source, priority và preference mặc định, gộp trùng rồi gửi thẳng sang
Resolver. Formatter không sinh lại URL `placeCandidates`; nó chỉ nhận summary
ngắn gồm số stop, interest, category, attribute, activity và source day để tạo
TripIntent canonical. Formatter dùng structured output
schema của provider thay vì nhét toàn bộ JSON Schema vào nội dung prompt.
Formatter và Resolver chạy song song vì cả hai chỉ phụ thuộc output đã chuẩn hóa
của Extractor.

### Giai đoạn 5: TripThemePlanner

TripThemePlanner tạo `tripThemes` ở cấp toàn chuyến:

- chọn nguồn định hướng theo thứ tự: interest/ràng buộc chuyến hiện tại,
  selected Place đã xác nhận, long-term profile có hiệu lực, rồi mới đến
  special experience đặc trưng của điểm đến;
- nếu không có interest, selected Place và profile, phải chọn ít nhất một
  special experience trusted khi graph có coverage; `must` trên graph là độ
  quan trọng với điểm đến, không tự động bắt buộc cho mọi user;
- không chọn trải nghiệm lệch intent, ví dụ không bắt leo núi khi user chỉ muốn
  văn hóa và đời sống địa phương;
- mỗi theme có focus tags, số activity tối thiểu và region mục tiêu khi có;
- ưu tiên profile ở cấp khu vực nhỏ nhất đang có trong `regionKey`;
- hiểu travel style là nhịp và hình dạng hành trình, không lặp cùng một hoạt
  động cho mọi ngày;
- `requiredExperiences` chỉ dùng claim, Activity và Place ID có trong bounded
  graph catalog, theo `required_anchor`, `choose_one` hoặc `open_candidate`;
- ontology v7 dùng `LocationEntity -> SPECIAL_EXPERIENCE -> Activity`, và
  `Activity -> TARGETS_PLACE -> Place` khi trải nghiệm có anchor trực tiếp;
- evidence inferred vẫn được đánh dấu và không được nâng thành verified;
- không tạo ngày, khung giờ, journey phase, route bucket hoặc place allocation.

CLI `trip_theme_cli.py research-context` chỉ chạy graph research và hiển thị cả
research bundle lẫn bounded `graphCandidateCatalog`; lệnh này không gọi LLM.

### Giai đoạn 6: PlaceSelector

TripThemePlanner runtime mang tên `TripThemePlannerService`. Nó tạo
`tripThemes` và `requiredExperiences` ở cấp toàn chuyến,
không tạo nội dung theo Ngày 1/Ngày 2. PlaceSelector tạo đúng số day slot từ
`tripSpec.days`; route optimizer quyết định activity thuộc ngày nào.

`PlaceSelectionInput` nhận `requiredExperiences`. PlaceSelector resolve
`required_anchor` và `choose_one` thành selected Place bắt buộc trước khi tạo
day slot. `open_candidate` hoặc ID chưa resolve được phải xuất hiện trong
`UnscheduledPlace` với `reasonCode=required_experience_unresolved`; không được
âm thầm bỏ trải nghiệm.

PlaceSelector điền item cụ thể:

- theme và day-part goal được dùng để tạo shortlist rộng, không còn là ràng buộc
  cứng ngăn activity phù hợp được chuyển sang ngày gần hơn về địa lý;

- với intake có URL hoặc ảnh/OCR, xếp candidate từ nguồn trước; PlaceSelector chỉ bổ
  sung catalog vào ngày hoàn toàn chưa có stop nguồn;
- PlaceSelector loại suggestion trùng danh tính với toàn bộ stop URL và item đã xếp,
  kể cả khi provider ID khác nhưng tên chuẩn hóa/biến thể alias cho thấy cùng
  một địa điểm;
- số place extractor nhận từ URL không bị giới hạn theo quota của PlaceSelector. Riêng
  `finder_suggestion` trên một ngày trống bị chặn theo pace
  (`relaxed=2`, `balanced=3`, `packed=4`); giới hạn này không đếm hoặc loại stop
  URL của user;
- PlaceSelector dùng theme, day-part goal, region và constraint do Planner tạo để chọn
  địa điểm bù; stop nguồn không bị thay thế và suggestion phải được đánh dấu;
- ở chế độ `route_first`, không chọn khung giờ và không loại candidate theo giờ mở cửa;
  timing claim chỉ được giữ làm provenance, chưa dùng để tạo giờ hẹn;
- rank Place bằng mô tả theo theme/goal của ngày trước, sau đó rerank bằng
  category, tags, region, confidence và các dữ liệu có cấu trúc;
- fallback có kiểm soát lên region cha khi locality nhỏ thiếu Place, nhưng không
  dùng hotel/restaurant/transport để lấp activity sai chủ đề;
- chốt đúng hai activity chính cho mỗi ngày, tối ưu activity ở cấp toàn chuyến,
  rồi mới chọn đủ breakfast/lunch/dinner theo các anchor địa lý của tuyến;
- stop ăn uống từ URL chiếm meal slot trước và thay thế meal suggestion
  của PlaceSelector; stop URL không được âm thầm loại khi chuyển giữa activity
  pool và meal slot;
- `cafe`/`coffee shop` là stop trải nghiệm thuộc activity pool, không
  được dùng làm breakfast/lunch/dinner chỉ vì provider gắn nhóm
  `food_drink`;
- giữ source ref từ `SelectedPlace` tới `TripItem`;
- tối ưu thứ tự item có tọa độ bằng nearest-neighbour rồi 2-opt;
- lấy route pedestrian/auto từ Valhalla sau khi xếp stop; leg provider có
  geometry, `fetchedAt`, `source=valhalla_routing`, `verified=true`, còn lỗi
  provider fallback về ước tính địa lý `verified=false`;
- với trip có `startDate`, lấy thêm OpenTripPlanner theo giờ kết thúc stop;
  chọn transit khi user ưu tiên bus/train, nếu không giữ làm alternative; không
  gọi timetable hiện tại cho trip chưa có ngày;
- chỉ thêm địa điểm mới từ place provider khi cần hoàn thiện ngày và phải đánh
  dấu đây là đề xuất của hệ thống;
- đưa địa điểm không xếp được vào `UnscheduledPlace` với reason code.

Sau khi `PlaceSelectorService` chọn Place mà chưa gọi route leg chi tiết,
`RouteFirstItineraryOptimizer` chạy ở cấp toàn chuyến.
Nó dùng travel-time matrix để giảm tổng thời gian di chuyển bằng cách hoán đổi
activity giữa các ngày rồi tối ưu thứ tự trong ngày. Sau đó `MealStopSelector` cố gắng chèn
ba bữa theo thứ tự breakfast → activity 1 → lunch → activity 2 → dinner. Stop nguồn có
`sourceDay`, `sourceOrder` hoặc provenance URL/OCR được giữ cố định. Đây là heuristic
deterministic. Walking/car/transit route chỉ được enrich sau khi nghiệm cuối đã chốt;
không được mô tả như tối ưu toàn cục. Có thể quay lại behavior cũ bằng
`ITINERARY_OPTIMIZER_MODE=legacy`.

Nếu không tìm được Place ăn uống đã xác minh cho một meal slot, PlaceSelector bỏ slot đó
khỏi `PlanDay.items` thay vì tạo card breakfast/lunch/dinner giả. Planning warning
vẫn ghi nhận meal slot bị thiếu để plan không bị mô tả như đã hoàn thiện.

Route-first hiện không tạo lịch theo đồng hồ. Các marker `timeWindow` rất ngắn chỉ tồn tại
để giữ tương thích schema và thứ tự; UI không cho nhập/sửa giờ và các marker không tham gia
candidate selection, opening-hours check hoặc timeline fitting.

Adapter PlaceSelector dùng `RepositoryPlaceSelectionTool` trong runtime để tìm Place đang
active theo `regionKey` và `focusTags`. Nếu catalog vùng trống nhưng có
`SelectedPlace`, PlaceSelector vẫn có thể lập plan giới hạn trong danh sách đã xác
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

Main Plan được chốt từ một version đã kiểm tra. Backup Plan dùng lại
`mainPlan.tripThemes`, chạy lại PlaceSelector với constraint dự phòng, có
`parentPlanId`, được validate độc lập và không mutate Main Plan.

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
- Candidate được tự động resolve theo lựa chọn sản phẩm no-interruption, nhưng
  chỉ kết quả resolved có danh tính cụ thể và đủ tọa độ được lưu để PlaceSelector dùng.
- Không chuyển caption/câu quảng bá/danh sách nhiều venue thành một PlanItem.
  URL place chưa có representative coordinates không xuất hiện trong plan;
  proposal/evidence vẫn ở import node và phần thiếu được PlaceSelector điền bằng
  Place đã chuẩn hóa khi policy cho phép.
- `sourceActivity` là mô tả hành động ngắn có evidence, không phải nơi sao chép
  nguyên caption hoặc transcript.
- Không âm thầm bỏ địa điểm đã xác nhận; phải xếp hoặc trả về `UnscheduledPlace`.
- Mỗi ngày có tối đa hai activity chính và ba meal stop. Restaurant/food URL
  thay meal suggestion và không chiếm activity slot; cafe/coffee vẫn là
  activity. Khi duration/date chưa bị user khóa hoặc user yêu cầu thêm ngày,
  duration tối thiểu được tính lại sau khi merge địa điểm của revision cũ với
  intake mới; nếu duration được giữ cố định, phần vượt sức chứa phải vào
  `UnscheduledPlace`.
- `timeWindow` phải nằm trọn trong một ngày địa phương. Sau khi cộng thời gian
  route, item đạt hoặc vượt `24:00` phải được bỏ khỏi ngày và trả về
  `UnscheduledPlace`, không được format thành giờ 24–28.
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
  key hoặc nhiều key phân tách bằng dấu phẩy. URL extraction ưu tiên
  `GEMINI_STT_API_KEYS` và `GEMINI_OCR_API_KEYS` để các call đồng thời không
  tranh cùng key. Client dùng pool key trong tiến trình; khi key hiện tại trả
  `429`, key đó được cooldown theo chỉ dẫn của provider và call chuyển sang key
  kế tiếp ngay. Key trả `401/403` bị loại khỏi pool cho đến khi tiến trình khởi
  động lại. API key không được ghi vào log.
  Circuit breaker vẫn là phần chưa triển khai.
- Chỉ cache khi quyền riêng tư, độ mới và phạm vi user cho phép.
- Giữ provider call sau `LLMClient`; domain code không gọi trực tiếp SDK của
  provider.
