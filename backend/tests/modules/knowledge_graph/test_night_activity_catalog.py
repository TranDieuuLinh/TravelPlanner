from sqlalchemy import select

from app.modules.knowledge_graph.model import KnowledgeEntity, KnowledgeRelationship
from app.modules.knowledge_graph.tagging.catalog import (
    BROAD_SPECIAL_ACTIVITY_IDS,
    HANOI_ID,
    LEGACY_INFERENCE_SOURCE,
    MANUAL_OFFERS,
    NIGHT_ACTIVITIES,
    OFFER_SOURCE,
    NightActivityCatalogService,
)


def _entity(entity_id: str, entity_type: str = "Activity") -> KnowledgeEntity:
    return KnowledgeEntity(
        id=entity_id,
        canonical_name=entity_id,
        normalized_name=entity_id,
        entity_type=entity_type,
        status="verified",
    )


def test_catalog_creates_only_offers_and_removes_broad_specials(db_session) -> None:
    db_session.add(_entity(HANOI_ID, "AreaAdm1"))
    manual_place_ids = {
        place_id for place_ids in MANUAL_OFFERS.values() for place_id in place_ids
    }
    db_session.add_all(_entity(place_id, "TravelPlace") for place_id in manual_place_ids)
    db_session.add_all(_entity(activity_id) for activity_id in BROAD_SPECIAL_ACTIVITY_IDS)
    db_session.flush()
    db_session.add_all(
        KnowledgeRelationship(
            from_entity_id=HANOI_ID,
            relationship_type="SPECIAL_EXPERIENCE",
            to_entity_id=activity_id,
            source="legacy",
        )
        for activity_id in BROAD_SPECIAL_ACTIVITY_IDS
    )
    nightlife_place_id = MANUAL_OFFERS["activity_nightlife_drink"][0]
    db_session.add(
        KnowledgeRelationship(
            from_entity_id=nightlife_place_id,
            relationship_type="OFFERS_ACTIVITY",
            to_entity_id="activity_nightlife_drink",
            source=LEGACY_INFERENCE_SOURCE,
        )
    )
    unrelated_activity = _entity("activity_unrelated")
    unrelated_place = _entity("place_unrelated", "TravelPlace")
    db_session.add_all([unrelated_activity, unrelated_place])
    db_session.flush()
    db_session.add(
        KnowledgeRelationship(
            from_entity_id=unrelated_place.id,
            relationship_type="OFFERS_ACTIVITY",
            to_entity_id=unrelated_activity.id,
            source=LEGACY_INFERENCE_SOURCE,
        )
    )
    db_session.commit()

    result = NightActivityCatalogService(db_session).reconcile()
    db_session.commit()

    assert result["specialExperienceEdgesCreated"] == 0
    assert not list(
        db_session.scalars(
            select(KnowledgeRelationship).where(
                KnowledgeRelationship.from_entity_id == HANOI_ID,
                KnowledgeRelationship.relationship_type == "SPECIAL_EXPERIENCE",
                KnowledgeRelationship.to_entity_id.in_(BROAD_SPECIAL_ACTIVITY_IDS),
            )
        )
    )
    night_ids = {definition.activity_id for definition in NIGHT_ACTIVITIES}
    offers = list(
        db_session.scalars(
            select(KnowledgeRelationship).where(
                KnowledgeRelationship.relationship_type == "OFFERS_ACTIVITY",
                KnowledgeRelationship.to_entity_id.in_(night_ids),
            )
        )
    )
    assert offers
    assert all(edge.from_entity_id in manual_place_ids for edge in offers)
    reconciled_nightlife = db_session.scalar(
        select(KnowledgeRelationship).where(
            KnowledgeRelationship.from_entity_id == nightlife_place_id,
            KnowledgeRelationship.to_entity_id == "activity_nightlife_drink",
        )
    )
    assert reconciled_nightlife is not None
    assert reconciled_nightlife.source == OFFER_SOURCE
    assert db_session.scalar(
        select(KnowledgeRelationship).where(
            KnowledgeRelationship.from_entity_id == unrelated_place.id,
            KnowledgeRelationship.to_entity_id == unrelated_activity.id,
        )
    ) is not None
