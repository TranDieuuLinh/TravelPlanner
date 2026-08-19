import assert from "node:assert/strict";
import test from "node:test";

import {
  plannerBudgetBreakdown,
  plannerBudgetReference,
} from "./planner-budget.ts";

test("uses the normalized PlaceChecker per-person budget before raw intake", () => {
  const plan = {
    id: "plan-budget",
    title: "Hà Nội",
    destination: "Hà Nội",
    kind: "main",
    days: [],
    budget: {
      amountPerPerson: 5_000_000,
      currency: "VND",
      source: "estimated_daily_cost",
    },
  };

  assert.deepEqual(plannerBudgetReference(plan, 10_000_000), {
    amountPerPerson: 5_000_000,
    source: "estimated_daily_cost",
  });
});

test("falls back to an explicit intake budget for legacy plans", () => {
  const plan = {
    id: "legacy-budget",
    title: "Hà Nội",
    destination: "Hà Nội",
    kind: "main",
    days: [],
  };

  assert.deepEqual(plannerBudgetReference(plan, 3_000_000), {
    amountPerPerson: 3_000_000,
    source: "explicit",
  });
});

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
  }, { travelerCount: 2 });

  assert.deepEqual(
    [result.travelPlaces, result.food, result.accommodation, result.transportation, result.perPersonTotal],
    [50_000, 0, 600_000, 100_000, 750_000],
  );
});

test("uses the already per-person daily room cost instead of the raw room price", () => {
  const result = plannerBudgetBreakdown({
    id: "current-plan",
    title: "Hà Nội",
    destination: "Hà Nội",
    kind: "main",
    days: [{
      day: 1,
      items: [],
      transportLegs: [],
      costBreakdown: {
        accommodation: 300_000,
        food: 0,
        localTransport: 0,
        activities: 0,
        misc: 0,
        total: 300_000,
        currency: "VND",
      },
    }],
    accommodation: {
      placeId: "hotel",
      name: "Khách sạn",
      latitude: 0,
      longitude: 0,
      pricePerNight: 600_000,
      currency: "VND",
      nights: 1,
    },
  }, { travelerCount: 2 });

  assert.equal(result.accommodation, 300_000);
  assert.equal(result.perPersonTotal, 300_000);
});
