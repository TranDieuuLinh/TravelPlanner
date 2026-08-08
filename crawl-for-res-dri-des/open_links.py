import csv
import os
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

CSV_PATH = Path(__file__).parent / "data.csv"

# Đường dẫn đến thư mục chứa Profile Chrome trên Windows
# Mặc định: C:\Users\<Username>\AppData\Local\Google\Chrome\User Data
LOCAL_APP_DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
CHROME_USER_DATA_DIR = LOCAL_APP_DATA / "Google" / "Chrome" / "User Data"
# Tên profile: "Default" (Tài khoản chính) hoặc "Profile 1", "Profile 2"...
CHROME_PROFILE_DIR = os.environ.get("CHROME_PROFILE_DIR", "Default")


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

        for idx, row in enumerate(links, 1):
            name = row.get("name", "N/A")
            link = row.get("link")

            if not link:
                print(f"⚠️ Dòng {idx} không có link, bỏ qua.")
                continue

            print(f"[{idx}/{len(links)}] 🌐 Đang mở: {name}")
            print(f"    URL: {link}")

            driver.get(link)

            print("    ⏳ Chờ 5 giây...")
            time.sleep(5)
            print("    ✅ Tiếp theo!\n")

    except Exception as e:
        print(f"❌ Đã xảy ra lỗi: {e}")
    finally:
        print("🏁 Đã mở xong tất cả các link. Đóng trình duyệt...")
        driver.quit()


if __name__ == "__main__":
    main()

