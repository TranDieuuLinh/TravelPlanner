from __future__ import annotations

import csv
import json
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


CSV_PATH = Path(__file__).parent / "accomation.csv"
OUTPUT_CSV_PATH = Path(__file__).parent / "data_crawled.csv"
BATCH_SIZE = 100
CRAWL_WORKERS = max(1, int(os.environ.get("CRAWL_WORKERS", "1")))
WAIT_SECONDS = 5
PAGE_DELAY_SECONDS = 0.5
LIST_DELAY_SECONDS = 2

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


def process_accommodation(driver: webdriver.Chrome, link: str) -> dict[str, Any]:
    """Open an accommodation listing and read its available booking sources."""

    result: dict[str, Any] = {"source_count": 0, "sources": "[]"}
    print(f"        [OPEN] {link[:120]}")
    driver.get(link)
    time.sleep(PAGE_DELAY_SECONDS)

    wait = WebDriverWait(driver, WAIT_SECONDS)

    try:
        source_button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, ".J8zHNe.NlVald.MkHJW")
            )
        )
        driver.execute_script("arguments[0].click();", source_button)
        time.sleep(LIST_DELAY_SECONDS)
        print("        [LIST] Booking/source panel opened")

        container = wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.m6QErb.XiKgde > div.m6QErb.DxyBCb.kA9KIf.dS8AEf.XiKgde.ecceSd",
                )
            )
        )
        links = container.find_elements(By.CSS_SELECTOR, "a")
        print(f"        Source panel contains {len(links)} link(s)")
        sources: list[dict[str, str]] = []
        skipped = 0
        seen: set[tuple[str, str, str]] = set()
        for link_element in links:
            try:
                name_element = link_element.find_element(By.CSS_SELECTOR, ".Maztge .US7LHc")
                image = link_element.find_element(By.CSS_SELECTOR, "img")
                price_element = link_element.find_element(By.CSS_SELECTOR, ".r1iqBd div")
                name = name_element.text.strip()
                price = price_element.text.strip()
                icon = get_image_url(image)
                href = link_element.get_attribute("href") or ""
            except Exception:
                # Not every anchor in the panel is a booking source.
                skipped += 1
                continue

            key = (href, name, price)
            if key in seen or not (name or price or icon):
                skipped += 1
                continue
            seen.add(key)
            sources.append({"icon": icon, "name": name, "price": price})

        result["source_count"] = len(sources)
        result["sources"] = json.dumps(sources, ensure_ascii=False)
        print(
            f"        [RESULT] extracted={len(sources)}, skipped={skipped} "
            "(saved as JSON in sources column)"
        )
    except Exception as error:
        print(f"        [ERROR] Source list error: {error}")

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
                processed.append({**row, **process_accommodation(driver, link)})
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
    print(f"[SAVE] {len(rows)} row(s), {len(fieldnames)} column(s) -> {OUTPUT_CSV_PATH.name}")


def load_saved_results() -> list[dict[str, Any]]:
    """Load previously saved rows so interrupted crawls can resume."""

    if not OUTPUT_CSV_PATH.exists():
        return []

    with OUTPUT_CSV_PATH.open(mode="r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def main(test_mode: bool = False, fresh: bool = False) -> None:
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
        # Accept regular UTF-8 and CSV files exported with a UTF-8 BOM.
        with CSV_PATH.open(mode="r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))

        if not rows:
            print(f"No rows found in {CSV_PATH.name}")
            return
        if "id" not in rows[0] or not any(
            (row.get("link") or row.get("source_url") or "").strip()
            for row in rows
        ):
            print("CSV must contain an id column and at least one link/source_url value")
            return

        saved_results = [] if fresh else load_saved_results()
        if fresh:
            print("Fresh mode: ignoring existing crawl output")
        saved_ids = {str(row.get("id", "")).strip() for row in saved_results}
        if saved_ids:
            rows = [row for row in rows if row.get("id", "").strip() not in saved_ids]
            print(f"Resume mode: skipping {len(saved_ids)} saved row(s)")

        if test_mode:
            rows = [
                row
                for row in rows
                if (row.get("link") or row.get("source_url") or "").strip()
            ][:2]
            print("Test mode: first 2 links")

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
                    processed.append({**row, **process_accommodation(driver, link)})
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
            print(
                f"- {result.get('name', 'N/A')} "
                f"({result.get('source_count', 0)} source item(s))"
            )
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crawl accommodation listings")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Crawl only the first 2 links for a quick validation",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Ignore data_crawled.csv and crawl every input row again",
    )
    args = parser.parse_args()
    main(test_mode=args.test, fresh=args.fresh)
