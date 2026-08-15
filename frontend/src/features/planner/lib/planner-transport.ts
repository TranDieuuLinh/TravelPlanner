import type {
  TransportOption,
  TravelPlan,
} from "@/features/planner/api/plans";
import {
  isAvailableTransportOption,
  isCarMode,
  isWalkingMode,
  transportOptionSelectionKey,
} from "@/features/planner/lib/transport-options";
import { transportLegAfterItem } from "@/features/planner/lib/planner-transport-leg";

export { transportLegAfterItem };

export function transportModeLabel(mode: string): string {
  const normalized = mode.toLowerCase();
  if (isWalkingMode(mode)) return "Đi bộ";
  if (normalized.includes("public") || normalized.includes("transit")) {
    return "Phương tiện công cộng";
  }
  if (normalized.includes("bike") || normalized.includes("motor"))
    return "Xe máy";
  if (normalized.includes("ride") || normalized.includes("hailing"))
    return "Xe công nghệ";
  if (isCarMode(mode)) return "Ô tô";
  if (normalized.includes("bus")) return "Xe buýt";
  if (normalized.includes("train")) return "Tàu hỏa";
  if (normalized.includes("flight") || normalized.includes("plane"))
    return "Máy bay";
  if (normalized.includes("mixed")) return "Phương tiện chưa xác định";
  if (normalized.includes("unknown")) return "Chưa xác định";
  return mode;
}

export function planTransportRouteMapKey(
  day: number,
  legIndex: number,
  option: TransportOption
): string {
  return `day-${day}-leg-${legIndex}-${transportOptionSelectionKey(option)}`;
}

export function directionTransportRouteMapKey(
  day: number,
  legIndex: number,
  option: TransportOption
): string {
  return `day-directions-${day}-${legIndex}-${transportOptionSelectionKey(
    option
  )}`;
}

export function promoteTransportOptionInPlan(
  plan: TravelPlan,
  dayNumber: number,
  legIndex: number,
  selectedOption: TransportOption
): TravelPlan {
  return {
    ...plan,
    days: plan.days.map((day) => {
      if (day.day !== dayNumber) return day;
      return {
        ...day,
        transportLegs: day.transportLegs.map((leg, index) => {
          if (index !== legIndex) return leg;
          const candidates = [leg, ...(leg.alternatives ?? [])];
          const selected =
            candidates.find(
              (option) =>
                transportOptionSelectionKey(option) ===
                transportOptionSelectionKey(selectedOption)
            ) ??
            candidates.find(
              (option) =>
                option.mode.toLowerCase() === selectedOption.mode.toLowerCase()
            );
          if (!selected) return leg;
          const selectedIndex = candidates.indexOf(selected);
          const alternativeKeys = new Set<string>();
          const alternatives = candidates.filter((option, optionIndex) => {
            if (optionIndex === selectedIndex) return false;
            const key = transportOptionSelectionKey(option);
            if (alternativeKeys.has(key)) return false;
            alternativeKeys.add(key);
            return true;
          });
          return {
            ...leg,
            mode: selected.mode,
            distanceMeters: selected.distanceMeters,
            estimatedDurationMinutes: selected.estimatedDurationMinutes,
            geometryCoordinates: selected.geometryCoordinates,
            source: selected.source,
            verified: selected.verified,
            fetchedAt: selected.fetchedAt,
            details: selected.details,
            alternatives,
          };
        }),
      };
    }),
  };
}

export function isDevelopmentTransitFixture(option: TransportOption): boolean {
  return (
    option.source === "opentripplanner_transit" &&
    option.details?.scheduleStatus === "development_shifted_2018"
  );
}

export function isDrawableTransportRoute(option: TransportOption): boolean {
  return (
    hasValidGeometryCoordinates(option.geometryCoordinates) &&
    option.geometryCoordinates.length >= 2 &&
    isAvailableTransportOption(option)
  );
}

export function hasValidGeometryCoordinates(
  coordinates: unknown
): coordinates is [number, number][] {
  return (
    Array.isArray(coordinates) &&
    coordinates.every(
      (coordinate) =>
        Array.isArray(coordinate) &&
        coordinate.length >= 2 &&
        typeof coordinate[0] === "number" &&
        Number.isFinite(coordinate[0]) &&
        typeof coordinate[1] === "number" &&
        Number.isFinite(coordinate[1])
    )
  );
}

export function formatDistance(distanceMeters: number): string {
  if (distanceMeters < 1000) {
    return `${Math.max(0, Math.round(distanceMeters))} m`;
  }
  return `${(distanceMeters / 1000).toLocaleString("vi-VN", {
    maximumFractionDigits: 1,
  })} km`;
}

export function formatDuration(durationMinutes: number): string {
  const roundedMinutes = Math.max(1, Math.round(durationMinutes));
  if (roundedMinutes < 60) return `${roundedMinutes} phút`;
  const hours = Math.floor(roundedMinutes / 60);
  const minutes = roundedMinutes % 60;
  return minutes > 0 ? `${hours} giờ ${minutes} phút` : `${hours} giờ`;
}
