from sqlalchemy import select

from app.modules.knowledge_graph.model import (
    KnowledgeEntity,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.tagging.catalog import HANOI_ID
from app.modules.knowledge_graph.tagging.specialty_food_catalog import (
    CATALOG_SOURCE,
    HanoiSpecialtyFoodCatalogService,
)


def _entity(
    entity_id: str,
    name: str,
    entity_type: str,
) -> KnowledgeEntity:
    return KnowledgeEntity(
        id=entity_id,
        canonical_name=name,
        normalized_name=name.casefold(),
        entity_type=entity_type,
        status="verified",
    )


def test_catalog_replaces_restaurant_specific_specials_with_item_types(
    db_session,
) -> None:
    area = _entity(HANOI_ID, "Hà Nội", "AreaAdm1")
    pho = _entity("restaurant-pho", "pho bo gia truyen", "Restaurant")
    cafe = _entity("drink-cafe-giang", "cafe giang", "DrinkDessert")
    old_pho = _entity(
        "activity_special_42a56958cb805b12",
        "an pho tai bat dan",
        "Activity",
    )
    old_coffee = _entity(
        "activity_special_74f7c6dcfee57c59",
        "uong ca phe trung tai cafe giang",
        "Activity",
    )
    db_session.add_all([area, pho, cafe, old_pho, old_coffee])
    db_session.flush()
    db_session.add_all(
        [
            KnowledgeRelationship(
                from_entity_id=HANOI_ID,
                relationship_type="SPECIAL_EXPERIENCE",
                to_entity_id=old_pho.id,
                source="legacy",
            ),
            KnowledgeRelationship(
                from_entity_id=old_pho.id,
                relationship_type="TARGETS_PLACE",
                to_entity_id=pho.id,
                source="legacy",
            ),
            KnowledgeRelationship(
                from_entity_id=HANOI_ID,
                relationship_type="SPECIAL_EXPERIENCE",
                to_entity_id=old_coffee.id,
                source="legacy",
            ),
            KnowledgeRelationship(
                from_entity_id=old_coffee.id,
                relationship_type="TARGETS_PLACE",
                to_entity_id=cafe.id,
                source="legacy",
            ),
        ]
    )
    db_session.commit()

    summary = HanoiSpecialtyFoodCatalogService(db_session).reconcile()
    db_session.commit()

    assert summary["supportedCount"] == 2
    assert db_session.get(KnowledgeEntity, old_pho.id) is None
    assert db_session.get(KnowledgeEntity, old_coffee.id) is None
    assert db_session.get(KnowledgeEntity, pho.id) is not None
    assert db_session.get(KnowledgeEntity, cafe.id) is not None

    expected = {
        (HANOI_ID, "SPECIAL_EXPERIENCE", "activity_hanoi_pho_bo"),
        (
            "activity_hanoi_pho_bo",
            "INVOLVES_ITEM",
            "food_item_hanoi_pho_bo",
        ),
        ("restaurant-pho", "OFFERS_ITEM", "food_item_hanoi_pho_bo"),
        (HANOI_ID, "SPECIAL_EXPERIENCE", "activity_hanoi_ca_phe_trung"),
        (
            "activity_hanoi_ca_phe_trung",
            "INVOLVES_ITEM",
            "drink_item_hanoi_ca_phe_trung",
        ),
        (
            "drink-cafe-giang",
            "OFFERS_ITEM",
            "drink_item_hanoi_ca_phe_trung",
        ),
    }
    actual = {
        (edge.from_entity_id, edge.relationship_type, edge.to_entity_id)
        for edge in db_session.scalars(
            select(KnowledgeRelationship).where(
                KnowledgeRelationship.source == CATALOG_SOURCE
            )
        )
    }
    assert expected <= actual
    assert not any(relationship == "OFFERS_ACTIVITY" for _, relationship, _ in actual)


def test_catalog_is_idempotent(db_session) -> None:
    db_session.add_all(
        [
            _entity(HANOI_ID, "Hà Nội", "AreaAdm1"),
            _entity("restaurant-bun-cha", "bun cha ha noi", "Restaurant"),
        ]
    )
    db_session.commit()

    first = HanoiSpecialtyFoodCatalogService(db_session).reconcile()
    db_session.commit()
    second = HanoiSpecialtyFoodCatalogService(db_session).reconcile()
    db_session.commit()

    assert first["supportedCount"] == 1
    assert second["supportedCount"] == 1
    assert second["changeCount"] == 0
