from __future__ import annotations

from app.modules.place_checker.contract import (
    AdmResolutionStatus,
    PlaceCandidateInput,
    TripEvaluationContext,
)
from app.modules.place_checker.enums import (
    IdentityResolutionStatus,
    SimilarityMethod,
    SourceTier,
)
from app.modules.place_checker.ports import NamedPlaceSearchTool
from app.modules.place_checker.resolution.contract import (
    CatalogPlace,
    IdentityResolutionBatch,
    PlaceMatchOption,
    ResolvedPlaceCandidate,
    SimilarityComponents,
)
from app.modules.place_checker.resolution.policy import select_provisional_option
from app.modules.place_checker.resolution.batch import EntityResolutionBatchMixin
from app.shared.tools.search_places import (
    AdministrativeArea,
    PlaceSearchMatch,
    PlaceSearchRequest,
    PlaceSearchResult,
)
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import text_similarity


MAX_MATCH_OPTIONS = 1


class EntityResolutionService(EntityResolutionBatchMixin):
    def __init__(
        self,
        search_tool: NamedPlaceSearchTool,
        *,
        max_concurrency: int = 10,
    ) -> None:
        self.search_tool = search_tool
        self.max_concurrency = max(1, max_concurrency)

    async def resolve_all(
        self,
        candidates: list[PlaceCandidateInput],
        context: TripEvaluationContext,
    ) -> IdentityResolutionBatch:
        if context.destination.status != AdmResolutionStatus.resolved:
            warning = "Không thể phân giải place khi destination ADM chưa rõ."
            return IdentityResolutionBatch(
                candidates=[
                    ResolvedPlaceCandidate(
                        candidate_index=index,
                        candidate=candidate,
                        status=IdentityResolutionStatus.unresolved,
                        warnings=[warning],
                    )
                    for index, candidate in enumerate(candidates)
                ],
                warnings=[warning],
            )

        results = await self._resolve_candidates(candidates, context)
        batch_warnings = list(
            dict.fromkeys(
                warning
                for result in results
                for warning in result.warnings
                if result.resolution_reason
                in {
                    "knowledge_graph_provider_error",
                    "search_places_unexpected_error",
                }
            )
        )
        return IdentityResolutionBatch(
            candidates=list(results),
            warnings=batch_warnings,
        )

    async def _resolve_one(
        self,
        index: int,
        candidate: PlaceCandidateInput,
        context: TripEvaluationContext,
    ) -> ResolvedPlaceCandidate:
        request = self._build_request(candidate, context)
        try:
            result = await self.search_tool.search(request)
        except Exception:
            return ResolvedPlaceCandidate(
                candidate_index=index,
                candidate=candidate,
                status=IdentityResolutionStatus.unresolved,
                warnings=["Công cụ search_places gặp lỗi không xác định."],
                resolution_reason="search_places_unexpected_error",
            )
        return self._map_result(index, candidate, context, result)

    @staticmethod
    def _build_request(
        candidate: PlaceCandidateInput,
        context: TripEvaluationContext,
    ) -> PlaceSearchRequest:
        destination = context.destination
        assert destination.adm_id is not None
        assert destination.canonical_name is not None
        assert destination.country_code is not None
        source = candidate.source_places[0]
        return PlaceSearchRequest(
            query=candidate.name,
            input_adm=AdministrativeArea(
                adm_id=destination.adm_id,
                name=destination.canonical_name,
                country_code=destination.country_code,
            ),
            search_mode="named_place",
            address_hint=EntityResolutionService._address_hint(candidate),
            source_url=source.source_url,
            source_evidence=source.evidence[:500],
            source_time_hint=source.source_time_hint,
            top_k=MAX_MATCH_OPTIONS,
            allow_external_fallback=True,
        )

    @classmethod
    def _map_result(
        cls,
        index: int,
        candidate: PlaceCandidateInput,
        context: TripEvaluationContext,
        result: PlaceSearchResult,
    ) -> ResolvedPlaceCandidate:
        options = [
            option
            for rank, match in enumerate(result.top_matches, start=1)
            if (option := cls._map_match(candidate, context, match, rank)) is not None
        ]
        eligible = [
            option
            for option in options
            if option.eligible_destination and not option.identity_conflicts
        ]
        selected_option = cls._selected_option(result, options)
        warnings = cls._warnings(result, options)
        margin = (
            eligible[0].score - eligible[1].score
            if len(eligible) > 1
            else (1.0 if eligible else None)
        )

        if result.status == "resolved" and selected_option is not None:
            if selected_option.identity_conflicts:
                return ResolvedPlaceCandidate(
                    candidate_index=index,
                    candidate=candidate,
                    status=IdentityResolutionStatus.needs_review,
                    match_options=options,
                    selected_score=selected_option.score,
                    score_margin=margin,
                    resolution_method=selected_option.method,
                    provider_attempts=result.provider_attempts,
                    resolution_reason="place_checker_identity_conflict",
                    warnings=[
                        *warnings,
                        "Identity có dữ liệu mâu thuẫn, cần kiểm tra thủ công.",
                    ],
                )
            if (
                result.selected is not None
                and result.selected.verification_status != "verified"
            ):
                return ResolvedPlaceCandidate(
                    candidate_index=index,
                    candidate=candidate,
                    status=IdentityResolutionStatus.provisional,
                    selected_place=selected_option.place,
                    match_options=options,
                    selected_score=selected_option.score,
                    score_margin=margin,
                    resolution_method=selected_option.method,
                    provider_attempts=result.provider_attempts,
                    resolution_reason="external_draft_requires_admin_review",
                    warnings=[
                        *warnings,
                        "Địa điểm từ Google Maps đã lưu dạng draft và cần admin duyệt.",
                    ],
                )
            return ResolvedPlaceCandidate(
                candidate_index=index,
                candidate=candidate,
                status=IdentityResolutionStatus.resolved,
                selected_place=selected_option.place,
                match_options=options,
                selected_score=selected_option.score,
                score_margin=margin,
                resolution_method=selected_option.method,
                provider_attempts=result.provider_attempts,
                resolution_reason=result.resolution_reason,
                warnings=warnings,
            )

        provisional = select_provisional_option(candidate, result, options)
        if provisional is not None:
            return ResolvedPlaceCandidate(
                candidate_index=index,
                candidate=candidate,
                status=IdentityResolutionStatus.provisional,
                selected_place=provisional.place,
                match_options=options,
                selected_score=provisional.score,
                score_margin=margin,
                resolution_method=provisional.method,
                provider_attempts=result.provider_attempts,
                resolution_reason=f"auto_selected_{result.resolution_reason}",
                warnings=[
                    *warnings,
                    "Place Checker đã tự chọn match tốt nhất để đưa qua Planner; identity vẫn cần được xác minh trước khi chốt lịch.",
                ],
            )

        status = (
            IdentityResolutionStatus.needs_review
            if result.status == "needs_review"
            else IdentityResolutionStatus.unresolved
        )
        best = options[0] if options else None
        return ResolvedPlaceCandidate(
            candidate_index=index,
            candidate=candidate,
            status=status,
            match_options=options,
            selected_score=best.score if best else None,
            score_margin=margin,
            resolution_method=best.method if best else None,
            provider_attempts=result.provider_attempts,
            resolution_reason=result.resolution_reason,
            warnings=warnings,
        )

    @classmethod
    def _map_match(
        cls,
        candidate: PlaceCandidateInput,
        context: TripEvaluationContext,
        match: PlaceSearchMatch,
        rank: int,
    ) -> PlaceMatchOption | None:
        if match.place_id is None:
            return None
        scores = match.score_components
        address_hint = cls._address_hint(candidate)
        name_score = scores.get("nameSimilarity", 0.0)
        destination_score = scores.get("admCompatibility", 0.0)
        semantic_score = scores.get("semanticSimilarity")
        address_score = scores.get("addressCompatibility") if address_hint else None
        method, alias_score = cls._match_method(candidate, match, name_score)
        if semantic_score is not None and semantic_score > name_score:
            method = SimilarityMethod.semantic

        destination = context.destination
        place = CatalogPlace(
            place_id=match.place_id,
            canonical_name=match.name,
            adm_id=destination.adm_id if destination_score == 1 else None,
            region_key=destination.region_key if destination_score == 1 else None,
            country_code=(destination.country_code if destination_score == 1 else None),
            address=match.address,
            category=match.canonical_type,
            coordinates=match.coordinates,
            provider_ids=[match.provider_id] if match.provider_id else [],
            tags=match.tags,
            relationships=match.relationship_evidence,
        )
        conflicts = list(match.rejection_reasons)
        if candidate.source_tier == SourceTier.url and not cls._has_explicit_name_match(
            candidate.name, match
        ):
            conflicts.append("source_name_not_verified_by_catalog")
        if cls._has_address_conflict(address_hint, match.address):
            conflicts.append("address_conflict")
        return PlaceMatchOption(
            place=place,
            method=method,
            components=SimilarityComponents(
                lexical_score=name_score,
                alias_score=alias_score,
                semantic_score=semantic_score,
                address_score=address_score,
                destination_score=destination_score,
                combined_score=match.score,
            ),
            rank=rank,
            eligible_destination=destination_score == 1,
            identity_conflicts=list(dict.fromkeys(conflicts)),
            reasons=[
                f"provider={match.provider}",
                *(f"{name}={value:.3f}" for name, value in scores.items()),
            ],
        )

    @staticmethod
    def _match_method(
        candidate: PlaceCandidateInput,
        match: PlaceSearchMatch,
        name_score: float,
    ) -> tuple[SimilarityMethod, float | None]:
        if normalize_text(candidate.name) == normalize_text(match.name):
            return SimilarityMethod.exact, None
        if name_score == 1:
            return SimilarityMethod.alias, 1.0
        return SimilarityMethod.lexical_only, None

    @staticmethod
    def _has_explicit_name_match(
        candidate_name: str,
        match: PlaceSearchMatch,
    ) -> bool:
        normalized_candidate = normalize_text(candidate_name)
        return normalized_candidate in {
            normalize_text(name) for name in (match.name, *match.aliases)
        }

    @staticmethod
    def _address_hint(candidate: PlaceCandidateInput) -> str | None:
        if candidate.address_hint:
            return candidate.address_hint
        return next(
            (
                source.address_hint
                for source in candidate.source_places
                if source.address_hint
            ),
            None,
        )

    @staticmethod
    def _has_address_conflict(
        address_hint: str | None,
        address: str | None,
    ) -> bool:
        if not address_hint or not address:
            return False
        normalized_hint = normalize_text(address_hint)
        normalized_address = normalize_text(address)
        compact_hint = normalized_hint.replace(" ", "")
        compact_address = normalized_address.replace(" ", "")
        if compact_hint in compact_address or compact_address in compact_hint:
            return False
        hint_tokens = set(normalized_hint.split())
        address_tokens = set(normalized_address.split())
        return bool(
            text_similarity(address_hint, address) < 0.45
            and hint_tokens
            and address_tokens
            and hint_tokens.isdisjoint(address_tokens)
        )

    @staticmethod
    def _selected_option(
        result: PlaceSearchResult,
        options: list[PlaceMatchOption],
    ) -> PlaceMatchOption | None:
        if result.selected is None or result.selected.place_id is None:
            return None
        return next(
            (
                option
                for option in options
                if option.place.place_id == result.selected.place_id
            ),
            None,
        )

    @staticmethod
    def _warnings(
        result: PlaceSearchResult,
        options: list[PlaceMatchOption],
    ) -> list[str]:
        warnings: list[str] = []
        if result.status == "provider_error":
            warnings.append("Knowledge Graph search tạm thời không khả dụng.")
        elif result.status == "needs_review":
            warnings.append("Nhiều identity có điểm quá gần nhau.")
        elif result.status == "unresolved":
            warnings.append("Không tìm thấy identity đủ tin cậy trong đúng ADM.")
        if len(options) < len(result.top_matches):
            warnings.append("Đã bỏ match không có stable identity.")
        return warnings
