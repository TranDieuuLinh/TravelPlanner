# Đặc tả AI Planner

## Mục tiêu

- AI/Extractor chỉ trích xuất tên, alias, vùng tìm kiếm, evidence và ngữ cảnh
  hoạt động của place candidate. Category cuối cùng không được suy diễn từ
  prompt, caption, STT, OCR hoặc tên địa điểm; phải lấy từ loại/properties của
  canonical `knowledge_entities` khi Knowledge Graph match, hoặc category do
  Google Maps Playwright trả về, rồi mới chuẩn hóa và lưu làm tag. Provider
  không trả category thì dùng `other`.

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

Conversation Supervisor chỉ phân loại intent và dispatch đúng một agent cho mỗi
turn. `create_plan` đi vào `ExplorerAgent`: agent này lưu intake và hỏi lại nếu
chưa xác định được destination; khi destination đã đủ, nó tiếp tục gọi pipeline
`TripThemePlanner -> PlaceSelector -> Check` và lưu revision đầu tiên.
`regenerate_plan` đi vào `MainPlanningAgent`; câu hỏi thông tin đi vào
`InformationFinderAgent`; mutation item đi vào `PlanEditorAgent`. Supervisor
không tự chạy Explorer như một bước tiền xử lý trước khi dispatch agent khác.
Mọi message đều đi qua structured classification của Gemini trước khi dispatch;
runtime không dùng keyword heuristic để bỏ qua model và tự chọn intent. Sau khi
model trả kết quả, server vẫn validate schema, intent-agent mapping, item ID,
confidence và confirmation gate trước khi cho agent thực thi.
Classifier chỉ trả `intent`, `confidence` và typed `arguments`; không trả
`agent` hoặc `responseText`. Mapping agent do server sở hữu. InformationFinder
tự gọi LLM để trả lời general advice, dùng grounded search cho dữ liệu cần độ
mới, dùng Knowledge Graph/provider cho place search và chỉ đọc snapshot hiện
tại khi giải thích plan.

Yêu cầu điểm gặp có từ hai điểm xuất phát dùng intent riêng
`find_meeting_point`. Các điểm xuất phát được trích thành `origins`, không được
coi là `mustVisitPlaces` hay stop của itinerary. InformationFinder resolve từng
origin, dừng để hỏi lại nếu origin không chắc chắn, tính tâm địa lý gần đúng rồi
tìm và xếp venue theo khoảng cách lớn nhất từ các origin. Kết quả phải ghi rõ
đây là khoảng cách đường chim bay; tối ưu theo thời gian đi thực tế cần route
matrix và không được ngụy tạo từ tâm địa lý.

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
Destination dùng region key để so khớp identity nhưng dùng tên canonical tiếng
Việt để hiển thị và lưu revision. Vì vậy alias nguồn như `Hanoi`, `Danang` hoặc
`Saigon` không được thay label `Hà Nội`, `Đà Nẵng` hoặc `TP. Hồ Chí Minh` của
plan sau khi thêm URL.

Candidate selection xếp hạng semantic relevance, category và chất lượng dữ liệu
trước khi xét route. Khoảng cách chỉ phá hòa giữa các candidate có cùng điểm
relevance; nguyên tắc này áp dụng cho activity và meal. Route optimizer chỉ phân
bổ/thứ tự các Place đã qua bước chọn, không được biến một Place kém phù hợp hơn
thành lựa chọn chính chỉ vì nó gần hơn.

Nearby graph survey dùng Haversine để loại candidate ngoài bán kính rồi lấy
route cost cho toàn shortlist bằng một matrix request; matrix lỗi thì giữ
Haversine thay vì gọi point-to-point tuần tự. Khi tạo Main Plan, route matrix và
coarse leg vẫn bảo đảm thứ tự/timeline sơ bộ trong critical path. Detailed leg,
geometry và provider verification chạy bằng request enrichment riêng sau
response đầu, dùng optimistic revision và chạy lại timeline/Checker trước khi
đánh dấu `routeEnrichmentStatus=completed`.

