from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    ExtractedPlace,
    FrameVisionObservation,
    SpeechToTextObservation,
    UrlMetadata,
)


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
    "biển",
    "beach",
    "núi",
    "mountain",
    "chợ",
    "night market",
    "spa",
    "bar",
    "club",
    "gallery",
    "art",
    "lake",
    "street",
]

GENERIC_PLACE_TERMS = {
    "ban quan",
    "banh cuon",
    "banh mi",
    "bun cha",
    "coffee",
    "cafe",
    "kem xoi",
    "night bus tour",
    "pho",
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
    "video info",
    "or our",
    "street guide",
    "maison centrale",
}


INTEREST_KEYWORDS = {
    "coffee": ["coffee", "cafe", "café"],
    "food": ["food", "restaurant", "michelin", "banh", "pho", "bun", "street food"],
    "shopping": ["shopping", "market", "vintage"],
    "history": ["temple", "museum", "literature", "old quarter"],
    "nature": ["nature", "park", "waterfall", "mountain", "hiking", "thiên nhiên", "núi", "thác"],
    "beach": ["beach", "coast", "island", "biển", "đảo"],
    "culture": ["culture", "heritage", "gallery", "art", "văn hóa", "di sản"],
    "nightlife": ["nightlife", "night market", "bar", "club", "chợ đêm"],
    "wellness": ["spa", "massage", "wellness", "yoga"],
    "adventure": ["adventure", "hiking", "trekking", "kayak", "mạo hiểm"],
    "family": ["family", "kids", "children", "gia đình", "trẻ em"],
}

ATTRIBUTE_KEYWORDS = {
    "local": ["local", "địa phương", "bản địa"],
    "hidden_gem": ["hidden gem", "ít người biết", "bí mật"],
    "photogenic": ["photogenic", "check-in", "instagrammable", "sống ảo"],
    "quiet": ["quiet", "yên tĩnh", "chill"],
    "crowded": ["crowded", "đông", "xếp hàng", "queue"],
    "budget": ["budget", "cheap", "affordable", "giá rẻ", "bình dân"],
    "premium": ["premium", "luxury", "fine dining", "cao cấp", "sang trọng"],
    "family_friendly": ["family friendly", "kids", "gia đình", "trẻ em"],
    "outdoor": ["outdoor", "ngoài trời", "hiking", "beach", "park"],
    "late_night": ["late night", "night market", "mở khuya", "chợ đêm"],
    "romantic": ["romantic", "date night", "lãng mạn", "hẹn hò"],
    "accessible": ["wheelchair", "accessible", "xe lăn", "thang máy"],
}

ADDRESS_CUE_RE = re.compile(
    r"\b(?:address|addr\.?|located at|location|địa chỉ|dia chi|ở tại|ở|tai|tại)\b"
    r"\s*(?:is|là|:|-)?\s*(?P<address>[^.!?\n]{6,140})",
    flags=re.IGNORECASE,
)

DAY_NUMBER_BY_WORD = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

# A plain "went to X" often names a venue, not a new routing region. Keep that
# weaker cue limited to well-known Vietnamese trip regions. Explicit
# "day trip/tour to X" wording remains usable for destinations outside this set.
VIETNAM_SEARCH_REGIONS = {
    "an giang",
    "bac ninh",
    "ca mau",
    "can tho",
    "cao bang",
    "da nang",
    "dak lak",
    "dien bien",
    "dong nai",
    "dong thap",
    "gia lai",
    "ha noi",
    "hai phong",
    "ho chi minh",
    "hue",
    "hung yen",
    "khanh hoa",
    "lai chau",
    "lam dong",
    "lang son",
    "lao cai",
    "ninh binh",
    "nghe an",
    "phu tho",
    "quang ngai",
    "quang ninh",
    "quang tri",
    "son la",
    "tay ninh",
    "thanh hoa",
    "thai nguyen",
    "tuyen quang",
    "vinh long",
}


