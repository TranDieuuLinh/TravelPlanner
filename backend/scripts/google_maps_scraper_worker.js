"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");
const { lookupQueries } = require("./google_maps_place_lookup");
const { searchGoogleWeb } = require("./google_web_search");

const workDir = process.env.GOOGLE_MAPS_SCRAPER_WORK_DIR || "/work";
const requestedConcurrency = Number.parseInt(
  process.env.GOOGLE_MAPS_SCRAPER_CONCURRENCY || "2",
  10
);
const concurrency = Number.isFinite(requestedConcurrency)
  ? Math.min(Math.max(requestedConcurrency, 1), 4)
  : 2;
const pollMilliseconds = 200;
const staleArtifactMilliseconds = Number.parseInt(
  process.env.GOOGLE_MAPS_SCRAPER_STALE_ARTIFACT_SECONDS || "600",
  10
) * 1000;
const directories = {
  requests: path.join(workDir, "requests"),
  processing: path.join(workDir, "processing"),
  responses: path.join(workDir, "responses"),
  errors: path.join(workDir, "errors"),
  cancellations: path.join(workDir, "cancellations"),
  status: path.join(workDir, "status"),
};

let stopping = false;

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function ensureDirectories() {
  await Promise.all(
    Object.values(directories).map((directory) =>
      fs.promises.mkdir(directory, { recursive: true })
    )
  );
}

async function recoverInterruptedJobs() {
  const entries = await fs.promises.readdir(directories.processing, {
    withFileTypes: true,
  });
  for (const entry of entries) {
    const source = path.join(directories.processing, entry.name);
    if (
      entry.isFile() &&
      (entry.name.endsWith(".txt") || entry.name.endsWith(".json"))
    ) {
      const destination = path.join(directories.requests, entry.name);
      await fs.promises.rename(source, destination).catch(async (error) => {
        if (error.code !== "EEXIST") {
          throw error;
        }
        await fs.promises.unlink(source).catch(() => {});
      });
      continue;
    }
  }
}

async function cleanupStaleArtifacts() {
  const cutoff = Date.now() - staleArtifactMilliseconds;
  for (const directory of [
    directories.responses,
    directories.errors,
    directories.cancellations,
    directories.status,
  ]) {
    const entries = await fs.promises.readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isFile() || entry.name.startsWith(".")) {
        continue;
      }
      const filePath = path.join(directory, entry.name);
      const stats = await fs.promises.stat(filePath).catch(() => null);
      if (stats && stats.mtimeMs < cutoff) {
        await fs.promises.unlink(filePath).catch(() => {});
      }
    }
  }
}

async function claimJob() {
  const names = (await fs.promises.readdir(directories.requests))
    .filter(
      (name) =>
        (name.endsWith(".json") || name.endsWith(".txt")) &&
        !name.startsWith(".")
    )
    .sort();
  for (const name of names) {
    const requestPath = path.join(directories.requests, name);
    const processingPath = path.join(directories.processing, name);
    try {
      await fs.promises.rename(requestPath, processingPath);
      return {
        id: name.replace(/\.(json|txt)$/, ""),
        processingPath,
      };
    } catch (error) {
      if (error.code !== "ENOENT") {
        throw error;
      }
    }
  }
  return null;
}

async function writeAtomic(destination, value) {
  const temporary = `${destination}.${process.pid}.${Date.now()}.tmp`;
  await fs.promises.writeFile(temporary, value, "utf8");
  await fs.promises.rename(temporary, destination);
}

