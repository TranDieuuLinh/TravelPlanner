# Task 08: Truy xuất, xác minh và promotion

## Mục tiêu

Bổ sung candidate còn thiếu cho từng pool canonical, giữ trust state rõ ràng và
không dùng external discovery để lấp số lượng.

## Luồng runtime

Coverage được tính sau khi resolve/enrich/evaluate place từ user input và URL.
Nếu một pool chưa đủ target, PlaceChecker tạo tối đa một query Knowledge Graph
cho pool đó:

```text
TravelPlace       12 × days
Restaurant         6 × days
Entertainment      2 × days
DrinkDessert       3 × days
Accommodation      tối đa 3 toàn chuyến
```

Năm query độc lập được batch/concurrent. Metadata của toàn bộ kết quả được
enrich theo batch; sau đó scoring hard-filter identity, ADM, avoid, cost,
duration, operational status và people eligibility rồi rank theo preference và
các signal chất lượng. Candidate key/place ID được dedup toàn cục trước handoff.

Trong một result set, các nguồn sau chỉ là signal, không phải tầng recovery nối
tiếp:

- tag property trực tiếp đã được lọc qua `auto-attach/tags-auto.yml`;
- `Special_Experience` từ ADM;
- `Offer_Item`;
- rating/review và metadata quality.

`Has_Style` không tạo candidate, tag, category, preference match hay quota. Nó
chỉ điền `time_duration` và `time_windows` khi field tương ứng trên entity/item
đang thiếu; property trực tiếp luôn thắng.

Runtime PostgreSQL không cấu hình external source cho targeted retrieval và đặt
external call budget bằng 0. Google Maps chỉ thuộc named-place recovery của Task
03 khi catalog trả zero row.

## Food query và anchor

Food anchors là toàn bộ `TravelPlace` và `Entertainment` đủ điều kiện, có tọa độ
trong pool cuối. Một query PostgreSQL duy nhất trả cả lựa chọn trong 5 km và lựa
chọn toàn ADM. `Special_Near`, computed distance,
`Special_Experience -> FoodItem` và `Offer_Item -> FoodItem` được giữ thành
evidence của cùng result set.

Selector loại avoid conflict và metadata không dùng được, ưu tiên short
preference, cân bằng `FoodItem`, dedup restaurant, rồi kiểm tra:

- đủ breakfast/lunch/dinner cho số ngày;
- target 6 restaurant/ngày;
- diversity món/tag trực tiếp;
- lựa chọn gần các activity anchor; một restaurant có thể cover nhiều anchor
  nhưng chỉ được đếm một lần.

## Xác minh

- Entity đã verify trong Knowledge Graph: `verified_kg`.
- Một external source: `provisional`, không planner-eligible.
- Hai external source độc lập đồng thuận: `verified_external`.
- Source conflict đáng kể: `needs_review`.
- Provider popularity/model confidence không tự verify identity.

Direct-user/URL identity là luồng riêng của Task 03. Provenance `input`/`url`
được giữ sau search; candidate explicit không bị optional ranking loại bỏ, nhưng
conflict vẫn tạo warning/constraint.

## Promotion

Chỉ queue external candidate đã `verified_external`. Worker phải idempotent,
kiểm tra duplicate lần cuối và bảo toàn source/provider/freshness. Checkpoint
hiện chỉ có `InMemoryPromotionOutbox` cho development/test; chưa có durable
promotion worker.

## Test và điều kiện hoàn thành

Test phải chứng minh một query mỗi deficient pool, không external discovery,
batch metadata enrichment, hard avoid, preference ranking, trust state,
promotion idempotency, food anchor/meal coverage và dedup toàn cục.
