from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.places.model import Place
from app.modules.places.resolver import PlaceResolution
from app.modules.plans.explorer.model import (
    ExplorerIntake,
    UrlExtractionCacheEntry,
    UserMustPlace,
    UserMustPlaceUser,
)
from app.modules.plans.explorer.repository import ExplorerPersistenceRepository


def test_explorer_persists_resolved_candidate_only_in_user_must_place() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[ExplorerIntake.__table__, UserMustPlace.__table__, UserMustPlaceUser.__table__],
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
                "searchRegion": "Đà Nẵng",
                "sourceEvidence": {
                    "ocr": "Mì Quảng Bà Mua",
                    "stt": "Order mì Quảng here.",
                },
                "sourceOrder": 2,
                "sourceDay": 1,
                "sourceTimeHint": "lunch",
                "sourceActivity": "Order mì Quảng with the house toppings.",
                "sourceDurationMinutes": 60,
            },
            "status": "resolved",
            "resolutionReason": None,
            "provider": "fake_places",
            "externalId": "place-123",
            "name": "Mì Quảng Bà Mua",
            "placeType": "Restaurant",
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
        assert must_place.search_region == "Đà Nẵng"
        assert must_place.source_evidence_json["ocr"] == "Mì Quảng Bà Mua"
        assert must_place.resolution_reason is None
        assert must_place.description == "Nhà hàng chuyên món mì Quảng."
        assert must_place.latitude == Decimal("16.0592000")
        assert must_place.external_id == "place-123"
        assert must_place.provider == "fake_places"
        intake = session.get(ExplorerIntake, "intake-1")
        assert intake is not None
        assert intake.destination == "Đà Nẵng"
        assert inspect(engine).get_table_names() == [
            "explorer_intakes",
            "user_must_place",
            "user_must_place_users",
        ]
        selected_places = repository.load_must_places("intake-1", None)
        assert len(selected_places) == 1
        assert selected_places[0].must_visit is False
        assert selected_places[0].preference_level.value == "preferred"
        assert selected_places[0].place_id is None
        assert selected_places[0].name == "Mì Quảng Bà Mua"
        assert selected_places[0].source_provider == "fake_places"
        assert selected_places[0].address == "Đà Nẵng"
        assert selected_places[0].notes == "Nhà hàng chuyên món mì Quảng."
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


def test_verified_place_type_overrides_incorrect_ai_candidate_category() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Place.__table__,
            ExplorerIntake.__table__,
            UserMustPlace.__table__,
            UserMustPlaceUser.__table__,
        ],
    )
    resolution = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Ho Chi Minh Museum",
                "category": "food",
                "sources": [
                    {"type": "url", "url": "https://example.com/video"}
                ],
                "confidence": 0.9,
            },
            "status": "resolved",
            "provider": "database",
            "placeId": "museum-1",
            "name": "Ho Chi Minh Museum",
            "placeType": "Museum",
            "city": "Hà Nội",
            "latitude": "21.0359000",
            "longitude": "105.8326000",
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-museum-category",
            user_id=None,
            destination="Hà Nội",
            resolutions=[resolution],
        )

        must_place = session.scalar(select(UserMustPlace))
        assert must_place is not None
        assert must_place.category == "culture"
        assert must_place.place_type == "Museum"
        selected = repository.load_must_places(
            "intake-museum-category",
            None,
        )
        assert selected[0].tags[0] == "culture"

    engine.dispose()


def test_unresolved_candidate_with_coordinates_is_not_persisted() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            ExplorerIntake.__table__,
            UserMustPlace.__table__,
            UserMustPlaceUser.__table__,
        ],
    )
    resolution = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Phở tại 144A Quán Thánh",
                "category": "food",
                "addressHint": "144A Quán Thánh, Ba Đình, Hà Nội",
                "searchRegion": "Hà Nội",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                "confidence": 0.9,
            },
            "status": "unresolved",
            "resolutionReason": "name_mismatch",
            "provider": "google_maps_scraper",
            "name": "144A Quán Thánh",
            "address": "144A Quán Thánh, Ba Đình, Hà Nội",
            "city": "Hà Nội",
            "latitude": "21.0421000",
            "longitude": "105.8422000",
        }
    )

    with Session(engine) as session:
        ExplorerPersistenceRepository(session).save(
            intake_id="intake-unresolved",
            user_id=None,
            destination="Hà Nội",
            resolutions=[resolution],
        )

        assert session.scalar(select(UserMustPlace)) is None

    engine.dispose()


