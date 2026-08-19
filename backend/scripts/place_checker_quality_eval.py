from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

from app.modules.place_checker.contract import PlaceCheckerInput
from app.modules.place_checker.factory import build_postgres_place_checker_pipeline


def source(
    evidence: str,
    *,
    origin: str = "input",
    evidence_type: str = "raw_prompt",
    address_hint: str | None = None,
    time_hint: str | None = None,
) -> dict[str, Any]:
    return {
        "origin": origin,
        "evidenceType": evidence_type,
        "sourceUrl": (
            "https://example.com/travel-video" if origin == "url" else None
        ),
        "evidence": evidence,
        "sourceTimeHint": time_hint,
        "addressHint": address_hint,
        "observedAt": "2026-08-11T10:00:00Z" if origin == "url" else None,
    }


def place(
    name: str,
    evidence: str,
    *,
    confidence: float = 0.95,
    address_hint: str | None = None,
    origin: str = "input",
    evidence_type: str = "raw_prompt",
    time_hint: str | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "addressHint": address_hint,
        "confidence": confidence,
        "sourcePlaces": [
            source(
                evidence,
                origin=origin,
                evidence_type=evidence_type,
                address_hint=address_hint,
                time_hint=time_hint,
            )
        ],
    }


def item(
    name: str,
    item_type: str,
    action: str,
    evidence: str,
    *,
    related_place_name: str | None = None,
    confidence: float = 0.95,
) -> dict[str, Any]:
    return {
        "name": name,
        "itemType": item_type,
        "action": action,
        "relatedPlaceName": related_place_name,
        "evidence": evidence,
        "confidence": confidence,
    }


def base(
    *,
    adm: str = "Hanoi",
    days: int = 3,
    level: str = "medium",
    target: int | None = None,
    adults: int = 2,
    children: int = 0,
    infants: int = 0,
    preferences: list[str] | None = None,
    avoids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "inputADM": adm,
        "places": [],
        "inputItems": [],
        "urlNotes": None,
        "days": days,
        "budget": {
            "level": level,
            "targetAmount": target,
            "currency": "VND",
            "source": "raw_prompt",
        },
        "people": {
            "adults": adults,
            "children": children,
            "infants": infants,
        },
        "shortPreferences": preferences or [],
        "shortAvoids": avoids or [],
    }


