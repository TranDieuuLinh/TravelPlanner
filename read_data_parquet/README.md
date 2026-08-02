# Read Data Parquet Tools

Bộ công cụ xử lý dữ liệu địa điểm du lịch thu thập dạng `.parquet` từ crawler (Google Maps), hỗ trợ xem preview và bóc tách dữ liệu ra 5 bảng quan hệ CSV.

## Các công cụ chính

1. **`read_parquet.py`**: Xem nội dung hoặc xuất file `.parquet` ra JSON / CSV thô.
   ```bash
   python read_parquet.py -f <path_to_file.parquet> -n 10
   python read_parquet.py -f <path_to_file.parquet> --all --json result.json
   ```

2. **`process_all_parquet_to_csv.py`**: Chuyển đổi trực tiếp toàn bộ dữ liệu Parquet lớn sang 5 file CSV quan hệ.
   ```bash
   python process_all_parquet_to_csv.py <path_to_file.parquet> [output_dir]
   ```
   *Kết quả tạo ra 5 bảng CSV*: `places.csv`, `reviews.csv`, `images.csv`, `amenities.csv`, `operating_hours.csv`.

3. **`preprocess_json.py`**: Chuẩn hóa dữ liệu địa điểm từ JSON thô thành định dạng `Place Candidate`.
   ```bash
   python preprocess_json.py <input.json> [output_clean.json]
   ```

4. **`export_relational_csv.py`**: Xuất file JSON đã chuẩn hóa sang 5 file CSV quan hệ.
   ```bash
   python export_relational_csv.py <input_clean.json> [output_dir]
   ```

## Yêu cầu thư viện

Cài đặt 1 trong các thư viện sau (khuyến nghị **DuckDB** hoặc **PyArrow**):
```bash
pip install duckdb pyarrow pandas
```
