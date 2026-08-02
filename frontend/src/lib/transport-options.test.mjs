import assert from "node:assert/strict";
import test from "node:test";

import { isAvailableTransportOption } from "./transport-options.ts";

const route = {
  mode: "public_transit",
  source: "opentripplanner_transit",
  verified: true,
  geometryCoordinates: [[21.03059, 105.84431], [21.043173, 105.839379]]
};

test("shows verified OpenTripPlanner transit", () => {
  assert.equal(isAvailableTransportOption(route), true);
});

test("hides unverified current or geometry-free transit", () => {
  assert.equal(isAvailableTransportOption({ ...route, verified: false }), false);
  assert.equal(isAvailableTransportOption({ ...route, geometryCoordinates: [] }), false);
});

test("shows shifted-development OpenTripPlanner routes with geometry", () => {
  assert.equal(isAvailableTransportOption({
    ...route,
    verified: false,
    details: { scheduleStatus: "development_shifted_2018" }
  }), true);
});

test("rejects transit from unknown providers", () => {
  assert.equal(isAvailableTransportOption({
    ...route,
    source: "unknown_transit_provider"
  }), false);
});
