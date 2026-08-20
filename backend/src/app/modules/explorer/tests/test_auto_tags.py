from app.modules.explorer.adapters.auto_tags import YamlPlaceTagCatalog


def test_catalog_rereads_tags_auto_file_when_it_changes(tmp_path) -> None:
    path = tmp_path / "tags-auto.yml"
    path.write_text("kiến trúc: [cầu]\n", encoding="utf-8")
    catalog = YamlPlaceTagCatalog(path)

    assert catalog.tags_for("Cầu Rồng") == ["kiến trúc"]

    path.write_text("chụp ảnh: [cầu]\n", encoding="utf-8")

    assert catalog.tags_for("Cầu Rồng") == ["chụp ảnh"]


def test_catalog_returns_only_declared_tag_keys(tmp_path) -> None:
    path = tmp_path / "tags-auto.yml"
    path.write_text(
        "Văn hóa: [phố cổ]\nnightlife: [chợ đêm]\n",
        encoding="utf-8",
    )
    catalog = YamlPlaceTagCatalog(path)

    assert catalog.tags_for("Phố cổ và chợ đêm") == ["Văn hóa", "nightlife"]
