from __future__ import annotations

from datetime import datetime, timezone

from app.modules.knowledge_graph.model import KnowledgeEntity, KnowledgeProperty
from app.modules.knowledge_graph.price_research import TravelPlacePriceOutcome
from scripts.auto_crawl_tien_ve.enrich_travel_place_prices import (
    apply_outcomes,
    load_candidates,
)


def _entity() -> KnowledgeEntity:
    return KnowledgeEntity(
        id="travel_place_1",
        canonical_name="Văn Miếu - Quốc Tử Giám",
        normalized_name="van mieu quoc tu giam",
        entity_type="TravelPlace",
        status="draft",
    )


def _outcome() -> TravelPlacePriceOutcome:
    return TravelPlacePriceOutcome(
        entityId="travel_place_1",
        status="verified_price",
        fetchedAt=datetime.now(timezone.utc),
        model="test-model",
        currency="VND",
        minAmount=70_000,
        maxAmount=70_000,
        representativeAmount=70_000,
        pricingUnit="per_adult",
        sourceAuthority="official",
        confidence=0.95,
        sources=[
            {
                "title": "Official tickets",
                "uri": "https://official.example/tickets",
            }
        ],
    )


def test_load_candidates_prioritizes_review_count(db_session) -> None:
    entity = _entity()
    db_session.add(entity)
    db_session.flush()
    db_session.add_all(
        [
            KnowledgeProperty(entity_id=entity.id, key="address", value="Hà Nội"),
            KnowledgeProperty(entity_id=entity.id, key="review_count", value="1234"),
            KnowledgeProperty(entity_id=entity.id, key="place_type", value="Museum"),
        ]
    )
    db_session.flush()

    records = load_candidates(db_session, min_review_count=100)

    assert len(records) == 1
    assert records[0].candidate.review_count == 1234
    assert records[0].candidate.place_type == "Museum"


def test_apply_outcome_writes_single_full_price_property(db_session) -> None:
    db_session.add(_entity())
    db_session.flush()

    stats = apply_outcomes(
        db_session,
        [_outcome()],
        apply=True,
        overwrite=False,
    )

    properties = {
        prop.key: prop
        for prop in db_session.query(KnowledgeProperty).filter_by(
            entity_id="travel_place_1"
        )
    }
    assert stats["admission_price_upserted"] == 1
    assert set(properties) == {"admission_price"}
    assert properties["admission_price"].source == "https://official.example/tickets"
    assert "verified_price" in properties["admission_price"].value


def test_apply_does_not_overwrite_existing_price_without_flag(db_session) -> None:
    db_session.add(_entity())
    db_session.flush()
    db_session.add(
        KnowledgeProperty(
            entity_id="travel_place_1",
            key="admission_price",
            value='{"currency":"VND","representativeAmount":50000}',
            source="manual",
        )
    )
    db_session.flush()

    stats = apply_outcomes(
        db_session,
        [_outcome()],
        apply=True,
        overwrite=False,
    )

    prop = db_session.query(KnowledgeProperty).filter_by(
        entity_id="travel_place_1",
        key="admission_price",
    ).one()
    assert stats["existing_price_skipped"] == 1
    assert prop.value == '{"currency":"VND","representativeAmount":50000}'
    assert prop.source == "manual"
