from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.knowledge_graph.model import (
    KnowledgeAlias,
    KnowledgeEntity,
    KnowledgeGraphImport,
    KnowledgeGraphImportEdge,
    KnowledgeGraphImportNode,
    KnowledgeProperty,
)
from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository
from app.modules.plans.explorer.model import DestinationRegionStory, SourceDocument
from app.modules.plans.explorer.tools.url_reels.schema import UrlReelExtractionResult


def _resolution(name: str = "Mì Quảng Bà Mua") -> PlaceResolution:
    return PlaceResolution.model_validate({
        "candidate": {
            "name": name,
            "category": "food",
            "sources": [{"type": "url", "url": "https://example.com/reel"}],
            "confidence": 0.9,
            "searchRegion": "Đà Nẵng",
            "sourceEvidence": {"ocr": name, "stt": f"Ăn tại {name}"},
            "sourceOrder": 2,
            "sourceActivity": "Ăn mì Quảng.",
        },
        "status": "resolved",
        "provider": "google_maps_scraper",
        "externalId": "google-123",
        "name": name,
        "placeType": "Restaurant",
        "address": "Hải Châu, Đà Nẵng",
        "city": "Đà Nẵng",
        "latitude": 16.0592,
        "longitude": 108.2131,
        "description": "Quán mì Quảng ở trung tâm Hải Châu.",
        "sourceLink": "https://www.google.com/maps/place/example",
        "openingHours": [{"dayOfWeek": 1, "rawTimeSlots": "08:00-22:00"}],
        "rating": 4.4,
        "reviewCount": 125,
        "placeMetadata": {
            "imageUrl": "https://images.example/one.jpg",
            "images": ["https://images.example/two.jpg"],
        },
        "fetchedAt": datetime(2026, 8, 5, tzinfo=timezone.utc),
        "attribution": "Google Maps",
    })


def test_explorer_persists_candidate_as_kg_import_node_with_minimal_snapshot() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-1", user_id=None, destination="Đà Nẵng",
            resolutions=[_resolution()],
        )

        import_job = session.get(KnowledgeGraphImport, "intake-1")
        node = session.scalar(select(KnowledgeGraphImportNode).where(
            KnowledgeGraphImportNode.type != "Area"
        ))
        assert import_job is not None
        assert import_job.import_kind == "explorer_intake"
        assert import_job.processing_status == "succeeded"
        assert import_job.review_status == "pending"
        assert node is not None
        assert node.source_evidence == {
            "ocr": "Mì Quảng Bà Mua", "stt": "Ăn tại Mì Quảng Bà Mua"
        }
        assert node.selected_entity_id is None
        assert node.identity_status == "unresolved"
        assert set(node.provider_snapshot) == {
            "status", "externalId", "name", "placeType", "address", "city",
            "description", "latitude", "longitude", "googleMapsUrl", "imageUrl",
            "openingHours", "rating", "reviewCount", "fetchedAt",
            "attribution",
        }
        assert node.provider_snapshot["imageUrl"] == "https://images.example/one.jpg"
        edge = session.scalar(select(KnowledgeGraphImportEdge))
        assert edge is not None
        assert edge.relationship_type == "LOCATED_IN"
        assert edge.to_ref == "area-root"

        selected = repository.load_must_places("intake-1", None)
        assert len(selected) == 1
        assert selected[0].source_import_node_id == node.id
        assert selected[0].image_urls == ["https://images.example/one.jpg"]
        assert selected[0].notes == "Ăn mì Quảng."
        assert selected[0].note_sources == []


def test_explorer_loads_curated_destination_region_stories_from_database() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        session.add(
            DestinationRegionStory(
                id="vn-ha-noi-history",
                region_key="vn,ha-noi",
                story_type="destination_history",
                text="Hanoi has more than a thousand years of history.",
                source_url="https://english.hanoi.gov.vn/history",
                evidence_types_json=["webpage"],
                fetched_at=datetime(2026, 8, 8, tzinfo=timezone.utc),
                sort_order=10,
                is_active=True,
            )
        )
        session.commit()

        stories = repository.load_destination_region_stories("Hanoi")

        assert len(stories) == 1
        assert stories[0].type == "destination_history"
        assert stories[0].text == "Hanoi has more than a thousand years of history."
        assert stories[0].evidence is None
        assert stories[0].ref == "https://english.hanoi.gov.vn/history"
        assert stories[0].evidence_types == ["webpage"]


