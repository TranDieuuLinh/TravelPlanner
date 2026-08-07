export type SourceProviderKind =
  | "youtube"
  | "tiktok"
  | "instagram"
  | "url";

const WEB_PAGE_PROVIDERS = new Set([
  "url",
  "web",
  "web_page",
  "webpage",
  "website",
]);

/**
 * Resolve only source types that have an icon in the itinerary UI.
 * Place-resolution providers (for example, Knowledge Graph or Google Maps)
 * are deliberately not presented as URL sources.
 */
export function sourceProviderKind(
  sourceUrl: string,
  sourceProvider: string | null | undefined
): SourceProviderKind | null {
  let hostname: string;
  try {
    const url = new URL(sourceUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    hostname = url.hostname.toLowerCase();
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

  // Revisions created before sourceProvider was persisted contain only the URL.
  if (!normalizedProvider) return "url";
  return null;
}
