"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const workDir = fs.mkdtempSync(path.join(os.tmpdir(), "vsf-maps-worker-"));
process.env.GOOGLE_MAPS_SCRAPER_WORK_DIR = workDir;
process.env.GOOGLE_MAPS_SCRAPER_STALE_ARTIFACT_SECONDS = "1";

const {
  cleanupStaleArtifacts,
  directories,
  processJob,
} = require("../scripts/google_maps_scraper_worker");

async function ensureDirectories() {
  await Promise.all(
    Object.values(directories).map((directory) =>
      fs.promises.mkdir(directory, { recursive: true })
    )
  );
}

test("expired jobs are discarded before Playwright lookup", async () => {
  await ensureDirectories();
  const jobId = "expired-job";
  const processingPath = path.join(directories.processing, `${jobId}.json`);
  await fs.promises.writeFile(
    processingPath,
    JSON.stringify({
      queries: ["Slow Place, Hà Nội"],
      createdAtMs: Date.now() - 2000,
      deadlineAtMs: Date.now() - 1000,
    })
  );
  let closeCalls = 0;

  await processJob(
    { close: async () => { closeCalls += 1; } },
    { id: jobId, processingPath }
  );

  assert.equal(closeCalls, 0);
  assert.equal(fs.existsSync(processingPath), false);
  assert.equal(
    fs.existsSync(path.join(directories.responses, `${jobId}.json`)),
    false
  );
  assert.equal(
    fs.existsSync(path.join(directories.errors, `${jobId}.txt`)),
    false
  );
});

test("stale response, status, error, and cancellation files are removed", async () => {
  await ensureDirectories();
  const oldDate = new Date(Date.now() - 5000);
  for (const [directory, fileName] of [
    [directories.responses, "orphan.json"],
    [directories.status, "orphan.json"],
    [directories.errors, "orphan.txt"],
    [directories.cancellations, "orphan.cancel"],
  ]) {
    const filePath = path.join(directory, fileName);
    await fs.promises.writeFile(filePath, "orphan");
    await fs.promises.utimes(filePath, oldDate, oldDate);
  }

  await cleanupStaleArtifacts();

  for (const directory of [
    directories.responses,
    directories.status,
    directories.errors,
    directories.cancellations,
  ]) {
    assert.deepEqual(await fs.promises.readdir(directory), []);
  }
});
