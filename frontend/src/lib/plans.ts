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

const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

export async function createPlan(input: { destination: string; days: number; interests: string[] }): Promise<TravelPlan> {
  const response = await fetch(`${apiBase}/plans/main`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      destination: input.destination,
      days: input.days,
      budget: "balanced",
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
