from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.adapters.user_insights import YamlInsightCatalog


def test_low_budget_fills_four_canonical_tags_and_avoid(tmp_path) -> None:
    tags = tmp_path / "tags-auto.yml"
    insights = tmp_path / "insight-user.yml"
    tags.write_text(
        "giá rẻ: [cheap]\n"
        "địa phương: [local]\n"
        "Văn hóa: [culture]\n"
        "cảnh quan: [view]\n"
        "sang trọng: [luxury]\n"
        "gia đình: [family]\n"
        'Phù Hợp Với Trẻ Em: [kids]\n'
        '18+: [adult]\n',
        encoding="utf-8",
    )
    insights.write_text(
        "đối_tượng:\n"
        "  gia_đình_có_trẻ_em:\n"
        "    priority-tags: [gia đình, Phù Hợp Với Trẻ Em]\n"
        "    avoid-tags: [18+]\n"
        "ngân_sách:\n"
        "  tiết_kiệm:\n"
        "    priority-tags: [giá rẻ, địa phương, Văn hóa, cảnh quan]\n"
        "    avoid-tags: [sang trọng]\n"
        "  trung_bình:\n"
        "    priority-tags: [địa phương]\n"
        "    avoid-tags: []\n"
        "  cao_cấp:\n"
        "    priority-tags: [sang trọng]\n"
        "    avoid-tags: [giá rẻ]\n"
        "sở_thích:\n"
        "  placeholder:\n"
        "    priority-tags: [Văn hóa]\n"
        "    avoid-tags: []\n",
        encoding="utf-8",
    )
    catalog = YamlInsightCatalog(YamlTagCatalog(tags), insights)

    preferences, avoids = catalog.enrich(
        budget_level="low",
        children=0,
        infants=0,
        preferences=[],
        avoids=[],
        seed="intake:hanoi:low",
    )

    assert len(preferences) == 4
    assert preferences[0] == "giá rẻ"
    assert set(preferences) == {"giá rẻ", "địa phương", "Văn hóa", "cảnh quan"}
    assert avoids == ["sang trọng"]


def test_children_add_family_insight_without_overwriting_user_tag(tmp_path) -> None:
    tags = tmp_path / "tags-auto.yml"
    insights = tmp_path / "insight-user.yml"
    tags.write_text(
        "Văn hóa: [culture]\n"
        "giá rẻ: [cheap]\n"
        "gia đình: [family]\n"
        'Phù Hợp Với Trẻ Em: [kids]\n'
        '18+: [adult]\n'
        "sang trọng: [luxury]\n",
        encoding="utf-8",
    )
    insights.write_text(
        "đối_tượng:\n"
        "  gia_đình_có_trẻ_em:\n"
        "    priority-tags: [gia đình, Phù Hợp Với Trẻ Em]\n"
        "    avoid-tags: [18+]\n"
        "ngân_sách:\n"
        "  tiết_kiệm:\n"
        "    priority-tags: [giá rẻ]\n"
        "    avoid-tags: [sang trọng]\n"
        "  trung_bình:\n"
        "    priority-tags: [Văn hóa]\n"
        "    avoid-tags: []\n"
        "  cao_cấp:\n"
        "    priority-tags: [sang trọng]\n"
        "    avoid-tags: [giá rẻ]\n"
        "sở_thích:\n"
        "  placeholder:\n"
        "    priority-tags: [Văn hóa]\n"
        "    avoid-tags: []\n",
        encoding="utf-8",
    )
    catalog = YamlInsightCatalog(YamlTagCatalog(tags), insights)

    preferences, avoids = catalog.enrich(
        budget_level="low",
        children=1,
        infants=0,
        preferences=["Văn hóa"],
        avoids=[],
        seed="family",
    )

    assert preferences[0] == "Văn hóa"
    assert "gia đình" in preferences
    assert avoids == ["sang trọng", "18+"]
