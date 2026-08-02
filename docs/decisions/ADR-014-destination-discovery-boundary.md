# ADR-014: Tách Destination Discovery khỏi core Planner

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-02

## Bối cảnh

Core Planner từng chạy `region_overview`, `constraint_research` và
`festival_discovery` rồi đưa toàn bộ kết quả vào prompt. Các tool này trùng một
phần với catalog snapshot, chỉ ảnh hưởng gián tiếp qua LLM và làm ranh giới giữa
hai câu hỏi bị mờ: “nên đi đâu?” và “đã chọn nơi rồi thì đi như thế nào?”.

Knowledge Graph giải thích theme và experience nhưng không phải nguồn sự thật cho
giá, giờ mở cửa, route hoặc độ mới của Place. Graph Hà Nội v2 hiện cũng chưa phủ
mọi destination.

## Quyết định

Tách hai use case:

```text
Destination Discovery
  -> xếp hạng region từ budget/duration/interests/catalog coverage
  -> user chọn destination
  -> Knowledge Graph tạo experience structure
  -> Macro Planner tạo DayBrief
  -> Finder chọn Place và kiểm tra feasibility
```

Core Planner chỉ thu thập catalog capability và tourism-zone evidence. Nó không
gọi `RegionOverviewTool`, `ConstraintResearchTool` hoặc
`FestivalDiscoveryTool`. `RepositoryPlannerResearchTool` tiếp tục kiểm chứng
graph expansion bằng Place active; Finder tiếp tục sở hữu Place cụ thể, thời gian
và route.

Destination Discovery trả `DestinationProposal` có score, catalog coverage,
interest match, graph coverage và ước tính activity cost. Khi chưa có provider
transport/accommodation, response phải công bố assumption và không mô tả con số
đó như tổng chi phí chuyến đi.

Các research tool cũ có thể còn tồn tại tạm thời trong admin diagnostics để so
sánh dữ liệu, nhưng không thuộc runtime macro-planning.

## Hệ quả

- Prompt Planner nhỏ hơn và ít evidence advisory trùng lặp.
- Câu hỏi mở như “ba triệu nên đi đâu?” có contract riêng.
- Destination chưa có graph vẫn có thể được Discovery đề xuất nhưng phải mang
  warning; không được giả vờ có graph coverage.
- Cần bổ sung transport/accommodation provider trước khi Discovery xác nhận tổng
  ngân sách end-to-end.
