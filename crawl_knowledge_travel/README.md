# Travel knowledge source collector

Công cụ này chỉ **thu thập dữ liệu nguồn thật** cho Travel Experience Knowledge
Graph. Collector không suy diễn quan hệ và không đánh dấu dữ liệu là verified.
Bước build riêng chỉ nối nguồn với taxonomy Planner/Finder bằng tín hiệu có cấu
trúc; nó không đưa prose thô hoặc tự tạo Place vào graph.

## Nguồn hiện có

- `wikidata`: entity du lịch, di sản, thiên nhiên và văn hóa tại Việt Nam qua
  Wikidata Query Service; CC0.
- `wikivoyage`: travel guide thuộc category Việt Nam qua MediaWiki API; CC BY-SA.
- `vietnam_travel`: bài viết/itinerary thực tế được phát hiện từ sitemap của
  Vietnam.travel; chỉ dùng làm official reference.
- `unesco`: danh mục và trang chi tiết di sản thế giới/phi vật thể của Việt Nam.
- `dsvh`: danh mục và trang chi tiết từ Cục Di sản Văn hóa; phải ghi nguồn.

## Cài đặt và chạy

```powershell
cd K:\VSF\VSF_TravelPlanner\crawl_knowledge_travel
python -m pip install -r requirements.txt
python collect.py --sources all --limit-per-source 500
```

Thu thập tối đa nguồn cho phép:

```powershell
python collect.py --sources all --limit-per-source 0
```

Riêng Wikivoyage nên chạy chậm hơn vì MediaWiki API có thể siết rate-limit:

```powershell
python collect.py --sources wikivoyage --limit-per-source 500 --delay 4
```

Nên chạy giới hạn trước để kiểm tra robots.txt, tốc độ và dung lượng. Mặc định
có khoảng nghỉ tối thiểu 2,5 giây cộng thêm jitter 0–0,5 giây giữa hai request
liên tiếp tới cùng host. Khi server trả `429`, collector còn tôn trọng
`Retry-After`. Có thể tiếp tục chạy; file normalized được merge bằng record ID
ổn định.

Nếu một category, nhóm truy vấn hoặc trang chi tiết liên tục lỗi, collector ghi
cảnh báo, bỏ qua phần đó và giữ các record đã lấy thành công. Không cố vượt
`robots.txt` hay tiếp tục đập vào một nguồn đang rate-limit.

## Tái xử lý raw mà không gọi mạng

Khi thay đổi parser, có thể dựng lại các record Vietnam.travel và Wikidata từ
raw response đã có mà không tải lại website:

```powershell
python reprocess_raw.py
```

Đây cũng là cách phục hồi một batch nếu lần chạy mạng bị ngắt sau khi raw response
đã được ghi xuống đĩa.

## Kết quả

```text
data/
  raw/<source>/
    <sha256>.bin.gz
    manifest.jsonl
  normalized/
    wikidata.jsonl
    wikivoyage.jsonl
    vietnam_travel.jsonl
    unesco.jsonl
    dsvh.jsonl
```

Mỗi normalized record có:

- source URL và license;
- thời điểm lấy;
- loại record, tiêu đề và ngôn ngữ;
- text/sections hoặc structured payload;
- content hash;
- metadata gốc cần thiết để xử lý downstream.

Raw response được nén và giữ riêng để có thể tái xử lý mà không gọi lại nguồn.
Không commit raw dump lớn vào Git.

## Build graph cho Planner và Finder

```powershell
python build_graph.py
```

Lệnh này lấy taxonomy seed `hanoi_graph.v1.json`, lọc record liên quan Hà Nội và
tạo `hanoi_graph.v2.json`. Graph v2 giữ nguyên các trường vận hành mà Finder cần
(`searchTerms`, `placeCategory`, `diversityGroup`) và thêm evidence có URL,
license, thời điểm lấy, content hash, confidence và node được hỗ trợ cho Planner.

Builder chỉ xét destination hint, admin label, title, URL, Wikidata field và tên
section. `text` và payload thô không được copy vào graph. Quan hệ suy ra bằng
full-text/LLM cần một hàng đợi review riêng trước khi được materialize.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Giới hạn chủ ý

- Không dùng OSM ngoài phạm vi Place/routing Hà Nội.
- Không crawl Google Maps, Tripadvisor, Booking hoặc nội dung không có quyền.
- Không tự tạo dữ liệu mẫu khi nguồn lỗi.
- Không biến thứ tự hiển thị trên trang thành quan hệ itinerary.
- Không đưa output trực tiếp vào Planner trước bước chuẩn hóa/review riêng.