TripThemePlanner không còn dùng research LLM hoặc place-catalog research tool
legacy. Tên service được giữ để tương thích nhưng vai trò hiện tại là chọn điểm
nhấn đặc trưng, không tạo theme điều khiển việc chọn Place.
Backend chạy `GraphResearchOrchestrator` một lần, loại hard conflict và chiếu
evidence `supported` hoặc `unknown` theo ontology v7 thành `graphCandidateCatalog`;
candidate `unknown` được xếp sau evidence `supported` và giữ warning về dữ liệu
vận hành chưa đủ. Sau đó LLM tạo
`TripThemeDraft` trong một lượt. Projection chỉ giữ nhóm Activity có seed
`SPECIAL_EXPERIENCE`; claim `OFFERS_ACTIVITY` chỉ bổ sung Place cho đúng nhóm
đó. Output luôn có `tripThemes=[]`; `requiredExperiences` chỉ chứa 0–3 điểm
nhấn, assumption, warning và trace; không có ngày, route hoặc allocation. Backend yêu
cầu Gemini tạo JSON bằng `responseJsonSchema` của `TripThemeDraft`, rồi vẫn
kiểm tra ID graph, region và các invariant nghiệp vụ phía server. Chỉ output
không thể chuẩn hóa an toàn mới yêu cầu model sửa, tối đa ba lần. PlaceSelector chịu toàn bộ trách nhiệm
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
Shorts nên giữ nhánh caption-only. Gemini Audio chỉ trả `transcript` bằng một
schema nhỏ và không còn tạo travel observation. Sau khi ASR và frame vision
chạy song song, Gemini Text nhận transcript, structured OCR observations,
caption/metadata, expected count và destination hint để trả danh sách source
observation hợp nhất. Mỗi observation giữ `order`, `placeName`, evidence theo
từng nguồn, day/time/activity, `searchRegion`, duration và confidence. Evidence
phải xuất hiện trong đúng source; destination hint chỉ là lookup context, không
phải evidence, và model không được chọn canonical identity hay tọa độ. Python
validate/ground output rồi mới tạo candidate. Fusion payload không lặp
description trong metadata và caption; raw OCR text bị bỏ khi structured OCR
observations đã đạt expected coverage, còn coverage thiếu thì giữ raw text làm
fallback. Candidate URL giữ `sourceOrder`,
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
Planner ưu tiên blueprint này nhưng PlaceSelector vẫn dùng chung
`meal_anchored_timeline` với raw prompt; metadata URL chỉ trở thành constraint
`sourceDay`, `sourceOrder`, timing và provenance. Route optimizer không đảo thứ
tự nguồn. Hard constraint của user vẫn được ưu tiên hơn URL, và stop bị loại
phải xuất hiện trong `UnscheduledPlace`/warning thay vì bị thay thế âm thầm.

Timeline route-first áp cùng invariant cho raw prompt và URL: mỗi ngày có ba
meal anchor `breakfast_meal`, `lunch_meal`, `dinner_meal`; mỗi khoảng
breakfast–lunch, lunch–dinner và dinner–21:00 được lấp bằng bao nhiêu activity
cũng được miễn `duration + travel + buffer` còn vừa, không áp quota số lượng.
Quán ăn từ URL được ưu tiên chiếm meal anchor phù hợp. Việc tắt
gợi ý thay thế source không được tắt gap filling: khi URL thiếu activity,
PlaceSelector được phép thêm một Place đã xác minh với
`source=finder_suggestion` vào từng khoảng ban ngày còn trống. Gap filling không
được xóa, thay hoặc đổi provenance của stop URL. Nếu không có meal venue đã xác
minh, plan vẫn giữ anchor tổng quát `source=finder_rule`; nếu không có activity
hợp lệ để bù, plan phải trả warning rõ ràng thay vì ngụy tạo địa điểm.

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
Sau khi tải media hoàn tất, audio extraction -> STT và frame extraction -> frame
vision là hai pipeline độc lập; một nhánh không chờ artifact của nhánh kia.
Gemini Text fusion gộp tín hiệu sau khi cả hai hoàn tất. Runtime chỉ bỏ call này
khi structured observations có expected count/order/evidence đầy đủ và không có
xung đột tên; transcript thô cần suy luận vẫn bắt buộc đi qua fusion. Khi hai source cùng nói về một địa điểm, OCR được
ưu tiên cho spelling/tên hiển thị, còn transcript ASR được ưu tiên cho day,
time hint, activity, duration và `searchRegion`. Evidence của metadata,
caption, STT và OCR vẫn được giữ tách biệt. Khi transcript chuyển một ngày sang day trip vùng khác, vùng đó
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

