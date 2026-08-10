import assert from "node:assert/strict";
import test from "node:test";

import {
  formatItineraryTimeWindow,
  itineraryTimeWindowAriaLabel
} from "./time-window.ts";

test("formats an itinerary clock range for display", () => {
  assert.equal(formatItineraryTimeWindow("8:05-09:30"), "08:05 – 09:30");
});

test("keeps an unknown non-empty window readable", () => {
  assert.equal(formatItineraryTimeWindow("Buổi sáng"), "Buổi sáng");
  assert.equal(formatItineraryTimeWindow("  "), null);
});

test("builds a Vietnamese accessible label", () => {
  assert.equal(
    itineraryTimeWindowAriaLabel("11:30-12:30"),
    "Khung giờ 11:30 đến 12:30"
  );
});
