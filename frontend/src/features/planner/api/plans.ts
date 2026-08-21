import { apiFetch } from "@/shared/api/client";
import { plannerOutputToTravelPlan } from "@/features/planner/lib/planner-output";
import {
  mapCurrentTripChat,
  mapCurrentTripChatSummary,
  type CurrentTripChat,
  type CurrentTripChatSummary,
} from "@/features/planner/lib/trip-chat-mapping";
import type {
  TransportLeg,
  TransportOption,
} from "@/features/planner/contracts/transport";
import type { AnswerBlock } from "@/features/planner/lib/answer-blocks";
import type { PlaceSuggestion } from "@/features/planner/api/place-search";

export type {
  CurrentLocationRouteInput,
  DayDirectionsInput,
  TransportLeg,
  TransportOption,
} from "@/features/planner/contracts/transport";
export {
  calculateCurrentLocationRoute,
  calculateDayDirections,
} from "@/features/planner/api/directions";
export { getPlaceReviews } from "@/features/planner/api/reviews";
export type {
  PlaceReview,
  PlaceReviewPage,
} from "@/features/planner/api/reviews";
export {
  listSubplaces,
  PLACE_SEARCH_TOP_K,
  searchPlaces,
} from "@/features/planner/api/place-search";
export type {
  PlaceSuggestion,
  SubplaceGroup,
  SubplaceSummary,
} from "@/features/planner/api/place-search";

const mapFullCurrentTripChat = (chat: CurrentTripChat): TripChat =>
  mapCurrentTripChat(chat, plannerOutputToTravelPlan);

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

export type PlanSourceNote = {
  text: string;
  sourceType: "url" | "google_maps" | "knowledge_graph" | "backend";
  sourceUrl?: string | null;
};

export type KnowledgePlaceType =
  | "TravelPlace"
  | "Restaurant"
  | "DrinkDessert"
  | "Entertainment"
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
  notes?: PlanSourceNote | string | null;
  noteSources?: PlanNoteSource[];
  personalNotes?: string | null;
  imageUrls?: string[];
  rating?: number | null;
  reviewCount?: number | null;
  openingHours?: OpeningHourEntry[];
  sourceLink?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  durationMinutes?: number | null;
  costPerPerson?: number | null;
};

export type PlanCostBreakdown = {
  accommodation: number;
  food: number;
  localTransport: number;
  activities: number;
  misc: number;
  total: number;
  currency: string;
};

export type PlanDay = {
  day: number;
  items: PlanItem[];
  transportLegs: TransportLeg[];
  costBreakdown?: PlanCostBreakdown | null;
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
  notes?: PlanSourceNote | string | null;
  personalNotes?: string | null;
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
  travelerCount?: number | null;
  regionStories?: PlanNoteSource[];
  kind: "main" | "backup";
  days: PlanDay[];
  accommodation?: {
    placeId: string;
    name: string;
    address?: string | null;
    latitude: number;
    longitude: number;
    rating?: number | null;
    reviewCount?: number | null;
    pricePerNight: number;
    currency: string;
    nights: number;
    personalNotes?: string | null;
  } | null;
  budget?: {
    amountPerPerson: number | null;
    currency: string;
    source: "explicit" | "estimated_daily_cost" | "unspecified";
    dailyEstimate?: {
      accommodation: number;
      food: number;
      localTransport: number;
      activities: number;
      total: number;
    } | null;
  };
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
  notes?: PlanSourceNote | string | null;
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

export type TripChatMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  attachmentNames: string[];
  planRevision: number | null;
  turnId?: string | null;
  messageKind?: string;
  contentBlocks?: AnswerBlock[];
  sources: TripChatSource[];
  createdAt: string;
  suggestions?: Array<{ field: string; label: string; value: string | number; currency?: string }>;
};

