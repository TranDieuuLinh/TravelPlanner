import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1] / "knowledge-graph-real-v2"
HANOI_ID = "area_city_0c21619b4e"
VIETNAM_TOURISM_SOURCE = "https://vietnam.travel/things-to-do/11-must-see-attractions-ha-noi"
VIETGOHAN_SOURCE = "https://vietgohan.com/en/20260610-2/"
CURATED_SOURCE = "inference:hanoi-special-experience-curation:v1"


def read_csv(name):
    with (BASE_DIR / name).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(name, rows, fieldnames):
    with (BASE_DIR / name).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalized(value):
    value = value.lower().replace("đ", "d")
    value = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def stable_id(prefix, value):
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def edge_id(relationship, from_id, to_id, label):
    return stable_id("edge", f"{relationship}|{from_id}|{to_id}|{label}")


def parse_int(value):
    try:
        return int(float(value or 0))
    except ValueError:
        return 0


def parse_float(value):
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def score_candidate(entity, props, selectors, allowed_types):
    if allowed_types and entity["type"] not in allowed_types:
        return 0

    name = entity["name"]
    address = props[entity["id"]].get("address", "")
    description = props[entity["id"]].get("description", "")
    raw_name = name.lower()
    raw_text = f"{name} {address} {description}".lower()
    norm_name = normalized(name)
    norm_text = normalized(f"{name} {address} {description}")

    score = 0
    for selector in selectors:
        selector_norm = normalized(selector)
        if selector.lower() in raw_name:
            score += 100
        elif selector_norm and re.search(rf"(^| ){re.escape(selector_norm)}($| )", norm_name):
            score += 90
        elif selector.lower() in raw_text:
            score += 20
        elif selector_norm and selector_norm in norm_text:
            score += 10
    if not score:
        return 0

    score += min(parse_int(props[entity["id"]].get("review_count")), 5000) / 100
    score += parse_float(props[entity["id"]].get("rating")) * 2
    return score


def find_best(entities, props, selectors, allowed_types, min_score=10):
    candidates = []
    for entity in entities:
        if entity["type"] in {"Area", "Activity"}:
            continue
        score = score_candidate(entity, props, selectors, allowed_types)
        if score >= min_score:
            candidates.append((score, entity))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1] if candidates else None


def find_target(entities, props, experience):
    exact_id = experience.get("exact_id")
    if exact_id:
        return next((entity for entity in entities if entity["id"] == exact_id), None)
    return find_best(entities, props, experience["selectors"], experience["types"])


