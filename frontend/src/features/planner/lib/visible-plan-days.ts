type PlanDayItemLike = {
  placeId?: string | null;
  placeType: string;
  source?: string;
  timelineCategory?: "activity" | "food" | "break";
};

type PlanDayLike = {
  items: PlanDayItemLike[];
};

export function isVisiblePlanItem(item: PlanDayItemLike): boolean {
  return !(
    item.source === "finder_rule"
    && item.placeType === "meal"
    && !item.placeId
  );
}

export function visiblePlanItems<T extends PlanDayItemLike>(items: T[]): T[] {
  return items.filter(isVisiblePlanItem);
}

export function dayHasPlace(day: PlanDayLike): boolean {
  return day.items.some(
    (item) =>
      item.timelineCategory !== "break"
      && item.placeType !== "break"
      && item.placeType !== "free_time"
      && isVisiblePlanItem(item)
  );
}

export function visiblePlanDays<T extends PlanDayLike>(days: T[]): T[] {
  return days.filter(dayHasPlace);
}
