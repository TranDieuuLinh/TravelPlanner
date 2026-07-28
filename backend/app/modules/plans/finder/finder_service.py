from app.modules.plans.domain.entities import MacroPlan, PlanDay, PlanItem, TravelIntent


class FinderService:
    def fill_main_plan(self, macro_plan: MacroPlan, intent: TravelIntent, selected_places: list[str]) -> list[PlanDay]:
        return self._fill_days(macro_plan, intent, selected_places, "main")

    def fill_backup_plan(self, macro_plan: MacroPlan, intent: TravelIntent, selected_places: list[str]) -> list[PlanDay]:
        return self._fill_days(macro_plan, intent, selected_places, "backup")

    def _fill_days(self, macro_plan: MacroPlan, intent: TravelIntent, selected_places: list[str], mode: str) -> list[PlanDay]:
        place_pool = selected_places or intent.must_visit_places or [f"{intent.destination} highlight"]
        days: list[PlanDay] = []
        for brief in macro_plan.day_briefs:
            primary_place = place_pool[(brief.day - 1) % len(place_pool)]
            days.append(
                PlanDay(
                    day=brief.day,
                    theme=brief.theme,
                    items=[
                        PlanItem(
                            name=primary_place,
                            timeWindow="09:00-12:00",
                            placeType="must_visit" if mode == "main" else "backup_option",
                            notes=f"Committed by Finder {mode} run",
                        ),
                        PlanItem(
                            name=brief.target_area,
                            timeWindow="14:00-17:00",
                            placeType="area_explore",
                            notes="Flexible block",
                        ),
                    ],
                )
            )
        return days
