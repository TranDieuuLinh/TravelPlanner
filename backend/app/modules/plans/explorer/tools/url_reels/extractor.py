from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from app.modules.plans.explorer.tools.url_reels.schema import (
    ExtractedContext,
    ExtractedDestinationStay,
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
    "cathedral",
    "church",
    "pagoda",
    "mausoleum",
    "square",
    "theater",
    "theatre",
]

GENERIC_PLACE_TERMS = {
    "ban quan",
    "banh cuon",
    "banh mi",
    "bun cha",
    "coffee",
    "cute cafes",
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
    "danang",
    "dak lak",
    "dien bien",
    "dong nai",
    "dong thap",
    "gia lai",
    "ha noi",
    "hanoi",
    "ha giang",
    "hai phong",
    "ho chi minh",
    "hochiminh",
    "hoi an",
    "hoian",
    "hue",
    "hung yen",
    "khanh hoa",
    "lai chau",
    "lam dong",
    "lang son",
    "lao cai",
    "da lat",
    "ninh binh",
    "ninhbinh",
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
    "sa pa",
    "sapa",
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
        destination_stays = self._destination_stays(
            metadata_text=metadata_text,
            visual_text=visual_text,
            speech_observations=speech_observations or [],
            visual_observations=visual_observations or [],
            visual_places=visual_places or [],
            destination=destination,
        )
        places = self._extract_places(
            metadata=metadata,
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
        stay_names = {
            self._location_identity(stay.name)
            for stay in destination_stays
        }
        place_details = [
            detail
            for detail in place_details
            if self._location_identity(detail.name) not in stay_names
            and self._parse_destination_stay_heading(detail.name) is None
        ]
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
            destinationStays=destination_stays,
            interests=interests,
            constraints=[],
            confidence=min(confidence, 1.0),
            notes=[
                "extracted from metadata, audio transcript, and sampled frame "
                "vision signals"
            ],
        )

    def _destination_stays(
        self,
        *,
        metadata_text: str,
        visual_text: str,
        speech_observations: list[SpeechToTextObservation],
        visual_observations: list[FrameVisionObservation],
        visual_places: list[str],
        destination: str | None,
    ) -> list[ExtractedDestinationStay]:
        headings: list[tuple[int, str, int, int | None, str]] = []
        for observation in speech_observations:
            parsed = self._parse_destination_stay_heading(
                observation.place_name,
                destination=destination,
            )
            if parsed is not None:
                name, duration_days = parsed
                headings.append(
                    (
                        observation.order,
                        name,
                        duration_days,
                        observation.day_number,
                        observation.evidence or observation.place_name,
                    )
                )
        for fallback_order, observation in enumerate(
            visual_observations,
            start=1,
        ):
            parsed = self._parse_destination_stay_heading(
                observation.place_name,
                destination=destination,
            )
            if parsed is not None:
                name, duration_days = parsed
                headings.append(
                    (
                        observation.order or fallback_order,
                        name,
                        duration_days,
                        observation.day_number,
                        observation.evidence or observation.place_name,
                    )
                )
        for fallback_order, value in enumerate(visual_places, start=1):
            parsed = self._parse_destination_stay_heading(
                value,
                destination=destination,
            )
            if parsed is not None:
                name, duration_days = parsed
                headings.append(
                    (fallback_order, name, duration_days, None, value)
                )
        for fallback_order, line in enumerate(metadata_text.splitlines(), start=1):
            parsed = self._parse_destination_stay_heading(
                line,
                destination=destination,
            )
            if parsed is not None:
                name, duration_days = parsed
                headings.append(
                    (fallback_order, name, duration_days, None, line.strip())
                )
        for fallback_order, line in enumerate(visual_text.splitlines(), start=1):
            evidence = line.rsplit("|", 1)[-1].strip()
            parsed = self._parse_destination_stay_heading(
                evidence,
                destination=destination,
            )
            if parsed is not None:
                name, duration_days = parsed
                headings.append(
                    (fallback_order, name, duration_days, None, evidence)
                )

        deduped: dict[str, tuple[int, str, int, int | None, str]] = {}
        for heading in sorted(headings, key=lambda item: item[0]):
            key = self._location_identity(heading[1])
            if key and key not in deduped:
                deduped[key] = heading

        stays: list[ExtractedDestinationStay] = []
        next_day = 1
        for order, name, duration_days, explicit_day, evidence in deduped.values():
            start_day = explicit_day or next_day
            end_day = min(30, start_day + duration_days - 1)
            stays.append(
                ExtractedDestinationStay(
                    name=name,
                    durationDays=end_day - start_day + 1,
                    startDay=start_day,
                    endDay=end_day,
                    sourceOrder=order,
                    evidence=evidence,
                )
            )
            next_day = end_day + 1
        return stays

    def _parse_destination_stay_heading(
        self,
        value: str,
        *,
        destination: str | None = None,
    ) -> tuple[str, int] | None:
        normalized = re.sub(r"\s+", " ", value).strip(" \t\r\n-|:–—")
        match = re.fullmatch(
            r"(?P<name>[^|:\-–—\n]{2,80}?)\s*(?:[-:|–—]\s*)?"
            r"(?P<days>\d{1,2})\s*(?:days?|ngày)\b",
            normalized,
            flags=re.IGNORECASE,
        )
        if match is None:
            return None
        days = int(match.group("days"))
        if not 1 <= days <= 30:
            return None
        name = match.group("name").strip(" \t-|:–—")
        location_key = " ".join(
            re.findall(
                r"[a-z0-9]+",
                "".join(
                    character
                    for character in unicodedata.normalize(
                        "NFD",
                        name.casefold(),
                    )
                    if unicodedata.category(character) != "Mn"
                ).replace("đ", "d"),
            )
        )
        destination_key = self._location_identity(destination or "")
        if (
            location_key not in VIETNAM_SEARCH_REGIONS
            and self._location_identity(name) != destination_key
        ):
            return None
        return name, days

    def _extract_places(
        self,
        metadata_text: str,
        transcript: str,
        destination: str | None,
        metadata: UrlMetadata | None = None,
        visual_places: list[str] | None = None,
        speech_observations: list[SpeechToTextObservation] | None = None,
        visual_observations: list[FrameVisionObservation] | None = None,
    ) -> list[str]:
        candidates: list[tuple[str, int]] = []
        numbered_places = self._numbered_itinerary_places(transcript)
        for phrase in numbered_places:
            candidates.append((phrase, 190))

        metadata_place = self._metadata_place_name(metadata)
        authoritative_places = self._authoritative_metadata_places(
            metadata,
            metadata_text,
            destination,
        )
        if (
            not numbered_places
            and metadata_place
            and authoritative_places[:1] == [metadata_place]
        ):
            candidates.append((metadata_place, 200))
        metadata_phrases = [
            phrase
            for phrase in authoritative_places
            if phrase != metadata_place
        ]
        for phrase in metadata_phrases:
            candidates.append((phrase, 180))

        for observation in sorted(
            speech_observations or [],
            key=lambda item: item.order,
        ):
            cleaned = self._normalize_candidate(observation.place_name)
            if (
                cleaned
                and cleaned.lower() not in GENERIC_PLACE_TERMS
                and not any(
                    self._same_place_name(cleaned, authoritative)
                    for authoritative in authoritative_places
                )
            ):
                candidates.append((cleaned, 140))

        ordered_visual_observations = sorted(
            visual_observations or [],
            key=lambda item: item.order or 10_000,
        )
        observed_visual_names: set[str] = set()
        for observation in ordered_visual_observations:
            cleaned = self._normalize_candidate(observation.place_name)
            if (
                cleaned
                and cleaned.lower() not in GENERIC_PLACE_TERMS
                and not any(
                    self._same_place_name(cleaned, authoritative)
                    for authoritative in authoritative_places
                )
            ):
                candidates.append((cleaned, 150))
                observed_visual_names.add(self._dedupe_key(cleaned))

        for phrase in visual_places or []:
            cleaned = self._normalize_candidate(phrase)
            if (
                cleaned
                and cleaned.lower() not in GENERIC_PLACE_TERMS
                and self._dedupe_key(cleaned) not in observed_visual_names
                and not any(
                    self._same_place_name(cleaned, authoritative)
                    for authoritative in authoritative_places
                )
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
        heuristic_phrases = (
            []
            if numbered_places
            else self._keyword_phrases(
                metadata_text,
                transcript_fallback,
            )
        )
        for phrase in heuristic_phrases:
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
        return [
            place
            for place in places
            if not self._is_destination_alias(place, destination)
        ]

    def _numbered_itinerary_places(self, transcript: str) -> list[str]:
        """Extract explicit list headings before weaker title-case heuristics."""

        if not transcript:
            return []
        text = re.sub(r"\[(?:music|singing)\]|>>", " ", transcript, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        number_word = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|[1-9]|10)"
        matches = list(
            re.finditer(
                rf"\b(?:starting\s+at\s+)?number\s+(?P<number>{number_word})\b",
                text,
                flags=re.IGNORECASE,
            )
        )
        if len(matches) < 2:
            return []

        places: list[str] = []
        seen_numbers: set[str] = set()
        for index, match in enumerate(matches):
            number_key = match.group("number").casefold()
            if number_key in seen_numbers:
                continue
            seen_numbers.add(number_key)
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            heading = text[match.end() : min(end, match.end() + 360)].strip(" ,:-")
            visit_match = re.search(
                r"\bwhich\s+is\s+to\s+visit\s+(?P<place>[^.]+)",
                heading,
                flags=re.IGNORECASE,
            )
            if visit_match is not None:
                heading = visit_match.group("place")
            else:
                heading = re.sub(
                    r"^(?:which\s+is\s+going\s+to\s+be|is|which\s+is)\s+",
                    "",
                    heading,
                    flags=re.IGNORECASE,
                )
                heading = heading.replace("St. ", "St ")
                heading = heading.split(".", 1)[0]
            heading = re.split(
                r"\s+(?:because|and\s+actually|and\s+I\s+don['’]?t|"
                r"which\s+is\s+arguably|but\s+definitely)\b",
                heading,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            heading = heading.strip(" ,:-")
            if re.match(r"^(?:to\s+)?eat\b", heading, flags=re.IGNORECASE):
                continue
            for place in self._split_numbered_place_heading(heading):
                cleaned = self._normalize_candidate(place)
                if cleaned and cleaned.casefold() not in GENERIC_PLACE_TERMS:
                    places.append(cleaned)
        return places

    def _split_numbered_place_heading(self, heading: str) -> list[str]:
        slash_parts = [
            part.strip()
            for part in re.split(r"\s*/\s*", heading)
            if part.strip()
        ]
        output: list[str] = []
        place_suffix = re.compile(
            r"\b(?:lake|temple|pagoda|cathedral|church|mausoleum|square|"
            r"prison|street|theat(?:er|re))\b",
            flags=re.IGNORECASE,
        )
        for part in slash_parts:
            conjunction = re.fullmatch(
                r"(?P<left>.+?)\s+and\s+(?P<right>.+)",
                part,
                flags=re.IGNORECASE,
            )
            if (
                conjunction is not None
                and place_suffix.search(conjunction.group("left"))
                and place_suffix.search(conjunction.group("right"))
            ):
                output.extend(
                    [conjunction.group("left"), conjunction.group("right")]
                )
            else:
                output.append(part)
        return output

    def _same_place_name(self, left: str, right: str) -> bool:
        left_key = self._dedupe_key(left)
        right_key = self._dedupe_key(right)
        if not left_key or not right_key:
            return False
        if left_key in right_key or right_key in left_key:
            return True
        if SequenceMatcher(None, left_key, right_key).ratio() >= 0.82:
            return True
        left_tokens = self._place_name_tokens(left)
        right_tokens = self._place_name_tokens(right)
        if left_tokens and left_tokens == right_tokens:
            return True
        left_first = self._dedupe_key(left.split()[0]) if left.split() else ""
        right_first = self._dedupe_key(right.split()[0]) if right.split() else ""
        return (
            left_first == right_first
            and SequenceMatcher(None, left_key, right_key).ratio() >= 0.62
        )

    def _metadata_itinerary_phrases(
        self,
        metadata_text: str,
        destination: str | None = None,
    ) -> list[str]:
        phrases: list[str] = []
        for item in self._metadata_numbered_items(metadata_text):
            item = re.sub(
                r"^(?:visit|explore|see|shopping\s+at|eat\s+at|drink\s+at)\s+",
                "",
                item,
                flags=re.IGNORECASE,
            )
            if destination:
                item = re.sub(
                    rf"\s+in\s+{re.escape(destination)}\s*$",
                    "",
                    item,
                    flags=re.IGNORECASE,
                )
            for part in self._split_numbered_place_heading(item):
                cleaned = self._normalize_candidate(part)
                if cleaned and cleaned.casefold() not in GENERIC_PLACE_TERMS:
                    phrases.append(cleaned)
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
                phrases.extend(self._split_pinned_place_phrase(cleaned))
        return phrases

    def _metadata_numbered_items(self, metadata_text: str) -> list[str]:
        """Return the most complete ``1. place 2. place`` caption list."""

        best_items: list[str] = []
        marker_pattern = re.compile(r"(?:^|\s)(?P<number>10|[1-9])\.\s*")
        for line in metadata_text.splitlines():
            markers = list(marker_pattern.finditer(line))
            if len(markers) < 2:
                continue
            items: list[str] = []
            for index, marker in enumerate(markers):
                end = (
                    markers[index + 1].start()
                    if index + 1 < len(markers)
                    else len(line)
                )
                item = line[marker.end() : end].strip(" ,;:-")
                item = re.split(
                    r"\s+(?:stay\s+tune(?:d)?|for\s+more|follow\s+for|"
                    r"tap\s+the|link\s+in\s+bio)\b|\s+#",
                    item,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )[0].strip(" ,;:-.")
                if item:
                    items.append(item)
            if len(items) > len(best_items):
                best_items = items
        return best_items

    def _split_pinned_place_phrase(self, phrase: str) -> list[str]:
        match = re.fullmatch(
            r"(?P<left>.+?\b(?:st|street))\s+(?:and|&)\s+"
            r"(?P<right>.+?\b(?:st|street))",
            phrase,
            flags=re.IGNORECASE,
        )
        if match is None:
            return [phrase]
        return [
            self._normalize_candidate(match.group("left")),
            self._normalize_candidate(match.group("right")),
        ]

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
                    for existing_key, existing in ordered.items()
                    if (
                        len(existing_key) >= 6
                        and (
                            key.startswith(existing_key)
                            or existing_key.startswith(key)
                        )
                    )
                    or self._likely_same_cafe_name(cleaned, existing[0])
                ),
                None,
            )
            if prefix_key is not None:
                previous = ordered[prefix_key]
                if (
                    score > previous[1]
                    or (
                        score == previous[1]
                        and len(cleaned) > len(previous[0])
                    )
                ):
                    ordered[prefix_key] = (cleaned, max(score, previous[1]))
                continue
            previous = ordered.get(key)
            if previous is None:
                ordered[key] = (cleaned, score)
            elif score > previous[1]:
                ordered[key] = (cleaned, score)
        return [candidate for candidate, _score in ordered.values()]

    def _likely_same_cafe_name(self, left: str, right: str) -> bool:
        left_words = left.casefold().split()
        right_words = right.casefold().split()
        cafe_terms = {"cafe", "café", "coffee"}
        if (
            not left_words
            or not right_words
            or left_words[0] not in cafe_terms
            or right_words[0] not in cafe_terms
        ):
            return False
        left_key = self._dedupe_key(left).replace("9", "nine")
        right_key = self._dedupe_key(right).replace("9", "nine")
        return (
            SequenceMatcher(
                None,
                left_key,
                right_key,
            ).ratio()
            >= 0.75
        )

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
        metadata_place = self._metadata_place_name(metadata)
        metadata_search_region = self._metadata_search_region(metadata)
        authoritative_places = self._authoritative_metadata_places(
            metadata,
            metadata_text,
            destination,
        )
        for order, place in enumerate(places, start=1):
            is_metadata_place = bool(
                metadata_place
                and self._same_place_name(place, metadata_place)
            )
            observation = self._matching_observation(
                place,
                observations_by_place,
            )
            speech_observation = self._matching_observation(
                place,
                speech_observations_by_place,
            )
            address = address_hints.get(self._dedupe_key(place))
            if not address:
                for source_observation in (
                    observation,
                    speech_observation,
                ):
                    if source_observation is None:
                        continue
                    address = self._leading_address_for_place(
                        place,
                        source_observation.evidence,
                    )
                    if address:
                        break
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
            metadata_evidence = metadata_place if is_metadata_place else ""
            evidence = (
                metadata_evidence
                or visual_evidence
                or speech_evidence
                or caption_evidence
            )
            source_evidence = {
                source: value
                for source, value in (
                    ("metadata", metadata_evidence),
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
            if is_metadata_place:
                source_order = 1
            authoritative_order = next(
                (
                    index
                    for index, authoritative in enumerate(
                        authoritative_places,
                        start=1,
                    )
                    if self._same_place_name(place, authoritative)
                ),
                None,
            )
            if authoritative_order is not None:
                source_order = authoritative_order
            elif authoritative_places:
                source_order = order

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

            search_region = metadata_search_region or destination
            if source_day is not None:
                search_region = (
                    day_regions.get(source_day)
                    or metadata_search_region
                    or destination
                )
            if (
                speech_observation is not None
                and speech_observation.search_region
                and not (
                    is_metadata_place
                    and metadata_search_region
                )
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
        place_text = place.lower()
        if any(
            term in place_text
            for term in (
                "museum",
                "temple",
                "pagoda",
                "pagot",
                "cathedral",
                "church",
                "mausoleum",
                "square",
                "theater",
                "theatre",
                "prison",
            )
        ):
            return "culture"
        if "train street" in place_text:
            return "attraction"
        if any(term in place_text for term in ("market", "shopping", "chợ")):
            return "shopping"
        if any(term in place_text for term in ("dong xuan", "hang ma")):
            return "shopping"
        if (
            re.search(r"\b(?:st|street)\b", place_text)
            and re.search(
                r"\b(?:market|shop|shopping|souvenir|clothing)\b",
                " ".join((metadata_text, transcript)).lower(),
            )
        ):
            return "shopping"
        if any(term in place_text for term in ("coffee", "cafe", "café")):
            return "cafe"
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
        metadata_places = self._extract_places(
            metadata=metadata,
            metadata_text=metadata_text,
            transcript="",
            destination=None,
        )
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
        for key in (
            "address",
            "street_address",
            "location_address",
            "location",
            "venue",
            "place",
        ):
            value = metadata.raw.get(key)
            if isinstance(value, str):
                address = self._normalize_address(value)
                if address:
                    return address
            if isinstance(value, dict):
                for field in (
                    "address",
                    "street_address",
                    "formatted_address",
                    "display_name",
                ):
                    nested = value.get(field)
                    if isinstance(nested, str):
                        address = self._normalize_address(nested)
                        if address:
                            return address
        return None

    def _metadata_place_name(
        self,
        metadata: UrlMetadata | None,
    ) -> str | None:
        if metadata is None:
            return None
        for key in ("place", "venue", "location_name", "location"):
            value = metadata.raw.get(key)
            if isinstance(value, str):
                candidate = self._normalize_candidate(value)
                if candidate:
                    return candidate
            if isinstance(value, dict):
                for field in ("name", "title", "place_name", "venue_name"):
                    nested = value.get(field)
                    if isinstance(nested, str):
                        candidate = self._normalize_candidate(nested)
                        if candidate:
                            return candidate
        return None

    def _metadata_search_region(
        self,
        metadata: UrlMetadata,
    ) -> str | None:
        values: list[object] = [
            metadata.raw.get(key)
            for key in (
                "city",
                "locality",
                "region",
                "state",
                "province",
                "country",
            )
        ]
        location = metadata.raw.get("location")
        if isinstance(location, dict):
            values.extend(
                location.get(key)
                for key in (
                    "city",
                    "locality",
                    "region",
                    "state",
                    "province",
                    "country",
                )
            )
        parts = [
            re.sub(r"\s+", " ", value).strip(" .,;:-")
            for value in values
            if isinstance(value, str) and value.strip()
        ]
        return ", ".join(dict.fromkeys(parts)) or None

    def _address_from_sentence(self, sentence: str) -> str | None:
        match = ADDRESS_CUE_RE.search(sentence)
        if not match:
            return None
        return self._normalize_address(match.group("address"))

    def _normalize_address(self, value: str) -> str | None:
        cleaned = re.sub(r"\s+", " ", value).strip(" .,;:-")
        cleaned = re.split(r"\s+(?:and|then|before|after|but|with|và|rồi|sau đó)\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
        cleaned = cleaned.strip(" .,;:-")
        if (
            len(cleaned) < 6
            or cleaned.lower() in GENERIC_PLACE_TERMS
            or cleaned.startswith("+")
            or re.search(
                r"\b(?:timetables?|comment|link in bio|video info)\b",
                cleaned,
                flags=re.IGNORECASE,
            )
        ):
            return None
        return cleaned

    def _leading_address_for_place(
        self,
        place: str,
        evidence: str,
    ) -> str | None:
        prefix, separator, remainder = evidence.partition(",")
        if not re.match(r"^\s*\d{1,5}\w?\s+\S+", prefix):
            return None
        if not separator:
            return self._normalize_address(prefix)
        if not self._same_place_name(place, remainder):
            return None
        return self._normalize_address(prefix)

    def _authoritative_metadata_places(
        self,
        metadata: UrlMetadata | None,
        metadata_text: str,
        destination: str | None,
    ) -> list[str]:
        ordered: list[str] = []
        for place in (
            self._metadata_place_name(metadata),
            *self._metadata_itinerary_phrases(
                metadata_text,
                destination=destination,
            ),
        ):
            if not place or self._is_destination_alias(place, destination):
                continue
            existing_index = next(
                (
                    index
                    for index, existing in enumerate(ordered)
                    if self._same_place_name(place, existing)
                ),
                None,
            )
            if existing_index is not None:
                if len(place) > len(ordered[existing_index]):
                    ordered[existing_index] = place
                continue
            ordered.append(place)
        return ordered

    def _is_destination_alias(
        self,
        place: str,
        destination: str | None,
    ) -> bool:
        if not destination:
            return False
        place_key = self._location_identity(place)
        destination_key = self._location_identity(destination)
        return bool(place_key and place_key == destination_key)

    def _location_identity(self, value: str) -> str:
        tokens = re.findall(
            r"[a-z0-9]+",
            "".join(
                character
                for character in unicodedata.normalize(
                    "NFD",
                    value.casefold(),
                )
                if unicodedata.category(character) != "Mn"
            ).replace("đ", "d"),
        )
        while tokens[:2] in (["thanh", "pho"], ["city", "of"]):
            tokens = tokens[2:]
        while tokens and tokens[0] in {"city", "province", "tinh", "tp"}:
            tokens = tokens[1:]
        while tokens and tokens[-1] in {"city", "province"}:
            tokens = tokens[:-1]
        if tokens[-2:] == ["viet", "nam"]:
            tokens = tokens[:-2]
        elif tokens[-1:] == ["vietnam"]:
            tokens = tokens[:-1]
        return "".join(tokens)

    def _place_name_tokens(self, value: str) -> set[str]:
        ignored = {"entrance", "of", "the"}
        aliases = {
            "northern": "north",
            "southern": "south",
        }
        return {
            aliases.get(token, token)
            for token in re.findall(
                r"[a-z0-9]+",
                "".join(
                    character
                    for character in unicodedata.normalize(
                        "NFD",
                        value.casefold(),
                    )
                    if unicodedata.category(character) != "Mn"
                ).replace("đ", "d"),
            )
            if token not in ignored
        }

    def _evidence_for_place(self, place: str, metadata_text: str, transcript: str, prefer_address: bool = False) -> str | None:
        key = self._dedupe_key(place)
        sentences = self._sentences(transcript, metadata_text)
        for index, sentence in enumerate(sentences):
            if key and key in self._dedupe_key(sentence):
                if (
                    len(sentence) < 80
                    and transcript.count("\n") >= 3
                ):
                    start = max(0, index - 1)
                    end = min(len(sentences), index + 7)
                    return " ".join(sentences[start:end])[:500]
                return sentence
        return None

    def _sentences(self, *texts: str) -> list[str]:
        joined = "\n".join(text for text in texts if text)
        numbered_items = self._metadata_numbered_items(joined)
        sentences = [
            re.sub(r"\s+", " ", sentence).strip()
            for sentence in re.split(r"[\n.!?]", joined)
            if sentence.strip()
        ]
        return list(dict.fromkeys([*numbered_items, *sentences]))

    def _dedupe_key(self, value: str) -> str:
        decomposed = unicodedata.normalize("NFD", value.strip().casefold())
        without_marks = "".join(
            character
            for character in decomposed
            if unicodedata.category(character) != "Mn"
        ).replace("đ", "d")
        return re.sub(r"[^a-z0-9]+", "", without_marks)
