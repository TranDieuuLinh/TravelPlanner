import csv
import os
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

CSV_PATH = Path(__file__).parent / "data.csv"

# Đường dẫn đến thư mục chứa Profile Chrome trên Windows
LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
CHROME_USER_DATA_DIR = LOCAL_APP_DATA / "Google" / "Chrome" / "User Data"
CHROME_PROFILE_DIR = os.environ.get("CHROME_PROFILE_DIR", "Default")


def process_drink_dessert(driver: webdriver.Chrome, link: str) -> dict:
    """Xử lý địa điểm drink_dessert theo quy trình:
    1. Mở link, chờ 0.5s.
    2. Lấy giá tại class="mgr77e" (nếu không có thì trả về -1), chờ 0.5s.
    3. Nhấn tab aria-label="Menu" (hoặc "Thực đơn"), lấy toàn bộ link ảnh trong class="fp2VUc"
       (nối nhau bằng dấu &). Nếu lỗi thì để trống, chờ 0.5s.
    4. Chờ 0.5s trước khi chuyển sang link tiếp theo.
    """
    result = {
        "price": -1,
        "menu_images": "",
    }

    # 1. Mở link và chờ 0.5s
    driver.get(link)
    time.sleep(0.5)

    wait_short = WebDriverWait(driver, 5)

    # 2. Lấy giá từ class="mgr77e"
    print("    🔍 [Step 1] Lấy giá cả (class='mgr77e')...")
    try:
        price_el = wait_short.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".mgr77e"))
        )
        val = price_el.text.strip()
        result["price"] = val if val else -1
        print(f"        -> Giá: {result['price']}")
    except Exception:
        result["price"] = -1
        print("        -> Giá: -1 (không tìm thấy)")
    time.sleep(0.5)

    # 3. Lấy ảnh Menu
    print("    🔍 [Step 2] Chuyển qua Tab Menu & lấy ảnh (class='fp2VUc')...")
    try:
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
        print(f"        -> Tìm thấy {len(img_urls)} ảnh menu")
    except Exception as e:
        result["menu_images"] = ""
        print(f"        -> Lỗi lấy Menu: {e}")
    time.sleep(0.5)

    # Chờ thêm 0.5s trước khi qua link tiếp theo
    time.sleep(0.5)
    return result


def main() -> None:
    options = Options()
    options.add_argument("--start-maximized")
    options.add_argument("--lang=en-US")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # 🔑 Thêm cấu hình Profile thật
    options.add_argument(f"--user-data-dir={CHROME_USER_DATA_DIR}")
    options.add_argument(f"--profile-directory={CHROME_PROFILE_DIR}")

    print(f"👤 Đang load Profile Chrome: {CHROME_PROFILE_DIR}")
    print("⚠️  LƯU Ý QUAN TRỌNG: Bạn cần ĐÓNG TẤT CẢ cửa sổ Chrome đang chạy trên máy trước khi bắt đầu.\n")

    try:
        driver = webdriver.Chrome(options=options)
    except Exception as err:
        print(f"\n❌ Không thể mở Chrome Profile thật: {err}")
        print("💡 NGUYÊN NHÂN: Chrome đang được mở bởi ứng dụng khác (hoặc đang chạy ngầm).")
        print("👉 GIẢI PHÁP: Tắt toàn bộ cửa sổ Chrome đang mở trên máy rồi chạy lại lệnh.")
        return

    try:
        if not CSV_PATH.exists():
            print(f"❌ Không tìm thấy file CSV tại {CSV_PATH}")
            return

        with open(CSV_PATH, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            links = list(reader)

        print(f"📋 Tìm thấy {len(links)} link trong file data.csv\n")

        results = []
        for idx, row in enumerate(links, 1):
            place_id = row.get("id", "")
            name = row.get("name", "N/A")
            link = row.get("link")

            if not link:
                print(f"⚠️ Dòng {idx} không có link, bỏ qua.")
                continue

            print(f"[{idx}/{len(links)}] 🌐 Đang mở: {name} (ID: {place_id})")
            print(f"    URL: {link}")

            data = process_drink_dessert(driver, link)
            results.append({"id": place_id, "name": name, **data})

            print("    ✅ Tiếp theo!\n")

        print("📊 TỔNG KẾT KẾT QUẢ CRAWL:")
        for r in results:
            print(f"  • {r['name']} (Giá: {r['price']}): {r['menu_images'][:100]}..." if r['menu_images'] else f"  • {r['name']} (Giá: {r['price']}): (Không có ảnh menu)")

    except Exception as e:
        print(f"❌ Đã xảy ra lỗi: {e}")
    finally:
        print("\n🏁 Đã xử lý xong tất cả các link. Đóng trình duyệt...")
        driver.quit()


if __name__ == "__main__":
    main()
