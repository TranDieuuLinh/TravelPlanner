import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1] / "knowledge-graph-real-v2"
SOURCE_ADM = "inference:adm-hierarchy-from-address:v1"
SOURCE_NEAR = "inference:adm-adjacency-curated:v1"
VIETNAM_ID = "area_country_9d1d170e85"
HANOI_ID = "area_city_0c21619b4e"


HANOI_DISTRICTS = [
    "Ba Đình",
    "Hoàn Kiếm",
    "Tây Hồ",
    "Long Biên",
    "Cầu Giấy",
    "Đống Đa",
    "Hai Bà Trưng",
    "Hoàng Mai",
    "Thanh Xuân",
    "Sóc Sơn",
    "Đông Anh",
    "Gia Lâm",
    "Nam Từ Liêm",
    "Thanh Trì",
    "Bắc Từ Liêm",
    "Mê Linh",
    "Hà Đông",
    "Sơn Tây",
    "Ba Vì",
    "Phúc Thọ",
    "Đan Phượng",
    "Hoài Đức",
    "Quốc Oai",
    "Thạch Thất",
    "Chương Mỹ",
    "Thanh Oai",
    "Thường Tín",
    "Phú Xuyên",
    "Ứng Hòa",
    "Mỹ Đức",
]


HANOI_ADM2_NEAR = {
    "Ba Đình": ["Hoàn Kiếm", "Tây Hồ", "Cầu Giấy", "Đống Đa"],
    "Hoàn Kiếm": ["Ba Đình", "Đống Đa", "Hai Bà Trưng"],
    "Tây Hồ": ["Ba Đình", "Cầu Giấy", "Bắc Từ Liêm", "Đông Anh"],
    "Long Biên": ["Hoàn Kiếm", "Hai Bà Trưng", "Gia Lâm", "Đông Anh"],
    "Cầu Giấy": ["Ba Đình", "Tây Hồ", "Bắc Từ Liêm", "Nam Từ Liêm", "Đống Đa", "Thanh Xuân"],
    "Đống Đa": ["Ba Đình", "Hoàn Kiếm", "Cầu Giấy", "Thanh Xuân", "Hai Bà Trưng"],
    "Hai Bà Trưng": ["Hoàn Kiếm", "Đống Đa", "Thanh Xuân", "Hoàng Mai", "Long Biên"],
    "Hoàng Mai": ["Hai Bà Trưng", "Thanh Xuân", "Thanh Trì", "Gia Lâm"],
    "Thanh Xuân": ["Cầu Giấy", "Đống Đa", "Hai Bà Trưng", "Hoàng Mai", "Hà Đông", "Nam Từ Liêm", "Thanh Trì"],
    "Sóc Sơn": ["Mê Linh", "Đông Anh"],
    "Đông Anh": ["Sóc Sơn", "Mê Linh", "Bắc Từ Liêm", "Tây Hồ", "Long Biên", "Gia Lâm"],
    "Gia Lâm": ["Đông Anh", "Long Biên", "Hoàng Mai", "Thanh Trì"],
    "Nam Từ Liêm": ["Bắc Từ Liêm", "Cầu Giấy", "Thanh Xuân", "Hà Đông", "Hoài Đức"],
    "Thanh Trì": ["Thanh Xuân", "Hoàng Mai", "Gia Lâm", "Hà Đông", "Thanh Oai", "Thường Tín"],
    "Bắc Từ Liêm": ["Đan Phượng", "Hoài Đức", "Nam Từ Liêm", "Cầu Giấy", "Tây Hồ", "Đông Anh"],
    "Mê Linh": ["Sóc Sơn", "Đông Anh", "Đan Phượng"],
    "Hà Đông": ["Nam Từ Liêm", "Thanh Xuân", "Thanh Trì", "Thanh Oai", "Hoài Đức"],
    "Sơn Tây": ["Ba Vì", "Phúc Thọ", "Thạch Thất"],
    "Ba Vì": ["Sơn Tây", "Phúc Thọ", "Thạch Thất"],
    "Phúc Thọ": ["Ba Vì", "Sơn Tây", "Thạch Thất", "Quốc Oai", "Đan Phượng"],
    "Đan Phượng": ["Mê Linh", "Bắc Từ Liêm", "Hoài Đức", "Quốc Oai", "Phúc Thọ"],
    "Hoài Đức": ["Đan Phượng", "Bắc Từ Liêm", "Nam Từ Liêm", "Hà Đông", "Quốc Oai"],
    "Quốc Oai": ["Phúc Thọ", "Đan Phượng", "Hoài Đức", "Thạch Thất", "Chương Mỹ"],
    "Thạch Thất": ["Ba Vì", "Sơn Tây", "Phúc Thọ", "Quốc Oai", "Chương Mỹ"],
    "Chương Mỹ": ["Quốc Oai", "Thạch Thất", "Hà Đông", "Thanh Oai", "Ứng Hòa", "Mỹ Đức"],
    "Thanh Oai": ["Hà Đông", "Thanh Trì", "Thường Tín", "Phú Xuyên", "Ứng Hòa", "Chương Mỹ"],
    "Thường Tín": ["Thanh Trì", "Thanh Oai", "Phú Xuyên"],
    "Phú Xuyên": ["Thường Tín", "Thanh Oai", "Ứng Hòa"],
    "Ứng Hòa": ["Chương Mỹ", "Thanh Oai", "Phú Xuyên", "Mỹ Đức"],
    "Mỹ Đức": ["Chương Mỹ", "Ứng Hòa"],
}