EXPERIENCES = [
    {
        "label": "ho_chi_minh_mausoleum",
        "title": "Viếng Lăng Chủ tịch Hồ Chí Minh buổi sáng",
        "selectors": ["Ho Chi Minh's Mausoleum", "Ho Chi Minh Mausoleum"],
        "types": {"TravelPlace"},
        "priority": "must",
        "intent": "visit",
        "timeSlots": [{"start": "08:00", "end": "10:30"}],
        "visitMinutes": 90,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "one_pillar_pagoda",
        "title": "Ghé Chùa Một Cột gần cụm Ba Đình",
        "selectors": ["One Pillar Pagoda", "Chùa Một Cột"],
        "types": {"TravelPlace"},
        "priority": "must",
        "intent": "visit",
        "timeSlots": [{"start": "08:00", "end": "11:30"}, {"start": "14:00", "end": "16:00"}],
        "visitMinutes": 45,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "old_quarter_walk",
        "title": "Đi bộ Phố cổ và xem nhịp sống 36 phố phường",
        "exact_id": "travel_place_ChIJp0o4Er6rNTERjlTif_IXU1k",
        "selectors": ["Old Quarter", "Phố Cổ", "Phố Bích Họa Phùng Hưng"],
        "types": {"TravelPlace"},
        "priority": "must",
        "intent": "walk",
        "timeSlots": [{"start": "08:00", "end": "11:00"}, {"start": "17:00", "end": "22:00"}],
        "visitMinutes": 120,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "hanoi_opera_house",
        "title": "Chụp ảnh/đi show ở Nhà hát Lớn Hà Nội",
        "selectors": ["Hanoi Opera House", "Nhà Hát Lớn Hà Nội"],
        "types": {"TravelPlace"},
        "priority": "recommended",
        "intent": "visit",
        "timeSlots": [{"start": "09:00", "end": "11:00"}, {"start": "19:00", "end": "22:00"}],
        "visitMinutes": 60,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "women_museum",
        "title": "Thăm Bảo tàng Phụ nữ Việt Nam",
        "selectors": ["Vietnamese Women's Museum", "Vietnamese Women’s Museum", "Bảo tàng Phụ nữ"],
        "types": {"TravelPlace"},
        "priority": "recommended",
        "intent": "visit",
        "timeSlots": [{"start": "09:00", "end": "11:30"}, {"start": "14:00", "end": "16:30"}],
        "visitMinutes": 90,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "hoan_kiem_lake",
        "title": "Dạo Hồ Hoàn Kiếm lúc sáng sớm hoặc chiều tối",
        "selectors": ["Hoàn Kiếm Lake", "Hoan Kiem Lake", "Hồ Gươm"],
        "types": {"TravelPlace"},
        "priority": "must",
        "intent": "walk",
        "timeSlots": [{"start": "06:00", "end": "08:30"}, {"start": "17:00", "end": "20:00"}],
        "visitMinutes": 75,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "ngoc_son_temple",
        "title": "Qua cầu Thê Húc thăm Đền Ngọc Sơn",
        "selectors": ["Ngoc Son Temple", "Ngọc Sơn Temple", "Đền Ngọc Sơn"],
        "types": {"TravelPlace"},
        "priority": "recommended",
        "intent": "visit",
        "timeSlots": [{"start": "07:30", "end": "11:00"}, {"start": "14:00", "end": "17:00"}],
        "visitMinutes": 45,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "temple_of_literature",
        "title": "Thăm Văn Miếu - Quốc Tử Giám",
        "exact_id": "travel_place_ChIJZ73nJpmrNTERHt_VdIgHDlg",
        "selectors": ["Temple of Literature", "Văn Miếu Quốc Tử Giám", "Văn Miếu - Quốc Tử Giám"],
        "types": {"TravelPlace"},
        "priority": "must",
        "intent": "visit",
        "timeSlots": [{"start": "08:00", "end": "11:00"}, {"start": "14:00", "end": "17:00"}],
        "visitMinutes": 90,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "ethnology_museum",
        "title": "Thăm Bảo tàng Dân tộc học Việt Nam",
        "selectors": ["Vietnam Museum of Ethnology", "Museum of Ethnology", "Bảo tàng Dân tộc học"],
        "types": {"TravelPlace"},
        "priority": "recommended",
        "intent": "visit",
        "timeSlots": [{"start": "09:00", "end": "11:30"}, {"start": "14:00", "end": "16:30"}],
        "visitMinutes": 120,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "st_joseph_cathedral",
        "title": "Ngắm Nhà thờ Lớn và cà phê quanh Nhà Chung",
        "selectors": ["Saint Joseph's Cathedral", "St. Joseph's Cathedral", "Nhà Thờ Lớn Hà Nội"],
        "types": {"TravelPlace"},
        "priority": "recommended",
        "intent": "visit",
        "timeSlots": [{"start": "08:00", "end": "11:00"}, {"start": "17:00", "end": "21:00"}],
        "visitMinutes": 60,
        "source": VIETNAM_TOURISM_SOURCE,
    },
    {
        "label": "water_puppet",
        "title": "Xem múa rối nước gần Hồ Gươm",
        "selectors": ["Thang Long Water Puppet Theatre", "Lotus Water Puppet Theater"],
        "types": {"TravelPlace"},
        "priority": "recommended",
        "intent": "show",
        "timeSlots": [{"start": "16:00", "end": "21:00"}],
        "visitMinutes": 75,
        "source": CURATED_SOURCE,
    },
    {
        "label": "train_street_coffee",
        "title": "Uống cà phê đường tàu, ưu tiên điểm an toàn/hợp lệ",
        "selectors": ["Train Street Hanoi coffee", "28 Train Street", "Train Street Kitchen"],
        "types": {"DrinkDessert", "Restaurant"},
        "priority": "recommended",
        "intent": "drink",
        "timeSlots": [{"start": "09:00", "end": "11:00"}, {"start": "15:00", "end": "18:00"}],
        "visitMinutes": 60,
        "source": CURATED_SOURCE,
    },
    {
        "label": "pho_bat_dan",
        "title": "Ăn phở sáng kiểu Hà Nội ở Bát Đàn",
        "selectors": ["Phở Gia Truyền Bát Đàn", "Pho Gia Truyen Bat Dan"],
        "types": {"Restaurant"},
        "priority": "must",
        "intent": "eat",
        "items": ["Phở bò", "Quẩy"],
        "timeSlots": [{"start": "06:00", "end": "10:00"}],
        "visitMinutes": 45,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "pho_10_ly_quoc_su",
        "title": "Ăn phở Lý Quốc Sư ở khu Hồ Gươm",
        "selectors": ["Pho 10 Ly Quoc Su", "Phở 10 Lý Quốc Sư"],
        "types": {"Restaurant"},
        "priority": "must",
        "intent": "eat",
        "items": ["Phở bò", "Quẩy"],
        "timeSlots": [{"start": "06:00", "end": "10:30"}, {"start": "18:00", "end": "20:30"}],
        "visitMinutes": 45,
        "source": CURATED_SOURCE,
    },
    {
        "label": "bun_cha_huong_lien",
        "title": "Ăn bún chả Hương Liên",
        "selectors": ["Bún Chả Hương Liên", "Bun Cha Huong Lien"],
        "types": {"Restaurant"},
        "priority": "must",
        "intent": "eat",
        "items": ["Bún chả", "Nem cua bể"],
        "timeSlots": [{"start": "11:00", "end": "13:30"}, {"start": "18:00", "end": "20:30"}],
        "visitMinutes": 60,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "bun_cha_dac_kim",
        "title": "Ăn bún chả Đắc Kim ở Hàng Mành",
        "selectors": ["Bún Chả Đắc Kim", "Bun Cha Dac Kim"],
        "types": {"Restaurant"},
        "priority": "recommended",
        "intent": "eat",
        "items": ["Bún chả"],
        "timeSlots": [{"start": "11:00", "end": "14:00"}, {"start": "18:00", "end": "20:00"}],
        "visitMinutes": 60,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "cafe_giang",
        "title": "Uống cà phê trứng ở Café Giảng",
        "selectors": ["Cafe Giảng", "Café Giảng"],
        "types": {"DrinkDessert"},
        "priority": "must",
        "intent": "drink",
        "items": ["Cà phê trứng"],
        "timeSlots": [{"start": "07:00", "end": "11:00"}, {"start": "14:00", "end": "18:00"}],
        "visitMinutes": 45,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "cafe_dinh",
        "title": "Uống cà phê trứng ở Café Đinh nhìn ra Hồ Gươm",
        "selectors": ["Cafe Đinh", "Café Đinh", "Dinh Cafe"],
        "types": {"DrinkDessert"},
        "priority": "recommended",
        "intent": "drink",
        "items": ["Cà phê trứng"],
        "timeSlots": [{"start": "07:00", "end": "11:00"}, {"start": "14:00", "end": "18:00"}],
        "visitMinutes": 45,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "banh_mi_25",
        "title": "Ăn Bánh Mì 25 ở Phố cổ",
        "selectors": ["Bánh Mì 25", "Banh Mi 25"],
        "types": {"Restaurant", "DrinkDessert", "TravelPlace"},
        "priority": "recommended",
        "intent": "eat",
        "items": ["Bánh mì"],
        "timeSlots": [{"start": "07:00", "end": "10:00"}, {"start": "15:00", "end": "17:00"}],
        "visitMinutes": 30,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "cha_ca_la_vong",
        "title": "Ăn chả cá Lã Vọng",
        "selectors": ["Chả Cá Lã Vọng", "Cha Ca La Vong"],
        "types": {"Restaurant"},
        "priority": "must",
        "intent": "eat",
        "items": ["Chả cá", "Bún", "Rau thì là"],
        "timeSlots": [{"start": "11:00", "end": "13:30"}, {"start": "18:00", "end": "21:00"}],
        "visitMinutes": 75,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "cha_ca_thang_long",
        "title": "Ăn chả cá Thăng Long",
        "selectors": ["Chả Cá Thăng Long", "Cha Ca Thang Long"],
        "types": {"Restaurant"},
        "priority": "recommended",
        "intent": "eat",
        "items": ["Chả cá"],
        "timeSlots": [{"start": "11:00", "end": "13:30"}, {"start": "18:00", "end": "21:00"}],
        "visitMinutes": 75,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "pho_cuon_huong_mai",
        "title": "Ăn phở cuốn Ngũ Xã",
        "selectors": ["Phở Cuốn Hương Mai", "Pho Cuon Huong Mai"],
        "types": {"Restaurant"},
        "priority": "recommended",
        "intent": "eat",
        "items": ["Phở cuốn"],
        "timeSlots": [{"start": "10:00", "end": "13:00"}, {"start": "17:00", "end": "21:00"}],
        "visitMinutes": 60,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "banh_cuon_ba_hoanh",
        "title": "Ăn bánh cuốn Bà Hoành buổi sáng",
        "selectors": ["Bánh Cuốn Bà Hoành", "Banh Cuon Ba Hoanh"],
        "types": {"Restaurant"},
        "priority": "recommended",
        "intent": "eat",
        "items": ["Bánh cuốn"],
        "timeSlots": [{"start": "06:00", "end": "09:30"}],
        "visitMinutes": 45,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "bun_bo_nam_bo",
        "title": "Ăn bún bò Nam Bộ Bách Phương",
        "selectors": ["Bún Bò Nam Bộ Bách Phương", "Bun Bo Nam Bo Bach Phuong", "Bún Bò Nam Bộ"],
        "types": {"Restaurant"},
        "priority": "recommended",
        "intent": "eat",
        "items": ["Bún bò Nam Bộ"],
        "timeSlots": [{"start": "11:00", "end": "14:00"}, {"start": "18:00", "end": "21:00"}],
        "visitMinutes": 60,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "bia_hoi_corner",
        "title": "Uống bia hơi ở Tạ Hiện - Lương Ngọc Quyến",
        "selectors": ["Ta Hien Beer Street", "beer ta hien", "Bia Hơi Corner"],
        "types": {"TravelPlace", "DrinkDessert"},
        "priority": "recommended",
        "intent": "nightlife",
        "items": ["Bia hơi"],
        "timeSlots": [{"start": "19:00", "end": "23:00"}],
        "visitMinutes": 90,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "kem_trang_tien",
        "title": "Ăn kem Tràng Tiền sau khi dạo hồ/nhà hát",
        "selectors": ["Kem Tràng Tiền", "Kem Trang Tien"],
        "types": {"DrinkDessert", "TravelPlace"},
        "priority": "recommended",
        "intent": "eat",
        "items": ["Kem Tràng Tiền"],
        "timeSlots": [{"start": "14:00", "end": "22:00"}],
        "visitMinutes": 30,
        "source": VIETGOHAN_SOURCE,
    },
    {
        "label": "bat_trang_pottery",
        "title": "Đi làng gốm Bát Tràng và thử workshop gốm",
        "selectors": ["Bat Trang Pottery Village", "Chợ gốm Bát Tràng", "Bat Trang Pottery Museum"],
        "types": {"TravelPlace"},
        "priority": "recommended",
        "intent": "craft",
        "timeSlots": [{"start": "09:00", "end": "12:00"}, {"start": "14:00", "end": "17:00"}],
        "visitMinutes": 150,
        "source": CURATED_SOURCE,
    },
    {
        "label": "long_bien_bridge",
        "title": "Ngắm Cầu Long Biên lúc hoàng hôn",
        "selectors": ["cầu Long Biên", "Long Bien Bridge"],
        "types": {"TravelPlace"},
        "priority": "recommended",
        "intent": "walk",
        "timeSlots": [{"start": "16:30", "end": "18:30"}],
        "visitMinutes": 60,
        "source": CURATED_SOURCE,
    },
    {
        "label": "tran_quoc_pagoda",
        "title": "Ghé Chùa Trấn Quốc cạnh Hồ Tây",
        "selectors": ["Chùa Trấn Quốc", "Tran Quoc Pagoda"],
        "types": {"TravelPlace"},
        "priority": "recommended",
        "intent": "visit",
        "timeSlots": [{"start": "08:00", "end": "10:30"}, {"start": "15:30", "end": "17:30"}],
        "visitMinutes": 45,
        "source": CURATED_SOURCE,
    },
]


