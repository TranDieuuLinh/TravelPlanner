const CLOCK_RANGE = /^\s*(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$/;

function normalizeClock(value: string): string {
  const [hours, minutes] = value.split(":");
  return `${hours.padStart(2, "0")}:${minutes}`;
}

export function formatItineraryTimeWindow(
  timeWindow?: string | null
): string | null {
  const value = timeWindow?.trim();
  if (!value) return null;

  const match = CLOCK_RANGE.exec(value);
  if (!match) return value;
  return `${normalizeClock(match[1])} – ${normalizeClock(match[2])}`;
}

export function itineraryTimeWindowAriaLabel(
  timeWindow?: string | null
): string | null {
  const formatted = formatItineraryTimeWindow(timeWindow);
  return formatted ? `Khung giờ ${formatted.replace(" – ", " đến ")}` : null;
}
