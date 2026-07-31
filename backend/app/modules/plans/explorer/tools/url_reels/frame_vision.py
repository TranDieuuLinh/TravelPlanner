from __future__ import annotations

import base64
import json
import mimetypes
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from queue import Queue

import httpx

from app.core.config import settings
from app.modules.plans.explorer.tools.url_reels.schema import (
    FrameVisionObservation,
    FrameVisionResult,
)

PROMOTIONAL_EVIDENCE_CUES = (
    "đặt combo",
    "dat combo",
    "inbox",
    "nhận tư vấn",
    "nhan tu van",
    "follow",
)


def _split_balanced_batches(
    frame_paths: list[Path],
    maximum_batch_size: int,
) -> list[list[Path]]:
    if not frame_paths:
        return []
    batch_count = (
        len(frame_paths) + maximum_batch_size - 1
    ) // maximum_batch_size
    base_size, larger_batch_count = divmod(
        len(frame_paths),
        batch_count,
    )
    batches: list[list[Path]] = []
    start = 0
    for batch_index in range(batch_count):
        batch_size = base_size + (
            1 if batch_index < larger_batch_count else 0
        )
        batches.append(frame_paths[start : start + batch_size])
        start += batch_size
    return batches


class GeminiReelFrameVision:
    def __init__(
        self,
        api_key: str | list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self.model_name = settings.gemini_image_ocr_model
        configured_keys = api_key or settings.gemini_ocr_key_pool
        raw_keys = (
            configured_keys.split(",")
            if isinstance(configured_keys, str)
            else list(configured_keys)
        )
        self.api_keys = tuple(
            key.strip()
            for key in raw_keys
            if key.strip()
        )

    def analyze(
        self,
        frame_paths: list[Path],
        *,
        destination: str | None,
    ) -> FrameVisionResult:
        if not frame_paths:
            return FrameVisionResult()
        if not self.api_keys:
            raise RuntimeError(
                "GEMINI_OCR_API_KEYS or GEMINI_API_KEY is required for "
                "URL reel frame vision."
            )
        batch_size = max(1, settings.url_reel_vision_batch_size)
        if len(frame_paths) <= batch_size:
            return self._analyze_batch(
                frame_paths,
                destination=destination,
                api_key=self.api_keys[-1],
            )

        start = time.perf_counter()
        batches = _split_balanced_batches(frame_paths, batch_size)
        maximum_concurrency = min(
            max(1, settings.url_reel_vision_max_concurrency),
            len(self.api_keys),
            len(batches),
        )
        # A leased OCR-only key is returned only after its batch (including
        # retry) completes, so simultaneous OCR calls use different keys and
        # never consume the separately configured STT pool.
        key_pool: Queue[str] = Queue()
        for api_key in reversed(self.api_keys[-maximum_concurrency:]):
            key_pool.put(api_key)

        def analyze_with_leased_key(batch: list[Path]) -> FrameVisionResult:
            api_key = key_pool.get()
            try:
                return self._analyze_batch_with_retry(
                    batch,
                    destination=destination,
                    api_key=api_key,
                )
            finally:
                key_pool.put(api_key)

        with ThreadPoolExecutor(
            max_workers=maximum_concurrency
        ) as executor:
            futures = [
                executor.submit(
                    analyze_with_leased_key,
                    batch,
                )
                for batch in batches
            ]
            batch_results: list[FrameVisionResult] = []
            batch_errors: list[str] = []
            # Read futures in batch order so concurrent completion cannot
            # reorder itinerary evidence.
            for future in futures:
                try:
                    batch_results.append(future.result())
                except (RuntimeError, httpx.HTTPError) as exc:
                    batch_errors.append(str(exc))

        if not batch_results:
            raise RuntimeError(
                batch_errors[-1]
                if batch_errors
                else "Gemini frame vision produced no batch results."
            )
        places: list[str] = []
        observations: list[FrameVisionObservation] = []
        seen: set[str] = set()
        for result in batch_results:
            observations_by_name = {
                item.place_name.casefold(): item
                for item in result.observations
            }
            for place in result.places:
                key = place.casefold()
                if key in seen:
                    continue
                seen.add(key)
                places.append(place)
                observation = observations_by_name.get(key)
                if observation is not None:
                    observations.append(observation)
        return FrameVisionResult(
            text="\n".join(
                result.text
                for result in batch_results
                if result.text
            ),
            places=places,
            observations=observations,
            status="partial" if batch_errors else "ok",
            error=(
                f"{len(batch_errors)} frame batch(es) failed; successful "
                "OCR evidence was preserved."
                if batch_errors
                else None
            ),
            durationSeconds=time.perf_counter() - start,
        )

    def _analyze_batch_with_retry(
        self,
        frame_paths: list[Path],
        *,
        destination: str | None,
        api_key: str,
    ) -> FrameVisionResult:
        last_error: RuntimeError | httpx.HTTPError | None = None
        for _attempt in range(2):
            try:
                return self._analyze_batch(
                    frame_paths,
                    destination=destination,
                    api_key=api_key,
                )
            except (RuntimeError, httpx.HTTPError) as exc:
                last_error = exc
        raise last_error or RuntimeError("Unknown frame batch failure.")

    def _analyze_batch(
        self,
        frame_paths: list[Path],
        *,
        destination: str | None,
        api_key: str,
    ) -> FrameVisionResult:
        start = time.perf_counter()
        prompt = (
            "Analyze these chronological frames sampled from a travel reel. "
            "Return one observation for each distinct, visually evidenced stop. "
            "Preserve frame order and copy the complete exact place name without "
            "splitting Vietnamese names. A heading such as 'địa điểm', a city, "
            "or a generic category is not a place name. Use an empty placeName "
            "when the frame does not visibly identify a specific venue. "
            "Transcribe the exact address, price, day, timing cue, recommended "
            "activity, dish, or booking note into evidence. "
            "Set dayNumber to the explicit day shown for that stop, or 0 when "
            "the source does not assign a day. Set timeHint and activity to "
            "empty strings when they are not visibly evidenced. "
            "Also describe travel-relevant venue categories and attributes such "
            "as local, hidden gem, photogenic, quiet, crowded, budget, premium, "
            "family friendly, outdoor, nightlife, beach, culture or nature. "
            "Distinguish sequential stops from alternatives. Do not invent text "
            "or identify a place without visual evidence."
        )
        if destination:
            prompt += f" The destination context is {destination}."
        parts: list[dict] = [{"text": prompt}]
        for frame_path in frame_paths:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": (
                            mimetypes.guess_type(frame_path.name)[0]
                            or "image/jpeg"
                        ),
                        "data": base64.b64encode(
                            frame_path.read_bytes()
                        ).decode("ascii"),
                    }
                }
            )

        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent"
        )
        with httpx.Client(timeout=90) as client:
            response = client.post(
                endpoint,
                params={"key": api_key},
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {
                        "mediaResolution": (
                            settings.url_reel_vision_media_resolution
                        ),
                        "maxOutputTokens": 8192,
                        "responseMimeType": "application/json",
                        "responseJsonSchema": {
                            "type": "object",
                            "properties": {
                                "observations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "order": {"type": "integer"},
                                            "placeName": {"type": "string"},
                                            "evidence": {"type": "string"},
                                            "dayNumber": {
                                                "type": "integer",
                                                "minimum": 0,
                                                "maximum": 30,
                                            },
                                            "timeHint": {"type": "string"},
                                            "activity": {"type": "string"},
                                        },
                                        "required": [
                                            "order",
                                            "placeName",
                                            "evidence",
                                            "dayNumber",
                                            "timeHint",
                                            "activity",
                                        ],
                                        "additionalProperties": False,
                                    },
                                }
                            },
                            "required": ["observations"],
                            "additionalProperties": False,
                        },
                    },
                },
            )
            if response.is_error:
                raise RuntimeError(
                    "Gemini frame vision failed with status "
                    f"{response.status_code}: {response.text[:500]}"
                )
            data = response.json()
        text = "\n".join(
            str(part.get("text", "")).strip()
            for part in data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [])
            if part.get("text")
        ).strip()
        place_names: list[str] = []
        structured_observations: list[FrameVisionObservation] = []
        try:
            observations = json.loads(text).get("observations", [])
        except (AttributeError, json.JSONDecodeError):
            observations = []
        if isinstance(observations, list):
            rendered: list[str] = []
            for observation in observations:
                if not isinstance(observation, dict):
                    continue
                place_name = str(observation.get("placeName", "")).strip()
                evidence = str(observation.get("evidence", "")).strip()
                if place_name and any(
                    cue in evidence.casefold()
                    for cue in PROMOTIONAL_EVIDENCE_CUES
                ):
                    place_name = ""
                raw_day = observation.get("dayNumber")
                day_number = (
                    raw_day
                    if isinstance(raw_day, int) and 1 <= raw_day <= 30
                    else None
                )
                time_hint = str(observation.get("timeHint", "")).strip()
                activity = str(observation.get("activity", "")).strip()
                if place_name and place_name not in place_names:
                    place_names.append(place_name)
                    structured_observations.append(
                        FrameVisionObservation(
                            order=(
                                observation.get("order")
                                if isinstance(observation.get("order"), int)
                                and observation["order"] >= 1
                                else None
                            ),
                            placeName=place_name,
                            evidence=evidence,
                            dayNumber=day_number,
                            timeHint=time_hint or None,
                            activity=activity or None,
                        )
                    )
                if place_name or evidence:
                    rendered.append(
                        f"PLACE: {place_name or '[unidentified]'}"
                        + (f" | {evidence}" if evidence else "")
                    )
            if rendered:
                text = "\n".join(rendered)
        return FrameVisionResult(
            text=text,
            places=place_names,
            observations=structured_observations,
            status="ok",
            durationSeconds=time.perf_counter() - start,
        )
