"use strict";

const fs = require("fs");
const { chromium } = require("playwright");

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

async function firstAttribute(page, selectors, attribute) {
  for (const selector of selectors) {
    const locator = page.locator(selector).first();
    if ((await locator.count()) === 0) {
      continue;
    }
    const value = (await locator.getAttribute(attribute))?.trim();
    if (value) {
      return value;
    }
  }
  return null;
}

function parseLocalizedNumber(value) {
  const match = String(value || "").match(/\d+(?:[.,]\d+)?/);
  if (!match) {
    return null;
  }
  const parsed = Number.parseFloat(match[0].replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

function parseReviewCount(value) {
  const normalized = String(value || "").trim().toLowerCase();
  const match = normalized.match(/(\d[\d.,\s]*)(?:\s*)(k|n|nghìn|m|tr|triệu)?/i);
  if (!match) {
    return null;
  }
  const suffix = (match[2] || "").toLowerCase();
  let numeric;
  if (suffix) {
    numeric = Number.parseFloat(match[1].replace(/\s/g, "").replace(",", "."));
  } else {
    numeric = Number.parseInt(match[1].replace(/\D/g, ""), 10);
  }
  if (!Number.isFinite(numeric)) {
    return null;
  }
  const multiplier = ["k", "n", "nghìn"].includes(suffix)
    ? 1000
    : ["m", "tr", "triệu"].includes(suffix)
      ? 1000000
      : 1;
  return Math.round(numeric * multiplier);
}

function parseOpeningHours(value) {
  const raw = String(value || "")
    .replace(/^(giờ mở cửa|opening hours)\s*:?\s*/i, "")
    .replace(/,\s*(sao chép giờ mở cửa|copy opening hours).*$/i, "")
    .trim();
  if (!raw) {
    return [];
  }
  const days = [
    [/^(thứ hai|monday)\b/i, 1],
    [/^(thứ ba|tuesday)\b/i, 2],
    [/^(thứ tư|wednesday)\b/i, 3],
    [/^(thứ năm|thursday)\b/i, 4],
    [/^(thứ sáu|friday)\b/i, 5],
    [/^(thứ bảy|saturday)\b/i, 6],
    [/^(chủ nhật|sunday)\b/i, 7],
  ];
  const parsed = raw.split(";").map((part) => part.trim()).filter(Boolean).map((part) => {
    const day = days.find(([pattern]) => pattern.test(part));
    if (!day) {
      return null;
    }
    const dayName = part.match(day[0])?.[0] || null;
    const rawTimeSlots = part
      .replace(day[0], "")
      .replace(/^[,:\s-]+/, "")
      .trim() || null;
    return {
      dayOfWeek: day[1],
      dayName,
      rawTimeSlots,
      is24Hours: /24\s*(giờ|hours?)/i.test(rawTimeSlots || ""),
      sourceFormat: "google_maps",
    };
  }).filter(Boolean);
  return parsed.length > 0
    ? parsed
    : [{ rawTimeSlots: raw, is24Hours: /24\s*(giờ|hours?)/i.test(raw), sourceFormat: "google_maps" }];
}

function googleIdentityFromUrl(value) {
  let decoded = value || "";
  try {
    decoded = decodeURIComponent(decoded);
  } catch {
    // Keep the original URL when Google includes a malformed escape sequence.
  }
  const placeId = decoded.match(/!1s(ChIJ[^!/?&]+)/)?.[1] || null;
  const dataId = decoded.match(/!1s([^!/?&]+)/)?.[1] || null;
  const cid = decoded.match(/[?&]cid=(\d+)/)?.[1] || null;
  return { placeId, dataId, cid };
}

function normalizedPlaceName(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/gi, "d")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

async function openBestPlaceResult(page, query) {
  if (new URL(page.url()).pathname.includes("/maps/place/")) {
    return;
  }
  const expectedName = normalizedPlaceName(query.split(",", 1)[0]);
  const links = await page
    .locator('a[href*="/maps/place/"]')
    .evaluateAll((anchors) => anchors.map((anchor, index) => ({
      href: anchor.href,
      label: anchor.getAttribute("aria-label") || anchor.textContent || "",
      index,
    })));
  if (links.length === 0) {
    return;
  }
  const scored = links.map((link) => {
    const label = normalizedPlaceName(link.label);
    const exact = label === expectedName;
    const startsWith = label.startsWith(`${expectedName} `);
    return {
      ...link,
      score: exact ? 3 : startsWith ? 2 : label.includes(expectedName) ? 1 : 0,
    };
  });
  scored.sort((left, right) => right.score - left.score || left.index - right.index);
  await page.goto(scored[0].href, {
    waitUntil: "domcontentloaded",
    timeout: 15000,
  });
  await page.waitForTimeout(1000);
}

async function scrapeListViewItems(page) {
  // Scrape data from the search results list
  const items = await page.evaluate(() => {
    const results = [];
    const elements = document.querySelectorAll('div.Nv2PK');
    
    for (const el of elements) {
      const text = el.textContent || '';
      
      // Normalize whitespace
      const normalizedText = text.replace(/\s+/g, ' ').trim();
      
      // Extract name - take everything before space+number
      const nameMatch = normalizedText.match(/^(.+?)\s+\d,\d/);
      const name = nameMatch ? nameMatch[1].trim() : null;
      if (!name || name.length < 2) continue;
      
      // Extract rating - look for "X,X" pattern (Vietnam uses comma as decimal)
      const ratingMatch = normalizedText.match(/(\d),(\d)(?=\S)/);
      const rating = ratingMatch ? parseFloat(ratingMatch[0].replace(',', '.')) : null;
      
      // Extract review count - Google Maps list view often doesn't show this
      // Try common patterns: (123), 123 đánh giá, etc.
      const reviewMatch = normalizedText.match(/\(([\d,]+)\)/);
      const reviewCount = reviewMatch ? parseInt(reviewMatch[1].replace(/\D/g, ''), 10) : null;
      
      // Extract category/type
      const categoryMatch = normalizedText.match(/(Khách sạn|Nhà hàng|Quán|Bảo tàng|Địa điểm du lịch|Công viên|Chùa|Nhà thờ|ATM|Ngân hàng|Bệnh viện|Cửa hàng|Phòng khám|Nhà nghỉ|Khu du lịch|Nhà hàng cơm|Nhà hàng)/);
      const category = categoryMatch ? categoryMatch[1] : null;
      
      // Extract address (contains P., Ng., Đ., district names, Vietnam)
      const addressMatch = normalizedText.match(/((?:P\.|Ng\.|Đ\.)?\s*[^•]{5,100}?(?:Hà Nội|Vietnam|Đà Nẵng|HCM))/);
      const address = addressMatch ? addressMatch[1].trim() : null;
      
      // Get the link
      const linkEl = el.querySelector('a[href*="/maps/place/"]');
      const href = linkEl ? linkEl.href : null;
      
      // Extract price level ($ symbols)
      const priceLevel = (normalizedText.match(/\$\$\$\$/g) || []).length || 
                        (normalizedText.match(/\$\$\$/g) || []).length || 
                        (normalizedText.match(/\$\$/g) || []).length || null;
      
      if (href && name) {
        results.push({
          name,
          rating,
          reviewCount,
          category,
          address,
          href,
          priceLevel,
        });
      }
    }
    return results;
  });
  return items;
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
  
  // FIRST: scrape data from list view (has rating, reviews) - MUST be before any navigation
  const listItems = await scrapeListViewItems(page);

  // Then check if we're already on a place page
  const currentUrl = page.url();
  const isPlacePage = currentUrl.includes("/maps/place/");
  
  // If not on place page, navigate to first result for detailed info
  if (!isPlacePage) {
    await openBestPlaceResult(page, query);
  }

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
  const ratingText = await firstText(page, [
    "div.F7nice span[aria-hidden='true']",
    "span.ceNzKf",
  ]);
  const reviewLabel = await firstAttribute(page, [
    'button[jsaction*="pane.reviewChart.moreReviews"]',
    'button[aria-label*="bài đánh giá"]',
    'button[aria-label*="reviews"]',
  ], "aria-label");
  const reviewText = await firstText(page, [
    'button[jsaction*="pane.reviewChart.moreReviews"]',
    'button[aria-label*="bài đánh giá"]',
    'button[aria-label*="reviews"]',
  ]);
  const openingHoursText = await firstAttribute(
    page,
    [
      'button[data-item-id="oh"]',
      '[data-item-id="oh"]',
      'button[aria-label*="Sao chép giờ mở cửa"]',
      'button[aria-label*="Copy opening hours"]',
    ],
    "aria-label"
  ) || await firstText(page, [
    'button[data-item-id="oh"]',
    '[data-item-id="oh"]',
    'button[aria-label*="Sao chép giờ mở cửa"]',
    'button[aria-label*="Copy opening hours"]',
  ]);
  const rawPlusCode = await firstText(page, [
    'button[data-item-id="oloc"]',
    '[data-item-id="oloc"]',
  ]);
  const plusCode = rawPlusCode?.replace(/^[\uE000-\uF8FF\s]+/, "") || null;
  const phoneItemId = await firstAttribute(page, [
    '[data-item-id^="phone:tel:"]',
  ], "data-item-id");
  const phoneText = await firstText(page, [
    '[data-item-id^="phone:tel:"]',
  ]);
  const website = await firstAttribute(page, [
    'a[data-item-id="authority"]',
    '[data-item-id="authority"] a',
  ], "href");
  const description = await firstText(page, [
    '[data-item-id="description"]',
    ".PYvSYb",
    ".WeS02d",
  ]);
  const identity = googleIdentityFromUrl(link);

  // If we have list items, enrich them with detail data
  if (listItems.length > 0) {
    const enrichedResults = listItems.map((item, index) => {
      const coords = coordinatesFromUrl(item.href);
      const itemIdentity = googleIdentityFromUrl(item.href);
      return {
        title: item.name,
        category: item.category || category,
        address: item.address || address,
        latitude: coords ? coords.latitude : (index === 0 ? coordinates.latitude : null),
        longitude: coords ? coords.longitude : (index === 0 ? coordinates.longitude : null),
        link: item.href,
        place_id: itemIdentity.placeId,
        data_id: itemIdentity.dataId,
        review_rating: item.rating || (index === 0 ? parseLocalizedNumber(ratingText) : null),
        review_count: item.reviewCount || (index === 0 ? parseReviewCount(reviewLabel || reviewText) : null),
        opening_hours: index === 0 ? parseOpeningHours(openingHoursText) : null,
        plus_code: null,
        phone: index === 0 ? (phoneItemId?.replace(/^phone:tel:/, "") || phoneText) : null,
        website: index === 0 ? website : null,
        descriptions: index === 0 && description ? [description] : [],
        price_level: item.priceLevel,
      };
    });
    return enrichedResults;
  }

  // Fallback: return single result with detail data
  return [{
    title,
    category,
    address,
    latitude: coordinates.latitude,
    longitude: coordinates.longitude,
    link,
    place_id: identity.placeId,
    data_id: identity.dataId,
    cid: identity.cid,
    review_rating: parseLocalizedNumber(ratingText),
    review_count: parseReviewCount(reviewLabel || reviewText),
    opening_hours: parseOpeningHours(openingHoursText),
    plus_code: plusCode,
    phone: phoneItemId?.replace(/^phone:tel:/, "") || phoneText,
    website,
    descriptions: description ? [description] : [],
  }];
}

async function lookupQueries(page, queries, options = {}) {
  const results = [];
  for (const query of queries) {
    if (options.shouldContinue && !options.shouldContinue()) {
      break;
    }
    const result = await lookup(page, query).catch((error) => {
      process.stderr.write(`Google Maps page lookup failed: ${error.message}\n`);
      return null;
    });
    if (result) {
      // result is now an array (list of places from search)
      if (Array.isArray(result)) {
        results.push(...result);
      } else {
        results.push(result);
      }
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
