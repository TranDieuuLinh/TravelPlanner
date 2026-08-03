import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from app.modules.places.model import Place
from app.modules.places.repository import SqlAlchemyPlaceRepository
from app.modules.places.resolver import DatabasePlaceResolver
from app.modules.plans.explorer.schema import UnifiedPlaceCandidate


def test_verified_google_alias_creates_catalog_place_and_resolves_from_db(
    db_session,
) -> None:
    repository = SqlAlchemyPlaceRepository(db_session)
    fetched_at = datetime.now(timezone.utc)

    changed = repository.upsert_verified_google_aliases(
        external_id="ChIJ-vpbank-hoan-kiem",
        canonical_name="VPBank Hoan Kiem",
        aliases=["VP Bank", "VPBank Hoan Kiem"],
        place_type="bank",
        address="Hoàn Kiếm, Hà Nội",
        city="Hà Nội",
        country="Việt Nam",
        country_code="VN",
        primary_area="Hoàn Kiếm",
        latitude=Decimal("21.0285000"),
        longitude=Decimal("105.8542000"),
        region_key="vn,ha-noi",
        source_link="https://www.google.com/maps/place/?q=place_id:test",
        fetched_at=fetched_at,
        attribution="Google Maps data via gosom/google-maps-scraper",
    )

    assert changed is True
    place = db_session.get(Place, "ChIJ-vpbank-hoan-kiem")
    assert place is not None
    assert place.status == "active"
    assert place.source_platform == "google_maps_scraper"
    assert place.metadata_json["aliases"] == ["VP Bank"]
    assert place.metadata_json["verifiedAliases"][0]["provider"] == (
        "google_maps_scraper"
    )
    assert place.metadata_json["verifiedAliases"][0]["language"] == "und"

    resolution = asyncio.run(
        DatabasePlaceResolver(repository).resolve(
            UnifiedPlaceCandidate(
                name="VP Bank",
                category="other",
                searchRegion="Hà Nội",
            ),
            destination="Hà Nội",
        )
    )

    assert resolution.status == "resolved"
    assert resolution.place_id == "ChIJ-vpbank-hoan-kiem"
    assert resolution.provider == "database"


def test_verified_google_alias_update_is_idempotent(db_session) -> None:
    repository = SqlAlchemyPlaceRepository(db_session)
    place = Place(
        id="ChIJ-existing-place",
        name="Banh Mi 25",
        place_type="restaurant",
        region_key="vn,ha-noi",
        latitude=Decimal("21.0341000"),
        longitude=Decimal("105.8472000"),
        status="active",
        opening_hours=[],
        data_confidence="high",
        revision=3,
        metadata_json={"aliases": ["Bánh Mì 25"]},
    )
    db_session.add(place)
    db_session.commit()
    arguments = {
        "external_id": place.id,
        "canonical_name": place.name,
        "aliases": ["Bunmi 25", "Bánh Mì 25"],
        "place_type": place.place_type,
        "address": None,
        "city": "Hà Nội",
        "country": "Việt Nam",
        "country_code": "VN",
        "primary_area": None,
        "latitude": place.latitude,
        "longitude": place.longitude,
        "region_key": place.region_key,
        "source_link": None,
        "fetched_at": datetime.now(timezone.utc),
        "attribution": "Google Maps data via gosom/google-maps-scraper",
    }

    assert repository.upsert_verified_google_aliases(**arguments) is True
    assert place.revision == 4
    assert place.metadata_json["aliases"] == ["Bánh Mì 25", "Bunmi 25"]
    learned = {
        value["name"]: value["language"]
        for value in place.metadata_json["verifiedAliases"]
    }
    assert learned["Bánh Mì 25"] == "vi"
    assert repository.upsert_verified_google_aliases(**arguments) is False
    assert place.revision == 4
