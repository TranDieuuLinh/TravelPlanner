from sqlalchemy.orm import Session

from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.place_search import KnowledgeGraphPlaceSearchRepository
from app.modules.knowledge_graph.place_repository import KnowledgeGraphPlaceRepository
from app.modules.knowledge_graph.text import normalize_knowledge_text


def _entity(
    entity_id: str,
    name: str,
    entity_type: str,
    *,
    status: str = "verified",
) -> KnowledgeEntity:
    return KnowledgeEntity(
        id=entity_id,
        canonical_name=name,
        normalized_name=normalize_knowledge_text(name),
        entity_type=entity_type,
        status=status,
    )


def _property(entity_id: str, key: str, value: str) -> KnowledgeProperty:
    return KnowledgeProperty(
        entity_id=entity_id,
        key=key,
        value=value,
        source="admin-reviewed:test",
    )


def test_search_returns_only_located_venue_entities_with_coordinates(
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            _entity("area-hanoi", "Hà Nội", "AreaAdm1"),
            _entity("area-hoan-kiem", "Hoàn Kiếm", "AreaAdm2"),
            _entity("area-danang", "Đà Nẵng", "AreaAdm1"),
            _entity("place-giang", "Giảng Cafe", "DrinkDessert"),
            _entity("place-no-coordinates", "Cafe Thiếu Tọa Độ", "Restaurant"),
            _entity("activity-coffee", "Cafe Workshop", "Activity"),
            _entity("place-danang", "Cafe Giảng Đà Nẵng", "DrinkDessert"),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            KnowledgeAlias(
                entity_id="place-giang",
                alias="Cà phê Giảng",
                normalized_alias="ca phe giang",
                status="reviewed",
            ),
            KnowledgeRelationship(
                from_entity_id="area-hoan-kiem",
                relationship_type="PART_OF",
                to_entity_id="area-hanoi",
            ),
            KnowledgeRelationship(
                from_entity_id="place-giang",
                relationship_type="LOCATED_IN",
                to_entity_id="area-hoan-kiem",
            ),
            KnowledgeRelationship(
                from_entity_id="place-no-coordinates",
                relationship_type="LOCATED_IN",
                to_entity_id="area-hanoi",
            ),
            KnowledgeRelationship(
                from_entity_id="activity-coffee",
                relationship_type="LOCATED_IN",
                to_entity_id="area-hanoi",
            ),
            KnowledgeRelationship(
                from_entity_id="place-danang",
                relationship_type="LOCATED_IN",
                to_entity_id="area-danang",
            ),
            _property("place-giang", "latitude", "21.0358"),
            _property("place-giang", "longitude", "105.8521"),
            _property("place-giang", "address", "39 Nguyễn Hữu Huân"),
            _property("place-giang", "rating", "4.5"),
            _property("place-giang", "review_count", "1234"),
            _property("place-no-coordinates", "address", "Hà Nội"),
            _property("activity-coffee", "latitude", "21.03"),
            _property("activity-coffee", "longitude", "105.85"),
            _property("place-danang", "latitude", "16.06"),
            _property("place-danang", "longitude", "108.22"),
        ]
    )
    db_session.commit()

    results = KnowledgeGraphPlaceSearchRepository(db_session).search(
        "ca phe",
        "Hà Nội",
        limit=5,
    )

    assert [result.entity_id for result in results] == ["place-giang"]
    assert results[0].address == "39 Nguyễn Hữu Huân"
    assert results[0].latitude == 21.0358
    assert results[0].rating == 4.5
    assert results[0].review_count == 1234

    # A middle-of-word substring is too weak to establish graph identity; the
    # service will use Google Maps fallback for this query instead.
    assert KnowledgeGraphPlaceSearchRepository(db_session).search(
        "iang",
        "Hà Nội",
        limit=5,
    ) == []


