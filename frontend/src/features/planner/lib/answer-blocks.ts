import type { TripChatSource } from "@/features/planner/api/plans";

export type TextSpan = { type: "text"; text: string };
export type EntitySpan = { type: "entity"; text: string; entityId: string };
export type InlineSpan = TextSpan | EntitySpan;

export type AnswerBlock = {
  type: string;
  [key: string]: unknown;
};

export type HighlightSegment = {
  text: string;
  highlighted: boolean;
};

export function inlineSpanText(spans: unknown): string {
  if (!Array.isArray(spans)) return "";
  return spans
    .flatMap((span) => {
      if (!span || typeof span !== "object") return [];
      const value = span as Record<string, unknown>;
      return typeof value.text === "string" &&
        (value.type === "text" || (value.type === "entity" && typeof value.entityId === "string"))
        ? [value.text]
        : [];
    })
    .join("");
}

export function highlightSegments(
  text: string,
  highlights: unknown,
): HighlightSegment[] {
  if (!text || !Array.isArray(highlights)) return [{ text, highlighted: false }];
  const ranges: Array<{ start: number; end: number }> = [];
  for (const highlight of highlights.slice(0, 3)) {
    if (typeof highlight !== "string" || !highlight.trim()) continue;
    const start = text.toLocaleLowerCase().indexOf(highlight.toLocaleLowerCase());
    if (start < 0) continue;
    const end = start + highlight.length;
    if (ranges.some((range) => start < range.end && end > range.start)) continue;
    ranges.push({ start, end });
  }
  ranges.sort((left, right) => left.start - right.start);
  if (!ranges.length) return [{ text, highlighted: false }];
  const segments: HighlightSegment[] = [];
  let cursor = 0;
  for (const range of ranges) {
    if (range.start > cursor) segments.push({ text: text.slice(cursor, range.start), highlighted: false });
    segments.push({ text: text.slice(range.start, range.end), highlighted: true });
    cursor = range.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), highlighted: false });
  return segments;
}

export function citationSources(
  sourceIds: unknown,
  sources: TripChatSource[],
): TripChatSource[] {
  if (!Array.isArray(sourceIds)) return [];
  const byId = new Map(sources.map((source) => [source.sourceId, source]));
  return sourceIds.flatMap((sourceId) => {
    if (typeof sourceId !== "string") return [];
    const source = byId.get(sourceId);
    return source && /^https?:\/\//i.test(source.url) ? [source] : [];
  });
}
