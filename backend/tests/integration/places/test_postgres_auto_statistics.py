from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.modules.places.auto_statistics.service import AutoPlaceStatisticsService
from app.modules.places.model import Place
from app.modules.places.repository import SqlAlchemyPlaceRepository
from app.modules.places.service import PlaceCatalogService, PlaceCreate


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
def test_postgres_update_automatically_refreshes_region_statistics(
    tmp_path: Path,
) -> None:
    assert TEST_DATABASE_URL is not None
    engine = create_engine(TEST_DATABASE_URL)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    place_id = str(uuid.uuid4())
    unrelated_place_id = str(uuid.uuid4())
    output_path = tmp_path / "place_region_statistics.json"

    try:
        with session_factory() as session:
            repository = SqlAlchemyPlaceRepository(session)
            statistics_service = AutoPlaceStatisticsService(repository, output_path)
            catalog_service = PlaceCatalogService(repository)
            catalog_service.create_place(
                PlaceCreate(
                    id=place_id,
                    name="PostgreSQL Auto Statistics Test",
                    place_type="cafe",
                    region_key="vn,da-nang,hai-chau",
                    city="Đà Nẵng",
                    country="Việt Nam",
                    country_code="VN",
                    latitude=Decimal("16.0600000"),
                    longitude=Decimal("108.2200000"),
                    status="active",
                    opening_hours=[
                        {
                            "dayOfWeek": 1,
                            "openTime": "07:00",
                            "closeTime": "22:00",
                            "is24Hours": False,
                        }
                    ],
                    data_confidence="high",
                    source_fetched_at=datetime.now(timezone.utc),
                    metadata={"description": "Integration test", "prices": []},
                )
            )
            first_lookup = statistics_service.get_for_planner("vn,da-nang")
            assert first_lookup.status == "computed"
            created_fingerprint = first_lookup.source_fingerprint
            hai_chau = _region(first_lookup.regions, "vn,da-nang,hai-chau")
            assert hai_chau["countsByType"]["cafe"] >= 1
            catalog_service.update_place(
                place_id,
                {
                    "place_type": "museum",
                    "region_key": "vn,da-nang,son-tra",
                },
            )
            second_lookup = statistics_service.get_for_planner("vn,da-nang")
            assert second_lookup.status == "computed"
            assert second_lookup.snapshot_id != first_lookup.snapshot_id
            updated_fingerprint = second_lookup.source_fingerprint
            son_tra = _region(second_lookup.regions, "vn,da-nang,son-tra")

            assert updated_fingerprint != created_fingerprint
            assert son_tra["countsByType"]["museum"] >= 1
            updated_place = repository.get(place_id)
            assert updated_place is not None
            assert updated_place.revision == 2

            catalog_service.create_place(
                PlaceCreate(
                    id=unrelated_place_id,
                    name="Unrelated Hanoi Update",
                    place_type="restaurant",
                    region_key="vn,ha-noi,ba-dinh",
                    status="active",
                    source_fetched_at=datetime.now(timezone.utc),
                    metadata={"description": "Unrelated region", "prices": []},
                )
            )
            third_lookup = statistics_service.get_for_planner("vn,da-nang")
            assert third_lookup.status == "computed"
            assert third_lookup.snapshot_id == second_lookup.snapshot_id
            assert third_lookup.catalog_version == second_lookup.catalog_version
            assert third_lookup.source_fingerprint == updated_fingerprint
    finally:
        with Session(engine) as cleanup_session:
            cleanup_session.execute(
                delete(Place).where(Place.id.in_([place_id, unrelated_place_id]))
            )
            cleanup_session.commit()
        engine.dispose()


def _region(regions: list[dict], region_key: str) -> dict:
    return next(
        region for region in regions if region["regionKey"] == region_key
    )
