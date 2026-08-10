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


def test_plannable_meal_nodes_require_a_restaurant_offer(db_session) -> None:
    db_session.add_all(
        [
            KnowledgeEntity(id="food-pho", canonical_name="Phở", normalized_name="pho", entity_type="FoodItem"),
            KnowledgeEntity(id="drink-tea", canonical_name="Trà", normalized_name="tra", entity_type="DrinkItem"),
            KnowledgeEntity(id="product-gift", canonical_name="Quà", normalized_name="qua", entity_type="ProductItem"),
            KnowledgeEntity(id="restaurant", canonical_name="Nhà hàng", normalized_name="nha hang", entity_type="Restaurant"),
            KnowledgeEntity(id="cafe", canonical_name="Quán trà", normalized_name="quan tra", entity_type="DrinkDessert"),
            KnowledgeRelationship(from_entity_id="restaurant", relationship_type="OFFERS_ITEM", to_entity_id="food-pho"),
            KnowledgeRelationship(from_entity_id="cafe", relationship_type="OFFERS_ITEM", to_entity_id="drink-tea"),
            KnowledgeRelationship(from_entity_id="restaurant", relationship_type="OFFERS_ITEM", to_entity_id="product-gift"),
        ]
    )
    db_session.commit()

    nodes = ScopeResolutionRepository(db_session).list_plannable_meal_item_nodes()

    assert [(node.id, node.entity_type) for node in nodes] == [
        ("food-pho", "FoodItem")
    ]


def test_activity_item_venue_candidates_include_restaurant_and_drink_dessert(
    db_session,
) -> None:
    db_session.add_all(
        [
            KnowledgeEntity(id="area-hanoi-item", canonical_name="Hà Nội Item", normalized_name="ha noi item", entity_type="Area"),
            KnowledgeEntity(id="area-hoan-kiem-item", canonical_name="Hoàn Kiếm Item", normalized_name="hoan kiem item", entity_type="Area"),
            KnowledgeEntity(id="area-other", canonical_name="Nơi khác", normalized_name="noi khac", entity_type="Area"),
            KnowledgeEntity(id="activity-coffee", canonical_name="Thưởng thức cà phê trứng", normalized_name="thuong thuc ca phe trung", entity_type="Activity"),
            KnowledgeEntity(id="item-coffee", canonical_name="Cà phê trứng", normalized_name="ca phe trung", entity_type="DrinkItem"),
            KnowledgeEntity(id="restaurant-coffee", canonical_name="Nhà hàng có cà phê trứng", normalized_name="nha hang co ca phe trung", entity_type="Restaurant"),
            KnowledgeEntity(id="cafe-giang", canonical_name="Cafe Giảng", normalized_name="cafe giang", entity_type="DrinkDessert"),
            KnowledgeEntity(id="travel-place", canonical_name="Điểm thường", normalized_name="diem thuong", entity_type="TravelPlace"),
            KnowledgeEntity(id="cafe-other", canonical_name="Cafe ngoài vùng", normalized_name="cafe ngoai vung", entity_type="DrinkDessert"),
            KnowledgeRelationship(from_entity_id="activity-coffee", relationship_type="INVOLVES_ITEM", to_entity_id="item-coffee"),
            KnowledgeRelationship(from_entity_id="area-hoan-kiem-item", relationship_type="PART_OF", to_entity_id="area-hanoi-item"),
            KnowledgeRelationship(from_entity_id="restaurant-coffee", relationship_type="OFFERS_ITEM", to_entity_id="item-coffee"),
            KnowledgeRelationship(from_entity_id="cafe-giang", relationship_type="OFFERS_ITEM", to_entity_id="item-coffee"),
            KnowledgeRelationship(from_entity_id="travel-place", relationship_type="OFFERS_ITEM", to_entity_id="item-coffee"),
            KnowledgeRelationship(from_entity_id="cafe-other", relationship_type="OFFERS_ITEM", to_entity_id="item-coffee"),
            KnowledgeRelationship(from_entity_id="restaurant-coffee", relationship_type="LOCATED_IN", to_entity_id="area-hanoi-item"),
            KnowledgeRelationship(from_entity_id="cafe-giang", relationship_type="LOCATED_IN", to_entity_id="area-hoan-kiem-item"),
            KnowledgeRelationship(from_entity_id="travel-place", relationship_type="LOCATED_IN", to_entity_id="area-hanoi-item"),
            KnowledgeRelationship(from_entity_id="cafe-other", relationship_type="LOCATED_IN", to_entity_id="area-other"),
        ]
    )
    db_session.commit()

    rows = ScopeResolutionRepository(db_session).list_activity_item_venue_candidates(
        "vn,ha-noi-item",
        "activity-coffee",
    )

    assert {(row.placeId, row.placeType, row.itemId) for row in rows} == {
        ("restaurant-coffee", "Restaurant", "item-coffee"),
        ("cafe-giang", "DrinkDessert", "item-coffee"),
    }


def test_activity_place_candidates_use_offers_activity_not_special_only(db_session) -> None:
    db_session.add_all(
        [
            KnowledgeEntity(id="area-hanoi-activity", canonical_name="Hà Nội Activity", normalized_name="ha noi activity", entity_type="Area"),
            KnowledgeEntity(id="activity-karaoke", canonical_name="Hát karaoke", normalized_name="hat karaoke", entity_type="Activity"),
            KnowledgeEntity(id="activity-meal", canonical_name="Dùng bữa", normalized_name="dung bua", entity_type="Activity"),
            KnowledgeEntity(id="karaoke-place", canonical_name="Music Box", normalized_name="music box", entity_type="TravelPlace"),
            KnowledgeEntity(id="restaurant-place", canonical_name="Nhà hàng", normalized_name="nha hang", entity_type="Restaurant"),
            KnowledgeRelationship(from_entity_id="karaoke-place", relationship_type="LOCATED_IN", to_entity_id="area-hanoi-activity"),
            KnowledgeRelationship(from_entity_id="restaurant-place", relationship_type="LOCATED_IN", to_entity_id="area-hanoi-activity"),
            KnowledgeRelationship(from_entity_id="karaoke-place", relationship_type="OFFERS_ACTIVITY", to_entity_id="activity-karaoke"),
            KnowledgeRelationship(from_entity_id="restaurant-place", relationship_type="OFFERS_ACTIVITY", to_entity_id="activity-meal"),
        ]
    )
    db_session.commit()

    rows = ScopeResolutionRepository(db_session).list_activity_place_candidates(
        "Hà Nội Activity",
        activity_terms=["karaoke"],
    )

    assert [(row.placeId, row.activityId) for row in rows] == [
        ("karaoke-place", "activity-karaoke")
    ]
