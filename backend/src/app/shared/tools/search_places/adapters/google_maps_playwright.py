from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import quote_plus

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.shared.contracts.place import Coordinates
from app.shared.tools.search_places.contract import (
    AdministrativeArea,
    PlaceProviderCandidate,
)
from app.shared.tools.search_places.ports import (
    ExternalPlaceDraftStore,
    PlaceSearchProviderError,
    PlaceSearchProviderTimeout,
)


class GoogleMapsPlaywrightSearch:
    """Bounded Google Maps browser adapter whose results remain unverified."""

    provider_name = "google_maps_playwright"

    def __init__(
        self,
        draft_store: ExternalPlaceDraftStore | None = None,
        *,
        timeout_seconds: float = 90,
        max_alias_queries: int = 2,
        max_concurrency: int = 2,
        headless: bool = True,
    ) -> None:
        self.draft_store = draft_store
        self.timeout_ms = round(timeout_seconds * 1000)
        self.max_alias_queries = max(0, max_alias_queries)
        self.max_concurrency = max(1, max_concurrency)
        self.headless = headless

    async def search(
        self,
        lookup_names: list[str],
        *,
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
        limit: int,
        anchor_place_id: str | None = None,
    ) -> list[PlaceProviderCandidate]:
        del anchor_place_id  # Google Maps receives locality through the query.
        queries = self._queries(lookup_names, input_adm, place_type_hint)
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=self.headless)
                try:
                    context = await browser.new_context(
                        locale="vi-VN",
                    )
                    urls = await self._collect_urls(context, queries, limit)
                    candidates = await self._collect_details(
                        context,
                        urls[:limit],
                        input_adm=input_adm,
                        place_type_hint=place_type_hint,
                    )
                finally:
                    await browser.close()
        except PlaywrightTimeoutError as exc:
            raise PlaceSearchProviderTimeout("Google Maps search timed out") from exc
        except (PlaceSearchProviderError, PlaceSearchProviderTimeout):
            raise
        except Exception as exc:
            raise PlaceSearchProviderError("Google Maps browser search failed") from exc

        if self.draft_store is None:
            return candidates
        persisted: list[PlaceProviderCandidate] = []
        for candidate in candidates:
            persisted.append(
                await self.draft_store.upsert_draft(candidate, input_adm=input_adm)
            )
        return persisted

    def _queries(
        self,
        lookup_names: list[str],
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
    ) -> list[str]:
        type_query = (
            None
            if (place_type_hint or "").casefold() in {
                "travel place",
                "travel_place",
                "attraction",
            }
            else place_type_hint
        )
        suffix = " ".join(
            part for part in (type_query, input_adm.name) if part
        ).strip()
        return [
            " ".join(part for part in (name, suffix) if part).strip()
            for name in lookup_names[: 1 + self.max_alias_queries]
        ]

    async def _collect_urls(self, context, queries: list[str], limit: int) -> list[str]:
        page = await context.new_page()
        urls: list[str] = []
        try:
            for query in queries:
                await page.goto(
                    (
                        "https://www.google.com/maps/search/?api=1&hl=vi&query="
                        f"{quote_plus(query)}"
                    ),
                    wait_until="domcontentloaded",
                    timeout=self.timeout_ms,
                )
                await self._reject_blocked_page(page)
                try:
                    await page.wait_for_selector(
                        'h1, a[href*="/maps/place/"]',
                        timeout=min(self.timeout_ms, 15_000),
                    )
                except PlaywrightTimeoutError:
                    continue
                if await page.locator("h1").count():
                    if page.url not in urls:
                        urls.append(page.url)
                    if len(urls) >= limit:
                        return urls
                found = await page.locator('a[href*="/maps/place/"]').evaluate_all(
                    "els => els.map(el => el.href).filter(Boolean)"
                )
                for url in found:
                    canonical = str(url).split("&entry=")[0]
                    if canonical not in urls:
                        urls.append(canonical)
                    if len(urls) >= limit:
                        return urls
        finally:
            await page.close()
        return urls

    async def _collect_details(
        self,
        context,
        urls: list[str],
        *,
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
    ) -> list[PlaceProviderCandidate]:
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def bounded(url: str) -> PlaceProviderCandidate | None:
            async with semaphore:
                return await self._detail(
                    context,
                    url,
                    input_adm=input_adm,
                    place_type_hint=place_type_hint,
                )

        results = await asyncio.gather(*(bounded(url) for url in urls))
        return [candidate for candidate in results if candidate is not None]

    async def _detail(
        self,
        context,
        url: str,
        *,
        input_adm: AdministrativeArea,
        place_type_hint: str | None,
    ) -> PlaceProviderCandidate | None:
        page = await context.new_page()
        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout_ms,
            )
            await self._reject_blocked_page(page)
            try:
                await page.wait_for_selector("h1", timeout=min(self.timeout_ms, 15_000))
            except PlaywrightTimeoutError:
                return None
            payload = await page.evaluate(
                """() => {
                  const text = (selector) => document.querySelector(selector)?.textContent?.trim() || null;
                  const aria = (selector) => document.querySelector(selector)?.getAttribute('aria-label') || null;
                  const href = (selector) => document.querySelector(selector)?.href || null;
                  const reviews = [...document.querySelectorAll('button')]
                    .map(el => el.getAttribute('aria-label') || el.textContent || '')
                    .find(value => /review|đánh giá/i.test(value)) || null;
                  const rating = [...document.querySelectorAll('[role="img"]')]
                    .map(el => el.getAttribute('aria-label') || '')
                    .find(value => /star|sao/i.test(value)) || null;
                  return {
                    name: text('h1'),
                    address: aria('button[data-item-id="address"]'),
                    phone: aria('button[data-item-id^="phone:tel:"]'),
                    website: href('a[data-item-id="authority"]'),
                    category: text('button[jsaction*="pane.rating.category"]'),
                    rating,
                    reviews,
                    hours: aria('div[aria-label*="Giờ mở cửa"], div[aria-label*="Hours"]'),
                    description: text('[data-section-id="editorial_summary"]'),
                    image: document.querySelector('meta[property="og:image"]')?.content || null
                  };
                }"""
            )
            final_url = page.url
            source_url = final_url
            coordinates = self.coordinates_from_url(final_url)
            if coordinates is None:
                coordinates = await self._coordinates_from_page(page)
            if coordinates is None:
                coordinates, final_url = await self._coordinates_via_directions(
                    page,
                    fallback_url=final_url,
                )
        finally:
            await page.close()
        name = self._clean(payload.get("name"))
        if not name or coordinates is None:
            return None
        provider_id = self.provider_id_from_url(final_url)
        category = self._clean(payload.get("category")) or place_type_hint
        return PlaceProviderCandidate(
            provider=self.provider_name,
            providerId=provider_id,
            name=name,
            address=self._strip_label(payload.get("address")),
            coordinates=coordinates,
            admIds=[input_adm.adm_id],
            admNames=[input_adm.name],
            canonicalType=self._canonical_type(category, place_type_hint),
            tags=[category] if category else [],
            rating=self._first_number(payload.get("rating")),
            reviewCount=self._first_integer(payload.get("reviews")),
            dataConfidence=0.68,
            fetchedAt=datetime.now(UTC),
            verificationStatus="not_verified",
            sourceUrl=source_url,
            providerMetadata={
                key: value
                for key, value in {
                    "category": category,
                    "phone": self._strip_label(payload.get("phone")),
                    "website": payload.get("website"),
                    "weekly_opening_hours": payload.get("hours"),
                    "description": payload.get("description"),
                    "image": payload.get("image"),
                }.items()
                if value
            },
        )

    @staticmethod
    async def _reject_blocked_page(page) -> None:
        title = (await page.title()).casefold()
        body = (await page.locator("body").inner_text()).casefold()
        if "unusual traffic" in body or "captcha" in title or "sorry" in page.url:
            raise PlaceSearchProviderError("Google Maps blocked the browser request")

    @staticmethod
    async def _coordinates_from_page(page) -> Coordinates | None:
        pair = await page.evaluate(
            """() => {
              const counts = new Map();
              const seen = new Set();
              const walk = (value, depth = 0) => {
                if (value == null || depth > 18 || typeof value !== 'object' || seen.has(value)) return;
                seen.add(value);
                if (Array.isArray(value)) {
                  for (let i = 0; i + 1 < value.length; i += 1) {
                    const lat = value[i], lng = value[i + 1];
                    if (typeof lat === 'number' && typeof lng === 'number'
                        && Math.abs(lat) > 1 && Math.abs(lat) <= 90
                        && Math.abs(lng) > 1 && Math.abs(lng) <= 180
                        && !Number.isInteger(lat) && !Number.isInteger(lng)) {
                      const key = `${lat.toFixed(7)},${lng.toFixed(7)}`;
                      counts.set(key, (counts.get(key) || 0) + 1);
                    }
                  }
                  value.forEach(item => walk(item, depth + 1));
                } else {
                  Object.values(value).forEach(item => walk(item, depth + 1));
                }
              };
              walk(window.APP_INITIALIZATION_STATE);
              const selected = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
              return selected ? selected[0].split(',').map(Number) : null;
            }"""
        )
        if not pair or len(pair) != 2:
            return None
        return Coordinates(latitude=float(pair[0]), longitude=float(pair[1]))

    @classmethod
    async def _coordinates_via_directions(
        cls,
        page,
        *,
        fallback_url: str,
    ) -> tuple[Coordinates | None, str]:
        # The label renders before Maps finishes binding its navigation action.
        await page.wait_for_timeout(2_000)
        buttons = page.get_by_role("button", name="Đường đi", exact=True)
        if await buttons.count() == 0:
            buttons = page.get_by_role("button", name="Directions", exact=True)
        if await buttons.count() == 0:
            buttons = page.get_by_text("Đường đi", exact=True)
        if await buttons.count() == 0:
            return None, fallback_url
        await buttons.first.click()
        await page.wait_for_timeout(1_500)
        return cls.coordinates_from_url(page.url), page.url

    @staticmethod
    def coordinates_from_url(url: str) -> Coordinates | None:
        destination = re.search(
            r"!1d(-?\d+(?:\.\d+)?).*?!2d(-?\d+(?:\.\d+)?)", url
        )
        if destination is not None:
            return Coordinates(
                latitude=float(destination.group(2)),
                longitude=float(destination.group(1)),
            )
        match = re.search(r"/@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)", url)
        if match is None:
            match = re.search(r"!3d(-?\d+(?:\.\d+)?).*?!4d(-?\d+(?:\.\d+)?)", url)
        if match is None:
            return None
        return Coordinates(latitude=float(match.group(1)), longitude=float(match.group(2)))

    @staticmethod
    def provider_id_from_url(url: str) -> str:
        match = re.search(r"!1s([^!]+)", url)
        raw = match.group(1) if match else url.split("?", 1)[0]
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def _canonical_type(category: str | None, hint: str | None) -> str:
        value = f"{category or ''} {hint or ''}".casefold()
        if any(token in value for token in ("hotel", "hostel", "khách sạn")):
            return "accommodation"
        if any(token in value for token in ("restaurant", "nhà hàng", "quán ăn")):
            return "restaurant"
        if any(token in value for token in ("cafe", "coffee", "cà phê")):
            return "drink_dessert"
        return "travel_place"

    @staticmethod
    def _strip_label(value: object) -> str | None:
        text = GoogleMapsPlaywrightSearch._clean(value)
        return text.split(":", 1)[-1].strip() if text else None

    @staticmethod
    def _clean(value: object) -> str | None:
        text = str(value).strip() if value is not None else ""
        return text or None

    @staticmethod
    def _first_number(value: object) -> float | None:
        match = re.search(r"\d+(?:[.,]\d+)?", str(value or ""))
        return float(match.group(0).replace(",", ".")) if match else None

    @staticmethod
    def _first_integer(value: object) -> int | None:
        digits = re.sub(r"\D", "", str(value or ""))
        return int(digits) if digits else None
