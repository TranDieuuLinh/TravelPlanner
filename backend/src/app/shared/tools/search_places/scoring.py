from difflib import SequenceMatcher
from math import asin, cos, log10, radians, sin, sqrt

from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places.contract import (
    PlaceProviderCandidate,
    PlaceSearchMatch,
    PlaceSearchRequest,
)
from app.shared.tools.search_places.normalization import normalize_text


def _tokens(value: str | None) -> set[str]:
    return set(normalize_text(value).split())


def text_similarity(left: str | None, right: str | None) -> float:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    left_tokens = set(normalized_left.split())
    right_tokens = set(normalized_right.split())
    union = left_tokens | right_tokens
    token_score = len(left_tokens & right_tokens) / len(union) if union else 0.0
    sequence_score = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    containment_score = (
        min(len(normalized_left), len(normalized_right))
        / max(len(normalized_left), len(normalized_right))
        if normalized_left in normalized_right or normalized_right in normalized_left
        else 0.0
    )
    return min(1.0, max(token_score, sequence_score, containment_score))


def distance_km(left: Coordinates, right: Coordinates) -> float:
    latitude_delta = radians(right.latitude - left.latitude)
    longitude_delta = radians(right.longitude - left.longitude)
    left_latitude = radians(left.latitude)
    right_latitude = radians(right.latitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(left_latitude) * cos(right_latitude) * sin(longitude_delta / 2) ** 2
    )
    return 6371.0 * 2 * asin(sqrt(haversine))


def _anchor_distance(
    request: PlaceSearchRequest,
    candidate: PlaceProviderCandidate,
) -> float | None:
    if candidate.coordinates is None:
        return None
    anchors = [
        anchor
        for anchor in (request.previous_place, request.next_place)
        if anchor is not None
    ]
    if not anchors:
        return None
    return sum(distance_km(anchor, candidate.coordinates) for anchor in anchors) / len(
        anchors
    )


def _name_score(request: PlaceSearchRequest, candidate: PlaceProviderCandidate) -> float:
    names = [candidate.name, *candidate.aliases]
    if request.search_mode == "requirement":
        names.extend(candidate.tags)
        return max(text_similarity(request.query, name) for name in names)
    query_tokens = _tokens(request.query)
    scores = []
    for name in names:
        name_tokens = _tokens(name)
        coverage = (
            len(query_tokens & name_tokens) / len(query_tokens)
            if query_tokens
            else 0.0
        )
        scores.append(text_similarity(request.query, name) * 0.70 + coverage * 0.30)
    return max(scores, default=0.0)


def _adm_score(request: PlaceSearchRequest, candidate: PlaceProviderCandidate) -> float:
    adm_id = normalize_text(request.input_adm.adm_id)
    adm_name = normalize_text(request.input_adm.name)
    candidate_ids = {normalize_text(value) for value in candidate.adm_ids}
    candidate_names = {normalize_text(value) for value in candidate.adm_names}
    if adm_id in candidate_ids or adm_name in candidate_names:
        return 1.0
    return 0.0


def _type_score(request: PlaceSearchRequest, candidate: PlaceProviderCandidate) -> float:
    if not request.place_type_hint:
        return 0.5
    if not candidate.canonical_type:
        return 0.0
    expected = normalize_text(request.place_type_hint)
    actual = normalize_text(candidate.canonical_type)
    if expected == actual:
        return 1.0
    compatible_groups = (
        {"restaurant", "food", "food venue"},
        {"cafe", "coffee", "drink dessert", "drink"},
        {"travel place", "attraction", "museum", "landmark"},
        {"accommodation", "hotel", "hostel"},
    )
    return 0.75 if any(expected in group and actual in group for group in compatible_groups) else 0.0


def score_candidate(
    request: PlaceSearchRequest,
    candidate: PlaceProviderCandidate,
) -> PlaceSearchMatch:
    name = _name_score(request, candidate)
    adm = _adm_score(request, candidate)
    address = (
        text_similarity(request.address_hint, candidate.address)
        if request.address_hint
        else 0.5
    )
    place_type = _type_score(request, candidate)
    confidence = candidate.data_confidence
    rating_score = (candidate.rating or 0.0) / 5.0
    review_score = min(1.0, log10((candidate.review_count or 0) + 1) / 5.0)
    anchor_distance = _anchor_distance(request, candidate)
    if request.search_mode == "requirement":
        score = (
            name * 0.16
            + adm * 0.16
            + place_type * 0.16
            + confidence * 0.08
            + address * 0.05
            + rating_score * 0.06
            + review_score * 0.02
            + candidate.relationship_score * 0.31
        )
    else:
        score = (
            name * 0.62
            + adm * 0.18
            + address * 0.08
            + place_type * 0.07
            + confidence * 0.05
        )
    rejection_reasons: list[str] = []
    if candidate.coordinates is None:
        rejection_reasons.append("coordinates_missing")
    if adm == 0:
        rejection_reasons.append("adm_mismatch_or_missing")
    if request.place_type_hint and place_type == 0:
        rejection_reasons.append("place_type_conflict_or_missing")
    if not candidate.stable_id:
        rejection_reasons.append("stable_identity_missing")
    return PlaceSearchMatch(
        placeId=candidate.stable_id,
        provider=candidate.provider,
        providerId=candidate.provider_id,
        name=candidate.name,
        canonicalType=candidate.canonical_type,
        address=candidate.address,
        coordinates=candidate.coordinates,
        tags=candidate.tags,
        rating=candidate.rating,
        reviewCount=candidate.review_count,
        relationshipScore=candidate.relationship_score,
        relationshipEvidence=candidate.relationship_evidence,
        score=round(min(1.0, max(0.0, score)), 6),
        scoreComponents={
            "nameSimilarity": round(name, 6),
            "admCompatibility": round(adm, 6),
            "addressCompatibility": round(address, 6),
            "typeCompatibility": round(place_type, 6),
            "dataConfidence": round(confidence, 6),
            "rating": round(rating_score, 6),
            "reviewCount": round(review_score, 6),
            "relationshipScore": round(candidate.relationship_score, 6),
            **(
                {"anchorDistanceKm": round(anchor_distance, 6)}
                if anchor_distance is not None
                else {}
            ),
        },
        rejectionReasons=rejection_reasons,
        fetchedAt=candidate.fetched_at,
    )


def rank_candidates(
    request: PlaceSearchRequest,
    candidates: list[PlaceProviderCandidate],
) -> list[PlaceSearchMatch]:
    matches = [score_candidate(request, candidate) for candidate in candidates]
    matches.sort(
        key=lambda match: (
            bool(match.rejection_reasons),
            -match.score,
            match.score_components.get("anchorDistanceKm", float("inf")),
            normalize_text(match.name),
        )
    )
    return matches[: request.top_k]