ADM1_NEAR = {
    "Hà Nội": ["Phu Tho", "Thai Nguyen", "Bac Ninh", "Hung Yen", "Hoa Binh"],
    "Quang Ninh": ["Bac Ninh", "Hai Phong", "Lang Son"],
    "Da Nang": ["Quang Nam", "Thua Thien Hue"],
    "Dong Nai City": ["Ho Chi Minh", "Lam Dong", "Binh Duong", "Binh Phuoc", "Ba Ria - Vung Tau"],
    "Lao Cai": ["Lai Chau", "Dien Bien", "Son La", "Yen Bai", "Ha Giang"],
    "Cao Bang": ["Tuyen Quang", "Thai Nguyen", "Lang Son"],
    "Thai Nguyen": ["Hà Nội", "Bac Ninh", "Phu Tho", "Tuyen Quang", "Cao Bang", "Lang Son"],
    "Phu Tho": ["Hà Nội", "Thai Nguyen", "Tuyen Quang", "Son La", "Hoa Binh"],
    "Ninh Binh": ["Thanh Hoa", "Hoa Binh", "Ha Nam", "Nam Dinh"],
    "Thanh Hoa": ["Ninh Binh", "Hoa Binh", "Son La", "Nghe An"],
    "Lam Dong": ["Dong Nai City", "Khanh Hoa", "Ninh Thuan", "Binh Thuan", "Dak Lak", "Dak Nong"],
    "Dien Bien": ["Lai Chau", "Lao Cai", "Son La"],
    "Bac Ninh": ["Hà Nội", "Thai Nguyen", "Quang Ninh", "Hung Yen", "Hai Duong"],
    "Ho Chi Minh": ["Dong Nai City", "Binh Duong", "Long An", "Tay Ninh", "Ba Ria - Vung Tau"],
    "Lai Chau": ["Dien Bien", "Lao Cai", "Son La"],
    "Tuyen Quang": ["Cao Bang", "Thai Nguyen", "Phu Tho", "Lao Cai", "Ha Giang"],
    "Son La": ["Dien Bien", "Lai Chau", "Lao Cai", "Phu Tho", "Thanh Hoa", "Hoa Binh"],
    "Hung Yen": ["Hà Nội", "Bac Ninh", "Hai Duong", "Thai Binh", "Ha Nam"],
    "Khanh Hoa": ["Lam Dong", "Dak Lak", "Phu Yen", "Ninh Thuan"],
}


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


def edge_id(relationship, from_id, to_id):
    return stable_id("edge", f"{relationship}|{from_id}|{to_id}")


def alias_for(name):
    return normalized(name).title()


def find_hanoi_district(address):
    norm_address = normalized(address)
    for district in sorted(HANOI_DISTRICTS, key=lambda item: len(normalized(item)), reverse=True):
        token = normalized(district)
        variants = [token, f"quan {token}", f"huyen {token}", f"thi xa {token}"]
        if any(re.search(rf"(^| ){re.escape(variant)}($| )", norm_address) for variant in variants):
            return district
    return None


def property_source_kind(source):
    if source.startswith("http"):
        return "url"
    if source.startswith("inference:"):
        return "inference"
    if source.startswith("dataset:"):
        return "dataset"
    return "other"


