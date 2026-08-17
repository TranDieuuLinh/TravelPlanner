import type {
  OpeningHourEntry,
  PlanItem,
  PlanSourceNote,
  TransportOption,
  TransportLeg,
  TravelPlan,
} from "@/features/planner/api/plans";
import { WALKING_DISPLAY_THRESHOLD_METERS } from "./transport-options.ts";

export type PlannerOutputStop = {
  itemId?: string;
  placeId: string;
  name: string;
  kind: "place" | "food" | "entertainment";
  priority: string;
  startMinute: number;
  endMinute: number;
  durationMinutes: number;
  mealType?: string | null;
  coordinates: { latitude: number; longitude: number };
  address?: string | null;
  notes?: PlanSourceNote | string | null;
  personalNotes?: string | null;
  tags?: string[];
  imageUrls?: string[];
  rating?: number | null;
  reviewCount?: number | null;
  openingHours?: Record<
    string,
    Array<{ startMinute: number; endMinute: number }> | null
  > | null;
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
  costPerPerson?: number;
  selectedTransport?: TransportOption | null;
};

export type ItineraryPlannerOutput = {
  destination: string;
  timezone: string;
  people?: number;
  accommodation?: {
    placeId: string;
    name: string;
    coordinates: { latitude: number; longitude: number };
    address?: string | null;
    rating?: number | null;
    reviewCount?: number | null;
    pricePerNight: { cost: number; currency: string };
    personalNotes?: string | null;
  } | null;
  accommodationNights?: number;
  days: Array<{
    day: number;
    date: string;
    stops: PlannerOutputStop[];
    legs: PlannerOutputLeg[];
    activityMinutes: number;
    travelMinutes: number;
    costPerPerson: number;
    costBreakdown: {
      accommodation: number;
      food: number;
      localTransport: number;
      activities: number;
      misc: number;
      total: number;
      currency: string;
    };
  }>;
  totalCostPerPerson: number;
  budgetPerPerson?: number | null;
  budgetSource?: "explicit" | "estimated_daily_cost" | "unspecified";
  dailyBudgetEstimate?: {
    accommodation: number;
    food: number;
    localTransport: number;
    activities: number;
    total: number;
  } | null;
  budgetProfileVersion?: string | null;
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

const WALKING_METERS_PER_MINUTE = 5_000 / 60;

function plannerLegToTransportLeg(
  leg: PlannerOutputLeg,
  fromItemId: string | null,
  toItemId: string | null,
  fromPlace: string,
  toPlace: string,
  currency: string,
): TransportLeg {
  const geometryCoordinates = decodeValhallaPolyline(leg.encodedPolyline);
  const car: TransportOption = {
    mode: "car",
    distanceMeters: leg.distanceMeters,
    estimatedDurationMinutes: leg.durationMinutes,
    geometryCoordinates,
    source: leg.provider,
    verified: leg.geometryAvailable && geometryCoordinates.length >= 2,
    estimatedCostPerPerson: leg.costPerPerson ?? null,
    currency,
  };

  let defaultLeg: TransportLeg;
  if (leg.distanceMeters >= WALKING_DISPLAY_THRESHOLD_METERS) {
    defaultLeg = {
      ...car,
      fromItemId,
      toItemId,
      fromPlace,
      toPlace,
      alternatives: [],
    };
  } else {
    defaultLeg = {
      ...car,
      fromItemId,
      toItemId,
      fromPlace,
      toPlace,
      mode: "walk",
      estimatedDurationMinutes: Math.max(
        1,
        Math.ceil(leg.distanceMeters / WALKING_METERS_PER_MINUTE),
      ),
      source: "post_planner_walking_estimate",
      verified: false,
      estimatedCostPerPerson: 0,
      currency,
      alternatives: [car],
    };
  }

  const selected = leg.selectedTransport;
  if (!selected) return defaultLeg;

  const sameOption = (option: TransportOption) =>
    option.mode === selected.mode
    && option.source === selected.source
    && option.distanceMeters === selected.distanceMeters
    && option.estimatedDurationMinutes === selected.estimatedDurationMinutes;
  const alternatives = [defaultLeg, ...(defaultLeg.alternatives ?? [])]
    .filter((option) => !sameOption(option));
  return {
    ...selected,
    fromItemId,
    toItemId,
    fromPlace,
    toPlace,
    alternatives,
  };
}

function plannerOpeningHoursToEntries(
  openingHours: PlannerOutputStop["openingHours"],
  days: ItineraryPlannerOutput["days"],
): OpeningHourEntry[] {
  if (!openingHours) return [];

  return Object.entries(openingHours).flatMap<OpeningHourEntry>(
    ([dayNumber, intervals]) => {
      const day = days.find((candidate) => String(candidate.day) === dayNumber);
      if (!day) return [];
      const date = new Date(`${day.date}T12:00:00`);
      if (Number.isNaN(date.getTime())) return [];
      const jsDay = date.getDay();
      const dayOfWeek = jsDay === 0 ? 7 : jsDay;

      if (intervals === null) return [];
      if (intervals.length === 0) {
        return [{ dayOfWeek, rawTimeSlots: "Đóng cửa" }];
      }
      const is24Hours = intervals.some(
        ({ startMinute, endMinute }) => startMinute === 0 && endMinute === 1440,
      );
      return [{
        dayOfWeek,
        is24Hours,
        rawTimeSlots: is24Hours
          ? null
          : intervals
              .map(({ startMinute, endMinute }) =>
                `${formatMinute(startMinute)}–${formatMinute(endMinute)}`)
              .join(", "),
      }];
    },
  );
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
  if (
    !output
    || output.days.length === 0
    || output.days.some((day) => day.stops.length === 0)
  ) return null;

  const days = output.days.map((day) => {
    const itemIdByPlace = new Map<string, string>();
    const nameByPlace = new Map<string, string>(
      output.accommodation
        ? [[output.accommodation.placeId, output.accommodation.name]]
        : [],
    );
    const items: PlanItem[] = day.stops.map((stop, index) => {
      const itemId = stop.itemId ?? `planner-${day.day}-${index + 1}-${stop.placeId}`;
      itemIdByPlace.set(stop.placeId, itemId);
      nameByPlace.set(stop.placeId, stop.name);
      return {
        itemId,
        placeId: stop.placeId,
        name: stop.name,
        address: stop.address ?? null,
        timeWindow: `${formatMinute(stop.startMinute)} – ${formatMinute(stop.endMinute)}`,
        placeType:
          stop.kind === "food"
            ? "restaurant"
            : stop.kind === "entertainment"
              ? "entertainment"
              : "activity",
        timelineCategory: stop.kind === "food" ? "food" : "activity",
        ontologyType:
          stop.kind === "food"
            ? "Restaurant"
            : stop.kind === "entertainment"
              ? "Entertainment"
              : "TravelPlace",
        source: "itinerary_planner",
        sourceRefs: [],
        tags: stop.tags ?? [],
        imageUrls: stop.imageUrls ?? [],
        notes: stop.notes ?? null,
        personalNotes: stop.personalNotes ?? null,
        rating: stop.rating ?? null,
        reviewCount: stop.reviewCount ?? null,
        openingHours: plannerOpeningHoursToEntries(stop.openingHours, output.days),
        latitude: stop.coordinates.latitude,
        longitude: stop.coordinates.longitude,
        durationMinutes: stop.durationMinutes,
        costPerPerson: stop.costPerPerson,
      };
    });
    const transportLegs: TransportLeg[] = day.legs.map((leg) =>
      plannerLegToTransportLeg(
        leg,
        itemIdByPlace.get(leg.fromPlaceId) ?? null,
        itemIdByPlace.get(leg.toPlaceId) ?? null,
        nameByPlace.get(leg.fromPlaceId) ?? leg.fromPlaceId,
        nameByPlace.get(leg.toPlaceId) ?? leg.toPlaceId,
        output.currency,
      )
    );
    return {
      day: day.day,
      items,
      transportLegs,
      costBreakdown: day.costBreakdown,
    };
  });

  return {
    id: options.id ?? `planner-${output.destination}-${output.days[0]?.date ?? "trip"}`,
    title: `${output.destination} · ${output.days.length} ngày`,
    destination: output.destination,
    travelerCount: output.people ?? null,
    kind: "main",
    days,
    accommodation: output.accommodation
      ? {
          placeId: output.accommodation.placeId,
          name: output.accommodation.name,
          address: output.accommodation.address,
          latitude: output.accommodation.coordinates.latitude,
          longitude: output.accommodation.coordinates.longitude,
          rating: output.accommodation.rating,
          reviewCount: output.accommodation.reviewCount,
          pricePerNight: output.accommodation.pricePerNight.cost,
          currency: output.accommodation.pricePerNight.currency,
          nights: output.accommodationNights ?? 0,
          personalNotes: output.accommodation.personalNotes ?? null,
        }
      : null,
    budget: {
      amountPerPerson: output.budgetPerPerson ?? null,
      currency: output.currency,
      source: output.budgetSource ?? "unspecified",
      dailyEstimate: output.dailyBudgetEstimate ?? null,
    },
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
