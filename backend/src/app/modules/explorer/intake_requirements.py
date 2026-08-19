from app.modules.explorer.contract import ExplorerBudget
from app.shared.contracts.user_context import UserContextRequest


def build_user_context_requests(
    *,
    input_adm: str | None,
    prompt_days: int | None,
    budget: ExplorerBudget,
) -> list[UserContextRequest]:
    requests: list[UserContextRequest] = []
    if not input_adm:
        requests.append(
            UserContextRequest(
                field="destination",
                source_agent="explorer",
                resume_route="explorer",
                reason="A destination is required before planning can continue.",
            )
        )
    if prompt_days is None:
        requests.append(
            UserContextRequest(
                field="duration_days",
                source_agent="explorer",
                resume_route="explorer",
                reason="Trip duration is required before planning can continue.",
            )
        )
    if budget.source == "default":
        requests.append(
            UserContextRequest(
                field="budget",
                source_agent="explorer",
                resume_route="explorer",
                reason="A budget is needed to choose suitable candidates.",
            )
        )
    return requests


def keep_unknown_context_requests(
    requests: list[UserContextRequest],
    known_fields: set[str],
) -> list[UserContextRequest]:
    return [request for request in requests if request.field not in known_fields]
