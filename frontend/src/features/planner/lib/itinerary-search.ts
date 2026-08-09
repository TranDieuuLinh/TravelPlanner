export type ItinerarySearchItem = {
  itemId?: string | null;
  name: string;
  address?: string | null;
  placeType?: string | null;
  timelineCategory?: "activity" | "food" | "break";
};

export type ItinerarySearchDay = {
  day: number;
  items: ItinerarySearchItem[];
};

export type ItinerarySearchResult = {
  day: number;
  itemIndex: number;
  item: ItinerarySearchItem;
  key: string;
};

export function normalizeItinerarySearchText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLocaleLowerCase("vi")
    .replace(/\s+/g, " ")
    .trim();
}

export function itinerarySearchResultKey(
  day: number,
  itemIndex: number,
  itemId?: string | null
): string {
  return itemId ? `${day}:${itemId}` : `${day}:index-${itemIndex}`;
}

export function searchItineraryPlaces(
  days: readonly ItinerarySearchDay[],
  query: string,
  limit = 8
): ItinerarySearchResult[] {
  const normalizedQuery = normalizeItinerarySearchText(query);
  if (!normalizedQuery || limit <= 0) return [];

  return days
    .flatMap((day) =>
      day.items.flatMap((item, itemIndex) => {
        if (item.timelineCategory === "break") return [];

        const name = normalizeItinerarySearchText(item.name);
        const address = normalizeItinerarySearchText(item.address ?? "");
        const placeType = normalizeItinerarySearchText(item.placeType ?? "");
        const rank = name.startsWith(normalizedQuery)
          ? 0
          : name.includes(normalizedQuery)
            ? 1
            : address.includes(normalizedQuery)
              ? 2
              : placeType.includes(normalizedQuery)
                ? 3
                : null;
        if (rank == null) return [];

        return [
          {
            day: day.day,
            itemIndex,
            item,
            key: itinerarySearchResultKey(day.day, itemIndex, item.itemId),
            rank,
          },
        ];
      })
    )
    .sort((left, right) => left.rank - right.rank)
    .slice(0, limit)
    .map(({ rank: _rank, ...result }) => result);
}
