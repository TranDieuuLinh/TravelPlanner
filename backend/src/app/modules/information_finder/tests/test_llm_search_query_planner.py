import asyncio
import json

import pytest

from app.modules.information_finder.adapters.llm_search_query_planner import (
    LlmSearchQueryPlanner,
)
from app.modules.information_finder.errors import SearchQueryPlanningError
from app.shared.llm import LlmResponseError


class FakeLlmClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def generate(self, user_prompt, **kwargs):
        self.calls.append((user_prompt, kwargs))
        if self.error:
            raise self.error("failed")
        return self.response


def run(coro):
    return asyncio.run(coro)


def test_planner_returns_search_decision_and_queries():
    client = FakeLlmClient(
        json.dumps(
            {
                "shouldSearch": True,
                "queries": [
                    "Hà Nội du lịch lịch sử",
                    "Hà Nội điểm tham quan nổi bật",
                ],
            }
        )
    )

    plan = run(LlmSearchQueryPlanner(client).generate("Cho tôi biết về Hà Nội"))

    assert plan.should_search is True
    assert plan.queries == ["Hà Nội du lịch lịch sử", "Hà Nội điểm tham quan nổi bật"]
    assert "Hà Nội" in client.calls[0][0]
    assert "localSources" in client.calls[0][0]
    assert client.calls[0][1]["temperature"] == 0.0


def test_planner_can_skip_search_when_local_sources_are_sufficient():
    client = FakeLlmClient(json.dumps({"shouldSearch": False, "queries": []}))

    plan = run(LlmSearchQueryPlanner(client).generate("Hà Nội"))

    assert plan.should_search is False
    assert plan.queries == []


@pytest.mark.parametrize(
    "response,error",
    [
        ("not-json", None),
        (json.dumps({"shouldSearch": True, "queries": []}), None),
        (None, LlmResponseError),
    ],
)
def test_planner_maps_invalid_output(response, error):
    client = FakeLlmClient(response=response, error=error)

    with pytest.raises(SearchQueryPlanningError):
        run(LlmSearchQueryPlanner(client).generate("Hà Nội"))
