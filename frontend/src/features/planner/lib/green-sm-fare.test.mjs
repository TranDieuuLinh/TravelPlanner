import assert from "node:assert/strict";
import test from "node:test";

import {
  estimateGreenSmHanoiFare,
  resolveTransportGroupFare,
} from "./green-sm-fare.ts";

test("estimates the buffered GreenSM Hanoi fare for legacy route legs", () => {
  assert.equal(estimateGreenSmHanoiFare(0), 0);
  assert.equal(estimateGreenSmHanoiFare(2_000), 35_075);
  assert.equal(estimateGreenSmHanoiFare(3_600), 62_123);
});

test("shows a route-level per-person estimate as the whole group fare", () => {
  assert.equal(resolveTransportGroupFare(1_500, 17_538, 2), 35_076);
  assert.equal(resolveTransportGroupFare(1_500, 17_538, 1), 17_538);
});

test("keeps the legacy distance fallback as a whole-vehicle fare", () => {
  assert.equal(resolveTransportGroupFare(2_000, null, 4), 35_075);
});
