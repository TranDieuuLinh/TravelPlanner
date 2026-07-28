from __future__ import annotations

import re

from app.modules.plans.explorer.tools.url_reels.schema import ExtractedContext, ExtractedPlace, UrlMetadata


PLACE_KEYWORDS = [
    "coffee",
    "cafe",
    "café",
    "restaurant",
    "temple",
    "museum",
    "prison",
    "bridge",
    "market",
    "shopping",
    "quarter",
    "literature",
    "hotel",
    "homestay",
    "banh",
    "bahn",
    "mi",
    "pho",
]

GENERIC_PLACE_TERMS = {
    "coffee",
    "cafe",
    "restaurant",
    "star restaurant",
    "michelin star restaurant",
    "temple",
    "literature",
    "shopping",
    "market",
    "city",
    "university",
}

NOISE_TERMS = {
    "tiktok",
    "sony",
    "rec",
    "spotfocus",
    "review",
    "reviews",
    "from",
    "first",
    "wanted",
    "world",
    "place",
    "tour",
    "hours exploring",
    "late night snack",
    "honestly",
}


INTEREST_KEYWORDS = {
    "coffee": ["coffee", "cafe", "café"],
    "food": ["food", "restaurant", "michelin", "banh", "pho", "bun", "street food"],
    "shopping": ["shopping", "market", "vintage"],
    "history": ["temple", "museum", "literature", "old quarter"],
}

ADDRESS_CUE_RE = re.compile(
    r"\b(?:address|addr\.?|located at|location|địa chỉ|dia chi|ở tại|ở|tai|tại)\b"
    r"\s*(?:is|là|:|-)?\s*(?P<address>[^.!?\n]{6,140})",
    flags=re.IGNORECASE,
)


