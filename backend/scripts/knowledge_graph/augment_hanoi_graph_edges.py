"""Enrich the CSV-backed Hanoi graph with curated experience and proximity edges.

The enrichment is intentionally deterministic: curated experience rules create
Area -> Place/Activity edges, while NEAR uses the Haversine distance between
eligible coordinates. Writes require --apply and always snapshot the old graph.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_GRAPH = WORKSPACE_ROOT / "knowledge-graph-real-v2"
SPECIAL_SOURCE = "inference:special-experience-hanoi:v1"
NEAR_SOURCE = "derived:haversine-distance-under-5km:v1"
MAX_DISTANCE_KM = 5.0
PLACE_TYPES = {"TravelPlace", "Restaurant", "DrinkDessert", "Accommodation"}
NEAR_FOOD_TYPES = {"Restaurant", "DrinkDessert"}


EXPERIENCE_RULES: tuple[dict[str, object], ...] = (
    {
        "key": "pho_quay_morning",
        "types": {"Restaurant"},
        "terms": ("pho",),
        "category_terms": ("pho restaurant", "noodle shop", "vietnamese restaurant"),
        "max_targets": 24,
        "intent": "eat",
        "priority": "must",
        "time_slots": (("06:30", "10:00"), ("11:00", "14:00")),
        "recommended_items": ("Phở", "Quẩy"),
        "reason": "Trải nghiệm ẩm thực Hà Nội tiêu biểu: ăn phở nóng, thường dùng kèm quẩy, ưu tiên buổi sáng; cần kiểm tra giờ phục vụ thực tế.",
        "activity_ids": ("activity_eat_pho",),
    },
    {
        "key": "bun_cha_hanoi",
        "types": {"Restaurant"},
        "terms": ("bun cha",),
        "category_terms": ("vietnamese restaurant",),
        "max_targets": 18,
        "intent": "eat",
        "priority": "must",
        "time_slots": (("11:00", "14:00"), ("18:00", "20:30")),
        "recommended_items": ("Bún chả",),
        "reason": "Một trải nghiệm ẩm thực đặc trưng của Hà Nội; phù hợp bữa trưa hoặc đầu buổi tối và cần đối chiếu giờ hoạt động.",
        "activity_ids": ("activity_eat_meal",),
    },
    {
        "key": "cha_ca_hanoi",
        "types": {"Restaurant"},
        "terms": ("cha ca",),
        "category_terms": ("vietnamese restaurant", "seafood restaurant", "restaurant"),
        "max_targets": 12,
        "intent": "eat",
        "priority": "recommended",
        "time_slots": (("11:00", "14:00"), ("18:00", "21:00")),
        "recommended_items": ("Chả cá",),
        "reason": "Gợi ý món chả cá theo ẩm thực địa phương Hà Nội; nên kiểm tra chi nhánh và giờ phục vụ trước khi xếp lịch.",
        "activity_ids": ("activity_eat_meal",),
    },
    {
        "key": "egg_coffee_hanoi",
        "types": {"DrinkDessert"},
        "terms": ("egg coffee", "ca phe trung", "giang coffee", "dinh coffee"),
        "category_terms": ("cafe", "coffee shop"),
        "max_targets": 18,
        "intent": "drink",
        "priority": "must",
        "time_slots": (("07:00", "11:00"), ("14:00", "18:00")),
        "recommended_items": ("Cà phê trứng",),
        "reason": "Cà phê trứng là trải nghiệm đồ uống nổi bật thường được gắn với Hà Nội; cần xác minh menu và giờ mở cửa hiện tại.",
        "activity_ids": ("activity_drink_coffee",),
    },
    {
        "key": "west_lake_banh_tom",
        "types": {"Restaurant"},
        "terms": ("banh tom", "west lake shrimp"),
        "category_terms": ("bistro", "restaurant"),
        "max_targets": 8,
        "intent": "eat",
        "priority": "recommended",
        "time_slots": (("11:00", "14:00"), ("17:30", "21:00")),
        "recommended_items": ("Bánh tôm Hồ Tây",),
        "reason": "Gợi ý thử bánh tôm khu vực Hồ Tây; cần kiểm tra địa chỉ chi nhánh và giờ phục vụ.",
        "activity_ids": ("activity_eat_meal",),
    },
    {
        "key": "ho_chi_minh_mausoleum",
        "types": {"TravelPlace"},
        "terms": ("ho chi minh mausoleum", "ho chi minh mausoleum"),
        "category_terms": ("historical landmark", "memorial estate", "memorial"),
        "max_targets": 6,
        "intent": "visit",
        "priority": "must",
        "time_slots": (("06:00", "11:00"),),
        "recommended_items": ("Lăng Chủ tịch Hồ Chí Minh", "Quảng trường Ba Đình"),
        "reason": "Điểm tham quan lịch sử - biểu tượng thường được ưu tiên khi đến Hà Nội; phải kiểm tra lịch mở cửa, quy định trang phục và khu vực hạn chế.",
        "activity_ids": ("activity_cultural_visit", "activity_sightseeing"),
    },
    {
        "key": "ba_dinh_square",
        "types": {"TravelPlace"},
        "terms": ("ba dinh square",),
        "category_terms": ("historical landmark", "town square", "cultural landmark"),
        "max_targets": 6,
        "intent": "visit",
        "priority": "must",
        "time_slots": (("06:00", "11:00"), ("16:00", "20:00")),
        "recommended_items": ("Quảng trường Ba Đình",),
        "reason": "Quảng trường trung tâm cạnh Lăng Bác; thường có lễ và sinh hoạt cộng đồng, nên kiểm tra lịch sự kiện.",
        "activity_ids": ("activity_cultural_visit", "activity_sightseeing"),
    },
    {
        "key": "hoan_kiem_lake",
        "types": {"TravelPlace"},
        "terms": ("hoan kiem lake",),
        "category_terms": ("lake",),
        "max_targets": 4,
        "intent": "walk",
        "priority": "must",
        "time_slots": (("06:00", "10:00"), ("16:00", "22:00")),
        "recommended_items": ("Hồ Hoàn Kiếm",),
        "reason": "Hồ ở trung tâm với không gian đi bộ quanh bờ hồ và đền Ngọc Sơn; phù hợp buổi sáng hoặc tối.",
        "activity_ids": ("activity_walk_outdoors", "activity_sightseeing"),
    },
    {
        "key": "ngoc_son_temple",
        "types": {"TravelPlace"},
        "terms": ("ngoc son temple",),
        "category_terms": ("place of worship", "temple"),
        "max_targets": 4,
        "intent": "visit",
        "priority": "must",
        "time_slots": (("08:00", "11:30"), ("14:00", "17:30")),
        "recommended_items": ("Đền Ngọc Sơn",),
        "reason": "Đền cổ trên đảo nhỏ giữa Hồ Hoàn Kiếm; kết hợp cùng đi bộ quanh hồ.",
        "activity_ids": ("activity_cultural_visit",),
    },
    {
        "key": "temple_of_literature",
        "types": {"TravelPlace"},
        "terms": ("temple of literature",),
        "category_terms": ("historical landmark", "place of worship", "tourist attraction"),
        "max_targets": 4,
        "intent": "visit",
        "priority": "must",
        "time_slots": (("08:00", "11:30"), ("14:00", "17:30")),
        "recommended_items": ("Văn Miếu - Quốc Tử Giám",),
        "reason": "Di tích văn hóa - giáo dục tiêu biểu của Hà Nội; tham quan ban ngày và kiểm tra giờ mở cửa thực tế.",
        "activity_ids": ("activity_cultural_visit",),
    },
    {
        "key": "thang_long_citadel",
        "types": {"TravelPlace"},
        "terms": ("thang long citadel", "imperial citadel of thang long"),
        "category_terms": ("historical landmark",),
        "max_targets": 4,
        "intent": "visit",
        "priority": "must",
        "time_slots": (("08:00", "11:30"), ("14:00", "17:30")),
        "recommended_items": ("Hoàng thành Thăng Long",),
        "reason": "Quần thể di sản và lịch sử quan trọng của Hà Nội; cần kiểm tra khu vực đang mở cửa và thời lượng tham quan.",
        "activity_ids": ("activity_cultural_visit", "activity_sightseeing"),
    },
    {
        "key": "hoa_lo_prison",
        "types": {"TravelPlace"},
        "terms": ("hoa lo prison relic",),
        "category_terms": ("history museum",),
        "max_targets": 2,
        "intent": "visit",
        "priority": "must",
        "time_slots": (("08:00", "11:30"), ("14:00", "17:30")),
        "recommended_items": ("Di tích Nhà tù Hỏa Lò",),
        "reason": "Không gian lịch sử - bảo tàng nổi bật ở trung tâm; nên dành đủ thời gian đọc tư liệu và kiểm tra giờ đón khách.",
        "activity_ids": ("activity_cultural_visit", "activity_sightseeing"),
    },
    {
        "key": "west_lake",
        "types": {"TravelPlace"},
        "terms": ("west lake",),
        "category_terms": ("lake",),
        "max_targets": 2,
        "intent": "walk",
        "priority": "recommended",
        "time_slots": (("06:00", "09:00"), ("16:00", "19:00")),
        "recommended_items": ("Hồ Tây",),
        "reason": "Phù hợp đi dạo, ngắm cảnh và kết hợp các điểm ven Hồ Tây vào sáng sớm hoặc cuối chiều.",
        "activity_ids": ("activity_walk_outdoors", "activity_sightseeing"),
    },
    {
        "key": "tran_quoc_pagoda",
        "types": {"TravelPlace"},
        "terms": ("tran quoc pagoda",),
        "category_terms": ("buddhist temple",),
        "max_targets": 2,
        "intent": "visit",
        "priority": "must",
        "time_slots": (("07:00", "11:00"), ("14:00", "18:00")),
        "recommended_items": ("Chùa Trấn Quốc",),
        "reason": "Ngôi chùa cổ trên bán đảo nhỏ của Hồ Tây; nên tham quan sáng sớm và tuân thủ quy định của chùa.",
        "activity_ids": ("activity_cultural_visit",),
    },
    {
        "key": "thang_long_water_puppet",
        "types": {"TravelPlace"},
        "terms": ("thang long water puppet theatre",),
        "category_terms": ("puppet theater",),
        "max_targets": 2,
        "intent": "cultural_evening",
        "priority": "recommended",
        "time_slots": (("17:00", "22:00"),),
        "recommended_items": ("Múa rối nước Thăng Long",),
        "reason": "Trải nghiệm biểu diễn truyền thống phù hợp buổi tối; cần kiểm tra suất diễn và tình trạng vé.",
        "activity_ids": ("activity_cultural_visit",),
    },
)


def clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.casefold() in {"nan", "none", "null"} else text


def normalized(value: object) -> str:
    import re
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", clean(value).casefold())
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain).split())


def edge_id(from_id: str, relationship: str, to_id: str) -> str:
    digest = hashlib.sha256(f"{from_id}|{relationship}|{to_id}".encode("utf-8")).hexdigest()[:20]
    return f"edge_{digest}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\r\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: object) -> float | None:
    try:
        parsed = float(clean(value))
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def load_graph(graph_dir: Path) -> dict[str, object]:
    entities = read_csv(graph_dir / "entities.csv")
    properties = read_csv(graph_dir / "properties.csv")
    relationships = read_csv(graph_dir / "relationships.csv")
    entity_by_id = {row["id"]: row for row in entities}
    properties_by_entity: dict[str, dict[str, str]] = defaultdict(dict)
    for row in properties:
        properties_by_entity[row["entity_id"]][row["key"]] = row["value"]
    return {
        "entities": entities,
        "properties": properties,
        "relationships": relationships,
        "entity_by_id": entity_by_id,
        "properties_by_entity": properties_by_entity,
    }


def find_hanoi_area(graph: dict[str, object]) -> str:
    entities = graph["entities"]
    candidates = [
        row for row in entities
        if row.get("type") == "Area" and normalized(row.get("name")) in {"ha noi", "hanoi"}
    ]
    if not candidates:
        raise ValueError("Không tìm thấy Area Hà Nội trong entities.csv")
    candidates.sort(key=lambda row: (normalized(row.get("name")), row.get("id", "")))
    return candidates[0]["id"]


def hanoi_place_ids(graph: dict[str, object], hanoi_area_id: str) -> set[str]:
    entity_by_id = graph["entity_by_id"]
    return {
        row["from_entity_id"]
        for row in graph["relationships"]
        if row.get("relationship") == "LOCATED_IN"
        and row.get("to_entity_id") == hanoi_area_id
        and entity_by_id.get(row.get("from_entity_id", ""), {}).get("type") in PLACE_TYPES
    }


def searchable_text(entity: dict[str, str], properties: dict[str, str]) -> dict[str, str]:
    return {
        "name": normalized(entity.get("name", "")),
        "category": normalized(properties.get("source_category", "") or properties.get("place_category", "")),
        "description": normalized(properties.get("description", "")),
        "address": normalized(properties.get("address", "")),
    }


def quality_score(entity: dict[str, str], properties: dict[str, str], score: int) -> tuple[int, float, int, str]:
    rating = parse_float(properties.get("rating")) or 0.0
    review_count = int(parse_float(properties.get("review_count")) or 0)
    return (score, rating, review_count, entity.get("name", "").casefold())


def time_slots(rule: dict[str, object]) -> list[dict[str, str]]:
    return [
        {"start": start, "end": end}
        for start, end in rule["time_slots"]
    ]


def recommendation(rule: dict[str, object]) -> dict[str, object]:
    item: dict[str, object] = {
        "experienceKey": rule["key"],
        "intent": rule["intent"],
        "priority": rule["priority"],
        "timeSlots": time_slots(rule),
        "reason": rule["reason"],
    }
    if rule["recommended_items"]:
        item["recommendedItems"] = list(rule["recommended_items"])
    return item


def rule_match_score(rule: dict[str, object], texts: dict[str, str]) -> int:
    score = 0
    for term in rule["terms"]:
        normalized_term = normalized(term)
        if not normalized_term:
            continue
        if normalized_term in texts["name"]:
            score += 4
        elif normalized_term in texts["category"]:
            score += 2
        elif normalized_term in texts["description"] or normalized_term in texts["address"]:
            score += 1
    for category_term in rule["category_terms"]:
        normalized_category = normalized(category_term)
        if not normalized_category:
            continue
        if normalized_category in texts["category"]:
            score += 1
    return score


def select_special_targets(graph: dict[str, object], hanoi_area_id: str) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[str]]]:
    entity_by_id = graph["entity_by_id"]
    properties_by_entity = graph["properties_by_entity"]
    hanoi_ids = hanoi_place_ids(graph, hanoi_area_id)
    selected: dict[str, list[dict[str, object]]] = defaultdict(list)
    rule_matches: dict[str, list[str]] = {}

    for rule in EXPERIENCE_RULES:
        candidates: list[tuple[tuple[int, float, int, str], str]] = []
        for entity_id in hanoi_ids:
            entity = entity_by_id[entity_id]
            if entity.get("type") not in rule["types"]:
                continue
            texts = searchable_text(entity, properties_by_entity.get(entity_id, {}))
            score = rule_match_score(rule, texts)
            if score <= 0:
                continue
            candidates.append((quality_score(entity, properties_by_entity.get(entity_id, {}), score), entity_id))
        candidates.sort(key=lambda item: item[0], reverse=True)
        chosen = [entity_id for _, entity_id in candidates[: int(rule["max_targets"])] ]
        rule_matches[rule["key"]] = chosen
        rec = recommendation(rule)
        for entity_id in chosen:
            selected[entity_id].append(rec)

    return dict(selected), rule_matches


def build_special_edges(
    graph: dict[str, object],
    hanoi_area_id: str,
    selected: dict[str, list[dict[str, object]]],
    rule_matches: dict[str, list[str]],
) -> list[dict[str, str]]:
    entity_by_id = graph["entity_by_id"]
    activity_recommendations: dict[str, list[dict[str, object]]] = defaultdict(list)
    rule_by_key = {rule["key"]: rule for rule in EXPERIENCE_RULES}
    for key, entity_ids in rule_matches.items():
        rule = rule_by_key[key]
        rec = recommendation(rule)
        for activity_id in rule["activity_ids"]:
            if activity_id in entity_by_id and rec not in activity_recommendations[activity_id]:
                activity_recommendations[activity_id].append(rec)

    edges: list[dict[str, str]] = []
    for entity_id in sorted(selected):
        if entity_id not in entity_by_id:
            continue
        key = (hanoi_area_id, "SPECIAL_EXPERIENCE", entity_id)
        edges.append({
            "id": edge_id(*key),
            "from_entity_id": hanoi_area_id,
            "relationship": "SPECIAL_EXPERIENCE",
            "to_entity_id": entity_id,
            "recommendations": json.dumps(selected[entity_id], ensure_ascii=False, separators=(",", ":")),
            "source": SPECIAL_SOURCE,
        })
    for activity_id in sorted(activity_recommendations):
        key = (hanoi_area_id, "SPECIAL_EXPERIENCE", activity_id)
        edges.append({
            "id": edge_id(*key),
            "from_entity_id": hanoi_area_id,
            "relationship": "SPECIAL_EXPERIENCE",
            "to_entity_id": activity_id,
            "recommendations": json.dumps(activity_recommendations[activity_id], ensure_ascii=False, separators=(",", ":")),
            "source": SPECIAL_SOURCE,
        })
    return edges


def coordinates(graph: dict[str, object]) -> dict[str, tuple[float, float]]:
    entity_by_id = graph["entity_by_id"]
    properties_by_entity = graph["properties_by_entity"]
    result: dict[str, tuple[float, float]] = {}
    for entity_id, entity in entity_by_id.items():
        if entity.get("type") not in PLACE_TYPES:
            continue
        props = properties_by_entity.get(entity_id, {})
        latitude = parse_float(props.get("latitude"))
        longitude = parse_float(props.get("longitude"))
        if latitude is None or longitude is None or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            continue
        result[entity_id] = (latitude, longitude)
    return result


def haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    radius_km = 6371.0088
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def eligible_near_ids(graph: dict[str, object], special_edges: list[dict[str, str]]) -> tuple[set[str], set[str], set[str]]:
    entity_by_id = graph["entity_by_id"]
    special_food_ids = {
        row["to_entity_id"]
        for row in [*graph["relationships"], *special_edges]
        if row.get("relationship") == "SPECIAL_EXPERIENCE"
        and entity_by_id.get(row.get("to_entity_id", ""), {}).get("type") in NEAR_FOOD_TYPES
    }
    travel_place_ids = {
        entity_id for entity_id, entity in entity_by_id.items()
        if entity.get("type") == "TravelPlace"
    }
    special_travel_place_ids = {
        row["to_entity_id"]
        for row in [*graph["relationships"], *special_edges]
        if row.get("relationship") == "SPECIAL_EXPERIENCE"
        and entity_by_id.get(row.get("to_entity_id", ""), {}).get("type") == "TravelPlace"
    }
    return travel_place_ids, special_food_ids, special_travel_place_ids


def near_pairs(
    graph: dict[str, object],
    special_edges: list[dict[str, str]],
    max_distance_km: float = MAX_DISTANCE_KM,
) -> tuple[list[tuple[str, str, float]], dict[str, int]]:
    """Tính cặp NEAR giữa:
    - TravelPlace với TravelPlace (cả 2 phía đều nằm trong nhóm TravelPlace eligible)
    - Restaurant/DrinkDessert có SPECIAL_EXPERIENCE với TravelPlace
    - Hai Restaurant/DrinkDessert cùng có SPECIAL_EXPERIENCE
    - Hai TravelPlace có SPECIAL_EXPERIENCE với nhau (vẫn đếm trong TP-TP)
    Bỏ qua: Accommodation và node không có toạ độ.
    """
    entity_by_id = graph["entity_by_id"]
    coords = coordinates(graph)
    travel_place_ids, special_food_ids, special_travel_place_ids = eligible_near_ids(graph, special_edges)

    tp_with_coords = sorted(i for i in travel_place_ids if i in coords)
    food_with_coords = sorted(i for i in special_food_ids if i in coords)
    stp_with_coords = sorted(i for i in special_travel_place_ids if i in coords)
    food_with_coords_set = set(food_with_coords)

    cell_size = max(max_distance_km / 111.0, 0.001)
    grid: dict[tuple[int, int], list[str]] = defaultdict(list)
    for entity_id in tp_with_coords:
        latitude, longitude = coords[entity_id]
        grid[(math.floor(latitude / cell_size), math.floor(longitude / cell_size))].append(entity_id)

    pairs: list[tuple[str, str, float]] = []
    seen: set[tuple[str, str]] = set()

    def add_pair(a: str, b: str) -> None:
        if a == b:
            return
        if a > b:
            a, b = b, a
        if (a, b) in seen:
            return
        distance = haversine_km(coords[a], coords[b])
        if distance < max_distance_km:
            seen.add((a, b))
            pairs.append((a, b, distance))

    # TravelPlace ↔ TravelPlace
    for from_id in tp_with_coords:
        latitude, longitude = coords[from_id]
        cell_lat = math.floor(latitude / cell_size)
        cell_lon = math.floor(longitude / cell_size)
        for delta_lat in range(-2, 3):
            for delta_lon in range(-2, 3):
                for to_id in grid.get((cell_lat + delta_lat, cell_lon + delta_lon), []):
                    add_pair(from_id, to_id)

    # Restaurant/DrinkDessert có SPECIAL_EXPERIENCE ↔ TravelPlace gần
    # Đã add TP-TP ở trên; giờ chỉ add FOOD ↔ TP
    for food_id in food_with_coords:
        latitude, longitude = coords[food_id]
        cell_lat = math.floor(latitude / cell_size)
        cell_lon = math.floor(longitude / cell_size)
        for delta_lat in range(-2, 3):
            for delta_lon in range(-2, 3):
                for tp_id in grid.get((cell_lat + delta_lat, cell_lon + delta_lon), []):
                    add_pair(food_id, tp_id)

    # Hai Restaurant/DrinkDessert có SPECIAL_EXPERIENCE (cùng loại hoặc khác loại)
    food_grid: dict[tuple[int, int], list[str]] = defaultdict(list)
    for food_id in food_with_coords:
        latitude, longitude = coords[food_id]
        food_grid[(math.floor(latitude / cell_size), math.floor(longitude / cell_size))].append(food_id)
    for food_id in food_with_coords:
        latitude, longitude = coords[food_id]
        cell_lat = math.floor(latitude / cell_size)
        cell_lon = math.floor(longitude / cell_size)
        for delta_lat in range(-2, 3):
            for delta_lon in range(-2, 3):
                for to_id in food_grid.get((cell_lat + delta_lat, cell_lon + delta_lon), []):
                    add_pair(food_id, to_id)

    pairs.sort(key=lambda item: (item[0], item[1]))
    type_counts: dict[str, int] = defaultdict(int)
    for from_id, to_id, _ in pairs:
        type_counts[f"{entity_by_id[from_id]['type']}->{entity_by_id[to_id]['type']}"] += 1
    return pairs, {
        "eligibleTravelPlaces": len(tp_with_coords),
        "eligibleSpecialFood": len(food_with_coords),
        "eligibleSpecialTravelPlaces": len(stp_with_coords),
        "undirectedPairs": len(pairs),
        "directedEdges": len(pairs) * 2,
        "pairTypeCounts": dict(sorted(type_counts.items())),
    }


def build_near_edges(
    graph: dict[str, object],
    special_edges: list[dict[str, str]],
    max_distance_km: float = MAX_DISTANCE_KM,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    pairs, stats = near_pairs(graph, special_edges, max_distance_km)
    entity_by_id = graph["entity_by_id"]
    edges: list[dict[str, str]] = []
    for first_id, second_id, distance in pairs:
        distance_meters = round(distance * 1000, 1)
        for from_id, to_id in ((first_id, second_id), (second_id, first_id)):
            key = (from_id, "NEAR", to_id)
            rec = [{
                "distanceMeters": distance_meters,
                "thresholdMeters": round(max_distance_km * 1000),
                "calculation": "haversine",
                "symmetric": True,
                "reason": "Khoảng cách đường chim bay giữa hai node nhỏ hơn ngưỡng; không phải thời gian hoặc quãng đường di chuyển thực tế.",
            }]
            edges.append({
                "id": edge_id(*key),
                "from_entity_id": from_id,
                "relationship": "NEAR",
                "to_entity_id": to_id,
                "recommendations": json.dumps(rec, ensure_ascii=False, separators=(",", ":")),
                "source": NEAR_SOURCE,
            })
    return edges, stats


def merge_edges(existing: list[dict[str, str]], additions: list[dict[str, str]]) -> tuple[list[dict[str, str]], int, int]:
    by_key = {
        (row.get("from_entity_id", ""), row.get("relationship", ""), row.get("to_entity_id", "")): row
        for row in existing
    }
    added = 0
    refreshed = 0
    for row in additions:
        key = (row["from_entity_id"], row["relationship"], row["to_entity_id"])
        current = by_key.get(key)
        if current is None:
            by_key[key] = row
            added += 1
        elif current.get("source", "") in {SPECIAL_SOURCE, NEAR_SOURCE}:
            current.update(row)
            refreshed += 1
    merged = list(by_key.values())
    merged.sort(key=lambda row: (row.get("from_entity_id", ""), row.get("relationship", ""), row.get("to_entity_id", "")))
    return merged, added, refreshed


def backup_graph(graph_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = graph_dir / "backups" / f"edge-enrichment-{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for path in graph_dir.iterdir():
        if path.is_file():
            shutil.copy2(path, backup_dir / path.name)
    return backup_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-dir", type=Path, default=DEFAULT_GRAPH)
    parser.add_argument("--max-distance-km", type=float, default=MAX_DISTANCE_KM)
    parser.add_argument("--analyze-only", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def build_summary(graph: dict[str, object], special_edges: list[dict[str, str]], near_stats: dict[str, int], rule_matches: dict[str, list[str]]) -> dict[str, object]:
    entity_by_id = graph["entity_by_id"]
    existing_counts: dict[str, int] = defaultdict(int)
    for row in graph["relationships"]:
        existing_counts[row.get("relationship", "")] += 1
    return {
        "hanoiAreaId": find_hanoi_area(graph),
        "existingRelationshipCounts": dict(sorted(existing_counts.items())),
        "specialExperienceEdgeCount": len(special_edges),
        "specialExperienceTargetTypeCounts": {
            node_type: sum(1 for row in special_edges if entity_by_id.get(row["to_entity_id"], {}).get("type") == node_type)
            for node_type in ("TravelPlace", "Restaurant", "DrinkDessert", "Activity")
        },
        "near": near_stats,
        "ruleMatchCounts": {key: len(value) for key, value in sorted(rule_matches.items())},
        "ruleMatchIds": {key: value for key, value in sorted(rule_matches.items())},
    }


def apply(graph_dir: Path, max_distance_km: float) -> dict[str, object]:
    graph = load_graph(graph_dir)
    hanoi_area_id = find_hanoi_area(graph)
    selected, rule_matches = select_special_targets(graph, hanoi_area_id)
    special_edges = build_special_edges(graph, hanoi_area_id, selected, rule_matches)
    near_edges, near_stats = build_near_edges(graph, special_edges, max_distance_km)
    additions = [*special_edges, *near_edges]
    merged, added, refreshed = merge_edges(graph["relationships"], additions)
    backup = backup_graph(graph_dir)
    fieldnames = ["id", "from_entity_id", "relationship", "to_entity_id", "recommendations", "source"]
    temporary = Path(tempfile.mkstemp(prefix="relationships-", suffix=".csv", dir=graph_dir)[1])
    try:
        write_csv(temporary, fieldnames, merged)
        temporary.replace(graph_dir / "relationships.csv")
    finally:
        if temporary.exists():
            temporary.unlink()
    summary = build_summary(graph, special_edges, near_stats, rule_matches)
    summary.update({
        "backupPath": str(backup),
        "addedEdgeCount": added,
        "refreshedEdgeCount": refreshed,
        "relationshipCountsAfter": {
            relationship: sum(1 for row in merged if row.get("relationship") == relationship)
            for relationship in sorted({row.get("relationship", "") for row in merged})
        },
        "totalEdgesAfter": len(merged),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "specialExperienceSource": SPECIAL_SOURCE,
        "nearSource": NEAR_SOURCE,
        "nearDirectionPolicy": "two directed rows per undirected pair",
    })
    report_path = graph_dir / "edge_enrichment_report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args()
    graph_dir = args.graph_dir.resolve()
    if args.max_distance_km <= 0:
        raise ValueError("--max-distance-km phải lớn hơn 0")
    if not (args.analyze_only or args.apply):
        raise ValueError("Dùng --analyze-only hoặc --apply")
    graph = load_graph(graph_dir)
    hanoi_area_id = find_hanoi_area(graph)
    selected, rule_matches = select_special_targets(graph, hanoi_area_id)
    special_edges = build_special_edges(graph, hanoi_area_id, selected, rule_matches)
    near_edges, near_stats = build_near_edges(graph, special_edges, args.max_distance_km)
    if args.analyze_only:
        summary = build_summary(graph, special_edges, near_stats, rule_matches)
        summary["plannedNearEdgeCount"] = len(near_edges)
        summary["plannedTotalEdgeCount"] = len(graph["relationships"]) + len(special_edges) + len(near_edges)
    else:
        summary = apply(graph_dir, args.max_distance_km)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
