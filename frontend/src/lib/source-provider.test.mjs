import assert from "node:assert/strict";
import test from "node:test";

import { sourceProviderKind } from "./source-provider.ts";

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

test("recognizes an explicit webpage source and legacy URL-only revisions", () => {
  assert.equal(sourceProviderKind("https://example.com/guide", "web_page"), "url");
  assert.equal(sourceProviderKind("https://example.com/guide", null), "url");
});

test("does not assign an icon to unsupported source providers", () => {
  assert.equal(
    sourceProviderKind("https://example.com/place", "database"),
    null
  );
  assert.equal(
    sourceProviderKind("https://maps.google.com/place", "google_maps_scraper"),
    null
  );
  assert.equal(sourceProviderKind("fixture://source", "web_page"), null);
});