Danh sách “things to do” có số thứ tự không chỉ tạo candidate cho venue.
Frame vision và STT phải giữ cả activity không nêu cơ sở cụ thể (ví dụ water
puppet show, head spa) và city/region của day trip. Các candidate này giữ
`sourceOrder`, `sourceActivity`, evidence và `entityType`; chúng được hiển thị
để user xác nhận hoặc chọn cơ sở cụ thể, không được giả mạo thành venue đã xác
minh. Chỉ address/person hoặc text chung không phải một recommendation mới bị
loại khỏi danh sách candidate.

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
  thiểu theo tổng thời lượng activity và transition để xếp hết stop;
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

- `transcript` từ ASR transcript-only cùng source observations do Gemini Text
  hợp nhất từ transcript, OCR và caption/metadata; candidate chỉ được tạo từ
  observations đã validate và có evidence grounded;
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
- lưu proposal/evidence/`sourceActivity` trong `knowledge_graph_import_nodes`;
  không lưu display note ở đây và không tự upsert `places` hoặc graph canonical;
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

TripThemePlanner giữ tên runtime cũ nhưng chỉ chọn điểm nhấn cấp toàn chuyến:

- runtime bỏ qua region statistics khi Explorer đã cung cấp interest,
  must-visit Place hoặc selected Place; statistics chỉ là fallback cho yêu cầu
  khám phá còn mơ hồ và không được quét toàn bộ catalog trong request rõ intent;
- chọn nguồn định hướng theo thứ tự: interest/ràng buộc chuyến hiện tại,
  selected Place đã xác nhận, long-term profile có hiệu lực, rồi mới đến
  special experience đặc trưng của điểm đến;
- catalog chỉ chứa Activity có `SPECIAL_EXPERIENCE`; `TARGETS_PLACE` cung cấp
  anchor trực tiếp và `OFFERS_ACTIVITY` chỉ bổ sung venue cho Activity đó;
- khi catalog có Place cụ thể, backend bảo đảm một bộ giới thiệu bounded; trần
  là một điểm nhấn mỗi ngày và tối đa năm. Catalog rỗng vẫn trả 0 điểm nhấn;
  `must` trên graph là độ quan trọng với điểm đến, không phải lựa chọn do user
  trực tiếp xác nhận;
- không chọn trải nghiệm lệch intent, ví dụ không bắt leo núi khi user chỉ muốn
  văn hóa và đời sống địa phương;
- `requiredExperiences` chỉ chứa highlight có ít nhất một claim ID của chính
  cạnh `SPECIAL_EXPERIENCE`; sau fit/ràng buộc, backend ưu tiên Activity và
  category khác nhau để tránh một danh sách chỉ gồm food/coffee/shopping;
- `tripThemes` luôn rỗng và không còn là quota đầu vào cho PlaceSelector;
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
`requiredExperiences` highlight ở cấp toàn chuyến và giữ `tripThemes=[]`,
không tạo nội dung theo Ngày 1/Ngày 2. PlaceSelector tạo đúng số day slot từ
`tripSpec.days`; route optimizer quyết định activity thuộc ngày nào.

`PlaceSelectionInput` nhận `requiredExperiences`. PlaceSelector resolve
`required_anchor` và `choose_one` thành selected Place bắt buộc trước khi tạo
day slot. `open_candidate` hoặc ID chưa resolve được phải xuất hiện trong
`UnscheduledPlace` với `reasonCode=required_experience_unresolved`; không được
âm thầm bỏ trải nghiệm.

Sau khi validate claim/Place/Activity ID, backend hydrate
`preferredTimeWindows` và `recommendedVisitMinutes` từ recommendation của graph
candidate tương ứng; mọi timing do LLM echo bị ghi đè. PlaceSelector dùng các
window này làm preference mềm: ưu tiên một activity block chứa trọn duration,
nhưng được fallback ngoài window khi không còn window khả thi và phải phát
warning. `openingHours` vẫn là dữ liệu vận hành riêng, không được suy ra từ
recommendation và không loại candidate trong PlaceSelector runtime hiện tại.

PlaceSelector điền item cụ thể:

