"""Unit and projection tests for memory candidate provenance and truthful blocked explanations.

Verifies:
1. AC1: Assistant answer mentioning out-of-destination places (e.g. Vịnh Hạ Long) is system/optional.
2. AC2: Direct user place remains origin=input; user URL remains origin=url.
3. AC2 (Assistant URL): Assistant citation URL stays origin=system, NOT origin=url.
4. AC3: Current-turn resolved_references promote assistant suggestions to origin=input.
5. AC3 (Stale Reference): Stale persisted active_references from earlier turns do NOT promote suggestions.
6. AC4: Blocked PlaceChecker response contains a truthful reason matching the actual condition.
7. AC5: Stale legacy memory mentioned_places without facts is classified safely as system.
"""

import unittest
from types import SimpleNamespace

from app.modules.conversation_memory.contract import (
    FactProvenance,
    MemoryFact,
    MemoryReference,
    WorkingMemoryState,
)
from app.modules.explorer.public import (
    ExplorerPlace,
    PlaceSource,
)
from app.modules.place_checker.contract import (
    AdmResolution,
    AdmResolutionStatus,
    PlaceCandidateInput,
)
from app.modules.place_checker.enums import (
    SourceTier,
)
from app.orchestration.memory_projection import (
    build_blocked_clarification,
    merge_memory_places,
)


