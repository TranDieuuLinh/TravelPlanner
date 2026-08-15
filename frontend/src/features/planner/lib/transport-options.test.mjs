import assert from "node:assert/strict";
import test from "node:test";

import {
  isAvailableTransportOption,
  isCarMode,
  isGenericTransportMode,
  isWalkingMode,
  resolveSelectedTransportOption,
  transportOptionSelectionKey,
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

test("recognizes walking and driving mode aliases", () => {
  assert.equal(isWalkingMode("walk"), true);
  assert.equal(isWalkingMode("walking"), true);
  assert.equal(isWalkingMode("pedestrian"), true);
  assert.equal(isCarMode("car"), true);
  assert.equal(isCarMode("driving"), true);
  assert.equal(isCarMode("ride_hailing"), true);
});

const walking = {
  ...route,
  mode: "walk",
  source: "valhalla",
  distanceMeters: 1400
};
const car = {
  ...route,
  mode: "ride_hailing",
  source: "valhalla",
  distanceMeters: 1400
};

test("recommends walking first for a leg under 1.5 km", () => {
  assert.deepEqual(
    visibleTransportOptions([car, walking, route], 1499),
    [walking, car, route]
  );
});

test("starts with car and omits walking at or above 1.5 km", () => {
  assert.deepEqual(visibleTransportOptions([walking, route, car], 1500), [car, route]);
  assert.deepEqual(visibleTransportOptions([walking, route, car], 4500), [car, route]);
});

test("does not expose mixed as a fallback option", () => {
  const mixed = { ...car, mode: "mixed" };
  assert.deepEqual(visibleTransportOptions([mixed, walking], 4500), []);
});

test("selection key distinguishes repeated transit mode variants", () => {
  const route31 = {
    ...route,
    estimatedDurationMinutes: 32,
    distanceMeters: 2900,
    details: {
      lines: ["31"],
      segments: [{
        mode: "BUS",
        line: "31",
        estimatedDurationMinutes: 18,
        distanceMeters: 2100
      }]
    }
  };
  const route14 = {
    ...route31,
    details: {
      lines: ["14"],
      segments: [{
        mode: "BUS",
        line: "14",
        estimatedDurationMinutes: 20,
        distanceMeters: 2200
      }]
    }
  };

  assert.notEqual(
    transportOptionSelectionKey(route31),
    transportOptionSelectionKey(route14)
  );
});

test("keeps the persisted transport choice when temporary selection state resets", () => {
  const selectedTransit = {
    ...route,
    estimatedDurationMinutes: 85,
    distanceMeters: 25_616,
    details: { lines: ["Route_06E_2", "Route_08A_1"] }
  };
  const alternativeCar = {
    ...car,
    estimatedDurationMinutes: 42,
    distanceMeters: 24_900
  };
  const displayedOptions = visibleTransportOptions(
    [selectedTransit, alternativeCar],
    selectedTransit.distanceMeters
  );

  assert.equal(displayedOptions[0], alternativeCar);
  assert.equal(
    resolveSelectedTransportOption(displayedOptions, selectedTransit),
    selectedTransit
  );
});