- mỗi ngày phải giữ đúng ba meal anchor: breakfast, lunch và dinner. MealSelector
  dùng node type `Restaurant` làm nguồn phân loại ưu tiên; `DrinkDessert` không
  được lấp meal anchor. Với place chưa đi qua graph, nhà hàng/quán ăn hoặc venue
  có bằng chứng món chính mới được dùng làm fallback. Category trình bày `food`
  không phải node type và không đủ để xác định một bữa chính;
- mỗi ngày phải có ít nhất hai activity non-food, ưu tiên một activity trước
  lunch và một activity sau lunch; café không được tính vào mức tối thiểu này;
- tối đa một café mỗi ngày, kể cả khi intent chứa cafe hopping;
- ice cream, dessert, juice, tea, bakery và các biến thể provider tương ứng là
  food/drink, không được dùng để lấp meal anchor hoặc activity slot;
- khi thiếu candidate non-food đã xác minh, để lại free-time/warning thay vì
  thay thế bằng một điểm ăn uống không đúng mục đích;

- theme và day-part goal được dùng để tạo shortlist rộng, không còn là ràng buộc
  cứng ngăn activity phù hợp được chuyển sang ngày gần hơn về địa lý;

- với intake có URL hoặc ảnh/OCR, xếp candidate nguồn tương thích trước trong
  từng meal/activity window; chỉ gọi Finder cho gap sau khi không còn candidate
  nguồn phù hợp với window đó;
- PlaceSelector loại suggestion trùng danh tính với toàn bộ stop URL và item đã xếp,
  kể cả khi provider ID khác nhưng tên chuẩn hóa/biến thể alias cho thấy cùng
  một địa điểm;
- số place extractor nhận từ URL không bị giới hạn theo quota của PlaceSelector.
  Selected Place và `finder_suggestion` cùng được xếp theo thời lượng còn trống
  giữa các meal anchor; không áp quota count hoặc pace;
- PlaceSelector dùng theme, day-part goal, region và constraint do Planner tạo để chọn
  địa điểm bù; stop nguồn không bị thay thế và suggestion phải được đánh dấu;
- ở chế độ `route_first`, PlaceSelector tạo khung giờ thật theo
  `preferredTimeWindows` và giữ timing claim làm provenance. Candidate fallback
  buổi tối phải khớp giờ mở cửa đã lưu; thiếu dữ liệu giờ được giữ là unknown;
- rank Place bằng mô tả theo theme/goal của ngày trước, sau đó rerank bằng
  category, tags, region, confidence và các dữ liệu có cấu trúc;
- với activity gap-fill, PlaceSelector bổ sung một bounded graph pool từ
  `Place -> OFFERS_ACTIVITY -> Activity`; Activity khớp interest được hydrate
  thành `activityId`/`sourceActivity`, còn Activity ID hoặc tên chưa xuất hiện
  trong ngày được ưu tiên mềm. Pool này độc lập với `SPECIAL_EXPERIENCE`: cạnh
  special vẫn dành cho điểm nhấn, `OFFERS_ACTIVITY` thông thường chỉ lấp lịch;
- chín Activity tối có identity riêng (`evening_cultural_performance`,
  `live_music`, `evening_city_walk`, `night_market`, `rooftop_city_view`,
  `night_sightseeing_tour`, `nightlife_drink`, `karaoke`,
  `wellness_evening`). Chúng chỉ được dùng làm optional fallback khi window tối
  còn trống, tối đa một item/ngày, và không tạo cạnh `SPECIAL_EXPERIENCE`;
- fallback có kiểm soát lên region cha khi locality nhỏ thiếu Place, nhưng không
  dùng hotel/restaurant/transport để lấp activity sai chủ đề;
- đặt breakfast/lunch/dinner làm anchor cố định, lấp số activity động theo
  duration và transition, rồi tối ưu tuyến và fit lại timeline bằng route leg;
- global optimizer chỉ phân cụm và cân bằng duration theo ngày; route leg chi tiết
  được tính riêng từng ngày, không nối các ngày thành một tuyến liên tục;
- activity overflow được thử chuyển sang đúng một ngày khả thi khác trước khi
  tạo `UnscheduledPlace`;
- stop ăn uống từ URL chiếm meal slot trước và thay thế meal suggestion
  của PlaceSelector; stop URL không được âm thầm loại khi chuyển giữa activity
  pool và meal slot;
- `cafe`/`coffee shop` được chuẩn hóa thành `ontologyType=DrinkDessert`, là stop
  trải nghiệm thuộc activity pool và không được dùng làm
  breakfast/lunch/dinner;
