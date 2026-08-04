type TransitOptionAvailability = {
  mode: string;
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

export function isAvailableTransportOption(
  option: TransitOptionAvailability
): boolean {
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
