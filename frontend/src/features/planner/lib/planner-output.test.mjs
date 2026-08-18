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
    people: 2,
    accommodation: {
      placeId: "hotel-old-quarter",
      name: "Khách sạn Phố Cổ",
      coordinates: { latitude: 21.035, longitude: 105.852 },
      address: "Hoàn Kiếm, Hà Nội",
      rating: 4.5,
      reviewCount: 320,
      personalNotes: "Nhận phòng sau 14h",
      pricePerNight: { cost: 800_000, currency: "VND" },
    },
    accommodationNights: 1,
    days: [{
      day: 1,
      date: "2026-08-15",
      stops: [
        {
          itemId: "planner:1:place-ho-guom",
          placeId: "place-ho-guom",
          name: "Hồ Hoàn Kiếm",
          kind: "place",
          priority: "special_experience",
          startMinute: 480,
          endMinute: 540,
          durationMinutes: 60,
          coordinates: { latitude: 21.0285, longitude: 105.8542 },
          tags: ["culture"],
          imageUrls: ["https://example.test/ho-guom.jpg"],
          rating: 4.7,
          reviewCount: 1234,
          openingHours: {
            "1": [{ startMinute: 480, endMinute: 1020 }],
          },
          notes: {
            text: "Nên đến trước 8 giờ",
            sourceType: "url",
            sourceUrl: "https://example.test/video",
          },
          personalNotes: "Nhớ mang ô",
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
      legs: [
        {
          fromPlaceId: "hotel-old-quarter",
          toPlaceId: "place-ho-guom",
          durationMinutes: 8,
          distanceMeters: 700,
          encodedPolyline: encodePolyline([[21.035, 105.852], [21.0285, 105.8542]]),
          provider: "valhalla",
          geometryAvailable: true,
          costPerPerson: 35_000,
        },
        {
          fromPlaceId: "place-ho-guom",
          toPlaceId: "restaurant-pho",
          durationMinutes: 15,
          distanceMeters: 1200,
          encodedPolyline: encodePolyline([[21.0285, 105.8542], [21.034, 105.848]]),
          provider: "valhalla",
          geometryAvailable: true,
          costPerPerson: 30_000,
          selectedTransport: {
            mode: "public_transit",
            distanceMeters: 1200,
            estimatedDurationMinutes: 18,
            geometryCoordinates: [[21.0285, 105.8542], [21.034, 105.848]],
            source: "opentripplanner_transit",
            verified: true,
            details: { lines: ["31"] },
          },
        },
        {
          fromPlaceId: "restaurant-pho",
          toPlaceId: "hotel-old-quarter",
          durationMinutes: 10,
          distanceMeters: 900,
          encodedPolyline: encodePolyline([[21.034, 105.848], [21.035, 105.852]]),
          provider: "valhalla",
          geometryAvailable: true,
          costPerPerson: 25_000,
        },
      ],
      activityMinutes: 120,
      travelMinutes: 15,
      costPerPerson: 60_000,
      costBreakdown: {
        accommodation: 800_000,
        food: 60_000,
        localTransport: 90_000,
        activities: 0,
        misc: 0,
        total: 950_000,
        currency: "VND",
      },
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
  assert.equal(plan.travelerCount, 2);
  assert.equal(plan.days[0].items.length, 2);
  assert.equal(plan.days[0].items[1].timelineCategory, "food");
  assert.equal(plan.days[0].items[1].ontologyType, "Restaurant");
  assert.deepEqual(plan.days[0].items[0].imageUrls, [
    "https://example.test/ho-guom.jpg",
  ]);
  assert.equal(plan.days[0].items[0].rating, 4.7);
  assert.equal(plan.days[0].items[0].reviewCount, 1234);
  assert.equal(plan.days[0].items[0].durationMinutes, 60);
  assert.equal(plan.days[0].items[1].costPerPerson, 60_000);
  assert.equal(plan.days[0].costBreakdown.localTransport, 90_000);
  assert.equal(plan.days[0].items[0].itemId, "planner:1:place-ho-guom");
  assert.equal(plan.days[0].items[0].notes.sourceType, "url");
  assert.deepEqual(plan.days[0].items[0].sourceRefs, [
    "https://example.test/video",
  ]);
  assert.equal(plan.days[0].items[0].personalNotes, "Nhớ mang ô");
  assert.deepEqual(plan.days[0].items[0].openingHours, [{
    dayOfWeek: 6,
    is24Hours: false,
    rawTimeSlots: "08:00–17:00",
  }]);
  assert.equal(plan.days[0].transportLegs[0].fromPlace, "Khách sạn Phố Cổ");
  assert.equal(plan.days[0].transportLegs[2].toPlace, "Khách sạn Phố Cổ");
  assert.equal(plan.days[0].transportLegs[0].mode, "walk");
  assert.equal(plan.days[0].transportLegs[0].estimatedDurationMinutes, 9);
  assert.equal(plan.days[0].transportLegs[0].verified, false);
  assert.equal(plan.days[0].transportLegs[0].alternatives[0].mode, "car");
  assert.equal(plan.days[0].transportLegs[0].alternatives[0].verified, true);
  assert.equal(plan.days[0].transportLegs[0].estimatedCostPerPerson, 0);
  assert.equal(plan.days[0].transportLegs[0].alternatives[0].estimatedCostPerPerson, 35_000);
  assert.equal(plan.days[0].transportLegs[0].alternatives[0].currency, "VND");
  assert.equal(plan.days[0].transportLegs[1].mode, "public_transit");
  assert.deepEqual(plan.days[0].transportLegs[1].details.lines, ["31"]);
  assert.deepEqual(plan.days[0].transportLegs[0].geometryCoordinates[0], [21.035, 105.852]);
  assert.deepEqual(plan.accommodation, {
    placeId: "hotel-old-quarter",
    name: "Khách sạn Phố Cổ",
    address: "Hoàn Kiếm, Hà Nội",
    latitude: 21.035,
    longitude: 105.852,
    rating: 4.5,
    reviewCount: 320,
    pricePerNight: 800_000,
    currency: "VND",
    nights: 1,
    personalNotes: "Nhận phòng sau 14h",
  });
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

test("maps entertainment stops without treating them as TravelPlace", () => {
  const plan = plannerOutputToTravelPlan({
    destination: "Hà Nội",
    timezone: "Asia/Ho_Chi_Minh",
    days: [{
      day: 1,
      date: "2026-08-15",
      stops: [{
        placeId: "entertainment-show",
        name: "Water Puppet Show",
        kind: "entertainment",
        priority: "special_experience",
        startMinute: 1140,
        endMinute: 1200,
        durationMinutes: 60,
        coordinates: { latitude: 21.03, longitude: 105.85 },
        costPerPerson: 100_000,
      }],
      legs: [],
      activityMinutes: 60,
      travelMinutes: 0,
      costPerPerson: 100_000,
    }],
    totalCostPerPerson: 100_000,
    currency: "VND",
    solver: {},
    unscheduled: [],
    discardedOptionalCount: 0,
    warnings: [],
    phaseTimingsMs: {},
  });

  assert.equal(plan.days[0].items[0].placeType, "entertainment");
  assert.equal(plan.days[0].items[0].timelineCategory, "activity");
  assert.equal(plan.days[0].items[0].ontologyType, "Entertainment");
});