ACTIVITY_EXPERIENCES = [
    ("activity_eat_pho", "Ăn phở Hà Nội kèm quẩy buổi sáng", "must", "eat", ["Phở", "Quẩy"], [{"start": "06:00", "end": "10:00"}], 60),
    ("activity_drink_coffee", "Uống cà phê trứng/cà phê vợt kiểu Hà Nội", "must", "drink", ["Cà phê trứng"], [{"start": "07:00", "end": "11:00"}, {"start": "14:00", "end": "18:00"}], 45),
    ("activity_cultural_visit", "Xếp cụm Ba Đình - Văn Miếu - bảo tàng vào lịch văn hóa", "must", "visit", [], [{"start": "08:00", "end": "11:30"}, {"start": "14:00", "end": "17:00"}], 120),
    ("activity_walk_outdoors", "Dạo Hồ Gươm/Phố cổ/Hồ Tây theo nhịp chậm", "recommended", "walk", [], [{"start": "06:00", "end": "09:00"}, {"start": "16:30", "end": "20:00"}], 90),
    ("activity_nightlife_drink", "Trải nghiệm bia hơi và phố đêm Tạ Hiện", "recommended", "nightlife", ["Bia hơi"], [{"start": "19:00", "end": "23:00"}], 90),
    ("activity_shopping", "Đi chợ Đồng Xuân hoặc mua quà đặc sản Phố cổ", "recommended", "shopping", [], [{"start": "09:00", "end": "12:00"}, {"start": "15:00", "end": "18:00"}], 90),
]


