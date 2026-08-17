import type { TravelPlan } from "@/features/planner/api/plans";

export type PlannerBudgetBreakdown = {
  travelPlaces: number;
  food: number;
  accommodation: number;
  transportation: number;
  perPersonTotal: number;
  currency: string;
};

type PlannerBudgetOptions = {
  travelerCount?: number | null;
};

export function formatPlannerMoney(
  amount: number,
  currency: string,
): string {
  try {
    return new Intl.NumberFormat("vi-VN", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${amount.toLocaleString("vi-VN")} ${currency}`;
  }
}

export function plannerBudgetBreakdown(
  plan: TravelPlan,
  options: PlannerBudgetOptions = {},
): PlannerBudgetBreakdown {
  const currency =
    plan.budget?.currency ?? plan.accommodation?.currency ?? "VND";
  const daysWithBreakdown = plan.days.filter((day) => day.costBreakdown);

  const fromDailyBreakdown = daysWithBreakdown.reduce(
    (total, day) => {
      const breakdown = day.costBreakdown!;
      total.travelPlaces += breakdown.activities + breakdown.misc;
      total.food += breakdown.food;
      total.accommodation += breakdown.accommodation;
      total.transportation += breakdown.localTransport;
      return total;
    },
    { travelPlaces: 0, food: 0, accommodation: 0, transportation: 0 },
  );

  const legacyItemCosts = plan.days.reduce(
    (total, day) => {
      for (const item of day.items) {
        const cost = Math.max(0, item.costPerPerson ?? 0);
        if (["food", "restaurant", "cafe"].includes(item.placeType)) {
          total.food += cost;
        } else {
          total.travelPlaces += cost;
        }
      }
      return total;
    },
    { travelPlaces: 0, food: 0 },
  );
  const travelPlaces = daysWithBreakdown.length
    ? fromDailyBreakdown.travelPlaces
    : legacyItemCosts.travelPlaces;
  const food = daysWithBreakdown.length
    ? fromDailyBreakdown.food
    : legacyItemCosts.food;
  const travelerCount = Math.max(1, options.travelerCount ?? 1);
  const inferredRoomCount = Math.ceil(travelerCount / 2);
  const accommodation = daysWithBreakdown.length
    ? fromDailyBreakdown.accommodation
    : plan.accommodation
      ? Math.max(
          0,
          plan.accommodation.pricePerNight
            * plan.accommodation.nights
            * inferredRoomCount
            / travelerCount,
        )
      : 0;
  const transportation = daysWithBreakdown.length
    ? fromDailyBreakdown.transportation
    : Math.max(
        0,
        (plan.budget?.dailyEstimate?.localTransport ?? 0) * plan.days.length,
      );

  return {
    travelPlaces,
    food,
    accommodation,
    transportation,
    // Daily breakdown values are already per-person. For legacy plans, room
    // prices are converted using the actual party size and a two-person room.
    perPersonTotal: travelPlaces + food + accommodation + transportation,
    currency,
  };
}