def test_url_source_document_does_not_persist_region_story() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        result = UrlReelExtractionResult.model_validate(
            {
                "url": "https://www.instagram.com/reel/example/",
                "platform": "instagram",
                "metadata": {
                    "originalUrl": "https://www.instagram.com/reel/example/",
                    "canonicalUrl": "https://www.instagram.com/reel/example/",
                    "platform": "instagram",
                },
                "artifacts": {},
                "speechToText": {
                    "text": "Hanoi story",
                    "status": "ok",
                    "source": "stt",
                    "durationSeconds": 1,
                },
                "extractedContext": {
                    "regionStory": {
                        "text": "A URL-authored Hanoi story.",
                        "evidence": "Hanoi story",
                        "evidenceType": "stt",
                    }
                },
                "timings": {},
            }
        )
        repository._save_source_documents(
            {"https://www.instagram.com/reel/example/": [result]}
        )

        document = session.scalar(select(SourceDocument))

        assert document is not None
        assert "regionStory" not in document.extracted_context_json


def test_explorer_keeps_critical_intake_when_kg_enrichment_fails() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)

        def fail_matching(*args, **kwargs):
            raise RuntimeError("enrichment unavailable")

        repository._match_knowledge_entities = fail_matching  # type: ignore[method-assign]

        with pytest.raises(RuntimeError, match="enrichment unavailable"):
            repository.save(
                intake_id="intake-degraded",
                user_id=None,
                destination="Đà Nẵng",
                resolutions=[_resolution()],
            )

        assert repository.critical_intake_exists("intake-degraded") is True
        saved = session.get(KnowledgeGraphImport, "intake-degraded")
        assert saved is not None
        assert saved.destination == "Đà Nẵng"


def test_persistence_reuses_place_resolution_without_kg_rematch() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        matched_names: list[str] = []

        def record_area_match(name: str, **_kwargs):
            matched_names.append(name)
            return [], None, "unresolved"

        repository._match_knowledge_entities = record_area_match  # type: ignore[method-assign]
        repository.save(
            intake_id="intake-no-rematch",
            user_id=None,
            destination="Đà Nẵng",
            resolutions=[_resolution()],
        )

        assert matched_names == ["Đà Nẵng"]


def test_critical_persistence_retries_transient_serialization_failure() -> None:
    class SerializationFailure(Exception):
        pgcode = "40001"

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        original = repository._save_source_documents
        attempts = 0

        def fail_once(results_by_url):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise OperationalError(
                    "source document serialization failure",
                    {},
                    SerializationFailure(),
                )
            return original(results_by_url)

        repository._save_source_documents = fail_once  # type: ignore[method-assign]
        metrics = repository.save(
            intake_id="intake-retry",
            user_id=None,
            destination="Đà Nẵng",
            resolutions=[],
        )

        assert attempts == 2
        assert metrics["transactionRetryCount"] == 1
        assert metrics["nodeCount"] == 1
        assert metrics["edgeCount"] == 0
        assert session.get(KnowledgeGraphImport, "intake-retry") is not None


def test_top_k_uses_reviewed_alias_and_resolves_a_clear_entity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        entity = KnowledgeEntity(
            id="venue-mi-quang", canonical_name="Mì Quảng Bà Mua",
            normalized_name="mi quang ba mua", entity_type="Restaurant",
            status="active",
        )
        entity.aliases.append(KnowledgeAlias(
            alias="Ba Mua Noodles", normalized_alias="ba mua noodles",
            language="en", status="verified",
        ))
        entity.properties.extend([
            KnowledgeProperty(key="city", value="Đà Nẵng"),
            KnowledgeProperty(key="latitude", value="16.0592"),
            KnowledgeProperty(key="longitude", value="108.2131"),
        ])
        session.add(entity)
        session.commit()

        repository = ExplorerPersistenceRepository(session)
        resolution = repository.resolve_from_knowledge_graph(
            _resolution("Ba Mua Noodles").candidate,
            destination="Đà Nẵng",
        )
        assert resolution is not None
        repository.save(
            intake_id="intake-alias", user_id=None, destination="Đà Nẵng",
            resolutions=[resolution],
        )
        node = session.scalar(select(KnowledgeGraphImportNode).where(
            KnowledgeGraphImportNode.type != "Area"
        ))
        assert node is not None
        assert node.selected_entity_id == "venue-mi-quang"
        assert node.identity_status == "resolved"
        assert node.selection_method == "knowledge_top_k"
        assert node.match_candidates[0]["entityId"] == "venue-mi-quang"