- coffee do Finder thêm tối đa một stop/ngày và bằng 0 nếu ngày đã có coffee từ
  URL; chỉ bỏ giới hạn khi intent nói rõ coffee tour/cafe hopping. Category
  Finder chưa xuất hiện trong ngày được ưu tiên để tăng diversity;
- giữ source ref từ `SelectedPlace` tới `TripItem`;
- tối ưu thứ tự item có tọa độ bằng nearest-neighbour rồi 2-opt;
- batch ordered stop của từng ngày qua Valhalla sau khi xếp stop; Haversine chỉ
  prefilter pedestrian, còn quyết định walk dùng route provider không quá
  1.500 m. Auto batch chạy khi walking không thực dụng hoặc user ưu tiên car; leg provider có
  geometry, `fetchedAt`, `source=valhalla_routing`, `verified=true`, còn lỗi
  provider fallback về ước tính địa lý `verified=false`;
- lấy OpenTripPlanner theo giờ kết thúc stop khi user ưu tiên/bắt buộc transit,
  tránh car mà walking không thực dụng, hoặc road route không khả dụng; không
  gọi OTP mặc định chỉ để tạo alternative;
- chỉ thêm địa điểm mới từ place provider khi cần hoàn thiện ngày và phải đánh
  dấu đây là đề xuất của hệ thống;
- đưa địa điểm không xếp được vào `UnscheduledPlace` với reason code.

Sau khi `PlaceSelectorService` chọn Place mà chưa gọi route leg chi tiết,
`RouteFirstItineraryOptimizer` chạy ở cấp toàn chuyến.
Nó dùng travel-time matrix để giảm tổng thời gian di chuyển bằng cách hoán đổi
activity giữa các ngày rồi tối ưu thứ tự trong ngày. Sau đó `MealStopSelector` cố gắng chèn
ba bữa và lấp activity theo capacity giữa các anchor. MealSelector tải một
candidate pool bounded cho toàn chuyến: `TARGETS_PLACE` của dining
`SPECIAL_EXPERIENCE` được ưu tiên, còn experience có `INVOLVES_ITEM` mở rộng
venue qua `OFFERS_ITEM`. `MealNodePlanner` được gọi tối đa một lần cho toàn
chuyến để chọn FoodItem/DrinkItem từ catalog node có ít nhất một Restaurant
cung cấp; output ngoài catalog, node lặp hoặc day/slot lặp bị loại, rồi backend
resolve venue qua `OFFERS_ITEM`. Nếu provider lỗi hoặc không có venue hợp lệ,
pipeline fail-open về specialty/catalog deterministic. Candidate được phân bổ
theo khung giờ, độ phù hợp, chất lượng và detour địa lý; venue và meal key đã
dùng không được lặp lại. Không gọi Gemini theo từng ngày hoặc retry meal slot. Stop nguồn có
`sourceDay`, `sourceOrder` hoặc provenance URL/OCR được giữ lại; timing nguồn là
constraint ưu tiên và có thể spill khi ngày nguồn hết capacity. Sau bước gợi ý
node, việc phân bổ venue vẫn là heuristic deterministic. Walking/car/transit
route chỉ được enrich sau khi nghiệm cuối đã chốt;
không được mô tả như tối ưu toàn cục. URL và raw prompt không chọn hai thuật toán
planning khác nhau.

Nếu không tìm được Place ăn uống đã xác minh cho một meal slot, PlaceSelector giữ
một generic meal anchor không có `placeId` và ghi warning; nó không giả mạo một
địa điểm ăn đã được xác minh.

`timeWindow` là giờ lịch thật và tham gia candidate selection, kiểm tra opening
hours cùng timeline fitting.

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
- `sourceActivity` là tóm tắt ngắn bằng tiếng Việt về câu chuyện, mẹo hoặc hành
  động tại đúng place mà creator thực sự kể; không sao chép nguyên caption/
  transcript và không tạo câu rỗng nghĩa kiểu “video có nhắc đến địa điểm”. Một
  place story chỉ được lưu khi có evidence span của đúng place chứa thông tin
  có nghĩa ngoài tên place; span được lưu trong `noteSources[].evidence`.
