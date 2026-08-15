type LegEndpoint = {
  itemId?: string | null;
  name: string;
};

type ItineraryLeg = {
  fromItemId?: string | null;
  toItemId?: string | null;
  fromPlace: string;
  toPlace: string;
};

function placeNamesMatch(left: string, right: string): boolean {
  return left.trim().toLocaleLowerCase("vi") === right.trim().toLocaleLowerCase("vi");
}

export function transportLegAfterItem<T extends ItineraryLeg>(
  day: { items: LegEndpoint[]; transportLegs: T[] },
  item: LegEndpoint,
  itemIndex: number,
): T | null {
  const nextItem = day.items[itemIndex + 1];
  const exactLeg = day.transportLegs.find((leg) => {
    const startsAtItem =
      item.itemId && leg.fromItemId
        ? item.itemId === leg.fromItemId
        : placeNamesMatch(item.name, leg.fromPlace);
    if (!startsAtItem) return false;
    if (!nextItem) return leg.toItemId == null;
    return nextItem.itemId && leg.toItemId
      ? nextItem.itemId === leg.toItemId
      : placeNamesMatch(nextItem.name, leg.toPlace);
  });

  return exactLeg ?? null;
}
