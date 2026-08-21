from dataclasses import dataclass

from app.modules.explorer.models import SourceArtifact


@dataclass(frozen=True)
class PrimaryEvidenceFacts:
    destination_found: bool
    named_place_count: int
    travel_detail_count: int
    description_useful: bool
    confidence: float


@dataclass(frozen=True)
class PrimaryEvidenceCoverage:
    sufficient: bool
    transcript_timeline_ratio: float | None
    meaningful_character_count: int
    destination_found: bool
    named_place_count: int
    travel_detail_count: int
    description_useful: bool
    confidence: float
    reasons: tuple[str, ...]


class PrimaryEvidenceCoveragePolicy:
    """Decide whether normalized primary text can avoid media analysis."""

    def __init__(
        self,
        *,
        minimum_confidence: float = 0.7,
        minimum_transcript_characters: int = 200,
        minimum_transcript_ratio: float = 0.8,
    ) -> None:
        self.minimum_confidence = minimum_confidence
        self.minimum_transcript_characters = minimum_transcript_characters
        self.minimum_transcript_ratio = minimum_transcript_ratio

    def evaluate(
        self,
        artifacts: list[SourceArtifact],
        facts: PrimaryEvidenceFacts,
        *,
        transcript_timeline_ratio: float | None = None,
        exhaustive_requested: bool = False,
    ) -> PrimaryEvidenceCoverage:
        transcript_text = "\n".join(
            artifact.text
            for artifact in artifacts
            if artifact.artifact_type == "transcript"
        )
        primary_text = "\n".join(artifact.text for artifact in artifacts)
        meaningful_characters = sum(character.isalnum() for character in primary_text)
        has_transcript = bool(transcript_text.strip())
        has_description = any(
            artifact.artifact_type == "caption" for artifact in artifacts
        )
        transcript_characters = sum(character.isalnum() for character in transcript_text)
        technical_transcript_coverage = has_transcript and (
            (
                transcript_timeline_ratio is not None
                and transcript_timeline_ratio >= self.minimum_transcript_ratio
            )
            or (
                transcript_timeline_ratio is None
                and transcript_characters >= self.minimum_transcript_characters
            )
        )
        semantic_anchor = facts.destination_found or facts.named_place_count > 0
        useful_transcript = technical_transcript_coverage and semantic_anchor and (
            facts.named_place_count >= 2 or facts.travel_detail_count >= 1
        )
        useful_description = (
            has_description
            and facts.description_useful
            and semantic_anchor
            and (
                facts.named_place_count >= 2
                or facts.travel_detail_count >= 2
            )
        )
        sufficient = (
            not exhaustive_requested
            and facts.confidence >= self.minimum_confidence
            and (useful_transcript or useful_description)
        )

        reasons: list[str] = []
        if exhaustive_requested:
            reasons.append("exhaustive_request")
        if facts.confidence < self.minimum_confidence:
            reasons.append("low_semantic_confidence")
        if has_transcript and not technical_transcript_coverage:
            reasons.append("incomplete_transcript")
        if not semantic_anchor:
            reasons.append("missing_destination_or_place")
        if not (useful_transcript or useful_description):
            reasons.append("insufficient_travel_evidence")
        if sufficient:
            reasons.append("primary_evidence_sufficient")

        return PrimaryEvidenceCoverage(
            sufficient=sufficient,
            transcript_timeline_ratio=transcript_timeline_ratio,
            meaningful_character_count=meaningful_characters,
            destination_found=facts.destination_found,
            named_place_count=facts.named_place_count,
            travel_detail_count=facts.travel_detail_count,
            description_useful=facts.description_useful,
            confidence=facts.confidence,
            reasons=tuple(reasons),
        )
