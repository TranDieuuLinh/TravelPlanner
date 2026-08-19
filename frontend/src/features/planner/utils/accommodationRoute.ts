type RouteEndpoint = {
  itemId?: string | null;
  name: string;
};

type RouteLeg = {
  fromItemId?: string | null;
  toItemId?: string | null;
  fromPlace: string;
  toPlace: string;
};

type RouteDay = {
  items: RouteEndpoint[];
  transportLegs: RouteLeg[];
};

function placeNamesMatch(left: string, right: string): boolean {
  return (
    left.trim().toLocaleLowerCase("vi") ===
    right.trim().toLocaleLowerCase("vi")
  );
}

export function accommodationRoutePositions(
  day: RouteDay,
  accommodationName: string,
): { start: boolean; end: boolean } {
  const firstItem = day.items[0];
  const lastItem = day.items.at(-1);

  const start = Boolean(
    firstItem &&
      day.transportLegs.some((leg) => {
        const reachesFirstItem =
          firstItem.itemId && leg.toItemId
            ? firstItem.itemId === leg.toItemId
            : placeNamesMatch(firstItem.name, leg.toPlace);
        return (
          placeNamesMatch(leg.fromPlace, accommodationName) &&
          reachesFirstItem
        );
      }),
  );
  const end = Boolean(
    lastItem &&
      day.transportLegs.some((leg) => {
        const startsAtLastItem =
          lastItem.itemId && leg.fromItemId
            ? lastItem.itemId === leg.fromItemId
            : placeNamesMatch(lastItem.name, leg.fromPlace);
        return (
          startsAtLastItem && placeNamesMatch(leg.toPlace, accommodationName)
        );
      }),
  );

  return { start, end };
}
