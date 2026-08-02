type PlanDayItemLike = {
  placeType: string;
  timelineCategory?: "activity" | "food" | "break";
};

type PlanDayLike = {
  items: PlanDayItemLike[];
};

export function dayHasPlace(day: PlanDayLike): boolean {
  return day.items.some(
    (item) =>
      item.timelineCategory !== "break"
      && item.placeType !== "break"
      && item.placeType !== "free_time"
  );
}

export function visiblePlanDays<T extends PlanDayLike>(days: T[]): T[] {
  return days.filter(dayHasPlace);
}
