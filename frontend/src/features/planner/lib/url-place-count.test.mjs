import assert from "node:assert/strict";
import test from "node:test";

import { urlPlaceCountLabel } from "./url-place-count.ts";

test("uses persisted places as the UI count and deduplicated candidates as the source total", () => {
  assert.equal(
    urlPlaceCountLabel({ candidateCount: 5, persistedCount: 3 }),
    "3 trên 5 được hiển thị"
  );
});

test("does not show duplicate or invalid counts above the unique source total", () => {
  assert.equal(
    urlPlaceCountLabel({ candidateCount: 2, persistedCount: 4 }),
    "2 trên 2 được hiển thị"
  );
  assert.equal(
    urlPlaceCountLabel({ candidateCount: 0, persistedCount: 1 }),
    "Chưa tìm thấy địa điểm"
  );
});
