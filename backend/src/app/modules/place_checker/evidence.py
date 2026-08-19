from __future__ import annotations

from collections import OrderedDict

from app.modules.place_checker.contract import SourcePlaceEvidence, SourceTier, UrlNote
from app.modules.place_checker.errors import PlaceCatalogUnavailableError
from app.modules.place_checker.ports import PlaceMetadataRepository
from app.modules.place_checker.resolution_contract import (
    CatalogPlace,
    EnrichedIdentityPlace,
    EvidenceEnrichmentOutput,
    IdentityResolutionBatch,
    PlaceMetadata,
    ResolvedPlaceCandidate,
)
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import text_similarity


SOURCE_PRIORITY = {
    SourceTier.direct_user: 0,
    SourceTier.url: 1,
    SourceTier.item_resolved: 2,
    SourceTier.system_suggested: 3,
}
NOTE_LINK_THRESHOLD = 0.90


class EvidenceEnrichmentService:
    def __init__(self, metadata_repository: PlaceMetadataRepository | None = None) -> None:
        self.metadata_repository = metadata_repository

    async def merge_and_enrich(
        self,
        batch: IdentityResolutionBatch,
        url_notes: list[UrlNote],
    ) -> EvidenceEnrichmentOutput:
        groups = self._group_candidates(batch.candidates)
        place_ids = list(
            dict.fromkeys(
                candidate.selected_place.place_id
                for group in groups.values()
                for candidate in group
                if candidate.selected_place is not None
            )
        )
        metadata_by_id: dict[str, PlaceMetadata] = {}
        warnings = list(batch.warnings)
        if self.metadata_repository is not None and place_ids:
            try:
                metadata_by_id = await self.metadata_repository.get_many(place_ids)
            except PlaceCatalogUnavailableError:
                warnings.append("Place metadata catalog tạm thời không khả dụng.")

        places = [
            self._build_place(group, metadata_by_id)
            for group in groups.values()
        ]
        unattached = self._attach_notes(places, url_notes)
        duplicate_count = sum(len(group) - 1 for group in groups.values())
        return EvidenceEnrichmentOutput(
            places=places,
            unattached_url_notes=unattached,
            duplicate_count=duplicate_count,
            warnings=list(dict.fromkeys(warnings)),
        )

    @staticmethod
    def _group_candidates(
        candidates: list[ResolvedPlaceCandidate],
    ) -> OrderedDict[str, list[ResolvedPlaceCandidate]]:
        groups: OrderedDict[str, list[ResolvedPlaceCandidate]] = OrderedDict()
        provider_group_keys: dict[str, str] = {}
        for candidate in sorted(candidates, key=lambda item: item.candidate_index):
            if candidate.selected_place is not None:
                place = candidate.selected_place
                canonical_key = f"place:{place.place_id.casefold()}"
                key = next(
                    (
                        provider_group_keys[provider_id.casefold()]
                        for provider_id in place.provider_ids
                        if provider_id.casefold() in provider_group_keys
                    ),
                    canonical_key,
                )
                for provider_id in place.provider_ids:
                    provider_group_keys.setdefault(provider_id.casefold(), key)
            else:
                name = normalize_text(candidate.candidate.name)
                address = normalize_text(candidate.candidate.address_hint)
                key = f"unresolved:{name}:{address}"
            groups.setdefault(key, []).append(candidate)
        return groups

    def _build_place(
        self,
        group: list[ResolvedPlaceCandidate],
        metadata_by_id: dict[str, PlaceMetadata],
    ) -> EnrichedIdentityPlace:
        selected = next(
            (candidate.selected_place for candidate in group if candidate.selected_place),
            None,
        )
        source_tier = min(
            (candidate.candidate.source_tier for candidate in group),
            key=SOURCE_PRIORITY.__getitem__,
        )
        metadata = self._metadata_for(selected, metadata_by_id)
        source_places = self._unique_sources(group)
        original_names = list(
            dict.fromkeys(candidate.candidate.name for candidate in group)
        )
        match_options = []
        seen_option_ids: set[str] = set()
        for candidate in group:
            for option in candidate.match_options:
                if option.place.place_id not in seen_option_ids:
                    seen_option_ids.add(option.place.place_id)
                    match_options.append(option)

        missing_fields: list[str] = []
        if selected is not None and metadata is not None:
            if metadata.coordinates is None:
                missing_fields.append("coordinates")
            if metadata.category is None:
                missing_fields.append("category")
            if metadata.typical_duration_minutes is None:
                missing_fields.append("typical_duration_minutes")
            if metadata.opening_hours is None:
                missing_fields.append("opening_hours")

        statuses = {candidate.status for candidate in group}
        status = min(statuses, key=lambda value: self._status_priority(value.value))
        selected_scores = [
            candidate.selected_score
            for candidate in group
            if candidate.selected_score is not None
        ]
        warnings = list(
            dict.fromkeys(
                warning
                for candidate in group
                for warning in candidate.warnings
            )
        )
        evidence_conflicts = self._evidence_conflicts(source_places)
        return EnrichedIdentityPlace(
            place_id=selected.place_id if selected else None,
            canonical_name=selected.canonical_name if selected else None,
            original_names=original_names,
            aliases=selected.aliases if selected else [],
            source_tier=source_tier,
            mandatory=source_tier == SourceTier.direct_user,
            removable=source_tier != SourceTier.direct_user,
            status=status,
            identity_confidence=max(selected_scores, default=None),
            metadata=metadata,
            source_places=source_places,
            match_options=match_options[:5],
            evidence_conflicts=evidence_conflicts,
            missing_fields=missing_fields,
            warnings=warnings,
        )

    @staticmethod
    def _status_priority(value: str) -> int:
        return {
            "resolved": 0,
            "provisional": 1,
            "needs_review": 2,
            "unresolved": 3,
        }[value]

    @staticmethod
    def _metadata_for(
        place: CatalogPlace | None,
        metadata_by_id: dict[str, PlaceMetadata],
    ) -> PlaceMetadata | None:
        if place is None:
            return None
        stored = metadata_by_id.get(place.place_id)
        if stored is None:
            return PlaceMetadata(
                place_id=place.place_id,
                coordinates=place.coordinates,
                address=place.address,
                category=place.category,
                tags=place.tags,
                relationships=place.relationships,
            )
        return stored.model_copy(
            update={
                "coordinates": stored.coordinates or place.coordinates,
                "address": stored.address or place.address,
                "category": stored.category or place.category,
                "tags": list(dict.fromkeys([*stored.tags, *place.tags])),
                "relationships": list(
                    {
                        (
                            relationship.relationship_type,
                            relationship.from_entity_id,
                            relationship.to_entity_id,
                        ): relationship
                        for relationship in [
                            *stored.relationships,
                            *place.relationships,
                        ]
                    }.values()
                ),
            }
        )

    @staticmethod
    def _unique_sources(
        group: list[ResolvedPlaceCandidate],
    ) -> list[SourcePlaceEvidence]:
        result: list[SourcePlaceEvidence] = []
        seen: set[tuple] = set()
        for candidate in group:
            for source in candidate.candidate.source_places:
                key = (
                    source.origin,
                    source.evidence_type,
                    source.source_url,
                    source.evidence,
                    source.source_time_hint,
                    source.address_hint,
                    source.observed_at,
                )
                if key not in seen:
                    seen.add(key)
                    result.append(source)
        return result

    @staticmethod
    def _evidence_conflicts(
        sources: list[SourcePlaceEvidence],
    ) -> list[str]:
        conflicts: list[str] = []
        time_hints = {
            normalize_text(source.source_time_hint)
            for source in sources
            if source.source_time_hint
        }
        if len(time_hints) > 1:
            conflicts.append("source_time_hint_conflict")

        addresses = [
            source.address_hint for source in sources if source.address_hint
        ]
        if any(
            text_similarity(left, right) < 0.20
            for index, left in enumerate(addresses)
            for right in addresses[index + 1 :]
        ):
            conflicts.append("source_address_hint_conflict")
        return conflicts

    @staticmethod
    def _attach_notes(
        places: list[EnrichedIdentityPlace],
        notes: list[UrlNote],
    ) -> list[UrlNote]:
        unattached: list[UrlNote] = []
        for note in notes:
            if not note.place_name:
                unattached.append(note)
                continue
            scored: list[tuple[float, EnrichedIdentityPlace]] = []
            for place in places:
                names = [
                    *place.original_names,
                    *place.aliases,
                    *([place.canonical_name] if place.canonical_name else []),
                ]
                score = max(
                    (text_similarity(note.place_name, name) for name in names),
                    default=0.0,
                )
                scored.append((score, place))
            scored.sort(key=lambda item: item[0], reverse=True)
            if not scored or scored[0][0] < NOTE_LINK_THRESHOLD:
                unattached.append(note)
                continue
            if len(scored) > 1 and scored[0][0] == scored[1][0]:
                unattached.append(note)
                continue
            scored[0][1].url_notes.append(note)
        return unattached