def main():
    entities = read_csv("entities.csv")
    aliases = read_csv("aliases.csv")
    properties = read_csv("properties.csv")
    relationships = read_csv("relationships.csv")

    entity_by_id = {row["id"]: row for row in entities}
    props_by_entity = defaultdict(dict)
    prop_rows_by_entity = defaultdict(list)
    for row in properties:
        props_by_entity[row["entity_id"]][row["key"]] = row["value"]
        prop_rows_by_entity[row["entity_id"]].append(row)

    area_name_to_id = {
        row["name"]: row["id"]
        for row in entities
        if row["type"] == "Area"
    }
    district_to_id = {
        district: stable_id("area_adm2_hanoi", normalized(district))
        for district in HANOI_DISTRICTS
    }

    district_stats = defaultdict(lambda: {"count": 0, "lat": 0.0, "lon": 0.0})
    updated_relationships = []
    matched = Counter()

    for row in relationships:
        if row["relationship"] == "LOCATED_IN" and row["to_entity_id"] == HANOI_ID:
            address = props_by_entity[row["from_entity_id"]].get("address", "")
            district = find_hanoi_district(address)
            if district:
                row = dict(row)
                row["to_entity_id"] = district_to_id[district]
                row["id"] = edge_id("LOCATED_IN", row["from_entity_id"], row["to_entity_id"])
                row["source"] = row["source"] or SOURCE_ADM
                matched[district] += 1
                lat = props_by_entity[row["from_entity_id"]].get("latitude")
                lon = props_by_entity[row["from_entity_id"]].get("longitude")
                try:
                    district_stats[district]["lat"] += float(lat)
                    district_stats[district]["lon"] += float(lon)
                    district_stats[district]["count"] += 1
                except (TypeError, ValueError):
                    pass
            else:
                matched["__unmatched__"] += 1
        updated_relationships.append(row)

    existing_ids = set(entity_by_id)
    for district, district_id in district_to_id.items():
        if district_id not in existing_ids:
            entities.append({
                "id": district_id,
                "name": district,
                "type": "Area",
                "status": "draft",
            })
            existing_ids.add(district_id)

        existing_keys = {row["key"] for row in prop_rows_by_entity[district_id]}
        stats = district_stats[district]
        property_values = {
            "administrative_level": "ADM2",
            "description": f"Khu vực ADM2 {district}, Hà Nội, Việt Nam được suy luận từ địa chỉ trong dữ liệu nguồn.",
        }
        if stats["count"]:
            property_values["latitude"] = str(stats["lat"] / stats["count"])
            property_values["longitude"] = str(stats["lon"] / stats["count"])
        for key, value in property_values.items():
            if key not in existing_keys:
                properties.append({
                    "entity_id": district_id,
                    "key": key,
                    "value": value,
                    "source": SOURCE_ADM,
                })

    for row in properties:
        if row["entity_id"] == VIETNAM_ID and row["key"] == "administrative_level":
            row["value"] = "ADM0"
        elif entity_by_id.get(row["entity_id"], {}).get("type") == "Area" and row["key"] == "administrative_level" and row["value"] == "city":
            row["value"] = "ADM1"

    existing_alias_pairs = {(row["entity_id"], row["alias"]) for row in aliases}
    for district, district_id in district_to_id.items():
        district_alias = alias_for(district)
        if (district_id, district_alias) not in existing_alias_pairs:
            aliases.append({"entity_id": district_id, "alias": district_alias})
            existing_alias_pairs.add((district_id, district_alias))

    existing_rel_keys = {
        (row["from_entity_id"], row["relationship"], row["to_entity_id"])
        for row in updated_relationships
    }

    def add_relationship(from_id, relationship, to_id, source):
        key = (from_id, relationship, to_id)
        if from_id == to_id or key in existing_rel_keys:
            return
        updated_relationships.append({
            "id": edge_id(relationship, from_id, to_id),
            "from_entity_id": from_id,
            "relationship": relationship,
            "to_entity_id": to_id,
            "recommendations": "[]",
            "source": source,
        })
        existing_rel_keys.add(key)

    for area_name, area_id in area_name_to_id.items():
        if area_id != VIETNAM_ID:
            add_relationship(area_id, "PART_OF", VIETNAM_ID, "dataset:hanoi_travel_relational_20260802/places.csv#city-country")

    for district, district_id in district_to_id.items():
        add_relationship(district_id, "PART_OF", HANOI_ID, SOURCE_ADM)

    for district, neighbors in HANOI_ADM2_NEAR.items():
        from_id = district_to_id[district]
        for neighbor in neighbors:
            if neighbor in district_to_id:
                to_id = district_to_id[neighbor]
                add_relationship(from_id, "NEAR", to_id, SOURCE_NEAR)
                add_relationship(to_id, "NEAR", from_id, SOURCE_NEAR)

    for area_name, neighbors in ADM1_NEAR.items():
        from_id = area_name_to_id.get(area_name)
        if not from_id:
            continue
        for neighbor in neighbors:
            to_id = area_name_to_id.get(neighbor)
            if to_id:
                add_relationship(from_id, "NEAR", to_id, SOURCE_NEAR)
                add_relationship(to_id, "NEAR", from_id, SOURCE_NEAR)

    write_csv("entities.csv", entities, ["id", "name", "type", "status"])
    write_csv("aliases.csv", aliases, ["entity_id", "alias"])
    write_csv("properties.csv", properties, ["entity_id", "key", "value", "source"])
    write_csv("relationships.csv", updated_relationships, ["id", "from_entity_id", "relationship", "to_entity_id", "recommendations", "source"])

    summary = {
        "district_located_in_matched": sum(count for key, count in matched.items() if key != "__unmatched__"),
        "hanoi_located_in_unmatched": matched["__unmatched__"],
        "district_match_counts": matched.most_common(),
        "entities": len(entities),
        "aliases": len(aliases),
        "properties": len(properties),
        "relationships": len(updated_relationships),
        "relationship_counts": Counter(row["relationship"] for row in updated_relationships).most_common(),
        "property_source_kinds": Counter(property_source_kind(row["source"]) for row in properties).most_common(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
