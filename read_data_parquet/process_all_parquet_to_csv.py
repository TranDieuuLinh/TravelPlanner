import csv
import json
import os
import sys
import time
from pathlib import Path

# Đảm bảo hiển thị Unicode trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse_json_field(val):
    """Giải mã các chuỗi JSON lồng nhau (nested JSON strings) hoặc trả về giá trị gốc."""
    if val is None:
        return None
    if isinstance(val, str):
        val_strip = val.strip()
        if val_strip in ("null", "None", ""):
            return None
        if (val_strip.startswith("{") and val_strip.endswith("}")) or (val_strip.startswith("[") and val_strip.endswith("]")):
            try:
                return json.loads(val_strip)
            except Exception:
                return val
    return val


def process_parquet_to_relational_csv(parquet_path, output_dir=None):
    """
    Đọc TOÀN BỘ file .parquet, tiền xử lý dữ liệu thô và xuất ra 5 file CSV quan hệ.
    """
    if not os.path.exists(parquet_path):
        print(f"❌ Không tìm thấy file Parquet: {parquet_path}")
        return

    if not output_dir:
        output_dir = Path(parquet_path).parent / "csv_relational"

    os.makedirs(output_dir, exist_ok=True)

    start_time = time.time()
    print(f"\n==================================================")
    print(f"🚀 BẮT ĐẦU XỬ LÝ TOÀN BỘ FILE PARQUET")
    print(f"📄 File nguồn: {parquet_path}")
    print(f"📂 Thư mục xuất CSV: {os.path.abspath(output_dir)}")
    print(f"==================================================\n")

    # Đọc file parquet dùng PyArrow hoặc DuckDB để tránh lỗi Windows AppLocker của Pandas
    records = []
    try:
        import duckdb
        print("📦 Đang đọc dữ liệu qua DuckDB...")
        con = duckdb.connect()
        # Chuyển dữ liệu Parquet thành danh sách Dict
        dict_records = con.execute(f"SELECT * FROM '{parquet_path}'").fetchdf().to_dict(orient="records")
        records = dict_records
        print(f"✅ Đã tải thành công {len(records):,} bản ghi địa điểm!")
    except Exception as e_duck:
        print(f"⚠️ DuckDB không khả dụng ({e_duck}), thử dùng PyArrow...")
        try:
            import pyarrow.parquet as pq
            table = pq.read_table(parquet_path)
            pydict = table.to_pydict()
            num_rows = table.num_rows
            keys = list(pydict.keys())
            for i in range(num_rows):
                records.append({k: pydict[k][i] for k in keys})
            print(f"✅ Đã tải thành công {len(records):,} bản ghi địa điểm (qua PyArrow)!")
        except Exception as e_arrow:
            print(f"❌ Lỗi đọc file Parquet: {e_arrow}")
            return

    # Danh sách dữ liệu cho 5 bảng CSV
    places_rows = []
    reviews_rows = []
    images_rows = []
    amenities_rows = []
    hours_rows = []

    print("\n🧹 Đang tiền xử lý và tách dữ liệu thành 5 bảng quan hệ...")

    json_fields = {
        "open_hours", "popular_times", "reviews_per_rating", "images",
        "reservations", "order_online", "menu", "owner",
        "complete_address", "about", "user_reviews"
    }

    for idx, item in enumerate(records, 1):
        if idx % 1000 == 0 or idx == len(records):
            print(f"   ⏳ Đã xử lý {idx:,}/{len(records):,} địa điểm...", end="\r")

        # Parse các trường JSON bị stringify
        cleaned = {}
        for k, v in item.items():
            if k in json_fields:
                cleaned[k] = parse_json_field(v)
            else:
                cleaned[k] = None if (v == "null" or v == "None") else v

        place_id = cleaned.get("place_id") or cleaned.get("cid") or cleaned.get("input_id") or cleaned.get("title")
        loc_details = cleaned.get("complete_address") or {}

        # 1. PLACES
        places_rows.append({
            "place_id": place_id,
            "title": cleaned.get("title"),
            "category": cleaned.get("category"),
            "description": cleaned.get("descriptions") or cleaned.get("status"),
            "latitude": cleaned.get("latitude"),
            "longitude": cleaned.get("longitude"),
            "address": cleaned.get("address"),
            "borough": loc_details.get("borough") if isinstance(loc_details, dict) else None,
            "city": loc_details.get("city") if isinstance(loc_details, dict) else None,
            "state": loc_details.get("state") if isinstance(loc_details, dict) else None,
            "country": loc_details.get("country") if isinstance(loc_details, dict) else None,
            "plus_code": cleaned.get("plus_code"),
            "rating": cleaned.get("review_rating"),
            "review_count": cleaned.get("review_count"),
            "source_platform": "google_maps",
            "source_link": cleaned.get("link")
        })

        # 2. REVIEWS
        user_reviews = cleaned.get("user_reviews") or []
        if isinstance(user_reviews, list):
            for rev in user_reviews:
                if isinstance(rev, dict):
                    reviews_rows.append({
                        "place_id": place_id,
                        "review_id": rev.get("review_id"),
                        "author_name": rev.get("Name"),
                        "rating": rev.get("Rating") or rev.get("rating_float"),
                        "published_at": rev.get("published_at"),
                        "when_text": rev.get("When"),
                        "language": rev.get("language"),
                        "review_text": rev.get("Description") or rev.get("text_original")
                    })

        # 3. IMAGES
        images = cleaned.get("images") or []
        if isinstance(images, list):
            for img in images:
                if isinstance(img, dict):
                    images_rows.append({
                        "place_id": place_id,
                        "image_title": img.get("title"),
                        "image_url": img.get("image")
                    })
                elif isinstance(img, str):
                    images_rows.append({
                        "place_id": place_id,
                        "image_title": None,
                        "image_url": img
                    })

        # 4. AMENITIES
        about_data = cleaned.get("about") or []
        if isinstance(about_data, list):
            for section in about_data:
                if isinstance(section, dict):
                    sec_name = section.get("name", "")
                    for opt in section.get("options", []):
                        if isinstance(opt, dict) and opt.get("enabled"):
                            amenities_rows.append({
                                "place_id": place_id,
                                "category_group": sec_name,
                                "amenity_name": opt.get("name")
                            })

        # 5. OPERATING_HOURS
        hours = cleaned.get("open_hours") or {}
        if isinstance(hours, dict):
            for day, time_slots in hours.items():
                slots_str = ", ".join(time_slots) if isinstance(time_slots, list) else str(time_slots)
                hours_rows.append({
                    "place_id": place_id,
                    "day_of_week": day,
                    "time_slots": slots_str
                })

    print(f"\n\n💾 Đang ghi dữ liệu ra 5 file CSV vào thư mục `csv_relational/`...")

    def write_csv(filename, headers, rows):
        if not rows:
            print(f"   ⚠️ Không có dữ liệu để ghi {filename}")
            return
        path = Path(output_dir) / filename
        with open(path, "w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        print(f"   📄 [Thành công] {filename} -> {len(rows):,} dòng")

    if places_rows:
        write_csv("places.csv", list(places_rows[0].keys()), places_rows)
    if reviews_rows:
        write_csv("reviews.csv", list(reviews_rows[0].keys()), reviews_rows)
    if images_rows:
        write_csv("images.csv", list(images_rows[0].keys()), images_rows)
    if amenities_rows:
        write_csv("amenities.csv", list(amenities_rows[0].keys()), amenities_rows)
    if hours_rows:
        write_csv("operating_hours.csv", list(hours_rows[0].keys()), hours_rows)

    elapsed = time.time() - start_time
    print(f"\n🎉 HOÀN THÀNH TOÀN BỘ TIẾN TRÌNH TRONG {elapsed:.2f} GIÂY!")


def main():
    if len(sys.argv) > 1:
        target_parquet = sys.argv[1]
    else:
        current_dir = Path(__file__).parent
        parquets = list(current_dir.glob("*.parquet"))
        if parquets:
            target_parquet = str(parquets[0])
        else:
            print("❌ Không tìm thấy file .parquet!")
            sys.exit(1)

    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    process_parquet_to_relational_csv(target_parquet, output_dir)


if __name__ == "__main__":
    main()
