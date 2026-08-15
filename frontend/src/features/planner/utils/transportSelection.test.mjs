import assert from "node:assert/strict";
import test from "node:test";

import { accommodationRoutePositions } from "./accommodationRoute.ts";

const item = (itemId, name) => ({ itemId, name });
const leg = (fromItemId, toItemId, fromPlace, toPlace) => ({
  fromItemId,
  toItemId,
  fromPlace,
  toPlace,
});

test("shows accommodation only at positions connected to the day's route", () => {
  const day = {
    day: 1,
    items: [item("food", "Quán ăn"), item("museum", "Bảo tàng")],
    transportLegs: [
      leg(null, "food", "Star Hotel", "Quán ăn"),
      leg("food", "museum", "Quán ăn", "Bảo tàng"),
    ],
  };

  assert.deepEqual(accommodationRoutePositions(day, "Star Hotel"), {
    start: true,
    end: false,
  });
});

test("does not show accommodation when it is absent from the day's route", () => {
  const day = {
    day: 1,
    items: [item("food", "Quán ăn"), item("museum", "Bảo tàng")],
    transportLegs: [leg("food", "museum", "Quán ăn", "Bảo tàng")],
  };

  assert.deepEqual(accommodationRoutePositions(day, "Star Hotel"), {
    start: false,
    end: false,
  });
});

test("detects an accommodation return after the final stop", () => {
  const day = {
    day: 2,
    items: [item("museum", "Bảo tàng")],
    transportLegs: [leg("museum", null, "Bảo tàng", "Star Hotel")],
  };

  assert.deepEqual(accommodationRoutePositions(day, "Star Hotel"), {
    start: false,
    end: true,
  });
});
