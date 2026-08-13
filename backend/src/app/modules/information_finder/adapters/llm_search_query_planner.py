import json

from pydantic import ValidationError

from app.modules.information_finder.contract import SearchQueryPlan
from app.modules.information_finder.errors import SearchQueryPlanningError
from app.modules.information_finder.prompts import (
    SEARCH_QUERY_SYSTEM_PROMPT,
    build_search_query_prompt,
)
from app.shared.llm import LlmClient, LlmError


class LlmSearchQueryPlanner:
    """Uses the shared Gemini client to formulate Tavily search queries."""

    def __init__(self, client: LlmClient, *, max_output_tokens: int = 256) -> None:
        self.client = client
        self.max_output_tokens = max_output_tokens

    async def generate(self, query: str) -> list[str]:
        try:
            raw = await self.client.generate(
                build_search_query_prompt(query),
                system_prompt=SEARCH_QUERY_SYSTEM_PROMPT,
                temperature=0.0,
                max_output_tokens=self.max_output_tokens,
                response_json_schema=SearchQueryPlan.model_json_schema(),
            )
            plan = SearchQueryPlan.model_validate(json.loads(raw))
        except (LlmError, json.JSONDecodeError, TypeError, ValidationError) as exc:
            raise SearchQueryPlanningError(
                "LLM search query planning failed"
            ) from exc

        queries: list[str] = []
        for query_item in plan.queries:
            normalized = " ".join(query_item.split())
            if normalized and normalized not in queries:
                queries.append(normalized)
        if not queries:
            raise SearchQueryPlanningError("LLM returned no usable search query")
        return queries
