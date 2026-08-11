import { apiFetch } from "@/shared/api/client";

export type OpeningHourEntry = {
  dayOfWeek?: number | null;
  dayName?: string | null;
  rawTimeSlots?: string | null;
  openTime?: string | null;
  closeTime?: string | null;
  is24Hours?: boolean | null;
};

export type PlanNoteSource = {
  type: string;
  text?: string | null;
  evidence?: string | null;
  ref?: string | null;
  evidenceTypes?: string[];
  fetchedAt?: string | null;
};

export type KnowledgePlaceType =
  | "TravelPlace"
  | "Restaurant"
  | "DrinkDessert"
  | "Accommodation";

export type PlanItem = {
  itemId?: string | null;
  placeId?: string | null;
  name: string;
  address?: string | null;
  timeWindow: string;
  placeType: string;
  role?: string | null;
  timelineCategory?: "activity" | "food" | "break";
  ontologyType?: KnowledgePlaceType | null;
  source: string;
  sourceRefs: string[];
  sourceProvider?: string | null;
  tags?: string[];
  sourceOrder?: number | null;
  sourceDay?: number | null;
  sourceTimeHint?: string | null;
  sourceActivity?: string | null;
  notes?: string | null;
  noteSources?: PlanNoteSource[];
  personalNotes?: string | null;
  imageUrls?: string[];
  rating?: number | null;
  reviewCount?: number | null;
  openingHours?: OpeningHourEntry[];
  sourceLink?: string | null;
  latitude?: number | null;
  longitude?: number | null;
};

export type PlaceReview = {
  id: string;
  authorName?: string | null;
  rating?: number | null;
  publishedAt?: string | null;
  whenText?: string | null;
  language?: string | null;
  reviewText?: string | null;
};

export type PlaceReviewPage = {
  items: PlaceReview[];
  total: number;
  limit: number;
  offset: number;
  hasMore: boolean;
  ratingCounts: Record<string, number>;
};

export function getPlaceReviews(
  placeId: string,
  options: { rating?: number | null; limit?: number; offset?: number } = {}
): Promise<PlaceReviewPage> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
  });
  if (options.rating != null) {
    params.set("rating", String(options.rating));
  }
  return apiFetch<PlaceReviewPage>(
    `/places/${encodeURIComponent(placeId)}/reviews?${params.toString()}`
  );
}
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
  items: PlanItem[];
  transportLegs: TransportLeg[];
};
export type UnscheduledPlace = {
  placeId?: string | null;
  candidateId?: string | null;
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
  topMatches?: Array<{
    rank: number;
    matchSource:
      | "url_snapshot"
      | "verified_alias"
      | "places_db"
      | "knowledge_graph"
      | "external_provider";
    provider: string;
    placeId?: string | null;
    externalId?: string | null;
    name: string;
    selected: boolean;
    address?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    score: number;
    scoreComponents: Record<string, number>;
    rejectionReasons: string[];
    fetchedAt?: string | null;
  }>;
};
export type TravelPlan = {
  id: string;
  title: string;
  destination: string;
  regionStories?: PlanNoteSource[];
  kind: "main" | "backup";
  days: PlanDay[];
  planningAssumptions?: string[];
  warnings?: string[];
  unscheduledPlaces?: UnscheduledPlace[];
  checkReport?: { status: string; summary: string } | null;
  routeEnrichmentStatus?: "not_required" | "pending" | "completed" | "failed";
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
  ontologyType?: KnowledgePlaceType | null;
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
    matchSource:
      | "url_snapshot"
      | "verified_alias"
      | "places_db"
      | "knowledge_graph"
      | "external_provider";
    provider: string;
    placeId?: string | null;
    externalId?: string | null;
    name: string;
    selected: boolean;
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

export type TripIntent = {
  destination: string;
  timing: {
    days: number;
    startDate?: string | null;
    endDate?: string | null;
    flexibility: "unknown" | "fixed" | "flexible";
    destinationStays: Array<{
      name: string;
      durationDays: number;
      startDay: number;
      endDay: number;
      sourceRefs: string[];
    }>;
  };
  travelParty: {
    type: "solo" | "couple" | "family" | "friends" | "group" | "other";
    adults: number;
    children: number;
    infants: number;
    pets: number;
    rooms: number;
  };
  budget: BudgetEnvelope;
  notes: string[];
  preferences: {
    travelStyle: string;
    pace: string;
    interests: string[];
    mustVisitPlaces: string[];
    avoidPlaces: string[];
    accommodation?: Record<string, unknown>;
    transport?: {
      preferredModes: string[];
      avoidModes: string[];
      includeBetweenPlaces: boolean;
      includeArrivalDeparture: boolean;
    };
  };
  constraints: {
    items: string[];
    policy: Record<string, unknown>;
  };
  clarifyingQuestions: string[];
};

export type ExplorerContext = {
  tripIntent: TripIntent;
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
  ontologyType?: KnowledgePlaceType | null;
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
  noteSources?: PlanNoteSource[];
  personalNotes?: string | null;
  sourceRefs?: string[];
  sourceProvider?: string | null;
  sourceActivity?: string | null;
  imageUrls?: string[];
  rating?: number | null;
  reviewCount?: number | null;
  openingHours?: OpeningHourEntry[];
  sourceLink?: string | null;
};

export type ExploreResponse = {
  intakeId: string;
  userId?: string | null;
  explorer: ExplorerContext;
  allowFinderGapFill: boolean;
  allowReplaceSourcePlaces: boolean;
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
    attemptedQueries: string[];
    aliasQueryCount: number;
    queueWaitSeconds: number;
    executionSeconds: number;
    outcome: "resolved" | "unresolved" | "error" | "timeout" | "cache_hit";
    rejectionReason?: string | null;
  }>;
  logFile?: string | null;
};

