import pytest

from app.modules.plans.knowledge_graph import (
    JsonTravelKnowledgeSearchTool,
    get_default_travel_knowledge_tool,
)


def test_old_quarter_graph_expands_to_precise_visitor_experiences() -> None:
    expansion = get_default_travel_knowledge_tool().expand(
        [
            "explore Hanoi Old Quarter",
            "historic architecture and culture",
            "food",
        ],
        region_key="vn,ha-noi,old-quarter-hoan-kiem",
        category="attraction",
    )

    assert "area:old-quarter" in expansion.matched_node_ids
    assert {
        "exp:temple",
        "exp:monument",
        "exp:museum",
        "exp:heritage-architecture",
        "exp:art-gallery",
        "exp:traditional-craft",
        "exp:neighborhood-walk",
        "exp:local-life",
    }.issubset(set(expansion.experience_node_ids))
    assert "historic temple" in expansion.query_terms
    assert "historical landmark" in expansion.query_terms
    assert expansion.categories == ("attraction",)
    assert "vn,ha-noi,hoan-kiem" in expansion.region_keys
    assert expansion.source_evidence
    assert all(
        item.source_url.startswith("https://")
        for item in expansion.source_evidence
    )
    assert all(item.license for item in expansion.source_evidence)
    assert any("exp:museum" in item.node_ids for item in expansion.source_evidence)


def test_graph_keeps_food_expansion_out_of_attraction_query() -> None:
    expansion = get_default_travel_knowledge_tool().expand(
        ["Old Quarter", "food"],
        region_key="vn,ha-noi",
        category="attraction",
    )

    assert "Hanoi coffee" not in expansion.query_terms
    assert "pho" not in expansion.query_terms


def test_graph_classifies_specific_food_experience_but_not_generic_restaurant() -> None:
    tool = get_default_travel_knowledge_tool()

    assert tool.classify_experience(
        ["Bún bò Huế", "Vietnamese restaurant"],
        region_key="vn,ha-noi",
        category="food_drink",
    ) == "bun"
    assert tool.classify_experience(
        ["Cafe Dinh", "Coffee shop"],
        region_key="vn,ha-noi",
        category="food_drink",
    ) == "coffee"
    assert tool.classify_experience(
        ["Nhà hàng tổng hợp", "restaurant"],
        region_key="vn,ha-noi",
        category="food_drink",
    ) is None


def test_hanoi_graph_does_not_leak_into_an_unsupported_region() -> None:
    expansion = get_default_travel_knowledge_tool().expand(
        ["Old Quarter history"],
        region_key="vn,da-nang",
        category="attraction",
    )

    assert expansion.query_terms == ()
    assert expansion.source_evidence == ()


def test_graph_loader_rejects_dangling_edges() -> None:
    with pytest.raises(ValueError, match="existing nodes"):
        JsonTravelKnowledgeSearchTool(
            {
                "schemaVersion": "travel-knowledge-graph.test",
                "regionKey": "vn,test",
                "nodes": [{"id": "theme:test", "kind": "theme", "label": "Test"}],
                "edges": [
                    {
                        "source": "theme:test",
                        "target": "exp:missing",
                        "relation": "INCLUDES_EXPERIENCE",
                    }
                ],
            }
        )
