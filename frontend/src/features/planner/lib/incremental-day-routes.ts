import type {
  PlanDay,
  PlanItem,
  TransportLeg,
  TravelPlan,
} from "@/features/planner/api/plans";

export type DayRouteEndpoint = {
  identityKey: string;
  itemId: string | null;
  name: string;
  address: string | null;
  latitude: number | null;
  longitude: number | null;
};

export type DayRouteEdge = {
  key: string;
  from: DayRouteEndpoint;
  to: DayRouteEndpoint;
};

export type DayRouteDiff = {
  edges: DayRouteEdge[];
  affectedEdges: DayRouteEdge[];
  reusableLegsByEdgeKey: ReadonlyMap<string, TransportLeg>;
};

function normalizedName(value: string): string {
  return value.trim().toLocaleLowerCase("vi");
}

function finiteCoordinate(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function endpointRouteSignature(endpoint: DayRouteEndpoint): string {
  if (
    finiteCoordinate(endpoint.latitude)
    && finiteCoordinate(endpoint.longitude)
  ) {
    return `${endpoint.identityKey}@${endpoint.latitude.toFixed(6)},${endpoint.longitude.toFixed(6)}`;
  }
  return `${endpoint.identityKey}@unresolved`;
}

function routeEdge(from: DayRouteEndpoint, to: DayRouteEndpoint): DayRouteEdge {
  return {
    key: `${endpointRouteSignature(from)}=>${endpointRouteSignature(to)}`,
    from,
    to,
  };
}

function itemEndpoint(item: PlanItem, index: number): DayRouteEndpoint {
  const identity = item.itemId || item.placeId || `${normalizedName(item.name)}:${index}`;
  return {
    identityKey: `item:${identity}`,
    itemId: item.itemId ?? null,
    name: item.name,
    address: item.address ?? null,
    latitude: finiteCoordinate(item.latitude) ? item.latitude : null,
    longitude: finiteCoordinate(item.longitude) ? item.longitude : null,
  };
}

function accommodationEndpoint(
  plan: TravelPlan,
): DayRouteEndpoint | null {
  const accommodation = plan.accommodation;
  if (!accommodation) return null;
  return {
    identityKey: `accommodation:${accommodation.placeId || normalizedName(accommodation.name)}`,
    itemId: accommodation.placeId || null,
    name: accommodation.name,
    address: accommodation.address ?? null,
    latitude: finiteCoordinate(accommodation.latitude)
      ? accommodation.latitude
      : null,
    longitude: finiteCoordinate(accommodation.longitude)
      ? accommodation.longitude
      : null,
  };
}

function dayRouteEndpoints(
  plan: TravelPlan,
  day: PlanDay,
  includeAccommodationReturn: boolean,
): DayRouteEndpoint[] {
  const items = day.items.map(itemEndpoint);
  const accommodation = accommodationEndpoint(plan);
  if (!accommodation) return items;
  return includeAccommodationReturn && items.length > 0
    ? [accommodation, ...items, accommodation]
    : [accommodation, ...items];
}

export function dayRouteEdges(
  plan: TravelPlan,
  dayNumber: number,
  options: { includeAccommodationReturn?: boolean } = {},
): DayRouteEdge[] {
  const day = plan.days.find((candidate) => candidate.day === dayNumber);
  if (!day) return [];
  const endpoints = dayRouteEndpoints(
    plan,
    day,
    options.includeAccommodationReturn === true,
  );
  return endpoints.slice(0, -1).map((from, index) =>
    routeEdge(from, endpoints[index + 1])
  );
}

function endpointMatchesLeg(
  endpoint: DayRouteEndpoint,
  legItemId: string | null | undefined,
  legPlaceName: string,
): boolean {
  return endpoint.itemId && legItemId
    ? endpoint.itemId === legItemId
    : normalizedName(endpoint.name) === normalizedName(legPlaceName);
}

function legForEdge(
  legs: TransportLeg[],
  edge: DayRouteEdge,
): TransportLeg | null {
  return legs.find((leg) =>
    endpointMatchesLeg(edge.from, leg.fromItemId, leg.fromPlace)
    && endpointMatchesLeg(edge.to, leg.toItemId, leg.toPlace)
  ) ?? null;
}

export function normalizeLegForEdge(
  leg: TransportLeg,
  edge: DayRouteEdge,
): TransportLeg {
  return {
    ...leg,
    fromItemId: edge.from.itemId,
    toItemId: edge.to.itemId,
    fromPlace: edge.from.name,
    toPlace: edge.to.name,
  };
}

export function diffDayRoutes(
  previousPlan: TravelPlan,
  nextPlan: TravelPlan,
  dayNumber: number,
): DayRouteDiff {
  const previousDay = previousPlan.days.find(
    (candidate) => candidate.day === dayNumber,
  );
  const previousLegs = previousDay?.transportLegs ?? [];
  const previousAccommodation = accommodationEndpoint(previousPlan);
  const previousLastItem = previousDay?.items.at(-1);
  const previousReturnEdge = previousAccommodation && previousLastItem
    ? routeEdge(
        itemEndpoint(previousLastItem, (previousDay?.items.length ?? 1) - 1),
        previousAccommodation,
      )
    : null;
  const includeAccommodationReturn = Boolean(
    previousReturnEdge && legForEdge(previousLegs, previousReturnEdge),
  );
  const previousEdges = dayRouteEdges(previousPlan, dayNumber, {
    includeAccommodationReturn,
  });
  const previousLegsByEdgeKey = new Map<string, TransportLeg>();

  for (const edge of previousEdges) {
    const leg = legForEdge(previousLegs, edge);
    if (leg) previousLegsByEdgeKey.set(edge.key, leg);
  }

  const edges = dayRouteEdges(nextPlan, dayNumber, {
    includeAccommodationReturn,
  });
  const reusableLegsByEdgeKey = new Map<string, TransportLeg>();
  const affectedEdges: DayRouteEdge[] = [];

  for (const edge of edges) {
    const reusable = previousLegsByEdgeKey.get(edge.key);
    if (reusable) {
      reusableLegsByEdgeKey.set(edge.key, normalizeLegForEdge(reusable, edge));
    } else {
      affectedEdges.push(edge);
    }
  }

  return { edges, affectedEdges, reusableLegsByEdgeKey };
}

export function mergeDayRouteLegs(
  diff: DayRouteDiff,
  recalculatedLegsByEdgeKey: ReadonlyMap<string, TransportLeg>,
): TransportLeg[] {
  return diff.edges.flatMap((edge) => {
    const leg = recalculatedLegsByEdgeKey.get(edge.key)
      ?? diff.reusableLegsByEdgeKey.get(edge.key);
    return leg ? [normalizeLegForEdge(leg, edge)] : [];
  });
}

export function withDayTransportLegs(
  plan: TravelPlan,
  dayNumber: number,
  transportLegs: TransportLeg[],
): TravelPlan {
  return {
    ...plan,
    days: plan.days.map((day) =>
      day.day === dayNumber ? { ...day, transportLegs } : day
    ),
  };
}

export function dayRouteTopologyKey(
  plan: TravelPlan,
  dayNumber: number,
): string {
  return dayRouteEdges(plan, dayNumber).map((edge) => edge.key).join("|");
}