def recommendation_payload(experience, target_name):
    return json.dumps([
        {
            "intent": experience["intent"],
            "priority": experience["priority"],
            "title": experience["title"],
            "timeSlots": experience["timeSlots"],
            "recommendedItems": experience.get("items", []),
            "recommendedVisitMinutes": experience.get("visitMinutes"),
            "reason": f"{target_name} được chọn làm trải nghiệm đặc trưng cho Hà Nội; cần đối chiếu giờ mở cửa và điều kiện thực tế trước khi chốt itinerary.",
        }
    ], ensure_ascii=False, separators=(",", ":"))


def main():
    entities = read_csv("entities.csv")
    relationships = read_csv("relationships.csv")
    properties = read_csv("properties.csv")
    props = defaultdict(dict)
    for row in properties:
        props[row["entity_id"]][row["key"]] = row["value"]

    entity_by_id = {row["id"]: row for row in entities}
    located_in = {}
    hanoi_area_ids = {HANOI_ID}
    for row in relationships:
        if row["relationship"] == "LOCATED_IN":
            located_in[row["from_entity_id"]] = row["to_entity_id"]
        elif row["relationship"] == "PART_OF" and row["to_entity_id"] == HANOI_ID:
            hanoi_area_ids.add(row["from_entity_id"])

    curated_sources = {VIETNAM_TOURISM_SOURCE, VIETGOHAN_SOURCE, CURATED_SOURCE}
    relationships = [
        row for row in relationships
        if not (row["relationship"] == "SPECIAL_EXPERIENCE" and row["source"] in curated_sources)
    ]

    existing_keys = {
        (row["from_entity_id"], row["relationship"], row["to_entity_id"], row["source"])
        for row in relationships
    }

    def add_special(from_id, target_id, experience, source):
        key = (from_id, "SPECIAL_EXPERIENCE", target_id, source)
        if key in existing_keys:
            return False
        target_name = entity_by_id[target_id]["name"]
        relationships.append({
            "id": edge_id("SPECIAL_EXPERIENCE", from_id, target_id, experience["label"]),
            "from_entity_id": from_id,
            "relationship": "SPECIAL_EXPERIENCE",
            "to_entity_id": target_id,
            "recommendations": recommendation_payload(experience, target_name),
            "source": source,
        })
        existing_keys.add(key)
        return True

    found = []
    missing = []
    added = 0
    for experience in EXPERIENCES:
        target = find_target(entities, props, experience)
        if not target:
            missing.append({
                "label": experience["label"],
                "title": experience["title"],
                "selectors": experience["selectors"],
                "source": experience["source"],
            })
            continue

        if add_special(HANOI_ID, target["id"], experience, experience["source"]):
            added += 1
        area_id = located_in.get(target["id"])
        if area_id and area_id != HANOI_ID and area_id in hanoi_area_ids:
            if add_special(area_id, target["id"], experience, experience["source"]):
                added += 1

        found.append({
            "label": experience["label"],
            "title": experience["title"],
            "target_id": target["id"],
            "target_name": target["name"],
            "target_type": target["type"],
            "area_id": located_in.get(target["id"]),
            "source": experience["source"],
        })

    for activity_id, title, priority, intent, items, time_slots, minutes in ACTIVITY_EXPERIENCES:
        if activity_id not in entity_by_id:
            missing.append({
                "label": activity_id,
                "title": title,
                "selectors": [activity_id],
                "source": CURATED_SOURCE,
            })
            continue
        experience = {
            "label": activity_id,
            "title": title,
            "priority": priority,
            "intent": intent,
            "items": items,
            "timeSlots": time_slots,
            "visitMinutes": minutes,
        }
        if add_special(HANOI_ID, activity_id, experience, CURATED_SOURCE):
            added += 1
        found.append({
            "label": activity_id,
            "title": title,
            "target_id": activity_id,
            "target_name": entity_by_id[activity_id]["name"],
            "target_type": "Activity",
            "area_id": HANOI_ID,
            "source": CURATED_SOURCE,
        })

    write_csv(
        "relationships.csv",
        relationships,
        ["id", "from_entity_id", "relationship", "to_entity_id", "recommendations", "source"],
    )

    report = {
        "added_special_experience_edges": added,
        "found_count": len(found),
        "missing_count": len(missing),
        "found": found,
        "missing": missing,
        "relationship_counts": Counter(row["relationship"] for row in relationships).most_common(),
    }
    (BASE_DIR / "special_experience_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
