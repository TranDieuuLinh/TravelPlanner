export type PlanItem = {
  name: string;
  timeWindow: string;
  placeType: string;
  notes?: string | null;
  latitude?: number | null;
  longitude?: number | null;
};
export type TransportLeg = {
  fromItemId?: string | null;
  toItemId?: string | null;
  fromPlace: string;
  toPlace: string;
  mode: string;
  distanceMeters: number;
  estimatedDurationMinutes: number;
  geometryCoordinates: [number, number][];
  source: string;
  verified: boolean;
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

export type BudgetLevel = "budget" | "medium" | "high";
export type BudgetInputMode = "qualitative" | "exact" | "range" | "unknown";
export type BudgetConfidence = "low" | "medium" | "high";

export type BudgetEnvelope = {
  inputMode: BudgetInputMode;
  minAmount?: number | null;
  targetAmount?: number | null;
  maxAmount?: number | null;
  currency: string;
  isHardCap: boolean;
  confidence: BudgetConfidence;
  calculationBasis?: {
    partySize: number;
    days: number;
    nights: number;
    destination: string;
    priceTier: BudgetLevel;
  } | null;
  notes?: string | null;
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
    budgetLevel: BudgetLevel;
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
  const plan = await createPlanFromExplorer({
    context: explore.explorer,
    intakeId: explore.intakeId,
    userId: explore.userId
  });

  return { explore, plan };
}

export async function getPlanFeatureMap(): Promise<FeatureMapItem[]> {
  return apiFetch<FeatureMapItem[]>("/plans/feature-map");
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
}): Promise<TravelPlan> {
  const selectedPlaces = input.selectedPlaces ?? [];

  return apiFetch<TravelPlan>("/plans/main/from-explorer", {
    method: "POST",
    body: JSON.stringify({
      intent: input.context.intent,
      tripSpec: input.context.tripSpec,
      intakeId: input.intakeId ?? null,
      userId: input.userId ?? null,
      selectedPlaces: selectedPlaces.map((place) => ({
        name: place.name,
        placeId: place.placeId ?? null,
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
  });
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
import { apiFetch } from "@/lib/api";
