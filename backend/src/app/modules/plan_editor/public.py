from app.modules.plan_editor.contract import (
    EditOperation,
    NaturalLanguagePlanEdit,
    PlanEditContext,
    PlanItemEdit,
    PlanEditorInput,
    PlanEditorOutput,
    TripContextEditorInput,
    TripContextEditorOutput,
)
from app.modules.plan_editor.adapters import GeminiPlanEditIntentResolver
from app.modules.plan_editor.graph import build_plan_editor_graph
from app.modules.plan_editor.ports import PlanEditIntentResolver
from app.modules.plan_editor.service import (
    NaturalLanguagePlanEditor,
    PlanEditorService,
    compact_plan_for_edit,
    validate_natural_language_plan_edit,
)


def build_gemini_natural_language_plan_editor(
    llm_client,
    *,
    max_output_tokens: int = 700,
    confidence_threshold: float = 0.72,
) -> NaturalLanguagePlanEditor:
    return NaturalLanguagePlanEditor(
        GeminiPlanEditIntentResolver(
            llm_client,
            max_output_tokens=max_output_tokens,
        ),
        confidence_threshold=confidence_threshold,
    )

__all__ = [
    "EditOperation",
    "GeminiPlanEditIntentResolver",
    "NaturalLanguagePlanEdit",
    "NaturalLanguagePlanEditor",
    "PlanEditContext",
    "PlanEditIntentResolver",
    "PlanItemEdit",
    "PlanEditorInput",
    "PlanEditorOutput",
    "PlanEditorService",
    "TripContextEditorInput",
    "TripContextEditorOutput",
    "build_gemini_natural_language_plan_editor",
    "build_plan_editor_graph",
    "compact_plan_for_edit",
    "validate_natural_language_plan_edit",
]
