import assert from "node:assert/strict";
import test from "node:test";

import { transportLegAfterItem } from "./planner-transport-leg.ts";

const item = (itemId, name) => ({ itemId, name });
const leg = (fromItemId, toItemId, fromPlace, toPlace) => ({
  fromItemId,
  toItemId,
  fromPlace,
  toPlace,
});

test("returns the accommodation transfer after the final itinerary stop", () => {
  const finalStop = item("stop-2", "Nhà hát");
  const accommodationTransfer = leg(
    "stop-2",
    null,
    "Nhà hát",
    "Khách sạn Phố Cổ",
  );
  const day = {
    items: [item("stop-1", "Hồ Hoàn Kiếm"), finalStop],
    transportLegs: [
      leg("stop-1", "stop-2", "Hồ Hoàn Kiếm", "Nhà hát"),
      accommodationTransfer,
    ],
  };

  assert.equal(transportLegAfterItem(day, finalStop, 1), accommodationTransfer);
});

test("does not invent a final transfer when the day has none", () => {
  const finalStop = item("stop-2", "Nhà hát");
  const day = {
    items: [item("stop-1", "Hồ Hoàn Kiếm"), finalStop],
    transportLegs: [
      leg("stop-1", "stop-2", "Hồ Hoàn Kiếm", "Nhà hát"),
    ],
  };

  assert.equal(transportLegAfterItem(day, finalStop, 1), null);
});
