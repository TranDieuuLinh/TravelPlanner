import { apiFetch } from "@/lib/api";

export type PlanItem = {
  itemId?: string | null;
  placeId?: string | null;
  name: string;
  address?: string | null;
  timeWindow: string;
  placeType: string;
  role?: string | null;
  timelineCategory?: "activity" | "food" | "break";
  source: string;
  sourceRefs: string[];
  sourceProvider?: string | null;
  sourceOrder?: number | null;
  sourceDay?: number | null;
  notes?: string | null;
  latitude?: number | null;
  longitude?: number | null;
};
export type TransportOption = {
  mode: string;
  distanceMeters: number;
  estimatedDurationMinutes: number;
  geometryCoordinates: [number, number][];
  source: string;
  verified: boolean;
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
  };
  destination: {
    itemId?: string | null;
    name: string;
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
export type PlanDay = {
  day: number;
  theme: string;
  items: PlanItem[];
  transportLegs: TransportLeg[];
};
export type TravelPlan = {
  id: string;
  title: string;
  destination: string;
  kind: "main" | "backup";
  days: PlanDay[];
  checkReport?: { status: string; summary: string } | null;
};

export type FeatureMapItem = {
  stage: string;
  feature: string;
  description: string;
};

export type PlanBundle = {
  mainPlan: TravelPlan;
  backupPlan: TravelPlan;
  validation: { status: string; summary: string };
};

export type PlaceCategory =
  | "attraction"
  | "food"
  | "cafe"
  | "hotel"
  | "transport"
  | "free_time"
  | "nature"
  | "culture"
  | "shopping"
  | "nightlife"
  | "wellness"
  | "adventure"
  | "beach"
  | "family"
  | "other";

export type BudgetLevel = "low" | "medium" | "high";

export type BudgetEnvelope = {
  targetAmount?: number | null;
  currency: string;
  level: BudgetLevel;
};

export type PreferenceSignal = {
  dimension: string;
  value: string;
  score: number;
  confidence: number;
  scope: "trip" | "destination" | "global";
  destination?: string | null;
  sourceTypes: string[];
};

export type LongTermPreferenceProfile = {
  version: number;
  explicit: string[];
  scores: Record<string, {
    score: number;
    confidence: number;
    observations: number;
    sourceTypes: string[];
    lastObservedAt?: string | null;
  }>;
  observationCount: number;
  updatedAt?: string | null;
};

export type PreferenceSnapshot = {
  version: number;
  signals: PreferenceSignal[];
  effectiveProfile: LongTermPreferenceProfile;
};

export type ExplorerContext = {
  intent: {
    destination: string;
    travelStyle: string;
    pace: string;
    interests: string[];
    mustVisitPlaces: string[];
    avoidPlaces: string[];
    constraints: string[];
    clarifyingQuestions: string[];
  };
  tripSpec: {
    days: number;
    partySize: number;
    startDate?: string | null;
    endDate?: string | null;
    transport?: {
      preferredModes: string[];
      avoidModes: string[];
      includeBetweenPlaces: boolean;
      includeArrivalDeparture: boolean;
    };
    budget: BudgetEnvelope;
  };
  assumptions: string[];
  missingInfoQuestions: string[];
  preferenceSnapshot: PreferenceSnapshot;
};

export type ExplorePlace = {
  name: string;
  category: PlaceCategory;
  placeId?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  source?: string;
  sourceUrl?: string | null;
  confidence?: number;
  priority?: number;
  preferenceLevel?: "mentioned" | "preferred" | "must_visit";
  attributes?: string[];
  notes?: string | null;
};

export type ExploreResponse = {
  intakeId: string;
  userId?: string | null;
  explorer: ExplorerContext;
  allowFinderSuggestions: boolean;
  timingReport?: ExplorerTimingReport | null;
};

export type ExplorerTimingStage = {
  key: string;
  label: string;
  durationSeconds: number;
  details: Record<string, string | number | boolean | null>;
};

export type ExplorerSourceTiming = {
  sourceIndex: number;
  platform: string;
  totalSeconds: number;
  stages: ExplorerTimingStage[];
  sampledFrames: number;
  speechStatus: string;
  visionStatus: string;
  sttChunkCount?: number;
  sttAudioDurationSeconds?: number | null;
  sttChunkDurationSeconds?: number[];
  sttChunkRetryCount?: number;
  extractedPlaceCount: number;
  candidateCount?: number;
  resolvedCount?: number;
  providerCounts?: Record<string, number>;
  resolvedProviderCounts?: Record<string, number>;
};

export type ExplorerTimingReport = {
  intakeId: string;
  status: string;
  totalSeconds: number;
  stages: ExplorerTimingStage[];
  sources: ExplorerSourceTiming[];
  urlCount: number;
  imageCount: number;
  candidateCount: number;
  resolvedCount: number;
  persistedCount: number;
  providerCounts: Record<string, number>;
  resolvedProviderCounts?: Record<string, number>;
  logFile?: string | null;
};

export type PlanTimingStage = {
  key: string;
  label: string;
  durationSeconds: number;
  details: Record<string, string | number | boolean | null>;
};

export type PlanTimingReport = {
  status: string;
  totalSeconds: number;
  stages: PlanTimingStage[];
  dayCount: number;
  itemCount: number;
  transportLegCount: number;
  unscheduledCount: number;
  warningCount: number;
};

export type PlanGenerationResult = {
  plan: TravelPlan;
  timingReport?: PlanTimingReport | null;
};

export type PlannerIntakeInput = {
  rawRequest: string;
  urls?: string[];
  images?: File[];
};

export type PlannerIntakeResult = {
  explore: ExploreResponse;
  plan: TravelPlan;
};

export type TripChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  attachmentNames: string[];
  planRevision: number | null;
  createdAt: string;
};

