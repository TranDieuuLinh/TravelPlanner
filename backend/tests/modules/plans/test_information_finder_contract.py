from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.modules.plans.information_finder import (
    InformationCandidate,
    InformationQuery,
    InformationResult,
)


def candidate(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "candidateId": "candidate-1",
        "placeId": "place-1",
        "source": "knowledge_graph",
        "sourceRefs": ["claim-1"],
        "latitude": 21.0285,
        "longitude": 105.8542,
        "confidence": 0.92,
        "isVerified": True,
        "fetchedAt": "2026-08-06T10:00:00Z",
    }
    value.update(overrides)
    return value


def test_valid_verified_candidate_and_camel_case_serialization() -> None:
    item = InformationCandidate.model_validate(candidate())

    assert item.candidate_id == "candidate-1"
    assert item.model_dump(by_alias=True)["candidateId"] == "candidate-1"
    assert "isVerified" in item.model_dump(by_alias=True)


def test_provisional_candidate_can_use_import_identity_without_place_id() -> None:
    item = InformationCandidate.model_validate(
        candidate(
            placeId=None,
            source="explorer_import",
            sourceImportNodeId=7,
            isVerified=False,
        )
    )

    assert item.place_id is None
    assert item.source_import_node_id == 7
    assert item.is_verified is False


@pytest.mark.parametrize(
    "payload",
    [
        {"placeId": None, "sourceImportNodeId": None, "candidateEntityIds": []},
        {"confidence": 1.1},
        {"latitude": 91},
        {"longitude": -181},
        {"latitude": 21.0, "longitude": None},
        {"candidateId": ""},
    ],
)
def test_invalid_candidate_values_are_rejected(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InformationCandidate.model_validate(candidate(**payload))


@pytest.mark.parametrize("top_k", [0, 11])
def test_query_rejects_invalid_top_k(top_k: int) -> None:
    with pytest.raises(ValidationError):
        InformationQuery.model_validate({"query": "coffee", "topK": top_k})


def test_result_uses_camel_case_and_rejects_raw_provider_payload() -> None:
    result = InformationResult.model_validate(
        {
            "kind": "candidates",
            "message": "Choose a place",
            "candidates": [candidate()],
            "needsUserChoice": True,
            "warnings": [],
        }
    )

    dumped = result.model_dump(by_alias=True)
    assert dumped["needsUserChoice"] is True
    assert "rawPayload" not in dumped

    with pytest.raises(ValidationError):
        InformationCandidate.model_validate(candidate(rawPayload={"provider": "raw"}))


def test_datetime_is_parsed() -> None:
    item = InformationCandidate.model_validate(candidate())
    assert item.fetched_at == datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)