def test_external_identity_is_not_persisted_as_missing_catalog_place_id() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Place.__table__,
            ExplorerIntake.__table__,
            UserMustPlace.__table__,
            UserMustPlaceUser.__table__,
        ],
    )
    resolution = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Hoan Kiem Lake",
                "category": "nature",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://www.youtube.com/watch?v=stale-place-id",
                    }
                ],
                "confidence": 0.9,
            },
            "status": "resolved",
            "provider": "google_maps_scraper",
            "externalId": "ChIJ-external-google-id",
            "placeId": "ChIJ-external-google-id",
            "name": "Hồ Hoàn Kiếm",
            "city": "Hà Nội",
            "latitude": "21.0287000",
            "longitude": "105.8522000",
        }
    )

    with Session(engine) as session:
        ExplorerPersistenceRepository(session).save(
            intake_id="intake-stale-place-id",
            user_id=None,
            destination="Hà Nội",
            resolutions=[resolution],
        )

        must_place = session.scalar(select(UserMustPlace))
        assert must_place is not None
        assert must_place.external_id == "ChIJ-external-google-id"
        assert must_place.place_id is None

    engine.dispose()


def test_existing_catalog_place_id_is_preserved() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Place.__table__,
            ExplorerIntake.__table__,
            UserMustPlace.__table__,
            UserMustPlaceUser.__table__,
        ],
    )
    resolution = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Văn Miếu - Quốc Tử Giám",
                "category": "culture",
                "sources": [
                    {"type": "url", "url": "https://example.com/catalog-place"}
                ],
                "confidence": 0.9,
            },
            "status": "resolved",
            "provider": "database",
            "externalId": "place-van-mieu",
            "placeId": "place-van-mieu",
            "name": "Văn Miếu - Quốc Tử Giám",
            "city": "Hà Nội",
            "latitude": "21.0280000",
            "longitude": "105.8355000",
        }
    )

    with Session(engine) as session:
        session.add(
            Place(
                id="place-van-mieu",
                name="Văn Miếu - Quốc Tử Giám",
                place_type="culture",
                region_key="vn,ha-noi",
                status="active",
                opening_hours=[],
                data_confidence="high",
                metadata_json={},
            )
        )
        session.commit()
        ExplorerPersistenceRepository(session).save(
            intake_id="intake-catalog-place",
            user_id=None,
            destination="Hà Nội",
            resolutions=[resolution],
        )

        must_place = session.scalar(select(UserMustPlace))
        assert must_place is not None
        assert must_place.place_id == "place-van-mieu"

    engine.dispose()


def test_stale_url_extraction_cache_is_recomputed() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[UrlExtractionCacheEntry.__table__],
    )
    url = "https://www.tiktok.com/@tereveling_/video/7667982507035348244"

    with Session(engine) as session:
        session.add(
            UrlExtractionCacheEntry(
                source_url=url,
                platform="tiktok",
                extracted_context_json={
                    "extractedPlaces": ["Hoa Lo Prison 10"],
                    "extractedPlaceDetails": [],
                },
            )
        )
        session.commit()

        assert ExplorerPersistenceRepository(session).load_cached_url_result(
            url
        ) is None

    engine.dispose()


def test_same_url_place_is_shared_across_multiple_intakes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            ExplorerIntake.__table__,
            UserMustPlace.__table__,
            UserMustPlaceUser.__table__,
            UrlExtractionCacheEntry.__table__,
        ],
    )
    resolution = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Hoan Kiem Lake",
                "category": "nature",
                "sources": [{
                    "type": "url",
                    "url": "https://www.youtube.com/watch?v=shared01&utm_source=x",
                }],
                "sourceEvidence": {
                    "stt": "Visit before 8am for a quieter walk.",
                    "ocr": "Hoan Kiem Lake",
                },
                "confidence": 0.9,
            },
            "status": "resolved",
            "provider": "google_maps_scraper",
            "externalId": "google-hoan-kiem",
            "name": "Hồ Hoàn Kiếm",
            "placeType": "nature",
            "address": "Hoàn Kiếm, Hà Nội",
            "city": "Hà Nội",
            "country": "Việt Nam",
            "countryCode": "VN",
            "latitude": "21.0287000",
            "longitude": "105.8522000",
            "rating": "4.7",
            "reviewCount": 12000,
            "placeMetadata": {
                "imageUrls": ["https://images.example/hoan-kiem.jpg"]
            },
            "placeStatus": "active",
            "dataConfidence": "medium",
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-shared-1",
            user_id=None,
            destination="Hà Nội",
            resolutions=[resolution],
        )
        repository.save(
            intake_id="intake-shared-2",
            user_id=None,
            destination="Hà Nội",
            resolutions=[resolution],
        )

        shared_places = list(session.scalars(select(UserMustPlace)))
        links = list(session.scalars(select(UserMustPlaceUser)))
        assert len(shared_places) == 1
        assert len(links) == 2
        assert shared_places[0].source_url == (
            "https://www.youtube.com/watch?v=shared01"
        )
        assert shared_places[0].name == "Hồ Hoàn Kiếm"
        assert shared_places[0].rating == Decimal("4.70")
        assert "Visit before 8am" in (shared_places[0].notes or "")
        selected_places = repository.load_must_places("intake-shared-1", None)
        assert len(selected_places) == 1
        assert selected_places[0].rating == 4.7
        assert selected_places[0].review_count == 12000
        assert selected_places[0].image_urls == [
            "https://images.example/hoan-kiem.jpg"
        ]
        assert len(repository.load_must_places("intake-shared-2", None)) == 1
        cached = repository.load_cached_url_result(
            "https://www.youtube.com/watch?v=shared01&utm_campaign=again"
        )
        assert cached is not None
        assert cached.speech_to_text.status == "cached"
        assert cached.extracted_context.extracted_places == ["Hoan Kiem Lake"]

    engine.dispose()


