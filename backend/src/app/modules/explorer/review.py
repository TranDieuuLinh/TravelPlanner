from app.modules.explorer.contract import ExplorerOutput
from app.modules.explorer.review_contract import (
    ExplorerReview,
    ExplorerReviewBudget,
    ExplorerReviewContext,
)


def build_explorer_review(output: ExplorerOutput) -> ExplorerReview:
    if output.status == "error":
        return ExplorerReview(
            kind="error",
            intakeId=output.intake_id,
            error=output.error,
        )
    if not output.input_adm:
        return ExplorerReview(
            kind="missing_fields",
            intakeId=output.intake_id,
            missingFields=["inputADM"],
        )

    context = ExplorerReviewContext(
        inputADM=output.input_adm,
        days=output.days,
        budget=ExplorerReviewBudget(
            amountPerPerson=output.budget.target_amount,
            currency=output.budget.currency,
            level=output.budget.level,
        ),
        people=output.people,
        shortPreferences=output.short_preferences,
    )
    if output.defaulted_fields:
        return ExplorerReview(
            kind="defaults_proposed",
            intakeId=output.intake_id,
            tripContext=context,
            defaultedFields=output.defaulted_fields,
        )
    return ExplorerReview(
        kind="ready_for_execution",
        intakeId=output.intake_id,
        tripContext=context,
    )