export type TripChatSummary = {
  id: string;
  title: string;
  destination: string | null;
  revision: number;
  hasPlan: boolean;
  createdAt: string;
  updatedAt: string;
};

export type TripChat = TripChatSummary & {
  currentPlan: TravelPlan | null;
  currentExplorer: ExplorerContext | null;
  latestExplorerTiming?: ExplorerTimingReport | null;
  latestPlannerTiming?: PlanTimingReport | null;
  messages: TripChatMessage[];
};

export async function createPlan(input: { destination: string; days: number; interests: string[] }): Promise<TravelPlan> {
  return apiFetch<TravelPlan>("/plans/main", {
    method: "POST",
    body: JSON.stringify({
      destination: input.destination,
      days: input.days,
      budget: "medium",
      travelStyle: "local",
      pace: "balanced",
      interests: input.interests,
      mustVisitPlaces: [],
      avoidPlaces: [],
      constraints: [],
      selectedPlaces: []
    })
  });
}

export async function exploreFullIntake(input: {
  rawRequest: string;
  urls?: string[];
  images?: File[];
}): Promise<ExploreResponse> {
  const form = new FormData();
  form.append("rawRequest", input.rawRequest);
  for (const url of input.urls ?? []) {
    form.append("urls", url);
  }
  for (const image of input.images ?? []) {
    form.append("images", image);
  }

  return apiFetch<ExploreResponse>("/plans/explore/full/intake", {
    method: "POST",
    body: form
  });
}

export async function runPlannerIntake(
  input: PlannerIntakeInput
): Promise<PlannerIntakeResult> {
  const explore = await exploreFullIntake(input);
  const generation = await createPlanFromExplorer({
    context: explore.explorer,
    intakeId: explore.intakeId,
    userId: explore.userId,
    allowFinderSuggestions: explore.allowFinderSuggestions
  });

  return { explore, plan: generation.plan };
}

export async function getPlanFeatureMap(): Promise<FeatureMapItem[]> {
  return apiFetch<FeatureMapItem[]>("/plans/feature-map");
}

export async function calculateCurrentLocationRoute(
  input: CurrentLocationRouteInput
): Promise<TransportLeg> {
  return apiFetch<TransportLeg>("/plans/current-location-route", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function calculateDayDirections(
  input: DayDirectionsInput
): Promise<TransportLeg[]> {
  return apiFetch<TransportLeg[]>("/plans/day-directions", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function exploreFull(
  input: Record<string, unknown>
): Promise<ExploreResponse> {
  return apiFetch<ExploreResponse>("/plans/explore/full", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function createPlanFromExplorer(input: {
  context: ExplorerContext;
  intakeId?: string | null;
  userId?: string | null;
  selectedPlaces?: ExplorePlace[];
  allowFinderSuggestions?: boolean;
}): Promise<PlanGenerationResult> {
  const selectedPlaces = input.selectedPlaces ?? [];

  const response = await apiFetch<PlanGenerationResult | TravelPlan>(
    "/plans/main/from-explorer",
    {
    method: "POST",
    body: JSON.stringify({
      intent: input.context.intent,
      tripSpec: input.context.tripSpec,
      intakeId: input.intakeId ?? null,
      userId: input.userId ?? null,
      allowFinderSuggestions: input.allowFinderSuggestions ?? true,
      selectedPlaces: selectedPlaces.map((place) => ({
        name: place.name,
        placeId: place.placeId ?? null,
        address: place.address ?? null,
        priority: place.priority ?? 1,
        mustVisit: place.preferenceLevel === "must_visit",
        preferenceLevel: place.preferenceLevel ?? "preferred",
        latitude: place.latitude ?? null,
        longitude: place.longitude ?? null,
        tags: [place.category, ...(place.attributes ?? [])],
        sourceRefs: place.sourceUrl ? [place.sourceUrl] : [],
        notes: place.notes ?? null
      })),
      preferenceProfile: input.context.preferenceSnapshot.effectiveProfile
    })
    }
  );

  if ("plan" in response) {
    return response;
  }

  return {
    plan: response,
    timingReport: null
  };
}

export async function createBackupPlan(
  planId: string,
  input: {
    reason?: string;
    constraints?: string[];
    keepDays?: boolean;
    avoidOutdoor?: boolean;
  } = {}
): Promise<PlanBundle> {
  return apiFetch<PlanBundle>(`/plans/${planId}/backup`, {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function createTripChat(title?: string): Promise<TripChat> {
  return apiFetch<TripChat>("/trip-chats", {
    method: "POST",
    body: JSON.stringify({ title: title || null })
  });
}

export async function listTripChats(): Promise<TripChatSummary[]> {
  return apiFetch<TripChatSummary[]>("/trip-chats");
}

export async function getTripChat(chatId: string): Promise<TripChat> {
  return apiFetch<TripChat>(`/trip-chats/${chatId}`);
}

export async function deleteTripChat(chatId: string): Promise<void> {
  return apiFetch<void>(`/trip-chats/${chatId}`, {
    method: "DELETE"
  });
}

export async function amendTripChat(input: {
  chatId: string;
  content: string;
  expectedRevision: number;
  images?: File[];
}): Promise<TripChat> {
  const form = new FormData();
  form.append("content", input.content);
  form.append("expectedRevision", String(input.expectedRevision));
  for (const image of input.images ?? []) {
    form.append("images", image);
  }
  return apiFetch<TripChat>(`/trip-chats/${input.chatId}/messages`, {
    method: "POST",
    body: form
  });
}
