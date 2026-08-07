/**
 * Reapply a locally requested order onto the latest server order.
 *
 * Items added by another session keep their current slots, while items removed
 * by another session are ignored. This lets optimistic drag-and-drop retry a
 * version conflict without discarding concurrent itinerary changes.
 */
export function rebaseItineraryItemOrder(
  latestItemIds: string[],
  requestedItemIds: string[]
): string[] {
  const latestIds = new Set(latestItemIds);
  const seenRequestedIds = new Set<string>();
  const remainingRequestedIds = requestedItemIds.filter((itemId) => {
    if (!latestIds.has(itemId) || seenRequestedIds.has(itemId)) return false;
    seenRequestedIds.add(itemId);
    return true;
  });
  const requestedIds = new Set(remainingRequestedIds);
  let requestedIndex = 0;

  return latestItemIds.map((itemId) => {
    if (!requestedIds.has(itemId)) return itemId;
    const rebasedItemId = remainingRequestedIds[requestedIndex];
    requestedIndex += 1;
    return rebasedItemId;
  });
}
