import assert from "node:assert/strict";
import test from "node:test";

import { shouldApplyBackgroundChatResult } from "./planner-chat-navigation.ts";

test("applies a completed planning result while its chat is still open", () => {
  assert.equal(shouldApplyBackgroundChatResult("chat-a", "chat-a"), true);
});

test("does not pull the user back after they switch chats or open a new chat", () => {
  assert.equal(shouldApplyBackgroundChatResult("chat-b", "chat-a"), false);
  assert.equal(shouldApplyBackgroundChatResult(null, "chat-a"), false);
});
