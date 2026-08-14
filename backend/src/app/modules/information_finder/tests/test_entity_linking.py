import asyncio

from app.modules.information_finder.entity_linking import (
    EntityResolver,
    ResolvedEntity,
    link_verified_entities,
)


class Resolver(EntityResolver):
    async def resolve(self, name: str) -> ResolvedEntity | None:
        if name == "Lăng Bác":
            return ResolvedEntity(name=name, entity_id="lang-bac")
        return None


def test_links_only_entities_confirmed_by_knowledge_graph():
    answer = asyncio.run(
        link_verified_entities(
            "Lăng Bác và Phở là những biểu tượng quen thuộc.",
            ["Lăng Bác", "Phở"],
            Resolver(),
        )
    )

    assert "[Lăng Bác](travel-entity://entity)" in answer
    assert "Phở" in answer
    assert "[Phở](travel-entity://entity)" not in answer
