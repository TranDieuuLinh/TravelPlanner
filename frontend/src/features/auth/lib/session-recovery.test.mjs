import assert from "node:assert/strict";
import test from "node:test";

import { authLoadFailureAction } from "./session-recovery.ts";

test("keeps the current session on a temporary network failure", () => {
  assert.equal(authLoadFailureAction(0), "retry");
});

test("clears the session only when authentication is rejected", () => {
  assert.equal(authLoadFailureAction(401), "clear-session");
  assert.equal(authLoadFailureAction(403), "clear-session");
});

test("does not hide unexpected API failures", () => {
  assert.equal(authLoadFailureAction(500), "throw");
  assert.equal(authLoadFailureAction(), "throw");
});
