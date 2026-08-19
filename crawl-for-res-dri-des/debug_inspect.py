import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

url = "https://www.google.com/maps/search/?api=1&query=Cafe+Gi%E1%BA%A3ng&query_place_id=ChIJ6VTf4g2pNTERmHDntrvBhLY"

options = Options()
# options.add_argument("--headless=new")
options.add_argument("--lang=vi")
driver = webdriver.Chrome(options=options)

try:
    driver.get(url)
    time.sleep(4)

    print("--- Searching for Price (.mgr77e or similar) ---")
    elements = driver.find_elements(By.CSS_SELECTOR, ".mgr77e")
    print(f"Found .mgr77e count: {len(elements)}")
    for e in elements:
        print("  .mgr77e text:", repr(e.text))

    if not elements:
        # Search for price text containing ₫ or $ or range
        spans = driver.find_elements(By.TAG_NAME, "span")
        for s in spans:
            txt = s.text.strip()
            if "₫" in txt or "$" in txt:
                print("  Span with price:", repr(txt), "class:", repr(s.get_attribute("class")))

    print("\n--- Searching for Tabs (Menu / Thực đơn) ---")
    tabs = driver.find_elements(By.XPATH, "//*[@role='tab'] | //button")
    for t in tabs:
        aria = t.get_attribute("aria-label") or ""
        txt = t.text.strip()
        if "menu" in aria.lower() or "thực đơn" in aria.lower() or "menu" in txt.lower() or "thực đơn" in txt.lower():
            print(f"  Found tab: tag={t.tag_name}, text={repr(txt)}, aria-label={repr(aria)}, class={repr(t.get_attribute('class'))}")

    # Let's also check all buttons/tabs in top panel
    buttons = driver.find_elements(By.CSS_SELECTOR, "button")
    print("\n--- All Buttons with aria-label ---")
    for b in buttons:
        aria = b.get_attribute("aria-label")
        if aria:
            print("  Button aria-label:", repr(aria))

finally:
    driver.quit()
