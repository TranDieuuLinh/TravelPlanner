import assert from "node:assert/strict";
import test from "node:test";

import { plannerOutputToTravelPlan } from "./planner-output.ts";

function encodePolyline(points) {
  let previousLatitude = 0;
  let previousLongitude = 0;
  const encode = (delta) => {
    let value = delta < 0 ? ~(delta << 1) : delta << 1;
    let result = "";
    while (value >= 0x20) {
      result += String.fromCharCode((0x20 | (value & 0x1f)) + 63);
      value >>= 5;
    }
    return result + String.fromCharCode(value + 63);
  };
  return points.map(([latitude, longitude]) => {
    const nextLatitude = Math.round(latitude * 1e6);
    const nextLongitude = Math.round(longitude * 1e6);
    const value = encode(nextLatitude - previousLatitude)
      + encode(nextLongitude - previousLongitude);
    previousLatitude = nextLatitude;
    previousLongitude = nextLongitude;
    return value;
  }).join("");
}

test("maps planner stops, route legs, and unscheduled places to TravelPlan", () => {
  const output = {
    destination: "Hà Nội",
    timezone: "Asia/Ho_Chi_Minh",
    days: [{
      day: 1,
      date: "2026-08-15",
      stops: [
        {
          placeId: "place-ho-guom",
          name: "Hồ Hoàn Kiếm",
          kind: "place",
          priority: "special_experience",
          startMinute: 480,
          endMinute: 540,
          durationMinutes: 60,
          coordinates: { latitude: 21.0285, longitude: 105.8542 },
          tags: ["culture"],
          costPerPerson: 0,
        },
        {
          placeId: "restaurant-pho",
          name: "Phở Gia Truyền",
          kind: "food",
          priority: "special_experience",
          startMinute: 555,
          endMinute: 615,
          durationMinutes: 60,
          mealType: "breakfast",
          coordinates: { latitude: 21.034, longitude: 105.848 },
          costPerPerson: 60_000,
        },
      ],
      legs: [{
        fromPlaceId: "place-ho-guom",
        toPlaceId: "restaurant-pho",
        durationMinutes: 15,
        distanceMeters: 1200,
        encodedPolyline: encodePolyline([[21.0285, 105.8542], [21.034, 105.848]]),
        provider: "valhalla",
        geometryAvailable: true,
      }],
      activityMinutes: 120,
      travelMinutes: 15,
      costPerPerson: 60_000,
    }],
    totalCostPerPerson: 60_000,
    currency: "VND",
    solver: {},
    unscheduled: [{
      placeId: "place-missing",
      name: "Điểm chưa xếp",
      priority: "user_input",
      reasonCode: "not_selected_by_optimizer",
      message: "Không đủ thời gian.",
    }],
    discardedOptionalCount: 0,
    warnings: ["warning"],
    phaseTimingsMs: {},
  };

  const plan = plannerOutputToTravelPlan(output, { id: "plan-1" });

  assert.equal(plan.id, "plan-1");
  assert.equal(plan.days[0].items.length, 2);
  assert.equal(plan.days[0].items[1].timelineCategory, "food");
  assert.equal(plan.days[0].items[1].ontologyType, "Restaurant");
  assert.equal(plan.days[0].transportLegs[0].fromPlace, "Hồ Hoàn Kiếm");
  assert.equal(plan.days[0].transportLegs[0].verified, true);
  assert.deepEqual(plan.days[0].transportLegs[0].geometryCoordinates[0], [21.0285, 105.8542]);
  assert.equal(plan.unscheduledPlaces[0].reasonCode, "not_selected_by_optimizer");
});

test("rejects planner outputs without a scheduled stop on every day", () => {
  const base = {
    destination: "Hà Nội",
    timezone: "Asia/Ho_Chi_Minh",
    totalCostPerPerson: 0,
    currency: "VND",
    solver: {},
    unscheduled: [],
    discardedOptionalCount: 0,
    warnings: [],
    phaseTimingsMs: {},
  };

  assert.equal(plannerOutputToTravelPlan({ ...base, days: [] }), null);
  assert.equal(
    plannerOutputToTravelPlan({
      ...base,
      days: [{
        day: 1,
        date: "2026-08-15",
        stops: [],
        legs: [],
        activityMinutes: 0,
        travelMinutes: 0,
        costPerPerson: 0,
      }],
    }),
    null,
  );
});