def test_search_returns_no_graph_result_when_destination_is_unknown(
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            _entity("area-hanoi", "Hà Nội", "AreaAdm1"),
            _entity("place-cafe", "Cafe Hà Nội", "DrinkDessert"),
        ]
    )
    db_session.flush()
    db_session.add_all(
        [
            KnowledgeRelationship(
                from_entity_id="place-cafe",
                relationship_type="LOCATED_IN",
                to_entity_id="area-hanoi",
            ),
            _property("place-cafe", "latitude", "21.03"),
            _property("place-cafe", "longitude", "105.85"),
        ]
    )
    db_session.commit()

    results = KnowledgeGraphPlaceSearchRepository(db_session).search(
        "Cafe",
        "Huế",
        limit=5,
    )

    assert results == []


def test_planner_repository_redirects_soft_merged_place_to_canonical(
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            _entity("place-canonical", "Temple of Literature", "TravelPlace"),
            _entity("place-merged", "Temple of Literature", "TravelPlace"),
            _property("place-canonical", "catalog_status", "active"),
            _property("place-canonical", "region_key", "vn,ha-noi"),
            _property("place-canonical", "latitude", "21.028"),
            _property("place-canonical", "longitude", "105.835"),
            _property("place-merged", "catalog_status", "merged"),
            _property(
                "place-merged", "merged_into_entity_id", "place-canonical"
            ),
            _property("place-merged", "region_key", "vn,ha-noi"),
            _property("place-merged", "latitude", "21.028"),
            _property("place-merged", "longitude", "105.835"),
        ]
    )
    db_session.commit()

    repository = KnowledgeGraphPlaceRepository(db_session)

    assert repository.get("place-merged").id == "place-canonical"
    assert [
        place.id
        for place in repository.list_for_place_selection("vn,ha-noi")
    ] == ["place-canonical"]


def test_planner_repository_prioritizes_travel_places_before_food_when_bounded(
    db_session: Session,
) -> None:
    db_session.add_all(
        [
            _entity("drink_dessert_001", "Cafe đầu danh sách", "DrinkDessert"),
            _entity("travel_place_001", "Bảo tàng Hà Nội", "TravelPlace"),
            _property("drink_dessert_001", "catalog_status", "active"),
            _property("drink_dessert_001", "region_key", "vn,ha-noi"),
            _property("drink_dessert_001", "latitude", "21.030"),
            _property("drink_dessert_001", "longitude", "105.850"),
            _property("travel_place_001", "catalog_status", "active"),
            _property("travel_place_001", "region_key", "vn,ha-noi"),
            _property("travel_place_001", "latitude", "21.031"),
            _property("travel_place_001", "longitude", "105.851"),
        ]
    )
    db_session.commit()

    results = KnowledgeGraphPlaceRepository(db_session).list_for_place_selection(
        "vn,ha-noi", limit=1
    )

    assert [place.id for place in results] == ["travel_place_001"]


def test_search_repairs_legacy_cp437_utf8_text_at_projection_boundary(
    db_session: Session,
) -> None:
    place = _entity(
        "place-food-culture",
        "Nh├á h├áng H├á Nß╗Öi",
        "Restaurant",
    )
    # The legacy row has a valid normalized index but corrupted display text.
    place.normalized_name = "nha hang ha noi"
    db_session.add_all([_entity("area-hanoi", "Hà Nội", "AreaAdm1"), place])
    db_session.flush()
    db_session.add_all(
        [
            KnowledgeRelationship(
                from_entity_id="place-food-culture",
                relationship_type="LOCATED_IN",
                to_entity_id="area-hanoi",
            ),
            _property("place-food-culture", "latitude", "21.0340925"),
            _property("place-food-culture", "longitude", "105.8538401"),
            _property(
                "place-food-culture",
                "address",
                "60 Ng. Phß╗æ H├áng, H├á Nß╗Öi",
            ),
        ]
    )
    db_session.commit()

    results = KnowledgeGraphPlaceSearchRepository(db_session).search(
        "nha hang",
        "Hà Nội",
        limit=5,
    )

    assert results[0].name == "Nhà hàng Hà Nội"
    assert results[0].address == "60 Ng. Phố Hàng, Hà Nội"
