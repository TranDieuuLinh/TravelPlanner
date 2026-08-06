"use strict";

const { chromium } = require("playwright");

function isGoogleHost(hostname) {
  return hostname === "google.com" || hostname.endsWith(".google.com");
}

function normalizeResultUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    if (isGoogleHost(parsed.hostname) && parsed.pathname === "/url") {
      const target = parsed.searchParams.get("q") || parsed.searchParams.get("url");
      return target ? normalizeResultUrl(target) : null;
    }
    if (!['http:', 'https:'].includes(parsed.protocol) || isGoogleHost(parsed.hostname)) {
      return null;
    }
    parsed.hash = "";
    return parsed.toString();
  } catch (_error) {
    return null;
  }
}

function normalizeSearchResults(rows, limit) {
  const results = [];
  const seen = new Set();
  for (const row of rows) {
    const uri = normalizeResultUrl(row.uri);
    const title = String(row.title || "").trim();
    if (!uri || !title || seen.has(uri)) {
      continue;
    }
    seen.add(uri);
    results.push({
      title: title.slice(0, 500),
      uri: uri.slice(0, 2048),
      snippet: String(row.snippet || "").trim().slice(0, 2000),
    });
    if (results.length >= limit) {
      break;
    }
  }
  return results;
}

async function acceptConsent(page) {
  for (const label of ["Accept all", "I agree", "Chấp nhận tất cả", "Tôi đồng ý"]) {
    const button = page.getByRole("button", { name: label, exact: true });
    if (await button.count()) {
      await button.first().click({ timeout: 2000 }).catch(() => {});
      return;
    }
  }
}

async function searchGoogleWeb(page, query, options = {}) {
  const limit = Math.min(Math.max(Number(options.limit) || 8, 1), 10);
  const shouldContinue = options.shouldContinue || (() => true);
  const url = new URL("https://www.google.com/search");
  url.searchParams.set("q", query);
  url.searchParams.set("hl", "vi");
  url.searchParams.set("gl", "vn");
  url.searchParams.set("num", String(limit));
  url.searchParams.set("filter", "0");
  await page.goto(url.toString(), {
    waitUntil: "domcontentloaded",
    timeout: 30000,
  });
  await acceptConsent(page);
  if (!shouldContinue()) {
    return [];
  }
  const bodyText = await page.locator("body").innerText().catch(() => "");
  const blocked =
    page.url().includes("/sorry/") ||
    /unusual traffic|automated queries|không phải là rô-bốt|captcha/i.test(bodyText);
  if (blocked) {
    throw new Error("google_playwright_blocked");
  }
  await page.locator("a h3").first().waitFor({ timeout: 10000 }).catch(() => {});
  const rows = await page.locator("a:has(h3)").evaluateAll((anchors) =>
    anchors.map((anchor) => {
      const heading = anchor.querySelector("h3");
      const container = anchor.closest("div.MjjYud") || anchor.parentElement?.parentElement;
      const fullText = container?.innerText || "";
      const title = heading?.innerText || "";
      return {
        title,
        uri: anchor.href,
        snippet: fullText.replace(title, "").trim(),
      };
    })
  );
  return normalizeSearchResults(rows, limit);
}

function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    args[argv[index]] = argv[index + 1];
  }
  return {
    query: String(args["--query"] || "").trim(),
    limit: Math.min(Math.max(Number.parseInt(args["--limit"] || "8", 10), 1), 10),
  };
}

async function main() {
  const { query, limit } = parseArgs(process.argv.slice(2));
  if (!query) {
    throw new Error("google_playwright_query_required");
  }
  const browser = await chromium.launch({
    headless: process.env.GOOGLE_WEB_SEARCH_HEADLESS !== "0",
    args: ["--disable-dev-shm-usage", "--no-sandbox"],
  });
  const context = await browser.newContext({ locale: "vi-VN" });
  const page = await context.newPage();
  try {
    const results = await searchGoogleWeb(page, query, { limit });
    process.stdout.write(JSON.stringify({ results }));
  } finally {
    await browser.close();
  }
}

module.exports = { normalizeResultUrl, normalizeSearchResults, searchGoogleWeb };

if (require.main === module) {
  main().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
