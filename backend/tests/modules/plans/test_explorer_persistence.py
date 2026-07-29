from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.model import UserMustPlace
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository


def test_explorer_persists_resolved_candidate_only_in_user_must_place() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[UserMustPlace.__table__],
    )
    resolution = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Mì Quảng Bà Mua",
                "category": "food",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                "confidence": 0.85,
                "sourceOrder": 2,
                "sourceDay": 1,
                "sourceTimeHint": "lunch",
                "sourceActivity": "Order mì Quảng with the house toppings.",
                "sourceDurationMinutes": 60,
            },
            "status": "resolved",
            "provider": "fake_places",
            "externalId": "place-123",
            "name": "Mì Quảng Bà Mua",
            "address": "Đà Nẵng",
            "city": "Đà Nẵng",
            "country": "Việt Nam",
            "countryCode": "VN",
            "latitude": "16.0592000",
            "longitude": "108.2131000",
            "description": "Nhà hàng chuyên món mì Quảng.",
            "dataConfidence": "high",
            "fetchedAt": datetime(2026, 7, 28, tzinfo=timezone.utc),
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-1",
            user_id=None,
            destination="Đà Nẵng",
            resolutions=[resolution],
        )

        must_place = session.scalar(select(UserMustPlace))

        assert must_place is not None
        assert must_place.resolution_status == "resolved"
        assert must_place.sources_json[0]["url"] == "https://example.com/reel"
        assert must_place.category == "food"
        assert must_place.description == "Nhà hàng chuyên món mì Quảng."
        assert must_place.latitude == Decimal("16.0592000")
        assert must_place.external_id == "place-123"
        assert must_place.provider == "fake_places"
        assert inspect(engine).get_table_names() == ["user_must_place"]
        selected_places = repository.load_must_places("intake-1", None)
        assert len(selected_places) == 1
        assert selected_places[0].must_visit is False
        assert selected_places[0].preference_level.value == "preferred"
        assert selected_places[0].place_id is None
        assert selected_places[0].name == "Mì Quảng Bà Mua"
        assert selected_places[0].latitude == 16.0592
        assert selected_places[0].longitude == 108.2131
        assert selected_places[0].source_order == 2
        assert selected_places[0].source_day == 1
        assert selected_places[0].source_time_hint == "lunch"
        assert selected_places[0].source_activity == (
            "Order mì Quảng with the house toppings."
        )
        assert selected_places[0].source_duration_minutes == 60
        assert repository.load_must_places("intake-1", "another-user") == []

    engine.dispose()


def test_url_itinerary_keeps_source_name_when_provider_match_is_broad() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[UserMustPlace.__table__],
    )
    resolution = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Văn Miếu - Quốc Tử Giám",
                "category": "culture",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                "confidence": 0.85,
                "sourceOrder": 3,
            },
            "status": "resolved",
            "provider": "fake_places",
            "name": "Hà Nội",
            "city": "Hà Nội",
            "latitude": "21.0285",
            "longitude": "105.8542",
            "dataConfidence": "medium",
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-source-name",
            user_id=None,
            destination="Hà Nội",
            resolutions=[resolution],
        )

        selected = repository.load_must_places(
            "intake-source-name",
            None,
        )

        assert selected[0].name == "Văn Miếu - Quốc Tử Giám"

    engine.dispose()


def test_explorer_does_not_schedule_unresolved_candidates_without_coordinates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[UserMustPlace.__table__],
    )
    unresolved = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Find Video Info",
                "category": "other",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                "confidence": 0.2,
            },
            "status": "unresolved",
            "name": "Find Video Info",
            "city": "Hà Nội",
            "dataConfidence": "low",
        }
    )
    no_coordinates = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Dong Xuan St and Hang Ma",
                "category": "attraction",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                "confidence": 0.55,
            },
            "status": "provisional",
            "provider": "fake_places",
            "name": "Dong Xuan St and Hang Ma",
            "address": "Hà Nội",
            "city": "Hà Nội",
            "dataConfidence": "low",
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-1",
            user_id=None,
            destination="Hà Nội",
            resolutions=[unresolved, no_coordinates],
        )

        assert session.scalar(select(UserMustPlace)) is not None
        assert repository.load_must_places("intake-1", None) == []

    engine.dispose()


def test_explorer_keeps_high_confidence_url_stop_without_coordinates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[UserMustPlace.__table__],
    )
    unresolved_activity = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Cooking Class",
                "category": "culture",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://example.com/hanoi-day",
                    }
                ],
                "confidence": 0.9,
                "sourceOrder": 5,
                "sourceDay": 1,
                "sourceTimeHint": "before lunch",
                "sourceActivity": "Join the market visit and cooking class.",
            },
            "status": "unresolved",
            "name": "Cooking Class",
            "city": "Hà Nội",
            "dataConfidence": "low",
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-url",
            user_id=None,
            destination="Hà Nội",
            resolutions=[unresolved_activity],
        )

        selected = repository.load_must_places("intake-url", None)

        assert len(selected) == 1
        assert selected[0].name == "Cooking Class"
        assert selected[0].source_order == 5
        assert selected[0].latitude is None
        assert selected[0].longitude is None

    engine.dispose()
