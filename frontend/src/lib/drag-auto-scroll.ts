export type DragAutoScrollBounds = {
  start: number;
  end: number;
};

/**
 * Returns a signed scroll speed for a pointer near a scroll area's edge.
 * The speed increases as the pointer approaches (or passes) the edge.
 */
export function dragAutoScrollVelocity(
  pointerPosition: number,
  bounds: DragAutoScrollBounds,
  edgeSize = 96,
  maximumSpeed = 20
): number {
  const availableSize = bounds.end - bounds.start;
  if (availableSize <= 0 || edgeSize <= 0 || maximumSpeed <= 0) return 0;

  const activeEdgeSize = Math.min(edgeSize, availableSize / 2);
  const topEdgeEnd = bounds.start + activeEdgeSize;
  const bottomEdgeStart = bounds.end - activeEdgeSize;

  if (pointerPosition < topEdgeEnd) {
    const intensity = Math.min(1, (topEdgeEnd - pointerPosition) / activeEdgeSize);
    return -Math.max(1, Math.round(maximumSpeed * intensity));
  }

  if (pointerPosition > bottomEdgeStart) {
    const intensity = Math.min(1, (pointerPosition - bottomEdgeStart) / activeEdgeSize);
    return Math.max(1, Math.round(maximumSpeed * intensity));
  }

  return 0;
}
