# ADR-011: Semantic retrieval cho Finder bằng Gemini Embedding và pgvector

- Trạng thái: Đã chấp nhận
- Ngày: 2026-08-01

## Bối cảnh

Finder hiện lọc địa điểm bằng category và từ khóa rồi ưu tiên rating/review. Cách
này loại được nhiều sai khác cấp category, nhưng vẫn có thể chọn một nhà hàng quốc
tế rất nổi tiếng cho yêu cầu như “ẩm thực truyền thống Hà Nội”. Popularity là tín
hiệu chất lượng, không phải bằng chứng rằng địa điểm đúng ý định của user.

Catalog hiện nằm trong PostgreSQL và riêng Hà Nội có hơn hai mươi nghìn địa điểm
active. Vector phải có version và có thể tạo lại khi nội dung địa điểm thay đổi.

## Quyết định

Finder dùng pipeline hybrid theo thứ tự:

1. Lọc cứng theo trạng thái active, vùng/bbox, category và danh sách loại trừ.
2. Tạo query embedding và dùng cosine similarity lấy semantic top-K chỉ trong tập
   ID đã vượt qua lọc cứng.
3. Rerank shortlist bằng semantic score làm tín hiệu chính; rating, số review,
   structured relevance và khoảng cách là tín hiệu thứ cấp.
4. Finder tiếp tục kiểm tra giờ mở cửa, duration, constraint và feasibility trước
   khi commit item vào timeline.

PostgreSQL dùng extension pgvector, cột `vector(768)` và HNSW cosine. Provider mặc
định là `gemini-embedding-2` với 768 chiều, nằm sau `EmbeddingClient`. Mỗi vector
lưu `embeddingModel`, `embeddingContentHash` và `embeddedAt`. Text document chỉ
gồm dữ liệu địa điểm chuẩn hóa cần cho retrieval, không gồm prompt/user profile.

Backfill ưu tiên địa điểm có nhiều review/rating để sớm có coverage cho nhóm địa
điểm nổi tiếng. Không được gửi catalog tới provider bên ngoài nếu môi trường/chủ
dữ liệu chưa cho phép. Khi provider hoặc vector chưa sẵn sàng, Finder fallback về
lexical retrieval hiện tại và không làm thất bại toàn bộ plan.

## Hệ quả

- Địa điểm sai chủ đề không còn thắng chỉ nhờ rating/review cao.
- Popularity vẫn có ảnh hưởng mạnh giữa các địa điểm gần nhau về ngữ nghĩa.
- Nội dung thay đổi làm vector stale và cần backfill lại theo content hash/time.
- Local/CI không có API key vẫn chạy được bằng fallback và fake embedding trong
  test.
- Provider ngoài tạo thêm chi phí, độ trễ và nghĩa vụ kiểm soát dữ liệu gửi đi.
