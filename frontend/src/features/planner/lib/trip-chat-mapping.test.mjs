import assert from "node:assert/strict";
import test from "node:test";

import {
  mapCurrentTripChat,
  mapCurrentTripChatSummary,
} from "./trip-chat-mapping.ts";
import { plannerOutputToTravelPlan } from "./planner-output.ts";

test("maps a list summary without pretending it contains a full planner output", () => {
  const summary = mapCurrentTripChatSummary({
    id: "chat-1",
    title: "Hà Nội",
    revision: 2,
    hasItinerary: true,
    createdAt: "2026-08-14T00:00:00Z",
    updatedAt: "2026-08-14T01:00:00Z",
  });

  assert.equal(summary.hasPlan, true);
  assert.equal(summary.destination, null);
});

test("maps the full planner snapshot received after sending a message", () => {
  const chat = mapCurrentTripChat({
    id: "chat-1",
    title: "Hà Nội",
    threadId: "thread-1",
    revision: 2,
    hasItinerary: true,
    createdAt: "2026-08-14T00:00:00Z",
    updatedAt: "2026-08-14T01:00:00Z",
    currentPlannerOutput: {
      destination: "Hà Nội",
      timezone: "Asia/Ho_Chi_Minh",
      days: [{
        day: 1,
        date: "2026-08-15",
        stops: [{
          placeId: "place-1",
          name: "Hồ Hoàn Kiếm",
          kind: "place",
          priority: "special_experience",
          startMinute: 480,
          endMinute: 540,
          durationMinutes: 60,
          coordinates: { latitude: 21.0285, longitude: 105.8542 },
          costPerPerson: 0,
        }],
        legs: [],
        activityMinutes: 60,
        travelMinutes: 0,
        costPerPerson: 0,
        costBreakdown: {
          accommodation: 0,
          food: 0,
          localTransport: 0,
          activities: 0,
          misc: 0,
          total: 0,
          currency: "VND",
        },
      }],
      totalCostPerPerson: 0,
      currency: "VND",
      solver: {},
      unscheduled: [],
      discardedOptionalCount: 0,
      warnings: [],
      phaseTimingsMs: {},
    },
    messages: [],
  }, plannerOutputToTravelPlan);

  assert.equal(chat.hasPlan, true);
  assert.equal(chat.currentPlan.days.length, 1);
  assert.equal(chat.currentPlan.days[0].items[0].name, "Hồ Hoàn Kiếm");
});
