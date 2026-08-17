export type EntityPreview = {
  id: string;
  name: string;
  entityType: string;
  description?: string | null;
  imageUrl?: string | null;
  details: Record<string, string>;
};

export const LEGACY_ENTITY_HREF = "travel-entity://entity";

const ENTITY_HREF_PREFIX = `${LEGACY_ENTITY_HREF}/`;

export function parseEntityId(href: string | undefined): string | null {
  if (!href || !href.startsWith(ENTITY_HREF_PREFIX)) return null;
  const encodedId = href.slice(ENTITY_HREF_PREFIX.length);
  if (!encodedId) return null;
  try {
    const entityId = decodeURIComponent(encodedId);
    return entityId ? entityId : null;
  } catch {
    return null;
  }
}

export function entityPreviewPath(entityId: string): string {
  return `/v1/knowledge-graph/entities/${encodeURIComponent(entityId)}/preview`;
}

export function legacyEntityPreviewPath(label: string): string {
  return `/v1/knowledge-graph/entity-preview?name=${encodeURIComponent(label)}`;
}

export function createEntityPreviewLoader(
  fetchPreview: (entityId: string) => Promise<EntityPreview>,
) {
  const requests = new Map<string, Promise<EntityPreview>>();

  return {
    load(entityId: string): Promise<EntityPreview> {
      const existing = requests.get(entityId);
      if (existing) return existing;

      const request = fetchPreview(entityId).catch((error: unknown) => {
        requests.delete(entityId);
        throw error;
      });
      requests.set(entityId, request);
      return request;
    },
  };
}
