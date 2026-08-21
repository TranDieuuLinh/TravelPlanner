from app.modules.explorer.adapters.auto_tags import YamlTagCatalog
from app.modules.explorer.adapters.user_insights import YamlInsightCatalog


def test_low_budget_returns_every_declared_priority_tag_in_order(tmp_path) -> None:
    tags = tmp_path / "tags-auto.yml"
    insights = tmp_path / "insight-user.yml"
    tags.write_text(
        "giá rẻ: [cheap]\n"
        "địa phương: [local]\n"
        "Văn hóa: [culture]\n"
        "cảnh quan: [view]\n"
        "thiên nhiên: [nature]\n"
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
        "    priority-tags: [giá rẻ, địa phương, Văn hóa, cảnh quan, thiên nhiên]\n"
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

    assert preferences == [
        "giá rẻ",
        "địa phương",
        "Văn hóa",
        "cảnh quan",
        "thiên nhiên",
    ]
    assert avoids == ["sang trọng"]

    other_seed_preferences, _ = catalog.enrich(
        budget_level="low",
        children=0,
        infants=0,
        preferences=[],
        avoids=[],
        seed="another-intake:hanoi:low",
    )
    assert other_seed_preferences == preferences


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

    assert preferences == [
        "Văn hóa",
        "giá rẻ",
        "gia đình",
        "Phù Hợp Với Trẻ Em",
    ]
    assert avoids == ["sang trọng", "18+"]


def test_preferences_must_be_declared_in_insight_user_and_tags_auto(tmp_path) -> None:
    tags = tmp_path / "tags-auto.yml"
    insights = tmp_path / "insight-user.yml"
    tags.write_text(
        "giá rẻ: [cheap]\n"
        "Văn hóa: [culture]\n"
        "sang trọng: [luxury]\n"
        "ngoài insight: [invented]\n",
        encoding="utf-8",
    )
    insights.write_text(
        "đối_tượng:\n"
        "  gia_đình_có_trẻ_em:\n"
        "    priority-tags: []\n"
        "    avoid-tags: []\n"
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
        "  văn_hóa:\n"
        "    priority-tags: [Văn hóa, thiếu trong tags-auto]\n"
        "    avoid-tags: []\n",
        encoding="utf-8",
    )
    catalog = YamlInsightCatalog(YamlTagCatalog(tags), insights)

    preferences, avoids = catalog.enrich(
        budget_level="low",
        children=0,
        infants=0,
        preferences=["Văn hóa", "ngoài insight", "thiếu trong tags-auto"],
        avoids=["ngoài insight"],
        seed="allowlist",
    )

    assert preferences == ["Văn hóa", "giá rẻ"]
    assert avoids == ["sang trọng"]
