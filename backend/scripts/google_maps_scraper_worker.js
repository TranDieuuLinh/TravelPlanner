"use strict";

const fs = require("fs");
const path = require("path");
const {
  chromium,
} = require("/opt/ms-playwright-go/1.57.0/package");
const { lookupQueries } = require("./google_maps_place_lookup");

const workDir = process.env.GOOGLE_MAPS_SCRAPER_WORK_DIR || "/work";
const requestedConcurrency = Number.parseInt(
  process.env.GOOGLE_MAPS_SCRAPER_CONCURRENCY || "2",
  10
);
const concurrency = Number.isFinite(requestedConcurrency)
  ? Math.min(Math.max(requestedConcurrency, 1), 4)
  : 2;
const pollMilliseconds = 200;
const directories = {
  requests: path.join(workDir, "requests"),
  processing: path.join(workDir, "processing"),
  responses: path.join(workDir, "responses"),
  errors: path.join(workDir, "errors"),
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
    if (entry.isFile() && entry.name.endsWith(".txt")) {
      const destination = path.join(directories.requests, entry.name);
      await fs.promises.rename(source, destination).catch(async (error) => {
        if (error.code !== "EEXIST") {
          throw error;
        }
        await fs.promises.unlink(source).catch(() => {});
      });
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".json")) {
      await fs.promises.unlink(source).catch(() => {});
    }
  }
}

async function claimJob() {
  const names = (await fs.promises.readdir(directories.requests))
    .filter((name) => name.endsWith(".txt") && !name.startsWith("."))
    .sort();
  for (const name of names) {
    const requestPath = path.join(directories.requests, name);
    const processingPath = path.join(directories.processing, name);
    try {
      await fs.promises.rename(requestPath, processingPath);
      return {
        id: name.slice(0, -4),
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
  try {
    const queries = (await fs.promises.readFile(job.processingPath, "utf8"))
      .split(/\r?\n/)
      .map((value) => value.trim())
      .filter(Boolean);
    const results = await lookupQueries(page, queries);
    await writeAtomic(responsePath, JSON.stringify(results));
  } catch (error) {
    await writeAtomic(errorPath, "Google Maps Playwright worker failed.\n");
    process.stderr.write(`Google Maps worker job failed: ${error.message}\n`);
  } finally {
    await fs.promises.unlink(job.processingPath).catch(() => {});
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
    await browser.close();
  }
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    stopping = true;
  });
}

main().catch((error) => {
  process.stderr.write(`Google Maps worker stopped: ${error.message}\n`);
  process.exitCode = 1;
});
