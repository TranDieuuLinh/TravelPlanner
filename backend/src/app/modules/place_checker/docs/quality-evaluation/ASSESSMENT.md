# Đánh giá chất lượng PlaceChecker với dữ liệu thật

Ngày chạy: 2026-08-12.

## Phạm vi

Bộ đánh giá dùng 9 output giả lập của Explorer và chạy qua
`build_postgres_place_checker_pipeline` với Knowledge Graph PostgreSQL hiện tại.
Mỗi ca có input và full output riêng trong `inputs/` và `outputs/`. File
`summary.json` là bản rút gọn để so sánh nhanh.

## Kết quả tổng quan

| Ca | Kết quả | Eligible | Nhận xét chính |
| --- | --- | ---: | --- |
| 01 Nguồn hỗn hợp hợp lệ | conditional | 40 | Resolve đúng Phở Bát Đàn, Café Giảng và Hồ Tây; pool đủ lớn cho 4 ngày |
| 02 Trùng nguồn và sai chính tả | conditional | 31 | Gộp provenance, giữ candidate lỗi ở trạng thái unresolved và không block direct place |
| 03 Chỉ có item | conditional | 30 | Cả ba item resolve và tạo được pool ăn/chơi tương đối đủ |
| 04 Gia đình, ngân sách thấp | conditional | 20 | Đủ pool tối thiểu cho 2 ngày; suitability còn thiếu nhiều dữ liệu |
| 05 Direct place xung đột avoid | conditional | 20 | Giữ Tạ Hiện vì người dùng yêu cầu trực tiếp và phát hiện xung đột avoid |
| 06 Địa điểm sai thành phố | blocked | 21 | Chặn đúng Dinh Độc Lập trong chuyến Hà Nội, vẫn giữ pool chẩn đoán |
| 07 Candidate lỗi cục bộ | partial | 20 | Bỏ đúng candidate lỗi và tiếp tục toàn request |
| 08 Destination không tồn tại | blocked | 1 | Dừng đúng, không tìm toàn cầu |
| 09 Chuyến 7 ngày quá ít input | conditional | 60 | Đạt trần pool 60, resolve Lăng Bác; vẫn cần bước chọn cụm trước khi lập lịch |

Không còn ca nào làm pipeline văng lỗi. Trong lần chạy đầu, ca 09 phát hiện
contract `rank <= 10` sai khi gộp nhiều gap; giới hạn này đã được bỏ và có test
hồi quy.

## Điểm mạnh

1. Contract camelCase của Explorer được parse đúng; `urlNotes=null` hoạt động.
2. Candidate lỗi cục bộ không làm hỏng cả request.
3. ADM không rõ và địa điểm sai ADM được chặn đúng.
4. Địa chỉ phân biệt đúng chi nhánh Café Giảng; tên đầy đủ cũng phân biệt được Lăng Bác với Bảo tàng Hồ Chí Minh.
5. Item resolution trả selected venue và tối đa bốn alternatives.
6. Direct-user place được giữ, còn candidate bổ sung có verification và score.
7. Pool có nhiều nhóm trải nghiệm hơn trước và không còn dồn toàn bộ vào cắm trại.
8. Unknown cost/duration được giữ là unknown, không biến thành 0 hoặc miễn phí.

## Vấn đề chất lượng

### P1 - Khoảng cách và cụm địa lý

Pool vẫn có thể bị `dispersed`, nhưng bán kính đã giảm còn khoảng 15-22 km ở
các ca có dữ liệu. Candidate xa điểm neo không bị loại khỏi pool; candidate
cách 8-15 km bị phạt và được giữ như phương án dự phòng. Bước tiếp theo vẫn
là gom 2-4 cụm và để PlaceSelector chọn một cụm chính cho mỗi ngày.

Đề xuất: tạo 2-4 cụm theo tọa độ, giữ quota theo cụm gần mandatory anchors và
chặn optional outlier khi pool trong cụm đã đủ.

### Đã xử lý - Identity ambiguity của địa điểm nổi tiếng

`Ho Chi Minh Mausoleum`/`Ho Chi Minh's Mausoleum` trước đây có thể bị unresolved
dù KG có entity đúng. Hiện công cụ dùng độ phủ token, tên đặc trưng, địa chỉ và
ngữ cảnh tuyến để phân biệt; ca đánh giá mới đã resolve được Lăng Bác.

Vẫn cần bổ sung alias/canonical ID tốt hơn trong KG cho các địa điểm có nhiều chi
nhánh hoặc tên gần nhau.

### Đã xử lý - Avoid và taxonomy song ngữ