class UrlReelContextExtractor:
    def extract(self, metadata: UrlMetadata, transcript: str, destination: str | None = None) -> ExtractedContext:
        metadata_text = "\n".join(part for part in [metadata.title, metadata.description] if part)
        combined = "\n".join(part for part in [metadata_text, transcript, destination] if part)
        places = self._extract_places(
            metadata_text=metadata_text,
            transcript=transcript,
            destination=destination,
        )
        place_details = self._place_details(
            places=places,
            destination=destination,
            metadata=metadata,
            metadata_text=metadata_text,
            transcript=transcript,
        )
        interests = self._extract_interests(combined)
        confidence = 0.3
        if transcript:
            confidence += 0.25
        if places:
            confidence += 0.15
        return ExtractedContext(
            extractedPlaces=places,
            extractedPlaceDetails=place_details,
            interests=interests,
            constraints=[],
            confidence=min(confidence, 1.0),
            notes=["extracted from metadata and audio transcript signals"],
        )

    def _extract_places(
        self,
        metadata_text: str,
        transcript: str,
        destination: str | None,
    ) -> list[str]:
        candidates: list[tuple[str, int]] = []
        if destination:
            candidates.append((destination, 100))

        for phrase in self._keyword_phrases(metadata_text, transcript):
            score = self._score_place_candidate(phrase, source="speech")
            if score > 0:
                candidates.append((phrase, score))

        return self._dedupe_ranked(candidates)[:12]

    def _keyword_phrases(self, *texts: str) -> list[str]:
        joined = "\n".join(text for text in texts if text)
        phrases: list[str] = []
        for sentence in re.split(r"[\n.!?]", joined):
            clean_sentence = re.sub(r"\s+", " ", sentence).strip(" .,;:-")
            lower = clean_sentence.lower()
            if not clean_sentence or not any(keyword in lower for keyword in PLACE_KEYWORDS):
                continue
            phrases.extend(self._extract_title_chunks(clean_sentence))
        return phrases

    def _extract_title_chunks(self, text: str) -> list[str]:
        return [
            self._normalize_candidate(match)
            for match in re.findall(
                r"\b[A-Z][A-Za-z&]+(?:\s+(?:of|the|and|[A-Z][A-Za-z&]+)){0,5}\b",
                text,
            )
            if len(match.strip()) >= 3
        ]

    def _score_place_candidate(self, candidate: str, source: str) -> int:
        cleaned = candidate.strip()
        lower = cleaned.lower()
        if len(cleaned) < 3 or any(term in lower for term in NOISE_TERMS):
            return 0
        if lower in GENERIC_PLACE_TERMS or lower in {"i know", "so come", "and finally", "the same", "michelin", "and the", "bami and"}:
            return 0
        if re.fullmatch(r"[A-Z]{2,}\d*", cleaned) and len(cleaned) <= 8:
            return 0
        if re.fullmatch(r"[\W\d_]+", cleaned):
            return 0

        score = 10
        if any(keyword in lower for keyword in PLACE_KEYWORDS):
            score += 30
        if re.search(r"\b[A-Z][A-Za-zÀ-ỹ]+", cleaned):
            score += 15
        word_count = len(cleaned.split())
        if word_count == 1:
            return 0
        if 1 <= word_count <= 5:
            score += 10
        if word_count > 7:
            score -= 30
        return max(score, 0)

    def _dedupe_ranked(self, candidates: list[tuple[str, int]]) -> list[str]:
        ranked: dict[str, tuple[str, int]] = {}
        for candidate, score in candidates:
            cleaned = self._normalize_candidate(candidate)
            if not cleaned:
                continue
            key = re.sub(r"[^a-z0-9à-ỹ]+", "", cleaned.lower())
            if not key:
                continue
            previous = ranked.get(key)
            if previous is None or score > previous[1]:
                ranked[key] = (cleaned, score)

        return [
            candidate
            for candidate, _score in sorted(
                ranked.values(),
                key=lambda item: (-item[1], item[0].lower()),
            )
        ]

    def _normalize_candidate(self, candidate: str) -> str:
        cleaned = re.sub(r"\s+", " ", candidate).strip(" .,;:-")
        cleaned = re.sub(r"^(?:at|in|on|to)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^the\s+", "", cleaned)
        cleaned = re.split(r"\s*,\s*(?:cheapest|world|michelin)", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = re.sub(r"\b(?:from|spot|historical|world's|cheapest)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:-")
        lower = cleaned.lower()
        if lower in GENERIC_PLACE_TERMS or re.search(r"\bshopping in\b", lower):
            return ""
        return cleaned

    def _extract_interests(self, text: str) -> list[str]:
        lower_text = text.lower()
        interests: list[str] = []
        for interest, keywords in INTEREST_KEYWORDS.items():
            if any(keyword in lower_text for keyword in keywords):
                interests.append(interest)
        return interests

    def _place_details(
        self,
        places: list[str],
        destination: str | None,
        metadata: UrlMetadata,
        metadata_text: str,
        transcript: str,
    ) -> list[ExtractedPlace]:
        address_hints = self._address_hints(
            places=places,
            metadata=metadata,
            metadata_text=metadata_text,
            transcript=transcript,
        )
        destination_key = self._dedupe_key(destination or "")
        return [
            ExtractedPlace(
                name=place,
                address=None if self._dedupe_key(place) == destination_key else address_hints.get(self._dedupe_key(place)),
                source="url_reel",
                evidence=self._evidence_for_place(
                    place=place,
                    metadata_text=metadata_text,
                    transcript=transcript,
                    prefer_address=bool(address_hints.get(self._dedupe_key(place))),
                ),
            )
            for place in places
        ]

    def _address_hints(
        self,
        places: list[str],
        metadata: UrlMetadata,
        metadata_text: str,
        transcript: str,
    ) -> dict[str, str]:
        hints: dict[str, str] = {}
        direct_address = self._metadata_address(metadata)
        metadata_places = self._extract_places(metadata_text=metadata_text, transcript="", destination=None)
        if direct_address:
            for place in metadata_places:
                hints[self._dedupe_key(place)] = direct_address

        for sentence in self._sentences(metadata_text, transcript):
            address = self._address_from_sentence(sentence)
            if not address:
                continue
            sentence_key = self._dedupe_key(sentence)
            for place in places:
                key = self._dedupe_key(place)
                if key and key in sentence_key and key not in hints:
                    hints[key] = address
            for place in self._keyword_phrases(sentence):
                key = self._dedupe_key(place)
                if key and key not in hints:
                    hints[key] = address
        return hints

    def _metadata_address(self, metadata: UrlMetadata) -> str | None:
        for key in ("address", "street_address", "location", "venue", "place"):
            value = metadata.raw.get(key)
            if isinstance(value, str):
                address = self._normalize_address(value)
                if address:
                    return address
        return None

    def _address_from_sentence(self, sentence: str) -> str | None:
        match = ADDRESS_CUE_RE.search(sentence)
        if not match:
            return None
        return self._normalize_address(match.group("address"))

    def _normalize_address(self, value: str) -> str | None:
        cleaned = re.sub(r"\s+", " ", value).strip(" .,;:-")
        cleaned = re.split(r"\s+(?:and|then|before|after|but|with|và|rồi|sau đó)\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = cleaned.strip(" .,;:-")
        if len(cleaned) < 6 or cleaned.lower() in GENERIC_PLACE_TERMS:
            return None
        return cleaned

    def _evidence_for_place(self, place: str, metadata_text: str, transcript: str, prefer_address: bool = False) -> str | None:
        key = self._dedupe_key(place)
        sentences = self._sentences(metadata_text, transcript)
        if prefer_address:
            address_sentences = [sentence for sentence in sentences if self._address_from_sentence(sentence)]
            sentences = [*address_sentences, *sentences]
        for sentence in sentences:
            if key and key in self._dedupe_key(sentence):
                return sentence
        return None

    def _sentences(self, *texts: str) -> list[str]:
        joined = "\n".join(text for text in texts if text)
        return [
            re.sub(r"\s+", " ", sentence).strip()
            for sentence in re.split(r"[\n.!?]", joined)
            if sentence.strip()
        ]

    def _dedupe_key(self, value: str) -> str:
        return re.sub(r"[^a-z0-9à-ỹ]+", "", value.lower())
