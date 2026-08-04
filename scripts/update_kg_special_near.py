import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1] / "knowledge-graph-real-v2"
SOURCE = "inference:special-experience-distance-near:v1"
MAX_DISTANCE_KM = 1.2


def read_csv(name):
    with (BASE_DIR / name).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(name, rows, fieldnames):
    with (BASE_DIR / name).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def stable_id(prefix, value):
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def edge_id(from_id, to_id):
    return stable_id("edge", f"NEAR|{from_id}|{to_id}|{SOURCE}")


def haversine_km(coord_a, coord_b):
    lat_a, lon_a = coord_a
    lat_b, lon_b = coord_b
    radius_km = 6371
    phi_a = math.radians(lat_a)
    phi_b = math.radians(lat_b)
    delta_phi = math.radians(lat_b - lat_a)
    delta_lambda = math.radians(lon_b - lon_a)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius_km * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def parse_coord(props, entity_id):
    try:
        return float(props[entity_id]["latitude"]), float(props[entity_id]["longitude"])
    except (KeyError, TypeError, ValueError):
        return None


def recommendation(distance_km, from_name, to_name):
    return json.dumps(
        [
            {
                "intent": "route_cluster",
                "priority": "recommended",
                "distanceKm": round(distance_km, 3),
                "reason": f"{from_name} và {to_name} đều là trải nghiệm nổi bật và cách nhau khoảng {distance_km:.1f} km, phù hợp gom vào cùng cụm lịch trình nếu thời gian/giờ mở cửa cho phép.",
            }
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def main():
    entities = read_csv("entities.csv")
    properties = read_csv("properties.csv")
    relationships = read_csv("relationships.csv")

    entity_by_id = {row["id"]: row for row in entities}
    props = defaultdict(dict)
    for row in properties:
        props[row["entity_id"]][row["key"]] = row["value"]

    special_target_ids = []
    for row in relationships:
        if row["relationship"] == "SPECIAL_EXPERIENCE" and row["to_entity_id"] not in special_target_ids:
            target_type = entity_by_id.get(row["to_entity_id"], {}).get("type")
            if target_type in {"TravelPlace", "Restaurant", "DrinkDessert", "Accommodation"}:
                special_target_ids.append(row["to_entity_id"])

    coordinates = {
        entity_id: parse_coord(props, entity_id)
        for entity_id in special_target_ids
    }
    coordinates = {
        entity_id: coord
        for entity_id, coord in coordinates.items()
        if coord is not None
    }

    relationships = [
        row for row in relationships
        if not (row["relationship"] == "NEAR" and row["source"] == SOURCE)
    ]
    existing_keys = {
        (row["from_entity_id"], row["relationship"], row["to_entity_id"], row["source"])
        for row in relationships
    }

    added_pairs = []

    def add_near(from_id, to_id, distance_km):
        key = (from_id, "NEAR", to_id, SOURCE)
        if key in existing_keys:
            return
        relationships.append(
            {
                "id": edge_id(from_id, to_id),
                "from_entity_id": from_id,
                "relationship": "NEAR",
                "to_entity_id": to_id,
                "recommendations": recommendation(
                    distance_km,
                    entity_by_id[from_id]["name"],
                    entity_by_id[to_id]["name"],
                ),
                "source": SOURCE,
            }
        )
        existing_keys.add(key)

    coord_ids = list(coordinates)
    for index, from_id in enumerate(coord_ids):
        for to_id in coord_ids[index + 1:]:
            distance_km = haversine_km(coordinates[from_id], coordinates[to_id])
            if distance_km <= MAX_DISTANCE_KM:
                add_near(from_id, to_id, distance_km)
                add_near(to_id, from_id, distance_km)
                added_pairs.append(
                    {
                        "distanceKm": round(distance_km, 3),
                        "from": entity_by_id[from_id]["name"],
                        "to": entity_by_id[to_id]["name"],
                    }
                )

    added_pairs.sort(key=lambda item: item["distanceKm"])
    write_csv(
        "relationships.csv",
        relationships,
        ["id", "from_entity_id", "relationship", "to_entity_id", "recommendations", "source"],
    )

    report = {
        "maxDistanceKm": MAX_DISTANCE_KM,
        "specialTargets": len(special_target_ids),
        "targetsWithCoordinates": len(coordinates),
        "undirectedNearPairsAdded": len(added_pairs),
        "directedNearEdgesAdded": len(added_pairs) * 2,
        "closestPairs": added_pairs[:80],
        "relationshipCounts": Counter(row["relationship"] for row in relationships).most_common(),
        "nearSourceCounts": Counter(row["source"] for row in relationships if row["relationship"] == "NEAR").most_common(),
    }
    (BASE_DIR / "special_near_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
