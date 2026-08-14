import asyncio
from types import SimpleNamespace

from app.modules.conversation_memory.contract import (
    FactProvenance,
    MemoryFact,
    WorkingMemoryState,
)
from app.modules.explorer.contract import ExplorerOutput
from app.orchestration.memory_projection import merge_memory_places
from app.orchestration.nodes import RootNodes


def memory_with_places() -> WorkingMemoryState:
    return WorkingMemoryState(
        chat_id="chat-phase04",
        user_id=1,
        destination="Hà Nội",
        mentioned_places=["Hồ Tây", "Lăng Bác"],
        selected_places=[],
        active_facts=[
            MemoryFact(
                fact_id="fact-ho-tay",
                fact_type="place_candidate",
                key="place_candidate",
                value="Hồ Tây",
                provenance=FactProvenance(
                    source_turn=1,
                    source_excerpt="https://example.test/hanoi",
                    source_message_id="m1",
                    extracted_by="rule_based_v1",
                    confidence=0.9,
                    source_url="https://example.test/hanoi",
                ),
            )
        ],
    )


def explorer_output() -> ExplorerOutput:
    return ExplorerOutput.model_validate(
        {
            "status": "ready",
            "intakeId": "intake-phase04",
            "input_ADM": "Hà Nội",
            "days": 3,
        }
    )


def test_memory_places_are_appended_without_replacing_explorer_evidence():
    existing = merge_memory_places(
        [
            {
                "name": "Phở Lý Quốc Sư",
                "confidence": 1.0,
                "source_places": [
                    {
                        "origin": "url",
                        "evidence_type": "url_metadata",
                        "source_url": "https://example.test/list",
                        "evidence": "URL mention",
                    }
                ],
            }
        ],
        memory_with_places(),
    )

    assert [place.name for place in existing] == [
        "Phở Lý Quốc Sư",
        "Hồ Tây",
        "Lăng Bác",
    ]
    ho_tay = existing[1]
    assert ho_tay.source_places[0].origin == "url"
    assert ho_tay.source_places[0].source_url == "https://example.test/hanoi"


def test_information_finder_receives_compact_memory_context():
    nodes = RootNodes()
    calls = []

    class InformationGraph:
        async def ainvoke(self, payload):
            calls.append(payload)
            return {
                "output": SimpleNamespace(answer="ok", warnings=[]),
            }

    nodes.information_finder = InformationGraph()
    asyncio.run(
        nodes.run_information_finder(
            {
                "message": "có gì chơi?",
                "conversation_memory": memory_with_places(),
                "resolved_references": [],
                "warnings": [],
            }
        )
    )

    query = calls[0]["query"]
    assert query.startswith("có gì chơi?")
    assert "điểm đến: Hà Nội" in query
    assert "Hồ Tây" not in query


def test_place_checker_fallback_receives_memory_candidates():
    nodes = RootNodes()
    calls = []

    class PlaceGraph:
        async def ainvoke(self, payload):
            calls.append(payload)
            return {"output": SimpleNamespace(warnings=[])}

    nodes.place_checker = PlaceGraph()
    asyncio.run(
        nodes.run_place_checker(
            {
                "explorer_output": explorer_output(),
                "conversation_memory": memory_with_places(),
                "warnings": [],
            }
        )
    )

    assert [place.name for place in calls[0]["places"]] == ["Hồ Tây", "Lăng Bác"]
