import assert from "node:assert/strict";
import test from "node:test";

import {
  formatNoteSources,
  formatPlanNote,
  planItemNotePresentation
} from "./plan-note.ts";

test("translates known itinerary notes into Vietnamese", () => {
  assert.equal(formatPlanNote("withdraw money"), "Rút tiền");
  assert.equal(
    formatPlanNote("Eat dessert and wait for sightseeing bus."),
    "Ăn món tráng miệng và chờ xe buýt tham quan"
  );
});

test("hides missing and NaN-like note values", () => {
  for (const value of [null, undefined, Number.NaN, "", "  ", "NaN", " null ", "N/A"]) {
    assert.equal(formatPlanNote(value), null);
  }
});

test("preserves valid notes that do not need a compatibility translation", () => {
  assert.equal(formatPlanNote("Thử món địa phương"), "Thử món địa phương");
});

test("presents source and personal notes without merging their ownership", () => {
  assert.deepEqual(
    planItemNotePresentation({
      notes: "Gọi cà phê trứng vào buổi sáng.",
      noteSources: [
        { type: "url", ref: "https://example.com/reel", evidenceTypes: ["stt"] },
        { type: "google_maps", ref: "google-place-id" }
      ],
      personalNotes: "Nhớ gọi ít đường."
    }),
    {
      sourceLabel: "Từ video tham khảo\nGoogle Maps",
      sourceText: "Gọi cà phê trứng vào buổi sáng.",
      personalText: "Nhớ gọi ít đường."
    }
  );
});

test("infers a source label for legacy plan revisions", () => {
  assert.equal(
    planItemNotePresentation({
      notes: null,
      sourceActivity: "Ăn sáng",
      sourceRefs: ["https://example.com/reel"]
    }).sourceLabel,
    "Từ video tham khảo"
  );
  assert.equal(
    formatNoteSources([{ type: "google_maps" }]),
    "Google Maps"
  );
  assert.equal(
    formatNoteSources([
      { type: "url" },
      { type: "place_provider" }
    ]),
    "Từ video tham khảo\nNguồn địa điểm"
  );
});