def test_same_name_branches_stay_for_route_selection_without_global_identity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for entity_id, address, latitude in (
            ("branch-hai-chau", "Hải Châu, Đà Nẵng", "16.06"),
            ("branch-son-tra", "Sơn Trà, Đà Nẵng", "16.08"),
        ):
            entity = KnowledgeEntity(
                id=entity_id, canonical_name="Mì Quảng Bà Mua",
                normalized_name="mi quang ba mua", entity_type="Restaurant",
                status="active",
            )
            entity.properties.extend([
                KnowledgeProperty(key="address", value=address),
                KnowledgeProperty(key="city", value="Đà Nẵng"),
                KnowledgeProperty(key="latitude", value=latitude),
                KnowledgeProperty(key="longitude", value="108.21"),
            ])
            session.add(entity)
        session.commit()

        repository = ExplorerPersistenceRepository(session)
        resolution = repository.resolve_from_knowledge_graph(
            _resolution().candidate,
            destination="Đà Nẵng",
        )
        assert resolution is not None
        repository.save(
            intake_id="intake-branches", user_id=None, destination="Đà Nẵng",
            resolutions=[resolution],
        )
        node = session.scalar(select(KnowledgeGraphImportNode).where(
            KnowledgeGraphImportNode.type != "Area"
        ))
        assert node is not None
        assert node.selected_entity_id is None
        assert node.identity_status == "branch_ambiguous"
        assert {item["entityId"] for item in node.match_candidates} == {
            "branch-hai-chau", "branch-son-tra"
        }
        selected = ExplorerPersistenceRepository(session).load_must_places(
            "intake-branches", None
        )[0]
        assert selected.candidate_entity_ids == [
            item["entityId"] for item in node.match_candidates
        ]
        assert selected.identity_confidence == "low"
        assert selected.place_id in {"branch-hai-chau", "branch-son-tra"}
        assert selected.selection_method == "route_proximity"


def test_soft_merged_duplicate_redirects_without_false_ambiguity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        canonical = KnowledgeEntity(
            id="temple-canonical",
            canonical_name="Temple of Literature",
            normalized_name="temple of literature",
            entity_type="TravelPlace",
            status="active",
        )
        canonical.properties.extend(
            [
                KnowledgeProperty(key="catalog_status", value="active"),
                KnowledgeProperty(key="city", value="Đà Nẵng"),
                KnowledgeProperty(key="latitude", value="16.0592"),
                KnowledgeProperty(key="longitude", value="108.2131"),
            ]
        )
        duplicate = KnowledgeEntity(
            id="temple-duplicate",
            canonical_name="Temple of Literature",
            normalized_name="temple of literature",
            entity_type="TravelPlace",
            status="active",
        )
        duplicate.properties.extend(
            [
                KnowledgeProperty(key="catalog_status", value="merged"),
                KnowledgeProperty(
                    key="merged_into_entity_id", value="temple-canonical"
                ),
                KnowledgeProperty(key="city", value="Đà Nẵng"),
                KnowledgeProperty(key="latitude", value="16.0592"),
                KnowledgeProperty(key="longitude", value="108.2131"),
            ]
        )
        session.add_all([canonical, duplicate])
        session.commit()

        repository = ExplorerPersistenceRepository(session)
        resolution = repository.resolve_from_knowledge_graph(
            _resolution("Temple of Literature").candidate,
            destination="Đà Nẵng",
        )
        assert resolution is not None
        repository.save(
            intake_id="intake-soft-merge",
            user_id=None,
            destination="Đà Nẵng",
            resolutions=[resolution],
        )

        node = session.scalar(
            select(KnowledgeGraphImportNode).where(
                KnowledgeGraphImportNode.type != "Area"
            )
        )
        assert node is not None
        assert node.identity_status == "resolved"
        assert node.selected_entity_id == "temple-canonical"
        assert [item["entityId"] for item in node.match_candidates] == [
            "temple-canonical"
        ]


def test_branch_candidates_resolve_from_kg_before_google_fallback() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        for entity_id, latitude in (("branch-a", "16.06"), ("branch-b", "16.08")):
            entity = KnowledgeEntity(
                id=entity_id, canonical_name="Mì Quảng Bà Mua",
                normalized_name="mi quang ba mua", entity_type="Restaurant",
                status="active",
            )
            entity.properties.extend([
                KnowledgeProperty(key="city", value="Đà Nẵng"),
                KnowledgeProperty(key="latitude", value=latitude),
                KnowledgeProperty(key="longitude", value="108.21"),
            ])
            session.add(entity)
        session.commit()
        candidate = _resolution().candidate

        resolution = ExplorerPersistenceRepository(
            session
        ).resolve_from_knowledge_graph(candidate, destination="Đà Nẵng")

        assert resolution is not None
        assert resolution.provider == "knowledge_graph"
        assert resolution.resolution_reason == "branch_ambiguous"
        assert resolution.place_id is None
        assert {option.place_id for option in resolution.match_options} == {
            "branch-a", "branch-b"
        }


def test_unresolved_provider_result_is_not_promoted_to_itinerary() -> None:
    resolution = _resolution().model_copy(update={"status": "unresolved"})
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ExplorerPersistenceRepository(session).save(
            intake_id="intake-unresolved", user_id=None, destination="Đà Nẵng",
            resolutions=[resolution],
        )
        assert session.scalar(select(KnowledgeGraphImportNode).where(
            KnowledgeGraphImportNode.type != "Area"
        )) is None
        assert ExplorerPersistenceRepository(session).load_must_places(
            "intake-unresolved", None
        ) == []
