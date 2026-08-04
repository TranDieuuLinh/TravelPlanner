import assert from "node:assert/strict";
import test from "node:test";

import {
  isAvailableTransportOption,
  isGenericTransportMode,
  visibleTransportOptions
} from "./transport-options.ts";

const route = {
  mode: "public_transit",
  distanceMeters: 4200,
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

test("hides generic mixed and unknown transport modes", () => {
  assert.equal(isGenericTransportMode("mixed"), true);
  assert.equal(isAvailableTransportOption({ ...route, mode: "mixed" }), false);
  assert.equal(isAvailableTransportOption({ ...route, mode: "unknown" }), false);
});

const walking = {
  ...route,
  mode: "walk",
  source: "valhalla",
  distanceMeters: 2900
};
const car = {
  ...route,
  mode: "ride_hailing",
  source: "valhalla",
  distanceMeters: 2700
};

test("always shows car and also shows walking for a leg under 3 km", () => {
  assert.deepEqual(
    visibleTransportOptions([car, walking, route], 2999),
    [walking, car, route]
  );
});

test("shows car but not walking for a leg at or above 3 km", () => {
  assert.deepEqual(visibleTransportOptions([walking, route, car], 3000), [car, route]);
  assert.deepEqual(visibleTransportOptions([walking, route, car], 4500), [car, route]);
});

test("does not expose mixed as a fallback option", () => {
  const mixed = { ...car, mode: "mixed" };
  assert.deepEqual(visibleTransportOptions([mixed, walking], 4500), []);
});
