from __future__ import annotations

import asyncio
import json

from scripts.repair_mojibake_data import (
    deterministic_repair,
    gemini_repair_values,
    has_strict_mojibake,
    repair_json_tree,
    validate_gemini_repair,
)


def test_deterministic_repair_restores_legacy_vietnamese() -> None:
    corrupted = (
        "Mß║╕T Vietnamese restaurant thuß╗Öc danh mß╗Ñc "
        "Vietnamese restaurant."
    )

    repaired = deterministic_repair(corrupted)

    assert repaired == (
        "MẸT Vietnamese restaurant thuộc danh mục Vietnamese restaurant."
    )
    assert not has_strict_mojibake(repaired)


def test_deterministic_repair_handles_mixed_correct_and_corrupt_text() -> None:
    corrupted = (
        "Visit church. Nhà Thờ Lớn. "
        "Nh├á Thß╗¥ Lß╗¢n H├á Nß╗Öi thuß╗Öc danh mß╗Ñc cathedral."
    )

    repaired = deterministic_repair(corrupted)

    assert repaired == (
        "Visit church. Nhà Thờ Lớn. "
        "Nhà Thờ Lớn Hà Nội thuộc danh mục cathedral."
    )


def test_deterministic_repair_leaves_box_drawing_emoticon_unchanged() -> None:
    emoticon = "too few movies (┬┬﹏┬┬)"

    assert deterministic_repair(emoticon) == emoticon


def test_repair_json_tree_preserves_shape_and_non_text_values() -> None:
    payload = {
        "name": "MẸT",
        "description": "Mß║╕T thuß╗Öc danh mß╗Ñc nh├á h├áng.",
        "nested": [1, True, None, {"address": "H├á Nß╗Öi"}],
    }

    repaired, changed, unresolved = repair_json_tree(payload)

    assert repaired == {
        "name": "MẸT",
        "description": "MẸT thuộc danh mục nhà hàng.",
        "nested": [1, True, None, {"address": "Hà Nội"}],
    }
    assert changed == 2
    assert unresolved == []


def test_repair_json_tree_uses_canonical_note_after_lossy_downstream_fold() -> None:
    payload = {
        "placeId": "restaurant_123",
        "name": "Ốc 29 Võ Thị Sáu",
        "notes": "SS╗Éc 29 Võ Thị Sáu thuộc danh mục Fast food restaurant.",
    }

    repaired, changed, unresolved = repair_json_tree(
        payload,
        canonical_notes={
            "restaurant_123": (
                "Ốc 29 Võ Thị Sáu thuộc danh mục Fast food restaurant."
            )
        },
    )

    assert repaired["notes"] == (
        "Ốc 29 Võ Thị Sáu thuộc danh mục Fast food restaurant."
    )
    assert changed == 1
    assert unresolved == []


def test_gemini_validation_rejects_paraphrase_and_remaining_markers() -> None:
    original = "Cafe ABC thuß╗Öc danh mß╗Ñc Coffee shop."

    assert validate_gemini_repair(
        original,
        "Cafe ABC thuộc danh mục Coffee shop.",
    )
    assert not validate_gemini_repair(original, "Quán cà phê ABC.")
    assert not validate_gemini_repair(original, original)


class FakeGeminiClient:
    async def generate_structured_json(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        response_schema: dict,
    ) -> str:
        assert "Không bao giờ dịch" in system_prompt
        assert response_schema["type"] == "object"
        payload = json.loads(user_payload)
        return json.dumps(
            {
                "items": [
                    {
                        "id": item["id"],
                        "repaired": "Cafe ABC thuộc danh mục Coffee shop.",
                    }
                    for item in payload["items"]
                ]
            },
            ensure_ascii=False,
        )


def test_gemini_fallback_uses_ids_and_returns_validated_mapping() -> None:
    original = "Cafe ABC thuß╗Öc danh mß╗Ñc Coffee shop."

    repaired = asyncio.run(
        gemini_repair_values(
            [original],
            client=FakeGeminiClient(),  # type: ignore[arg-type]
            batch_size=10,
        )
    )

    assert repaired == {original: "Cafe ABC thuộc danh mục Coffee shop."}
