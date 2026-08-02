import assert from "node:assert/strict";
import test from "node:test";

import { dayHasPlace, visiblePlanDays } from "./visible-plan-days.ts";

test("removes days with no itinerary items", () => {
  const days = [
    { day: 1, items: [{ placeType: "attraction", timelineCategory: "activity" }] },
    { day: 2, items: [] }
  ];

  assert.deepEqual(visiblePlanDays(days).map((day) => day.day), [1]);
});

test("removes days containing only breaks or free time", () => {
  assert.equal(dayHasPlace({
    items: [
      { placeType: "break", timelineCategory: "break" },
      { placeType: "free_time" }
    ]
  }), false);
});

test("keeps food and manually added place items", () => {
  assert.equal(dayHasPlace({
    items: [{ placeType: "restaurant", timelineCategory: "food" }]
  }), true);
  assert.equal(dayHasPlace({
    items: [{ placeType: "attraction" }]
  }), true);
});
