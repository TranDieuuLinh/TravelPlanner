from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

CRAWL_PRICE_DIR = (
    Path(__file__).resolve().parents[3] / "tool-crawl" / "crawl-price"
)
if str(CRAWL_PRICE_DIR) not in sys.path:
    sys.path.insert(0, str(CRAWL_PRICE_DIR))

from app.integrations.llm.base import GroundedStructuredResult, GroundingSource
from app.modules.knowledge_graph.model import KnowledgeEntity, KnowledgeProperty
from app.modules.knowledge_graph.price_research import (
    TravelPlacePriceCandidate,
    TravelPlacePriceOutcome,
)
from enrich_travel_place_prices import (
    CandidateRecord,
    apply_outcomes,
    count_admission_prices,
    fetch_outcomes,
    load_candidates,
)
from enrich_travel_place_prices_from_sources import (
    load_records as load_source_records,
    load_source_rows,
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
    assert count_admission_prices(db_session) == 1


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


def test_apply_rejects_verified_outcome_without_grounded_source(db_session) -> None:
    db_session.add(_entity())
    db_session.flush()
    outcome = _outcome().model_copy(update={"sources": []})

    stats = apply_outcomes(
        db_session,
        [outcome],
        apply=True,
        overwrite=False,
    )

    assert stats["missing_grounded_source_skipped"] == 1
    assert (
        db_session.query(KnowledgeProperty)
        .filter_by(entity_id="travel_place_1", key="admission_price")
        .count()
        == 0
    )


class DelayedGroundedClient:
    async def generate_grounded_structured_json(self, *args, **kwargs):
        del kwargs
        entity_id = json.loads(args[1])["entityId"]
        await asyncio.sleep(0.03 if entity_id == "slow" else 0.0)
        return GroundedStructuredResult(
            text=json.dumps(
                {
                    "identityMatched": True,
                    "status": "priced",
                    "currency": "VND",
                    "representativeAmount": 70_000,
                    "sourceIndexes": [0],
                    "confidence": 0.9,
                }
            ),
            sources=(
                GroundingSource(
                    title="Official tickets",
                    uri=f"https://official.example/{entity_id}",
                ),
            ),
            search_queries=(),
        )


def test_fetch_outcomes_persists_each_result_as_it_completes() -> None:
    records = [
        CandidateRecord(
            candidate=TravelPlacePriceCandidate(
                entityId=entity_id,
                canonicalName=entity_id,
            ),
            has_existing_price=False,
        )
        for entity_id in ("slow", "fast")
    ]
    persisted: list[str] = []

    outcomes = asyncio.run(
        fetch_outcomes(
            records,
            llm_client=DelayedGroundedClient(),
            model_name="test-model",
            concurrency=2,
            on_outcome=lambda outcome: persisted.append(outcome.entity_id),
        )
    )

    assert persisted == ["fast", "slow"]
    assert [outcome.entity_id for outcome in outcomes] == persisted


class QuotaLimitedClient:
    def __init__(self) -> None:
        self.call_count = 0

    async def generate_grounded_structured_json(self, *args, **kwargs):
        del args, kwargs
        self.call_count += 1
        await asyncio.sleep(0)
        raise RuntimeError("Gemini quota limited")


def test_fetch_outcomes_stops_claiming_records_after_quota_exhaustion() -> None:
    records = [
        CandidateRecord(
            candidate=TravelPlacePriceCandidate(
                entityId=f"place_{index}",
                canonicalName=f"Place {index}",
            ),
            has_existing_price=False,
        )
        for index in range(10)
    ]
    client = QuotaLimitedClient()

    outcomes = asyncio.run(
        fetch_outcomes(
            records,
            llm_client=client,
            model_name="test-model",
            concurrency=4,
        )
    )

    assert len(outcomes) == 4
    assert client.call_count == 4
    assert all(outcome.error == "gemini_quota_limited" for outcome in outcomes)


def test_load_source_rows_accepts_jsonl_source_file(tmp_path) -> None:
    source_file = tmp_path / "sources.jsonl"
    source_file.write_text(
        json.dumps(
            {
                "entityId": "travel_place_1",
                "sources": [
                    {
                        "title": "Official tickets",
                        "uri": "https://official.example/tickets",
                        "snippet": "Adult ticket is 70,000 VND.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    rows = load_source_rows(source_file)

    assert rows["travel_place_1"][0]["uri"] == "https://official.example/tickets"


def test_source_records_skip_existing_price_without_overwrite(db_session) -> None:
    entity = _entity()
    db_session.add(entity)
    db_session.flush()
    db_session.add(
        KnowledgeProperty(
            entity_id=entity.id,
            key="admission_price",
            value='{"currency":"VND","representativeAmount":50000}',
            source="manual",
        )
    )
    db_session.flush()

    records = load_source_records(
        db_session,
        {
            entity.id: [
                {
                    "title": "Official tickets",
                    "uri": "https://official.example/tickets",
                    "snippet": "Adult ticket is 70,000 VND.",
                }
            ]
        },
        overwrite=False,
    )

    assert records == []
