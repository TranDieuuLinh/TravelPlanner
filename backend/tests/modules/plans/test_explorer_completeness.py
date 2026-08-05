from app.modules.plans.explorer.explorer_service import (
    apply_raw_prompt_completeness,
)
from app.modules.plans.explorer.schema import (
    ExplorerContextResponse,
    FullExploreRequest,
    IntakeInputCompleteness,
)


def _explorer(
    *,
    destination: str = "Hà Nội",
    assumptions: list[str] | None = None,
) -> ExplorerContextResponse:
    return ExplorerContextResponse.model_validate(
        {
            "tripIntent": {
                "destination": destination,
                "timing": {"days": 3},
                "travelParty": {"type": "solo", "adults": 1},
                "clarifyingQuestions": ["Model-generated question"],
            },
            "assumptions": assumptions or [],
            "missingInfoQuestions": ["Model-generated question"],
        }
    )


def test_vague_raw_prompt_records_missing_fields_without_questions() -> None:
    result = apply_raw_prompt_completeness(
        FullExploreRequest(
            rawRequest="Tôi muốn đi du lịch",
            destination="",
        ),
        _explorer(
            destination="Đà Lạt",
            assumptions=["Assume Đà Lạt is the destination"],
        ),
    )

    assert result.mode == "vague"
    assert result.input_completeness is IntakeInputCompleteness.vague
    assert [item.field for item in result.missing_fields] == [
        "destination",
        "days",
        "budget",
    ]
    assert all(not item.was_provided for item in result.missing_fields)
    assert all(item.inferred_source is None for item in result.missing_fields)
    assert result.missing_info_questions == []
    assert result.intent.clarifying_questions == []
    assert result.intent.destination == ""
    assert result.assumptions == []
    assert result.trace == {"inputSource": "raw_prompt"}


def test_destination_only_raw_prompt_is_partial() -> None:
    result = apply_raw_prompt_completeness(
        FullExploreRequest(
            rawRequest="Tôi muốn khám phá Hội An",
            destination="Hội An",
        ),
        _explorer(destination="Hội An"),
    )

    assert result.mode == "partial"
    assert result.input_completeness is IntakeInputCompleteness.partial
    assert [item.field for item in result.missing_fields] == [
        "days",
        "budget",
    ]


def test_destination_normalized_from_raw_prompt_is_partial() -> None:
    result = apply_raw_prompt_completeness(
        FullExploreRequest(rawRequest="Khám phá Paris"),
        _explorer(destination="Paris"),
    )

    assert result.mode == "partial"
    assert [item.field for item in result.missing_fields] == [
        "days",
        "budget",
    ]


def test_raw_prompt_with_core_fields_is_complete() -> None:
    result = apply_raw_prompt_completeness(
        FullExploreRequest(
            rawRequest="Hội An 3 ngày, ngân sách tiết kiệm",
            destination="Hội An",
            tripSpec={"days": 3, "budget": {"level": "low"}},
        ),
        _explorer(destination="Hội An"),
    )

    assert result.mode == "confirmed"
    assert result.input_completeness is IntakeInputCompleteness.complete
    assert result.missing_fields == []


def test_reference_input_retains_existing_explorer_behavior() -> None:
    explorer = _explorer()
    result = apply_raw_prompt_completeness(
        FullExploreRequest(
            rawRequest="Tạo lịch trình từ URL",
            destination="Hà Nội",
            urls=["https://example.com/reel"],
        ),
        explorer,
    )

    assert result is explorer
    assert result.mode == "confirmed"
    assert result.input_completeness is IntakeInputCompleteness.complete
    assert result.missing_info_questions == ["Model-generated question"]


def test_completeness_metadata_uses_api_aliases() -> None:
    payload = apply_raw_prompt_completeness(
        FullExploreRequest(rawRequest="Đi du lịch đi"),
        _explorer(),
    ).model_dump(mode="json", by_alias=True)

    assert payload["inputCompleteness"] == "vague"
    assert payload["missingFields"][0] == {
        "field": "destination",
        "wasProvided": False,
        "inferredSource": None,
    }