export type PlanTimingSubstage = {
  key: string;
  label: string;
  durationSeconds: number;
  details: Record<string, string | number | boolean | null>;
};

export type PlanTimingStage = PlanTimingSubstage & {
  subStages?: PlanTimingSubstage[];
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

export type TripChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  attachmentNames: string[];
  planRevision: number | null;
  turnId?: string | null;
  messageKind?: string;
  contentBlocks?: Array<Record<string, unknown>>;
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
  tripIntentVersion: number;
  tripIntentPlanStatus: "synced" | "queued" | "running" | "failed";
  currentIntakeId?: string | null;
  currentPlan: TravelPlan | null;
  currentTripIntent: TripIntent | null;
  candidateReviews: PlaceCandidateReview[];
  latestExplorerTiming?: ExplorerTimingReport | null;
  latestPlannerTiming?: PlanTimingReport | null;
  messages: TripChatMessage[];
  turns: TripChatTurn[];
};

type CurrentTripChat = {
  id: string;
  title: string;
  threadId: string;
  revision: number;
  hasItinerary: boolean;
  currentItinerary?: Record<string, any> | null;
  createdAt: string;
  updatedAt: string;
  messages?: Array<{
    id: string;
    role: "assistant" | "user";
    content: string;
    route?: string | null;
    clarificationQuestion?: string | null;
    warnings?: string[];
    sources?: Array<Record<string, unknown>>;
    createdAt: string;
  }>;
};

function currentItineraryToPlan(itinerary: Record<string, any> | null | undefined): TravelPlan | null {
  if (!itinerary) return null;
  const intent = itinerary.intent ?? {};
  return {
    id: itinerary.itineraryId ?? itinerary.itinerary_id ?? "agent-itinerary",
    title: `${intent.destination ?? "Chuyến đi"} · ${itinerary.days?.length ?? 0} ngày`,
    destination: intent.destination ?? "",
    kind: "main",
    warnings: itinerary.warnings ?? [],
    days: (itinerary.days ?? []).map((day: any) => ({
      day: day.day,
      transportLegs: [],
      items: (day.items ?? []).map((item: any) => {
        const place = item.place ?? {};
        const start = item.startMinute ?? item.start_minute;
        const end = item.endMinute ?? item.end_minute;
        return {
          itemId: item.itemId ?? item.item_id,
          placeId: place.placeId ?? place.place_id,
          name: place.name ?? "Địa điểm",
          address: null,
          timeWindow: `${formatMinute(start)} – ${formatMinute(end)}`,
          placeType: "activity",
          source: place.source ?? "agent",
          sourceRefs: [],
          latitude: place.coordinates?.latitude ?? null,
          longitude: place.coordinates?.longitude ?? null,
          tags: place.tags ?? [],
        };
      }),
    })),
  };
}

function formatMinute(value: unknown): string {
  const minute = Number(value);
  if (!Number.isFinite(minute)) return "--:--";
  return `${String(Math.floor(minute / 60)).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}`;
}

