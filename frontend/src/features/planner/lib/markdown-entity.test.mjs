import assert from "node:assert/strict";
import test from "node:test";

test("parses an encoded entity id and builds the id preview endpoint", async () => {
  const { entityPreviewPath, parseEntityId } = await import("./markdown-entity.ts");

  assert.equal(parseEntityId("travel-entity://entity/h%C3%A0-n%E1%BB%99i%2F1"), "hà-nội/1");
  assert.equal(
    entityPreviewPath("hà-nội/1"),
    "/v1/knowledge-graph/entities/h%C3%A0-n%E1%BB%99i%2F1/preview",
  );
});

test("keeps same-label entities distinct by id", async () => {
  const { entityPreviewPath } = await import("./markdown-entity.ts");

  assert.notEqual(entityPreviewPath("node-a"), entityPreviewPath("node-b"));
  assert.equal(entityPreviewPath("node-a").includes("entity-preview?name="), false);
});

test("deduplicates hover and click requests for the same entity id", async () => {
  const { createEntityPreviewLoader } = await import("./markdown-entity.ts");
  let calls = 0;
  let resolveRequest;
  const loader = createEntityPreviewLoader(
    () => new Promise((resolve) => {
      calls += 1;
      resolveRequest = resolve;
    }),
  );

  const hoverRequest = loader.load("shared-node");
  const clickRequest = loader.load("shared-node");
  assert.equal(hoverRequest, clickRequest);
  assert.equal(calls, 1);

  resolveRequest({ id: "shared-node", name: "Shared node", entityType: "Place", details: {} });
  await Promise.all([hoverRequest, clickRequest]);
});
