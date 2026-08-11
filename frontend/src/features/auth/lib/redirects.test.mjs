import assert from "node:assert/strict";
import test from "node:test";

import { defaultRouteForUser, postAuthRoute, safeNextPath } from "./redirects.ts";

test("keeps safe same-origin destinations", () => {
  assert.equal(safeNextPath("/planner?destination=Da%20Nang"), "/planner?destination=Da%20Nang");
  assert.equal(postAuthRoute({ role: "traveler" }, "/explore"), "/explore");
});

test("uses role-aware default destinations", () => {
  assert.equal(defaultRouteForUser({ role: "traveler" }), "/profile");
  assert.equal(defaultRouteForUser({ role: "creator" }), "/creator/listings");
  assert.equal(defaultRouteForUser({ role: "admin" }), "/admin/places");
});

test("rejects open redirects and auth loops", () => {
  assert.equal(safeNextPath("https://evil.example"), null);
  assert.equal(safeNextPath("//evil.example"), null);
  assert.equal(safeNextPath("/login"), null);
  assert.equal(postAuthRoute({ role: "traveler" }, null), "/profile");
});
