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
    EntitySummary,
    EdgeEvidence,
)
from app.modules.plans.trip_theme_planner.graph_candidate_projection import (
    build_graph_candidate_catalog,
)

place_hk = EntitySummary(id="place-hk", name="Hoan Kiem Lake", type="Place", status="verified")
place_tl = EntitySummary(id="place-tl", name="Temple of Literature", type="Place", status="verified")
activity = EntitySummary(id="act-tour", name="Temple Guided Tour", type="Tour", status="verified")

claim_1 = GraphEvidenceClaim(
    claimId="claim-1",
    subject=place_hk,
    predicate="SPECIAL_EXPERIENCE",
    object=place_hk,
    path=["SPECIAL_EXPERIENCE"],
    anchorPlace=place_hk,
    evidence=[EdgeEvidence(source="seed://hanoi")],
    trust=TrustLevel.VERIFIED,
)
claim_2 = GraphEvidenceClaim(
    claimId="claim-2",
    subject=place_tl,
    predicate="OFFERS_ACTIVITY",
    object=activity,
    path=["OFFERS_ACTIVITY"],
    anchorPlace=place_tl,
    activity=activity,
    evidence=[EdgeEvidence(source="seed://hanoi")],
    trust=TrustLevel.VERIFIED,
)

bundle = TripResearchBundle(
    scope=ScopeResolveOutput(),
    eligibleExperiences=[
        RankedExperience(claim=claim_1, fit=FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=3), rank=1),
        RankedExperience(claim=claim_2, fit=FitResult(status=CheckStatus.SUPPORTED, hasHardConflict=False, dimensionCount=3), rank=2),
    ],
    graphSnapshot=GraphSnapshot(timestamp="2026-08-05T00:00:00Z"),
)

catalog = build_graph_candidate_catalog(bundle)
print(json.dumps([c.model_dump(by_alias=True) for c in catalog.candidates], indent=2))