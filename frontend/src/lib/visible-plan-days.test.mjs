import assert from "node:assert/strict";
import test from "node:test";

import {
  dayHasPlace,
  visiblePlanDays,
  visiblePlanItems
} from "./visible-plan-days.ts";

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

test("removes days containing only unresolved Finder meal placeholders", () => {
  assert.equal(dayHasPlace({
    items: [
      {
        placeId: null,
        placeType: "meal",
        source: "finder_rule",
        timelineCategory: "food"
      }
    ]
  }), false);
});

test("removes unresolved meal placeholders from otherwise populated days", () => {
  const items = [
    { placeId: "museum", placeType: "attraction", source: "selected_place" },
    { placeId: null, placeType: "meal", source: "finder_rule" }
  ];

  assert.deepEqual(visiblePlanItems(items), [items[0]]);
});

test("keeps food and manually added place items", () => {
  assert.equal(dayHasPlace({
    items: [{ placeType: "restaurant", timelineCategory: "food" }]
  }), true);
  assert.equal(dayHasPlace({
    items: [{ placeType: "attraction" }]
  }), true);
  assert.equal(dayHasPlace({
    items: [{ placeId: null, placeType: "meal", source: "manual" }]
  }), true);
});
