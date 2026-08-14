import asyncio
import sys
from types import SimpleNamespace

from app.modules.place_checker.adapters.postgres_catalog import PostgresPlaceCatalog
from app.modules.place_checker.adapters.postgres_catalog_mapping import (
    PostgresCatalogMappingMixin,
)
from app.modules.place_checker.adapters.postgres_search_query import PLACE_SEARCH_SQL
from app.modules.place_checker.adapters.postgres_food_query import (
    SPECIAL_FOOD_RESTAURANT_SQL,
)
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence


def test_generic_travel_pool_uses_adm_candidates_without_experience_bucket_cap() -> None:
    assert "generic_travel_ranked" in PLACE_SEARCH_SQL
    assert "ranked.discovery_rank" in PLACE_SEARCH_SQL
    assert "$1 = 'travel place'" in PLACE_SEARCH_SQL
    assert "$1 <> 'travel place'" in PLACE_SEARCH_SQL
    assert "style_property.key = 'time_duration'" in PLACE_SEARCH_SQL
    assert "props.price_min IS NOT NULL OR props.price_max IS NOT NULL" in PLACE_SEARCH_SQL
    assert "activity.entity_type = 'ActivityItem'" in PLACE_SEARCH_SQL
    assert "'entityType', target.entity_type" in PLACE_SEARCH_SQL
    assert "key = 'time_windows'" in PLACE_SEARCH_SQL


def test_postgres_search_uses_trigram_prefilter_and_bounded_top_k() -> None:
    assert "entity.normalized_name % $1" in PLACE_SEARCH_SQL
    assert "alias.normalized_alias % $1" in PLACE_SEARCH_SQL
    assert "target.normalized_name % $1" in PLACE_SEARCH_SQL
    assert "LIMIT $4" in PLACE_SEARCH_SQL


def test_postgres_search_supports_cloud_relationship_shape() -> None:
    assert "WITH RECURSIVE adm_descendants" in PLACE_SEARCH_SQL
    assert "adm_ancestors" in PLACE_SEARCH_SQL
    assert "relationship_type = 'Special_Near'" in PLACE_SEARCH_SQL
    assert "'Near'" not in PLACE_SEARCH_SQL
    assert "'Must_Visit'" not in PLACE_SEARCH_SQL
    assert "special.to_entity_id" in PLACE_SEARCH_SQL
    assert "special.from_entity_id IN (SELECT id FROM adm_scope)" in PLACE_SEARCH_SQL
    assert "relationship_evidence" in PLACE_SEARCH_SQL
    assert "PARTITION BY relation.to_entity_id" in PLACE_SEARCH_SQL
    assert "'style_breakfast', 'style_lunch', 'style_dinner'" in PLACE_SEARCH_SQL


def test_special_food_query_traverses_adm_food_restaurant_and_anchor() -> None:
    assert "special.from_entity_id = $1" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "special.relationship_type = 'Special_Experience'" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "food.entity_type = 'FoodItem'" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "near_edge.relationship_type = 'Special_Near'" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "restaurant_special.relationship_type = 'Special_Experience'" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "food.food_item_id = restaurant_special.to_entity_id" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "offer.relationship_type = 'Offer_Item'" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "restaurant.entity_type = 'Restaurant'" in SPECIAL_FOOD_RESTAURANT_SQL


def test_special_food_query_does_not_match_food_by_name() -> None:
    assert "normalized_name" not in SPECIAL_FOOD_RESTAURANT_SQL
    assert "similarity(" not in SPECIAL_FOOD_RESTAURANT_SQL
    assert "food_item_tokens" not in SPECIAL_FOOD_RESTAURANT_SQL


def test_special_food_query_uses_offered_item_only_for_unmatched_anchor() -> None:
    assert "), special_pairs AS (" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "), fallback_pairs AS (" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "'offer_item_fallback'::text AS food_match_type" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "FROM special_pairs special" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "special.anchor_place_id = offered.anchor_place_id" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "SELECT * FROM special_pairs" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "UNION ALL\n    SELECT * FROM fallback_pairs" in SPECIAL_FOOD_RESTAURANT_SQL


def test_style_time_properties_only_fill_missing_place_metadata() -> None:
    relationship = PlaceRelationshipEvidence(
        relationship_type="Has_Style",
        direction="place_to_attribute",
        scope="place",
        from_entity_id="place:1",
        to_entity_id="style:nightlife",
        priority=80,
        properties={
            "time_windows": [{"start": "18:00", "end": "23:59"}],
            "time_duration": "PT120M",
        },
        score=0.65,
    )

    fallback = PostgresCatalogMappingMixin._metadata(
        "place:1", "TravelPlace", {}, [], None, [relationship]
    )
    direct = PostgresCatalogMappingMixin._metadata(
        "place:1",
        "TravelPlace",
        {"time_windows": '[{"start":"09:00","end":"10:00"}]', "time_duration": "PT45M"},
        [],
        None,
        [relationship],
    )

    assert fallback.typical_duration_minutes == 120
    assert fallback.opening_hours == ["18:00-23:59"]
    assert direct.typical_duration_minutes == 45
    assert direct.opening_hours == ["09:00-10:00"]


