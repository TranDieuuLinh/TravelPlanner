export function formatPlannerDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  if (!year || !month || !day) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(year, month - 1, day));
}

export function tripDaysBetween(startDate: string, endDate: string): number {
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  return Math.max(1, Math.round((end - start) / 86_400_000) + 1);
}

export function addTripDays(startDate: string, durationDays = 3): string {
  const date = new Date(`${startDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return "";
  date.setUTCDate(date.getUTCDate() + Math.max(0, durationDays - 1));
  return date.toISOString().slice(0, 10);
}

export function defaultTripEndDate(
  startDate: string | null | undefined,
  endDate: string | null | undefined,
  durationDays: number | null | undefined,
): string {
  if (!startDate) return endDate ?? "";
  const days = durationDays && durationDays > 0 ? durationDays : 3;
  return !endDate || (days === 3 && endDate === startDate)
    ? addTripDays(startDate, days)
    : endDate;
}
