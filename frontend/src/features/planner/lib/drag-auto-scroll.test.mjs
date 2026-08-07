import assert from "node:assert/strict";
import test from "node:test";

import { dragAutoScrollVelocity } from "./drag-auto-scroll.ts";

test("scrolls upward near the top edge", () => {
  assert.equal(
    dragAutoScrollVelocity(110, { start: 100, end: 700 }, 100, 20),
    -18
  );
});

test("scrolls downward near the bottom edge", () => {
  assert.equal(
    dragAutoScrollVelocity(690, { start: 100, end: 700 }, 100, 20),
    18
  );
});

test("does not scroll away from either edge", () => {
  assert.equal(
    dragAutoScrollVelocity(400, { start: 100, end: 700 }, 100, 20),
    0
  );
});

test("caps speed when the pointer moves outside the scroll area", () => {
  assert.equal(
    dragAutoScrollVelocity(20, { start: 100, end: 700 }, 100, 20),
    -20
  );
  assert.equal(
    dragAutoScrollVelocity(780, { start: 100, end: 700 }, 100, 20),
    20
  );
});
