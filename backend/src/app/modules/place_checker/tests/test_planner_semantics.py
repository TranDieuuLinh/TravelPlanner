from app.modules.place_checker.planning.semantics import (
    audience_values,
    candidate_semantics,
    split_trip_preferences,
)
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence


def test_candidate_semantics_ignores_has_style_as_planner_semantics() -> None:
    style = PlaceRelationshipEvidence(
        relationship_type="Has_Style",
        direction="place_to_attribute",
        scope="place",
        from_entity_id="place:1",
        to_entity_id="style:slow_travel",
        related_entity_id="style:slow_travel",
    )

    tags, styles = candidate_semantics(
        ["temple", "history", "style:slow_travel", "retrieval:relation"],
        [style],
    )

    assert tags == ["temple", "history"]
    assert styles == []


def test_trip_preferences_split_known_styles_from_flat_tags() -> None:
    tags, avoids, styles = split_trip_preferences(
        ["history", "slow travel", "style:local_life"],
        ["nightlife"],
    )

    assert tags == ["history"]
    assert avoids == ["nightlife"]
    assert styles == ["slow_travel", "local_life"]


def test_audience_combines_children_and_infants_into_kids() -> None:
    assert audience_values(adults=True, children=True, infants=False) == (
        False,
        True,
    )
    assert audience_values(adults=True, children=False, infants=False) == (
        True,
        False,
    )
    assert audience_values(adults=True, children=None, infants=None) == (
        None,
        None,
    )
