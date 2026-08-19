import asyncio

from app.modules.place_checker.adapters.postgres_catalog_batch import (
    MAX_SEARCH_BATCH_SIZE,
    PostgresCatalogBatchMixin,
)
from app.shared.tools.search_places import AdministrativeArea


class FakePool:
    def __init__(self) -> None:
        self.arguments = None

    async def fetch(self, sql, *arguments):
        self.arguments = arguments
        return [
            {"batch_index": 0, "id": "place-1"},
            {"batch_index": 1, "id": "place-2"},
        ]


class Catalog(PostgresCatalogBatchMixin):
    def __init__(self) -> None:
        self.pool = FakePool()

    async def _get_pool(self):
        return self.pool

    @staticmethod
    def _types_for_hint(value):
        return {"TravelPlace"}

    @staticmethod
    def _candidate(row, input_adm):
        return row["id"]


def test_catalog_search_many_uses_one_query_and_preserves_groups() -> None:
    catalog = Catalog()
    adm = AdministrativeArea(
        adm_id="adm-1", name="Hà Nội", country_code="VN"
    )

    result = asyncio.run(catalog.search_many(
        [["Hồ Hoàn Kiếm"], ["Văn Miếu"]],
        input_adm=adm,
        place_type_hint=None,
        limit=5,
    ))

    assert result == [["place-1"], ["place-2"]]
    assert catalog.pool.arguments[0] == ["ho hoan kiem", "van mieu"]
    assert catalog.pool.arguments[4] == [None, None]


def test_catalog_search_many_passes_one_anchor_per_query() -> None:
    catalog = Catalog()
    adm = AdministrativeArea(adm_id="adm-1", name="Hà Nội", country_code="VN")

    asyncio.run(catalog.search_many(
        [["Museum"], ["Garden"]],
        input_adm=adm,
        place_type_hint="travel_place",
        limit=5,
        anchor_place_ids=["place-a", "place-b"],
    ))

    assert catalog.pool.arguments[4] == ["place-a", "place-b"]


def test_catalog_search_many_rejects_more_than_ten_queries() -> None:
    catalog = Catalog()
    adm = AdministrativeArea(
        adm_id="adm-1", name="Hà Nội", country_code="VN"
    )

    async def run():
        await catalog.search_many(
            [[str(index)] for index in range(MAX_SEARCH_BATCH_SIZE + 1)],
            input_adm=adm,
            place_type_hint=None,
            limit=5,
        )

    try:
        asyncio.run(run())
    except ValueError as exc:
        assert "limited to 10" in str(exc)
    else:
        raise AssertionError("Expected batch-size validation")