async function processJob(page, job) {
  const responsePath = path.join(directories.responses, `${job.id}.json`);
  const errorPath = path.join(directories.errors, `${job.id}.txt`);
  const cancellationPath = path.join(
    directories.cancellations,
    `${job.id}.cancel`
  );
  const statusPath = path.join(directories.status, `${job.id}.json`);
  let cancellationWatcher = null;
  let cancelled = false;
  try {
    const rawRequest = await fs.promises.readFile(job.processingPath, "utf8");
    let queries;
    let requestKind = "google_maps";
    let webQuery = "";
    let resultLimit = 8;
    let createdAtMs;
    let deadlineAtMs;
    if (job.processingPath.endsWith(".json")) {
      const request = JSON.parse(rawRequest);
      requestKind = String(request.kind || "google_maps");
      queries = Array.isArray(request.queries)
        ? request.queries.map((value) => String(value).trim()).filter(Boolean)
        : [];
      webQuery = String(request.query || "").trim();
      resultLimit = Math.min(Math.max(Number(request.limit) || 8, 1), 10);
      createdAtMs = Number(request.createdAtMs) || Date.now();
      deadlineAtMs = Number(request.deadlineAtMs) || Date.now();
    } else {
      queries = rawRequest
        .split(/\r?\n/)
        .map((value) => value.trim())
        .filter(Boolean);
      createdAtMs = Date.now();
      deadlineAtMs = Date.now() + 90000;
    }
    const isCancelled = () =>
      cancelled || fs.existsSync(cancellationPath) || Date.now() >= deadlineAtMs;
    if (isCancelled()) {
      return;
    }
    const startedAtMs = Date.now();
    await writeAtomic(
      statusPath,
      JSON.stringify({ createdAtMs, startedAtMs, deadlineAtMs })
    );
    cancellationWatcher = setInterval(() => {
      if (!isCancelled()) {
        return;
      }
      cancelled = true;
      page.close().catch(() => {});
    }, 100);
    const results = requestKind === "google_web_search"
      ? await searchGoogleWeb(page, webQuery, {
          limit: resultLimit,
          shouldContinue: () => !isCancelled(),
        })
      : await lookupQueries(page, queries, {
          shouldContinue: () => !isCancelled(),
        });
    if (isCancelled()) {
      return;
    }
    const finishedAtMs = Date.now();
    await writeAtomic(
      responsePath,
      JSON.stringify({
        results,
        telemetry: {
          queueWaitSeconds: Math.max(0, startedAtMs - createdAtMs) / 1000,
          executionSeconds: Math.max(0, finishedAtMs - startedAtMs) / 1000,
        },
      })
    );
  } catch (error) {
    if (!cancelled && !fs.existsSync(cancellationPath)) {
      await writeAtomic(errorPath, "Google Maps Playwright worker failed.\n");
      process.stderr.write(`Google Maps worker job failed: ${error.message}\n`);
    }
  } finally {
    if (cancellationWatcher) {
      clearInterval(cancellationWatcher);
    }
    await fs.promises.unlink(job.processingPath).catch(() => {});
    await fs.promises.unlink(statusPath).catch(() => {});
    await fs.promises.unlink(cancellationPath).catch(() => {});
  }
}

async function runSlot(context) {
  let page = await context.newPage();
  while (!stopping) {
    const job = await claimJob();
    if (!job) {
      await sleep(pollMilliseconds);
      continue;
    }
    if (page.isClosed()) {
      page = await context.newPage();
    }
    await processJob(page, job);
  }
  await page.close().catch(() => {});
}

async function main() {
  await ensureDirectories();
  await recoverInterruptedJobs();
  await cleanupStaleArtifacts();
  const cleanupTimer = setInterval(() => {
    cleanupStaleArtifacts().catch((error) => {
      process.stderr.write(`Google Maps cleanup failed: ${error.message}\n`);
    });
  }, 60000);
  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox"],
  });
  const context = await browser.newContext({ locale: "vi-VN" });
  process.stdout.write(
    `Google Maps Playwright worker ready: one browser, ${concurrency} pages\n`
  );
  try {
    await Promise.all(
      Array.from({ length: concurrency }, () => runSlot(context))
    );
  } finally {
    clearInterval(cleanupTimer);
    await browser.close();
  }
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    stopping = true;
  });
}

module.exports = { cleanupStaleArtifacts, directories, processJob };

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`Google Maps worker stopped: ${error.message}\n`);
    process.exitCode = 1;
  });
}