def scenarios() -> dict[str, dict[str, Any]]:
    happy = base(
        days=4,
        level="low",
        target=6_000_000,
        preferences=["local_food", "sunset_views", "traditional_drinks"],
        avoids=["crowded_places", "nightlife"],
    )
    happy["places"] = [
        place(
            "Phở Gia Truyền Bát Đàn",
            "Tôi muốn ăn phở tại Phở Gia Truyền Bát Đàn",
            address_hint="49 Bát Đàn, Hoàn Kiếm, Hà Nội",
        ),
        place(
            "Café Giảng",
            "Buổi sáng ghé Café Giảng uống cà phê trứng",
            address_hint="39 Nguyễn Hữu Huân, Hoàn Kiếm, Hà Nội",
            origin="url",
            evidence_type="stt",
            time_hint="morning",
        ),
        place("Hồ Tây", "Tôi muốn ngắm hoàng hôn ở Hồ Tây", time_hint="sunset"),
    ]
    happy["inputItems"] = [
        item(
            "phở",
            "food",
            "eat",
            "ăn phở tại Phở Gia Truyền Bát Đàn",
            related_place_name="Phở Gia Truyền Bát Đàn",
        ),
        item(
            "ngắm hoàng hôn",
            "activity",
            "watch",
            "ngắm hoàng hôn ở Hồ Tây",
            related_place_name="Hồ Tây",
        ),
    ]

    noisy = base(days=3, preferences=["history", "local_food"])
    noisy["places"] = [
        place("Ho Chi Minh Mausoleum", "I want to visit Ho Chi Minh Mausoleum"),
        place(
            "Lăng Chủ tịch Hồ Chí Minh",
            "OCR: Lăng Chủ tịch Hồ Chí Minh",
            origin="url",
            evidence_type="frame_ocr",
        ),
        place(
            "Templ of Litereture",
            "STT nhận dạng chưa chính xác: Templ of Litereture",
            confidence=0.68,
            origin="url",
            evidence_type="stt",
        ),
    ]
    noisy["inputItems"] = [item("bún chả", "food", "eat", "muốn thử bún chả")]

    items_only = base(
        days=3,
        level="low",
        preferences=["local_food", "traditional_drinks", "culture"],
    )
    items_only["inputItems"] = [
        item("bún chả", "food", "eat", "ăn bún chả Hà Nội"),
        item("cà phê trứng", "drink", "drink", "thử cà phê trứng"),
        item("múa rối nước", "activity", "watch", "xem múa rối nước"),
    ]

    family = base(
        days=2,
        level="low",
        target=1_000_000,
        adults=2,
        children=2,
        infants=1,
        preferences=["family_friendly", "outdoor"],
        avoids=["nightlife", "alcohol"],
    )
    family["places"] = [
        place("Hanoi Zoo", "Gia đình muốn đưa trẻ đi sở thú"),
        place("Vietnam Museum of Ethnology", "Muốn cho trẻ tham quan bảo tàng"),
    ]
    family["inputItems"] = [
        item("khu vui chơi trẻ em", "activity", "play", "cần chỗ chơi cho trẻ"),
        item("bánh mì", "food", "eat", "ăn bánh mì nhanh và rẻ"),
    ]

    nightlife = base(
        days=2,
        level="low",
        preferences=["street_food"],
        avoids=["nightlife", "alcohol", "crowded_places"],
    )
    nightlife["places"] = [
        place("Ta Hien Beer Street", "Tôi vẫn muốn ghé phố bia Tạ Hiện"),
        place("Hanoi Old Quarter", "Đi bộ trong phố cổ"),
    ]

    wrong_city = base(days=2)
    wrong_city["places"] = [
        place("Independence Palace", "Tôi muốn thăm Dinh Độc Lập khi ở Hà Nội"),
        place("West Lake", "Tôi cũng muốn đi Hồ Tây"),
    ]

    malformed = base(days=2)
    malformed["places"] = [
        place("West Lake", "Tôi muốn đi Hồ Tây"),
        {
            "name": "Broken candidate",
            "addressHint": None,
            "confidence": 1.4,
            "sourcePlaces": [],
        },
    ]

    unknown_adm = base(adm="Atlantis", days=3)
    unknown_adm["places"] = [
        place("West Lake", "Tôi muốn đi Hồ Tây tại Atlantis")
    ]

    long_sparse = base(
        days=7,
        level="low",
        preferences=["history", "culture", "outdoor", "local_food"],
        avoids=["nightlife"],
    )
    long_sparse["places"] = [
        place("Ho Chi Minh's Mausoleum", "Tôi muốn thăm Lăng Bác")
    ]

    return {
        "01_happy_mixed_sources": happy,
        "02_noisy_duplicate_and_typo": noisy,
        "03_items_only": items_only,
        "04_family_low_budget": family,
        "05_direct_place_conflicts_with_avoids": nightlife,
        "06_wrong_city_place": wrong_city,
        "07_malformed_candidate_partial": malformed,
        "08_unknown_destination": unknown_adm,
        "09_long_trip_sparse_input": long_sparse,
    }


def experience_groups(places: list[Any]) -> list[str]:
    groups = {
        tag.split(":", 1)[1]
        for checked in places
        for tag in checked.tags
        if tag.startswith("experience:")
    }
    return sorted(groups)


POOL_CATEGORIES = [
    "food",
    "drink",
    "culture",
    "nature",
    "shopping",
    "nightlife",
    "workshop",
    "performance",
    "outdoor",
    "family",
    "special_experience",
    "local_activity",
]


