import asyncio

from app.modules.information_finder.entity_linking import (
    EntityResolver,
    ResolvedEntity,
    link_verified_entities,
)
from app.modules.information_finder.contract import EntityCandidate


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

    assert "[Lăng Bác](travel-entity://entity/lang-bac)" in answer
    assert "Phở" in answer
    assert "[Phở](travel-entity://entity)" not in answer


def test_preserves_external_markdown_links():
    answer = asyncio.run(
        link_verified_entities(
            "[Hà Nội](http://localhost:3000/planner?chatId=old) có Hồ Hoàn Kiếm.",
            [],
            ResolverForHanoi(),
        )
    )

    assert "[Hà Nội](http://localhost:3000/planner?chatId=old)" in answer


def test_tries_entity_aliases_until_one_resolves():
    answer = asyncio.run(
        link_verified_entities(
            "Lăng Bác là điểm đến lịch sử.",
            [],
            AliasOnlyResolver(),
            [
                EntityCandidate(
                    display_name="Lăng Bác",
                    lookup_names=[
                        "Lăng Chủ tịch Hồ Chí Minh",
                        "Ho Chi Minh Mausoleum",
                        "Lăng Hồ Chí Minh",
                    ],
                )
            ],
        )
    )

    assert "[Lăng Bác](travel-entity://entity/lang-bac)" in answer


def test_preserves_citation_links_and_entity_link_order():
    answer = asyncio.run(
        link_verified_entities(
            "Lăng Bác [1] và Hồ Hoàn Kiếm [2].",
            ["Lăng Bác"],
            Resolver(),
        )
    )

    assert answer == "[Lăng Bác](travel-entity://entity/lang-bac) [1] và Hồ Hoàn Kiếm [2]."


class AliasOnlyResolver(EntityResolver):
    async def resolve(self, name: str) -> ResolvedEntity | None:
        if name == "Lăng Chủ tịch Hồ Chí Minh":
            return ResolvedEntity(name=name, entity_id="lang-bac")
        return None


class ResolverForHanoi(EntityResolver):
    async def resolve(self, name: str) -> ResolvedEntity | None:
        if name == "Hà Nội":
            return ResolvedEntity(name=name, entity_id="ha-noi")
        return None