class UrlReelContextExtractor:
    def extract(
        self,
        metadata: UrlMetadata,
        transcript: str,
        speech_observations: list[SpeechToTextObservation] | None = None,
        destination: str | None = None,
        visual_text: str = "",
        visual_places: list[str] | None = None,
        visual_observations: list[FrameVisionObservation] | None = None,
    ) -> ExtractedContext:
        metadata_text = "\n".join(part for part in [metadata.title, metadata.description] if part)
        structured_stt_text = "\n".join(
            observation.evidence
            for observation in speech_observations or []
            if observation.evidence
        )
        combined = "\n".join(
            part
            for part in [
                metadata_text,
                (
                    structured_stt_text
                    if speech_observations is not None
                    else transcript
                ),
                visual_text,
                destination,
            ]
            if part
        )
        places = self._extract_places(
            metadata_text=metadata_text,
            transcript=transcript,
            destination=destination,
            visual_places=visual_places or [],
            speech_observations=speech_observations,
            visual_observations=visual_observations or [],
        )
        place_details = self._place_details(
            places=places,
            destination=destination,
            metadata=metadata,
            metadata_text=metadata_text,
            transcript=transcript,
            speech_observations=speech_observations,
            visual_text=visual_text,
            visual_observations=visual_observations or [],
        )
        places = [detail.name for detail in place_details]
        interests = self._extract_interests(combined)
        confidence = 0.3
        if transcript:
            confidence += 0.25
        if visual_text:
            confidence += 0.15
        if places:
            confidence += 0.15
        if speech_observations:
            confidence = max(
                confidence,
                sum(
                    observation.confidence
                    for observation in speech_observations
                )
                / len(speech_observations),
            )
        return ExtractedContext(
            extractedPlaces=places,
            extractedPlaceDetails=place_details,
            interests=interests,
            constraints=[],
            confidence=min(confidence, 1.0),
            notes=[
                "extracted from metadata, audio transcript, and sampled frame "
                "vision signals"
            ],
        )

    def _extract_places(
        self,
        metadata_text: str,
        transcript: str,
        destination: str | None,
        visual_places: list[str] | None = None,
        speech_observations: list[SpeechToTextObservation] | None = None,
        visual_observations: list[FrameVisionObservation] | None = None,
    ) -> list[str]:
        candidates: list[tuple[str, int]] = []
        metadata_phrases = self._metadata_itinerary_phrases(metadata_text)
        for phrase in metadata_phrases:
            candidates.append((phrase, 120))

        for observation in sorted(
            speech_observations or [],
            key=lambda item: item.order,
        ):
            cleaned = self._normalize_candidate(observation.place_name)
            if cleaned and cleaned.lower() not in GENERIC_PLACE_TERMS:
                candidates.append((cleaned, 140))

        ordered_visual_observations = sorted(
            visual_observations or [],
            key=lambda item: item.order or 10_000,
        )
        observed_visual_names: set[str] = set()
        for observation in ordered_visual_observations:
            cleaned = self._normalize_candidate(observation.place_name)
            if cleaned and cleaned.lower() not in GENERIC_PLACE_TERMS:
                candidates.append((cleaned, 150))
                observed_visual_names.add(self._dedupe_key(cleaned))

        for phrase in visual_places or []:
            cleaned = self._normalize_candidate(phrase)
            if (
                cleaned
                and cleaned.lower() not in GENERIC_PLACE_TERMS
                and self._dedupe_key(cleaned) not in observed_visual_names
            ):
                candidates.append((cleaned, 150))

        known_places = [
            candidate
            for candidate, _score in candidates
        ]
        transcript_fallback = (
            transcript
            if speech_observations is None
            else ""
        )
        for phrase in self._keyword_phrases(
            metadata_text,
            transcript_fallback,
        ):
            if any(
                self._same_place_name(phrase, known)
                for known in known_places
            ):
                continue
            score = self._score_place_candidate(phrase, source="speech")
            if score > 0:
                candidates.append((phrase, score))
                known_places.append(phrase)

        places = self._dedupe_in_order(candidates)
        destination_key = self._dedupe_key(destination or "")
        return [
            place
            for place in places
            if self._dedupe_key(place) != destination_key
        ]

    def _same_place_name(self, left: str, right: str) -> bool:
        left_key = self._dedupe_key(left)
        right_key = self._dedupe_key(right)
        if not left_key or not right_key:
            return False
        if left_key in right_key or right_key in left_key:
            return True
        if SequenceMatcher(None, left_key, right_key).ratio() >= 0.82:
            return True
        left_first = self._dedupe_key(left.split()[0]) if left.split() else ""
        right_first = self._dedupe_key(right.split()[0]) if right.split() else ""
        return (
            left_first == right_first
            and SequenceMatcher(None, left_key, right_key).ratio() >= 0.62
        )

    def _metadata_itinerary_phrases(self, metadata_text: str) -> list[str]:
        phrases: list[str] = []
        for match in re.finditer(
            r"(?:📍|📌|🚂|🧑‍🍳)\s*([^📍📌🚂🧑#\n]+)",
            metadata_text,
        ):
            phrase = re.split(
                r"\s+(?:if you|for more|tap the|check out|send us)\b",
                match.group(1),
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            cleaned = self._normalize_candidate(phrase)
            if cleaned:
                phrases.append(cleaned)
        return phrases

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
                r"\b[A-ZÀ-ỸĐ][A-Za-zÀ-ỹĐđ&'-]+"
                r"(?:\s+(?:of|the|and|[A-ZÀ-ỸĐ0-9][A-Za-zÀ-ỹĐđ0-9&'-]+)){0,5}\b",
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

    def _dedupe_in_order(self, candidates: list[tuple[str, int]]) -> list[str]:
        ordered: dict[str, tuple[str, int]] = {}
        for candidate, score in candidates:
            cleaned = self._normalize_candidate(candidate)
            key = self._dedupe_key(cleaned)
            if not key:
                continue
            prefix_key = next(
                (
                    existing_key
                    for existing_key in ordered
                    if len(existing_key) >= 6
                    and (
                        key.startswith(existing_key)
                        or existing_key.startswith(key)
                    )
                ),
                None,
            )
            if prefix_key is not None:
                previous = ordered[prefix_key]
                if len(cleaned) > len(previous[0]) or score > previous[1]:
                    ordered[prefix_key] = (cleaned, max(score, previous[1]))
                continue
            previous = ordered.get(key)
            if previous is None:
                ordered[key] = (cleaned, score)
            elif score > previous[1]:
                ordered[key] = (cleaned, score)
        return [candidate for candidate, _score in ordered.values()]

    def _normalize_candidate(self, candidate: str) -> str:
        candidate = "".join(
            " "
            if unicodedata.category(character) == "So" or character == "\ufe0f"
            else character
            for character in candidate
        )
        cleaned = re.sub(r"\s+", " ", candidate).strip(" .,;:-")
        cleaned = re.sub(
            r"^(?:at|in|on|to|visit)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^the\s+", "", cleaned)
        cleaned = re.split(r"\s*,\s*(?:cheapest|world|michelin)", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = re.sub(r"\b(?:from|spot|historical|world's|cheapest)\b", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.split(
            r"\s+(?:if|guide|for our|or our|find video info)\b",
            cleaned,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
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
        visual_text: str,
        speech_observations: list[SpeechToTextObservation] | None = None,
        visual_observations: list[FrameVisionObservation] | None = None,
    ) -> list[ExtractedPlace]:
        structured_stt_text = "\n".join(
            observation.evidence
            for observation in speech_observations or []
            if observation.evidence
        )
        stt_evidence_text = (
            structured_stt_text
            if speech_observations is not None
            else transcript
        )
        combined_evidence_text = "\n".join(
            part for part in (stt_evidence_text, visual_text) if part
        )
        address_hints = self._address_hints(
            places=places,
            metadata=metadata,
            metadata_text=metadata_text,
            transcript=combined_evidence_text,
        )
        destination_key = self._dedupe_key(destination or "")
        source_text = (
            metadata_text
            if speech_observations is not None
            else f"{metadata_text}\n{combined_evidence_text}"
        )
        multi_day = bool(
            re.search(
                r"\b(?:[2-9]|[12]\d|30)\s*[- ]day\b"
                r"|\bday\s+(?:two|three|four|five|six|seven|eight|nine|ten|[2-9]|[12]\d|30)\b",
                source_text,
                flags=re.IGNORECASE,
            )
        )
        single_day = not multi_day and bool(
            re.search(
                r"\b(?:perfect|first|one)\s+day\b|\bday\s+trip\b",
                source_text,
                flags=re.IGNORECASE,
            )
        )
        details: list[ExtractedPlace] = []
        observations_by_place = {
            self._dedupe_key(observation.place_name): observation
            for observation in visual_observations or []
        }
        speech_observations_by_place = {
            self._dedupe_key(observation.place_name): observation
            for observation in speech_observations or []
        }
        transcript_days = (
            [None for _place in places]
            if speech_observations is not None
            else [
                self._transcript_day_for_place(place, transcript)
                for place in places
            ]
        )
        for index, day in enumerate(transcript_days):
            if day is not None:
                continue
            previous_day = next(
                (
                    known_day
                    for known_day in reversed(transcript_days[:index])
                    if known_day is not None
                ),
                None,
            )
            next_day = next(
                (
                    known_day
                    for known_day in transcript_days[index + 1 :]
                    if known_day is not None
                ),
                None,
            )
            if previous_day is not None and previous_day == next_day:
                transcript_days[index] = previous_day
        day_regions = (
            {}
            if speech_observations is not None
            else self._day_region_hints(
                transcript,
                destination=destination,
            )
        )
        for order, place in enumerate(places, start=1):
            observation = self._matching_observation(
                place,
                observations_by_place,
            )
            speech_observation = self._matching_observation(
                place,
                speech_observations_by_place,
            )
            address = address_hints.get(self._dedupe_key(place))
            speech_evidence = (
                speech_observation.evidence
                if speech_observation is not None
                else self._evidence_for_place(
                    place=place,
                    metadata_text="",
                    transcript=transcript,
                    prefer_address=bool(address),
                )
                if speech_observations is None
                else ""
            )
            visual_evidence = (
                observation.evidence
                if observation is not None and observation.evidence
                else self._evidence_for_place(
                    place=place,
                    metadata_text="",
                    transcript=visual_text,
                )
            )
            caption_evidence = self._evidence_for_place(
                place=place,
                metadata_text=metadata_text,
                transcript="",
            )
            evidence = (
                visual_evidence
                or speech_evidence
                or caption_evidence
            )
            source_evidence = {
                source: value
                for source, value in (
                    ("ocr", visual_evidence),
                    ("stt", speech_evidence),
                    ("caption", caption_evidence),
                )
                if value
            }
            local_evidence = " ".join(source_evidence.values()) or place
            source_day = transcript_days[order - 1]
            if (
                speech_observation is not None
                and speech_observation.day_number is not None
            ):
                source_day = speech_observation.day_number
            elif (
                source_day is None
                and observation is not None
                and observation.day_number is not None
            ):
                source_day = observation.day_number
            elif source_day is None and single_day:
                source_day = 1

            source_order = order
            if (
                speech_observation is not None
                and speech_observation.order is not None
            ):
                source_order = speech_observation.order
            if observation is not None and observation.order is not None:
                source_order = observation.order

            source_time_hint = self._time_hint(speech_evidence or "")
            if speech_observation is not None and speech_observation.time_hint:
                source_time_hint = speech_observation.time_hint
            elif (
                not source_time_hint
                and observation is not None
                and observation.time_hint
            ):
                source_time_hint = observation.time_hint
            if not source_time_hint:
                source_time_hint = self._time_hint(local_evidence)

            source_activity = None
            if speech_observation is not None and speech_observation.activity:
                source_activity = speech_observation.activity
            elif observation is not None and observation.activity:
                source_activity = observation.activity

            search_region = destination
            if source_day is not None:
                search_region = day_regions.get(source_day) or destination
            if (
                speech_observation is not None
                and speech_observation.search_region
            ):
                search_region = speech_observation.search_region

            source_duration_minutes = (
                speech_observation.duration_minutes
                if speech_observation is not None
                else None
            )
            details.append(
                ExtractedPlace(
                    name=place,
                    category=self._category_for_place(place, local_evidence, ""),
                    address=(
                        None
                        if self._dedupe_key(place) == destination_key
                        else address
                    ),
                    searchRegion=search_region,
                    source="url_reel",
                    evidence=evidence,
                    sourceEvidence=source_evidence,
                    attributes=self._attributes_for_place(
                        place,
                        local_evidence,
                        "",
                    ),
                    sourceOrder=source_order,
                    sourceDay=source_day,
                    sourceTimeHint=source_time_hint,
                    sourceActivity=source_activity,
                    sourceDurationMinutes=source_duration_minutes,
                )
            )
        return sorted(
            details,
            key=lambda detail: (
                detail.source_order is None,
                detail.source_order or 10_000,
                detail.source_day or 10_000,
            ),
        )

    def _matching_observation(
        self,
        place: str,
        observations_by_place: dict[
            str,
            FrameVisionObservation | SpeechToTextObservation,
        ],
    ) -> FrameVisionObservation | SpeechToTextObservation | None:
        exact = observations_by_place.get(self._dedupe_key(place))
        if exact is not None:
            return exact
        return next(
            (
                observation
                for observation in observations_by_place.values()
                if self._same_place_name(place, observation.place_name)
            ),
            None,
        )

    def _day_region_hints(
        self,
        transcript: str,
        *,
        destination: str | None,
    ) -> dict[int, str]:
        current_day: int | None = None
        regions: dict[int, str] = {}
        for sentence in self._sentences(transcript):
            marker = re.search(
                r"\b(?:on\s+)?day\s+"
                r"(?P<day>one|two|three|four|five|six|seven|eight|nine|ten|[1-9]|[12]\d|30)\b",
                sentence,
                flags=re.IGNORECASE,
            )
            if marker:
                raw_day = marker.group("day").casefold()
                current_day = (
                    int(raw_day)
                    if raw_day.isdigit()
                    else DAY_NUMBER_BY_WORD[raw_day]
                )
            if current_day is None:
                continue
            region = self._region_from_sentence(sentence)
            if (
                region
                and self._dedupe_key(region)
                != self._dedupe_key(destination or "")
            ):
                regions[current_day] = region
        return regions

    def _region_from_sentence(self, sentence: str) -> str | None:
        for pattern, require_known_region in (
            (
                r"\b(?:day|nature|overnight|weekend)?\s*"
                r"(?:trip|tour)\s+to\s+(?P<region>.+)$",
                False,
            ),
            (
                r"\b(?:went|go|headed|travelled|traveled)\s+to\s+"
                r"(?P<region>.+)$",
                True,
            ),
        ):
            match = re.search(pattern, sentence, flags=re.IGNORECASE)
            if match is None:
                continue
            region = re.split(
                r",|\s+(?:for|where|and|then|but|which|that|to see)\b",
                match.group("region"),
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip(" ,.;:-")
            words = region.split()
            if not 1 <= len(words) <= 5:
                continue
            normalized_words = " ".join(words).casefold()
            if normalized_words.startswith(("see ", "visit ")):
                continue
            region_key = re.sub(
                r"[^a-z0-9]+",
                " ",
                "".join(
                    character
                    for character in unicodedata.normalize(
                        "NFD",
                        region.casefold(),
                    )
                    if unicodedata.category(character) != "Mn"
                ).replace("đ", "d"),
            ).strip()
            if (
                require_known_region
                and region_key not in VIETNAM_SEARCH_REGIONS
            ):
                continue
            if region:
                return region
        return None

    def _transcript_day_for_place(
        self,
        place: str,
        transcript: str,
    ) -> int | None:
        current_day: int | None = None
        for sentence in self._sentences(transcript):
            marker = re.search(
                r"\b(?:on\s+)?day\s+"
                r"(?P<day>one|two|three|four|five|six|seven|eight|nine|ten|[1-9]|[12]\d|30)\b",
                sentence,
                flags=re.IGNORECASE,
            )
            if marker:
                raw_day = marker.group("day").casefold()
                current_day = (
                    int(raw_day)
                    if raw_day.isdigit()
                    else DAY_NUMBER_BY_WORD[raw_day]
                )
            if (
                current_day is not None
                and self._sentence_mentions_place(sentence, place)
            ):
                return current_day
        return None

    def _sentence_mentions_place(self, sentence: str, place: str) -> bool:
        place_key = self._dedupe_key(place)
        sentence_key = self._dedupe_key(sentence)
        if not place_key:
            return False
        if place_key in sentence_key:
            return True

        place_words = re.findall(r"[A-Za-zÀ-ỹĐđ0-9]+", place)
        sentence_words = re.findall(r"[A-Za-zÀ-ỹĐđ0-9]+", sentence)
        if not place_words or not sentence_words:
            return False
        for width in {
            max(1, len(place_words) - 1),
            len(place_words),
            len(place_words) + 1,
        }:
            for start in range(0, len(sentence_words) - width + 1):
                window_key = self._dedupe_key(
                    " ".join(sentence_words[start : start + width])
                )
                if (
                    SequenceMatcher(None, place_key, window_key).ratio()
                    >= 0.82
                ):
                    return True
        return False

    def _time_hint(self, evidence: str) -> str | None:
        lowered = evidence.casefold()
        for hint in (
            "after dinner",
            "before lunch",
            "late afternoon",
            "early afternoon",
            "breakfast",
            "morning",
            "lunch",
            "afternoon",
            "dinnertime",
            "dinner",
            "evening",
            "nightlife",
            "night",
        ):
            if hint in lowered:
                return "dinner" if hint == "dinnertime" else hint
        return None

    def _category_for_place(
        self,
        place: str,
        metadata_text: str,
        transcript: str,
    ) -> str:
        text = " ".join((place, metadata_text, transcript)).lower()
        if any(term in text for term in ("coffee", "cafe", "café")):
            return "cafe"
        if any(
            term in text
            for term in (
                "restaurant",
                "food",
                "mì",
                "mi ",
                "phở",
                "pho",
                "bánh",
                "banh",
                "bún",
                "bun ",
                "quán ăn",
                "breakfast",
                "sticky rice",
                "rice",
                "xôi",
            )
        ):
            return "food"
        if any(term in text for term in ("hotel", "homestay", "resort")):
            return "hotel"
        if any(
            term in text
            for term in ("station", "airport", "bus stop", "train station")
        ):
            return "transport"
        if any(
            term in text
            for term in (
                "temple",
                "museum",
                "bridge",
                "quarter",
                "prison",
                "histor",
                "cooking class",
            )
        ):
            return "culture"
        if any(term in text for term in ("beach", "coast", "island", "biển", "đảo")):
            return "beach"
        if any(
            term in text
            for term in (
                "park",
                "lake",
                "waterfall",
                "mountain",
                "forest",
                "núi",
                "thác",
            )
        ):
            return "nature"
        if any(term in text for term in ("market", "shopping", "mall", "chợ")):
            return "shopping"
        if "train street" in text:
            return "attraction"
        if any(
            term in text
            for term in ("nightlife", "night market", "bar", "club", "chợ đêm")
        ):
            return "nightlife"
        if any(term in text for term in ("spa", "massage", "wellness", "yoga")):
            return "wellness"
        if any(term in text for term in ("hiking", "trekking", "kayak", "adventure")):
            return "adventure"
        if any(term in text for term in ("family", "kids", "children", "gia đình")):
            return "family"
        return "other"

    def _attributes_for_place(
        self,
        place: str,
        metadata_text: str,
        transcript: str,
    ) -> list[str]:
        text = " ".join((place, metadata_text, transcript)).casefold()
        return [
            attribute
            for attribute, keywords in ATTRIBUTE_KEYWORDS.items()
            if any(keyword in text for keyword in keywords)
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
        sentences = self._sentences(transcript, metadata_text)
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
        decomposed = unicodedata.normalize("NFD", value.strip().casefold())
        without_marks = "".join(
            character
            for character in decomposed
            if unicodedata.category(character) != "Mn"
        ).replace("đ", "d")
        return re.sub(r"[^a-z0-9]+", "", without_marks)
