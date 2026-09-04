from app.modules.place_checker.output_contract import PlannerTimeWindow


def parse_planner_windows(values: list[str]) -> list[PlannerTimeWindow]:
    result: list[PlannerTimeWindow] = []
    for value in values:
        if "-" not in value:
            continue
        start, end = value.split("-", 1)
        try:
            start_hour, start_minute = (int(part) for part in start.split(":"))
            end_hour, end_minute = (int(part) for part in end.split(":"))
        except (TypeError, ValueError):
            continue
        start_total = start_hour * 60 + start_minute
        end_total = end_hour * 60 + end_minute
        if start_total == end_total:
            end_total = 1440
        if not (0 <= start_total <= 1439 and 0 <= end_total <= 1440):
            continue
        window = PlannerTimeWindow(
            start_minute=start_total,
            end_minute=end_total,
        )
        if window not in result:
            result.append(window)
    return result


def meals_for_hours(opening_hours: list[str] | None) -> list[str]:
    spans = parse_planner_windows(opening_hours or [])
    if not spans:
        return ["breakfast", "lunch", "dinner"]
    return [
        meal
        for meal, minute in (("breakfast", 480), ("lunch", 720), ("dinner", 1140))
        if any(window.start_minute <= minute <= window.end_minute for window in spans)
    ]
