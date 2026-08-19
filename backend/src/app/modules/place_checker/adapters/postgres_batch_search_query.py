"""Batch wrapper for the existing PlaceChecker candidate search SQL."""

from __future__ import annotations

import re

from app.modules.place_checker.adapters.postgres_search_query import PLACE_SEARCH_SQL


_BATCH_PARAMETER = {
    1: "input.query",
    2: "$2",
    3: "$3",
    4: "$4",
    5: "input.anchor_place_id",
    6: "$6",
}


def _batch_body() -> str:
    return re.sub(
        r"\$(\d+)",
        lambda match: _BATCH_PARAMETER[int(match.group(1))],
        PLACE_SEARCH_SQL.strip(),
    )


PLACE_BATCH_SEARCH_SQL = f"""
SELECT input.ordinality - 1 AS batch_index, result.*
FROM unnest($1::text[], $5::text[])
     WITH ORDINALITY AS input(query, anchor_place_id, ordinality)
CROSS JOIN LATERAL (
{_batch_body()}
) AS result
ORDER BY input.ordinality
"""
