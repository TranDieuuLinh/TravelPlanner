import type { TravelPlan } from "./plans";

const EMPTY_NOTE_VALUES = new Set([
  "nan",
  "none",
  "null",
  "undefined",
  "n/a"
]);

const VIETNAMESE_NOTE_TRANSLATIONS: Record<string, string> = {
  "withdraw money": "Rút tiền",
  "eat dessert and wait for sightseeing bus":
    "Ăn món tráng miệng và chờ xe buýt tham quan",
  "no place is required for this break block":
    "Khoảng nghỉ này không cần địa điểm cụ thể"
};

function normalizedLookupKey(value: string): string {
  return value
    .trim()
    .toLocaleLowerCase("en")
    .replace(/[.!?]+$/g, "")
    .trim();
}

/** Returns user-facing Vietnamese text, or null when a note has no real value. */
export function formatPlanNote(value: unknown): string | null {
  if (typeof value !== "string") return null;

  const note = value.trim();
  if (!note) return null;

  const lookupKey = normalizedLookupKey(note);
  if (EMPTY_NOTE_VALUES.has(lookupKey)) return null;

  return VIETNAMESE_NOTE_TRANSLATIONS[lookupKey] ?? note;
}

const SOURCE_TIME_LABELS: Record<string, string> = {
  breakfast: "Bữa sáng",
  morning: "Buổi sáng",
  "before lunch": "Trước bữa trưa",
  lunch: "Bữa trưa",
  afternoon: "Buổi chiều",
  dinner: "Bữa tối",
  "after dinner": "Sau bữa tối",
  evening: "Buổi tối",
  nightlife: "Buổi tối"
};

export type SourceScheduleNote = {
  key: string;
  day: number;
  place: string;
  text: string;
};

/** Builds only evidence-backed URL notes; generic plan assumptions stay hidden. */
export function sourceScheduleNotes(plan: TravelPlan): SourceScheduleNote[] {
  const seen = new Set<string>();
  const notes: SourceScheduleNote[] = [];

  for (const day of plan.days) {
    for (const [itemIndex, item] of day.items.entries()) {
      const hasUrlSource = (item.sourceRefs ?? []).some(
        (sourceRef) => sourceRef.startsWith("http://") || sourceRef.startsWith("https://")
      );
      const activity = formatPlanNote(item.sourceActivity);
      if (!hasUrlSource || !activity) continue;

      const timeHint = item.sourceTimeHint?.trim().toLocaleLowerCase("en") ?? "";
      const timeLabel = SOURCE_TIME_LABELS[timeHint] ?? item.sourceTimeHint?.trim();
      const text = timeLabel ? `${timeLabel}: ${activity}` : activity;
      const dedupeKey = `${day.day}|${item.name}|${text}`.toLocaleLowerCase("vi");
      if (seen.has(dedupeKey)) continue;
      seen.add(dedupeKey);
      notes.push({
        key: `${day.day}-${item.itemId ?? itemIndex}-${dedupeKey}`,
        day: day.day,
        place: item.name,
        text
      });
    }
  }

  return notes;
}
