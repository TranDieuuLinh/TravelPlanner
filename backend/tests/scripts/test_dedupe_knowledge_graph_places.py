from scripts.dedupe_knowledge_graph_places import (
    PlaceRecord,
    _pair_auto_merge_reason,
    addresses_are_all_similar,
    addresses_need_manual_review,
    build_reports,
)


def _place(
    entity_id: str,
    name: str,
    *,
    place_type: str = "Historical landmark",
    address: str = "58 Quốc Tử Giám, Hà Nội",
    latitude: float = 21.028,
    longitude: float = 105.836,
    aliases: tuple[str, ...] = (),
    review_count: int = 0,
) -> PlaceRecord:
    return PlaceRecord(
        id=entity_id,
        name=name,
        normalized_name=name.casefold(),
        entity_type="TravelPlace",
        place_type=place_type,
        address=address,
        city="Hà Nội",
        region_key="vn,ha-noi",
        latitude=latitude,
        longitude=longitude,
        data_confidence="medium",
        review_count=review_count,
        revision=1,
        aliases=aliases,
    )


def test_landmark_aliases_with_close_coordinates_stay_in_review() -> None:
    english = _place(
        "temple-en",
        "Temple of Literature",
        aliases=("Văn Miếu Quốc Tử Giám",),
    )
    vietnamese = _place(
        "temple-vi",
        "Văn Miếu Quốc Tử Giám",
        longitude=105.837,
        review_count=100,
    )

    allowed, reason, _ = _pair_auto_merge_reason(english, vietnamese)

    assert allowed is False
    assert reason == "address_match_needs_manual_review"


def test_chain_branches_are_never_auto_merged_without_same_address() -> None:
    left = _place(
        "coffee-one",
        "Cộng Cà Phê",
        place_type="Coffee shop",
        address="15A Trúc Bạch, Hà Nội",
    )
    right = _place(
        "coffee-two",
        "Cộng Cà Phê",
        place_type="Cafe",
        address="94 Đường Láng, Hà Nội",
        latitude=21.0281,
        longitude=105.8361,
    )

    allowed, reason, _ = _pair_auto_merge_reason(left, right)

    assert allowed is False
    assert reason == "address_mismatch_needs_manual_review"


def test_exact_same_address_stays_in_review_for_manual_confirmation() -> None:
    left = _place(
        "museum-en",
        "Hanoi Museum",
        address="1 Phạm Hùng, Hà Nội",
        latitude=21.01,
        longitude=105.80,
    )
    right = _place(
        "museum-vi",
        "Bảo tàng Hà Nội",
        address="1  Phạm Hùng, Hà Nội",
        latitude=21.10,
        longitude=105.95,
    )

    allowed, reason, _ = _pair_auto_merge_reason(left, right)

    assert allowed is False
    assert reason == "address_match_needs_manual_review"


def test_reports_choose_richer_record_and_keep_ambiguous_branch_for_review() -> None:
    temple_old = _place("temple-old", "Temple of Literature")
    temple_reviewed = _place(
        "temple-reviewed",
        "Temple of Literature",
        longitude=105.8362,
        review_count=100,
    )
    coffee_one = _place(
        "coffee-one",
        "Cộng Cà Phê",
        place_type="Coffee shop",
        address="15A Trúc Bạch, Hà Nội",
    )
    coffee_two = _place(
        "coffee-two",
        "Cộng Cà Phê",
        place_type="Cafe",
        address="94 Đường Láng, Hà Nội",
        latitude=21.04,
        longitude=105.87,
    )

    auto_report, review_report = build_reports(
        [temple_old, temple_reviewed, coffee_one, coffee_two]
    )

    assert auto_report["groupCount"] == 0
    assert review_report["groupCount"] == 2
    assert {record["entityId"] for record in review_report["groups"][0]["records"]} == {
        "coffee-one",
        "coffee-two",
    }


def test_address_filter_keeps_similar_addresses_but_dismisses_different() -> None:
    assert addresses_need_manual_review(["19 P. Hàng Thiếc, Hà Nội", "19 Hàng Thiếc, Hà Nội"])
    assert not addresses_need_manual_review(["19 P. Hàng Thiếc, Hà Nội", "90 P. Hoàng Ngân, Hà Nội"])
    assert addresses_need_manual_review(["19 P. Hàng Thiếc, Hà Nội", ""])
    assert addresses_are_all_similar(["19 P. Hàng Thiếc, Hà Nội", "19 Hàng Thiếc, Hà Nội"])
    assert not addresses_are_all_similar(["19 P. Hàng Thiếc, Hà Nội", "90 P. Hoàng Ngân, Hà Nội"])
