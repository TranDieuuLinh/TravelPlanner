from app.modules.knowledge_graph.routes.admin_entities import (
    EntityListResponse,
    EntitySummary,
    KnowledgeGraphStats,
)


def test_admin_knowledge_graph_responses_use_camel_case() -> None:
    stats = KnowledgeGraphStats(
        entity_count=1,
        alias_count=2,
        relationship_count=3,
    )
    assert stats.model_dump(by_alias=True) == {
        "entityCount": 1,
        "aliasCount": 2,
        "relationshipCount": 3,
    }

    page = EntityListResponse(
        items=[
            EntitySummary(
                id="place_001",
                canonical_name="Hoan Kiem Lake",
                entity_type="TravelPlace",
                status="draft",
                created_at="2026-08-04T00:00:00+00:00",
                updated_at="2026-08-04T00:00:00+00:00",
            )
        ],
        total=32_325,
        limit=25,
        offset=0,
        has_more=True,
    )

    payload = page.model_dump(by_alias=True)
    assert payload["hasMore"] is True
    assert payload["items"][0]["canonicalName"] == "Hoan Kiem Lake"
    assert payload["items"][0]["entityType"] == "TravelPlace"
