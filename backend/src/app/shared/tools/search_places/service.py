import time

from app.shared.tools.search_places.batch import SearchPlacesBatchMixin
from app.shared.observability import traced_call
from app.shared.tools.search_places.contract import (
    PlaceProviderCandidate,
    PlaceSearchMatch,
    PlaceSearchRequest,
    PlaceSearchResult,
    ProviderAttempt,
)
from app.shared.tools.search_places.external_search import search_external_only
from app.shared.tools.search_places.normalization import lookup_names
from app.shared.tools.search_places.policy import PlaceSearchPolicy
from app.shared.tools.search_places.service_helpers import SearchPlacesHelpersMixin
from app.shared.tools.search_places.ports import (
    ExternalPlaceSearch,
    KnowledgeGraphPlaceSearch,
    PlaceSearchProviderError,
    PlaceSearchProviderTimeout,
)
from app.shared.tools.search_places.scoring import rank_candidates


class SearchPlacesTool(SearchPlacesBatchMixin, SearchPlacesHelpersMixin):
    """Resolve or discover places through ranked, policy-checked providers."""

    def __init__(
        self,
        knowledge_graph: KnowledgeGraphPlaceSearch,
        external: ExternalPlaceSearch | None = None,
        *,
        policy: PlaceSearchPolicy | None = None,
    ) -> None:
        self.knowledge_graph = knowledge_graph
        self.external = external
        self.policy = policy or PlaceSearchPolicy()

    async def __call__(self, request: PlaceSearchRequest) -> PlaceSearchResult:
        return await self.search(request)

    async def search(self, request: PlaceSearchRequest) -> PlaceSearchResult:
        return await traced_call(
            "places.search",
            lambda: self._search(request),
            kind="tool",
            input_summary={
                "queryChars": len(request.query),
                "alternateNameCount": len(request.alternate_names),
                "providerScope": request.provider_scope,
                "allowExternalFallback": request.allow_external_fallback,
            },
            output_summary=lambda value: {
                "status": value.status,
                "matchCount": len(value.top_matches),
                "attempts": [
                    {
                        "provider": attempt.provider,
                        "status": attempt.outcome,
                        "candidateCount": attempt.candidate_count,
                        "errorCode": attempt.error_code,
                    }
                    for attempt in value.provider_attempts
                ],
            },
            metadata={"capability": "place_search"},
        )

    async def _search(self, request: PlaceSearchRequest) -> PlaceSearchResult:
        names = lookup_names(request.query, request.alternate_names)
        attempts: list[ProviderAttempt] = []
        if request.provider_scope == "external":
            return await search_external_only(self, request, names, attempts)
        kg_candidates, kg_failed = await self._call_provider(
            self.knowledge_graph,
            request,
            names,
            attempts,
        )
        kg_matches = rank_candidates(request, self._deduplicate(kg_candidates))
        kg_decision = self._decide(request, kg_matches)
        if kg_decision is not None:
            status, selected, reason = kg_decision
            if status in {"resolved", "needs_review"}:
                return self._result(
                    request,
                    status=status,
                    selected=selected,
                    matches=kg_matches,
                    attempts=attempts,
                    reason=reason,
                )

        if request.search_mode == "named_place" and request.top_k == 1 and kg_matches:
            return self._result(
                request,
                status="unresolved",
                matches=kg_matches,
                attempts=attempts,
                reason="catalog_top_1_not_eligible",
            )
        if request.search_mode == "named_place" and request.top_k == 1 and kg_failed:
            return self._result(
                request,
                status="provider_error",
                matches=[],
                attempts=attempts,
                reason="knowledge_graph_provider_error",
                retryable=True,
            )

        if (
            request.provider_scope == "knowledge_graph"
            or not request.allow_external_fallback
            or self.external is None
        ):
            reason = (
                "external_fallback_disabled"
                if not request.allow_external_fallback
                else "external_provider_not_configured"
            )
            if kg_failed and not kg_matches:
                return self._result(
                    request,
                    status="provider_error",
                    matches=[],
                    attempts=attempts,
                    reason="knowledge_graph_provider_error",
                    retryable=True,
                )
            return self._result(
                request,
                status="unresolved",
                matches=kg_matches,
                attempts=attempts,
                reason=reason,
            )

        external_candidates, external_failed = await self._call_provider(
            self.external,
            request,
            names,
            attempts,
        )
        external_matches = rank_candidates(
            request,
            self._deduplicate(external_candidates),
        )
        external_decision = self._decide(request, external_matches)
        combined = self._merge_matches(kg_matches, external_matches, request.top_k)
        if external_decision is not None:
            status, selected, reason = external_decision
            if status in {"resolved", "needs_review"}:
                return self._result(
                    request,
                    status=status,
                    selected=selected,
                    matches=combined,
                    attempts=attempts,
                    reason=f"external_{reason}",
                )
        if external_failed:
            return self._result(
                request,
                status="provider_error",
                matches=combined,
                attempts=attempts,
                reason="external_provider_error",
                retryable=True,
            )
        return self._result(
            request,
            status="unresolved",
            matches=combined,
            attempts=attempts,
            reason="no_candidate_passed_policy",
        )

    async def _call_provider(
        self,
        provider: KnowledgeGraphPlaceSearch | ExternalPlaceSearch,
        request: PlaceSearchRequest,
        names: list[str],
        attempts: list[ProviderAttempt],
    ) -> tuple[list[PlaceProviderCandidate], bool]:
        started_at = time.perf_counter()
        try:
            provider_kwargs = {
                "input_adm": request.input_adm,
                "place_type_hint": request.place_type_hint,
                "limit": request.top_k,
            }
            if getattr(provider, "supports_search_mode", False):
                provider_kwargs["search_mode"] = request.search_mode
            if getattr(provider, "supports_address_hint", False):
                provider_kwargs["address_hint"] = request.address_hint
            if request.anchor_place_id is not None:
                provider_kwargs["anchor_place_id"] = request.anchor_place_id
            candidates = await provider.search(names, **provider_kwargs)
        except PlaceSearchProviderTimeout as exc:
            attempts.append(
                self._attempt(
                    provider.provider_name,
                    "timeout",
                    names,
                    started_at,
                    error_code=exc.code,
                )
            )
            return [], True
        except PlaceSearchProviderError as exc:
            attempts.append(
                self._attempt(
                    provider.provider_name,
                    "error",
                    names,
                    started_at,
                    error_code=exc.code,
                )
            )
            return [], True
        attempts.append(
            self._attempt(
                provider.provider_name,
                "candidates" if candidates else "empty",
                names,
                started_at,
                candidate_count=len(candidates),
            )
        )
        return candidates, False

    def _decide(
        self,
        request: PlaceSearchRequest,
        matches: list[PlaceSearchMatch],
    ) -> tuple[str, PlaceSearchMatch | None, str] | None:
        if request.search_mode == "named_place" and request.top_k == 1 and matches:
            top = matches[0]
            identity_rejections = set(top.rejection_reasons) - {"coordinates_missing"}
            if not identity_rejections:
                return "resolved", top, "unified_catalog_top_1"
        eligible = [match for match in matches if not match.rejection_reasons]
        if not eligible:
            return None
        top = eligible[0]
        if request.search_mode == "requirement":
            if (
                top.score >= self.policy.requirement_acceptance_score
                or top.score_components.get("nameSimilarity", 0) >= 0.90
            ):
                return "resolved", top, "requirement_match"
            return None
        if top.score <= self.policy.named_acceptance_score:
            return None
        if len(eligible) > 1:
            second = eligible[1]
            margin = top.score - second.score
            both_name_matches = (
                top.score_components.get("nameSimilarity", 0)
                >= self.policy.ambiguity_name_score
                and second.score_components.get("nameSimilarity", 0)
                >= self.policy.ambiguity_name_score
            )
            if margin < self.policy.named_minimum_margin and both_name_matches:
                if self._address_hint_disambiguates(request, top, second):
                    return "resolved", top, "address_hint_identity"
                if self._distinctive_name_disambiguates(top, second):
                    return "resolved", top, "distinctive_name_identity"
                if self._route_context_disambiguates(top, second):
                    return "resolved", top, "route_context_identity"
                if not request.address_hint:
                    # Same-name branches are already ranked deterministically.
                    # Without an address hint there is no extra signal to ask
                    # the user for, so select the first catalog result.
                    return "resolved", top, "first_branch_without_address_hint"
                return "needs_review", None, "branch_or_identity_ambiguous"
            if margin < self.policy.named_minimum_margin:
                return "needs_review", None, "top_matches_too_close"
        return "resolved", top, "high_confidence_identity"


async def search_places(
    request: PlaceSearchRequest,
    *,
    knowledge_graph: KnowledgeGraphPlaceSearch,
    external: ExternalPlaceSearch | None = None,
    policy: PlaceSearchPolicy | None = None,
) -> PlaceSearchResult:
    """Convenience entry point for modules that do not retain a tool instance."""

    return await SearchPlacesTool(
        knowledge_graph,
        external,
        policy=policy,
    ).search(request)
