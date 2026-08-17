import assert from "node:assert/strict";
import test from "node:test";

import {
  citationSources,
  highlightSegments,
  inlineSpanText,
} from "./answer-blocks.ts";

test("highlightSegments marks only backend supplied non-overlapping highlights", () => {
  assert.deepEqual(
    highlightSegments("Di tích quốc gia đặc biệt năm 2013.", [
      "quốc gia đặc biệt",
      "năm 2013",
      "không có",
    ]),
    [
      { text: "Di tích ", highlighted: false },
      { text: "quốc gia đặc biệt", highlighted: true },
      { text: " ", highlighted: false },
      { text: "năm 2013", highlighted: true },
      { text: ".", highlighted: false },
    ],
  );
});

test("inlineSpanText preserves text and ignores malformed spans", () => {
  assert.equal(
    inlineSpanText([
      { type: "text", text: "Hồ " },
      { type: "entity", text: "Gươm", entityId: "place-1" },
      { type: "entity", text: "bad" },
    ]),
    "Hồ Gươm",
  );
});

test("citationSources resolves only valid source IDs and URLs", () => {
  assert.deepEqual(
    citationSources(["source-2", "missing", "source-1"], [
      { sourceId: "source-1", title: "One", url: "https://one.test" },
      { sourceId: "source-2", title: "Two", url: "https://two.test" },
      { sourceId: "bad", title: "Bad", url: "javascript:alert(1)" },
    ]).map((source) => source.sourceId),
    ["source-2", "source-1"],
  );
});