function mapCurrentTripChat(chat: CurrentTripChat): TripChat {
  const plan = currentItineraryToPlan(chat.currentItinerary);
  return {
    id: chat.id,
    title: chat.title,
    destination: plan?.destination ?? null,
    revision: chat.revision,
    hasPlan: Boolean(plan),
    createdAt: chat.createdAt,
    updatedAt: chat.updatedAt,
    tripIntentVersion: 0,
    tripIntentPlanStatus: "synced",
    currentPlan: plan,
    currentTripIntent: null,
    candidateReviews: [],
    messages: (chat.messages ?? []).map((message) => ({
      id: message.id,
      role: message.role,
      content: message.content,
      attachmentNames: [],
      planRevision: plan ? chat.revision : null,
      createdAt: message.createdAt,
      messageKind: message.role,
      contentBlocks: [],
    })),
    turns: [],
  };
}

async function sendCurrentTripChatMessage(chatId: string, content: string): Promise<TripChat> {
  const response = await apiFetch<{ chat: CurrentTripChat }>(
    `/v1/trip-chats/${encodeURIComponent(chatId)}/messages`,
    { method: "POST", body: JSON.stringify({ content }) },
  );
  return mapCurrentTripChat(response.chat);
}

function completedAgentTurn(chat: TripChat, content: string, clientTurnId?: string): TripChatTurn {
  const now = chat.updatedAt;
  return {
    id: `agent-${chat.id}-${chat.revision}`,
    chatId: chat.id,
    clientTurnId: clientTurnId ?? `agent-${chat.revision}`,
    status: "completed",
    content,
    attachmentNames: [],
    baseRevision: Math.max(0, chat.revision - 1),
    intent: null,
    confidence: null,
    requiresConfirmation: false,
    proposedOperations: [],
    assistantBlocks: [],
    resultSummary: { planRevision: chat.revision },
    errorCode: null,
    errorMessage: null,
    createdAt: now,
    updatedAt: now,
    planRevision: chat.currentPlan ? chat.revision : null,
  };
}