def test_url_itinerary_displays_resolved_vietnamese_name() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[ExplorerIntake.__table__, UserMustPlace.__table__, UserMustPlaceUser.__table__],
    )
    resolution = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Museum of Ethnology",
                "category": "culture",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://example.com/tiktok",
                    }
                ],
                "confidence": 0.9,
                "sourceOrder": 2,
            },
            "status": "resolved",
            "provider": "google_maps_scraper",
            "name": "Bảo tàng Dân tộc học Việt Nam",
            "address": "Đường Nguyễn Văn Huyên, Cầu Giấy, Hà Nội, Việt Nam",
            "city": "Hà Nội",
            "country": "Việt Nam",
            "latitude": "21.0403000",
            "longitude": "105.7980000",
            "dataConfidence": "high",
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-localized-name",
            user_id=None,
            destination="Hà Nội",
            resolutions=[resolution],
        )

        selected = repository.load_must_places(
            "intake-localized-name",
            None,
        )

        assert selected[0].name == "Bảo tàng Dân tộc học Việt Nam"
        assert selected[0].address == (
            "Đường Nguyễn Văn Huyên, Cầu Giấy, Hà Nội, Việt Nam"
        )
        assert selected[0].latitude == 21.0403
        assert selected[0].longitude == 105.798

    engine.dispose()


def test_url_itinerary_drops_source_name_when_provider_match_is_only_city() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[ExplorerIntake.__table__, UserMustPlace.__table__, UserMustPlaceUser.__table__],
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

        assert selected == []

    engine.dispose()


def test_url_itinerary_rejects_destination_alias_resolved_to_airport() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[ExplorerIntake.__table__, UserMustPlace.__table__, UserMustPlaceUser.__table__],
    )
    resolution = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Hanoi",
                "category": "other",
                "sources": [
                    {
                        "type": "url",
                        "url": "https://example.com/reel",
                    }
                ],
                "confidence": 0.9,
                "sourceOrder": 1,
            },
            "status": "resolved",
            "provider": "google_maps_scraper",
            "name": "Sân bay Quốc tế Nội Bài",
            "city": "Hà Nội",
            "country": "Việt Nam",
            "latitude": "21.2187",
            "longitude": "105.8042",
            "dataConfidence": "medium",
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-hanoi-alias",
            user_id=None,
            destination="Hanoi, Vietnam",
            resolutions=[resolution],
        )

        assert repository.load_must_places(
            "intake-hanoi-alias",
            None,
        ) == []

    engine.dispose()


def test_explorer_does_not_persist_unresolved_candidates_without_coordinates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[ExplorerIntake.__table__, UserMustPlace.__table__, UserMustPlaceUser.__table__],
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

        assert session.scalar(select(UserMustPlace)) is None
        assert repository.load_must_places("intake-1", None) == []

    engine.dispose()


def test_explorer_does_not_persist_provisional_candidate_with_coordinates() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[ExplorerIntake.__table__, UserMustPlace.__table__, UserMustPlaceUser.__table__],
    )
    provisional = PlaceResolution.model_validate(
        {
            "candidate": {
                "name": "Địa điểm chưa xác minh",
                "category": "other",
                "sources": [{"type": "user_prompt", "url": None}],
                "confidence": 0.5,
            },
            "status": "provisional",
            "provider": "fake_places",
            "name": "Địa điểm chưa xác minh",
            "city": "Hà Nội",
            "latitude": "21.0285",
            "longitude": "105.8542",
            "dataConfidence": "low",
        }
    )

    with Session(engine) as session:
        repository = ExplorerPersistenceRepository(session)
        repository.save(
            intake_id="intake-provisional",
            user_id=None,
            destination="Hà Nội",
            resolutions=[provisional],
        )

        assert session.scalar(select(UserMustPlace)) is None

    engine.dispose()


def test_explorer_drops_high_confidence_url_stop_without_verified_identity() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[ExplorerIntake.__table__, UserMustPlace.__table__, UserMustPlaceUser.__table__],
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

        assert selected == []
        assert session.scalar(select(UserMustPlace)) is None

    engine.dispose()
