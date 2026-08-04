import csv
import json
import os
import sys
from pathlib import Path

# Đảm bảo hiển thị Unicode trên Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def export_relational_csv(input_json_path, output_dir=None):
    """
    Tách dữ liệu địa điểm đã tiền xử lý thành 5 file CSV quan hệ:
    1. places.csv           - Thông tin chính địa điểm
    2. reviews.csv          - Bài đánh giá (khóa ngoại: place_id)
    3. images.csv           - Đường dẫn hình ảnh (khóa ngoại: place_id)
    4. amenities.csv        - Tiện ích/tiện nghi (khóa ngoại: place_id)
    5. operating_hours.csv  - Giờ mở cửa theo tuần (khóa ngoại: place_id)
    """
    if not os.path.exists(input_json_path):
        print(f"❌ Không tìm thấy file: {input_json_path}")
        return

    if not output_dir:
        output_dir = Path(input_json_path).parent / "csv_relational"

    os.makedirs(output_dir, exist_ok=True)
    print(f"📖 Đang nạp dữ liệu từ: {input_json_path}")

    with open(input_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    places_rows = []
    reviews_rows = []
    images_rows = []
    amenities_rows = []
    hours_rows = []

    for item in data:
        place_id = item.get("id") or item.get("title")
        loc = item.get("location") or {}
        details = loc.get("details") or {}
        metrics = item.get("metrics") or {}
        source = item.get("source") or {}

        # 1. Bảng PLACES
        places_rows.append({
            "place_id": place_id,
            "title": item.get("title"),
            "category": item.get("category"),
            "description": item.get("description"),
            "latitude": loc.get("latitude"),
            "longitude": loc.get("longitude"),
            "address": loc.get("address"),
            "borough": details.get("borough") if isinstance(details, dict) else None,
            "city": details.get("city") if isinstance(details, dict) else None,
            "state": details.get("state") if isinstance(details, dict) else None,
            "country": details.get("country") if isinstance(details, dict) else None,
            "plus_code": loc.get("plus_code"),
            "rating": metrics.get("rating"),
            "review_count": metrics.get("review_count"),
            "source_platform": source.get("platform"),
            "source_link": source.get("link")
        })

        # 2. Bảng REVIEWS (Quan hệ 1 - N với Place)
        user_reviews = item.get("user_reviews") or []
        if isinstance(user_reviews, list):
            for rev in user_reviews:
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

        # 3. Bảng IMAGES (Quan hệ 1 - N với Place)
        images = item.get("images") or []
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

        # 4. Bảng AMENITIES (Quan hệ 1 - N với Place)
        amenities = item.get("amenities") or []
        if isinstance(amenities, list):
            for am in amenities:
                amenities_rows.append({
                    "place_id": place_id,
                    "amenity": am
                })

        # 5. Bảng OPERATING_HOURS (Quan hệ 1 - N với Place)
        hours = item.get("operating_hours") or {}
        if isinstance(hours, dict):
            for day, time_slots in hours.items():
                slots_str = ", ".join(time_slots) if isinstance(time_slots, list) else str(time_slots)
                hours_rows.append({
                    "place_id": place_id,
                    "day_of_week": day,
                    "time_slots": slots_str
                })

    # Hàm ghi CSV
    def write_csv(filename, headers, rows):
        path = Path(output_dir) / filename
        with open(path, "w", newline="", encoding="utf-8-sig") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        print(f"   📄 [Ghi thành công] {filename} ({len(rows):,} dòng)")

    print(f"\n💾 Đang xuất các file CSV vào thư mục: {os.path.abspath(output_dir)}")

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

    print(f"\n🎉 Hoàn tất xuất đầy đủ 5 bảng CSV!")


def main():
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = os.path.join(os.path.dirname(__file__), "result_1_clean.json")

    output_directory = sys.argv[2] if len(sys.argv) > 2 else None
    export_relational_csv(input_file, output_directory)


if __name__ == "__main__":
    main()
