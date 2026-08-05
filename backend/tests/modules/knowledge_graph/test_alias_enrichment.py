from __future__ import annotations

from app.modules.knowledge_graph.model import KnowledgeEntity
from app.modules.knowledge_graph.text import (
    latin_transliteration,
    normalize_knowledge_text,
    repair_cp437_utf8_mojibake,
)
from scripts.enrich_knowledge_graph_aliases import (
    candidates_for_entity,
    classify_existing_alias,
    provider_name_fragments,
)


def test_normalization_handles_vietnamese_d() -> None:
    assert normalize_knowledge_text("Đống Đa") == "dong da"


def test_transliteration_preserves_words() -> None:
    assert latin_transliteration("Văn Miếu – Quốc Tử Giám") == (
        "Van Mieu Quoc Tu Giam"
    )


def test_repairs_legacy_cp437_utf8_mojibake() -> None:
    assert repair_cp437_utf8_mojibake("H├á Nß╗Öi") == "Hà Nội"
    assert repair_cp437_utf8_mojibake("Bß║»c Tß╗½ Li├¬m") == "Bắc Từ Liêm"
    assert repair_cp437_utf8_mojibake("HanoiΓÇÖs Lane") == "Hanoi’s Lane"


def test_provider_fragments_only_use_explicit_former_names() -> None:
    assert provider_name_fragments(
        "Belvilla Central Park | formerly Le Grand Hanoi"
    ) == ["Le Grand Hanoi"]
    assert provider_name_fragments(
        "Lotus Care Spa | massage body | chăm sóc da"
    ) == []
    assert provider_name_fragments("Capella Hanoi") == []


def test_hanoi_gets_curated_and_transliterated_aliases() -> None:
    entity = KnowledgeEntity(
        id="area_city_hanoi",
        canonical_name="H├á Nß╗Öi",
        normalized_name="ha noi",
        entity_type="Area",
        status="active",
    )
    candidates = candidates_for_entity(
        entity,
        "Hà Nội",
        place=None,
    )
    by_value = {candidate.value: candidate for candidate in candidates}
    assert by_value["Ha Noi"].alias_type == "transliteration"
    assert by_value["Hanoi"].alias_type == "english_name"
    assert by_value["HN"].alias_type == "abbreviation"


def test_non_latin_name_does_not_create_punctuation_only_alias() -> None:
    entity = KnowledgeEntity(
        id="restaurant_korean",
        canonical_name="화정족발 호떠이점 (한식, 중식)",
        normalized_name="",
        entity_type="Restaurant",
        status="active",
    )

    assert candidates_for_entity(entity, entity.canonical_name, place=None) == []


def test_existing_ascii_spelling_is_classified_as_transliteration() -> None:
    assert classify_existing_alias("Dong Da", "Đống Đa") == (
        "transliteration",
        "vi-Latn",
    )
