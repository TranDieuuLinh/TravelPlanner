from app.modules.explorer.public import ExplorerReview


def compose_explorer_review(review: ExplorerReview) -> tuple[str, str | None]:
    if review.kind == "missing_fields":
        question = "Bạn muốn đi tỉnh hoặc thành phố nào?"
        return question, question
    if review.kind == "error":
        message = (
            review.error.message
            if review.error is not None
            else "Explorer không thể xử lý yêu cầu này."
        )
        return message, None
    if review.kind != "defaults_proposed" or review.trip_context is None:
        return "Dữ liệu chuyến đi đã sẵn sàng.", None

    context = review.trip_context
    details: list[str] = []
    fields = set(review.defaulted_fields)
    details.append(f"**📍 {context.input_adm}**")
    if "days" in fields:
        details.append(f"**📅 {context.days} ngày**")
    if "people" in fields:
        details.append(f"**👥 {_people_label(context.people)}**")
    if "budget" in fields:
        details.append(f"**💰 {_budget_label(context.budget)}**")
    if "shortPreferences" in fields and context.short_preferences:
        details.append(
            f"**✨ Ưu tiên {' | '.join(context.short_preferences)}**"
        )
    summary = "  \n".join(details)
    response = (
        f"{summary}\n\nBạn xem qua các thông tin này nhé — nếu muốn, mình có thể điều chỉnh lại theo ý bạn."
    )
    return response, response


def _people_label(people) -> str:
    parts = [f"{people.adults} người lớn"]
    if people.children:
        parts.append(f"{people.children} trẻ em")
    if people.infants:
        parts.append(f"{people.infants} em bé")
    return ", ".join(parts)


def _budget_label(budget) -> str:
    levels = {"low": "tiết kiệm", "medium": "trung bình", "high": "cao"}
    label = levels[budget.level].capitalize()
    if budget.amount_per_person is not None:
        amount = f"{budget.amount_per_person:,}".replace(",", ".")
        label += f" · {amount} {budget.currency}/người/chuyến"
    return label