def pool_category_distribution(places: list[Any]) -> dict[str, int]:
    return {
        category: sum(
            f"pool_category:{category}" in checked.tags
            for checked in places
        )
        for category in POOL_CATEGORIES
    }


def summarize(name: str, payload: PlaceCheckerInput, result: Any) -> dict[str, Any]:
    resolved_items = []
    for resolved in result.resolved_items:
        resolved_items.append(
            {
                "requirement": resolved.item.name,
                "status": resolved.status.value,
                "selected": resolved.selected.name if resolved.selected else None,
                "alternatives": [option.name for option in resolved.alternatives],
            }
        )
    checked_places = [
        {
            "name": checked.canonical_name,
            "category": checked.category,
            "mandatory": checked.mandatory,
            "eligible": checked.evaluation.planner_eligible,
            "state": checked.evaluation.state.value,
            "verification": checked.verification.status.value,
            "score": checked.ranking.score,
            "costTier": checked.cost.tier.value,
            "costKnown": checked.cost.known,
            "durationKnown": checked.duration.known,
            "avoidConflicts": checked.evaluation.avoid_conflicts,
            "tags": checked.tags,
        }
        for checked in result.checked_places
    ]
    return {
        "scenario": name,
        "status": result.status.value,
        "destinationStatus": result.trip_context.destination.status.value,
        "destination": result.trip_context.destination.canonical_name,
        "inputPlaceCount": len(payload.places),
        "candidateValidationIssueCount": len(payload.validation_issues),
        "checkedPlaceCount": len(result.checked_places),
        "eligiblePlaceCount": len(result.planner_eligible_place_ids),
        "mandatoryCount": sum(place.mandatory for place in result.checked_places),
        "categoryDistribution": result.coverage_analysis.category_distribution,
        "experienceGroups": experience_groups(result.checked_places),
        "poolCategoryDistribution": pool_category_distribution(
            result.checked_places
        ),
        "budgetStatus": result.budget_analysis.status.value,
        "unknownCostCount": result.budget_analysis.total.unknown_amount_count,
        "capacityStatus": result.capacity_analysis.status.value,
        "geographicSpread": result.geographic_analysis.spread,
        "geographicRadiusKm": result.geographic_analysis.radius_km,
        "openGaps": [gap.gap_type.value for gap in result.gap_analysis.gaps],
        "resolvedItems": resolved_items,
        "unresolvedEntities": [
            unresolved.model_dump(mode="json", by_alias=True)
            for unresolved in result.unresolved_entities
        ],
        "warnings": result.warnings,
        "checkedPlaces": checked_places,
        "durationMs": result.metadata.duration_ms,
    }


async def run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    inputs_dir = output_dir / "inputs"
    outputs_dir = output_dir / "outputs"
    inputs_dir.mkdir(exist_ok=True)
    outputs_dir.mkdir(exist_ok=True)
    pipeline = build_postgres_place_checker_pipeline(os.environ["DATABASE_URL"])
    summaries: list[dict[str, Any]] = []
    try:
        for name, raw_payload in scenarios().items():
            (inputs_dir / f"{name}.json").write_text(
                json.dumps(raw_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            try:
                payload = PlaceCheckerInput.model_validate(raw_payload)
                result = await pipeline.check(
                    payload,
                    request_id=f"quality-eval:{name}",
                )
                full_output = result.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=False,
                )
                (outputs_dir / f"{name}.json").write_text(
                    json.dumps(full_output, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                summaries.append(summarize(name, payload, result))
            except Exception as exc:
                summaries.append(
                    {
                        "scenario": name,
                        "executionError": type(exc).__name__,
                        "message": str(exc),
                    }
                )
    finally:
        catalog = pipeline.context_builder.adm_resolver
        close = getattr(catalog, "close", None)
        if close is not None:
            await close()
    (output_dir / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.output_dir))


if __name__ == "__main__":
    main()
