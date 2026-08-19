export type SourceProviderKind =
  | "youtube"
  | "tiktok"
  | "instagram"
  | "url";

type ItinerarySourceItem = {
  sourceUrl?: string | null;
  sourceRefs?: string[];
  notes?: { sourceUrl?: string | null } | string | null;
  noteSources?: Array<{
    type: string;
    ref?: string | null;
  }>;
};

const WEB_PAGE_PROVIDERS = new Set([
  "url",
  "web",
  "web_page",
  "webpage",
  "website",
]);

const PLACE_PROVIDER_HOSTS = new Set([
  "maps.google.com",
  "maps.app.goo.gl",
]);

/** Collect every user-facing origin URL that may survive into a plan item. */
export function itinerarySourceUrls(item: ItinerarySourceItem): string[] {
  const noteUrl =
    item.notes && typeof item.notes !== "string"
      ? item.notes.sourceUrl
      : null;
  const noteSourceUrls = (item.noteSources ?? [])
    .filter((source) => source.type === "url")
    .map((source) => source.ref);

  // The selected note is the item's direct provenance. Prefer it over broader
  // place references so an official/map URL cannot mask a social import URL.
  return [item.sourceUrl, noteUrl, ...noteSourceUrls, ...(item.sourceRefs ?? [])]
    .map((value) => value?.trim() ?? "")
    .filter(
      (value, index, values) =>
        /^https?:\/\//i.test(value) && values.indexOf(value) === index
    );
}

/**
 * Resolve only source types that have an icon in the itinerary UI.
 * The sourceProvider field can describe the later place-resolution provider,
 * so a normal webpage URL must primarily be recognized from sourceUrl. Direct
 * place-provider links (for example Google Maps) are deliberately excluded.
 */
export function sourceProviderKind(
  sourceUrl: string,
  sourceProvider: string | null | undefined
): SourceProviderKind | null {
  let hostname: string;
  let pathname: string;
  try {
    const url = new URL(sourceUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    hostname = url.hostname.toLowerCase();
    pathname = url.pathname.toLowerCase();
  } catch {
    return null;
  }

  if (
    hostname === "youtu.be" ||
    hostname === "youtube.com" ||
    hostname.endsWith(".youtube.com")
  ) {
    return "youtube";
  }
  if (hostname === "tiktok.com" || hostname.endsWith(".tiktok.com")) {
    return "tiktok";
  }
  if (hostname === "instagram.com" || hostname.endsWith(".instagram.com")) {
    return "instagram";
  }

  const normalizedProvider = sourceProvider?.trim().toLowerCase() ?? "";
  if (normalizedProvider.includes("youtube")) return "youtube";
  if (normalizedProvider.includes("tiktok")) return "tiktok";
  if (normalizedProvider.includes("instagram")) return "instagram";
  if (WEB_PAGE_PROVIDERS.has(normalizedProvider)) return "url";

  if (
    PLACE_PROVIDER_HOSTS.has(hostname) ||
    ((hostname === "google.com" || hostname === "www.google.com") &&
      pathname.startsWith("/maps"))
  ) {
    return null;
  }

  // Webpage candidates keep their article URL in sourceRefs, while
  // sourceProvider is replaced by the resolver (database/Knowledge Graph/etc).
  // Older revisions may also contain only this URL.
  return "url";
}
