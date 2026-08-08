import assert from "node:assert/strict";
import test from "node:test";

import { visibleConversationMessages } from "./conversation-messages.ts";

function message(overrides) {
  return {
    id: crypto.randomUUID(),
    role: "assistant",
    content: "Answer",
    attachmentNames: [],
    planRevision: 4,
    createdAt: "2026-08-08T00:00:00Z",
    ...overrides,
  };
}

test("keeps user questions and assistant answers in the Q&A transcript", () => {
  const messages = visibleConversationMessages({
    messages: [
      message({ role: "user", content: "How do I buy a SIM card?" }),
      message({
        content: "Bring your passport to an official mobile carrier store.",
        messageKind: "turn_response",
        contentBlocks: [{ type: "text" }],
      }),
    ],
  });

  assert.deepEqual(
    messages.map(({ role, text }) => ({ role, text })),
    [
      { role: "user", text: "How do I buy a SIM card?" },
      {
        role: "assistant",
        text: "Bring your passport to an official mobile carrier store.",
      },
    ]
  );
});

test("hides typed and structured plan-update notifications", () => {
  const messages = visibleConversationMessages({
    messages: [
      message({ content: "Đã cập nhật lịch trình.", messageKind: "plan_update" }),
      message({
        content: "Moved the place.",
        messageKind: "turn_response",
        contentBlocks: [{ type: "planDiff", affectedDays: [2] }],
      }),
      message({ content: "A real answer", messageKind: "turn_response" }),
    ],
  });

  assert.deepEqual(messages.map((item) => item.text), ["A real answer"]);
});

test("hides operational notifications saved before message kinds existed", () => {
  const messages = visibleConversationMessages({
    messages: [
      message({ content: "Đã chọn Showtime Lotte Center Hanoi cho Lotte Center (bản sửa đổi 3)." }),
      message({ content: "Đã xác minh thêm 2 địa điểm; còn 1 địa điểm cần xem lại (bản sửa đổi 4)." }),
      message({ content: "Bạn nên mua SIM tại cửa hàng chính thức." }),
    ],
  });

  assert.deepEqual(messages.map((item) => item.text), [
    "Bạn nên mua SIM tại cửa hàng chính thức.",
  ]);
});
