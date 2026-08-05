from datetime import datetime, timezone

from sqlalchemy import create_engine, select
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
        "sourceLink": "https://www.google.com/maps/place/example",
        "openingHours": [{"dayOfWeek": 1, "rawTimeSlots": "08:00-22:00"}],
        "rating": 4.4,
        "reviewCount": 125,
        "placeMetadata": {
            "imageUrl": "https://images.example/one.jpg",
            "images": ["https://images.example/two.jpg"],
        },
        "fetchedAt": datetime(2026, 8, 5, tzinfo=timezone.utc),
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
            "latitude", "longitude", "googleMapsUrl", "imageUrl",
            "openingHours", "rating", "reviewCount", "fetchedAt",
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

        ExplorerPersistenceRepository(session).save(
            intake_id="intake-alias", user_id=None, destination="Đà Nẵng",
            resolutions=[_resolution("Ba Mua Noodles")],
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

        ExplorerPersistenceRepository(session).save(
            intake_id="intake-branches", user_id=None, destination="Đà Nẵng",
            resolutions=[_resolution()],
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
