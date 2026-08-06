from __future__ import annotations

import pytest

from app.integrations.search.google_playwright import _decode_results


def test_decode_google_playwright_results() -> None:
    results = _decode_results(
        '{"results":[{"title":"Official","uri":"https://example.test/tickets",'
        '"snippet":"70.000 VND"}]}'
    )

    assert results[0]["uri"] == "https://example.test/tickets"


def test_decode_google_playwright_rejects_invalid_payload() -> None:
    with pytest.raises(RuntimeError, match="invalid_payload"):
        _decode_results('{"items":[]}')
