import assert from "node:assert/strict";
import test from "node:test";

import { estimateGreenSmHanoiFare } from "./green-sm-fare.ts";

test("estimates the buffered GreenSM Hanoi fare for legacy route legs", () => {
  assert.equal(estimateGreenSmHanoiFare(0), 0);
  assert.equal(estimateGreenSmHanoiFare(2_000), 35_075);
  assert.equal(estimateGreenSmHanoiFare(3_600), 62_123);
});
