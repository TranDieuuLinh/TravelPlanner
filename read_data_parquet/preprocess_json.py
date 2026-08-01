import json
import os
import sys
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


def preprocess_place_item(item):
    """
    Tiền xử lý 1 địa điểm từ dữ liệu cào thô (Google Maps crawler format):
    1. Parse tất cả các trường bị stringify/escape (open_hours, images, about, user_reviews,...)
    2. Chuẩn hóa null values ('null' string -> None)
    3. Chuẩn hóa cấu trúc địa điểm (Place Candidate / Provenance)
    """
    cleaned = {}

    # Danh sách các trường chứa JSON bị stringify
    json_string_fields = {
        "open_hours", "popular_times", "reviews_per_rating", "images",
        "reservations", "order_online", "menu", "owner",
        "complete_address", "about", "user_reviews"
    }

    for key, val in item.items():
        if key in json_string_fields:
            cleaned[key] = parse_json_field(val)
        else:
            if val == "null" or val == "None":
                cleaned[key] = None
            else:
                cleaned[key] = val

    # Tách nhỏ tiện ích (about) thành danh sách tags sạch nếu có
    amenities_tags = []
    about_data = cleaned.get("about")
    if isinstance(about_data, list):
        for section in about_data:
            sec_name = section.get("name", "")
            for opt in section.get("options", []):
                if opt.get("enabled"):
                    amenities_tags.append(f"{sec_name}: {opt.get('name')}")

    # Xây dựng cấu trúc địa điểm chuẩn hóa (Cleaned Place Candidate)
    processed_place = {
        "id": cleaned.get("place_id") or cleaned.get("cid") or cleaned.get("input_id"),
        "title": cleaned.get("title"),
        "category": cleaned.get("category"),
        "description": cleaned.get("descriptions") or cleaned.get("status"),
        "location": {
            "latitude": cleaned.get("latitude"),
            "longitude": cleaned.get("longitude"),
            "address": cleaned.get("address"),
            "details": cleaned.get("complete_address"),
            "plus_code": cleaned.get("plus_code")
        },
        "metrics": {
            "rating": cleaned.get("review_rating"),
            "review_count": cleaned.get("review_count"),
            "rating_breakdown": cleaned.get("reviews_per_rating")
        },
        "operating_hours": cleaned.get("open_hours"),
        "popular_times": cleaned.get("popular_times"),
        "amenities": amenities_tags,
        "images": cleaned.get("images"),
        "user_reviews": cleaned.get("user_reviews"),
        "source": {
            "platform": "google_maps",
            "link": cleaned.get("link"),
            "cid": cleaned.get("cid"),
            "data_id": cleaned.get("data_id")
        },
        "raw_attributes": cleaned  # Giữ lại bản ghi gốc đã parse JSON
    }

    return processed_place


def preprocess_file(input_json_path, output_json_path=None):
    """Đọc file JSON đầu vào và tiền xử lý toàn bộ các địa điểm."""
    if not os.path.exists(input_json_path):
        print(f"❌ Không tìm thấy file: {input_json_path}")
        return

    print(f"📖 Đang đọc dữ liệu từ: {input_json_path}")
    with open(input_json_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    if isinstance(raw_data, dict):
        raw_data = [raw_data]

    processed_list = [preprocess_place_item(item) for item in raw_data]

    if not output_json_path:
        base_name = Path(input_json_path).stem
        output_json_path = str(Path(input_json_path).parent / f"{base_name}_clean.json")

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(processed_list, f, ensure_ascii=False, indent=2)

    print(f"✅ Đã tiền xử lý {len(processed_list)} địa điểm!")
    print(f"💾 File kết quả đã lưu tại: {os.path.abspath(output_json_path)}")
    return output_json_path


def main():
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    else:
        input_file = os.path.join(os.path.dirname(__file__), "result_1.json")

    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    preprocess_file(input_file, output_file)


if __name__ == "__main__":
    main()
