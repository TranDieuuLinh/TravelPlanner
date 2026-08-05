from __future__ import annotations

import json

from app.modules.knowledge_graph.research import (
    CheckStatus,
    FitResult,
    GraphEvidenceClaim,
    GraphSnapshot,
    RankedExperience,
    ScopeResolveOutput,
    TripResearchBundle,
    TrustLevel,
)
from app.modules.knowledge_graph.research.schema import EdgeEvidence, EntitySummary
from scripts import trip_theme_cli


class _Session:
    def close(self) -> None:
        pass


class _Orchestrator:
    def research(self, input_data) -> TripResearchBundle:
        activity = EntitySummary(
            id="activity-walk",
            name="Đi dạo",
            type="Activity",
            status="verified",
        )
        claim = GraphEvidenceClaim(
            claimId="claim-walk",
            subject=EntitySummary(
                id="area-hanoi",
                name="Hà Nội",
                type="Area",
                status="verified",
            ),
            predicate="SPECIAL_EXPERIENCE",
            object=activity,
            path=["area-hanoi", "SPECIAL_EXPERIENCE", "activity-walk"],
            activity=activity,
            evidence=[EdgeEvidence(source="https://example.com/walk")],
            trust=TrustLevel.SOURCE_BACKED,
        )
        return TripResearchBundle(
            scope=ScopeResolveOutput(),
            eligibleExperiences=[
                RankedExperience(
                    claim=claim,
                    fit=FitResult(
                        status=CheckStatus.SUPPORTED,
                        hasHardConflict=False,
                        dimensionCount=1,
                    ),
                    rank=1,
                )
            ],
            graphSnapshot=GraphSnapshot(timestamp="2026-08-05T00:00:00Z"),
        )


def test_trip_theme_research_context_prints_bounded_catalog_without_llm(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(trip_theme_cli, "SessionLocal", lambda: _Session())
    monkeypatch.setattr(
        trip_theme_cli,
        "ScopeResolutionRepository",
        lambda session: object(),
    )
    monkeypatch.setattr(
        trip_theme_cli,
        "GraphResearchOrchestrator",
        lambda scope_repo, discovery_repo: _Orchestrator(),
    )
    args = trip_theme_cli.build_parser().parse_args(
        [
            "research-context",
            "--destination",
            "Hà Nội",
            "--interest",
            "culture",
        ]
    )

    assert trip_theme_cli.research_context(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["graphCandidateCatalog"]["candidates"][0]["activityId"] == (
        "activity-walk"
    )
    assert "llm" not in json.dumps(payload).casefold()
