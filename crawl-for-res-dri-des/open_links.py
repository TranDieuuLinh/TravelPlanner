from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from typing import Any

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


CSV_PATH = Path(__file__).parent / "data.csv"
OUTPUT_CSV_PATH = Path(__file__).parent / "data_crawled.csv"
BATCH_SIZE = 100
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


def create_driver() -> webdriver.Chrome:
    """Create Chrome using the configured local user profile."""

    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--lang=en-US")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(f"--user-data-dir={CHROME_USER_DATA_DIR}")
    options.add_argument(f"--profile-directory={CHROME_PROFILE_DIR}")
    return webdriver.Chrome(options=options)


def save_results(rows: list[dict[str, Any]]) -> None:
    """Persist all processed rows so a later batch can resume safely."""

    if not rows:
        return

    fieldnames: list[str] = []
    for row in rows:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)

    with OUTPUT_CSV_PATH.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} row(s) to {OUTPUT_CSV_PATH.name}")


def main() -> None:
    if not CSV_PATH.exists():
        print(f"CSV file not found: {CSV_PATH}")
        return

    try:
        driver = create_driver()
    except Exception as error:
        print(f"Could not open Chrome profile: {error}")
        print("Close all Chrome windows and run the script again.")
        return

    try:
        with CSV_PATH.open(mode="r", encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))

        print(f"Found {len(rows)} link(s) in data.csv")
        results: list[dict[str, Any]] = []

        for index, row in enumerate(rows, start=1):
            link = row.get("link", "").strip()
            if not link:
                print(f"[{index}/{len(rows)}] Missing link; skipped")
                continue

            place_id = row.get("id", "")
            name = row.get("name", "N/A")
            print(f"[{index}/{len(rows)}] Opening {name} (ID: {place_id})")

            data = process_drink_dessert(driver, link)
            results.append({**row, **data})

            if len(results) % BATCH_SIZE == 0:
                save_results(results)

        save_results(results)

        print("\nCrawl summary:")
        for result in results:
            images = result["menu_images"]
            preview = f"{images[:100]}..." if images else "No menu image"
            print(f"- {result['name']} (price: {result['price']}): {preview}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
