from scripts.backfill_non_latin_place_aliases import ALIAS_SPECS, SKIPPED_NAMES


def test_all_32_reviewed_non_latin_names_have_a_decision() -> None:
    assert len(ALIAS_SPECS) == 24
    assert len(SKIPPED_NAMES) == 8
    assert {spec.canonical_name for spec in ALIAS_SPECS}.isdisjoint(SKIPPED_NAMES)
