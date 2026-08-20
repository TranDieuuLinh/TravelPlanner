import pytest

from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.contract import (
    ExplorerBudget,
    ExplorerOutput,
    ExplorerPeople,
)
from app.orchestration.explorer_handoff import (
    ExplorerHandoffError,
    ExplorerHandoffProjector,
)


def projector(tmp_path) -> ExplorerHandoffProjector:
    path = tmp_path / "tags-auto.yml"
    path.write_text(
        "Văn hóa: [culture, văn hóa]\n"
        "đồ uống: [coffee, cà phê]\n"
        "nightlife: [nightlife, bar]\n",
        encoding="utf-8",
    )
    return ExplorerHandoffProjector(YamlTagCatalog(path))


def test_current_turn_wins_and_memory_tags_are_normalized(tmp_path) -> None:
    output = ExplorerOutput(
        status="ready",
        intakeId="intake-current",
        input_ADM="Hanoi",
        days=2,
        budget=ExplorerBudget(
            level="high", targetAmount=3_000_000, source="raw_prompt"
        ),
        people=ExplorerPeople(adults=3),
        shortPreferences=["Văn hóa"],
    )

    handoff = projector(tmp_path).project(
        output,
        raw_prompt="Đi Hanoi 2 ngày cho 3 người, budget 3 triệu",
        memory={
            "destination": "Huế",
            "durationDays": 7,
            "travelers": 5,
            "budget": "low",
            "preferences": ["culture", "unknown"],
            "avoids": ["nightlife", "unknown"],
        },
    )

    assert handoff.place_checker_input.input_adm == "Hanoi"
    assert handoff.place_checker_input.days == 2
    assert handoff.place_checker_input.people.adults == 3
    assert handoff.place_checker_input.budget.level == "high"
    assert handoff.place_checker_input.budget.amount_per_person == 1_000_000
    assert handoff.place_checker_input.short_preferences == ["Văn hóa"]
    assert handoff.place_checker_input.short_avoids == ["nightlife"]


def test_memory_fills_missing_trip_context_before_validation(tmp_path) -> None:
    output = ExplorerOutput(
        status="clarification",
        intakeId="intake-follow-up",
        input_ADM=None,
        clarificationQuestion="Bạn muốn đi tỉnh hoặc thành phố nào?",
    )

    handoff = projector(tmp_path).project(
        output,
        raw_prompt="Lên plan các điểm bên trên",
        memory={
            "destination": "Huế",
            "durationDays": 4,
            "preferences": ["coffee"],
        },
    )

    assert handoff.explorer_output.status == "ready"
    assert handoff.place_checker_input.input_adm == "Huế"
    assert handoff.place_checker_input.days == 4
    assert handoff.place_checker_input.short_preferences == ["đồ uống"]


def test_current_source_budget_wins_over_memory(tmp_path) -> None:
    output = ExplorerOutput(
        status="ready",
        intakeId="intake-source-budget",
        input_ADM="Đà Nẵng",
        budget=ExplorerBudget(level="high", source="image"),
    )

    handoff = projector(tmp_path).project(
        output,
        raw_prompt="Lên lịch theo ảnh này",
        memory={"budget": "low"},
        has_source_input=True,
    )

    assert handoff.place_checker_input.budget.level == "high"
    assert handoff.place_checker_input.budget.amount_per_person is None


def test_handoff_is_compact_and_budget_is_total_per_person(tmp_path) -> None:
    output = ExplorerOutput(
        status="ready",
        intakeId="intake-compact",
        input_ADM="Hà Nội",
        days=3,
        budget=ExplorerBudget(level="low", source="default"),
        people=ExplorerPeople(adults=2),
    )

    handoff = projector(tmp_path).project(output, raw_prompt="Đi Hà Nội")
    payload = handoff.place_checker_input.model_dump(by_alias=True)

    assert payload["budget"] == {
        "amountPerPerson": 1_923_284,
        "currency": "VND",
        "level": "low",
    }
    assert payload["places"] == []
    assert payload["specialNotes"] == []
    assert "validationIssues" not in payload


def test_missing_destination_becomes_structured_handoff_blocker(tmp_path) -> None:
    output = ExplorerOutput(
        status="clarification",
        intakeId="intake-missing",
        input_ADM=None,
        clarificationQuestion="Bạn muốn đi tỉnh hoặc thành phố nào?",
    )

    with pytest.raises(ExplorerHandoffError) as caught:
        projector(tmp_path).project(output, raw_prompt="Lên kế hoạch")

    assert caught.value.code == "PLACE_CHECKER_DESTINATION_REQUIRED"
    assert caught.value.status == "blocked"
