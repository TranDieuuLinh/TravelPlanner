"""GraphResearchOrchestrator - orchestrates trip research tools.

This module provides the orchestration layer that coordinates the three research tools:
- kg_resolve_scope: resolves geographic scope
- kg_discover_experiences: discovers special experiences
- kg_evaluate_experience_fit: evaluates fit for candidates

The orchestrator does not re-implement tool logic; it calls their public interfaces.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Protocol

from app.modules.knowledge_graph.research import (
    CheckStatus,
    ConflictedExperience,
    EdgeEvidence,
    ExperienceDiscoveryInput,
    ExperienceFitInput,
    FitResult,
    GraphEvidenceBundle,
    GraphEvidenceClaim,
    GraphSnapshot,
    RankedExperience,
    ResearchTrace,
    ScopeResolveInput,
    ScopeResolveOutput,
    TrustLevel,
    TripResearchBundle,
    TripResearchInput,
)
from app.modules.knowledge_graph.research.experience_fit_tool import (
    HARD_CONSTRAINTS,
    kg_evaluate_experience_fit,
)
from app.modules.knowledge_graph.research.experience_tool import (
    build_special_experience_catalog,
    kg_discover_experiences,
)
from app.modules.knowledge_graph.research.schema import (
    RecommendationPriority,
)
from app.modules.knowledge_graph.research.scope_tool import kg_resolve_scope

if TYPE_CHECKING:
    from app.modules.knowledge_graph.research.repository import (
        KnowledgeGraphResearchRepository,
        ScopeResolutionRepository,
    )


class GraphScopeError(Exception):
    """Raised when scope resolution fails."""

    CODE = "GRAPH_SCOPE_NOT_FOUND"

    def __init__(self, destination: str) -> None:
        self.destination = destination
        super().__init__(
            f"GRAPH_SCOPE_NOT_FOUND: Cannot resolve '{destination}' to a known Area"
        )


# ---------------------------------------------------------------------------
# Trust / Priority ordering helpers
# ---------------------------------------------------------------------------

_TRUST_ORDER: dict[TrustLevel, int] = {
    TrustLevel.VERIFIED: 0,
    TrustLevel.SOURCE_BACKED: 1,
    TrustLevel.INFERRED: 2,
}

_PRIORITY_ORDER: dict[str, int] = {
    "must": 0,
    "recommended": 1,
    "optional": 2,
}


def _get_highest_priority(claim: GraphEvidenceClaim) -> str:
    """Get the highest (lowest numeric) priority from claim recommendations."""
    best = "optional"
    for rec in claim.recommendations:
        p = rec.priority.value
        if _PRIORITY_ORDER.get(p, 99) < _PRIORITY_ORDER.get(best, 99):
            best = p
    return best


def _has_hard_conflict(fit_status: CheckStatus, checks: list) -> tuple[bool, list[str]]:
    """Check if any hard constraint is conflicted."""
    conflict_reasons: list[str] = []
    has_hard = False

    for check in checks:
        if check.dimension in HARD_CONSTRAINTS:
            if check.status == CheckStatus.CONFLICTED:
                has_hard = True
                conflict_reasons.append(f"{check.dimension}: {check.reason}")

    return has_hard, conflict_reasons


# ---------------------------------------------------------------------------
# Diversity ranking helpers
# ---------------------------------------------------------------------------

_MAX_SAME_CATEGORY_RATIO = 0.6


def _apply_diversity_rerank(
    candidates: list[tuple[int, "CandidateScore"]],
    max_ratio: float = _MAX_SAME_CATEGORY_RATIO,
) -> list[tuple[int, "CandidateScore"]]:
    """Rerank candidates to prevent one category from dominating top results.

    Takes sorted candidates and redistributes them so that no single object.type
    occupies more than max_ratio of the top positions.
    """
    if len(candidates) <= 3:
        return candidates

    result: list[tuple[int, "CandidateScore"]] = []
    remaining = list(candidates)
    object_type_positions: dict[str, int] = {}

    while remaining:
        max_allowed = max(1, int(len(candidates) * max_ratio))

        placed = 0
        for i, candidate in enumerate(remaining):
            obj_type = candidate[1].object_type
            current_count = object_type_positions.get(obj_type, 0)

            if current_count < max_allowed:
                result.append(candidate)
                object_type_positions[obj_type] = current_count + 1
                remaining.pop(i)
                placed = 1
                break

        if placed == 0:
            result.extend(remaining)
            break

    return result


# ---------------------------------------------------------------------------
# Candidate scoring for ranking
# ---------------------------------------------------------------------------

class CandidateScore:
    """Pre-computed scoring components for a candidate."""

    __slots__ = (
        "claim",
        "fit",
        "trust_order",
        "priority_order",
        "is_user_selected",
        "is_source_place",
        "object_type",
        "claim_id",
    )

    def __init__(
        self,
        claim: GraphEvidenceClaim,
        fit: FitResult,
        user_selected_ids: set[str],
        source_place_ids: set[str],
    ) -> None:
        self.claim = claim
        self.fit = fit
        self.trust_order = _TRUST_ORDER.get(claim.trust, 99)
        self.priority_order = _PRIORITY_ORDER.get(_get_highest_priority(claim), 99)
        self.is_user_selected = claim.object.id in user_selected_ids
        self.is_source_place = claim.object.id in source_place_ids
        self.object_type = claim.object.type
        self.claim_id = claim.claimId

    def sort_key(self) -> tuple:
        """Deterministic sort key for ranking."""
        return (
            self.trust_order,
            self.priority_order,
            -int(self.is_user_selected),
            -int(self.is_source_place),
            self.claim.object.name.lower(),
            self.claim_id,
        )


# ---------------------------------------------------------------------------
# Repository protocol for testability
# ---------------------------------------------------------------------------

class RepositoryProtocol(Protocol):
    """Protocol defining the repository interface needed by the orchestrator."""

    def is_empty(self) -> bool:
        """Check if the knowledge graph is empty."""
        ...

    def resolve_area_by_name(self, destination: str) -> "KnowledgeEntity | None":
        """Resolve an Area by name."""
        ...

    def get_area_ref(
        self, entity: "KnowledgeEntity", depth: int
    ) -> "AreaRef":
        """Convert entity to AreaRef."""
        ...

    def traverse_part_of_ancestors(
        self, entity_id: str, max_depth: int
    ) -> list["AreaRef"]:
        """Traverse PART_OF ancestors."""
        ...

    def traverse_part_of_descendants(
        self, entity_id: str, max_depth: int, limit: int
    ) -> list["AreaRef"]:
        """Traverse PART_OF descendants."""
        ...

    def get_entities_by_ids(self, entity_ids: list[str]) -> dict[str, "KnowledgeEntity"]:
        """Batch fetch entities by IDs."""
        ...

    def get_all_properties_with_sources(
        self, entity_id: str
    ) -> list[tuple[str, str, str | None]]:
        """Get all properties with sources."""
        ...

    def get_entity_by_id(self, entity_id: str) -> "KnowledgeEntity | None":
        """Get entity by ID."""
        ...


# ---------------------------------------------------------------------------
# Batch fit evaluator
# ---------------------------------------------------------------------------

def _batch_evaluate_fit(
    repo: ScopeResolutionRepository,
    claims: list[GraphEvidenceClaim],
    input_data: TripResearchInput,
    destination: str,
) -> dict[str, FitResult]:
    """Evaluate fit for multiple claims in batch.

    Returns a dict mapping claimId -> FitResult.
    """
    results: dict[str, FitResult] = {}

    for claim in claims:
        # Activities are often graph nodes without their own LOCATED_IN edge.
        # Their anchor place is the geographic entity that PlaceSelector will
        # hydrate and schedule, so evaluate fit against that anchor when one
        # is available.
        entity_id = (
            claim.anchorPlace.id
            if claim.anchorPlace is not None
            else claim.object.id
        )

        fit_input = ExperienceFitInput(
            entityId=entity_id,
            destination=destination,
            days=input_data.days,
            partySize=input_data.partySize,
            startDate=input_data.startDate,
            endDate=input_data.endDate,
            budgetLevel=input_data.budget.level,
            budgetTargetAmount=input_data.budget.targetAmount,
            excludedPlaceTypes=input_data.excludedPlaceTypes,
            preferredTransportModes=input_data.preferredModes,
            avoidedTransportModes=input_data.avoidModes,
            userConstraints=input_data.constraints,
        )

        try:
            fit_output = kg_evaluate_experience_fit(repo, fit_input)
            has_hard, _ = _has_hard_conflict(fit_output.overallStatus, fit_output.checks)

            results[claim.claimId] = FitResult(
                status=fit_output.overallStatus,
                hasHardConflict=has_hard,
                dimensionCount=len(fit_output.checks),
            )
        except Exception:
            results[claim.claimId] = FitResult(
                status=CheckStatus.UNKNOWN,
                hasHardConflict=False,
                dimensionCount=0,
            )

    return results


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

class GraphResearchOrchestrator:
    """Orchestrates the trip research flow using the three KG research tools.

    Flow:
        TripResearchInput
        → kg_resolve_scope
        → kg_discover_experiences
        → batch kg_evaluate_experience_fit
        → deterministic rank/filter
        → TripResearchBundle

    The orchestrator calls the public interface of each tool and does not
    re-implement their logic.
    """

    def __init__(
        self,
        scope_repo: ScopeResolutionRepository,
        discovery_repo: KnowledgeGraphResearchRepository,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            scope_repo: Repository for scope resolution and fit evaluation.
            discovery_repo: Repository for experience discovery.
        """
        self.scope_repo = scope_repo
        self.discovery_repo = discovery_repo

    def research(self, input_data: TripResearchInput) -> TripResearchBundle:
        """Execute the trip research orchestration flow.

        Args:
            input_data: Trip research input parameters.

        Returns:
            TripResearchBundle with ranked experiences and metadata.

        Raises:
            GraphScopeError: If scope resolution fails.
        """
        warnings: list[str] = []
        trace = ResearchTrace()

        # ------------------------------------------------------------------
        # Step 1: Resolve scope
        # ------------------------------------------------------------------
        scope_input = ScopeResolveInput(
            destination=input_data.destination,
            selectedPlaceIds=input_data.selectedPlaceIds or None,
            maxDepth=4,
            resultLimit=100,
        )
        scope_output = kg_resolve_scope(self.scope_repo, scope_input)

        trace.scopeResultCount = len(scope_output.includedAreas)

        if scope_output.rootArea is None:
            raise GraphScopeError(input_data.destination)

        warnings.extend(scope_output.warnings)

        # ------------------------------------------------------------------
        # Step 2: Discover experiences
        # ------------------------------------------------------------------
        discovery_input = ExperienceDiscoveryInput(
            rootAreaId=scope_output.rootArea.id,
            interests=input_data.interests,
            selectedPlaceIds=input_data.selectedPlaceIds or None,
            limit=input_data.candidateLimit,
            includeInferred=input_data.includeInferred,
        )
        discovery_output = kg_discover_experiences(self.discovery_repo, discovery_input)

        trace.discoveredClaimCount = len(discovery_output.claims)
        warnings.extend(discovery_output.warnings)

        # If no experiences, return empty bundle
        if not discovery_output.claims:
            warnings.append("GRAPH_EXPERIENCE_COVERAGE_EMPTY: No experiences found in scope")
            return TripResearchBundle(
                scope=scope_output,
                eligibleExperiences=[],
                conflictedExperiences=[],
                unknowns=[],
                warnings=warnings,
                graphSnapshot=discovery_output.graphSnapshot,
                trace=trace,
                catalog=discovery_output.catalog,
            )

        # ------------------------------------------------------------------
        # Step 3: Evaluate fit for all candidates
        # ------------------------------------------------------------------
        all_claims = discovery_output.claims
        fit_results = _batch_evaluate_fit(
            self.scope_repo,
            all_claims,
            input_data,
            input_data.destination,
        )
        trace.evaluatedExperienceCount = len(all_claims)

        # ------------------------------------------------------------------
        # Step 4: Categorize and rank
        # ------------------------------------------------------------------
        user_selected_ids = set(input_data.selectedPlaceIds)
        source_place_ids: set[str] = set()
        for claim in all_claims:
            if claim.object.type in ("Place", "TravelPlace", "Cafe", "Restaurant",
                                    "Hotel", "Shop", "Attraction", "Entertainment"):
                source_place_ids.add(claim.object.id)

        eligible_candidates: list[CandidateScore] = []
        conflicted_candidates: list[tuple[CandidateScore, list[str]]] = []
        unknown_candidates: list[CandidateScore] = []

        for claim in all_claims:
            fit = fit_results.get(claim.claimId)
            if fit is None:
                fit = FitResult(
                    status=CheckStatus.UNKNOWN,
                    hasHardConflict=False,
                    dimensionCount=0,
                )

            score = CandidateScore(
                claim=claim,
                fit=fit,
                user_selected_ids=user_selected_ids,
                source_place_ids=source_place_ids,
            )

            if fit.status == CheckStatus.CONFLICTED or fit.hasHardConflict:
                _, reasons = _has_hard_conflict(fit.status, [])
                conflicted_candidates.append((score, reasons))
            elif fit.status == CheckStatus.UNKNOWN:
                unknown_candidates.append(score)
            else:
                eligible_candidates.append(score)

        # ------------------------------------------------------------------
        # Rank eligible candidates
        # ------------------------------------------------------------------
        eligible_sorted = sorted(
            [(i, c) for i, c in enumerate(eligible_candidates)],
            key=lambda x: x[1].sort_key(),
        )

        # Apply diversity reranking
        eligible_sorted = _apply_diversity_rerank(eligible_sorted)

        # Assign final ranks
        ranked_experiences: list[RankedExperience] = []
        catalog_claims: list[GraphEvidenceClaim] = []
        rank_reasons_map: dict[str, list[str]] = {}

        for rank, (idx, candidate) in enumerate(eligible_sorted, start=1):
            claim = candidate.claim

            reasons: list[str] = []
            reasons.append(candidate.claim.trust.value)
            if candidate.claim.recommendations:
                priorities = [r.priority.value for r in candidate.claim.recommendations]
                if "must" in priorities:
                    reasons.append("special_experience")
                elif "recommended" in priorities:
                    reasons.append("recommended_experience")

            if candidate.is_user_selected:
                reasons.append("user_selected_place")
            if candidate.is_source_place:
                reasons.append("source_place")

            rank_reasons_map[claim.claimId] = reasons

            ranked_experiences.append(RankedExperience(
                claim=claim,
                fit=candidate.fit,
                rank=rank,
                rankReasons=reasons,
            ))
            catalog_claims.append(claim)

        # Add unknown candidates at the end (they are eligible but with warnings)
        for rank_offset, candidate in enumerate(unknown_candidates):
            rank = len(ranked_experiences) + rank_offset + 1
            claim = candidate.claim
            warnings.append(
                f"UNKNOWN_FIT: Experience '{claim.object.name}' has unknown fit status"
            )

            reasons: list[str] = [candidate.claim.trust.value]
            if candidate.is_user_selected:
                reasons.append("user_selected_place")

            ranked_experiences.append(RankedExperience(
                claim=claim,
                fit=candidate.fit,
                rank=rank,
                rankReasons=reasons,
            ))

        # Build conflicted list
        conflicted_experiences: list[ConflictedExperience] = []
        for score, reasons in conflicted_candidates:
            conflicted_experiences.append(ConflictedExperience(
                claim=score.claim,
                fit=score.fit,
                conflictReasons=reasons or ["Hard constraint violation"],
            ))

        # Build unknowns list (claims with unknown fit)
        unknowns_list: list[GraphEvidenceClaim] = [
            c.claim for c in unknown_candidates
        ]

        # Update trace
        trace.eligibleExperienceCount = len(ranked_experiences)
        trace.conflictedExperienceCount = len(conflicted_experiences)

        return TripResearchBundle(
            scope=scope_output,
            eligibleExperiences=ranked_experiences,
            conflictedExperiences=conflicted_experiences,
            unknowns=unknowns_list,
            warnings=warnings,
            graphSnapshot=discovery_output.graphSnapshot,
            trace=trace,
            catalog=build_special_experience_catalog(
                catalog_claims,
                input_data.candidateLimit,
            ),
        )


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def orchestrate_trip_research(
    scope_repo: ScopeResolutionRepository,
    discovery_repo: KnowledgeGraphResearchRepository,
    input_data: TripResearchInput,
) -> TripResearchBundle:
    """Convenience function to run trip research orchestration.

    Args:
        scope_repo: Repository for scope resolution and fit evaluation.
        discovery_repo: Repository for experience discovery.
        input_data: Trip research input parameters.

    Returns:
        TripResearchBundle with ranked experiences and metadata.
    """
    orchestrator = GraphResearchOrchestrator(scope_repo, discovery_repo)
    return orchestrator.research(input_data)