def test_style_node_properties_are_projected_onto_has_style_evidence() -> None:
    row = {
        "relationship_type": "Has_Style",
        "direction": "place_to_attribute",
        "scope": "place",
        "from_entity_id": "restaurant:1",
        "to_entity_id": "style:lunch",
        "related_entity_id": "style:lunch",
        "related_name": "Ăn trưa",
        "recommendations": '{"priority":80}',
        "source": "auto_attach",
        "source_note": None,
    }

    evidence = PostgresPlaceCatalog._metadata_relationship(
        row,
        style_properties={
            "time_duration": "PT45M",
            "time_windows": '[{"start":"11:00","end":"13:00"}]',
        },
    )
    relationship = PlaceRelationshipEvidence.model_validate(evidence)
    metadata = PostgresCatalogMappingMixin._metadata(
        "restaurant:1", "Restaurant", {}, [], None, [relationship]
    )

    assert metadata.typical_duration_minutes == 45
    assert metadata.opening_hours == ["11:00-13:00"]


def test_activity_node_timing_is_projected_onto_offer_evidence() -> None:
    row = {
        "relationship_type": "Offer_Item",
        "direction": "place_to_attribute",
        "scope": "place",
        "from_entity_id": "place:1",
        "to_entity_id": "activity:walk",
        "related_entity_id": "activity:walk",
        "related_name": "Đi bộ",
        "related_entity_type": "ActivityItem",
        "recommendations": '{"confidence":0.9}',
        "source": "manual",
        "source_note": None,
    }

    evidence = PostgresPlaceCatalog._metadata_relationship(
        row,
        target_properties={
            "time_windows": '[{"start":"08:00","end":"11:00"}]'
        },
    )

    assert evidence["properties"] == {
        "entityType": "ActivityItem",
        "time_windows": '[{"start":"08:00","end":"11:00"}]',
    }


def test_has_style_edge_properties_override_style_node_defaults() -> None:
    row = {
        "relationship_type": "Has_Style",
        "direction": "place_to_attribute",
        "scope": "place",
        "from_entity_id": "restaurant:1",
        "to_entity_id": "style:lunch",
        "related_entity_id": "style:lunch",
        "related_name": "Ăn trưa",
        "recommendations": (
            '{"properties":{"time_duration":"PT60M",'
            '"time_windows":[{"start":"11:30","end":"14:00"}]}}'
        ),
        "source": "manual",
        "source_note": None,
    }

    evidence = PostgresPlaceCatalog._metadata_relationship(
        row,
        style_properties={
            "time_duration": "PT45M",
            "time_windows": '[{"start":"11:00","end":"13:00"}]',
        },
    )

    assert evidence["properties"] == {
        "time_duration": "PT60M",
        "time_windows": [{"start": "11:30", "end": "14:00"}],
    }


def test_multiple_style_windows_are_combined_when_place_has_no_direct_timing() -> None:
    relationships = [
        PlaceRelationshipEvidence(
            relationship_type="Has_Style",
            direction="place_to_attribute",
            scope="place",
            from_entity_id="restaurant:1",
            to_entity_id=f"style:{meal}",
            priority=priority,
            properties={
                "time_duration": duration,
                "time_windows": [{"start": start, "end": end}],
            },
        )
        for meal, priority, duration, start, end in (
            ("breakfast", 90, "PT45M", "06:00", "10:00"),
            ("lunch", 80, "PT45M", "11:00", "13:00"),
            ("dinner", 70, "PT60M", "18:00", "20:00"),
        )
    ]

    metadata = PostgresCatalogMappingMixin._metadata(
        "restaurant:1", "Restaurant", {}, [], None, relationships
    )

    assert metadata.typical_duration_minutes == 60
    assert metadata.opening_hours == [
        "06:00-10:00",
        "11:00-13:00",
        "18:00-20:00",
    ]


def test_special_near_score_decreases_with_distance() -> None:
    base = {
        "relationship_type": "Special_Near",
        "direction": "place_to_place",
        "scope": "anchor",
        "from_entity_id": "place:1",
        "to_entity_id": "place:2",
        "related_entity_id": "place:2",
        "related_name": "Nearby",
        "source": "derived",
        "source_note": None,
    }
    near = PostgresPlaceCatalog._metadata_relationship(
        {**base, "recommendations": '{"distance_km":1,"threshold_km":5}'}
    )
    far = PostgresPlaceCatalog._metadata_relationship(
        {**base, "recommendations": '{"distance_km":4,"threshold_km":5}'}
    )

    assert near["score"] > far["score"]


def test_concurrent_catalog_calls_create_only_one_pool(monkeypatch) -> None:
    calls = 0
    pool = object()

    async def create_pool(*args, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return pool

    monkeypatch.setitem(
        sys.modules,
        "asyncpg",
        SimpleNamespace(create_pool=create_pool),
    )
    catalog = PostgresPlaceCatalog("postgresql://example")

    async def get_concurrently():
        return await asyncio.gather(*(catalog._get_pool() for _ in range(20)))

    results = asyncio.run(get_concurrently())

    assert calls == 1
    assert results == [pool] * 20
