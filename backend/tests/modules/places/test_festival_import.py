from scripts.import_festivals import normalize_csv_row, parse_listed_year, row_to_festival


def test_current_festival_catalog_headers_map_to_database_fields() -> None:
    normalized = normalize_csv_row(
        {
            "source_id": "6048",
            "name": "Cần Trạm- Hố Cát",
            "festival_type": "Lễ hội truyền thống",
            "province_text": "Tỉnh Bắc Ninh (Bắc Giang)",
            "venue_text": "Thị trấn Vôi, huyện Lạng Giang",
            "source_url": "https://lehoi.com.vn/lehoi/detail.aspx?id=6048",
            "source_list_url": "https://lehoi.com.vn/lehoi/danhsach.aspx?page=518",
            "retrieved_at": "2026-07-30T07:50:40+00:00",
        }
    )

    festival = row_to_festival(normalized)

    assert festival["source_id"] == "6048"
    assert festival["name"] == "Cần Trạm- Hố Cát"
    assert festival["festival_type"] == "Lễ hội truyền thống"
    assert festival["province"] == "Tỉnh Bắc Ninh (Bắc Giang)"
    assert festival["venue"] == "Thị trấn Vôi, huyện Lạng Giang"
    assert festival["metadata_json"] == {
        "sourceListUrl": "https://lehoi.com.vn/lehoi/danhsach.aspx?page=518",
        "retrievedAt": "2026-07-30T07:50:40+00:00",
    }


def test_legacy_vietnamese_headers_remain_supported() -> None:
    normalized = normalize_csv_row(
        {
            "source_id": "legacy-1",
            "Tên lễ hội": "Lễ hội mẫu",
            "Tỉnh/Thành phố": "Hà Nội",
            "Địa điểm tổ chức": "Hoàn Kiếm",
            "Quy mô tổ chức": "Cấp quốc gia",
        }
    )

    festival = row_to_festival(normalized)

    assert festival["name"] == "Lễ hội mẫu"
    assert festival["province"] == "Hà Nội"
    assert festival["venue"] == "Hoàn Kiếm"
    assert festival["scale_level"] == "quoc-gia"


def test_listed_year_parser_keeps_valid_year_and_rejects_invalid_value() -> None:
    assert parse_listed_year("2026") == 2026
    assert parse_listed_year("không rõ") is None
