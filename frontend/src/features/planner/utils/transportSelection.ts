import type { TransportLeg, TransportOption } from "@/features/planner/api/plans";
import {
  resolveSelectedTransportOption,
  visibleTransportOptions,
} from "@/features/planner/lib/transport-options";

export function transportOptionsForLeg(leg: TransportLeg): TransportOption[] {
  return visibleTransportOptions(
    [leg, ...(leg.alternatives ?? [])],
    leg.distanceMeters,
  );
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
