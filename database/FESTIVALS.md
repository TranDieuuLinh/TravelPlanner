# Dữ liệu lễ hội Việt Nam

`festivals.csv` là danh mục lễ hội có tổ chức được nhập từ Cổng thông tin điện
tử Lễ hội của Cục Văn hóa cơ sở, Gia đình và Thư viện.

Nguồn chính: <https://lehoi.com.vn/>

## Phạm vi

- Bao gồm lễ hội truyền thống, lễ hội văn hóa, lễ hội ngành nghề và lễ hội có
  nguồn gốc từ nước ngoài.
- Không chủ động thêm ngày nghỉ lễ, ngày kỷ niệm, ngày rằm hoặc ngày văn hóa
  không có một lễ hội cụ thể.
- Giữ nguyên tên, tỉnh và địa điểm do nguồn cung cấp. Dữ liệu nguồn có thể chứa
  lỗi chính tả, bản ghi trùng, tên địa giới cũ hoặc tên tỉnh sau sáp nhập kèm
  địa giới cũ trong ngoặc.
- File `festivals.metadata.json` ghi tổng số bản ghi theo loại và thống kê trường
  bị thiếu. Không tự suy đoán tên hoặc địa điểm để lấp khoảng trống của nguồn.

## Ý nghĩa trường

| Trường | Ý nghĩa |
| --- | --- |
| `source_id` | ID của bản ghi trên Cổng Lễ hội |
| `name` | Tên lễ hội do nguồn công bố |
| `festival_type` | Nhóm lễ hội của nguồn |
| `province_text` | Tên tỉnh/thành dạng văn bản của nguồn |
| `venue_text` | Địa điểm tổ chức dạng văn bản của nguồn |
| `source_url` | Trang chi tiết dùng làm provenance |
| `source_list_url` | Trang danh mục nơi importer tìm thấy bản ghi |
| `retrieved_at` | Thời điểm lấy trang danh mục, UTC |

Khi chạy importer với `--details`, CSV có thêm lịch tổ chức dạng văn bản, quy mô,
đối tượng thờ phụng, phần lễ, phần hội và các trường mô tả khác. Không được diễn
giải `schedule_text` là một occurrence đã được xác nhận cho một năm cụ thể.

## Cập nhật

```powershell
python database/scripts/import_vietnam_festivals.py
```

Nhập toàn bộ trang chi tiết:

```powershell
python database/scripts/import_vietnam_festivals.py --details --workers 4
```

Importer có retry giới hạn, đặt User-Agent nhận diện ứng dụng và nghỉ ngắn giữa
các request. Trước khi phân phối lại dữ liệu hoặc dùng hình ảnh/tư liệu mô tả,
cần xác nhận điều kiện tái sử dụng với đơn vị vận hành nguồn.
