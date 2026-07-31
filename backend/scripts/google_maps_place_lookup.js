"use strict";

const fs = require("fs");
const {
  chromium,
} = require("/opt/ms-playwright-go/1.57.0/package");

function coordinatesFromUrl(value) {
  let decoded = value || "";
  try {
    decoded = decodeURIComponent(decoded);
  } catch {
    // Full HTML can contain standalone percent signs; search it as-is.
  }
  const atMatch = decoded.match(
    /@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/
  );
  if (atMatch) {
    return {
      latitude: Number(atMatch[1]),
      longitude: Number(atMatch[2]),
    };
  }
  const protobufMatch = decoded.match(
    /!2d(-?\d+(?:\.\d+)?).*?!3d(-?\d+(?:\.\d+)?)/
  );
  if (protobufMatch) {
    return {
      latitude: Number(protobufMatch[2]),
      longitude: Number(protobufMatch[1]),
    };
  }
  const dataMatch = decoded.match(
    /!3d(-?\d+(?:\.\d+)?).*?!4d(-?\d+(?:\.\d+)?)/
  );
  if (dataMatch) {
    return {
      latitude: Number(dataMatch[1]),
      longitude: Number(dataMatch[2]),
    };
  }
  return null;
}

async function firstText(page, selectors) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if ((await locator.count()) === 0) {
      continue;
    }
    const value = (await locator.textContent())?.trim();
    if (value) {
      return value;
    }
  }
  return null;
}

async function lookup(page, query) {
  const searchUrl =
    `https://www.google.com/maps/search/${encodeURIComponent(query)}` +
    "?hl=vi";
  await page.goto(searchUrl, {
    waitUntil: "domcontentloaded",
    timeout: 15000,
  });

  const consentButton = page
    .getByRole("button", { name: /accept all|đồng ý tất cả/i })
    .first();
  if ((await consentButton.count()) > 0) {
    await consentButton.click({ timeout: 2000 }).catch(() => {});
  }
  await page.waitForTimeout(2500);
  await page
    .waitForURL((url) => url.pathname.includes("/maps/place/"), {
      timeout: 5000,
    })
    .catch(() => {});

  let link = page.url();
  let coordinates = coordinatesFromUrl(link);
  if (!coordinates) {
    const placeLinks = await page
      .locator('a[href*="/maps/place/"]')
      .evaluateAll((anchors) => anchors.map((anchor) => anchor.href));
    for (const placeLink of placeLinks) {
      coordinates = coordinatesFromUrl(placeLink);
      if (coordinates) {
        link = placeLink;
        break;
      }
    }
  }
  if (!coordinates) {
    const shareButton = page
      .locator(
        'button[jsaction*="share"], button[aria-label*="Chia sẻ"], button[aria-label*="Share"]'
      )
      .first();
    if ((await shareButton.count()) > 0) {
      await shareButton.click({ timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(750);
      const shareInput = page.locator('div[role="dialog"] input').first();
      if ((await shareInput.count()) > 0) {
        const shareUrl = await shareInput.inputValue();
        coordinates = coordinatesFromUrl(shareUrl);
        if (!coordinates && shareUrl) {
          const response = await page.request.get(shareUrl, {
            maxRedirects: 10,
            timeout: 10000,
          });
          link = response.url();
          coordinates = coordinatesFromUrl(link);
        }
      }
    }
  }
  if (!coordinates) {
    coordinates = coordinatesFromUrl(await page.content());
  }
  if (!coordinates) {
    const resourceUrls = await page.evaluate(() =>
      performance
        .getEntriesByType("resource")
        .map((entry) => entry.name)
    );
    for (const resourceUrl of resourceUrls) {
      coordinates = coordinatesFromUrl(resourceUrl);
      if (coordinates) {
        break;
      }
    }
  }
  if (!coordinates) {
    link = page.url();
    coordinates = coordinatesFromUrl(link);
  }
  if (!coordinates) {
    const currentUrl = new URL(page.url());
    const pageTitle = (await page.title()).slice(0, 120);
    const placeLinkCount = await page.locator('a[href*="/maps/place/"]').count();
    process.stderr.write(
      `No Google Maps coordinates at ${currentUrl.hostname}${currentUrl.pathname}; ` +
        `title=${JSON.stringify(pageTitle)}; placeLinks=${placeLinkCount}\n`
    );
    return null;
  }

  const title =
    (await firstText(page, ["h1.DUwDvf", "h1"])) || query.split(",")[0];
  const rawAddress = await firstText(page, [
    'button[data-item-id="address"]',
    '[data-item-id="address"]',
  ]);
  const address = rawAddress?.replace(/^[\uE000-\uF8FF\s]+/, "") || null;
  const category = await firstText(page, [
    'button[jsaction*="pane.rating.category"]',
    'button[jsaction*="category"]',
  ]);

  return {
    title,
    category,
    address,
    latitude: coordinates.latitude,
    longitude: coordinates.longitude,
    link,
  };
}

async function lookupQueries(page, queries) {
  const results = [];
  for (const query of queries) {
    const result = await lookup(page, query).catch((error) => {
      process.stderr.write(`Google Maps page lookup failed: ${error.message}\n`);
      return null;
    });
    if (result) {
      results.push(result);
    }
  }
  return results;
}

async function runCli() {
  const inputPath = process.argv[2];
  const outputPath = process.argv[3];
  if (!inputPath || !outputPath) {
    throw new Error("Usage: node google_maps_place_lookup.js INPUT OUTPUT");
  }
  const queries = fs
    .readFileSync(inputPath, "utf8")
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox"],
  });
  const context = await browser.newContext({
    locale: "vi-VN",
  });
  const page = await context.newPage();

  let results;
  try {
    results = await lookupQueries(page, queries);
  } finally {
    await browser.close();
  }

  fs.writeFileSync(outputPath, JSON.stringify(results));
  if (results.length === 0) {
    process.exitCode = 2;
  }
}

module.exports = { lookup, lookupQueries };

if (require.main === module) {
  runCli().catch((error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}
