import assert from "node:assert/strict";
import test from "node:test";

import { formatPlanNote, sourceScheduleNotes } from "./plan-note.ts";

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

test("builds schedule notes only from meaningful URL activity evidence", () => {
  const notes = sourceScheduleNotes({
    id: "plan-1",
    title: "Hà Nội",
    destination: "Hà Nội",
    kind: "main",
    planningAssumptions: ["Generic assumption that must not be shown"],
    days: [{
      day: 1,
      theme: "Phố cổ",
      transportLegs: [],
      items: [
        {
          name: "Cafe Phố Cổ",
          timeWindow: "08:00-09:00",
          placeType: "cafe",
          source: "selected_place",
          sourceRefs: ["https://example.com/reel"],
          sourceTimeHint: "morning",
          sourceActivity: "Gọi cà phê trứng"
        },
        {
          name: "Hồ Hoàn Kiếm",
          timeWindow: "09:00-10:00",
          placeType: "attraction",
          source: "finder_suggestion",
          sourceRefs: [],
          notes: "Mô tả địa điểm chung chung"
        },
        {
          name: "Nhà thờ Lớn",
          timeWindow: "10:00-11:00",
          placeType: "attraction",
          source: "selected_place",
          sourceRefs: ["https://example.com/reel"],
          sourceActivity: null
        }
      ]
    }]
  });

  assert.deepEqual(notes.map(({ day, place, text }) => ({ day, place, text })), [{
    day: 1,
    place: "Cafe Phố Cổ",
    text: "Buổi sáng: Gọi cà phê trứng"
  }]);
});
