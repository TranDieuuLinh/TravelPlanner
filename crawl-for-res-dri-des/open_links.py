from __future__ import annotations

import csv
import os
import tempfile
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


CSV_PATH = Path(__file__).parent / "restaurants_and_drink_desserts.csv"
OUTPUT_CSV_PATH = Path(__file__).parent / "data_crawled.csv"
BATCH_SIZE = 100
CRAWL_WORKERS = max(1, int(os.environ.get("CRAWL_WORKERS", "1")))
WAIT_SECONDS = 5
PAGE_DELAY_SECONDS = 0.5
MENU_DELAY_SECONDS = 2

LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
CHROME_USER_DATA_DIR = LOCAL_APP_DATA / "Google" / "Chrome" / "User Data"
CHROME_PROFILE_DIR = os.environ.get("CHROME_PROFILE_DIR", "Default")

MENU_TAB_SELECTOR = (
    '[role="tab"][aria-label="Menu"], '
    '[role="tab"][aria-label="Thực đơn"], '
    '[role="tab"][aria-label*="Menu"], '
    '[role="tab"][aria-label*="Thực đơn"]'
)

# The required menu is the dryRY block inside the fp2VUc panel.
MENU_IMAGE_SELECTOR = (
    '[class*="fp2VUc"] [class*="cRLbXd"] '
    '[class*="dryRY"] > div > button > img'
)


def get_image_url(image: Any) -> str:
    """Return the first available URL attribute from an image element."""

    source = (
        image.get_attribute("src")
        or image.get_attribute("data-src")
        or image.get_attribute("data-lazy-src")
    )
    if source:
        return source

    srcset = image.get_attribute("srcset") or image.get_attribute("data-srcset")
    if srcset:
        return srcset.split(",")[-1].strip().split(" ")[0]
    return ""


def process_drink_dessert(driver: webdriver.Chrome, link: str) -> dict[str, Any]:
    """Read the price and menu image URLs for one Google Maps place."""

    result: dict[str, Any] = {"price": -1, "menu_images": ""}
    driver.get(link)
    time.sleep(PAGE_DELAY_SECONDS)

    wait = WebDriverWait(driver, WAIT_SECONDS)

    try:
        price_element = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".mgr77e"))
        )
        result["price"] = price_element.text.strip() or -1
    except Exception:
        pass

    time.sleep(PAGE_DELAY_SECONDS)

    try:
        menu_tab = wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, MENU_TAB_SELECTOR))
        )
        menu_tab.click()
        time.sleep(MENU_DELAY_SECONDS)

        images = wait.until(
            EC.presence_of_all_elements_located(
                (By.CSS_SELECTOR, MENU_IMAGE_SELECTOR)
            )
        )
        image_urls: list[str] = []
        for image in images:
            url = get_image_url(image)
            if url and url not in image_urls:
                image_urls.append(url)

        result["menu_images"] = "&".join(image_urls)
        print(f"        Found {len(image_urls)} menu image(s)")
    except Exception as error:
        print(f"        Menu image error: {error}")

    time.sleep(PAGE_DELAY_SECONDS * 2)
    return result


def create_driver(
    user_data_dir: Path | None = None,
    headless: bool = False,
) -> webdriver.Chrome:
    """Create Chrome using the configured profile or an isolated worker profile."""

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    else:
        options.add_argument("--start-maximized")
    options.add_argument("--lang=en-US")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"--user-data-dir={user_data_dir or CHROME_USER_DATA_DIR}")
    if user_data_dir is None:
        options.add_argument(f"--profile-directory={CHROME_PROFILE_DIR}")
    return webdriver.Chrome(options=options)


def crawl_chunk(chunk: list[tuple[int, dict[str, str]]]) -> list[dict[str, Any]]:
    """Crawl one batch with one isolated Chrome worker."""

    with tempfile.TemporaryDirectory(prefix="travelplanner-crawl-") as profile:
        driver = create_driver(Path(profile), headless=True)
        try:
            processed: list[dict[str, Any]] = []
            for index, row in chunk:
                link = (row.get("link") or row.get("source_url") or "").strip()
                if not link:
                    continue
                print(f"[{index}] Opening {row.get('name', 'N/A')}")
                processed.append({**row, **process_drink_dessert(driver, link)})
            return processed
        finally:
            driver.quit()


def save_results(rows: list[dict[str, Any]]) -> None:
    """Persist all processed rows so a later batch can resume safely."""

    if not rows:
        return

    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)

    temp_output = OUTPUT_CSV_PATH.with_suffix(".csv.tmp")
    with temp_output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp_output.replace(OUTPUT_CSV_PATH)
    print(f"Saved {len(rows)} row(s) to {OUTPUT_CSV_PATH.name}")


def load_saved_results() -> list[dict[str, Any]]:
    """Load previously saved rows so interrupted crawls can resume."""

    if not OUTPUT_CSV_PATH.exists():
        return []

    with OUTPUT_CSV_PATH.open(mode="r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main(test_mode: bool = False) -> None:
    if not CSV_PATH.exists():
        print(f"CSV file not found: {CSV_PATH}")
        return

    driver: webdriver.Chrome | None = None
    if CRAWL_WORKERS == 1:
        try:
            driver = create_driver()
        except Exception as error:
            print(f"Could not open Chrome profile: {error}")
            print("Close all Chrome windows and run the script again.")
            return

    try:
        with CSV_PATH.open(mode="r", encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))

        saved_results = load_saved_results()
        saved_ids = {str(row.get("id", "")).strip() for row in saved_results}
        if saved_ids:
            rows = [row for row in rows if row.get("id", "").strip() not in saved_ids]
            print(f"Resume mode: skipping {len(saved_ids)} saved row(s)")

        if test_mode:
            test_rows: list[dict[str, str]] = []
            seen_types: set[str] = set()
            for row in rows:
                row_type = row.get("type", "").strip() or row.get("category", "").strip()
                if row_type not in seen_types:
                    seen_types.add(row_type)
                    test_rows.append(row)
            rows = test_rows
            print("Test mode: one row per type")

        print(f"Found {len(rows)} link(s) in {CSV_PATH.name}")
        results: list[dict[str, Any]] = saved_results
        indexed_rows = list(enumerate(rows, start=1))
        chunks = [
            indexed_rows[start : start + BATCH_SIZE]
            for start in range(0, len(indexed_rows), BATCH_SIZE)
        ]

        if CRAWL_WORKERS == 1 and driver is not None:
            for chunk in chunks:
                processed: list[dict[str, Any]] = []
                for index, row in chunk:
                    link = (row.get("link") or row.get("source_url") or "").strip()
                    if not link:
                        continue
                    print(f"[{index}] Opening {row.get('name', 'N/A')}")
                    processed.append({**row, **process_drink_dessert(driver, link)})
                results.extend(processed)
                save_results(results)
        else:
            print(f"Running {CRAWL_WORKERS} Chrome workers in parallel")
            with ThreadPoolExecutor(max_workers=CRAWL_WORKERS) as executor:
                futures = [executor.submit(crawl_chunk, chunk) for chunk in chunks]
                for future in as_completed(futures):
                    results.extend(future.result())
                    save_results(results)

        save_results(results)

        print("\nCrawl summary:")
        for result in results:
            images = result["menu_images"]
            preview = f"{images[:100]}..." if images else "No menu image"
            print(f"- {result['name']} (price: {result['price']}): {preview}")
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl restaurant and drink/dessert places")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Crawl only one row per type for a quick validation",
    )
    args = parser.parse_args()
    main(test_mode=args.test)
