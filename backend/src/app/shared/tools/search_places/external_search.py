from typing import Any

from app.shared.tools.search_places.contract import (
    PlaceSearchRequest,
    PlaceSearchResult,
    ProviderAttempt,
)
from app.shared.tools.search_places.scoring import rank_candidates


async def search_external_only(
    tool: Any,
    request: PlaceSearchRequest,
    names: list[str],
    attempts: list[ProviderAttempt],
) -> PlaceSearchResult:
    """Run only the injected external provider for a retrieval fallback."""
    if tool.external is None:
        return tool._result(
            request,
            status="unresolved",
            matches=[],
            attempts=attempts,
            reason="external_provider_not_configured",
        )
    candidates, failed = await tool._call_provider(
        tool.external,
        request,
        names,
        attempts,
    )
    matches = rank_candidates(request, tool._deduplicate(candidates))
    decision = tool._decide(request, matches)
    if decision is not None:
        status, selected, reason = decision
        if status in {"resolved", "needs_review"}:
            return tool._result(
                request,
                status=status,
                selected=selected,
                matches=matches,
                attempts=attempts,
                reason=f"external_{reason}",
            )
    return tool._result(
        request,
        status="provider_error" if failed else "unresolved",
        matches=matches,
        attempts=attempts,
        reason="external_provider_error" if failed else "no_candidate_passed_policy",
        retryable=failed,
    )
