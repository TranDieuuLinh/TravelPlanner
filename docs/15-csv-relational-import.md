# Hướng dẫn import dữ liệu Google Maps (csv_relational) vào PostgreSQL

Tài liệu này mô tả quy trình thay thế dữ liệu `places` hiện tại trong
PostgreSQL bằng dataset `csv_relational/` sinh ra từ pipeline
`auto-crawl/read_parquet`. Quy trình gồm migration schema và script
importer idempotent.

## ⚠️ Cảnh báo

Đây là thao tác **phá hủy dữ liệu**: migration `20260731_0002`
xóa và tạo lại bảng `places`,
`user_visited_places`, và rename bảng `reviews` của marketplace thành
`marketplace_reviews`. Dữ liệu `reviews` của Google Maps Place được ghi
vào bảng `reviews` mới.

Nội dung các bảng **CHỈ CÓ THỂ** được khôi phục nếu bạn đã backup. Hãy
chạy `pg_dump` trước khi apply migration.

## 1. Backup (bắt buộc)

```powershell
cd K:\VSF\VSF_TravelPlanner\backend
$env:DATABASE_URL = "postgresql://vsf:vsf@localhost:5432/vsf_travel"
pg_dump --no-owner --format=custom --file=..\database\backup_before_google_maps.dump $env:DATABASE_URL
```

(Thay URL cho đúng môi trường của bạn.)

## 2. Cập nhật model

File `backend/app/modules/places/model.py` và
`backend/app/modules/marketplace/model.py` đã được cập nhật cho schema
mới. Các thay đổi chính:

* `places.id` mở rộng từ `VARCHAR(36)` thành `VARCHAR(96)` để chứa Google
  Place ID.
* Thêm cột `places.source_platform`, `places.source_link`, `places.plus_code`,
  `places.rating`, `places.review_count`.
* Thêm 4 bảng con: `place_amenities`, `place_opening_hours`,
  `place_images`, `reviews` (Google Maps place reviews).
* Bảng `reviews` của marketplace được rename thành `marketplace_reviews`.

## 3. Apply migration

```powershell
cd K:\VSF\VSF_TravelPlanner\backend
$env:DATABASE_URL = "postgresql+psycopg://vsf:vsf@localhost:5432/vsf_travel"
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Migration `20260731_0002_replace_places_with_google_csv` sẽ chạy. Nếu
fail vì ràng buộc còn sót, hãy dừng lại và xem log; **không xóa thủ
công các bảng** vì có thể phá vỡ transaction của migration.

## 4. Dry-run import (khuyến nghị)

```powershell
.\.venv\Scripts\python.exe scripts\import_google_places_to_postgres.py --dry-run --limit 100
```

Lệnh này parse 100 dòng đầu của mỗi CSV và in ra summary. Kiểm tra:

* Số dòng sẽ insert vào `places`, `place_opening_hours`, `place_amenities`,
  `place_images`, `reviews`.
* Số dòng bị skip (thiếu lat/lng, thiếu tên, …).
* Không có lỗi parse.

## 5. Import đầy đủ

```powershell
.\.venv\Scripts\python.exe scripts\import_google_places_to_postgres.py
```

Script là idempotent: chạy lại sẽ bỏ qua các dòng đã tồn tại nhờ
`ON CONFLICT DO NOTHING` trên mỗi unique constraint.

Sau khi import, mỗi `place` sẽ có `opening_hours` được populate lại từ
bảng `place_opening_hours` đúng contract mà Planner mong đợi.

## 6. Kiểm tra thống kê vùng

```powershell
.\.venv\Scripts\python.exe scripts\run_auto_place_statistics.py --region-key vn,ha-noi --force
```

Lệnh này kiểm tra việc tính thống kê theo `region_key`. Kết quả runtime được
tính trực tiếp từ `places`; không còn ghi cache vào bảng PostgreSQL.

## 7. Kiểm tra

Một số query hữu ích:

```sql
-- Tổng số place
SELECT COUNT(*) FROM places;

-- Phân bố theo khu vực
SELECT region_key, COUNT(*) FROM places GROUP BY region_key ORDER BY 2 DESC LIMIT 10;

-- Top 10 place có rating cao nhất
SELECT name, rating, review_count, primary_area
  FROM places
  WHERE rating IS NOT NULL
  ORDER BY rating DESC, review_count DESC
  LIMIT 10;

-- Số review của Google Maps
SELECT COUNT(*) FROM reviews;

-- Số amenities trung bình / place
SELECT AVG(c) FROM (
  SELECT place_id, COUNT(*) AS c
    FROM place_amenities
    GROUP BY place_id
) t;

-- Demo places đã được seed lại
SELECT id, name FROM places WHERE id LIKE 'demo-visited-%';
```

## 8. Lệnh rollback

Nếu cần quay lại schema cũ, dùng `pg_dump` đã backup ở bước 1:

```powershell
# Restore lại
pg_restore --clean --no-owner --dbname=vsf_travel `
  ..\database\backup_before_google_maps.dump
```

Hoặc chạy alembic downgrade:

```powershell
.\.venv\Scripts\python.exe -m alembic downgrade -1
```

downgrade sẽ xóa schema mới, rename lại `marketplace_reviews` về
`reviews`, và recreate các bảng cũ với schema-13 ban đầu.
