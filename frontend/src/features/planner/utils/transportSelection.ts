import type { TransportLeg, TransportOption } from "@/features/planner/api/plans";
import {
  resolveSelectedTransportOption,
  visibleTransportOptions,
} from "@/features/planner/lib/transport-options";

export function transportOptionsForLeg(leg: TransportLeg): TransportOption[] {
  const options = visibleTransportOptions(
    [leg, ...(leg.alternatives ?? [])],
    leg.distanceMeters,
  );
  if (options.length > 0) return options;

  // Older planner outputs may mark a leg as `unknown`/`unavailable` even
  // though it already contains a valid geometry. Keep that leg usable in the
  // timeline instead of rendering a blocking retry card. It is explicitly an
  // estimate and does not claim verified routing.
  const hasGeometry = Array.isArray(leg.geometryCoordinates)
    && leg.geometryCoordinates.length >= 2
    && leg.geometryCoordinates.every(
      (point) => Array.isArray(point)
        && typeof point[0] === "number"
        && Number.isFinite(point[0])
        && typeof point[1] === "number"
        && Number.isFinite(point[1]),
    );
  if (
    hasGeometry
    && Number.isFinite(leg.distanceMeters)
    && Number.isFinite(leg.estimatedDurationMinutes)
  ) {
    return [{
      ...leg,
      mode: "car",
      source: leg.source || "estimated",
      verified: false,
    }];
  }
  return [];
}

export function planLegSelectionKey(day: number, legIndex: number): string {
  return `${day}:${legIndex}`;
}

export function planPlaceNamesMatch(left: string, right: string): boolean {
  return left.trim().toLocaleLowerCase("vi") === right.trim().toLocaleLowerCase("vi");
}

export function transportLegsMatch(left: TransportLeg, right: TransportLeg): boolean {
  const sameFrom =
    left.fromItemId && right.fromItemId
      ? left.fromItemId === right.fromItemId
      : planPlaceNamesMatch(left.fromPlace, right.fromPlace);
  const sameTo =
    left.toItemId && right.toItemId
      ? left.toItemId === right.toItemId
      : planPlaceNamesMatch(left.toPlace, right.toPlace);
  return sameFrom && sameTo;
}

export function selectedTransportOption(
  leg: TransportLeg,
  selectedOptionKey?: string,
): TransportOption {
  return resolveSelectedTransportOption(
    transportOptionsForLeg(leg),
    leg,
    selectedOptionKey,
  );
}
