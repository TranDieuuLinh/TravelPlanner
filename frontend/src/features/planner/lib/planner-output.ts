import type {
  PlanItem,
  TransportLeg,
  TravelPlan,
} from "@/features/planner/api/plans";

export type PlannerOutputStop = {
  placeId: string;
  name: string;
  kind: "place" | "food";
  priority: string;
  startMinute: number;
  endMinute: number;
  durationMinutes: number;
  mealType?: string | null;
  coordinates: { latitude: number; longitude: number };
  address?: string | null;
  notes?: string | null;
  tags?: string[];
  costPerPerson: number;
};

export type PlannerOutputLeg = {
  fromPlaceId: string;
  toPlaceId: string;
  durationMinutes: number;
  distanceMeters: number;
  encodedPolyline?: string | null;
  provider: string;
  geometryAvailable: boolean;
};

export type ItineraryPlannerOutput = {
  destination: string;
  timezone: string;
  days: Array<{
    day: number;
    date: string;
    stops: PlannerOutputStop[];
    legs: PlannerOutputLeg[];
    activityMinutes: number;
    travelMinutes: number;
    costPerPerson: number;
  }>;
  totalCostPerPerson: number;
  budgetPerPerson?: number | null;
  currency: string;
  solver: Record<string, unknown>;
  sourceMix?: Array<Record<string, unknown>>;
  unscheduled: Array<{
    placeId: string;
    name: string;
    priority: string;
    reasonCode: string;
    message: string;
  }>;
  discardedOptionalCount: number;
  warnings: string[];
  phaseTimingsMs: Record<string, number>;
};

function formatMinute(value: number): string {
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

// Valhalla uses Google's encoded-polyline algorithm with six-digit precision.
function decodeValhallaPolyline(encoded: string | null | undefined): [number, number][] {
  if (!encoded) return [];
  const coordinates: [number, number][] = [];
  let index = 0;
  let latitude = 0;
  let longitude = 0;

  const nextDelta = (): number | null => {
    let shift = 0;
    let result = 0;
    while (index < encoded.length) {
      const byte = encoded.charCodeAt(index++) - 63;
      if (byte < 0 || byte > 63) return null;
      result |= (byte & 0x1f) << shift;
      shift += 5;
      if (byte < 0x20) return (result & 1) ? ~(result >> 1) : result >> 1;
    }
    return null;
  };

  while (index < encoded.length) {
    const latitudeDelta = nextDelta();
    const longitudeDelta = nextDelta();
    if (latitudeDelta === null || longitudeDelta === null) return [];
    latitude += latitudeDelta;
    longitude += longitudeDelta;
    coordinates.push([latitude / 1e6, longitude / 1e6]);
  }
  return coordinates;
}

export function plannerOutputToTravelPlan(
  output: ItineraryPlannerOutput | null | undefined,
  options: { id?: string } = {},
): TravelPlan | null {
  if (!output) return null;

  const days = output.days.map((day) => {
    const itemIdByPlace = new Map<string, string>();
    const nameByPlace = new Map<string, string>();
    const items: PlanItem[] = day.stops.map((stop, index) => {
      const itemId = `planner-${day.day}-${index + 1}-${stop.placeId}`;
      itemIdByPlace.set(stop.placeId, itemId);
      nameByPlace.set(stop.placeId, stop.name);
      return {
        itemId,
        placeId: stop.placeId,
        name: stop.name,
        address: stop.address ?? null,
        timeWindow: `${formatMinute(stop.startMinute)} – ${formatMinute(stop.endMinute)}`,
        placeType: stop.kind === "food" ? "restaurant" : "activity",
        timelineCategory: stop.kind === "food" ? "food" : "activity",
        ontologyType: stop.kind === "food" ? "Restaurant" : "TravelPlace",
        source: "itinerary_planner",
        sourceRefs: [],
        tags: stop.tags ?? [],
        notes: stop.notes ?? null,
        latitude: stop.coordinates.latitude,
        longitude: stop.coordinates.longitude,
      };
    });
    const transportLegs: TransportLeg[] = day.legs.map((leg) => {
      const geometryCoordinates = decodeValhallaPolyline(leg.encodedPolyline);
      return {
        fromItemId: itemIdByPlace.get(leg.fromPlaceId) ?? null,
        toItemId: itemIdByPlace.get(leg.toPlaceId) ?? null,
        fromPlace: nameByPlace.get(leg.fromPlaceId) ?? leg.fromPlaceId,
        toPlace: nameByPlace.get(leg.toPlaceId) ?? leg.toPlaceId,
        mode: "car",
        distanceMeters: leg.distanceMeters,
        estimatedDurationMinutes: leg.durationMinutes,
        geometryCoordinates,
        source: leg.provider,
        verified: leg.geometryAvailable && geometryCoordinates.length >= 2,
        alternatives: [],
      };
    });
    return { day: day.day, items, transportLegs };
  });

  return {
    id: options.id ?? `planner-${output.destination}-${output.days[0]?.date ?? "trip"}`,
    title: `${output.destination} · ${output.days.length} ngày`,
    destination: output.destination,
    kind: "main",
    days,
    warnings: output.warnings,
    unscheduledPlaces: output.unscheduled.map((item) => ({
      placeId: item.placeId,
      name: item.name,
      reasonCode: item.reasonCode,
      reason: item.message,
    })),
    routeEnrichmentStatus: "completed",
  };
}
