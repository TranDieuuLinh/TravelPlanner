type TransportOptionAvailability = {
  mode: string;
  distanceMeters: number;
  estimatedDurationMinutes?: number;
  source: string;
  verified: boolean;
  geometryCoordinates: [number, number][];
  details?: {
    lines?: string[];
    scheduleStatus?: string;
    segments?: Array<{
      mode: string;
      line?: string | null;
      estimatedDurationMinutes: number;
      distanceMeters: number;
    }>;
  };
};

export function isPublicTransitMode(mode: string): boolean {
  const normalized = mode.toLowerCase();
  return ["public", "transit", "bus", "train"].some((token) =>
    normalized.includes(token)
  );
}

export function isGenericTransportMode(mode: string): boolean {
  const normalized = mode.toLowerCase();
  return normalized.includes("mixed") || normalized.includes("unknown");
}

export function isAvailableTransportOption(
  option: TransportOptionAvailability
): boolean {
  if (isGenericTransportMode(option.mode)) return false;
  if (!isPublicTransitMode(option.mode)) return true;
  if (option.geometryCoordinates.length < 2) return false;

  return (
    option.source === "opentripplanner_transit"
    && (
      option.verified
      || option.details?.scheduleStatus === "development_shifted_2018"
    )
  );
}

// This recommendation is applied after itinerary planning, so the optimizer can
// keep using one consistent routing profile for schedule feasibility.
export const WALKING_DISPLAY_THRESHOLD_METERS = 1_500;

export function isWalkingMode(mode: string): boolean {
  const normalized = mode.toLowerCase();
  return (
    normalized.includes("walk")
    || normalized.includes("walking")
    || normalized.includes("pedestrian")
  );
}

export function isCarMode(mode: string): boolean {
  const normalized = mode.toLowerCase();
  return [
    "car",
    "auto",
    "drive",
    "driving",
    "ride",
    "hailing",
    "taxi"
  ].some((token) => normalized.includes(token));
}

export function visibleTransportOptions<T extends TransportOptionAvailability>(
  options: T[],
  distanceMeters: number
): T[] {
  const showWalking = distanceMeters < WALKING_DISPLAY_THRESHOLD_METERS;
  const available = options.filter(isAvailableTransportOption);
  const walking = showWalking
    ? available.find((option) => isWalkingMode(option.mode))
    : undefined;
  if (showWalking) return walking ? [walking] : [];

  const car = available.find((option) => isCarMode(option.mode));
  const publicTransit = available.filter((option) =>
    isPublicTransitMode(option.mode)
  );

  return [car, ...publicTransit].filter(
    (option, index, result): option is T =>
      option != null
      && result.findIndex((candidate) => candidate?.mode === option.mode) === index
  );
}

export function transportOptionSelectionKey(
  option: TransportOptionAvailability
): string {
  return [
    option.mode.toLocaleLowerCase("vi"),
    option.source,
    option.estimatedDurationMinutes ?? "",
    Math.round(option.distanceMeters),
    (option.details?.lines ?? []).join(","),
    (option.details?.segments ?? [])
      .map((segment) => (
        `${segment.mode}:${segment.line ?? ""}:${segment.estimatedDurationMinutes}:${Math.round(segment.distanceMeters)}`
      ))
      .join("|")
  ].join("::");
}

export function resolveSelectedTransportOption<
  T extends TransportOptionAvailability
>(
  options: T[],
  currentOption: T,
  selectedOptionKey?: string
): T {
  return (
    options.find(
      (option) => transportOptionSelectionKey(option) === selectedOptionKey
    )
    ?? options.find((option) => option.mode === selectedOptionKey)
    ?? options.find(
      (option) =>
        transportOptionSelectionKey(option) ===
        transportOptionSelectionKey(currentOption)
    )
    ?? options[0]
    ?? currentOption
  );
}
