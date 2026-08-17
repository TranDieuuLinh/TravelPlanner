from app.modules.place_checker.planner_candidate_metadata import (
    preferred_time_values,
    source_metadata,
)
from app.modules.place_checker.relationship_contract import PlaceRelationshipEvidence


def relationship(kind: str, target: str, **properties):
    return PlaceRelationshipEvidence(
        relationship_type=kind,
        direction="area_to_place" if kind == "Special_Experience" else "place_to_attribute",
        scope="destination" if kind == "Special_Experience" else "place",
        from_entity_id="adm:hanoi" if kind == "Special_Experience" else "place:1",
        to_entity_id=target,
        related_entity_id=target,
        properties=properties,
    )


def test_activity_offer_is_explicit_and_not_double_counted_with_special() -> None:
    relations = [
        relationship("Special_Experience", "place:1"),
        relationship(
            "Offer_Item",
            "activity:walk",
            entityType="ActivityItem",
            time_windows=[{"start": "08:00", "end": "11:00"}],
        ),
    ]

    kind, activity_ids = source_metadata(relations)

    assert kind == "both"
    assert activity_ids == ["activity:walk"]


def test_pending_special_relationship_is_not_promoted_to_special_source() -> None:
    pending = relationship("Special_Experience", "place:1").model_copy(
        update={"status": "pending"}
    )

    kind, activity_ids = source_metadata([pending])

    assert kind == "generic"
    assert activity_ids == []


def test_activity_timing_precedes_style_and_style_is_fallback() -> None:
    activity = relationship(
        "Offer_Item",
        "activity:walk",
        entityType="ActivityItem",
        time_windows='[{"start":"08:00","end":"11:00"}]',
    )
    style = relationship(
        "Has_Style",
        "style:culture",
        time_windows=[{"start": "18:00", "end": "22:00"}],
    )

    values, source = preferred_time_values(
        direct_values=[], relationships=[activity, style]
    )
    fallback_values, fallback_source = preferred_time_values(
        direct_values=[], relationships=[style]
    )

    assert values == ["08:00-11:00"]
    assert source == "activity_item"
    assert fallback_values == ["18:00-22:00"]
    assert fallback_source == "has_style"
