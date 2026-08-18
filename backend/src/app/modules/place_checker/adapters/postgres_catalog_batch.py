"""Bounded multi-query read path for the PlaceChecker PostgreSQL catalog."""

from __future__ import annotations

from collections import defaultdict

from app.modules.place_checker.adapters.postgres_batch_search_query import (
    PLACE_BATCH_SEARCH_SQL,
)
from app.modules.place_checker.adapters.postgres_retry import fetch_catalog_rows
from app.shared.tools.search_places import AdministrativeArea, PlaceProviderCandidate
from app.shared.tools.search_places.normalization import normalize_text


MAX_SEARCH_BATCH_SIZE = 10


class PostgresCatalogBatchMixin:
    async def search_many(
        self,
        lookup_name_batches: list[list[str]],
        *,
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
        limit: int,
        anchor_place_id: str | None = None,
        anchor_place_ids: list[str | None] | None = None,
    ) -> list[list[PlaceProviderCandidate]]:
        if not lookup_name_batches:
            return []
        if len(lookup_name_batches) > MAX_SEARCH_BATCH_SIZE:
            raise ValueError("Place search batches are limited to 10 queries")
        anchors = anchor_place_ids or [anchor_place_id] * len(lookup_name_batches)
        if len(anchors) != len(lookup_name_batches):
            raise ValueError("Each batch query must have one anchor value")

        queries = [
            next(
                (
                    normalized
                    for name in names
                    if (normalized := normalize_text(name))
                ),
                "",
            )
            for names in lookup_name_batches
        ]
        requested_types = sorted(self._types_for_hint(place_type_hint))
        fetch_limit = min(60, max(1, limit))
        rows = await fetch_catalog_rows(
            self,
            PLACE_BATCH_SEARCH_SQL,
            queries,
            input_adm.adm_id,
            requested_types,
            fetch_limit,
            anchors,
            0.30,
        )
        grouped = defaultdict(list)
        for row in rows:
            grouped[int(row["batch_index"])].append(
                self._candidate(row, input_adm)
            )
        return [grouped[index] for index in range(len(queries))]
