# Golden Dataset cho TravelPlanner

Bộ dữ liệu chuẩn (Golden Dataset) dùng để kiểm thử độc lập Input/Output của từng module (Extractor, Explorer, Planner, Finder, Checker, Backup Plan) và kiểm thử toàn trình E2E trong TravelPlanner.

## Cấu trúc Thư mục

```text
database/golden_dataset/
├── README.md                     # Tài liệu hướng dẫn sử dụng & quy chuẩn
├── extractor_cases.json          # Test cases cho Module trích xuất (Audio STT, OCR, URL Reels)
├── explorer_cases.json           # Test cases cho Explorer Agent (Chuẩn hóa ý định, preferences)
├── planner_cases.json            # Test cases cho Planner Agent (Kế hoạch vĩ mô MacroPlan & DayBriefs)
├── finder_cases.json             # Test cases cho Finder Agent (Lịch trình chi tiết, timeWindow, routes)
├── checker_backup_cases.json     # Test cases cho Checker & Backup Plan Workflow
└── full_pipeline_cases.json      # Test cases cho End-to-End Pipeline (Từ Prompt/URL đến Final Plan)
```

## Cấu trúc Một Case Kiểm thử (Schema Format)

Mỗi file JSON chứa danh sách các `cases` với cấu trúc chuẩn sau:

- `id`: Mã định danh case duy nhất (ví dụ: `EXT-001`, `EXP-001`, `PLN-001`, `FND-001`, `CHK-001`, `E2E-001`).
- `scenarioName`: Tên ngắn gọn của kịch bản.
- `scenarioPurpose`: Mô tả mục đích thử nghiệm và bối cảnh (Ví dụ: Kiểm tra xử lý ràng buộc mâu thuẫn, kiểm tra bổ sung catalog khi ngày thưa...).
- `category`: Phân loại test (`standard_flow`, `multi_day`, `url_reels_integration`, `constraint_conflict`, `sparse_catalog`, `overcrowded_pace`, `backup_recovery`).
- `input`: Payload dữ liệu đầu vào chuẩn theo DTO contract (`agent_contracts.py`).
- `goldenOutput`: Payload dữ liệu đầu ra kỳ vọng (Ground Truth).
- `assertions`: Danh sách các tiêu chí kiểm tra bắt buộc (rule-based validation criteria).

## Cách Sử dụng trong Pytest / Evaluation Script

Có thể load dữ liệu từ các file này trong pytest hoặc trong các
script đánh giá `scripts/evaluate_theme_selector.py` và
`scripts/evaluate_route_first_place_selector.py`:

```python
import json
from pathlib import Path

def load_golden_cases(module_filename: str):
    path = Path("database/golden_dataset") / module_filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["cases"]
```