export type TripChatSource = {
  sourceId: string;
  title: string;
  url: string;
  updatedAt?: string | null;
  dateKind?: string | null;
  reviewStatus?: string | null;
  publishedAt?: string | null;
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

async function sendCurrentTripChatMessage(chatId: string, content: string): Promise<TripChat> {
  const response = await apiFetch<{ chat: CurrentTripChat }>(
    `/v1/trip-chats/${encodeURIComponent(chatId)}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ content }),
    },
  );
  return mapFullCurrentTripChat(response.chat);
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
    chatSnapshot: chat,
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
  chatSnapshot?: TripChat;
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

export async function enrichTripChatRoutes(input: {
  chatId: string;
  expectedRevision: number;
}): Promise<TripChat> {
  return apiFetch<TripChat>(`/trip-chats/${input.chatId}/plan/routes/enrich`, {
    method: "POST",
    body: JSON.stringify({ expectedRevision: input.expectedRevision })
  });
}


export async function createTripChat(title?: string): Promise<TripChat> {
  const chat = await apiFetch<CurrentTripChat>("/v1/trip-chats", {
    method: "POST",
    body: JSON.stringify({ title: title || null })
  });
  return mapFullCurrentTripChat(chat);
}

export async function listTripChats(
  init: Pick<RequestInit, "signal"> = {}
): Promise<TripChatSummary[]> {
  const chats = await apiFetch<CurrentTripChatSummary[]>("/v1/trip-chats?limit=30", init);
  return chats.map(mapCurrentTripChatSummary);
}

export async function bootstrapTripChats(
  chatId: string | null,
  init: Pick<RequestInit, "signal"> = {}
): Promise<{ chats: TripChatSummary[]; activeChat: TripChat | null }> {
  const params = new URLSearchParams({ limit: "30" });
  if (chatId) params.set("chatId", chatId);
  const response = await apiFetch<{
    chats: CurrentTripChatSummary[];
    activeChat: CurrentTripChat | null;
  }>(`/v1/trip-chats/bootstrap?${params.toString()}`, init);
  return {
    chats: response.chats.map(mapCurrentTripChatSummary),
    activeChat: response.activeChat
      ? mapFullCurrentTripChat(response.activeChat)
      : null,
  };
}

export async function getTripChat(
  chatId: string,
  init: Pick<RequestInit, "signal"> = {}
): Promise<TripChat> {
  const chat = await apiFetch<CurrentTripChat>(`/v1/trip-chats/${encodeURIComponent(chatId)}`, init);
  return mapFullCurrentTripChat(chat);
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

export async function confirmTripChatUnscheduledPlace(input: {
  chatId: string;
  expectedRevision: number;
  place: Pick<
    UnscheduledPlace,
    | "name"
    | "placeId"
    | "candidateId"
    | "sourceRefs"
    | "sourceProvider"
    | "sourceActivity"
    | "notes"
    | "personalNotes"
  >;
  day: number;
  match: {
    placeId?: string | null;
    name: string;
    address?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    rating?: number | null;
    reviewCount?: number | null;
    imageUrl?: string | null;
    placeType?: string | null;
  };
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));
  form.append("name", input.place.name);
  form.append("day", String(input.day));
  if (input.place.placeId) form.append("placeId", input.place.placeId);
  if (input.place.candidateId) form.append("candidateId", input.place.candidateId);
  form.append("selectedName", input.match.name);
  if (input.match.placeId) form.append("selectedPlaceId", input.match.placeId);
  if (input.match.address) form.append("address", input.match.address);
  if (input.match.placeType) form.append("placeType", input.match.placeType);
  if (input.match.latitude != null) form.append("latitude", String(input.match.latitude));
  if (input.match.longitude != null) form.append("longitude", String(input.match.longitude));
  if (input.match.rating != null) form.append("rating", String(input.match.rating));
  if (input.match.reviewCount != null) form.append("reviewCount", String(input.match.reviewCount));
  if (input.match.imageUrl) form.append("imageUrl", input.match.imageUrl);
  for (const sourceRef of input.place.sourceRefs ?? []) {
    form.append("sourceRefs", sourceRef);
  }
  if (input.place.sourceProvider) form.append("sourceProvider", input.place.sourceProvider);
  if (input.place.sourceActivity) form.append("sourceActivity", input.place.sourceActivity);
  if (input.place.notes) {
    if (typeof input.place.notes === "string") {
      form.append("noteText", input.place.notes);
    } else {
      form.append("noteText", input.place.notes.text);
      form.append("noteSourceType", input.place.notes.sourceType);
      if (input.place.notes.sourceUrl) form.append("noteSourceUrl", input.place.notes.sourceUrl);
    }
  }
  if (input.place.personalNotes) form.append("personalNotes", input.place.personalNotes);

  return apiFetch<TripChat>(
    `/v1/trip-chats/${input.chatId}/plan/unscheduled-places/confirm`,
    { method: "POST", body: form },
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

  const chat = await apiFetch<CurrentTripChat>(`/v1/trip-chats/${input.chatId}/plan/items`, {
    method: "POST",
    body: form
  });
  return mapFullCurrentTripChat(chat);
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

  const chat = await apiFetch<CurrentTripChat>(`/v1/trip-chats/${input.chatId}/plan/days/${input.day}/items/${input.itemId}`, {
    method: "PATCH",
    body: form
  });
  return mapFullCurrentTripChat(chat);
}

export async function replaceTripChatItem(input: {
  chatId: string;
  expectedRevision: number;
  day: number;
  itemId: string;
  place: PlaceSuggestion;
}): Promise<TripChat> {
  if (
    !input.place.placeId
    || input.place.latitude == null
    || input.place.longitude == null
  ) {
    throw new Error("Địa điểm mới chưa có định danh hoặc tọa độ hợp lệ.");
  }
  const chat = await apiFetch<CurrentTripChat>(
    `/v1/trip-chats/${encodeURIComponent(input.chatId)}/plan/days/${input.day}/items/${encodeURIComponent(input.itemId)}/replace`,
    {
      method: "POST",
      body: JSON.stringify({
        expectedRevision: input.expectedRevision,
        placeId: input.place.placeId,
        name: input.place.name,
        address: input.place.address,
        placeType: input.place.placeType,
        latitude: input.place.latitude,
        longitude: input.place.longitude,
        durationMinutes: input.place.durationMinutes,
        openingHours: input.place.openingHours,
        rating: input.place.rating,
        reviewCount: input.place.reviewCount,
        costPerPerson: input.place.costPerPerson,
        imageUrl: input.place.imageUrl,
      }),
    },
  );
  return mapFullCurrentTripChat(chat);
}

export async function updateTripChatItemPersonalNotes(input: {
  chatId: string;
  expectedRevision: number;
  day: number;
  itemId: string;
  personalNotes?: string | null;
}): Promise<TripChat> {
  const chat = await apiFetch<CurrentTripChat>(
    `/v1/trip-chats/${encodeURIComponent(input.chatId)}/plan/days/${input.day}/items/${encodeURIComponent(input.itemId)}/personal-notes`,
    {
      method: "PATCH",
      body: JSON.stringify({
        expectedRevision: input.expectedRevision,
        personalNotes: input.personalNotes ?? null,
      }),
    },
  );
  return mapFullCurrentTripChat(chat);
}

export async function updateTripChatAccommodation(input: {
  chatId: string;
  expectedRevision: number;
  accommodation: {
    placeId?: string | null;
    name?: string;
    address?: string | null;
    latitude?: number | null;
    longitude?: number | null;
    personalNotes?: string | null;
  };
}): Promise<TripChat> {
  const chat = await apiFetch<CurrentTripChat>(
    `/v1/trip-chats/${encodeURIComponent(input.chatId)}/plan/accommodation`,
    {
      method: "PATCH",
      body: JSON.stringify({
        expectedRevision: input.expectedRevision,
        ...input.accommodation,
      }),
    },
  );
  return mapFullCurrentTripChat(chat);
}

export async function removeTripChatAccommodation(input: {
  chatId: string;
  expectedRevision: number;
}): Promise<TripChat> {
  const chat = await apiFetch<CurrentTripChat>(
    `/v1/trip-chats/${encodeURIComponent(input.chatId)}/plan/accommodation?expectedRevision=${input.expectedRevision}`,
    { method: "DELETE" },
  );
  return mapFullCurrentTripChat(chat);
}

export async function removeTripChatItem(input: {
  chatId: string;
  expectedRevision: number;
  day: number;
  itemId: string;
}): Promise<TripChat> {
  const form = new FormData();
  form.append("expectedRevision", String(input.expectedRevision));

  const chat = await apiFetch<CurrentTripChat>(`/v1/trip-chats/${input.chatId}/plan/days/${input.day}/items/${input.itemId}`, {
    method: "DELETE",
    body: form
  });
  return mapFullCurrentTripChat(chat);
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

  return apiFetch<TripChat>(`/v1/trip-chats/${input.chatId}/plan/unscheduled-places`, {
    method: "DELETE",
    body: form
  });
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

  const chat = await apiFetch<CurrentTripChat>(`/v1/trip-chats/${input.chatId}/plan/days/${input.day}/items/reorder`, {
    method: "PUT",
    body: form
  });
  return mapFullCurrentTripChat(chat);
}

export async function selectTripChatTransportOption(input: {
  chatId: string;
  expectedRevision: number;
  day: number;
  legIndex: number;
  option: TransportOption;
}): Promise<TripChat> {
  const chat = await apiFetch<CurrentTripChat>(
    `/v1/trip-chats/${encodeURIComponent(input.chatId)}/plan/days/${input.day}/transport-legs/${input.legIndex}/selection`,
    {
      method: "PUT",
      body: JSON.stringify({
        expectedRevision: input.expectedRevision,
        mode: input.option.mode,
        source: input.option.source,
        distanceMeters: Math.round(input.option.distanceMeters),
        estimatedDurationMinutes: Math.round(
          input.option.estimatedDurationMinutes
        ),
        geometryCoordinates: input.option.geometryCoordinates,
        verified: input.option.verified,
        estimatedCostPerPerson: input.option.estimatedCostPerPerson,
        currency: input.option.currency,
        fetchedAt: input.option.fetchedAt,
        details: input.option.details,
      }),
    }
  );
  return mapFullCurrentTripChat(chat);
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
