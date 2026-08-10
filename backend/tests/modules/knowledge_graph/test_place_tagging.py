import json

from sqlalchemy import func, select

from app.modules.knowledge_graph.model import KnowledgeEntity, KnowledgeProperty
from app.modules.knowledge_graph.tag_model import (
    KnowledgeEntityTagAssertion,
    KnowledgeTag,
    KnowledgeTagScanResult,
)
from app.modules.knowledge_graph.tagging.classifier import classify_place
from app.modules.knowledge_graph.tagging.service import PlaceTaggingService


def test_classifier_uses_structured_categories_and_hours() -> None:
    tags = {
        item.tag: item
        for item in classify_place(
            name="Moon Rooftop",
            properties={
                "source_category": "Cocktail bar",
                "metadata": json.dumps({"google": {"category": "Rooftop bar"}}),
                "opening_hours": json.dumps(
                    [{"days": ["friday"], "start": "18:00", "end": "23:30"}]
                ),
            },
            property_sources={
                "source_category": "https://provider.example/place",
                "metadata": "https://provider.example/place",
                "opening_hours": "https://provider.example/place",
            },
        )
    }

    assert tags["cocktail"].status == "source_backed"
    assert tags["alcohol"].status == "source_backed"
    assert tags["rooftop"].status == "source_backed"
    assert tags["night_view"].status == "inferred"
    assert tags["late_night"].status == "source_backed"


def test_classifier_does_not_invent_sensitive_tags() -> None:
    tags = {
        item.tag
        for item in classify_place(
            name="Ordinary Coffee Shop",
            properties={"source_category": "Coffee shop"},
            property_sources={"source_category": "https://provider.example/place"},
        )
    }
    assert "coffee" in tags
    assert "adult_only" not in tags
    assert "family_friendly" not in tags
    assert "live_music" not in tags


def test_classifier_reads_provider_raw_opening_hours_for_late_night() -> None:
    tags = {
        item.tag
        for item in classify_place(
            name="Late venue",
            properties={
                "opening_hours": json.dumps(
                    [
                        {
                            "dayName": "Friday",
                            "rawTimeSlots": "8:30\u202fAM–11:30\u202fPM",
                            "is24Hours": False,
                        }
                    ]
                )
            },
            property_sources={"opening_hours": "https://provider.example/place"},
        )
    }
    assert "late_night" in tags


def test_service_records_every_scanned_place_and_is_assertion_idempotent(db_session) -> None:
    for key in ("coffee", "late_night"):
        db_session.add(
            KnowledgeTag(
                key=key,
                tag_group="test",
                display_name_vi=key,
                display_name_en=key,
                applicable_entity_types=["DrinkDessert"],
                risk_level="low",
            )
        )
    place = KnowledgeEntity(
        id="drink_test",
        canonical_name="Test Coffee",
        normalized_name="test coffee",
        entity_type="DrinkDessert",
        status="draft",
    )
    untagged = KnowledgeEntity(
        id="place_untagged",
        canonical_name="Untyped Point",
        normalized_name="untyped point",
        entity_type="TravelPlace",
        status="draft",
    )
    db_session.add_all([place, untagged])
    db_session.flush()
    db_session.add(
        KnowledgeProperty(
            entity_id=place.id,
            key="source_category",
            value="Coffee shop",
            source="https://provider.example/place",
        )
    )
    db_session.commit()

    first = PlaceTaggingService(db_session).run(apply=True, run_id="tagrun_test_1")
    db_session.commit()
    second = PlaceTaggingService(db_session).run(apply=True, run_id="tagrun_test_2")
    db_session.commit()

    assert first["processedCount"] == 2
    assert second["processedCount"] == 2
    assert db_session.scalar(select(func.count(KnowledgeTagScanResult.id))) == 4
    assert db_session.scalar(select(func.count(KnowledgeEntityTagAssertion.id))) == 1
