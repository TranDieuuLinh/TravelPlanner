# Place development data

## Vietnam festivals

Xem [`FESTIVALS.md`](FESTIVALS.md) cho danh mục lễ hội có tổ chức trên toàn
quốc, quy tắc provenance và lệnh cập nhật dữ liệu.

Thư mục này chứa dữ liệu phát triển theo schema mục tiêu trong
`docs/13-database-schema.md`.

- `places.csv`: file import Place được chuyển đổi từ bộ dữ liệu mock bên ngoài;
  đây không phải repository runtime.
- `generated/place_region_statistics.json`: file debug khi chạy thống kê toàn
  catalog thủ công. Cache khu vực của Planner được lưu trong PostgreSQL, không
  dùng file này.

Giờ mở cửa và giá có thể chứa dữ liệu mock. Mỗi record mock trong JSON nguồn
được giữ cờ `isMock` hoặc provenance tương ứng; không được hiển thị như dữ liệu
thực tế đã xác minh.

Import Place vào PostgreSQL:

```powershell
cd backend
$env:DATABASE_URL = "postgresql+psycopg://vsf:vsf@localhost:5432/vsf_travel"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts\import_places_to_postgres.py
```

Mô phỏng Planner lấy thống kê Hà Nội:

```powershell
.\.venv\Scripts\python.exe scripts\run_auto_place_statistics.py --region-key vn,ha-noi
```

Runtime dùng `SqlAlchemyPlaceRepository`. Create/update qua `PlaceCatalogService`
chỉ tăng `revision`, không chạy thống kê. Khi Planner yêu cầu một `region_key`,
tool kiểm tra fingerprint riêng của khu vực và các vùng con:

- fingerprint không đổi: trả snapshot hiện tại trong PostgreSQL;
- fingerprint thay đổi: tạo dòng `place_region_snapshots` mới và cập nhật
  `place_region_catalog_state`;
- thay đổi ở khu vực khác không làm cache đang được yêu cầu hết hạn.
