import assert from "node:assert/strict";
import test from "node:test";

import { rebaseItineraryItemOrder } from "./itinerary-order.ts";

test("reapplies a dragged order to the latest itinerary", () => {
  assert.deepEqual(
    rebaseItineraryItemOrder(["a", "b", "c"], ["b", "a", "c"]),
    ["b", "a", "c"]
  );
});

test("keeps concurrently added items in their latest slots", () => {
  assert.deepEqual(
    rebaseItineraryItemOrder(["a", "new", "b", "c"], ["b", "a", "c"]),
    ["b", "new", "a", "c"]
  );
});

test("ignores concurrently removed and duplicate requested items", () => {
  assert.deepEqual(
    rebaseItineraryItemOrder(["new", "b", "c"], ["b", "a", "b", "c"]),
    ["new", "b", "c"]
  );
});
