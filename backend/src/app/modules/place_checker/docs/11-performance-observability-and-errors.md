# Task 11: Performance, observability và xử lý lỗi

Cập nhật lần cuối: 2026-08-17.

## Mục tiêu

Đảm bảo PlaceChecker có giới hạn tài nguyên, dễ chẩn đoán và chịu được lỗi cục
bộ từ source/tool.

## Chính sách hiệu năng

- Batch ADM, identity và metadata KG query.
- Cache ADM resolution, identity result và metadata với freshness phù hợp.
- Không search lại entity đã verify và còn fresh.
- Giới hạn candidate trước khi enrichment tốn chi phí.
- Áp external call budget và top-K budget cho từng gap.
- Không chạy N x N route matrix; detailed routing thuộc downstream.
- Dùng bounded concurrency và database session tách biệt khi cần.

## Chính sách lỗi

Place-level failure tạo structured finding và cho candidate khác tiếp tục.
Request-level failure chỉ dành cho core input sai hoặc destination context không
thể dùng. KG/internal/external timeout trả partial output khi an toàn. Unknown
cost/opening giữ nguyên unknown. Promotion failure không rollback planning output.

## Khả năng quan sát

Ghi planning run stage, correlation ID, latency theo phase, KG hit rate, cache
hit rate, external fallback/corroboration rate, ambiguity, gap resolution,
unknown-cost ratio và promotion failure.

Log không được chứa raw third-party payload, full prompt, secret hoặc dữ liệu cá
nhân không cần thiết. Chỉ persist normalized provenance và freshness.

## Test và điều kiện hoàn thành

Test từng loại timeout, partial output, call limit, cache behavior, concurrency
bound, log đã redact và correlation metadata ổn định. Hoàn thành khi lỗi một
source/place không thể làm crash request vẫn còn dữ liệu sử dụng được.

## Hiện thực tại Checkpoint 6

- Giới hạn input: 100 place, 50 item và 200 URL note mỗi request.
- Runtime PostgreSQL giới hạn entity resolution ở 2 call song song và pool đọc
  Knowledge Graph của PlaceChecker ở tối đa 2 connection trên mỗi process.
  Item resolution vẫn có semaphore riêng nhưng mọi query cùng chia sẻ pool này.
- Entity resolution gom tối đa 10 tên vào một SQL call; 50 tên thường thành 5
  batch và tối đa 2 batch chạy đồng thời.
- Google Maps Playwright dùng limiter dùng chung trên adapter, tối đa 2 search
  đồng thời; limiter trang chi tiết vẫn áp dụng bên trong từng search. Mỗi
  PlaceChecker request chỉ gọi external retrieval cho tối đa 2 gap và mỗi gap
  chỉ dùng anchor đầu tiên.
- Targeted KG retrieval chỉ dùng 1 anchor đại diện mỗi gap, tránh số SQL
  call tăng theo phép nhân giữa toàn bộ place đầu vào và toàn bộ gap.
- Runtime dùng coverage hiện có để chỉ tạo reserve query theo shortfall, thay vì
  luôn chạy toàn bộ core/theme pool. Các query cùng ADM, type và top-K được gom
  tối đa 10 query mỗi SQL batch, chạy tối đa 2 batch đồng thời. Candidate từ
  tất cả gap được deduplicate và load metadata trong một lượt `get_many`.
- Retrieval chỉ giữ top-K, tối đa hai external provider và dừng khi đã đủ
  candidate verify. Kết quả top-K từ KG được dùng ngay; external Playwright chỉ
  chạy khi KG không trả candidate phù hợp nào. Không có distance matrix N x N.
- Với nhiều branch trùng tên, `addressHint` được dùng để xếp hạng/chọn branch;
  nếu input không có address hint thì chọn kết quả KG đầu tiên.
- Có wrapper cache TTL cho ADM, named/requirement search và metadata batch.
  Provider error không được cache; metadata chỉ query ID còn thiếu.
- Output metadata có request ID, correlation ID, tổng latency, latency theo
  phase, tool-call summary và cờ partial.
- Metrics port ghi duration, checked/eligible count, open gap, unresolved count,
  external search count và unknown-cost ratio. Lỗi metrics không làm request lỗi.
- Provider/place/promotion failure trả partial result hoặc warning có cấu trúc;
  không log raw payload, full prompt hay secret.

Cache hiện là in-process wrapper và metrics adapter hiện là in-memory cho test.
Durable/distributed cache, metrics backend và planning-run persistence thuộc
runtime infrastructure, chưa được mô tả là production-ready.