class TestMemoryContaminationProjection(unittest.TestCase):
    def setUp(self) -> None:
        self.user_id = 1

    def test_ac1_assistant_mention_does_not_become_mandatory(self) -> None:
        """AC1: Assistant mentioning Vinh Ha Long produces origin=system / SourceTier.system_suggested."""
        working_memory = WorkingMemoryState(
            chat_id="chat-ac1",
            user_id=self.user_id,
            destination="Hà Nội",
            duration_days=3,
            mentioned_places=["Hồ Gươm", "Vịnh Hạ Long"],
            selected_places=[],
            active_facts=[
                MemoryFact(
                    fact_id="fact-vhl",
                    fact_type="place_candidate",
                    key="place_candidate",
                    value="Vịnh Hạ Long",
                    provenance=FactProvenance(
                        source_turn=1,
                        source_excerpt="Bạn cũng có thể đi Vịnh Hạ Long",
                        extracted_by="information_finder_v1",
                        source_message_id="assistant:chat-ac1:1",
                        confidence=0.7,
                    ),
                    confirmed_by_user=False,
                ),
            ],
        )

        merged = merge_memory_places([], working_memory)
        merged_by_name = {p.name: p for p in merged}

        self.assertIn("Vịnh Hạ Long", merged_by_name)
        vhl = merged_by_name["Vịnh Hạ Long"]
        self.assertEqual(vhl.source_places[0].origin, "system")

        candidate = PlaceCandidateInput.model_validate(
            {
                "name": vhl.name,
                "confidence": vhl.confidence,
                "sourcePlaces": [
                    {
                        "origin": vhl.source_places[0].origin,
                        "evidenceType": vhl.source_places[0].evidence_type,
                        "evidence": vhl.source_places[0].evidence,
                    }
                ],
            }
        )
        self.assertEqual(candidate.source_tier, SourceTier.system_suggested)

    def test_ac2_direct_user_and_user_url_places_retain_origin(self) -> None:
        """AC2: User selection is origin=input and user-provided URL is origin=url."""
        working_memory = WorkingMemoryState(
            chat_id="chat-ac2",
            user_id=self.user_id,
            destination="Đà Nẵng",
            duration_days=2,
            selected_places=["Bà Nà Hills"],
            mentioned_places=["Bà Nà Hills", "Cầu Rồng"],
            active_facts=[
                MemoryFact(
                    fact_id="fact-bana",
                    fact_type="place_candidate",
                    key="place_candidate",
                    value="Bà Nà Hills",
                    provenance=FactProvenance(
                        source_turn=1,
                        source_excerpt="Tôi muốn đi Bà Nà Hills",
                        extracted_by="rule_based_v1",
                        source_message_id="user:chat-ac2:1",
                        confidence=0.95,
                    ),
                    confirmed_by_user=True,
                ),
                MemoryFact(
                    fact_id="fact-caurong",
                    fact_type="place_candidate",
                    key="place_candidate",
                    value="Cầu Rồng",
                    provenance=FactProvenance(
                        source_turn=1,
                        source_excerpt="Cầu Rồng trong bài viết",
                        extracted_by="url_extractor",
                        source_message_id="user:chat-ac2:1",
                        confidence=0.9,
                        source_url="https://example.test/danang-review",
                    ),
                    confirmed_by_user=False,
                ),
            ],
        )

        merged = merge_memory_places([], working_memory)
        merged_by_name = {p.name: p for p in merged}

        self.assertEqual(merged_by_name["Bà Nà Hills"].source_places[0].origin, "input")
        self.assertEqual(merged_by_name["Cầu Rồng"].source_places[0].origin, "url")
        self.assertEqual(
            merged_by_name["Cầu Rồng"].source_places[0].source_url,
            "https://example.test/danang-review",
        )

    def test_ac2_assistant_citation_url_remains_system_origin(self) -> None:
        """AC2: An assistant citation URL must remain origin=system and not become a protected URL."""
        working_memory = WorkingMemoryState(
            chat_id="chat-ac2-citation",
            user_id=self.user_id,
            destination="Hà Nội",
            mentioned_places=["Vịnh Hạ Long"],
            selected_places=[],
            active_facts=[
                MemoryFact(
                    fact_id="fact-citation",
                    fact_type="place_candidate",
                    key="place_candidate",
                    value="Vịnh Hạ Long",
                    provenance=FactProvenance(
                        source_turn=1,
                        source_excerpt="Vịnh Hạ Long từ nguồn trích dẫn",
                        extracted_by="information_finder_v1",
                        source_message_id="assistant:chat-ac2:1",
                        confidence=0.7,
                        source_url="https://example.test/assistant-citation",
                    ),
                    confirmed_by_user=False,
                )
            ],
        )

        merged = merge_memory_places([], working_memory)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].source_places[0].origin, "system")
        self.assertIsNone(merged[0].source_places[0].source_url)

    def test_ac3_explicit_current_turn_reference_promotes_assistant_suggestions(self) -> None:
        """AC3: When the current turn explicitly references a place, it is promoted to origin=input."""
        working_memory = WorkingMemoryState(
            chat_id="chat-ac3",
            user_id=self.user_id,
            destination="Hà Nội",
            mentioned_places=["Văn Miếu", "Hồ Tây"],
            selected_places=[],
            active_facts=[
                MemoryFact(
                    fact_id="fact-vm",
                    fact_type="place_candidate",
                    key="place_candidate",
                    value="Văn Miếu",
                    provenance=FactProvenance(
                        source_turn=1,
                        source_excerpt="Gợi ý Văn Miếu",
                        extracted_by="information_finder_v1",
                        source_message_id="assistant:chat-ac3:1",
                        confidence=0.7,
                    ),
                    confirmed_by_user=False,
                ),
            ],
        )
        current_turn_refs = [
            MemoryReference(
                reference_id="ref-turn2",
                phrase="những chỗ vừa kể",
                reference_type="deictic",
                resolved_entity="Văn Miếu",
                target_fact_ids=["fact-vm"],
            )
        ]

        merged = merge_memory_places(
            [], working_memory, resolved_references=current_turn_refs
        )
        merged_by_name = {p.name: p for p in merged}

        self.assertEqual(merged_by_name["Văn Miếu"].source_places[0].origin, "input")

    def test_ac3_stale_persisted_reference_does_not_promote_assistant_suggestion(self) -> None:
        """AC3: Stale active_references in memory must NOT promote suggestions when current turn is empty."""
        working_memory = WorkingMemoryState(
            chat_id="chat-ac3-stale",
            user_id=self.user_id,
            destination="Hà Nội",
            mentioned_places=["Vịnh Hạ Long"],
            selected_places=[],
            active_facts=[
                MemoryFact(
                    fact_id="fact-vhl-old",
                    fact_type="place_candidate",
                    key="place_candidate",
                    value="Vịnh Hạ Long",
                    provenance=FactProvenance(
                        source_turn=1,
                        source_excerpt="Gợi ý Vịnh Hạ Long",
                        extracted_by="information_finder_v1",
                        source_message_id="assistant:chat-ac3:1",
                        confidence=0.7,
                    ),
                    confirmed_by_user=False,
                ),
            ],
            active_references=[
                MemoryReference(
                    reference_id="ref-old-turn1",
                    phrase="những chỗ vừa kể",
                    reference_type="deictic",
                    resolved_entity="Vịnh Hạ Long",
                    target_fact_ids=["fact-vhl-old"],
                )
            ],
        )

        # Current turn has no reference (resolved_references=None or empty list)
        merged = merge_memory_places([], working_memory, resolved_references=[])
        merged_by_name = {p.name: p for p in merged}

        # Stale reference did NOT promote Vịnh Hạ Long to input
        self.assertEqual(merged_by_name["Vịnh Hạ Long"].source_places[0].origin, "system")

    def test_ac4_truthful_blocked_place_checker_response_reasons(self) -> None:
        """AC4: Blocked PlaceChecker responses distinguish destination, mandatory places, and pool issues."""
        # Destination resolution failure
        dest_output = SimpleNamespace(
            trip_context=SimpleNamespace(
                destination=AdmResolution(
                    input_name="Atlantis",
                    status=AdmResolutionStatus.unresolved,
                )
            ),
            checked_places=[],
            unresolved_entities=[],
            warnings=[],
        )
        q_dest, resp_dest = build_blocked_clarification(dest_output)
        self.assertIn("Atlantis", q_dest)
        self.assertIn("Atlantis", resp_dest)

        # Mandatory place blocked
        place_output = SimpleNamespace(
            trip_context=SimpleNamespace(
                destination=AdmResolution(
                    input_name="Hà Nội",
                    status=AdmResolutionStatus.resolved,
                    adm_id="adm1_hn",
                    canonical_name="Hà Nội",
                    country_code="VN",
                    region_key="vn,hn",
                )
            ),
            checked_places=[
                SimpleNamespace(
                    mandatory=True,
                    canonical_name="Bảo Tàng Không Tồn Tại",
                    original_names=["Bảo Tàng Không Tồn Tại"],
                    evaluation=SimpleNamespace(state="blocked"),
                )
            ],
            unresolved_entities=[],
            warnings=[],
        )
        q_place, resp_place = build_blocked_clarification(place_output)
        self.assertIn("Bảo Tàng Không Tồn Tại", q_place)
        self.assertIn("Bảo Tàng Không Tồn Tại", resp_place)

        # Pool / candidate warning
        pool_output = SimpleNamespace(
            trip_context=SimpleNamespace(
                destination=AdmResolution(
                    input_name="Hà Nội",
                    status=AdmResolutionStatus.resolved,
                    adm_id="adm1_hn",
                    canonical_name="Hà Nội",
                    country_code="VN",
                    region_key="vn,hn",
                )
            ),
            checked_places=[],
            unresolved_entities=[],
            warnings=["Không đủ địa điểm tham quan để lên lịch."],
        )
        q_pool, resp_pool = build_blocked_clarification(pool_output)
        self.assertIn("Không đủ địa điểm tham quan", q_pool)
        self.assertIn("Không đủ địa điểm tham quan", resp_pool)

    def test_ac5_stale_legacy_mentioned_places_safe_system_classification(self) -> None:
        """AC5: Old memory rows with only mentioned_places are classified safely as system."""
        legacy_memory = WorkingMemoryState(
            chat_id="legacy-chat",
            user_id=self.user_id,
            destination="Hà Nội",
            mentioned_places=["Vịnh Hạ Long", "Ninh Bình"],
            selected_places=[],
            active_facts=[],
        )

        merged = merge_memory_places([], legacy_memory)
        for place in merged:
            self.assertEqual(place.source_places[0].origin, "system")
            self.assertEqual(place.confidence, 0.7)


if __name__ == "__main__":
    unittest.main()
