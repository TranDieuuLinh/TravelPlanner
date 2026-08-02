# ADR-012: Travel Knowledge Graph cho cấu trúc trải nghiệm

- Trạng thái: Đã chấp nhận cho MVP
- Ngày: 2026-08-01

Ghi chú 2026-08-02: ADR-013 thay embedding retrieval bằng graph-first structured
retrieval. Quyết định về taxonomy và interface Knowledge Graph trong ADR này vẫn
còn hiệu lực.

## Bối cảnh

Embedding tìm Place gần ý định người dùng nhưng không biểu diễn tốt quan hệ có cấu
trúc như: Phố Cổ có những loại trải nghiệm nào, đền và tượng bổ trợ nhau ra sao,
hay ba quán bún trong cùng buổi là lặp trải nghiệm. Nếu tiếp tục thêm keyword và
if/else trực tiếp vào Finder, taxonomy sẽ khó mở rộng và không thể giải thích.

## Quyết định

Thêm `TravelKnowledgeSearchTool` làm ranh giới provider cho đồ thị tri thức du lịch.
MVP dùng graph JSON có version tại
`backend/app/modules/plans/knowledge_graph/hanoi_graph.v2.json` và traversal cục bộ.
Graph chứa các node area, theme, experience và các edge như `SUPPORTS_THEME`,
`INCLUDES_EXPERIENCE`, `COMPLEMENTS`, `TOO_SIMILAR`.

V2 giữ taxonomy v1 nhưng gắn evidence từ normalized source record vào node.
Evidence chỉ giữ metadata provenance, license, độ mới và confidence; prose/payload
thô không đi vào graph runtime. Planner nhận evidence qua expansion, còn Finder
chỉ tiêu thụ query term, category và diversity group.

Finder dùng graph để mở rộng mục tiêu activity thành các nhóm trải nghiệm cụ thể
trước khi structured catalog retrieval. Graph cũng cấp `diversityGroup` để tránh
lặp cùng trải nghiệm trong ngày. Category/type/group/tags lấy Place candidate;
rating, review, khoảng cách và feasibility vẫn rerank/kiểm tra sau đó.

Interface không phụ thuộc JSON. Khi dữ liệu lớn hơn, có thể thêm adapter PostgreSQL,
Apache AGE, Neo4j hoặc RDF mà không đổi contract Planner/Finder.

Không đưa tất cả Place vào graph seed bằng tay. Place instance tiếp tục nằm trong
catalog PostgreSQL và được nối động với experience bằng structured metadata. Chỉ
materialize quan hệ Place–Experience khi pipeline enrichment đủ ổn định.

## Hệ quả

- Taxonomy và quan hệ trải nghiệm có version, review và test độc lập.
- Query activity “Phố Cổ” có thể mở rộng sang đền, tượng, bảo tàng và kiến trúc,
  trong khi meal vẫn là truy vấn riêng.
- Dữ liệu seed Hà Nội hiện chỉ là nền MVP, chưa phải ontology du lịch đầy đủ.
- Graph không thay thế rule feasibility như giờ mở cửa, duration, category cứng,
  quyền riêng tư hoặc routing.
