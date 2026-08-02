# Travel Knowledge Graph MVP

## Mục tiêu

Graph mô tả quan hệ giữa khu vực, chủ đề và nhóm trải nghiệm. Nó giúp Planner và
Finder trả lời câu hỏi “một ngày theo chủ đề này nên gồm những loại trải nghiệm
nào?” trước khi structured catalog retrieval tìm Place cụ thể.

Pipeline hiện tại:

```text
user intent + day goal
  -> TravelKnowledgeSearchTool.expand
  -> experience query terms + place category + diversity group
  -> category + metadata retrieval trong catalog Place
  -> popularity/distance rerank
  -> opening hours/duration/route feasibility
  -> Place cụ thể trong timeline
```

Planner cũng gọi graph trong bước kiểm chứng research. Mỗi `themeQuery` được
chuyển thành `experienceEvidence` gồm node đã match, experience node, query term,
category và diversity group. Với chuyến Hà Nội local tối đa ba ngày, bước này
thay cho research LLM riêng; chuyến phức tạp vẫn dùng research LLM rồi kiểm chứng
bằng cùng graph và Place catalog.

Meal query được xử lý riêng. Một ngày tham quan Phố Cổ có thể mở rộng thành đền,
tượng, bảo tàng và kiến trúc; lunch/dinner không quyết định category của activity.

## Schema vận hành

File seed: `backend/app/modules/plans/knowledge_graph/hanoi_graph.v1.json`.

Node bắt buộc có `id`, `kind`, `label`. Node có thể thêm:

- `aliases`: cách user thường gọi node;
- `searchTerms`: cụm từ đưa vào semantic query;
- `placeCategory`: hard category mà Place phải thỏa;
- `diversityGroup`: nhóm không nên lặp trong cùng ngày;
- `weight`: độ ưu tiên mặc định.

Quan hệ v1:

- `SUPPORTS_THEME`: area phù hợp với theme;
- `INCLUDES_EXPERIENCE`: theme gồm các experience;
- `COMPLEMENTS`: hai experience bổ trợ nhau;
- `TOO_SIMILAR`: hai experience dễ tạo lịch lặp.

`JsonTravelKnowledgeSearchTool` hiện traversal `SUPPORTS_THEME` và
`INCLUDES_EXPERIENCE`. Hai relation còn lại được lưu từ v1 để bước sequence
planner có thể dùng mà không đổi schema.

Graph runtime dùng `hanoi_graph.v2.json`. V2 giữ nguyên taxonomy v1 và thêm:

- `sources`: metadata nguồn chuẩn hóa gồm URL, license, `retrievedAt`, content
  hash và loại record; không chứa prose hoặc payload crawl thô;
- `evidenceRefs` trên node: liên kết tới source cùng confidence và phương pháp
  match;
- `sourceEvidence` trong kết quả expansion: bằng chứng Planner đưa vào
  `verifiedResearch`. Finder bỏ qua trường này và tiếp tục dùng query term,
  category cùng diversity group.

Graph v2 được build bằng `crawl_knowledge_travel/build_graph.py`. Builder chỉ
materialize liên kết deterministic từ trường có tín hiệu cao. Một record được
thu thập không đồng nghĩa claim trong record đã được hệ thống xác minh.

Graph loader kiểm tra ID node/source duy nhất, edge không treo và evidence ref
phải trỏ tới source tồn tại. Runtime công bố `supports_region(regionKey)` để
Destination Discovery phân biệt region đã có graph với catalog-only fallback.

Graph không tự chọn destination. Destination Discovery dùng budget, duration,
interest và catalog coverage để xếp hạng region; chỉ sau khi user chọn region,
graph tương ứng mới mở rộng theme thành experience cho Macro Planner/Finder.

## Cách mở rộng an toàn

1. Thêm node/edge vào một file version mới và giữ file cũ để regression test.
2. Thêm persona/test mô tả hành vi mong muốn trước khi nối taxonomy mới vào Finder.
3. Không thêm Place instance bằng tay. Dùng enrichment job để nối Place với
   experience từ category, type/group, tags và curated metadata.
4. Không đưa rating, review hoặc giờ mở cửa vào taxonomy edge; đây là dữ liệu
   vận hành có độ mới và vẫn thuộc Place catalog.
5. Khi chuyển storage, implement lại `TravelKnowledgeSearchTool`; không để Cypher,
   Gremlin hay SQL graph lọt vào Planner/Finder.

## Lộ trình storage

- Giai đoạn 1: JSON versioned trong repo, phù hợp taxonomy Hà Nội nhỏ.
- Giai đoạn 2: PostgreSQL adjacency tables khi cần admin/editor và version runtime.
- Giai đoạn 3: Apache AGE hoặc Neo4j khi cần multi-hop query, explanation path,
  creator knowledge và enrichment hàng loạt.

Chỉ chuyển sang graph database khi query/runtime thực tế vượt khả năng adjacency
JSON/PostgreSQL; provider là quyết định khó đảo ngược và cần ADR riêng.
