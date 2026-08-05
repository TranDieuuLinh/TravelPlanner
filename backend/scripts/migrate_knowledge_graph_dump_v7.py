"""Migrate the UTF-16 PostgreSQL Knowledge Graph dump to schema version 7.

The source dump is preserved. The migrated dump:
- adds nullable ``knowledge_properties.note``;
- removes legacy Place-to-Place ``NEAR`` edges;
- rewrites ``SPECIAL_EXPERIENCE`` to ``LocationEntity -> Activity``;
- creates Item nodes and Item edges from sourced ``recommendedItems`` values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = WORKSPACE_ROOT / "database" / "kg_dump.sql"
DEFAULT_OUTPUT = WORKSPACE_ROOT / "database" / "kg_dump_v7.sql"
MIGRATED_AT = "2026-08-05 00:00:00+00"


COPY_HEADERS = {
    "entities": "COPY public.knowledge_entities ",
    "properties": "COPY public.knowledge_properties ",
    "relationships": "COPY public.knowledge_relationships ",
}


@dataclass
class CopySection:
    header_index: int
    data_start: int
    data_end: int
    rows: list[list[str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def parse_copy_section(lines: list[str], prefix: str) -> CopySection:
    header_index = next(
        index for index, line in enumerate(lines) if line.startswith(prefix)
    )
    data_start = header_index + 1
    data_end = next(
        index for index in range(data_start, len(lines)) if lines[index] == r"\."
    )
    rows = [line.split("\t") for line in lines[data_start:data_end]]
    return CopySection(header_index, data_start, data_end, rows)


def copy_unescape(value: str) -> str | None:
    if value == r"\N":
        return None
    output: list[str] = []
    index = 0
    escapes = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
    while index < len(value):
        character = value[index]
        if character != "\\" or index + 1 >= len(value):
            output.append(character)
            index += 1
            continue
        next_character = value[index + 1]
        if next_character in escapes:
            output.append(escapes[next_character])
            index += 2
        elif next_character == "\\":
            output.append("\\")
            index += 2
        else:
            output.append(next_character)
            index += 2
    return "".join(output)


def copy_escape(value: object | None) -> str:
    if value is None:
        return r"\N"
    text = str(value)
    return (
        text.replace("\\", "\\\\")
        .replace("\b", "\\b")
        .replace("\f", "\\f")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("\v", "\\v")
    )


def decoded(row: list[str], index: int) -> str:
    return copy_unescape(row[index]) or ""


def normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def json_array(raw_value: str) -> list[dict[str, object]]:
    value = copy_unescape(raw_value) or "[]"
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def encode_json(items: list[dict[str, object]]) -> str:
    return copy_escape(json.dumps(items, ensure_ascii=False, separators=(",", ":")))


def merge_json_items(
    first: list[dict[str, object]], second: list[dict[str, object]]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in [*first, *second]:
        identity = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if identity not in seen:
            seen.add(identity)
            result.append(item)
    return result


def merge_sources(first: str, second: str) -> str:
    values: list[str] = []
    for source in [first, second]:
        for item in source.split(" | "):
            item = item.strip()
            if item and item not in values:
                values.append(item)
    return " | ".join(values)


def activity_categories_for_intents(intents: set[str]) -> set[str]:
    mapping = {
        "visit": {"cultural", "sightseeing"},
        "show": {"cultural", "sightseeing", "entertainment"},
        "walk": {"outdoor"},
        "eat": {"dining", "dessert"},
        "drink": {"beverage", "nightlife"},
        "stay": {"lodging"},
        "shopping": {"shopping"},
        "exercise": {"sports"},
        "wellness": {"wellness"},
        "nightlife": {"nightlife"},
    }
    categories: set[str] = set()
    for intent in intents:
        categories.update(mapping.get(intent.casefold(), set()))
    return categories


def activity_category_for_intent(intent: str) -> str:
    return {
        "visit": "sightseeing",
        "show": "cultural",
        "walk": "outdoor",
        "eat": "dining",
        "drink": "beverage",
        "stay": "lodging",
        "shopping": "shopping",
        "exercise": "sports",
        "wellness": "wellness",
        "nightlife": "nightlife",
    }.get(intent.casefold(), "experience")


def item_type_for_activity(category: str) -> tuple[str, str] | None:
    if category in {"dining", "dessert"}:
        return "FoodItem", "food"
    if category in {"beverage", "nightlife"}:
        return "DrinkItem", "drink"
    if category == "shopping":
        return "ProductItem", "product"
    return None


def next_numeric_id(rows: list[list[str]]) -> int:
    return max((int(decoded(row, 0)) for row in rows), default=0) + 1


def new_relationship_row(
    row_id: int,
    from_id: str,
    relationship: str,
    to_id: str,
    recommendations: list[dict[str, object]],
    source: str,
) -> list[str]:
    return [
        str(row_id),
        copy_escape(from_id),
        relationship,
        copy_escape(to_id),
        encode_json(recommendations),
        copy_escape(source),
        MIGRATED_AT,
        MIGRATED_AT,
    ]


def migrate(lines: list[str]) -> tuple[list[str], dict[str, object]]:
    sections = {
        name: parse_copy_section(lines, prefix)
        for name, prefix in COPY_HEADERS.items()
    }
    entity_rows = sections["entities"].rows
    property_rows = sections["properties"].rows
    relationship_rows = sections["relationships"].rows

    entity_type = {decoded(row, 0): decoded(row, 3) for row in entity_rows}
    entity_name = {decoded(row, 0): decoded(row, 1) for row in entity_rows}
    property_values: dict[str, dict[str, str]] = defaultdict(dict)
    for row in property_rows:
        property_values[decoded(row, 1)][decoded(row, 2)] = decoded(row, 3)

    activity_category = {
        entity_id: values.get("activity_category", "")
        for entity_id, values in property_values.items()
        if entity_type.get(entity_id) == "Activity"
    }

    removed_near = 0
    removed_legacy_special = 0
    unmapped_special = 0
    retained_rows: list[list[str]] = []
    legacy_special_rows: list[list[str]] = []
    for row in relationship_rows:
        relationship = decoded(row, 2)
        if relationship == "NEAR":
            removed_near += 1
        elif relationship == "SPECIAL_EXPERIENCE":
            legacy_special_rows.append(row)
            removed_legacy_special += 1
        else:
            retained_rows.append(row)

    next_relationship_id = next_numeric_id(relationship_rows)
    special_by_key: dict[tuple[str, str, str], list[str]] = {}
    special_activity_by_identity: dict[
        tuple[str, str], dict[str, object]
    ] = {}
    targets_place_by_key: dict[tuple[str, str, str], list[str]] = {}
    for legacy in legacy_special_rows:
        from_id = decoded(legacy, 1)
        target_id = decoded(legacy, 3)
        recommendations = json_array(legacy[4])
        source = decoded(legacy, 5)
        if entity_type.get(target_id) == "Activity":
            candidate_activities = [(target_id, recommendations)]
        else:
            candidate_activities: list[tuple[str, list[dict[str, object]]]] = []
            for recommendation in recommendations:
                title = str(recommendation.get("title", "")).strip()
                if not title:
                    target_name = entity_name.get(target_id, target_id)
                    title = f"Trải nghiệm {target_name}"
                identity = (target_id, normalized(title))
                activity = special_activity_by_identity.get(identity)
                if activity is None:
                    digest = hashlib.sha256(
                        f"special|{target_id}|{identity[1]}".encode()
                    ).hexdigest()[:16]
                    activity = {
                        "id": f"activity_special_{digest}",
                        "name": title,
                        "intent": str(recommendation.get("intent", "experience")),
                        "description": str(recommendation.get("reason", "")).strip()
                        or title,
                        "duration": recommendation.get("recommendedVisitMinutes"),
                        "time_slots": recommendation.get("timeSlots", []),
                        "source": source,
                    }
                    special_activity_by_identity[identity] = activity
                else:
                    activity["source"] = merge_sources(str(activity["source"]), source)
                activity_id = str(activity["id"])
                candidate_activities.append((activity_id, [recommendation]))
                target_key = (activity_id, "TARGETS_PLACE", target_id)
                existing_target = targets_place_by_key.get(target_key)
                if existing_target is None:
                    targets_place_by_key[target_key] = new_relationship_row(
                        next_relationship_id,
                        activity_id,
                        "TARGETS_PLACE",
                        target_id,
                        [],
                        source,
                    )
                    next_relationship_id += 1
                else:
                    existing_target[5] = copy_escape(
                        merge_sources(decoded(existing_target, 5), source)
                    )
        if not candidate_activities:
            unmapped_special += 1
            continue
        for activity_id, activity_recommendations in candidate_activities:
            key = (from_id, "SPECIAL_EXPERIENCE", activity_id)
            existing = special_by_key.get(key)
            if existing is None:
                special_by_key[key] = new_relationship_row(
                    next_relationship_id,
                    from_id,
                    "SPECIAL_EXPERIENCE",
                    activity_id,
                    activity_recommendations,
                    source,
                )
                next_relationship_id += 1
            else:
                existing[4] = encode_json(
                    merge_json_items(
                        json_array(existing[4]), activity_recommendations
                    )
                )
                existing[5] = copy_escape(merge_sources(decoded(existing, 5), source))

    # Derive concrete Item nodes only from explicitly sourced recommendedItems
    # on Place -> Activity edges with food, beverage, or shopping semantics.
    item_by_identity: dict[tuple[str, str], tuple[str, str, str, str]] = {}
    offers_item_by_key: dict[tuple[str, str, str], list[str]] = {}
    involves_item_by_key: dict[tuple[str, str, str], list[str]] = {}
    for edge in relationship_rows:
        if decoded(edge, 2) != "OFFERS_ACTIVITY":
            continue
        place_id = decoded(edge, 1)
        activity_id = decoded(edge, 3)
        classification = item_type_for_activity(activity_category.get(activity_id, ""))
        if classification is None:
            continue
        item_type, item_category = classification
        recommendations = json_array(edge[4])
        source = decoded(edge, 5)
        for recommendation in recommendations:
            items = recommendation.get("recommendedItems", [])
            if not isinstance(items, list):
                continue
            for value in items:
                name = str(value).strip()
                identity = normalized(name)
                if not identity:
                    continue
                item_key = (item_type, identity)
                if item_key not in item_by_identity:
                    digest = hashlib.sha256(f"{item_type}|{identity}".encode()).hexdigest()[:16]
                    prefix = {
                        "FoodItem": "food_item",
                        "DrinkItem": "drink_item",
                        "ProductItem": "product_item",
                    }[item_type]
                    item_by_identity[item_key] = (
                        f"{prefix}_{digest}", name, item_type, item_category
                    )
                item_id = item_by_identity[item_key][0]
                offers_key = (place_id, "OFFERS_ITEM", item_id)
                selected_recommendation = [{**recommendation, "recommendedItems": [name]}]
                existing_offer = offers_item_by_key.get(offers_key)
                if existing_offer is None:
                    offers_item_by_key[offers_key] = new_relationship_row(
                        next_relationship_id,
                        place_id,
                        "OFFERS_ITEM",
                        item_id,
                        selected_recommendation,
                        source,
                    )
                    next_relationship_id += 1
                else:
                    existing_offer[4] = encode_json(
                        merge_json_items(
                            json_array(existing_offer[4]), selected_recommendation
                        )
                    )
                    existing_offer[5] = copy_escape(
                        merge_sources(decoded(existing_offer, 5), source)
                    )
                involves_key = (activity_id, "INVOLVES_ITEM", item_id)
                existing_involves = involves_item_by_key.get(involves_key)
                if existing_involves is None:
                    involves_item_by_key[involves_key] = new_relationship_row(
                        next_relationship_id,
                        activity_id,
                        "INVOLVES_ITEM",
                        item_id,
                        [],
                        source,
                    )
                    next_relationship_id += 1
                else:
                    existing_involves[5] = copy_escape(
                        merge_sources(decoded(existing_involves, 5), source)
                    )

    next_property_id = next_numeric_id(property_rows)
    special_activity_entity_rows: list[list[str]] = []
    special_activity_property_rows: list[list[str]] = []
    for activity in sorted(
        special_activity_by_identity.values(), key=lambda item: str(item["id"])
    ):
        activity_id = str(activity["id"])
        activity_name = str(activity["name"])
        special_activity_entity_rows.append([
            copy_escape(activity_id),
            copy_escape(activity_name),
            copy_escape(normalized(activity_name)),
            "Activity",
            "draft",
            MIGRATED_AT,
            MIGRATED_AT,
        ])
        property_items: list[tuple[str, object]] = [
            ("description", activity["description"]),
            (
                "activity_category",
                activity_category_for_intent(str(activity["intent"])),
            ),
        ]
        if activity.get("duration") not in {None, ""}:
            property_items.append(
                ("typical_duration_minutes", activity["duration"])
            )
        if isinstance(activity.get("time_slots"), list) and activity["time_slots"]:
            property_items.append(
                (
                    "best_time_slots",
                    json.dumps(
                        activity["time_slots"],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            )
        for key, value in property_items:
            special_activity_property_rows.append([
                str(next_property_id),
                copy_escape(activity_id),
                key,
                copy_escape(value),
                copy_escape(activity["source"]),
                copy_escape(
                    "Derived from a legacy sourced SPECIAL_EXPERIENCE edge during schema v7 migration."
                ),
                MIGRATED_AT,
            ])
            next_property_id += 1

    new_item_entity_rows: list[list[str]] = []
    new_property_rows: list[list[str]] = []
    for item_id, name, item_type, item_category in sorted(item_by_identity.values()):
        new_item_entity_rows.append([
            copy_escape(item_id),
            copy_escape(name),
            copy_escape(normalized(name)),
            item_type,
            "draft",
            MIGRATED_AT,
            MIGRATED_AT,
        ])
        source_values = [
            decoded(row, 5)
            for key, row in offers_item_by_key.items()
            if key[2] == item_id
        ]
        source = ""
        for value in source_values:
            source = merge_sources(source, value)
        note = "Derived from sourced recommendations.recommendedItems during schema v7 migration."
        description_prefix = {
            "FoodItem": "Món ăn",
            "DrinkItem": "Đồ uống",
            "ProductItem": "Sản phẩm",
        }[item_type]
        for key, value in (
            ("description", f"{description_prefix} {name} được trích từ dữ liệu gợi ý có nguồn."),
            ("item_category", item_category),
        ):
            new_property_rows.append([
                str(next_property_id),
                copy_escape(item_id),
                key,
                copy_escape(value),
                copy_escape(source),
                copy_escape(note),
                MIGRATED_AT,
            ])
            next_property_id += 1

    # Existing property rows receive the new nullable note field before updated_at.
    migrated_property_rows = [
        [*row[:5], r"\N", *row[5:]] if len(row) == 6 else row
        for row in property_rows
    ]
    migrated_entity_rows = [
        *entity_rows,
        *special_activity_entity_rows,
        *new_item_entity_rows,
    ]
    migrated_relationship_rows = [
        *retained_rows,
        *special_by_key.values(),
        *targets_place_by_key.values(),
        *offers_item_by_key.values(),
        *involves_item_by_key.values(),
    ]

    replacements = {
        "entities": migrated_entity_rows,
        "properties": [
            *migrated_property_rows,
            *special_activity_property_rows,
            *new_property_rows,
        ],
        "relationships": migrated_relationship_rows,
    }
    for name in sorted(sections, key=lambda value: sections[value].data_start, reverse=True):
        section = sections[name]
        lines[section.data_start:section.data_end] = [
            "\t".join(row) for row in replacements[name]
        ]

    property_header_index = next(
        index for index, line in enumerate(lines)
        if line.startswith(COPY_HEADERS["properties"])
    )
    lines[property_header_index] = (
        "COPY public.knowledge_properties "
        "(id, entity_id, key, value, source, note, updated_at) FROM stdin;"
    )

    ddl_source = "    source text,\n    updated_at timestamp with time zone DEFAULT now() NOT NULL"
    ddl_target = "    source text,\n    note text,\n    updated_at timestamp with time zone DEFAULT now() NOT NULL"
    joined = "\n".join(lines)
    if ddl_source not in joined:
        raise ValueError("Không tìm thấy DDL knowledge_properties để thêm note")
    joined = joined.replace(ddl_source, ddl_target, 1)

    max_property_id = next_property_id - 1
    max_relationship_id = next_relationship_id - 1
    joined = re.sub(
        r"SELECT pg_catalog\.setval\('public\.knowledge_properties_id_seq', \d+, true\);",
        f"SELECT pg_catalog.setval('public.knowledge_properties_id_seq', {max_property_id}, true);",
        joined,
        count=1,
    )
    joined = re.sub(
        r"SELECT pg_catalog\.setval\('public\.knowledge_relationships_id_seq', \d+, true\);",
        f"SELECT pg_catalog.setval('public.knowledge_relationships_id_seq', {max_relationship_id}, true);",
        joined,
        count=1,
    )

    report = {
        "schemaVersion": 7,
        "sourceNodeCount": len(entity_rows),
        "outputNodeCount": len(migrated_entity_rows),
        "createdSpecialActivityNodeCount": len(special_activity_entity_rows),
        "createdItemNodeCount": len(new_item_entity_rows),
        "sourcePropertyCount": len(property_rows),
        "outputPropertyCount": (
            len(migrated_property_rows)
            + len(special_activity_property_rows)
            + len(new_property_rows)
        ),
        "sourceRelationshipCount": len(relationship_rows),
        "outputRelationshipCount": len(migrated_relationship_rows),
        "removedNearCount": removed_near,
        "removedLegacySpecialExperienceCount": removed_legacy_special,
        "createdSpecialExperienceCount": len(special_by_key),
        "createdTargetsPlaceCount": len(targets_place_by_key),
        "unmappedSpecialExperienceCount": unmapped_special,
        "createdOffersItemCount": len(offers_item_by_key),
        "createdInvolvesItemCount": len(involves_item_by_key),
        "maxPropertyId": max_property_id,
        "maxRelationshipId": max_relationship_id,
    }
    return joined.split("\n"), report


def main() -> int:
    args = parse_args()
    content = args.source.read_text(encoding="utf-16")
    migrated_lines, report = migrate(content.splitlines())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not args.dry_run:
        args.output.write_text("\r\n".join(migrated_lines) + "\r\n", encoding="utf-16")
        report_path = args.output.with_name(f"{args.output.stem}_report.json")
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.output}")
        print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
