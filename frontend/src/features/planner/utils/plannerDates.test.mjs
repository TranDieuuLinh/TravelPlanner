import test from "node:test";
import assert from "node:assert/strict";
import {
  addTripDays,
  defaultTripEndDate,
  formatPlannerDate,
  tripDaysBetween,
} from "./plannerDates.ts";

test("tính ngày kết thúc và số ngày của chuyến đi", () => {
  assert.equal(addTripDays("2026-08-10", 3), "2026-08-12");
  assert.equal(defaultTripEndDate("2026-08-10", null, 3), "2026-08-12");
  assert.equal(tripDaysBetween("2026-08-10", "2026-08-12"), 3);
});

test("định dạng ngày theo locale tiếng Việt", () => {
  assert.equal(formatPlannerDate("2026-08-10"), "10/08/2026");
  assert.equal(formatPlannerDate("invalid"), "invalid");
});
