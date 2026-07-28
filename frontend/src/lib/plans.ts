export type PlanItem = { name: string; timeWindow: string; placeType: string; notes?: string | null };
export type PlanDay = { day: number; theme: string; items: PlanItem[] };
export type TravelPlan = {
  id: string;
  title: string;
  destination: string;
  kind: "main" | "backup";
  days: PlanDay[];
  checkReport?: { status: string; summary: string } | null;
};

export type PlaceCategory =
  | "attraction"
  | "food"
  | "cafe"
  | "hotel"
  | "transport"
  | "free_time"
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

export type ExplorePlace = {
  name: string;
  category: PlaceCategory;
  placeId?: string | null;
  address?: string | null;
  source?: string;
  sourceUrl?: string | null;
  confidence?: number;
  priority?: number;
  notes?: string | null;
};

export type ExploreResponse = {
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
  placeCandidates: ExplorePlace[];
  foodPlaces: ExplorePlace[];
  urlReelSignals: Array<{
    url: string;
    platform?: string | null;
    extractedPlaces: string[];
    interests: string[];
    constraints: string[];
    confidence: number;
    notes: string[];
  }>;
  assumptions: string[];
  missingInfoQuestions: string[];
};

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export async function createPlan(input: { destination: string; days: number; interests: string[] }): Promise<TravelPlan> {
  const response = await fetch(`${apiBase}/plans/main`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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

  if (!response.ok) throw new Error("Không thể tạo plan. Hãy kiểm tra backend ở cổng 8000.");
  return response.json() as Promise<TravelPlan>;
}

export async function exploreFullIntake(input: {
  rawRequest: string;
  images: File[];
}): Promise<ExploreResponse> {
  const form = new FormData();
  form.append("rawRequest", input.rawRequest);
  for (const image of input.images) {
    form.append("images", image);
  }

  const response = await fetch(`${apiBase}/plans/explore/full/intake`, {
    method: "POST",
    body: form
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || "Không thể chạy Explorer. Hãy kiểm tra backend ở cổng 8000.");
  }
  return response.json() as Promise<ExploreResponse>;
}
