from scripts.backfill_knowledge_graph_regions import region_from_source_address


def test_region_from_google_address_accepts_current_city_with_postal_code() -> None:
    assert region_from_source_address(
        "57 Ng. 198 Đ. Trần Cung, Nghĩa Đô, Hà Nội 10000, Vietnam"
    ) == ("vn,ha-noi", "ha noi")


def test_region_from_google_address_accepts_ascii_province_name() -> None:
    assert region_from_source_address(
        "Tề Lỗ, Vĩnh Yên, Phu Tho, Vietnam"
    ) == ("vn,phu-tho", "phu tho")


def test_region_from_google_address_rejects_placeholder_or_unknown_locality() -> None:
    assert region_from_source_address("Chưa có địa chỉ trong dữ liệu nguồn.") is None
    assert region_from_source_address("Ngõ 111, Vietnam") is None


def test_region_from_google_address_rejects_conflicting_provinces() -> None:
    assert region_from_source_address(
        "Một địa điểm, Hà Nội, Hưng Yên, Vietnam"
    ) is None
