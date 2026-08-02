from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Literal

from pydantic import ValidationError

from app.integrations.llm.base import LLMClient
from app.modules.plans.dto.agent_contracts import (
    PlannerAgentInput,
    PlannerMacroPlanDraft,
    PlannerResearchDraft,
    PlannerVerifiedResearch,
)
from app.modules.plans.planner.prompt import (
    PLANNER_RESEARCH_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    build_planner_repair_payload,
    build_planner_research_payload,
    build_planner_user_payload,
)
from app.modules.plans.planner.research_tool import (
    CAPABILITY_ALIASES,
    EmptyPlannerResearchTool,
    PlannerResearchTool,
    canonical_capability,
)


logger = logging.getLogger(__name__)
PLANNER_MAX_REPAIR_ATTEMPTS = 3
PlanningComplexity = Literal["local", "multi_region"]


class PlanningComplexityPolicy:
    """Choose a planning strategy from trip shape, not from a destination name."""

    def classify(self, planner_input: PlannerAgentInput) -> PlanningComplexity:
        style = planner_input.intent.travel_style.strip().casefold().replace("-", "_")
        multi_region_markers = ("road_trip", "road trip", "multi_base", "phuot")
        if (
            planner_input.trip_spec.days > 3
            or any(marker in style for marker in multi_region_markers)
        ):
            return "multi_region"
        return "local"


@dataclass(frozen=True)
class MacroPlanGenerationResult:
    draft: PlannerMacroPlanDraft
    research_draft: PlannerResearchDraft
    verified_research: PlannerVerifiedResearch
    repair_attempts: int
    research_generator: str


MacroDraftValidator = Callable[
    [str, PlannerResearchDraft, PlannerVerifiedResearch],
    PlannerMacroPlanDraft,
]


class MacroPlanGenerator:
    """Own all LLM interaction, structured parsing and repair for Planner."""

    def __init__(
        self,
        llm: LLMClient,
        research_tool: PlannerResearchTool | None = None,
        *,
        complexity_policy: PlanningComplexityPolicy | None = None,
        max_repair_attempts: int = PLANNER_MAX_REPAIR_ATTEMPTS,
    ) -> None:
        self.llm = llm
        self.research_tool = research_tool or EmptyPlannerResearchTool()
        self.complexity_policy = complexity_policy or PlanningComplexityPolicy()
        self.max_repair_attempts = max_repair_attempts

    async def generate(
        self,
        planner_input: PlannerAgentInput,
        *,
        evidence_payload: dict,
        validate_macro_draft: MacroDraftValidator,
    ) -> MacroPlanGenerationResult:
        research_generator = "llm"
        try:
            if self.complexity_policy.classify(planner_input) == "local":
                research_draft = self._build_local_research(planner_input)
                research_generator = "deterministic_graph"
            else:
                research_raw = await self.llm.generate_structured_json(
                    system_prompt=PLANNER_RESEARCH_SYSTEM_PROMPT,
                    user_payload=build_planner_research_payload(
                        planner_input,
                        evidence_bundle=evidence_payload,
                    ),
                    response_schema=PlannerResearchDraft.model_json_schema(),
                )
                research_draft = PlannerResearchDraft.model_validate_json(
                    research_raw
                )
            verified_research = self.research_tool.verify(
                research_draft,
                root_region_key=planner_input.region_context.region_key,
            )
        except ValidationError as exc:
            raise RuntimeError(
                "LLM Planner returned an invalid research contract."
            ) from exc

        raw = await self.llm.generate_structured_json(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_payload=build_planner_user_payload(
                planner_input,
                research_draft,
                verified_research,
                evidence_bundle=evidence_payload,
            ),
            response_schema=PlannerMacroPlanDraft.model_json_schema(),
        )
        repair_attempts = 0
        while True:
            try:
                draft = validate_macro_draft(
                    raw,
                    research_draft,
                    verified_research,
                )
                break
            except (ValidationError, ValueError) as exc:
                feedback = validation_feedback(exc)
                if repair_attempts >= self.max_repair_attempts:
                    logger.warning(
                        "Planner MacroPlan contract remained invalid after %s "
                        "repair attempts: %s",
                        repair_attempts,
                        feedback,
                    )
                    raise RuntimeError(
                        "LLM Planner returned an invalid MacroPlan contract "
                        f"after {repair_attempts} repair attempts."
                    ) from exc

                repair_attempts += 1
                raw = await self.llm.generate_structured_json(
                    system_prompt=PLANNER_SYSTEM_PROMPT,
                    user_payload=build_planner_repair_payload(
                        planner_input,
                        research_draft,
                        verified_research,
                        evidence_bundle=evidence_payload,
                        previous_output=raw,
                        validation_feedback=feedback,
                    ),
                    response_schema=PlannerMacroPlanDraft.model_json_schema(),
                )

        return MacroPlanGenerationResult(
            draft=draft,
            research_draft=research_draft,
            verified_research=verified_research,
            repair_attempts=repair_attempts,
            research_generator=research_generator,
        )

    @staticmethod
    def _build_local_research(
        planner_input: PlannerAgentInput,
    ) -> PlannerResearchDraft:
        requested_themes = list(
            dict.fromkeys(
                interest.strip()
                for interest in planner_input.intent.interests
                if interest.strip()
            )
        )
        if not requested_themes:
            requested_themes = [
                "culture",
                "history and heritage",
                "scenic landmark",
            ]

        theme_queries = []
        for theme in requested_themes[:6]:
            capability = canonical_capability(theme)
            if capability not in CAPABILITY_ALIASES:
                capability = "culture"
            theme_queries.append(
                {
                    "theme": theme,
                    "capabilities": [capability],
                    "preferredRegionKey": planner_input.region_context.region_key,
                    "rationale": (
                        "Giữ nguyên chủ đề/khu vực người dùng nêu, rồi kiểm chứng "
                        "bằng knowledge graph và Place active trong catalog."
                    ),
                }
            )
        return PlannerResearchDraft.model_validate(
            {
                "journeyStyle": "local_base",
                "varietyStrategy": (
                    "Chọn một trải nghiệm chính có địa điểm cụ thể cho mỗi ngày; "
                    "dùng graph để bổ sung trải nghiệm khác nhóm và giữ bữa ăn độc lập."
                ),
                "themeQueries": theme_queries,
                "expandBeyondRoot": False,
                "nearbyCapabilities": [],
                "maxDistanceKm": 50,
            }
        )


def validation_feedback(exc: ValidationError | ValueError) -> str:
    if isinstance(exc, ValidationError):
        fields = [
            ".".join(str(part) for part in error["loc"])
            + ":"
            + str(error["type"])
            for error in exc.errors()[:10]
        ]
        return "Schema validation failed at " + ", ".join(fields)
    return str(exc)
