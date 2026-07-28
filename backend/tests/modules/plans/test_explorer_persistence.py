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
        assert selected_places[0].must_visit is True
        assert selected_places[0].place_id is None
        assert selected_places[0].name == "Mì Quảng Bà Mua"
        assert repository.load_must_places("intake-1", "another-user") == []

    engine.dispose()