`shortAvoids=[nightlife, alcohol]` hiện đã khớp được tag tiếng Việt như `Trải
nghiệm đồ uống buổi tối`, `bia`, `cocktail`. Tạ Hiện vẫn được giữ đúng vì là
direct-user, nhưng output có warning xung đột; candidate bổ sung thì bị loại.

Tiếp tục mở rộng bảng taxonomy khi Knowledge Graph có thêm nhãn mới.

### P1 - Pool còn entity phân loại sai

`Vietnam Treasures Travel` và một số địa điểm dạng nhà hàng/khu dịch vụ vẫn lọt
pool do dữ liệu nguồn gắn `TravelPlace` hoặc `Special_Experience` chưa chuẩn.

Đề xuất: thêm curation status/venue subtype trong KG; không dùng blacklist tên
làm giải pháp chính.

### P1 - Item match còn quá rộng

`cà phê trứng` chọn `Cà Phê Trang`; chưa có bằng chứng rõ venue thực sự phục vụ
cà phê trứng. `múa rối nước` ưu tiên Đào Thục dù có thể quá xa trung tâm. Match
hiện thiên về token/category hơn claim món/hoạt động cụ thể và khoảng cách.

Đề xuất: yêu cầu exact `Offer_Item`/`Special_Experience` cho requirement cụ thể,
sau đó mới fallback semantic; rerank item theo anchor/cụm trung tâm.

### P1 - Budget chưa đủ dữ liệu

Các ca thường có 6-12 địa điểm unknown cost nên budget status là `unknown` hoặc
`at_risk`. Đây là hành vi an toàn, nhưng chưa giúp Final Planner nhiều.

Đã giữ budget là soft ranking khi tạo pool; không tạo số tiền giả khi dữ liệu
thiếu. Cần bổ sung dữ liệu giá nếu muốn Planner tính tổng chính xác hơn. Chỉ
hard-filter khi Explorer truyền explicit hard limit cho từng địa điểm/người.

### P1 - Family suitability còn yếu

Pipeline tạo đúng gap `people_accessibility`, nhưng nhiều optional candidate vẫn
eligible khi suitability là unknown. Điều này đúng theo policy không bịa dữ
liệu, nhưng Final Planner không nên coi unknown là family-friendly.

Đề xuất: family trip chỉ đưa candidate unknown vào reserve tier, sau candidate
đã xác minh phù hợp trẻ em.

## Chấm điểm hiện tại

| Hạng mục | Điểm / 10 |
| --- | ---: |
| Contract và khả năng chịu lỗi | 9 |
| Resolve ADM và chặn sai thành phố | 9 |
| Resolve identity địa điểm | 8 |
| Item resolution | 6 |
| Độ đa dạng pool | 7 |
| Chất lượng địa lý | 5 |
| Preferences/avoids | 8 |
| Budget | 5 |
| Family/accessibility | 4 |
| Quan sát và giải thích output | 8 |

**Điểm tổng hợp: 7/10.** Module phù hợp để development và làm nguồn candidate
cho một PlaceSelector mạnh. Chưa nên để Final Planner lấy toàn bộ eligible IDs
và xếp lịch trực tiếp mà không có bước chọn cụm, lọc chất lượng và giới hạn số
địa điểm.

## Thứ tự cải thiện đề xuất

1. Implement PlaceSelector: chọn candidate theo cụm, slot sáng/tối và giới hạn số điểm.
2. Áp quota 70/30 sáng, 60/40 tối và 80/20 preference/exploration ở PlaceSelector.
3. Siết item bằng quan hệ món/trải nghiệm cụ thể.
4. Thêm quality tier và curation status từ KG.
6. Bổ sung cost, duration và family suitability.

## Giới hạn hiện tại của flow sau

PlaceChecker đã tạo pool và trả đủ tag `experience:*`, `item:*`, preference,
tọa độ, chi phí, thời gian và provenance. Tuy nhiên `ItineraryPlanner` hiện tại
vẫn là bản nền: nó chia các địa điểm được nhận theo vòng tròn vào các ngày, chưa
phải PlaceSelector áp quota. Vì vậy không nên đánh giá lịch cuối từ endpoint hiện
tại là đã áp 70/30 hoặc 60/40; cần thêm PlaceSelector trước bước xếp timeline.

## Chạy lại

```bash
docker run --rm \
  --network travelplanner-develop-ver-2_default \
  -e DATABASE_URL=postgresql://travelplanner:travelplanner@postgres:5432/travelplanner \
  -e PYTHONPATH=/app/src \
  -v "$PWD/backend/src:/app/src:ro" \
  -v "$PWD/backend/scripts:/work/scripts:ro" \
  -v "$PWD/backend/src/app/modules/place_checker/docs/quality-evaluation:/work/results" \
  travelplanner-develop-ver-2-backend \
  python /work/scripts/place_checker_quality_eval.py --output-dir /work/results
```
