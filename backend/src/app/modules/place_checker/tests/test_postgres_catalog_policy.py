import asyncio
import sys
from types import SimpleNamespace

import asyncpg

from app.modules.place_checker.adapters.postgres_catalog import PostgresPlaceCatalog
from app.modules.place_checker.adapters.postgres_catalog_mapping import (
    PostgresCatalogMappingMixin,
)
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence
from app.shared.tools.search_places import AdministrativeArea


def test_named_search_passes_contiguous_postgres_parameters(monkeypatch) -> None:
    catalog = PostgresPlaceCatalog("postgresql://example")
    captured = {}

    async def fetch(sql, *arguments):
        captured["sql"] = sql
        captured["arguments"] = arguments
        return []

    monkeypatch.setattr(catalog, "_fetch", fetch)
    asyncio.run(
        catalog.search(
            ["Văn Miếu"],
            input_adm=AdministrativeArea(
                admId="adm:hanoi",
                name="Hà Nội",
                countryCode="VN",
            ),
            place_type_hint=None,
            limit=1,
            search_mode="named_place",
            address_hint=None,
        )
    )

    assert len(captured["arguments"]) == 6
    assert captured["arguments"][0] == "van mieu"
    assert captured["arguments"][1] == "adm:hanoi"
    assert captured["arguments"][3:] == (1, 0.30, None)


def test_get_many_skips_invalid_relationship_evidence(monkeypatch) -> None:
    catalog = PostgresPlaceCatalog("postgresql://example")
    responses = iter(
        [
            [{"id": "restaurant:1", "entity_type": "Restaurant"}],
            [],
            [
                {
                    "entity_id": "restaurant:1",
                    "relationship_type": "Has_Style",
                    "direction": "place_to_attribute",
                    "scope": "place",
                    "from_entity_id": "restaurant:1",
                    "to_entity_id": "style:invalid",
                    "related_entity_id": "style:invalid",
                    "related_name": "Invalid style",
                    "related_entity_type": "Style",
                    "recommendations": "{}",
                    "source": "x" * 2001,
                    "source_note": None,
                }
            ],
            [],
        ]
    )

    async def fetch(sql, *arguments):
        return next(responses)

    monkeypatch.setattr(catalog, "_fetch", fetch)

    metadata = asyncio.run(catalog.get_many(["restaurant:1"]))

    assert metadata["restaurant:1"].relationships == []


def test_catalog_recycles_dropped_connection_before_retrying_read(monkeypatch) -> None:
    class FlakyPool:
        def __init__(self, rows, *, fail_first: bool = False) -> None:
            self.rows = rows
            self.fail_first = fail_first
            self.calls = 0
            self.terminated = False

        async def fetch(self, sql, *arguments):
            self.calls += 1
            if self.fail_first and self.calls == 1:
                raise asyncpg.ConnectionDoesNotExistError("connection dropped")
            return self.rows

        def terminate(self):
            self.terminated = True

    stale = FlakyPool([], fail_first=True)
    healthy = FlakyPool([{"id": "place-1"}])
    catalog = PostgresPlaceCatalog("postgresql://example")
    catalog._pool = stale

    async def get_pool():
        if catalog._pool is None:
            catalog._pool = healthy
        return catalog._pool

    monkeypatch.setattr(catalog, "_get_pool", get_pool)

    rows = asyncio.run(catalog._fetch("SELECT 1"))

    assert rows == [{"id": "place-1"}]
    assert stale.calls == 1
    assert stale.terminated is True
    assert healthy.calls == 1


def test_style_fills_only_missing_duration_and_time_window() -> None:
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


def test_metadata_does_not_need_has_style_tags_for_semantics() -> None:
    metadata = PostgresCatalogMappingMixin._metadata(
        "place:tagged",
        "TravelPlace",
        {"tags": '["Tâm linh", "kiến trúc", "Văn hóa"]'},
        [],
        None,
    )

    assert metadata.tags == [
        "travel place",
        "Tâm linh",
        "kiến trúc",
        "Văn hóa",
    ]


def test_metadata_reads_image_urls_from_knowledge_properties() -> None:
    metadata = PostgresCatalogMappingMixin._metadata(
        "place:photo",
        "TravelPlace",
        {
            "image": "https://example.test/primary.jpg",
            "images": '["https://example.test/secondary.jpg", {"url": "https://example.test/third.jpg"}]',
        },
        [],
        None,
    )

    assert metadata.image_urls == [
        "https://example.test/secondary.jpg",
        "https://example.test/third.jpg",
        "https://example.test/primary.jpg",
    ]


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
    assert relationship.properties["time_windows"] == (
        '[{"start":"11:00","end":"13:00"}]'
    )


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
        target_properties={"time_windows": '[{"start":"08:00","end":"11:00"}]'},
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


def test_highest_priority_style_supplies_missing_time_fields() -> None:
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

    assert metadata.typical_duration_minutes == 45
    assert metadata.opening_hours == ["06:00-10:00"]


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


def test_google_description_and_map_url_become_provider_note() -> None:
    metadata = PostgresCatalogMappingMixin._metadata(
        "place:1",
        "TravelPlace",
        {
            "description": "Không gian ngắm hoàng hôn.",
            "url_google_map": "https://google.com/maps/place/example",
        },
        [],
        None,
    )

    assert metadata.source_note is not None
    assert metadata.source_note.text == "Không gian ngắm hoàng hôn."
    assert metadata.source_note.source_type == "google_maps"
    assert metadata.source_note.source_url == "https://google.com/maps/place/example"


def test_concurrent_catalog_calls_create_only_one_pool(monkeypatch) -> None:
    calls = 0
    options = {}
    pool = object()

    async def create_pool(*args, **kwargs):
        nonlocal calls, options
        calls += 1
        options = kwargs
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
    assert options["min_size"] == 0
    assert options["max_size"] == 1
    assert results == [pool] * 20
