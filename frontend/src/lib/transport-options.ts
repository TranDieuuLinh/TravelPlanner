type TransportOptionAvailability = {
  mode: string;
  distanceMeters: number;
  source: string;
  verified: boolean;
  geometryCoordinates: [number, number][];
  details?: {
    scheduleStatus?: string;
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

export const WALKING_DISPLAY_THRESHOLD_METERS = 3_000;

function isWalkingMode(mode: string): boolean {
  const normalized = mode.toLowerCase();
  return normalized.includes("walk") || normalized.includes("pedestrian");
}

function isCarMode(mode: string): boolean {
  const normalized = mode.toLowerCase();
  return ["car", "auto", "ride", "hailing", "taxi"].some((token) =>
    normalized.includes(token)
  );
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
  const car = available.find((option) => isCarMode(option.mode));
  const publicTransit = available.filter((option) =>
    isPublicTransitMode(option.mode)
  );

  return [walking, car, ...publicTransit].filter(
    (option, index, result): option is T =>
      option != null
      && result.findIndex((candidate) => candidate?.mode === option.mode) === index
  );
}
