import assert from "node:assert/strict";
import test from "node:test";

import {
  resolvePlannerEntryChatId,
  shouldApplyBackgroundChatResult,
} from "./planner-chat-navigation.ts";

test("applies a completed planning result while its chat is still open", () => {
  assert.equal(shouldApplyBackgroundChatResult("chat-a", "chat-a"), true);
});

test("does not pull the user back after they switch chats or open a new chat", () => {
  assert.equal(shouldApplyBackgroundChatResult("chat-b", "chat-a"), false);
  assert.equal(shouldApplyBackgroundChatResult(null, "chat-a"), false);
});

test("opens the requested chat when a deep link points to an existing chat", () => {
  assert.equal(resolvePlannerEntryChatId("chat-b", false, ["chat-a", "chat-b"]), "chat-b");
});

test("starts a new chat when entering Planner without a deep link", () => {
  assert.equal(resolvePlannerEntryChatId(null, false, ["chat-b", "chat-a"]), null);
});

test("keeps a prefilled request as a new chat instead of replacing it with history", () => {
  assert.equal(resolvePlannerEntryChatId("chat-a", true, ["chat-a"]), null);
});

test("does not reopen history when a pending history request finishes on a new chat", () => {
  assert.equal(resolvePlannerEntryChatId(null, false, ["chat-a"]), null);
});
