import assert from "node:assert/strict";
import test from "node:test";

import {
  formatNoteSources,
  formatPlanNote,
  formatSourceNoteForDisplay,
  planItemNotePresentation
} from "./plan-note.ts";

test("translates known itinerary notes into Vietnamese", () => {
  assert.equal(formatPlanNote("withdraw money"), "Rút tiền");
  assert.equal(
    formatPlanNote("Eat dessert and wait for sightseeing bus."),
    "Ăn món tráng miệng và chờ xe buýt tham quan"
  );
});

test("translates known source notes and preserves unknown English notes", () => {
  assert.equal(
    formatSourceNoteForDisplay(
      "explore cute cafés, shops, and a night market"
    ),
    "Khám phá các quán cà phê xinh xắn, cửa hàng và chợ đêm"
  );
  assert.equal(
    formatSourceNoteForDisplay("nature viewpoint hike"),
    "Đi bộ đường dài đến điểm ngắm cảnh thiên nhiên"
  );
  assert.equal(
    formatSourceNoteForDisplay(
      "purchase the audio guide as the show is in vietnamese"
    ),
    "Mua hướng dẫn âm thanh vì chương trình biểu diễn bằng tiếng Việt"
  );
  assert.equal(
    formatSourceNoteForDisplay(
      "relaxing head spa treatment that leaves hair shining"
    ),
    "Thư giãn với liệu trình spa đầu giúp tóc bóng mượt"
  );
  assert.equal(
    formatSourceNoteForDisplay("A new untranslated generated note"),
    "A new untranslated generated note"
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
        {
          type: "url",
          text: "Creator gọi cà phê trứng vào buổi sáng và dặn nên gọi ít đường.",
          ref: "https://example.com/reel",
          evidenceTypes: ["stt"]
        },
        {
          type: "google_maps",
          text: "Theo dữ liệu từ Google, Cà phê Giảng là một quán cà phê.",
          ref: "google-place-id"
        }
      ],
      personalNotes: "Nhớ gọi ít đường."
    }),
    {
      sourceNotes: [
        {
          type: "url",
          label: "Gợi ý từ nguồn tham khảo",
          text: "Creator gọi cà phê trứng vào buổi sáng và dặn nên gọi ít đường."
        }
      ],
      sourceLabel: "Gợi ý từ nguồn tham khảo",
      sourceText: "Creator gọi cà phê trứng vào buổi sáng và dặn nên gọi ít đường.",
      personalText: "Nhớ gọi ít đường."
    }
  );
});

test("infers a source label for legacy plan revisions", () => {
  const legacyPresentation = planItemNotePresentation({
    name: "Cà phê Giảng",
    notes: null,
    sourceActivity: "Explore Cà phê Giảng in the morning",
    sourceRefs: ["https://example.com/reel"],
    sourceProvider: "google_maps_scraper",
    placeType: "Coffee shop"
  });
  assert.equal(legacyPresentation.sourceLabel, null);
  assert.deepEqual(legacyPresentation.sourceNotes, []);
  assert.equal(
    formatNoteSources([{ type: "google_maps" }]),
    null
  );
  assert.equal(
    formatNoteSources([
      { type: "url" },
      { type: "place_provider" }
    ]),
    "Gợi ý từ nguồn tham khảo"
  );
});

test("does not turn provider metadata into a note", () => {
  const presentation = planItemNotePresentation({
    name: "Private-Box Hookah",
    source: "finder_suggestion",
    sourceProvider: "google_maps",
    sourceRefs: ["https://example.com/video"],
    notes: "Private-Box Hookah belongs to the coffee shop category.",
    placeType: "Coffee shop",
    rating: 4.9,
    reviewCount: 951
  });

  assert.deepEqual(presentation.sourceNotes, []);
});

test("hides mention-only video provenance", () => {
  const presentation = planItemNotePresentation({
    name: "Hoàng thành Thăng Long",
    noteSources: [
      {
        type: "url",
        text: "Video tham khảo có nhắc đến Hoàng thành Thăng Long."
      }
    ]
  });

  assert.deepEqual(presentation.sourceNotes, []);
});
