"""Build a conservative Hanoi knowledge-graph snapshot from relational CSVs.

Places and areas remain drafts. Activity nodes and OFFERS_ACTIVITY edges are
approved from a small deterministic taxonomy and carry explicit model-inference
provenance; they are not represented as externally verified facts.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import mkdtemp

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = REPO_ROOT / "trung-temp" / "hanoi_travel_relational_20260802"
DEFAULT_GRAPH = REPO_ROOT / "knowledge-graph-real"
DEFAULT_CONTRACT = REPO_ROOT / "knowledge-graph-real-v2"
DATASET_SOURCE = "dataset:hanoi_travel_relational_20260802"
ACTIVITY_SOURCE = "inference:activity-taxonomy:v1"
SPECIAL_EXPERIENCE_SOURCE = "inference:special-experience-taxonomy:v1"

PLACE_PREFIX = {
    "TravelPlace": "travel_place",
    "Restaurant": "restaurant",
    "DrinkDessert": "drink_dessert",
    "Accommodation": "accommodation",
}

ACTIVITIES = {
    "eat_meal": ("Dùng bữa", "dining"),
    "eat_pho": ("Ăn phở", "dining"),
    "eat_rice": ("Ăn cơm", "dining"),
    "drink_coffee": ("Uống cà phê", "beverage"),
    "drink_tea": ("Uống trà", "beverage"),
    "enjoy_dessert": ("Thưởng thức món tráng miệng", "dessert"),
    "nightlife_drink": ("Trải nghiệm đồ uống buổi tối", "nightlife"),
    "enjoy_drink": ("Thưởng thức đồ uống", "beverage"),
    "stay": ("Lưu trú", "lodging"),
    "walk_outdoors": ("Đi dạo ngoài trời", "outdoor"),
    "exercise": ("Tập luyện thể thao", "sports"),
    "wellness": ("Thư giãn và chăm sóc sức khỏe", "wellness"),
    "cultural_visit": ("Tham quan văn hóa và tín ngưỡng", "cultural"),
    "sightseeing": ("Tham quan địa danh", "sightseeing"),
    "shopping": ("Mua sắm", "shopping"),
    "karaoke": ("Hát karaoke", "entertainment"),
}

# Curated search names for the small, controlled Activity taxonomy. Generic
# aliases are intentionally avoided for Place nodes because the source dataset
# does not prove that a venue is commonly known by another business name.
ACTIVITY_ALIASES = {
    "eat_meal": ["Ăn uống", "Dining"],
    "eat_pho": ["Phở", "Pho"],
    "eat_rice": ["Cơm", "Rice meal"],
    "drink_coffee": ["Cà phê", "Coffee"],
    "drink_tea": ["Trà", "Tea"],
    "enjoy_dessert": ["Món tráng miệng", "Dessert"],
    "nightlife_drink": ["Nightlife", "Đồ uống buổi tối"],
    "enjoy_drink": ["Đồ uống", "Drinks"],
    "stay": ["Nghỉ lại", "Stay"],
    "walk_outdoors": ["Đi bộ ngoài trời", "Outdoor walk"],
    "exercise": ["Thể thao", "Exercise"],
    "wellness": ["Chăm sóc sức khỏe", "Wellness"],
    "cultural_visit": ["Tham quan văn hóa", "Cultural visit"],
    "sightseeing": ["Tham quan", "Sightseeing"],
    "shopping": ["Mua sắm", "Shopping"],
    "karaoke": ["Karaoke"],
}

EXPERIENCE_PROFILES: dict[str, dict[str, object]] = {
    "eat_meal": {
        "intent": "eat", "priority": "recommended", "duration": 75,
        "timeSlots": [("11:00", "13:30"), ("18:00", "21:00")],
        "items": [], "reason": "Phù hợp xếp vào bữa trưa hoặc bữa tối.",
    },
    "eat_pho": {
        "intent": "eat", "priority": "must", "duration": 60,
        "timeSlots": [("06:30", "10:00"), ("11:00", "14:00")],
        "items": ["Phở"], "reason": "Phở là trải nghiệm ẩm thực tiêu biểu, thường phù hợp bữa sáng hoặc bữa trưa.",
    },
    "eat_rice": {
        "intent": "eat", "priority": "recommended", "duration": 60,
        "timeSlots": [("11:00", "14:00"), ("18:00", "20:30")],
        "items": ["Cơm"], "reason": "Phù hợp xếp vào bữa trưa hoặc bữa tối.",
    },
    "drink_coffee": {
        "intent": "drink", "priority": "must", "duration": 60,
        "timeSlots": [("07:00", "11:00"), ("14:00", "18:00")],
        "items": ["Cà phê"], "reason": "Phù hợp buổi sáng hoặc một khoảng nghỉ vào buổi chiều.",
    },
    "drink_tea": {
        "intent": "drink", "priority": "recommended", "duration": 60,
        "timeSlots": [("10:00", "12:00"), ("14:00", "19:00")],
        "items": ["Trà"], "reason": "Phù hợp nghỉ giữa buổi hoặc gặp gỡ vào buổi chiều.",
    },
    "enjoy_dessert": {
        "intent": "eat", "priority": "recommended", "duration": 45,
        "timeSlots": [("14:00", "18:00"), ("19:00", "21:00")],
        "items": ["Món tráng miệng"], "reason": "Phù hợp sau bữa trưa, buổi chiều hoặc sau bữa tối.",
    },
    "nightlife_drink": {
        "intent": "nightlife", "priority": "recommended", "duration": 120,
        "timeSlots": [("19:00", "23:30")],
        "items": [], "reason": "Trải nghiệm đồ uống và không khí nightlife phù hợp buổi tối.",
    },
    "enjoy_drink": {
        "intent": "drink", "priority": "recommended", "duration": 60,
        "timeSlots": [("10:00", "12:00"), ("14:00", "20:00")],
        "items": ["Đồ uống"], "reason": "Phù hợp làm điểm nghỉ giữa các hoạt động chính.",
    },
    "stay": {
        "intent": "stay", "priority": "recommended", "duration": 0,
        "timeSlots": [("14:00", "22:00")],
        "items": [], "reason": "Khung giờ gợi ý cho việc nhận phòng; cần đối chiếu chính sách cơ sở lưu trú.",
    },
    "walk_outdoors": {
        "intent": "walk", "priority": "recommended", "duration": 90,
        "timeSlots": [("06:00", "09:00"), ("16:00", "18:30")],
        "items": [], "reason": "Sáng sớm hoặc cuối chiều thường mát và dễ đi bộ hơn.",
    },
    "exercise": {
        "intent": "exercise", "priority": "recommended", "duration": 90,
        "timeSlots": [("06:00", "09:00"), ("17:00", "20:00")],
        "items": [], "reason": "Phù hợp tập luyện trước giờ làm việc hoặc vào cuối ngày.",
    },
    "wellness": {
        "intent": "wellness", "priority": "recommended", "duration": 90,
        "timeSlots": [("10:00", "12:00"), ("14:00", "21:00")],
        "items": [], "reason": "Phù hợp làm khoảng nghỉ phục hồi giữa hoặc sau lịch tham quan.",
    },
    "cultural_visit": {
        "intent": "visit", "priority": "must", "duration": 90,
        "timeSlots": [("07:00", "11:00"), ("14:00", "17:00")],
        "items": [], "reason": "Nên tham quan ban ngày và dành thời gian tôn trọng không gian văn hóa, tín ngưỡng.",
    },
    "sightseeing": {
        "intent": "visit", "priority": "must", "duration": 90,
        "timeSlots": [("08:00", "11:30"), ("14:00", "17:30")],
        "items": [], "reason": "Khung giờ ban ngày phù hợp quan sát và tham quan địa danh.",
    },
    "shopping": {
        "intent": "shopping", "priority": "recommended", "duration": 120,
        "timeSlots": [("10:00", "12:00"), ("14:00", "21:00")],
        "items": [], "reason": "Phù hợp ban ngày hoặc đầu buổi tối; cần đối chiếu giờ hoạt động thực tế.",
    },
    "karaoke": {
        "intent": "karaoke", "priority": "recommended", "duration": 120,
        "timeSlots": [("19:00", "23:00")],
        "items": [], "reason": "Karaoke phù hợp làm hoạt động giải trí buổi tối.",
    },
}

GENERIC_VISIT_PROFILE: dict[str, object] = {
    "intent": "visit", "priority": "recommended", "duration": 90,
    "timeSlots": [("08:00", "11:30"), ("14:00", "17:30")],
    "items": [],
    "reason": "Khung giờ ban ngày là gợi ý lập kế hoạch chung; cần đối chiếu giờ mở cửa thực tế.",
}

ACCOMMODATION_WORDS = (
    "hotel", "resort", "homestay", "villa", "motel", "hostel", "guest house",
    "lodging", "serviced accommodation", "apartment building", "bed breakfast",
    "vacation home", "inn",
)
RESTAURANT_WORDS = (
    "restaurant", "bistro", "noodle", "pho", "seafood", "bun", "com", "lau",
    "nuong", "diner", "steak", "sushi", "fast food", "pizza", "ramen",
    "banh mi", "quan an", "nha hang", "dim sum", "grill", "barbecue", "buffet",
    "taco", "eatery", "food court", "cafeteria", "deli",
)
DRINK_WORDS = (
    "coffee", "cafe", "tea", "tra", "bubble tea", "bakery", "dessert",
    "ice cream", "kem", "bar", "pub", "juice", "pastry", "banh ngot", "che",
    "snack", "beverage", "cocktail", "boba", "espresso", "donut",
)


def configure_runtime() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.casefold() in {"nan", "none", "null"} else text


def normalized(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", clean(value).casefold())
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_text).split())


def ascii_alias(value: object) -> str:
    """Return a readable accent-free search alias without inventing a name."""
    text = clean(value).replace("Đ", "D").replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip()


def alias_identity(value: object) -> str:
    """Compare aliases case-insensitively while preserving accent differences."""
    return unicodedata.normalize("NFC", clean(value).casefold())


def contains_any(text: str, values: tuple[str, ...]) -> bool:
    padded = f" {normalized(text)} "
    return any(f" {normalized(value)} " in padded for value in values)


def classify_place(category: str) -> str:
    if contains_any(category, ACCOMMODATION_WORDS):
        return "Accommodation"
    if contains_any(category, DRINK_WORDS):
        return "DrinkDessert"
    if contains_any(category, RESTAURANT_WORDS):
        return "Restaurant"
    return "TravelPlace"


def infer_activity(category: str, place_type: str) -> str | None:
    text = normalized(category)
    if "karaoke" in text:
        return "karaoke"
    if place_type == "Accommodation":
        return "stay"
    if place_type == "Restaurant":
        if " pho " in f" {text} ":
            return "eat_pho"
        if any(word in f" {text} " for word in (" rice ", " com ")):
            return "eat_rice"
        return "eat_meal"
    if place_type == "DrinkDessert":
        if any(word in text for word in ("coffee", "cafe", "espresso")):
            return "drink_coffee"
        if any(word in text for word in ("bubble tea", "tea house", " tea ", " tra ", "boba")):
            return "drink_tea"
        if any(word in text for word in ("bakery", "dessert", "ice cream", "pastry", "donut", "kem", "che")):
            return "enjoy_dessert"
        if any(word in text for word in ("bar", "pub", "brewpub", "cocktail")):
            return "nightlife_drink"
        return "enjoy_drink"
    if any(word in text for word in ("park", "garden", "walking", "hiking", "promenade")):
        return "walk_outdoors"
    if any(word in text for word in ("gym", "fitness", "sports", "pickleball", "swimming", "stadium", "court")):
        return "exercise"
    if any(word in text for word in ("spa", "massage", "wellness", "sauna")):
        return "wellness"
    if any(word in text for word in ("temple", "pagoda", "church", "worship", "shrine", "mosque")):
        return "cultural_visit"
    if any(word in text for word in ("museum", "historical", "tourist attraction", "monument", "heritage", "landmark")):
        return "sightseeing"
    if any(word in text for word in ("shopping", "mall", "market")):
        return "shopping"
    return None


def experience_item(
    profile: dict[str, object],
    *,
    priority: str | None = None,
    reason: str | None = None,
) -> dict[str, object]:
    slots = [
        {"start": start, "end": end}
        for start, end in profile.get("timeSlots", [])
    ]
    item: dict[str, object] = {
        "intent": profile["intent"],
        "priority": priority or profile["priority"],
        "timeSlots": slots,
        "reason": reason or profile["reason"],
    }
    recommended_items = list(profile.get("items", []))
    if recommended_items:
        item["recommendedItems"] = recommended_items
    duration = int(profile.get("duration", 0))
    if duration:
        item["recommendedVisitMinutes"] = duration
    return item


def inferred_priority(row: dict[str, str]) -> str:
    try:
        rating = float(clean(row.get("rating")))
        review_count = int(float(clean(row.get("review_count"))))
    except ValueError:
        return "recommended"
    return "must" if rating >= 4.6 and review_count >= 500 else "recommended"


def place_experience(row: dict[str, str], activity_key: str | None) -> list[dict[str, object]]:
    profile = EXPERIENCE_PROFILES.get(activity_key or "", GENERIC_VISIT_PROFILE)
    category = clean(row.get("category")) or "địa điểm"
    reason = (
        f"Gợi ý theo taxonomy của danh mục {category}; khung giờ dùng để lập kế hoạch "
        "và cần đối chiếu giờ hoạt động thực tế."
    )
    return [experience_item(profile, priority=inferred_priority(row), reason=reason)]


def activity_experience(activity_key: str) -> list[dict[str, object]]:
    return [experience_item(EXPERIENCE_PROFILES[activity_key])]


def stable_id(prefix: str, source_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", clean(source_id))
    candidate = f"{prefix}_{safe}"
    if safe and len(candidate) <= 96:
        return candidate
    digest = hashlib.sha256(clean(source_id).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def area_id(level: str, name: str) -> str:
    digest = hashlib.sha256(f"{level}|{normalized(name)}".encode()).hexdigest()[:10]
    return f"area_{level}_{digest}"


def edge_id(from_id: str, relationship: str, to_id: str) -> str:
    digest = hashlib.sha256(f"{from_id}|{relationship}|{to_id}".encode()).hexdigest()[:20]
    return f"edge_{digest}"


def source_for(row: dict[str, str]) -> str:
    return clean(row.get("source_link")) or f"{DATASET_SOURCE}/places.csv"


def fallback_description(title: str, category: str) -> str:
    if category:
        return f"{title} thuộc danh mục {category}; mô tả tối thiểu được tạo từ dữ liệu nguồn."
    return f"{title} là địa điểm được nhập từ dữ liệu nguồn."


def fallback_address(row: dict[str, str]) -> str:
    address = clean(row.get("address"))
    if address:
        return address
    values = [
        clean(row.get("plus_code")), clean(row.get("borough")),
        clean(row.get("city")), clean(row.get("state")), clean(row.get("country")),
    ]
    return ", ".join(dict.fromkeys(value for value in values if value)) or "Chưa có địa chỉ trong dữ liệu nguồn."


def canonical_city(row: dict[str, str]) -> str:
    city = clean(row.get("city"))
    address = clean(row.get("address"))
    if normalized(city) == "ha noi" or (not city and re.search(r"Hà Nội|Ha Noi", address, re.I)):
        return "Hà Nội"
    return city


def property_row(entity_id: str, key: str, value: object, source: str) -> dict[str, str] | None:
    text = (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        if isinstance(value, (list, dict))
        else clean(value)
    )
    if not text:
        return None
    return {"entity_id": entity_id, "key": key, "value": text, "source": source}


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def create_backup(graph_dir: Path) -> Path | None:
    existing = [graph_dir / name for name in ("entities.csv", "properties.csv", "aliases.csv", "relationships.csv")]
    if not any(path.exists() for path in existing):
        return None
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = graph_dir / "backups" / f"rebuild-{timestamp}"
    target.mkdir(parents=True, exist_ok=False)
    for path in existing:
        if path.exists():
            shutil.copy2(path, target / path.name)
    return target


def build_rows(places_path: Path, limit: int | None = None) -> dict[str, object]:
    entities: dict[str, dict[str, str]] = {}
    properties: dict[tuple[str, str], dict[str, str]] = {}
    relationships: dict[tuple[str, str, str], dict[str, str]] = {}
    area_stats: dict[str, dict[str, object]] = {}
    activity_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()

    def add_property(entity_id: str, key: str, value: object, source: str) -> None:
        row = property_row(entity_id, key, value, source)
        if row:
            properties[(entity_id, key)] = row

    def add_edge(
        from_id: str,
        relationship: str,
        to_id: str,
        source: str,
        recommendations: list[dict[str, object]],
    ) -> None:
        key = (from_id, relationship, to_id)
        relationships[key] = {
            "id": edge_id(*key),
            "from_entity_id": from_id,
            "relationship": relationship,
            "to_entity_id": to_id,
            "recommendations": json.dumps(
                recommendations,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "source": source,
        }

    country_id = area_id("country", "Việt Nam")
    area_stats[country_id] = {
        "name": "Việt Nam", "level": "country", "lat": 0.0, "lon": 0.0, "count": 0,
    }

    with places_path.open(encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle), start=1):
            if limit and index > limit:
                break
            source_place_id = clean(row.get("place_id"))
            if not source_place_id:
                continue
            category = clean(row.get("category"))
            place_type = classify_place(category)
            entity_id = stable_id(PLACE_PREFIX[place_type], source_place_id)
            title = clean(row.get("title")) or entity_id
            source = source_for(row)
            entities[entity_id] = {
                "id": entity_id, "name": title, "type": place_type, "status": "draft",
            }
            type_counts[place_type] += 1
            add_property(entity_id, "description", clean(row.get("description")) or fallback_description(title, category), source)
            add_property(entity_id, "address", fallback_address(row), source)
            for key in ("latitude", "longitude", "rating", "review_count", "source_platform", "source_link"):
                target_key = "source_url" if key == "source_link" else key
                add_property(entity_id, target_key, row.get(key), source)
            add_property(entity_id, "source_category", category, source)
            if place_type == "TravelPlace":
                add_property(entity_id, "place_category", category, source)
            elif place_type == "Accommodation":
                add_property(entity_id, "accommodation_type", category, source)

            activity_key = infer_activity(category, place_type)
            special_experience = place_experience(row, activity_key)
            add_property(
                entity_id,
                "special_experience",
                special_experience,
                SPECIAL_EXPERIENCE_SOURCE,
            )

            try:
                latitude = float(clean(row.get("latitude")))
                longitude = float(clean(row.get("longitude")))
            except ValueError:
                latitude = longitude = 0.0
            if latitude or longitude:
                country = area_stats[country_id]
                country["lat"] = float(country["lat"]) + latitude
                country["lon"] = float(country["lon"]) + longitude
                country["count"] = int(country["count"]) + 1

            city = canonical_city(row)
            if city:
                city_id = area_id("city", city)
                if city_id not in area_stats:
                    area_stats[city_id] = {
                        "name": city, "level": "city", "lat": 0.0, "lon": 0.0, "count": 0,
                    }
                if latitude or longitude:
                    stats = area_stats[city_id]
                    stats["lat"] = float(stats["lat"]) + latitude
                    stats["lon"] = float(stats["lon"]) + longitude
                    stats["count"] = int(stats["count"]) + 1
                add_edge(entity_id, "LOCATED_IN", city_id, source, [])
                add_edge(
                    city_id,
                    "PART_OF",
                    country_id,
                    f"{DATASET_SOURCE}/places.csv#city-country",
                    [],
                )
            else:
                add_edge(entity_id, "LOCATED_IN", country_id, source, [])

            if activity_key:
                activity_id = f"activity_{activity_key}"
                activity_name, activity_category = ACTIVITIES[activity_key]
                entities[activity_id] = {
                    "id": activity_id, "name": activity_name, "type": "Activity", "status": "verified",
                }
                add_property(
                    activity_id,
                    "description",
                    f"Hoạt động {activity_name.casefold()} được suy luận từ taxonomy danh mục địa điểm; chưa xác minh bằng nguồn ngoài.",
                    ACTIVITY_SOURCE,
                )
                add_property(activity_id, "activity_category", activity_category, ACTIVITY_SOURCE)
                activity_special = activity_experience(activity_key)
                add_property(
                    activity_id,
                    "special_experience",
                    activity_special,
                    SPECIAL_EXPERIENCE_SOURCE,
                )
                profile = EXPERIENCE_PROFILES[activity_key]
                add_property(
                    activity_id,
                    "best_time_slots",
                    activity_special[0]["timeSlots"],
                    SPECIAL_EXPERIENCE_SOURCE,
                )
                duration = int(profile.get("duration", 0))
                if duration:
                    add_property(
                        activity_id,
                        "typical_duration_minutes",
                        duration,
                        SPECIAL_EXPERIENCE_SOURCE,
                    )
                add_edge(
                    entity_id,
                    "OFFERS_ACTIVITY",
                    activity_id,
                    ACTIVITY_SOURCE,
                    special_experience,
                )
                activity_counts[activity_key] += 1

    for entity_id, stats in area_stats.items():
        count = int(stats["count"])
        if not count:
            continue
        name = str(stats["name"])
        level = str(stats["level"])
        source = f"{DATASET_SOURCE}/places.csv#{level}"
        entities[entity_id] = {
            "id": entity_id, "name": name, "type": "Area", "status": "draft",
        }
        add_property(entity_id, "description", f"Khu vực {name} được tổng hợp từ địa chỉ trong dữ liệu nguồn.", source)
        add_property(entity_id, "latitude", float(stats["lat"]) / count, source)
        add_property(entity_id, "longitude", float(stats["lon"]) / count, source)
        add_property(entity_id, "administrative_level", level, source)
        if level == "country":
            add_property(entity_id, "country", "VN", source)

    valid_ids = set(entities)
    relationships = {
        key: row for key, row in relationships.items()
        if row["from_entity_id"] in valid_ids and row["to_entity_id"] in valid_ids
    }
    aliases: dict[tuple[str, str], dict[str, str]] = {}

    def add_alias(entity_id: str, alias: str) -> None:
        canonical_name = entities[entity_id]["name"]
        value = clean(alias)
        identity = alias_identity(value)
        if not value or not identity or identity == alias_identity(canonical_name):
            return
        aliases[(entity_id, identity)] = {
            "entity_id": entity_id,
            "alias": value,
        }

    # Every accent-bearing canonical name receives a deterministic accent-free
    # lookup form. This improves Vietnamese search while remaining traceable to
    # the source name and does not assert an unofficial venue nickname.
    for entity_id, entity in entities.items():
        folded_name = ascii_alias(entity["name"])
        if folded_name != entity["name"]:
            add_alias(entity_id, folded_name)

    for activity_key, curated_aliases in ACTIVITY_ALIASES.items():
        entity_id = f"activity_{activity_key}"
        if entity_id in entities:
            for alias in curated_aliases:
                add_alias(entity_id, alias)

    for entity_id, entity in entities.items():
        if entity["type"] != "Area":
            continue
        if normalized(entity["name"]) == "ha noi":
            for alias in ("Hanoi", "Ha Noi"):
                add_alias(entity_id, alias)
        elif normalized(entity["name"]) == "viet nam":
            for alias in ("Vietnam", "Viet Nam"):
                add_alias(entity_id, alias)

    return {
        "entities": sorted(entities.values(), key=lambda row: (row["type"], row["id"])),
        "properties": sorted(properties.values(), key=lambda row: (row["entity_id"], row["key"])),
        "relationships": sorted(relationships.values(), key=lambda row: (row["from_entity_id"], row["relationship"], row["to_entity_id"])),
        "aliases": sorted(aliases.values(), key=lambda row: (row["entity_id"], row["alias"].casefold())),
        "typeCounts": dict(sorted(type_counts.items())),
        "activityEdgeCounts": dict(sorted(activity_counts.items())),
    }


def validate(rows: dict[str, object], schema: dict[str, object]) -> list[str]:
    entities = rows["entities"]
    properties = rows["properties"]
    relationships = rows["relationships"]
    aliases = rows["aliases"]
    assert isinstance(entities, list) and isinstance(properties, list) and isinstance(relationships, list) and isinstance(aliases, list)
    errors: list[str] = []
    entity_by_id = {row["id"]: row for row in entities}
    if len(entity_by_id) != len(entities):
        errors.append("duplicate_entity_id")
    seen_aliases: set[tuple[str, str]] = set()
    for row in aliases:
        entity_id = row["entity_id"]
        alias_key = alias_identity(row["alias"])
        key = (entity_id, alias_key)
        if entity_id not in entity_by_id:
            errors.append(f"orphan_alias:{entity_id}")
        elif alias_key == alias_identity(entity_by_id[entity_id]["name"]):
            errors.append(f"alias_matches_canonical_name:{entity_id}:{row['alias']}")
        if key in seen_aliases:
            errors.append(f"duplicate_alias:{entity_id}:{row['alias']}")
        seen_aliases.add(key)
    allowed_nodes = set(schema.get("nodes", []))
    allowed_properties = set((schema.get("property_definitions") or {}).keys())
    property_keys: defaultdict[str, set[str]] = defaultdict(set)
    for row in properties:
        if row["entity_id"] not in entity_by_id:
            errors.append(f"orphan_property:{row['entity_id']}")
        if row["key"] not in allowed_properties:
            errors.append(f"unsupported_property:{row['entity_id']}:{row['key']}")
        if not row["source"]:
            errors.append(f"missing_property_source:{row['entity_id']}:{row['key']}")
        if row["key"] == "special_experience":
            try:
                experiences = json.loads(row["value"])
                if not isinstance(experiences, list) or not experiences:
                    errors.append(f"empty_special_experience:{row['entity_id']}")
                elif any(
                    not isinstance(item, dict)
                    or not {"intent", "priority", "timeSlots", "reason"} <= item.keys()
                    for item in experiences
                ):
                    errors.append(f"invalid_special_experience:{row['entity_id']}")
            except json.JSONDecodeError:
                errors.append(f"invalid_special_experience_json:{row['entity_id']}")
        property_keys[row["entity_id"]].add(row["key"])
    required = {
        "TravelPlace": {"description", "latitude", "longitude", "address"},
        "Restaurant": {"description", "latitude", "longitude", "address"},
        "DrinkDessert": {"description", "latitude", "longitude", "address"},
        "Accommodation": {"description", "latitude", "longitude", "address"},
        "Area": {"description", "latitude", "longitude"},
        "Activity": {"description", "activity_category"},
    }
    for row in entities:
        if row["type"] not in allowed_nodes:
            errors.append(f"unsupported_type:{row['id']}:{row['type']}")
        expected_status = "verified" if row["type"] == "Activity" else "draft"
        if row["status"] != expected_status:
            errors.append(f"wrong_status:{row['id']}:{row['status']}")
        expected_properties = set(required.get(row["type"], set()))
        if row["type"] != "Area":
            expected_properties.add("special_experience")
        for key in expected_properties - property_keys[row["id"]]:
            errors.append(f"missing_required:{row['id']}:{key}")
    seen_edges: set[tuple[str, str, str]] = set()
    for row in relationships:
        key = (row["from_entity_id"], row["relationship"], row["to_entity_id"])
        if key in seen_edges:
            errors.append(f"duplicate_edge:{key}")
        seen_edges.add(key)
        if row["from_entity_id"] not in entity_by_id or row["to_entity_id"] not in entity_by_id:
            errors.append(f"orphan_edge:{row['id']}")
        try:
            recommendations = json.loads(row["recommendations"])
            if not isinstance(recommendations, list):
                errors.append(f"invalid_edge_recommendations:{row['id']}")
            elif row["relationship"] == "OFFERS_ACTIVITY" and not recommendations:
                errors.append(f"empty_activity_recommendations:{row['id']}")
            elif row["relationship"] in {"LOCATED_IN", "PART_OF"} and recommendations:
                errors.append(f"structural_edge_has_recommendations:{row['id']}")
        except json.JSONDecodeError:
            errors.append(f"invalid_edge_recommendations:{row['id']}")
        if row["relationship"] == "OFFERS_ACTIVITY":
            source_type = entity_by_id[row["from_entity_id"]]["type"]
            target_type = entity_by_id[row["to_entity_id"]]["type"]
            if source_type not in PLACE_PREFIX or target_type != "Activity":
                errors.append(f"invalid_activity_edge:{row['id']}")
            if row["source"] != ACTIVITY_SOURCE:
                errors.append(f"invalid_activity_source:{row['id']}")
    return errors


def main() -> int:
    configure_runtime()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--graph-dir", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--contract-dir", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    places_path = args.input_dir.resolve() / "places.csv"
    graph_dir = args.graph_dir.resolve()
    contract_dir = args.contract_dir.resolve()
    schema_path = contract_dir / "schema.yaml"
    ontology_path = contract_dir / "ontology.yaml"
    if not places_path.exists() or not schema_path.exists() or not ontology_path.exists():
        raise FileNotFoundError("Thiếu places.csv hoặc schema/ontology contract")
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
    rows = build_rows(places_path, args.limit)
    errors = validate(rows, schema)
    if errors:
        raise ValueError(f"Graph validation failed ({len(errors)}): {errors[:20]}")

    stage = Path(mkdtemp(prefix="hanoi-graph-", dir=graph_dir.parent))
    try:
        write_csv(stage / "entities.csv", ["id", "name", "type", "status"], rows["entities"])
        write_csv(stage / "properties.csv", ["entity_id", "key", "value", "source"], rows["properties"])
        write_csv(stage / "aliases.csv", ["entity_id", "alias"], rows["aliases"])
        write_csv(stage / "relationships.csv", ["id", "from_entity_id", "relationship", "to_entity_id", "recommendations", "source"], rows["relationships"])
        shutil.copy2(schema_path, stage / "schema.yaml")
        shutil.copy2(ontology_path, stage / "ontology.yaml")
        status_counts = Counter(row["status"] for row in rows["entities"])
        relationship_counts = Counter(row["relationship"] for row in rows["relationships"])
        special_experience_rows = [
            row for row in rows["properties"]
            if row["key"] == "special_experience"
        ]
        special_priorities = Counter(
            item.get("priority", "unknown")
            for row in special_experience_rows
            for item in json.loads(row["value"])
        )
        special_experience_eligible_nodes = sum(
            row["type"] != "Area" for row in rows["entities"]
        )
        report = {
            "entityCount": len(rows["entities"]),
            "propertyCount": len(rows["properties"]),
            "relationshipCount": len(rows["relationships"]),
            "aliasCount": len(rows["aliases"]),
            "aliasMethod": "canonical_ascii_fold_plus_curated_activity_and_area_aliases",
            "statusCounts": dict(status_counts),
            "typeCounts": rows["typeCounts"],
            "relationshipCounts": dict(relationship_counts),
            "specialExperienceNodeCount": len(special_experience_rows),
            "specialExperienceEligibleNodeCount": special_experience_eligible_nodes,
            "specialExperienceCoverage": len(special_experience_rows) / special_experience_eligible_nodes,
            "specialExperiencePriorities": dict(special_priorities),
            "recommendedEdgeCount": sum(
                bool(json.loads(row["recommendations"]))
                for row in rows["relationships"]
            ),
            "activityEdgeCounts": rows["activityEdgeCounts"],
            "activityReviewMethod": "llm_prior_taxonomy",
            "activityExternallyVerified": False,
            "activityProvenance": ACTIVITY_SOURCE,
            "specialExperienceProvenance": SPECIAL_EXPERIENCE_SOURCE,
            "validationErrors": [],
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
        (stage / "import_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest = {
            "sourceKey": "hanoi_travel_relational_20260802",
            "placeAndAreaDecision": "pending",
            "activityDecision": "approved_by_llm_prior",
            "activityExternallyVerified": False,
            "activityProvenance": ACTIVITY_SOURCE,
            "specialExperienceProperty": "special_experience",
            "specialExperienceProvenance": SPECIAL_EXPERIENCE_SOURCE,
            "aliasMethod": "canonical_ascii_fold_plus_curated_activity_and_area_aliases",
        }
        (stage / "pending_import_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        if not args.check_only:
            graph_dir.mkdir(parents=True, exist_ok=True)
            backup = create_backup(graph_dir)
            report["backupPath"] = str(backup) if backup else None
            (stage / "import_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            for name in ("entities.csv", "properties.csv", "aliases.csv", "relationships.csv", "schema.yaml", "ontology.yaml", "import_report.json", "pending_import_manifest.json"):
                (stage / name).replace(graph_dir / name)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
