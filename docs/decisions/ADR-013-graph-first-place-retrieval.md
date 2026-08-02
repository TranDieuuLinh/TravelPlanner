# ADR-013: Graph-first Place retrieval không phụ thuộc embedding

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-02
- Thay thế phần runtime retrieval của: ADR-011

## Bối cảnh

Catalog hiện có khoảng 32.000 Place nhưng chỉ khoảng 400 record có description.
Embedding document từ dữ liệu mô tả thưa tạo độ phủ không đồng đều, trong khi
Finder đã có Knowledge Graph để mở rộng theme/goal thành experience query terms,
category và diversity group. Duy trì Gemini query embedding cùng pgvector ranking
trong runtime làm tăng provider dependency và khiến kết quả phụ thuộc vào tiến độ
backfill hơn là evidence có cấu trúc.

## Quyết định

Planner và Finder không khởi tạo hoặc gọi embedding client trong runtime.
Retrieval Place dùng pipeline:

```text
Knowledge Graph expansion
  -> active/region/bbox/category hard filters
  -> structured relevance từ type/group/tags/name/region
  -> rating/review/confidence/distance rerank
  -> opening-hours, duration, constraint và route feasibility
```

Description là evidence phụ, không phải điều kiện để candidate được retrieve.
Tourism-zone anchor cũng dùng graph region evidence, capability metadata,
popularity và compactness thay vì cosine similarity.

Cột embedding, repository method và backfill script được giữ trong giai đoạn
chuyển tiếp để không cần migration phá hủy dữ liệu và không làm gián đoạn job đang
chạy. Chúng không được dependency wiring của Planner/Finder sử dụng.

## Hệ quả

- Runtime Planner/Finder không phụ thuộc Gemini Embedding hoặc mức độ hoàn tất
  của backfill.
- Place không có description vẫn có thể được chọn từ category và metadata.
- Chất lượng phụ thuộc mạnh hơn vào taxonomy Graph, category mapping, tags,
  placeGroup và dữ liệu geographic/operational.
- Cần theo dõi độ phủ metadata có cấu trúc và mở rộng graph theo region thay vì
  dùng vector similarity làm fallback mặc định.
