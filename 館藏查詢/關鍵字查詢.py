"""
爬蟲目標：https://aulib.asia.edu.tw/webpac/search.cfm
功能：測試 #hot_keyword 下所有 <li> > <a> 的 href 是否可正常連結

需求套件：pip install selenium webdriver-manager
"""

import time
import urllib.request
import urllib.error
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

TARGET_URL = "https://aulib.asia.edu.tw/webpac/search.cfm"
BASE_URL   = "https://aulib.asia.edu.tw"


def open_page(headless: bool = False) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver  = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    print(f"[+] 正在開啟頁面：{TARGET_URL}")
    driver.get(TARGET_URL)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        print(f"[+] 頁面載入成功！標題：{driver.title}")
    except Exception as e:
        print(f"[!] 等待逾時：{e}")
    return driver


def is_service_unavailable(driver: webdriver.Chrome) -> bool:
    return "Service Unavailable" in driver.page_source


def check_hot_keywords(driver: webdriver.Chrome):
    """
    測試結構：
        #hot_keyword
          └─ <li>        (多筆)
               └─ <a href="...">

    對每個 href 發送 HTTP HEAD 請求，驗證連結是否有效。
    最後輸出報告：應該有 / 成功 / 失敗 / 失敗清單
    """
    print("\n" + "=" * 55)
    print("  🔍  hot_keyword 連結測試")
    print("=" * 55)

    try:
        # 等待 #hot_keyword 出現
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "hot_keyword"))
        )
        hot_keyword = driver.find_element(By.ID, "hot_keyword")
        print(f"[+] 找到 #hot_keyword")

        # 取得所有 li > a
        anchors = hot_keyword.find_elements(By.CSS_SELECTOR, "li > a")
        total   = len(anchors)
        print(f"[+] 共找到 {total} 個 <li> > <a>\n")

        success_count = 0
        fail_list     = []   # (關鍵字文字, href, 失敗原因)

        for idx, anchor in enumerate(anchors, start=1):
            text = anchor.text.strip() or "（無文字）"
            href = anchor.get_attribute("href") or ""

            if not href:
                print(f"  [{idx:02d}] {text:<20} ⚠  無 href")
                fail_list.append((text, "（無 href）", "缺少 href"))
                continue

            # 補全相對路徑
            full_url = href if href.startswith("http") else BASE_URL + href

            # HEAD 請求驗證
            try:
                req = urllib.request.Request(
                    full_url,
                    method="HEAD",
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    status = resp.status
                    if status == 200:
                        print(f"  [{idx:02d}] {text:<20} ✅ {status}  {full_url}")
                        success_count += 1
                    else:
                        print(f"  [{idx:02d}] {text:<20} ❌ {status}  {full_url}")
                        fail_list.append((text, full_url, f"HTTP {status}"))

            except urllib.error.HTTPError as e:
                print(f"  [{idx:02d}] {text:<20} ❌ HTTP {e.code}  {full_url}")
                fail_list.append((text, full_url, f"HTTP {e.code}"))
            except urllib.error.URLError as e:
                print(f"  [{idx:02d}] {text:<20} ❌ 連線失敗  {full_url}")
                fail_list.append((text, full_url, f"連線失敗：{e.reason}"))
            except Exception as e:
                print(f"  [{idx:02d}] {text:<20} ❌ 例外錯誤  {full_url}")
                fail_list.append((text, full_url, str(e)))

        # ── 最終報告 ──
        fail_count = len(fail_list)
        print("\n" + "█" * 55)
        print("  📋  hot_keyword 連結測試報告")
        print("█" * 55)
        print(f"  應該有：{total} 筆")
        print(f"  成功：  {success_count} 筆")
        print(f"  失敗：  {fail_count} 筆")
        if fail_list:
            print(f"\n  失敗的連結：")
            for name, url, reason in fail_list:
                print(f"    • {name}")
                print(f"      原因：{reason}")
                print(f"      網址：{url}")
        else:
            print(f"\n  ✅ 所有連結均可正常存取")
        print("█" * 55)

    except Exception as e:
        print(f"[!] check_hot_keywords 發生錯誤：{e}")


def main(max_retries: int = 10, retry_interval: int = 30):
    driver = None

    for attempt in range(1, max_retries + 1):
        print(f"\n{'='*40}")
        print(f"[+] 第 {attempt}/{max_retries} 次嘗試...")

        if driver is None:
            driver = open_page(headless=False)
        else:
            print(f"[+] 重新整理頁面...")
            driver.refresh()
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                pass

        if is_service_unavailable(driver):
            print(f"[!] 伺服器回傳 Service Unavailable")
            if attempt < max_retries:
                print(f"[+] {retry_interval} 秒後自動重試...")
                time.sleep(retry_interval)
            else:
                print(f"[!] 已達最大重試次數（{max_retries}），放棄。")
            continue

        print(f"[+] 頁面正常，開始測試...")
        check_hot_keywords(driver)
        break

    print("\n[+] 完成，按 Enter 關閉瀏覽器...")
    input()
    if driver:
        driver.quit()
    print("[+] 瀏覽器已關閉。")


if __name__ == "__main__":
    main()