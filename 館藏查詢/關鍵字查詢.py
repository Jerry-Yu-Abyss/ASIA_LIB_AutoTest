"""
爬蟲目標：https://aulib.asia.edu.tw/webpac/search.cfm
功能：逐一點擊 #hot_keyword 下的熱門關鍵字，並取得搜尋結果中的
      第 1、5、10 筆書名。三筆皆成功取得才算通過。

需求套件：pip install selenium webdriver-manager
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

TARGET_URL = "https://aulib.asia.edu.tw/webpac/search.cfm"
RESULT_TITLE_SELECTOR = "#list .list_box .title ul li:last-child a"
REQUIRED_POSITIONS = (1, 5, 10)


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


def check_hot_keywords(driver: webdriver.Chrome) -> bool:
    """
    逐一點擊熱門關鍵字，確認頁面成功跳轉，並從搜尋結果中取得
    第 1、5、10 筆書名。所有關鍵字都成功才回傳 True。
    """
    print("\n" + "=" * 55)
    print("  熱門關鍵字搜尋結果測試")
    print("=" * 55)

    try:
        WebDriverWait(driver, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, "#hot_keyword li > a")) > 0
        )
        keyword_names = [
            anchor.text.strip() or anchor.get_attribute("title") or "（無文字）"
            for anchor in driver.find_elements(By.CSS_SELECTOR, "#hot_keyword li > a")
        ]
        total = len(keyword_names)
        print(f"[+] 共找到 {total} 個熱門關鍵字")

        report = []

        for idx, keyword in enumerate(keyword_names, start=1):
            print(f"\n[{idx:02d}/{total:02d}] 測試關鍵字：{keyword}")
            result = {
                "keyword": keyword,
                "success": False,
                "url": "",
                "books": {},
                "reason": "",
            }

            try:
                # 每次回到首頁重新取得元素，避免上一頁的 WebElement 失效。
                driver.get(TARGET_URL)
                WebDriverWait(driver, 15).until(
                    lambda d: len(
                        d.find_elements(By.CSS_SELECTOR, "#hot_keyword li > a")
                    ) >= idx
                )
                anchor = driver.find_elements(
                    By.CSS_SELECTOR, "#hot_keyword li > a"
                )[idx - 1]
                before_url = driver.current_url

                # 實際點擊關鍵字，不只對 href 發送請求。
                anchor.click()
                WebDriverWait(driver, 20).until(
                    lambda d: d.current_url != before_url
                )
                result["url"] = driver.current_url
                print(f"  [+] 已跳轉：{result['url']}")

                if is_service_unavailable(driver):
                    raise RuntimeError("搜尋結果頁回傳 Service Unavailable")

                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, "list"))
                )
                title_anchors = driver.find_elements(
                    By.CSS_SELECTOR, RESULT_TITLE_SELECTOR
                )
                print(f"  [+] 搜尋結果共載入 {len(title_anchors)} 筆")

                missing = []
                for position in REQUIRED_POSITIONS:
                    if len(title_anchors) < position:
                        missing.append(f"第 {position} 筆不存在")
                        continue

                    title_anchor = title_anchors[position - 1]
                    book_name = (
                        title_anchor.get_attribute("title")
                        or title_anchor.text
                        or ""
                    ).strip()
                    if not book_name:
                        missing.append(f"第 {position} 筆書名為空")
                        continue

                    result["books"][position] = book_name
                    print(f"      第 {position:>2} 筆：{book_name}")

                if missing:
                    result["reason"] = "；".join(missing)
                    print(f"  [FAIL] 失敗：{result['reason']}")
                else:
                    result["success"] = True
                    print("  [PASS] 點擊成功，且已取得第 1、5、10 筆書名")

            except Exception as e:
                result["url"] = driver.current_url
                result["reason"] = str(e) or type(e).__name__
                print(f"  [FAIL] 失敗：{result['reason']}")

            report.append(result)

        success_count = sum(1 for item in report if item["success"])
        fail_count = total - success_count

        print("\n" + "█" * 55)
        print("  熱門關鍵字簡易測試報告")
        print("█" * 55)
        print(f"  關鍵字總數：{total}")
        print(f"  成功：      {success_count}")
        print(f"  失敗：      {fail_count}")

        for item in report:
            status = "成功" if item["success"] else "失敗"
            print(f"\n  [{status}] {item['keyword']}")
            for position in REQUIRED_POSITIONS:
                name = item["books"].get(position, "（未取得）")
                print(f"         第 {position:>2} 筆：{name}")
            if item["reason"]:
                print(f"         原因：{item['reason']}")
            if item["url"]:
                print(f"         網址：{item['url']}")

        print("\n" + "─" * 55)
        if fail_count == 0:
            print("  [PASS] 全部關鍵字連結成功，且皆取得第 1、5、10 筆書名")
        else:
            print(f"  [FAIL] 測試未完全通過，共 {fail_count} 個關鍵字失敗")
        print("█" * 55)
        return fail_count == 0

    except Exception as e:
        print(f"[!] check_hot_keywords 發生錯誤：{e}")
        return False


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
