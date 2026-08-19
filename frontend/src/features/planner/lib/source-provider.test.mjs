import assert from "node:assert/strict";
import test from "node:test";

import {
  itinerarySourceUrls,
  sourceProviderKind,
} from "./source-provider.ts";

test("collects itinerary URLs from refs and source notes", () => {
  assert.deepEqual(
    itinerarySourceUrls({
      sourceRefs: ["https://www.youtube.com/watch?v=example"],
      notes: {
        sourceUrl: "https://www.tiktok.com/@creator/video/1",
      },
      noteSources: [
        { type: "url", ref: "https://www.instagram.com/reel/example" },
        { type: "google_maps", ref: "https://maps.google.com/place" },
      ],
    }),
    [
      "https://www.tiktok.com/@creator/video/1",
      "https://www.instagram.com/reel/example",
      "https://www.youtube.com/watch?v=example",
    ]
  );
});

test("collects a planner stop URL kept only in its note", () => {
  assert.deepEqual(
    itinerarySourceUrls({
      sourceRefs: [],
      notes: {
        sourceUrl: "https://example.com/travel-guide",
      },
    }),
    ["https://example.com/travel-guide"]
  );
});

test("recognizes supported social source URLs", () => {
  assert.equal(
    sourceProviderKind("https://youtu.be/example", "database"),
    "youtube"
  );
  assert.equal(
    sourceProviderKind("https://www.tiktok.com/@creator/video/1", "knowledge_graph"),
    "tiktok"
  );
  assert.equal(
    sourceProviderKind("https://instagram.com/reel/example", "google_maps_scraper"),
    "instagram"
  );
});

test("recognizes webpage sources before and after place resolution", () => {
  assert.equal(sourceProviderKind("https://example.com/guide", "web_page"), "url");
  assert.equal(sourceProviderKind("https://example.com/guide", null), "url");
  assert.equal(
    sourceProviderKind(
      "https://vietnam.travel/things-to-do/11-must-see-attractions-ha-noi",
      "database"
    ),
    "url"
  );
  assert.equal(
    sourceProviderKind("https://example.com/guide", "knowledge_graph"),
    "url"
  );
});

test("does not assign a website icon to place-provider links", () => {
  assert.equal(
    sourceProviderKind("https://maps.google.com/place", "google_maps_scraper"),
    null
  );
  assert.equal(
    sourceProviderKind("https://www.google.com/maps/place/example", "database"),
    null
  );
  assert.equal(sourceProviderKind("fixture://source", "web_page"), null);
});
