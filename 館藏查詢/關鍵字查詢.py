# 測試成功標準：
# 1. 所有熱門關鍵字皆可被點擊，且點擊後能成功跳轉至搜尋結果頁。
# 2. 每個關鍵字的第 1、5、10 筆搜尋結果都能點開書目詳情頁。
# 3. 三筆書目都能從「索書號(卷期)」欄位取得分類號，才算該關鍵字成功。
# 4. 所有關鍵字均符合上述條件，才算整體成功。

"""
爬蟲目標：https://aulib.asia.edu.tw/webpac/search.cfm
需求套件：pip install selenium webdriver-manager
"""

import re
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

TARGET_URL = "https://aulib.asia.edu.tw/webpac/search.cfm"
RESULT_TITLE_SELECTOR = "#list .list_box .title ul li:last-child a"
REQUIRED_POSITIONS = (1, 5, 10)
CALL_NUMBER_PREFIX = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{0,3}\d+(?:\.[A-Za-z0-9]+)*)")


def get_classification_numbers(driver: webdriver.Chrome) -> list[str]:
    """從書目詳情頁的「索書號(卷期)」欄位取出不重複的分類號。"""
    try:
        tables = WebDriverWait(driver, 20).until(
            lambda d: d.find_elements(
                By.XPATH, "//table[thead/tr/*[normalize-space()='索書號(卷期)']]"
            ) or False
        )
    except TimeoutException as exc:
        raise RuntimeError("書目詳情頁找不到索書號(卷期)欄位") from exc
    numbers = []
    for table in tables:
        headers = [
            (cell.get_attribute("textContent") or "").strip()
            for cell in table.find_elements(By.XPATH, "./thead/tr[1]/*")
        ]
        if "索書號(卷期)" not in headers:
            continue
        number_index = headers.index("索書號(卷期)")
        for row in table.find_elements(By.XPATH, "./tbody/tr"):
            cells = row.find_elements(By.XPATH, "./th|./td")
            if number_index >= len(cells):
                continue
            raw_number = (cells[number_index].get_attribute("textContent") or "").strip()
            match = CALL_NUMBER_PREFIX.search(raw_number)
            if match and match.group(1) not in numbers:
                numbers.append(match.group(1))
    return numbers


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
    逐一點擊熱門關鍵字，再點開第 1、5、10 筆書目並讀取分類號。
    所有關鍵字的三筆書目都成功取得分類號才回傳 True。
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
                result_count = len(driver.find_elements(By.CSS_SELECTOR, RESULT_TITLE_SELECTOR))
                print(f"  [+] 搜尋結果共載入 {result_count} 筆")

                missing = []
                for position in REQUIRED_POSITIONS:
                    if result_count < position:
                        missing.append(f"第 {position} 筆不存在")
                        continue

                    # 詳情頁偶爾載入逾時；失敗時重試一次，再記入報告。
                    for detail_attempt in (1, 2):
                        try:
                            # 返回結果頁後重新定位，避免沿用失效的 WebElement。
                            title_anchor = driver.find_elements(
                                By.CSS_SELECTOR, RESULT_TITLE_SELECTOR
                            )[position - 1]
                            book_name = (
                                title_anchor.get_attribute("title")
                                or title_anchor.text
                                or ""
                            ).strip()
                            if not book_name:
                                raise RuntimeError("書名為空")
                            result["books"][position] = {
                                "name": book_name,
                                "numbers": [],
                            }

                            before_detail_url = driver.current_url
                            title_anchor.click()
                            try:
                                WebDriverWait(driver, 20).until(
                                    lambda d: d.current_url != before_detail_url
                                )
                            except TimeoutException as exc:
                                raise RuntimeError("點擊書目後未跳轉至詳情頁") from exc
                            if is_service_unavailable(driver):
                                raise RuntimeError("書目詳情頁回傳 Service Unavailable")

                            numbers = get_classification_numbers(driver)
                            result["books"][position]["numbers"] = numbers
                            if not numbers:
                                raise RuntimeError("索書號(卷期)欄位沒有分類號")
                            print(
                                f"      第 {position:>2} 筆：{book_name}；"
                                f"分類號：{'、'.join(numbers)}"
                            )
                            break
                        except Exception as e:
                            reason = (
                                "書目詳情頁載入逾時"
                                if isinstance(e, TimeoutException)
                                else str(e).strip() or type(e).__name__
                            )
                            if detail_attempt == 2:
                                missing.append(f"第 {position} 筆：{reason}")
                            else:
                                print(f"      第 {position:>2} 筆重試：{reason}")
                        finally:
                            if driver.current_url != result["url"]:
                                driver.back()
                                WebDriverWait(driver, 20).until(
                                    lambda d: d.current_url == result["url"]
                                    and len(d.find_elements(By.CSS_SELECTOR, RESULT_TITLE_SELECTOR)) > 0
                                )

                if missing:
                    result["reason"] = "；".join(missing)
                    print(f"  [FAIL] 失敗：{result['reason']}")
                else:
                    result["success"] = True
                    print("  [PASS] 三筆書目均已點開並取得分類號")

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
                book = item["books"].get(position)
                if book:
                    print(f"         第 {position:>2} 筆：{book['name']}")
                    print(f"                分類號：{'、'.join(book['numbers']) or '（未取得）'}")
                else:
                    print(f"         第 {position:>2} 筆：未取得")
            if item["reason"]:
                print(f"         原因：{item['reason']}")
            if item["url"]:
                print(f"         網址：{item['url']}")

        print("\n" + "─" * 55)
        if fail_count == 0:
            print("  [PASS] 全部關鍵字的三筆書目均取得分類號")
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
