from __future__ import annotations

from collections import Counter
from math import ceil

from app.modules.place_checker.contract import SourcePlaceEvidence, TripEvaluationContext
from app.modules.place_checker.avoid_policy import has_avoid_conflict
from app.modules.place_checker.enums import (
    EvidenceOrigin,
    IdentityResolutionStatus,
    OperationalStatus,
    SourceTier,
)
from app.modules.place_checker.ports import StyleCandidateSource
from app.modules.place_checker.resolution_contract import EnrichedIdentityPlace
from app.modules.place_checker.style_candidate_contract import (
    StyleCandidate,
    StyleCandidateCoverage,
    StyleCandidateSelection,
    StyleCandidateSelectionBatch,
)
from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places.normalization import normalize_text
from app.shared.tools.search_places.scoring import distance_km


STYLE_CANDIDATES_PER_DAY = 2
TECHNICAL_TAG_PREFIXES = (
    "experience:",
    "item:",
    "pool_category:",
    "relationship:",
    "retrieval:",
    "style:",
)


class StyleCandidateSelectionService:
    def __init__(self, source: StyleCandidateSource) -> None:
        self.source = source

    async def select(
        self,
        context: TripEvaluationContext,
        *,
        style_inputs: list[str],
        item_inputs: list[str],
        anchor_coordinates: list[Coordinates] | None = None,
    ) -> StyleCandidateSelectionBatch:
        adm_id = context.destination.adm_id
        normalized_styles = self._style_inputs(style_inputs)
        explicit_styles = {
            normalize_text(value.split(":", 1)[1])
            for value in style_inputs
            if value.casefold().startswith("style:")
        }
        normalized_items = self._unique(item_inputs)
        if not adm_id or (not normalized_styles and not normalized_items):
            return StyleCandidateSelectionBatch()
        try:
            source_batch = await self.source.find_style_candidates(
                adm_id=adm_id,
                style_inputs=normalized_styles,
                item_inputs=normalized_items,
                per_style_limit=min(60, max(8, context.days * 6)),
            )
        except Exception:
            return StyleCandidateSelectionBatch(
                warnings=["Không thể lấy candidate theo Style/Item từ catalog."],
            )

        candidates = [
            self._with_distance(candidate, anchor_coordinates or [])
            for candidate in source_batch.candidates
            if self._eligible(candidate, context)
        ]
        selected, coverage = self._balance(
            candidates,
            source_batch.resolved_intents,
            days=context.days,
        )
        unresolved_styles = [
            value
            for value in source_batch.unresolved_style_inputs
            if value in explicit_styles
        ]
        warnings = [
            *(
                [
                    "Không resolve được Style: "
                    + ", ".join(unresolved_styles)
                    + "."
                ]
                if unresolved_styles
                else []
            ),
            *(
                [
                    "Không resolve được Item về canonical ID: "
                    + ", ".join(source_batch.unresolved_item_inputs)
                    + "."
                ]
                if source_batch.unresolved_item_inputs
                else []
            ),
            *(
                [
                    "Style candidate coverage còn thiếu: "
                    + ", ".join(
                        f"{item.style_name}={item.selected_candidates}/"
                        f"{item.target_candidates}"
                        for item in coverage
                        if not item.complete
                    )
                    + "."
                ]
                if any(not item.complete for item in coverage)
                else []
            ),
        ]
        return StyleCandidateSelectionBatch(
            selections=[self._selection(candidate) for candidate in selected],
            coverage=coverage,
            resolved_intents=source_batch.resolved_intents,
            unresolved_style_inputs=unresolved_styles,
            unresolved_item_inputs=source_batch.unresolved_item_inputs,
            warnings=warnings,
        )

    @classmethod
    def _balance(cls, candidates, resolved_intents, *, days: int):
        target = days * STYLE_CANDIDATES_PER_DAY
        style_names = {
            intent.style_id: intent.style_name for intent in resolved_intents
        }
        by_style = {
            style_id: [item for item in candidates if item.style_id == style_id]
            for style_id in style_names
        }
        requested_items = {
            style_id: {
                intent.item_id
                for intent in resolved_intents
                if intent.style_id == style_id and intent.item_id
            }
            for style_id in style_names
        }
        item_targets = {
            (style_id, item_id): ceil(target / len(item_ids))
            for style_id, item_ids in requested_items.items()
            for item_id in item_ids
            if item_ids
        }
        selected: list[StyleCandidate] = []
        selected_places: set[str] = set()
        style_counts: Counter[str] = Counter()
        item_counts: Counter[tuple[str, str]] = Counter()
        tag_counts: Counter[str] = Counter()
        while True:
            open_styles = [
                style_id
                for style_id in style_names
                if style_counts[style_id] < target
                and any(
                    item.place_id not in selected_places
                    for item in by_style[style_id]
                )
            ]
            if not open_styles:
                break
            style_id = min(
                open_styles,
                key=lambda value: (
                    style_counts[value] - target,
                    len(
                        {
                            item.place_id
                            for item in by_style[value]
                            if item.place_id not in selected_places
                        }
                    ),
                    value,
                ),
            )
            available = [
                item
                for item in by_style[style_id]
                if item.place_id not in selected_places
            ]
            chosen = min(
                available,
                key=lambda item: cls._candidate_key(
                    item,
                    item_counts,
                    item_targets,
                    tag_counts,
                ),
            )
            selected.append(chosen)
            selected_places.add(chosen.place_id)
            style_counts[style_id] += 1
            if chosen.item_id:
                item_counts[(style_id, chosen.item_id)] += 1
            tag_counts.update(cls._tags(chosen))

        coverage = []
        for style_id, style_name in sorted(style_names.items()):
            count = style_counts[style_id]
            distinct_items = len(
                {
                    item.item_id
                    for item in selected
                    if item.style_id == style_id and item.item_id
                }
            )
            coverage.append(
                StyleCandidateCoverage(
                    style_id=style_id,
                    style_name=style_name,
                    target_candidates=target,
                    selected_candidates=count,
                    distinct_items=distinct_items,
                    complete=count >= target,
                    shortfall_reason=(
                        None
                        if count >= target
                        else "catalog_has_insufficient_eligible_unique_places"
                    ),
                )
            )
        return selected, coverage

    @classmethod
    def _candidate_key(cls, candidate, item_counts, item_targets, tag_counts):
        tags = cls._tags(candidate)
        metadata = candidate.metadata
        item_key = (candidate.style_id, candidate.item_id or "")
        return (
            item_counts[item_key] - item_targets.get(item_key, 0),
            item_counts[item_key],
            sum(tag_counts[tag] for tag in tags),
            max((tag_counts[tag] for tag in tags), default=0),
            0 if candidate.relationship_source == "Offer_Item" else 1,
            -(metadata.rating or 0),
            -(metadata.review_count or 0),
            candidate.distance_from_anchor_km
            if candidate.distance_from_anchor_km is not None
            else float("inf"),
            candidate.place_id,
        )

    @staticmethod
    def _eligible(candidate: StyleCandidate, context: TripEvaluationContext) -> bool:
        metadata = candidate.metadata
        if not metadata.coordinates or not metadata.typical_duration_minutes:
            return False
        if metadata.operational_status in {
            OperationalStatus.permanently_closed,
            OperationalStatus.temporarily_closed,
        }:
            return False
        if context.people.children and metadata.children_suitable is False:
            return False
        if context.people.infants and metadata.infants_suitable is False:
            return False
        return not has_avoid_conflict(
            context.avoids,
            [candidate.place_name, metadata.category or "", *metadata.tags],
        )

    @staticmethod
    def _tags(candidate: StyleCandidate) -> set[str]:
        return {
            normalized
            for value in candidate.metadata.tags
            if not value.strip().casefold().startswith(TECHNICAL_TAG_PREFIXES)
            if (normalized := normalize_text(value))
            and normalized not in {"travel place", "restaurant", "drink dessert"}
        } or {candidate.entity_type.casefold()}

    @staticmethod
    def _with_distance(candidate, anchors):
        coordinates = candidate.metadata.coordinates
        if not coordinates or not anchors:
            return candidate
        return candidate.model_copy(
            update={
                "distance_from_anchor_km": min(
                    distance_km(coordinates, anchor) for anchor in anchors
                )
            }
        )

    @staticmethod
    def _selection(candidate):
        return StyleCandidateSelection.model_validate(candidate.model_dump())

    @classmethod
    def _style_inputs(cls, values: list[str]) -> list[str]:
        return cls._unique(
            value.split(":", 1)[1]
            if value.casefold().startswith("style:")
            else value
            for value in values
        )

    @staticmethod
    def _unique(values) -> list[str]:
        return list(
            dict.fromkeys(
                normalized
                for value in values
                if (normalized := normalize_text(value))
            )
        )

    @staticmethod
    def to_enriched_places(
        batch: StyleCandidateSelectionBatch,
    ) -> list[EnrichedIdentityPlace]:
        return [
            EnrichedIdentityPlace(
                place_id=item.place_id,
                canonical_name=item.place_name,
                original_names=[item.place_name],
                source_tier=SourceTier.system_suggested,
                mandatory=False,
                removable=True,
                status=IdentityResolutionStatus.resolved,
                identity_confidence=0.9,
                metadata=item.metadata,
                source_places=[
                    SourcePlaceEvidence(
                        origin=EvidenceOrigin.system,
                        evidence_type="style_candidate_selection",
                        evidence=(
                            f"{item.relationship_source}:"
                            f"{item.style_id}:"
                            f"{item.item_id or 'direct'}"
                        ),
                    )
                ],
            )
            for item in batch.selections
        ]
