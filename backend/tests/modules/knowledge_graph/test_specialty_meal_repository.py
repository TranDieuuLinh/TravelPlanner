from app.modules.knowledge_graph.model import (
    KnowledgeEntity,
    KnowledgeProperty,
    KnowledgeRelationship,
)
from app.modules.knowledge_graph.research.repository import ScopeResolutionRepository


def test_specialty_meals_prefer_targets_then_expand_offers_item(db_session) -> None:
    entities = [
        KnowledgeEntity(id="area-hanoi", canonical_name="Hà Nội", normalized_name="ha noi", entity_type="Area"),
        KnowledgeEntity(id="activity-bun-cha", canonical_name="Ăn bún chả", normalized_name="an bun cha", entity_type="Activity"),
        KnowledgeEntity(id="activity-pho", canonical_name="Ăn phở", normalized_name="an pho", entity_type="Activity"),
        KnowledgeEntity(id="bun-cha", canonical_name="Bún chả Hương Liên", normalized_name="bun cha huong lien", entity_type="Restaurant"),
        KnowledgeEntity(id="pho-place", canonical_name="Phở Bát Đàn", normalized_name="pho bat dan", entity_type="Restaurant"),
        KnowledgeEntity(id="pho-item", canonical_name="Phở", normalized_name="pho", entity_type="FoodItem"),
    ]
    db_session.add_all(entities)
    db_session.flush()
    db_session.add_all([
        KnowledgeProperty(entity_id="activity-bun-cha", key="activity_category", value="dining"),
        KnowledgeProperty(entity_id="activity-bun-cha", key="best_time_slots", value='[{"start":"11:00","end":"14:00"}]'),
        KnowledgeProperty(entity_id="activity-pho", key="activity_category", value="dining"),
        KnowledgeRelationship(from_entity_id="area-hanoi", relationship_type="SPECIAL_EXPERIENCE", to_entity_id="activity-bun-cha"),
        KnowledgeRelationship(from_entity_id="area-hanoi", relationship_type="SPECIAL_EXPERIENCE", to_entity_id="activity-pho"),
        KnowledgeRelationship(from_entity_id="activity-bun-cha", relationship_type="TARGETS_PLACE", to_entity_id="bun-cha"),
        KnowledgeRelationship(from_entity_id="activity-pho", relationship_type="INVOLVES_ITEM", to_entity_id="pho-item"),
        KnowledgeRelationship(from_entity_id="pho-place", relationship_type="OFFERS_ITEM", to_entity_id="pho-item"),
        KnowledgeRelationship(from_entity_id="pho-place", relationship_type="LOCATED_IN", to_entity_id="area-hanoi"),
    ])
    db_session.commit()

    rows = ScopeResolutionRepository(db_session).list_specialty_meal_candidates(
        "vn,ha-noi"
    )

    assert [(row.placeId, row.selectionPath) for row in rows] == [
        ("bun-cha", "target_place"),
        ("pho-place", "offers_item"),
    ]
    assert rows[0].bestTimeSlots == ["11:00-14:00"]
    assert rows[1].itemName == "Phở"
