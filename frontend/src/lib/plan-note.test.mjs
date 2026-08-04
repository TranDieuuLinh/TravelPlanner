import assert from "node:assert/strict";
import test from "node:test";

import { formatPlanNote } from "./plan-note.ts";

test("translates known itinerary notes into Vietnamese", () => {
  assert.equal(formatPlanNote("withdraw money"), "Rút tiền");
  assert.equal(
    formatPlanNote("Eat dessert and wait for sightseeing bus."),
    "Ăn món tráng miệng và chờ xe buýt tham quan"
  );
});

test("hides missing and NaN-like note values", () => {
  for (const value of [null, undefined, Number.NaN, "", "  ", "NaN", " null ", "N/A"]) {
    assert.equal(formatPlanNote(value), null);
  }
});

test("preserves valid notes that do not need a compatibility translation", () => {
  assert.equal(formatPlanNote("Thử món địa phương"), "Thử món địa phương");
});
