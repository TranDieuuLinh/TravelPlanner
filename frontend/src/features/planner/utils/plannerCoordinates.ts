import type { TravelPlan } from "@/features/planner/api/plans";

export type PlanItem = TravelPlan["days"][number]["items"][number];

export function hasPlanItemCoordinates(
  item: PlanItem,
): item is PlanItem & { latitude: number; longitude: number } {
  return (
    typeof item.latitude === "number" &&
    Number.isFinite(item.latitude) &&
    item.latitude >= -90 &&
    item.latitude <= 90 &&
    typeof item.longitude === "number" &&
    Number.isFinite(item.longitude) &&
    item.longitude >= -180 &&
    item.longitude <= 180
  );
}

export function dateKeyForTripDay(
  startDate: string | null | undefined,
  day: number,
): string {
  if (!startDate || !/^\d{4}-\d{2}-\d{2}$/.test(startDate)) {
    return `day-${day}`;
  }

  const date = new Date(`${startDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return `day-${day}`;
  date.setUTCDate(date.getUTCDate() + day - 1);
  return date.toISOString().slice(0, 10);
}
