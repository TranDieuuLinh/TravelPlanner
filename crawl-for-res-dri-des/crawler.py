"""Selenium crawler for Google Maps places.

Reads place entries from `data.csv` and dispatches to a per-category scrape
function based on the `id` prefix. Each function returns a structured dict
so the same dispatcher can persist results regardless of category.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any, Callable

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CSV_PATH = Path("data.csv")

# Selenium waits (seconds)
SHORT_WAIT = 5
LONG_WAIT = 15

# Place categories supported by this crawler. The id prefix in `data.csv`
# determines which scraper is invoked.
CATEGORY_DRINK_DESSERT = "drink_dessert"
CATEGORY_RESTAURANT = "restaurant"


# ---------------------------------------------------------------------------
# Driver bootstrap
# ---------------------------------------------------------------------------


def build_driver(headless: bool = True) -> WebDriver:
    """Create a Chrome WebDriver.

    Selenium Manager (bundled with Selenium >= 4.6) downloads and caches a
    ChromeDriver that matches the installed Chrome, so no manual path is
    required.
    """

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--lang=vi")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )

    return webdriver.Chrome(options=options)


# ---------------------------------------------------------------------------
# Scrapers
# ---------------------------------------------------------------------------


def scrape_drink_dessert(driver: WebDriver, link: str, place_id: str) -> dict[str, Any]:
    """Scrape a drink / dessert place (Café Giảng, etc.).

    Steps:
      1. Open the link and wait 0.5s.
      2. Read price from `class="mgr77e"` (default -1 if missing).
      3. Switch to the "Menu" tab (`aria-label="Menu"` or `"Thực đơn"`) and collect
         every image found inside `class="fp2VUc"`. Multiple URLs are joined with `&`.
    Each step pauses ~0.5s; another 0.5s is added before returning so the next
    link in the dispatcher starts on a quiet page.
    """

    result: dict[str, Any] = {
        "id": place_id,
        "category": CATEGORY_DRINK_DESSERT,
        "link": link,
        "price": -1,
        "menu_images": "",
    }

    # 1. Open link and wait 0.5s
    driver.get(link)
    time.sleep(0.5)

    # Wait helper with short timeout so SPA has time to render
    wait_short = WebDriverWait(driver, 5)

    # 2. Lấy giá từ class="mgr77e"
    try:
        price_el = wait_short.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".mgr77e"))
        )
        val = price_el.text.strip()
        result["price"] = val if val else -1
    except Exception:
        result["price"] = -1
    time.sleep(0.5)

    # 3. Lấy ảnh Menu
    try:
        # Hỗ trợ cả giao diện Tiếng Anh ("Menu") và Tiếng Việt ("Thực đơn")
        menu_selector = (
            '[role="tab"][aria-label="Menu"], '
            '[role="tab"][aria-label="Thực đơn"], '
            '[role="tab"][aria-label*="Menu"], '
            '[role="tab"][aria-label*="Thực đơn"]'
        )
        menu_tab = wait_short.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, menu_selector))
        )
        menu_tab.click()
        time.sleep(0.5)

        # Tìm class="fp2VUc" và lấy tất cả link ảnh
        gallery = wait_short.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".fp2VUc"))
        )
        img_elements = gallery.find_elements(By.TAG_NAME, "img")
        img_urls = [
            img.get_attribute("src") or img.get_attribute("data-src")
            for img in img_elements
        ]
        img_urls = [url for url in img_urls if url and not url.startswith("data:image/svg")]
        result["menu_images"] = "&".join(img_urls)
    except Exception:
        result["menu_images"] = ""
    time.sleep(0.5)

    return result



def scrape_restaurant(driver: WebDriver, link: str, place_id: str) -> dict[str, Any]:
    """Scrape a restaurant (Bún Chả Hương Liên, etc.).

    Same boilerplate as the drink/dessert scraper but the layout is different
    (menu block, price range, popular dishes), so the selectors diverge.
    """

    driver.get(link)
    wait = WebDriverWait(driver, LONG_WAIT)

    # TODO: wait for the restaurant panel. Restaurants tend to render the menu
    # block sooner than the reviews block, so anchor on a menu-related element.
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1")))

    result: dict[str, Any] = {
        "id": place_id,
        "category": CATEGORY_RESTAURANT,
        "link": link,
        "name": None,
        "rating": None,
        "review_count": None,
        "address": None,
        "opening_hours": None,
        "price_range": None,
        "popular_dishes": [],
    }

    # TODO: pull each field with restaurant-specific selectors.

    time.sleep(2)
    return result


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

# Registry keyed by the id prefix in `data.csv`. Each scraper has the same
# signature: (driver, link, place_id) -> dict.
SCRAPER_REGISTRY: dict[str, Callable[[WebDriver, str, str], dict[str, Any]]] = {
    CATEGORY_DRINK_DESSERT: scrape_drink_dessert,
    CATEGORY_RESTAURANT: scrape_restaurant,
}


def route_for(place_id: str) -> Callable[[WebDriver, str, str], dict[str, Any]] | None:
    """Return the scraper matching the `id` prefix, or None if unsupported."""

    for prefix, scraper in SCRAPER_REGISTRY.items():
        if place_id.startswith(f"{prefix}_"):
            return scraper
    return None


def load_rows(csv_path: Path = CSV_PATH) -> list[dict[str, str]]:
    """Load place entries from the CSV file."""

    with csv_path.open(newline="", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def crawl(
    csv_path: Path = CSV_PATH,
    headless: bool = True,
    only_category: str | None = None,
    only_id: str | None = None,
) -> list[dict[str, Any]]:
    """Read the CSV, dispatch each row to the right scraper, return results."""

    rows = load_rows(csv_path)

    if only_id is not None:
        rows = [r for r in rows if r["id"] == only_id]
    elif only_category is not None:
        rows = [r for r in rows if r["id"].startswith(f"{only_category}_")]

    driver = build_driver(headless=headless)
    results: list[dict[str, Any]] = []

    try:
        for row in rows:
            place_id = row["id"]
            link = row["link"]
            scraper = route_for(place_id)

            if scraper is None:
                print(f"[skip] no scraper registered for id={place_id!r}")
                continue

            print(f"[scrape] {place_id} via {scraper.__name__}")
            try:
                results.append(scraper(driver, link, place_id))
            except Exception as exc:  # noqa: BLE001
                print(f"[error] {place_id}: {exc}")
                results.append({
                    "id": place_id,
                    "category": place_id.split("_", 1)[0],
                    "link": link,
                    "error": str(exc),
                })
    finally:
        driver.quit()

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl Google Maps places from data.csv")
    parser.add_argument(
        "--only",
        choices=[CATEGORY_DRINK_DESSERT, CATEGORY_RESTAURANT],
        help="Only scrape rows matching this category prefix.",
    )
    parser.add_argument(
        "--id",
        dest="place_id",
        help="Only scrape the row whose id exactly matches this value.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run Chrome with a visible window (useful for debugging selectors).",
    )
    args = parser.parse_args()

    data = crawl(
        csv_path=CSV_PATH,
        headless=not args.headed,
        only_category=args.only,
        only_id=args.place_id,
    )
    print(f"\nScraped {len(data)} rows")
    for row in data:
        print(row)
