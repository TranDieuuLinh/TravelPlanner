import assert from "node:assert/strict";
import test from "node:test";

import { plannerBudgetBreakdown } from "./planner-budget.ts";

test("combines daily costs into the four user-facing budget groups", () => {
  const result = plannerBudgetBreakdown({
    id: "plan-1",
    title: "Hà Nội",
    destination: "Hà Nội",
    kind: "main",
    days: [{
      day: 1,
      items: [],
      transportLegs: [],
      costBreakdown: {
        accommodation: 400_000,
        food: 180_000,
        localTransport: 90_000,
        activities: 120_000,
        misc: 10_000,
        total: 800_000,
        currency: "VND",
      },
    }],
    budget: { amountPerPerson: null, currency: "VND", source: "estimated_daily_cost" },
  });

  assert.equal(result.travelPlaces, 130_000);
  assert.equal(result.food, 180_000);
  assert.equal(result.accommodation, 400_000);
  assert.equal(result.transportation, 90_000);
  assert.equal(result.perPersonTotal, 800_000);
});

test("falls back to item, hotel, and daily transport prices for older plans", () => {
  const result = plannerBudgetBreakdown({
    id: "legacy-plan",
    title: "Hà Nội",
    destination: "Hà Nội",
    kind: "main",
    days: [{
      day: 1,
      items: [{ name: "Bảo tàng", timeWindow: "", placeType: "activity", source: "test", sourceRefs: [], costPerPerson: 50_000 }],
      transportLegs: [],
    }],
    accommodation: {
      placeId: "hotel",
      name: "Khách sạn",
      latitude: 0,
      longitude: 0,
      pricePerNight: 600_000,
      currency: "VND",
      nights: 2,
    },
    budget: {
      amountPerPerson: null,
      currency: "VND",
      source: "estimated_daily_cost",
      dailyEstimate: { accommodation: 0, food: 0, localTransport: 100_000, activities: 0, total: 100_000 },
    },
  });

  assert.deepEqual(
    [result.travelPlaces, result.food, result.accommodation, result.transportation, result.perPersonTotal],
    [50_000, 0, 1_200_000, 100_000, 1_350_000],
  );
});