- Extractor có thể tạo `regionStory` riêng khi creator kể về không khí, nhịp đi,
  lời khuyên áp dụng toàn vùng, lý do vùng đáng ghé hoặc cách các điểm kết nối.
  Model phải trả `regionStoryEvidence` là span nguyên văn; backend chỉ nhận khi
  span đó tồn tại trong caption/transcript và không chỉ là tên destination.
  Story hợp lệ được lưu trong `Plan.regionStories`, không nhân bản vào từng item.
- Sau place resolution, composer tạo từng ghi chú nguồn độc lập trong
  `PlanItem.noteSources`: ghi chú video chỉ dùng `sourceActivity` có nội dung
  hữu ích thuộc đúng place. Nếu source không có câu chuyện/mẹo place-specific thì
  UI không hiện source note. Address, rating, review count, opening hours và link
  provider chỉ hiển thị bằng field/UI có cấu trúc, không tạo provider note. Copy
  hiển thị là tiếng Việt và không phát lại caption/transcript hay summary cấp
  hành trình. `PlanItem.notes` gộp chỉ
  được giữ để đọc revision cũ. Bước này không gọi Gemini lần nữa; Gemini có thể
  đã được dùng ở extraction/structuring.
- Không âm thầm bỏ địa điểm đã xác nhận; phải xếp hoặc trả về `UnscheduledPlace`.
- Mỗi ngày có ba meal anchor và số activity phụ thuộc ngân sách thời gian. Restaurant/food URL
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
- Enrichment giá TravelPlace dùng Gemini Google Search grounding qua
  `LLMClient.generate_grounded_structured_json`. Model chỉ đề xuất JSON; code
  kiểm tra exact identity, schema, amount và citation index trước khi cho phép
  lưu. Không có grounded source thì kết quả phải ở trạng thái `ambiguous`.
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
- Pool price research đọc `GEMINI_PRICE_API_KEYS` khi có, nếu không dùng toàn bộ
  key trong `GEMINI_API_KEY`. Client round-robin cả sau request thành công,
  cooldown key trả `429` và disable key trả `401/403`. Nhiều key không mặc định
  làm tăng quota nếu chúng thuộc cùng Google project. Price batch mặc định giãn
  bốn giây giữa thời điểm bắt đầu request để giảm burst RPM. Nếu một outcome chỉ
  còn lỗi quota sau khi client đã thử pool key, worker ngừng claim địa điểm mới,
  chờ các request đang chạy và hoãn phần còn lại tới lần chạy sau.
- Price CLI có thể dùng `--search-provider tavily` khi Gemini Google Search
  grounding không có quota. Tavily chỉ trả search result đã chuẩn hóa; Gemini
  chạy structured output không-grounding và code vẫn xác minh source index/URL.
  Thiếu `TAVILY_API_KEY` phải fail-fast.
- Chỉ cache khi quyền riêng tư, độ mới và phạm vi user cho phép.
- Giữ provider call sau `LLMClient`; domain code không gọi trực tiếp SDK của
  provider.
## Mandatory capacity và phân bổ ngày

Với trip chưa khóa số ngày, Planner không được chạy lại toàn bộ workflow cho
từng phương án 3/4/5/6 ngày. Sau Explorer, TripThemePlanner chọn highlight; các
required experience được resolve rồi gộp với Place từ URL/user thành mandatory
pool. Chỉ lúc đó `ClusterFirstRepairSolver` dùng capacity, meal anchors và
TravelTimeMatrix để chọn số ngày/phân cụm trong bộ nhớ. Suggestion dùng để lấp
gap không tham gia quyết định tăng ngày.

Theme là tín hiệu cấp chuyến đi, không phải contract cấp ngày. Số lượng
`requiredExperiences` không phụ thuộc `tripSpec.days`; các ngày cần đa dạng hoạt
động nhưng không có `dayTheme` bắt buộc. Snapshot Plan mới không phát hành field
`days[].theme`, trong khi revision cũ vẫn đọc được.

Nếu user khóa duration, solver không tự tăng ngày và mandatory overflow phải
xuất hiện trong `unscheduledPlaces`. Sau mandatory allocation, PlaceSelector
phát hiện từng activity/meal gap, query một pool bounded và chỉ commit candidate
thực sự vừa timeline. Suggestion không được chọn không trở thành
`UnscheduledPlace`; candidate `needs_review` vẫn luôn được giữ trong danh sách
này vì đó là cam kết nguồn chưa resolve, không phải suggestion.