export type UrlImportJob = {
  id: string;
  chatId: string;
  sourceType: "url" | "image";
  sourceLabel: string;
  url: string;
  forceRefresh: boolean;
  status: "queued" | "running" | "succeeded" | "failed";
  phase: "queued" | "exploring" | "planning" | "complete";
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

// --- Conversation supervisor (turns) --------------------------------------

export type TurnStatus =
  | "queued"
  | "classifying"
  | "executing"
  | "awaiting_confirmation"
  | "completed"
  | "failed"
  | "cancelled";

export type TripChatTurn = {
  id: string;
  chatId: string;
  clientTurnId: string;
  status: TurnStatus;
  content: string;
  attachmentNames: string[];
  baseRevision: number;
  intent: string | null;
  confidence: number | null;
  requiresConfirmation: boolean;
  proposedOperations: Array<Record<string, unknown>>;
  assistantBlocks: Array<Record<string, unknown>>;
  resultSummary: Record<string, unknown>;
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
  planRevision: number | null;
};

export const TERMINAL_TURN_STATUSES: ReadonlySet<TurnStatus> = new Set([
  "completed",
  "awaiting_confirmation",
  "failed",
  "cancelled",
]);

const SUPERVISOR_STORAGE_KEY = "travelplanner.supervisor.enabled";
const DEFAULT_SUPERVISOR_ENABLED = true;

/**
 * Build-time default. Override at runtime via
 * ``NEXT_PUBLIC_CONVERSATION_SUPERVISOR_DISABLED`` (string ``"1"`` / ``"true"``
 * force-off) or by writing the boolean to ``localStorage`` under
 * ``travelplanner.supervisor.enabled``. The override always wins so operators can
 * kill the feature without rebuilding.
 */
function readRuntimeSupervisorFlag(): boolean {
  if (typeof window !== "undefined") {
    try {
      const stored = window.localStorage.getItem(SUPERVISOR_STORAGE_KEY);
      if (stored !== null) return stored === "true" || stored === "1";
    } catch {
      // ignore localStorage failures (private mode, SSR)
    }
  }
  const envFlag = process.env.NEXT_PUBLIC_CONVERSATION_SUPERVISOR_DISABLED;
  if (envFlag && ["1", "true", "yes"].includes(envFlag.toLowerCase())) {
    return false;
  }
  return DEFAULT_SUPERVISOR_ENABLED;
}

export function isSupervisorEnabled(): boolean {
  return readRuntimeSupervisorFlag();
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

export async function enrichTripChatRoutes(input: {
  chatId: string;
  expectedRevision: number;
}): Promise<TripChat> {
  return apiFetch<TripChat>(`/trip-chats/${input.chatId}/plan/routes/enrich`, {
    method: "POST",
    body: JSON.stringify({ expectedRevision: input.expectedRevision })
  });
}

export async function enrichPlanRoutes(planId: string): Promise<TravelPlan> {
  return apiFetch<TravelPlan>(`/plans/${planId}/routes/enrich`, {
    method: "POST"
  });
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

export async function createPlanFromExplorer(input: {
  context: ExplorerContext;
  intakeId?: string | null;
  userId?: string | null;
  selectedPlaces?: ExplorePlace[];
  allowFinderGapFill?: boolean;
  allowReplaceSourcePlaces?: boolean;
  signal?: AbortSignal;
}): Promise<PlanGenerationResult> {
  const selectedPlaces = input.selectedPlaces ?? [];

  const response = await apiFetch<PlanGenerationResult | TravelPlan>(
    "/plans/main/from-explorer",
    {
    method: "POST",
    signal: input.signal,
    body: JSON.stringify({
      tripIntent: input.context.tripIntent,
      intakeId: input.intakeId ?? null,
      userId: input.userId ?? null,
      allowFinderGapFill: input.allowFinderGapFill ?? true,
      allowReplaceSourcePlaces: input.allowReplaceSourcePlaces ?? false,
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
        ontologyType: place.ontologyType ?? null,
        tags: [place.category, ...(place.attributes ?? [])],
        sourceRefs: place.sourceUrl ? [place.sourceUrl] : [],
        notes: place.notes ?? null,
        noteSources: place.noteSources ?? [],
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

export async function createTripChat(title?: string): Promise<TripChat> {
  const chat = await apiFetch<CurrentTripChat>("/v1/trip-chats", {
    method: "POST",
    body: JSON.stringify({ title: title || null })
  });
  return mapCurrentTripChat(chat);
}

export async function listTripChats(
  init: Pick<RequestInit, "signal"> = {}
): Promise<TripChatSummary[]> {
  const chats = await apiFetch<CurrentTripChat[]>("/v1/trip-chats", init);
  return chats.map((chat) => mapCurrentTripChat(chat));
}

export async function getTripChat(
  chatId: string,
  init: Pick<RequestInit, "signal"> = {}
): Promise<TripChat> {
  const chat = await apiFetch<CurrentTripChat>(`/v1/trip-chats/${encodeURIComponent(chatId)}`, init);
  return mapCurrentTripChat(chat);
}

export async function updateTripChatIntent(input: {
  chatId: string;
  tripIntent: TripIntent;
  expectedRevision: number;
  expectedTripIntentVersion: number;
}): Promise<TripChat> {
  return sendCurrentTripChatMessage(
    input.chatId,
    `Cập nhật thông tin chuyến đi:\n${JSON.stringify(input.tripIntent)}`,
  );
}

export async function deleteTripChat(chatId: string): Promise<void> {
  return apiFetch<void>(`/v1/trip-chats/${encodeURIComponent(chatId)}`, {
    method: "DELETE"
  });
}

export async function deleteAllTripChats(): Promise<void> {
  return apiFetch<void>("/v1/trip-chats", {
    method: "DELETE"
  });
}

export async function amendTripChat(input: {
  chatId: string;
  content: string;
  expectedRevision: number;
  images?: File[];
}): Promise<TripChat> {
  return sendCurrentTripChatMessage(input.chatId, input.content);
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

export async function confirmTripChatCandidateResolution(input: {
  chatId: string;
  expectedRevision: number;
  candidateId: string;
  matchRank: number;
}): Promise<TripChat> {
  return apiFetch<TripChat>(
    `/trip-chats/${input.chatId}/candidate-resolutions/confirm`,
    {
      method: "POST",
      body: JSON.stringify({
        expectedRevision: input.expectedRevision,
        candidateId: input.candidateId,
        matchRank: input.matchRank,
      })
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
  await sendCurrentTripChatMessage(input.chatId, `${input.content}\n\nNguồn URL:\n${input.urls.join("\n")}`);
  return { jobs: [] };
}

export async function enqueueTripChatImages(input: {
  chatId: string;
  content: string;
  expectedRevision: number;
  images: File[];
}): Promise<UrlImportJobBatch> {
  await sendCurrentTripChatMessage(input.chatId, input.content);
  return { jobs: [] };
}

export async function listUrlImportJobs(): Promise<UrlImportJobBatch> {
  return { jobs: [] };
}

export async function listActiveTripChatTurns(): Promise<TripChatTurn[]> {
  return [];
}

export async function listTripChatPlannerRuns(): Promise<TripChatTurn[]> {
  return [];
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
  personalNotes?: string | null;
  tags?: string[];
  position?: number | null;
  rating?: number | null;
  reviewCount?: number | null;
  imageUrls?: string[];
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
  if (input.item.personalNotes) form.append("personalNotes", input.item.personalNotes);
  if (input.item.position != null) form.append("position", String(input.item.position));

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
  place: Pick<UnscheduledPlace, "name" | "placeId" | "candidateId">;
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));
  form.append("name", input.place.name);
  if (input.place.placeId) form.append("placeId", input.place.placeId);
  if (input.place.candidateId) {
    form.append("candidateId", input.place.candidateId);
  }

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
  imageUrl?: string | null;
  rating?: number | null;
  reviewCount?: number | null;
  priceLevel?: number | null;
  placeType?: string | null;
  phone?: string | null;
  website?: string | null;
  openingHours?: string[] | null;
  isVerified?: boolean;
  source?: "knowledge_graph" | "google_maps_scraper" | string | null;
};

export const PLACE_SEARCH_TOP_K = 5;

export async function searchPlaces(
  query: string,
  destination?: string,
  topK = PLACE_SEARCH_TOP_K
): Promise<PlaceSuggestion[]> {
  const params = new URLSearchParams({ query, topK: String(topK) });
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

export async function selectTripChatTransportOption(input: {
  chatId: string;
  expectedRevision: number;
  day: number;
  legIndex: number;
  mode: string;
  optionKey?: string;
  source?: string;
  distanceMeters?: number;
  estimatedDurationMinutes?: number;
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));
  form.append("mode", input.mode);
  if (input.optionKey) form.append("optionKey", input.optionKey);
  if (input.source) form.append("source", input.source);
  if (input.distanceMeters != null) {
    form.append("distanceMeters", String(input.distanceMeters));
  }
  if (input.estimatedDurationMinutes != null) {
    form.append(
      "estimatedDurationMinutes",
      String(input.estimatedDurationMinutes)
    );
  }

  return apiFetch<TripChat>(
    `/trip-chats/${input.chatId}/plan/days/${input.day}/transport-legs/${input.legIndex}/selection`,
    {
      method: "PUT",
      body: form
    }
  );
}

export async function retryTripChatTransportLeg(input: {
  chatId: string;
  expectedRevision: number;
  day: number;
  legIndex: number;
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));
  return apiFetch<TripChat>(
    `/trip-chats/${input.chatId}/plan/days/${input.day}/transport-legs/${input.legIndex}/retry`,
    {
      method: "POST",
      body: form
    }
  );
}

// --- Conversation supervisor endpoints -------------------------------------

export async function createTripChatTurn(input: {
  chatId: string;
  content: string;
  expectedRevision: number;
  clientTurnId?: string;
  attachmentNames?: string[];
}): Promise<TripChatTurn> {
  const chat = await sendCurrentTripChatMessage(input.chatId, input.content);
  return completedAgentTurn(chat, input.content, input.clientTurnId);
}

export async function getTripChatTurn(input: {
  chatId: string;
  turnId: string;
}): Promise<TripChatTurn> {
  const chat = await getTripChat(input.chatId);
  const lastUserMessage = [...chat.messages].reverse().find((message) => message.role === "user");
  return completedAgentTurn(chat, lastUserMessage?.content ?? "", input.turnId);
}


export async function executeTripChatTurn(input: {
  chatId: string;
  turnId: string;
}): Promise<TripChatTurn> {
  const chat = await getTripChat(input.chatId);
  return completedAgentTurn(chat, "", input.turnId);
}

export async function confirmTripChatTurn(input: {
  chatId: string;
  turnId: string;
}): Promise<TripChatTurn> {
  const chat = await getTripChat(input.chatId);
  return completedAgentTurn(chat, "", input.turnId);
}

export async function cancelTripChatTurn(input: {
  chatId: string;
  turnId: string;
}): Promise<TripChatTurn> {
  const chat = await getTripChat(input.chatId);
  return { ...completedAgentTurn(chat, "", input.turnId), status: "cancelled" };
}
