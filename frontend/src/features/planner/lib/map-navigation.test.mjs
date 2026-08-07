import assert from "node:assert/strict";
import test from "node:test";

import {
  coordinateBearing,
  routeForwardBearing
} from "./map-navigation.ts";

test("calculates the cardinal camera bearings", () => {
  assert.ok(Math.abs(coordinateBearing([0, 0], [1, 0]) - 0) < 0.001);
  assert.ok(Math.abs(coordinateBearing([0, 0], [0, 1]) - 90) < 0.001);
  assert.ok(Math.abs(coordinateBearing([0, 0], [-1, 0]) - 180) < 0.001);
  assert.ok(Math.abs(coordinateBearing([0, 0], [0, -1]) - 270) < 0.001);
});

test("uses the route direction nearest the current position", () => {
  const route = [
    [21.0285, 105.8540],
    [21.0285, 105.8541],
    [21.0285, 105.8550]
  ];

  const bearing = routeForwardBearing([21.02851, 105.85408], route);
  assert.ok(bearing != null && Math.abs(bearing - 90) < 0.1);
});

test("skips tiny route segments and returns null without a forward segment", () => {
  const route = [
    [21.0285, 105.8540],
    [21.02850001, 105.85400001],
    [21.0295, 105.8540]
  ];

  const bearing = routeForwardBearing([21.0285, 105.8540], route);
  assert.ok(bearing != null && (bearing < 0.1 || bearing > 359.9));
  assert.equal(routeForwardBearing([21.0295, 105.8540], route), null);
});
