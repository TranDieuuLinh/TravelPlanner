from app.modules.explorer.adapters.auto_tags import YamlTagCatalog


def test_catalog_rereads_allowed_tag_keys_when_file_changes(tmp_path) -> None:
    path = tmp_path / "tags-auto.yml"
    path.write_text("kiến trúc: [cầu]\n", encoding="utf-8")
    catalog = YamlTagCatalog(path)

    assert catalog.filter_allowed(["kiến trúc", "chụp ảnh"]) == ["kiến trúc"]

    path.write_text("chụp ảnh: [cầu]\n", encoding="utf-8")

    assert catalog.filter_allowed(["kiến trúc", "chụp ảnh"]) == ["chụp ảnh"]


def test_catalog_does_not_semantically_map_keyword_values(tmp_path) -> None:
    path = tmp_path / "tags-auto.yml"
    path.write_text(
        "Văn hóa: [phố cổ]\nnightlife: [chợ đêm]\n",
        encoding="utf-8",
    )
    catalog = YamlTagCatalog(path)

    assert catalog.filter_allowed(["Phố cổ và chợ đêm"]) == []


def test_catalog_filters_final_keys_without_keyword_resolution(tmp_path) -> None:
    path = tmp_path / "tags-auto.yml"
    path.write_text(
        "địa phương: [local food]\nđồ uống: [coffee]\n",
        encoding="utf-8",
    )
    catalog = YamlTagCatalog(path)

    assert catalog.filter_allowed(["local_food", "coffee", "unknown"]) == []
    assert catalog.filter_allowed(["đồ uống", "unknown", "đồ uống"]) == [
        "đồ uống"
    ]
