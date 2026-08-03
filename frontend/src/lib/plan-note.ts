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
