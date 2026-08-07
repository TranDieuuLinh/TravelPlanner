import assert from "node:assert/strict";
import test from "node:test";

import { guestConversationShortcut } from "./conversation-shortcuts.ts";

test("guest greetings stay in conversation instead of starting Planner", () => {
  const result = guestConversationShortcut("  Xin chào!  ");

  assert.equal(result?.intent, "travel_advice");
  assert.match(result?.response ?? "", /Chào bạn/);
});

test("guest capability questions stay in conversation", () => {
  assert.equal(
    guestConversationShortcut("Bạn có thể giúp gì cho tôi?")?.intent,
    "travel_advice",
  );
});

test("guest origin questions stay in conversation", () => {
  const result = guestConversationShortcut("Bạn đến từ đâu?");

  assert.equal(result?.intent, "travel_advice");
  assert.match(result?.response ?? "", /không có quê quán/);
});

test("planning prompts are not swallowed by the guest shortcut", () => {
  assert.equal(guestConversationShortcut("Xin chào, lên plan Đà Nẵng 3 ngày"), null);
  assert.equal(guestConversationShortcut("Tôi muốn đi Hà Nội"), null);
  assert.equal(guestConversationShortcut("https://example.com/video"), null);
});
