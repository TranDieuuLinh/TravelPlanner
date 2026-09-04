import assert from "node:assert/strict";
import test from "node:test";

import {
  diffDayRoutes,
  mergeDayRouteLegs,
  withDayTransportLegs,
} from "./incremental-day-routes.ts";

const item = (itemId, latitude, longitude, name = itemId.toUpperCase()) => ({
  itemId,
  placeId: itemId,
  name,
  latitude,
  longitude,
});

const leg = (from, to, extra = {}) => ({
  mode: "car",
  source: "valhalla",
  verified: true,
  distanceMeters: 1000,
  estimatedDurationMinutes: 5,
  geometryCoordinates: [[0, 0], [1, 1]],
  fromItemId: from.itemId,
  toItemId: to.itemId,
  fromPlace: from.name,
  toPlace: to.name,
  ...extra,
});

function plan(items, legs) {
  return {
    id: "plan-1",
    title: "Hà Nội",
    destination: "Hà Nội",
    kind: "main",
    days: [{ day: 1, items, transportLegs: legs }],
  };
}

test("adding a place recalculates only the two edges around its insertion", () => {
  const a = item("a", 21.01, 105.81);
  const b = item("b", 21.02, 105.82);
  const c = item("c", 21.03, 105.83);
  const x = item("x", 21.015, 105.815);
  const previous = plan([a, b, c], [leg(a, b), leg(b, c, { selectedTransport: { mode: "walk" } })]);
  const next = plan([a, x, b, c], previous.days[0].transportLegs);

  const diff = diffDayRoutes(previous, next, 1);

  assert.deepEqual(
    diff.affectedEdges.map((edge) => [edge.from.itemId, edge.to.itemId]),
    [["a", "x"], ["x", "b"]],
  );
  assert.equal(diff.reusableLegsByEdgeKey.size, 1);
  assert.deepEqual(
    mergeDayRouteLegs(diff, new Map())[0].selectedTransport,
    { mode: "walk" },
  );
});

test("deleting a place keeps later route legs and creates one bridge edge", () => {
  const a = item("a", 21.01, 105.81);
  const b = item("b", 21.02, 105.82);
  const c = item("c", 21.03, 105.83);
  const d = item("d", 21.04, 105.84);
  const previous = plan([a, b, c, d], [leg(a, b), leg(b, c), leg(c, d)]);
  const next = plan([a, c, d], previous.days[0].transportLegs);

  const diff = diffDayRoutes(previous, next, 1);

  assert.deepEqual(
    diff.affectedEdges.map((edge) => [edge.from.itemId, edge.to.itemId]),
    [["a", "c"]],
  );
  assert.deepEqual(
    mergeDayRouteLegs(diff, new Map()).map((route) => [route.fromItemId, route.toItemId]),
    [["c", "d"]],
  );
});

test("dragging one place preserves every adjacency that did not change", () => {
  const a = item("a", 21.01, 105.81);
  const b = item("b", 21.02, 105.82);
  const c = item("c", 21.03, 105.83);
  const d = item("d", 21.04, 105.84);
  const previous = plan([a, b, c, d], [leg(a, b), leg(b, c), leg(c, d)]);
  const next = plan([a, b, d, c], previous.days[0].transportLegs);

  const diff = diffDayRoutes(previous, next, 1);

  assert.deepEqual(
    diff.affectedEdges.map((edge) => [edge.from.itemId, edge.to.itemId]),
    [["b", "d"], ["d", "c"]],
  );
  assert.deepEqual(
    mergeDayRouteLegs(diff, new Map()).map((route) => [route.fromItemId, route.toItemId]),
    [["a", "b"]],
  );
});

test("editing coordinates invalidates only the adjacent edges", () => {
  const a = item("a", 21.01, 105.81);
  const b = item("b", 21.02, 105.82);
  const c = item("c", 21.03, 105.83);
  const previous = plan([a, b, c], [leg(a, b), leg(b, c)]);
  const movedB = item("b", 21.22, 105.92, "B mới");
  const next = withDayTransportLegs(
    plan([a, movedB, c], previous.days[0].transportLegs),
    1,
    previous.days[0].transportLegs,
  );

  const diff = diffDayRoutes(previous, next, 1);

  assert.deepEqual(
    diff.affectedEdges.map((edge) => [edge.from.itemId, edge.to.itemId]),
    [["a", "b"], ["b", "c"]],
  );
});

test("moving the final place recalculates an existing return to accommodation", () => {
  const hotel = item("hotel", 21.0, 105.8, "Khách sạn");
  const a = item("a", 21.01, 105.81);
  const b = item("b", 21.02, 105.82);
  const c = item("c", 21.03, 105.83);
  const previous = {
    ...plan([a, b, c], [
      leg(hotel, a),
      leg(a, b),
      leg(b, c),
      leg(c, hotel),
    ]),
    accommodation: {
      placeId: hotel.itemId,
      name: hotel.name,
      latitude: hotel.latitude,
      longitude: hotel.longitude,
      pricePerNight: 0,
      currency: "VND",
      nights: 1,
    },
  };
  const next = {
    ...previous,
    days: [{
      ...previous.days[0],
      items: [a, c, b],
    }],
  };

  const diff = diffDayRoutes(previous, next, 1);

  assert.deepEqual(
    diff.affectedEdges.map((edge) => [edge.from.itemId, edge.to.itemId]),
    [["a", "c"], ["c", "b"], ["b", "hotel"]],
  );
  assert.deepEqual(
    mergeDayRouteLegs(diff, new Map()).map((route) => [route.fromItemId, route.toItemId]),
    [["hotel", "a"]],
  );
});
