export type TransportOption = {
  mode: string;
  distanceMeters: number;
  estimatedDurationMinutes: number;
  geometryCoordinates: [number, number][];
  source: string;
  verified: boolean;
  estimatedCostPerPerson?: number | null;
  currency?: string | null;
  fetchedAt?: string | null;
  details?: {
    transitModes?: string[];
    lines?: string[];
    scheduleStatus?: string;
    segments?: Array<{
      mode: string;
      fromPlace: string;
      toPlace: string;
      distanceMeters: number;
      estimatedDurationMinutes: number;
      geometryCoordinates: [number, number][];
      line?: string | null;
      headsign?: string | null;
    }>;
  };
};

export type TransportLeg = TransportOption & {
  fromItemId?: string | null;
  toItemId?: string | null;
  fromPlace: string;
  toPlace: string;
  alternatives?: TransportOption[];
};

export type CurrentLocationRouteInput = {
  origin: {
    latitude: number;
    longitude: number;
    name?: string;
  };
  destination: {
    itemId?: string | null;
    name: string;
    selected: boolean;
    address?: string | null;
    timeWindow?: string | null;
    latitude: number;
    longitude: number;
  };
  departureTime?: string | null;
  preferredModes?: string[];
  avoidModes?: string[];
};

export type DayDirectionsInput = {
  origin: {
    latitude: number;
    longitude: number;
    name?: string;
  };
  destinations: Array<{
    itemId?: string | null;
    name: string;
    address?: string | null;
    latitude: number;
    longitude: number;
  }>;
  requestedMode?: "walk" | "car" | "bus" | null;
  departureTime?: string | null;
};
