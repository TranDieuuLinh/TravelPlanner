# Chính sách pool sau PlaceChecker

Cập nhật lần cuối: 2026-08-21.

## Ranh giới

PlaceChecker resolve, enrich, filter và tạo candidate pool. Module không gán
ngày, chọn slot cuối hoặc tối ưu route; các quyết định đó thuộc Planner.

Explicit place từ user input và URL giữ provenance xuyên suốt named-place
search. Chúng không bị optional ranking remove; conflict avoid/eligibility vẫn
được báo bằng warning hoặc constraint.

## Named-place

Mỗi mention chạy một query identity chung trên năm entity type:

- `TravelPlace`;
- `Restaurant`;
- `DrinkDessert`;
- `Entertainment`;
- `Accommodation`.

Query match name, alias, address và ADM, trả top-1. Không giả định place từ URL
là TravelPlace. Nếu catalog có row thì dùng row đó; chỉ catalog zero-result mới
gọi Google Maps. Catalog error hoặc top-1 conflict không kích hoạt Maps.

## Optional pool

Sau khi đếm explicit/URL place đủ điều kiện, mỗi deficient pool chạy tối đa một
Knowledge Graph query. Không fan-out theo culture/nature/theme và không external
discovery.

| Pool | Target |
| --- | ---: |
| TravelPlace | 12/ngày |
| Restaurant | 6/ngày |
| Entertainment | 2/ngày |
| DrinkDessert | 3/ngày |
| Accommodation | tối đa 3/toàn chuyến |

Các query độc lập có thể chạy concurrent. Metadata được enrich theo batch;
avoid, eligibility và preference được đánh giá sau khi đủ direct tags và timing.
Candidate được dedup theo canonical place ID trên toàn bộ pool, nên không thể
giúp nhiều quota cùng lúc.

`Special_Experience`, direct tags, `Offer_Item`, rating/review và data quality là
signal trong cùng rank. Không có bucket bắt buộc cho SpecialExperience và không
có phase “special thiếu thì query toàn Hà Nội”; catalog query đã trả candidate
toàn ADM trong một lượt.

Activity scoring chỉ dùng canonical key từ `auto-attach/tags-auto.yml` cho ba
quyết định preference, avoid và diversity. Tag/alias đọc từ Knowledge Graph
được resolve qua catalog runtime trước khi scoring; tag kỹ thuật hoặc group khác
không đi vào công thức. Avoid là hard filter. Phần preference của một candidate
bằng `số canonical tag khớp / tổng canonical tag của candidate`, vì vậy một
địa điểm có nhiều tag không được cộng toàn bộ điểm chỉ vì trùng một tag.

TravelPlace được rerank tham lam theo độ mới của tag. Mỗi tag đóng góp
`1 / (1 + số lần tag đã được chọn)` và điểm diversity của candidate là trung
bình các đóng góp đó. Các TravelPlace direct/URL đã có trong pool cũng khởi tạo
bộ đếm. Tổng trọng số activity là 85% core quality/fit, 10% preference và 5%
tag diversity. Sau rerank, quota entity type chỉ cắt theo đúng thứ tự này; không
còn vòng chia bucket theo `pool_category` làm thay đổi kết quả tag diversity.

## Time và HasStyle

Mọi entity/item dùng `time_duration` và `time_windows` trực tiếp trước. Chỉ field
nào thiếu mới kế thừa từ `Has_Style` priority cao nhất có field đó.
`Has_Style` không tạo tag, semantic style, candidate, category, preference match
hoặc quota.

Entertainment optional phải có window giao buổi tối từ 18:00. DrinkDessert
optional phải có window giao ban ngày 07:00–18:00. Hai nhóm được cap riêng rồi
mới gộp vào `entertainment[]` với `entityType`.

Trước khi tạo compact pool, category thô `TravelPlace` được đối chiếu thêm với
tên, tag, pool category và provider note. Venue có provider category `Art
center` được chiếu thành `Entertainment`; rule này bao phủ Mango Art và các art
center tương đương mà không thay đổi `entity_type` trong Knowledge Graph.

Generic Knowledge Graph discovery bỏ qua entity có property
`generic_discovery_excluded=true`. Cờ này dùng cho shop, showroom, trường/lớp
hoặc dịch vụ không phù hợp làm gợi ý du lịch đại trà; named-place lookup không
áp dụng cờ nên yêu cầu gọi đúng tên vẫn có thể resolve entity. Night market vẫn
thuộc `TravelPlace`.

Candidate generation trong PostgreSQL dùng cùng Bayesian reputation semantics
với scoring downstream: prior mean và prior weight được tính trên scoped pool,
sau đó kết hợp adjusted rating với review reliability trước khi giới hạn top-K.
Rating thô chỉ còn là dữ liệu đầu vào, không còn là khóa sort ưu tiên khiến điểm
ít review đẩy landmark phổ biến khỏi cửa sổ retrieval.

Semantic category chỉ dùng tên món ăn để sửa node nguồn `TravelPlace`; node đã
là `Entertainment` không bị đổi thành `Restaurant`. Riêng token phở được kiểm
tra trên Unicode gốc để phân biệt `Phở`/`Pho` với `Phố` trước khi bỏ dấu.

Named-place lookup dùng alias curated với `normalized_alias` theo cùng policy
ASCII của query. Alias hiển thị giữ dấu và language; alias mojibake hoặc alias
địa danh sai phải được xóa chọn lọc, không xóa hàng loạt alias hợp lệ.
Alias curation không kiêm identity merge hay generic-discovery exclusion. Khi
hai entity cùng chỉ một địa điểm, kiểm tra alias có thể xác nhận đúng địa điểm
vật lý nhưng dedupe/status vẫn phải được review và áp dụng riêng theo exact ID.

## Food coverage

Food anchors là mọi TravelPlace và Entertainment đủ điều kiện, có tọa độ trong
pool cuối. Không tạo anchor cluster giả và không dùng Restaurant, DrinkDessert
hoặc Accommodation làm anchor.

Một query food duy nhất trả cả restaurant gần anchor (5 km) và restaurant toàn
ADM. `Special_Near`, computed distance, `Special_Experience -> FoodItem` và
`Offer_Item -> FoodItem` là evidence cùng result set. Selector:

- hard-filter avoid, closed/people/data eligibility;
- ưu tiên short preference qua FoodItem, restaurant name và direct tags;
- đảm bảo breakfast/lunch/dinner cho từng ngày;
- ưu tiên FoodItem chưa dùng trước khi lặp món, đồng thời cân bằng anchor;
- chỉ chọn mỗi Restaurant một lần trên toàn pool;
- cho phép một restaurant cover nhiều anchor nhưng chỉ đếm một candidate.

Target food là 6 restaurant/ngày. Meal feasibility là ba slot/ngày và được trả
riêng trong `foodCoverage`; số restaurant và số meal slot không phải cùng một
khái niệm.

## Tag và output

Mọi public tag phải là key runtime từ `auto-attach/tags-auto.yml`; catalog đọc
lại file khi resolve/filter/scoring nên thay đổi taxonomy không cần restart
backend. Technical provenance và relationship type nằm ở field riêng, không giả
thành tag.

Planner tiếp tục nhận score, coordinates, cost, opening/time preference,
verification, relationships, food coverage và source provenance để chọn lịch
khả thi.
