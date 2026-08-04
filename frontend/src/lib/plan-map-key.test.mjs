import assert from "node:assert/strict";
import test from "node:test";

import { planItemMapKey } from "./plan-map-key.ts";

test("keeps a plan marker identity stable when its itinerary position changes", () => {
  const before = planItemMapKey({
    day: 1,
    itemId: "place-42",
    itemIndex: 0,
    name: "Hồ Hoàn Kiếm"
  });
  const after = planItemMapKey({
    day: 1,
    itemId: "place-42",
    itemIndex: 2,
    name: "Hồ Hoàn Kiếm"
  });

  assert.equal(after, before);
});

test("uses the position only for legacy items without an item id", () => {
  assert.notEqual(
    planItemMapKey({ day: 1, itemIndex: 0, name: "Điểm cũ" }),
    planItemMapKey({ day: 1, itemIndex: 1, name: "Điểm cũ" })
  );
});
