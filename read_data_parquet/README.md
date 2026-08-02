# Read Data Parquet Tools

Bộ công cụ xử lý dữ liệu địa điểm du lịch thu thập dạng `.parquet` từ crawler (Google Maps), hỗ trợ xem preview, bóc tách dữ liệu ra 5 bảng quan hệ CSV, hoặc lưu trực tiếp vào cơ sở dữ liệu PostgreSQL.

## Các công cụ chính

1. **`import_parquet_to_postgres.py`**: **[MỚI]** Đọc file Parquet, tiền xử lý và lưu toàn bộ địa điểm, tiện nghi, giờ mở cửa, hình ảnh, bài đánh giá vào cơ sở dữ liệu PostgreSQL.
   ```bash
   # Tự động tìm file Parquet và dùng DB URL cấu hình trong backend/.env
   python import_parquet_to_postgres.py

   # Hoặc chỉ định đường dẫn file Parquet và PostgreSQL connection string cụ thể:
   python import_parquet_to_postgres.py -f K:\VSF\VSF_TravelPlanner\hanoi_travel_deduplicated_final.parquet --db-url postgresql+psycopg://vsf:vsf@localhost:5432/vsf_travel
   ```

2. **`read_parquet.py`**: Xem nội dung hoặc xuất file `.parquet` ra JSON / CSV thô.
   ```bash
   python read_parquet.py -f <path_to_file.parquet> -n 10
   python read_parquet.py -f <path_to_file.parquet> --all --json result.json
   ```

3. **`process_all_parquet_to_csv.py`**: Chuyển đổi trực tiếp toàn bộ dữ liệu Parquet lớn sang 5 file CSV quan hệ.
   ```bash
   python process_all_parquet_to_csv.py <path_to_file.parquet> [output_dir]
   ```
   *Kết quả tạo ra 5 bảng CSV*: `places.csv`, `reviews.csv`, `images.csv`, `amenities.csv`, `operating_hours.csv`.

4. **`preprocess_json.py`**: Chuẩn hóa dữ liệu địa điểm từ JSON thô thành định dạng `Place Candidate`.
   ```bash
   python preprocess_json.py <input.json> [output_clean.json]
   ```

5. **`export_relational_csv.py`**: Xuất file JSON đã chuẩn hóa sang 5 file CSV quan hệ.
   ```bash
   python export_relational_csv.py <input_clean.json> [output_dir]
   ```

## Yêu cầu thư viện

Cài đặt các thư viện đọc Parquet và kết nối PostgreSQL:
```bash
pip install duckdb pyarrow pandas sqlalchemy psycopg
```
