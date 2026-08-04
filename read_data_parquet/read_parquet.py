import os
import sys
import argparse
import json
from pathlib import Path

# Đảm bảo hiển thị Unicode trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def export_with_duckdb(file_path, output_json=None, output_csv=None, head_n=None):
    """Xuất dữ liệu bằng DuckDB (không cần pandas C-extensions bị Windows AppLocker chặn)."""
    import duckdb

    limit_clause = f"LIMIT {head_n}" if head_n and head_n > 0 else ""
    query = f"SELECT * FROM '{file_path}' {limit_clause}"

    if output_json:
        print(f"\n💾 Đang xuất ra file JSON (bằng DuckDB) -> {output_json}...")
        con = duckdb.connect()
        # Xuất thẳng ra JSON dưới dạng mảng JSON
        con.execute(f"COPY ({query}) TO '{output_json}' (FORMAT JSON, ARRAY true)")
        print(f"✅ Xuất file JSON thành công tại: {os.path.abspath(output_json)}")

    if output_csv:
        print(f"\n💾 Đang xuất ra file CSV (bằng DuckDB) -> {output_csv}...")
        con = duckdb.connect()
        con.execute(f"COPY ({query}) TO '{output_csv}' (HEADER, DELIMITER ',')")
        print(f"✅ Xuất file CSV thành công tại: {os.path.abspath(output_csv)}")


def export_with_pyarrow(file_path, output_json=None, output_csv=None, head_n=None):
    """Xuất dữ liệu bằng PyArrow."""
    import pyarrow.parquet as pq

    parquet_file = pq.ParquetFile(file_path)
    table = parquet_file.read()
    
    if head_n and head_n > 0:
        table = table.slice(0, head_n)

    pydict = table.to_pydict()
    num_rows = table.num_rows

    rows = []
    keys = list(pydict.keys())
    for i in range(num_rows):
        row = {k: pydict[k][i] for k in keys}
        rows.append(row)

    if output_json:
        print(f"\n💾 Đang xuất ra file JSON (bằng PyArrow) -> {output_json}...")
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2, default=str)
        print(f"✅ Xuất file JSON thành công tại: {os.path.abspath(output_json)}")


def main():
    parser = argparse.ArgumentParser(description="Công cụ đọc và xuất file Parquet sang JSON/CSV")
    parser.add_argument(
        "-f", "--file",
        type=str,
        help="Đường dẫn tới file .parquet (Mặc định: tự tìm file parquet trong thư mục)"
    )
    parser.add_argument(
        "-n", "--head",
        type=int,
        default=5,
        help="Số dòng muốn xem/xuất (Mặc định: 5)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Xuất toàn bộ file"
    )
    parser.add_argument(
        "--json",
        type=str,
        help="Đường dẫn file JSON cần xuất (Ví dụ: result_1.json)"
    )
    parser.add_argument(
        "--csv",
        type=str,
        help="Đường dẫn file CSV cần xuất"
    )

    args = parser.parse_args()

    # Tìm file parquet
    target_file = args.file
    if not target_file:
        current_dir = Path(__file__).parent
        parquet_files = list(current_dir.glob("*.parquet"))
        if parquet_files:
            target_file = str(parquet_files[0])
            print(f"🔍 Tự động tìm thấy file Parquet: {target_file}")
        else:
            print("❌ Không tìm thấy file .parquet nào!")
            sys.exit(1)

    if not os.path.exists(target_file):
        print(f"❌ File không tồn tại: {target_file}")
        sys.exit(1)

    head_n = None if args.all else args.head

    # 1. Thử dùng DuckDB trước (Không bị lỗi AppLocker của Pandas DLL)
    try:
        import duckdb
        print("🚀 Đang xử lý bằng DuckDB...")
        con = duckdb.connect()

        total_rows = con.execute(f"SELECT COUNT(*) FROM '{target_file}'").fetchone()[0]
        print(f"📊 Tổng số dòng trong file: {total_rows:,}")

        if args.json or args.csv:
            export_with_duckdb(target_file, output_json=args.json, output_csv=args.csv, head_n=head_n)
        else:
            limit_val = head_n if head_n else 5
            res = con.execute(f"SELECT * FROM '{target_file}' LIMIT {limit_val}").fetchdf()
            print(f"\n--- PREVIEW {limit_val} DÒNG ---")
            print(res)
        return
    except Exception as e_duck:
        print(f"⚠️ DuckDB không khả dụng ({e_duck}), thử chuyển sang PyArrow...")

    # 2. Thử dùng PyArrow
    try:
        import pyarrow.parquet as pq
        print("🚀 Đang xử lý bằng PyArrow...")
        if args.json or args.csv:
            export_with_pyarrow(target_file, output_json=args.json, output_csv=args.csv, head_n=head_n)
        else:
            table = pq.read_table(target_file)
            print(f"📊 Số lượng dòng: {table.num_rows:,}")
            print(f"📋 Schema các cột:\n{table.schema}")
        return
    except Exception as e_arrow:
        print(f"⚠️ PyArrow không khả dụng ({e_arrow}), thử chuyển sang Pandas...")

    # 3. Thử Pandas nếu 2 cái trên thất bại
    try:
        import pandas as pd
        df = pd.read_parquet(target_file)
        print(f"📊 Tổng số dòng: {len(df):,}")
        export_df = df if args.all else df.head(args.head if args.head else 5)
        if args.json:
            export_df.to_json(args.json, orient="records", force_ascii=False, indent=2)
            print(f"✅ Xuất JSON thành công tại: {os.path.abspath(args.json)}")
    except Exception as e_pd:
        print(f"❌ Không thể đọc file bằng bất kỳ thư viện nào!")
        print(f"Lỗi Pandas: {e_pd}")


if __name__ == "__main__":
    main()
