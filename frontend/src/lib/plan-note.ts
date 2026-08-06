import type { PlanNoteSource } from "./plans";

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

const NOTE_SOURCE_LABELS: Record<string, string> = {
  url: "Từ video tham khảo",
  image: "Từ ảnh tham khảo",
  google_maps: "Google Maps",
  place_provider: "Nguồn địa điểm",
  creator: "Từ creator"
};

function inferredNoteSources(
  item: {
    sourceRefs?: string[];
    sourceProvider?: string | null;
  }
): PlanNoteSource[] {
  const sources: PlanNoteSource[] = [];
  for (const ref of item.sourceRefs ?? []) {
    if (ref.startsWith("http://") || ref.startsWith("https://")) {
      sources.push({ type: "url", ref });
    } else if (ref === "ocr") {
      sources.push({ type: "image", ref, evidenceTypes: ["ocr"] });
    }
  }
  if (
    sources.length === 0 &&
    ["google_maps", "google_maps_scraper"].includes(item.sourceProvider ?? "")
  ) {
    sources.push({ type: "google_maps" });
  }
  return sources;
}

export function formatNoteSources(
  sources: PlanNoteSource[] | null | undefined
): string | null {
  const labels = (sources ?? [])
    .map((source) => NOTE_SOURCE_LABELS[source.type] ?? "Nguồn tham khảo")
    .filter((label, index, values) => values.indexOf(label) === index);
  return labels.length ? labels.join("\n") : null;
}

export type PlanItemNotePresentation = {
  sourceLabel: string | null;
  sourceText: string | null;
  personalText: string | null;
};

type NoteBearingItem = {
  notes?: string | null;
  noteSources?: PlanNoteSource[];
  personalNotes?: string | null;
  sourceActivity?: string | null;
  sourceRefs?: string[];
  sourceProvider?: string | null;
};

/** One shared note view-model for itinerary cards and map marker popups. */
export function planItemNotePresentation(
  item: NoteBearingItem
): PlanItemNotePresentation {
  const sources = item.noteSources?.length
    ? item.noteSources
    : inferredNoteSources(item);
  const sourceLabel = formatNoteSources(sources);
  const sourceText =
    formatPlanNote(item.notes) ??
    (sourceLabel ? formatPlanNote(item.sourceActivity) : null);
  return {
    sourceLabel: sourceText ? sourceLabel ?? "Thông tin bổ sung" : null,
    sourceText,
    personalText: formatPlanNote(item.personalNotes)
  };
}
