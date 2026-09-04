from app.modules.place_checker.adapters.postgres_catalog_mapping import (
    PLACE_TYPES,
    PostgresCatalogMappingMixin,
    TYPE_BY_HINT,
)
from app.modules.place_checker.adapters.postgres_food_query import (
    SPECIAL_FOOD_RESTAURANT_SQL,
)
from app.modules.place_checker.adapters.postgres_named_place_query import (
    NAMED_PLACE_SEARCH_SQL,
)
from app.modules.place_checker.adapters.postgres_search_query import PLACE_SEARCH_SQL


def test_generic_catalog_pool_uses_adm_candidates() -> None:
    assert "generic_travel_ranked" in PLACE_SEARCH_SQL
    assert (
        "$1 IN ('travel place', 'restaurant', 'cafe', 'entertainment', 'hotel')"
        in PLACE_SEARCH_SQL
    )
    assert "style_property.key = 'time_duration'" in PLACE_SEARCH_SQL
    assert "activity.entity_type = 'ActivityItem'" in PLACE_SEARCH_SQL
    assert "'entityType', target.entity_type" in PLACE_SEARCH_SQL
    assert "percentile_cont(0.5)" in PLACE_SEARCH_SQL
    assert "bayesian_quality DESC NULLS LAST" in PLACE_SEARCH_SQL
    assert "generic_rank.bayesian_rating DESC NULLS LAST" in PLACE_SEARCH_SQL
    assert "NULLIF(props.rating, '')::double precision DESC" not in PLACE_SEARCH_SQL


def test_generic_catalog_exclusion_does_not_hide_named_places() -> None:
    assert "discovery_policy.key = 'generic_discovery_excluded'" in PLACE_SEARCH_SQL
    assert "lower(btrim(discovery_policy.value)) = 'true'" in PLACE_SEARCH_SQL
    assert "generic_discovery_excluded" not in NAMED_PLACE_SEARCH_SQL


def test_entertainment_type_has_a_dedicated_hint() -> None:
    assert TYPE_BY_HINT["entertainment"] == {"Entertainment"}
    assert "Entertainment" not in TYPE_BY_HINT["travel place"]


def test_named_search_is_unified_identity_only() -> None:
    assert PLACE_TYPES == {
        "TravelPlace",
        "Restaurant",
        "DrinkDessert",
        "Entertainment",
        "Accommodation",
    }
    assert PostgresCatalogMappingMixin._types_for_hint(None) == PLACE_TYPES
    assert "entity.entity_type = ANY($3::text[])" in NAMED_PLACE_SEARCH_SQL
    assert "entity.normalized_name % $1" in NAMED_PLACE_SEARCH_SQL
    assert "alias.normalized_alias % $1" in NAMED_PLACE_SEARCH_SQL
    assert "lower(address.value) % lower($6)" in NAMED_PLACE_SEARCH_SQL
    assert ") >= $5" in NAMED_PLACE_SEARCH_SQL
    assert "$7" not in NAMED_PLACE_SEARCH_SQL
    assert "LIMIT $4" in NAMED_PLACE_SEARCH_SQL
    for relation in ("Special_Experience", "Special_Near", "Offer_Item", "Has_Style"):
        assert relation not in NAMED_PLACE_SEARCH_SQL


def test_requirement_search_keeps_relationship_evidence_but_not_style_semantics() -> (
    None
):
    assert "WITH RECURSIVE adm_descendants" in PLACE_SEARCH_SQL
    assert "relationship_type = 'Special_Near'" in PLACE_SEARCH_SQL
    assert "relationship_evidence" in PLACE_SEARCH_SQL
    assert (
        "relation.relationship_type IN ('Offer_Item', 'Has_Style')" in PLACE_SEARCH_SQL
    )


def test_food_query_uses_item_ids_without_has_style_or_name_matching() -> None:
    assert "special.from_entity_id = $1" in SPECIAL_FOOD_RESTAURANT_SQL
    assert (
        "special.relationship_type = 'Special_Experience'"
        in SPECIAL_FOOD_RESTAURANT_SQL
    )
    assert "offer.relationship_type = 'Offer_Item'" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "restaurant.entity_type = 'Restaurant'" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "Has_Style" not in SPECIAL_FOOD_RESTAURANT_SQL
    assert "normalized_name" not in SPECIAL_FOOD_RESTAURANT_SQL
    assert "'offer_item'::text" in SPECIAL_FOOD_RESTAURANT_SQL


def test_food_query_returns_nearby_and_general_candidates_in_one_pass() -> None:
    assert "pair.distance_km <= $3" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "nearby.distance_km <= 5.0" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "ELSE 'general_adm'" in SPECIAL_FOOD_RESTAURANT_SQL
    assert "PARTITION BY nearby.anchor_place_id" in SPECIAL_FOOD_RESTAURANT_SQL
