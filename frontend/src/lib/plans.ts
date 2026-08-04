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
  tags?: string[];
  sourceOrder?: number | null;
  sourceDay?: number | null;
  sourceTimeHint?: string | null;
  sourceActivity?: string | null;
  notes?: string | null;
  personalNotes?: string | null;
  imageUrls?: string[];
  rating?: number | null;
  reviewCount?: number | null;
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
export type PlanDay = {
  day: number;
  theme: string;
  items: PlanItem[];
  transportLegs: TransportLeg[];
};
export type UnscheduledPlace = {
  placeId?: string | null;
  name: string;
  day?: number | null;
  reasonCode: string;
  reason: string;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  placeType?: string | null;
  tags?: string[];
  sourceRefs?: string[];
  sourceProvider?: string | null;
  sourceActivity?: string | null;
  rating?: number | null;
  reviewCount?: number | null;
};
export type TravelPlan = {
  id: string;
  title: string;
  destination: string;
  kind: "main" | "backup";
  days: PlanDay[];
  planningAssumptions?: string[];
  warnings?: string[];
  unscheduledPlaces?: UnscheduledPlace[];
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

export type PlaceCandidateReview = {
  candidateId: string;
  name: string;
  category: PlaceCategory;
  status: "resolved" | "needs_review" | "merged" | "ignored";
  resolutionReason?: string | null;
  provider?: string | null;
  resolvedName?: string | null;
  verifiedAliases: string[];
  verifiedVietnameseAliases: string[];
  observedAliases: Array<{
    value: string;
    source: "metadata" | "caption" | "transcript" | "stt" | "ocr" | "user";
  }>;
  generatedLookupAliases: Array<{
    value: string;
    language: "vi" | "en" | "und";
    generator: "normalizer" | "llm";
    version: string;
  }>;
  topMatches: Array<{
    rank: number;
    matchSource: "url_snapshot" | "verified_alias" | "places_db" | "external_provider";
    provider: string;
    placeId?: string | null;
    externalId?: string | null;
    name: string;
    address?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    score: number;
    scoreComponents: Record<string, number>;
    rejectionReasons: string[];
    fetchedAt?: string | null;
  }>;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  hasRepresentativeLocation: boolean;
  searchRegion?: string | null;
  sourceUrls: string[];
  sourceOrder?: number | null;
  sourceDay?: number | null;
  sourceTimeHint?: string | null;
  sourceActivity?: string | null;
  sourceDurationMinutes?: number | null;
  confidence: number;
  extractionConfidence: number;
  resolutionConfidence: number;
  retryable: boolean;
  entityType?: "venue" | "sub_place";
  authority?: "high" | "medium" | "low";
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
    destinationStays?: Array<{
      name: string;
      durationDays: number;
      startDay: number;
      endDay: number;
      sourceRefs: string[];
    }>;
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
  candidateReviews?: PlaceCandidateReview[];
  trace?: {
    destinationGuardrail?: {
      status: "matched" | "corrected";
      authority: "url_evidence";
      requestedDestination: string;
      sourceDestination: string;
      supportingStopCount: number;
      locatedStopCount: number;
    };
    [key: string]: unknown;
  };
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
  imageUrls?: string[];
  rating?: number | null;
  reviewCount?: number | null;
};

export type ExploreResponse = {
  intakeId: string;
  userId?: string | null;
  explorer: ExplorerContext;
  allowPlaceSuggestions: boolean;
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
  cacheStatus?: "hit" | "miss" | "bypassed" | "unknown";
  cacheLookupSeconds?: number;
  stages: ExplorerTimingStage[];
  sampledFrames: number;
  speechStatus: string;
  speechSource?: string;
  visionStatus: string;
  sttChunkCount?: number;
  sttAudioDurationSeconds?: number | null;
  sttChunkDurationSeconds?: number[];
  sttChunkRetryCount?: number;
  extractedPlaceCount: number;
  expectedPlaceCount?: number | null;
  extractionCoverage?: number | null;
  coverageStatus?: "unknown" | "sufficient" | "review" | "insufficient";
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
  providerAttempts?: Array<{
    candidate: string;
    provider: string;
    aliasQueryCount: number;
    queueWaitSeconds: number;
    executionSeconds: number;
    outcome: "resolved" | "unresolved" | "error" | "timeout" | "cache_hit";
    rejectionReason?: string | null;
  }>;
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
  currentIntakeId?: string | null;
  currentPlan: TravelPlan | null;
  currentExplorer: ExplorerContext | null;
  latestExplorerTiming?: ExplorerTimingReport | null;
  latestPlannerTiming?: PlanTimingReport | null;
  messages: TripChatMessage[];
};

export type UrlImportJob = {
  id: string;
  chatId: string;
  sourceType: "url" | "image";
  sourceLabel: string;
  url: string;
  forceRefresh: boolean;
  status: "queued" | "running" | "succeeded" | "failed";
  queuePosition: number | null;
  attemptCount: number;
  resultRevision: number | null;
  errorCode: string | null;
  errorMessage: string | null;
  explorerTiming: ExplorerTimingReport | null;
  plannerTiming: PlanTimingReport | null;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
};

export type UrlImportJobBatch = { jobs: UrlImportJob[] };

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
  forceRefresh?: boolean;
}, signal?: AbortSignal): Promise<ExploreResponse> {
  const form = new FormData();
  form.append("rawRequest", input.rawRequest);
  form.append("forceRefresh", String(input.forceRefresh ?? false));
  for (const url of input.urls ?? []) {
    form.append("urls", url);
  }
  for (const image of input.images ?? []) {
    form.append("images", image);
  }
  return apiFetch<ExploreResponse>("/plans/explore/full/intake", {
    method: "POST",
    body: form,
    signal
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
    allowPlaceSuggestions: explore.allowPlaceSuggestions
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
  allowPlaceSuggestions?: boolean;
  signal?: AbortSignal;
}): Promise<PlanGenerationResult> {
  const selectedPlaces = input.selectedPlaces ?? [];

  const response = await apiFetch<PlanGenerationResult | TravelPlan>(
    "/plans/main/from-explorer",
    {
    method: "POST",
    signal: input.signal,
    body: JSON.stringify({
      intent: input.context.intent,
      tripSpec: input.context.tripSpec,
      intakeId: input.intakeId ?? null,
      userId: input.userId ?? null,
      allowPlaceSuggestions: input.allowPlaceSuggestions ?? true,
      candidateReviews: input.context.candidateReviews ?? [],
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
        notes: place.notes ?? null,
        imageUrls: place.imageUrls ?? [],
        rating: place.rating ?? null,
        reviewCount: place.reviewCount ?? null
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

export async function retryTripChatCandidateResolutions(input: {
  chatId: string;
  expectedRevision: number;
}): Promise<TripChat> {
  return apiFetch<TripChat>(
    `/trip-chats/${input.chatId}/candidate-resolutions/retry`,
    {
      method: "POST",
      body: JSON.stringify({ expectedRevision: input.expectedRevision })
    }
  );
}

export async function enqueueTripChatUrls(input: {
  chatId: string;
  content: string;
  expectedRevision: number;
  urls: string[];
  forceRefresh?: boolean;
}): Promise<UrlImportJobBatch> {
  const form = new FormData();
  form.append("content", input.content);
  form.append("expectedRevision", String(input.expectedRevision));
  for (const url of input.urls) form.append("urls", url);
  form.append("forceRefresh", String(input.forceRefresh ?? false));
  return apiFetch<UrlImportJobBatch>(`/trip-chats/${input.chatId}/url-jobs`, {
    method: "POST",
    body: form
  });
}

export async function enqueueTripChatImages(input: {
  chatId: string;
  content: string;
  expectedRevision: number;
  images: File[];
}): Promise<UrlImportJobBatch> {
  const form = new FormData();
  form.append("content", input.content);
  form.append("expectedRevision", String(input.expectedRevision));
  for (const image of input.images) form.append("images", image);
  return apiFetch<UrlImportJobBatch>(`/trip-chats/${input.chatId}/image-jobs`, {
    method: "POST",
    body: form
  });
}

export async function listUrlImportJobs(): Promise<UrlImportJobBatch> {
  return apiFetch<UrlImportJobBatch>("/url-import-jobs");
}

export async function retryUrlImportJob(jobId: string): Promise<UrlImportJob> {
  return apiFetch<UrlImportJob>(`/url-import-jobs/${jobId}/retry`, {
    method: "POST"
  });
}

export async function reprocessUrlImportJob(jobId: string): Promise<UrlImportJob> {
  return apiFetch<UrlImportJob>(`/url-import-jobs/${jobId}/reprocess`, {
    method: "POST"
  });
}

export async function deleteUrlImportJob(jobId: string): Promise<void> {
  return apiFetch<void>(`/url-import-jobs/${jobId}`, {
    method: "DELETE"
  });
}

export type AddItemInput = {
  day: number;
  placeId?: string | null;
  name: string;
  address?: string | null;
  placeType?: string;
  timeWindow?: string | null;
  durationMinutes?: number;
  latitude?: number | null;
  longitude?: number | null;
  notes?: string | null;
  personalNotes?: string | null;
  tags?: string[];
  position?: number | null;
};

export type UpdateItemInput = {
  placeId?: string | null;
  name?: string | null;
  address?: string | null;
  placeType?: string | null;
  timeWindow?: string | null;
  durationMinutes?: number | null;
  latitude?: number | null;
  longitude?: number | null;
  notes?: string | null;
  personalNotes?: string | null;
  tags?: string[] | null;
};

export async function addTripChatItem(input: {
  chatId: string;
  expectedRevision: number;
  item: AddItemInput;
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));
  form.append("day", String(input.item.day));
  if (input.item.placeId) form.append("placeId", input.item.placeId);
  form.append("name", input.item.name);
  if (input.item.address) form.append("address", input.item.address);
  if (input.item.placeType) form.append("placeType", input.item.placeType);
  if (input.item.timeWindow) form.append("timeWindow", input.item.timeWindow);
  if (input.item.durationMinutes) form.append("durationMinutes", String(input.item.durationMinutes));
  if (input.item.latitude != null) form.append("latitude", String(input.item.latitude));
  if (input.item.longitude != null) form.append("longitude", String(input.item.longitude));
  if (input.item.notes) form.append("notes", input.item.notes);
  if (input.item.personalNotes) form.append("personalNotes", input.item.personalNotes);

  return apiFetch<TripChat>(`/trip-chats/${input.chatId}/plan/items`, {
    method: "POST",
    body: form
  });
}

export async function updateTripChatItem(input: {
  chatId: string;
  expectedRevision: number;
  day: number;
  itemId: string;
  item: UpdateItemInput;
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));
  if (input.item.placeId !== undefined) form.append("placeId", input.item.placeId || "");
  if (input.item.name) form.append("name", input.item.name);
  if (input.item.address !== undefined) form.append("address", input.item.address || "");
  if (input.item.placeType) form.append("placeType", input.item.placeType);
  if (input.item.timeWindow !== undefined) form.append("timeWindow", input.item.timeWindow || "");
  if (input.item.durationMinutes != null) form.append("durationMinutes", String(input.item.durationMinutes));
  if (input.item.latitude != null) form.append("latitude", String(input.item.latitude));
  if (input.item.longitude != null) form.append("longitude", String(input.item.longitude));
  if (input.item.notes !== undefined) form.append("notes", input.item.notes || "");
  if (input.item.personalNotes !== undefined) form.append("personalNotes", input.item.personalNotes || "");

  return apiFetch<TripChat>(`/trip-chats/${input.chatId}/plan/days/${input.day}/items/${input.itemId}`, {
    method: "PATCH",
    body: form
  });
}

export async function removeTripChatItem(input: {
  chatId: string;
  expectedRevision: number;
  day: number;
  itemId: string;
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));

  return apiFetch<TripChat>(`/trip-chats/${input.chatId}/plan/days/${input.day}/items/${input.itemId}`, {
    method: "DELETE",
    body: form
  });
}

export async function removeTripChatUnscheduledPlace(input: {
  chatId: string;
  expectedRevision: number;
  place: Pick<UnscheduledPlace, "name" | "placeId">;
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));
  form.append("name", input.place.name);
  if (input.place.placeId) form.append("placeId", input.place.placeId);

  return apiFetch<TripChat>(`/trip-chats/${input.chatId}/plan/unscheduled-places`, {
    method: "DELETE",
    body: form
  });
}

export type PlaceSuggestion = {
  name: string;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  placeId?: string | null;
};

export async function searchPlaces(query: string, destination?: string): Promise<PlaceSuggestion[]> {
  const params = new URLSearchParams({ query });
  if (destination) params.append("destination", destination);
  return apiFetch<PlaceSuggestion[]>(`/plans/places/search?${params.toString()}`);
}

export async function reorderTripChatItem(input: {
  chatId: string;
  expectedRevision: number;
  day: number;
  itemIds: string[];
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));
  for (const itemId of input.itemIds) {
    form.append("itemIds", itemId);
  }

  return apiFetch<TripChat>(`/trip-chats/${input.chatId}/plan/days/${input.day}/items/reorder`, {
    method: "PUT",
    body: form
  });
}
