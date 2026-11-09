# 測試成功標準：
# 1. 所有熱門關鍵字皆可被點擊，且點擊後能成功跳轉至搜尋結果頁。
# 2. 略過非印刷品單行本；每個關鍵字第 1、5、10 筆符合條件的書目都能點開詳情頁。
# 3. 三筆書目都能成功開啟詳情頁，才算該關鍵字成功。
# 4. 所有關鍵字均符合上述條件，才算整體成功。

"""
爬蟲目標：https://aulib.asia.edu.tw/webpac/search.cfm
需求套件：pip install selenium webdriver-manager
"""

import argparse
import json
from pathlib import Path
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

if __package__:
    from .網頁載入 import ConnectionTimeout, get_with_retries
else:
    from 網頁載入 import ConnectionTimeout, get_with_retries

TARGET_URL = "https://aulib.asia.edu.tw/webpac/search.cfm"
RESULT_TITLE_SELECTOR = "#list .list_box .title ul li:last-child a"
RESULT_BOX_SELECTOR = "#list .list_box"
REQUIRED_POSITIONS = (1, 5, 10)
PRINT_BOOK_TYPE = "書目-語言資料,印刷品:單行本"
BOOK_TYPE_SELECTOR = ".product_info .product_info_content img[alt]"


def show_more_results(driver: webdriver.Chrome) -> str:
    """把預設每頁 10 筆改成 100 筆，供印刷品篩選使用。"""
    url = urlsplit(driver.current_url)
    params = dict(parse_qsl(url.query, keep_blank_values=True))
    params.update(list_num="100", current_page="1")
    expanded_url = urlunsplit((url.scheme, url.netloc, url.path, urlencode(params), url.fragment))
    get_with_retries(driver, expanded_url)
    if urlsplit(driver.current_url).path.endswith("/error.html"):
        raise RuntimeError("圖書館搜尋結果頁發生錯誤（error.html）")
    WebDriverWait(driver, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, RESULT_TITLE_SELECTOR) or False
    )
    return driver.current_url


def print_book_indices(driver: webdriver.Chrome) -> list[int]:
    """從搜尋結果的書目類型標示挑出印刷品單行本。"""
    indices = []
    for index, box in enumerate(driver.find_elements(By.CSS_SELECTOR, RESULT_BOX_SELECTOR)):
        icons = box.find_elements(By.CSS_SELECTOR, BOOK_TYPE_SELECTOR)
        book_type = (icons[0].get_attribute("alt") or "").strip() if icons else ""
        if book_type == PRINT_BOOK_TYPE:
            indices.append(index)
            if len(indices) == max(REQUIRED_POSITIONS):
                break
        else:
            print(f"      略過搜尋結果第 {index + 1} 筆：{book_type or '未標示書目類型'}")
    return indices


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
    driver.set_page_load_timeout(45)
    try:
        get_with_retries(driver, TARGET_URL)
    except ConnectionTimeout:
        driver.quit()
        raise
    except WebDriverException:
        driver.quit()
        raise RuntimeError("無法開啟圖書館網站，請稍後再試或檢查網路") from None
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


def check_hot_keywords(driver: webdriver.Chrome, report_path: Path | None = None) -> bool:
    """
    逐一點擊熱門關鍵字，再確認第 1、5、10 筆印刷品單行本可開啟詳情頁。
    所有關鍵字的三筆書目都成功開啟詳情頁才回傳 True。
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
                get_with_retries(driver, TARGET_URL)
                WebDriverWait(driver, 15).until(
                    lambda d: len(
                        d.find_elements(By.CSS_SELECTOR, "#hot_keyword li > a")
                    ) >= idx
                )
                anchor = driver.find_elements(
                    By.CSS_SELECTOR, "#hot_keyword li > a"
                )[idx - 1]
                search_url = anchor.get_attribute("href")
                before_url = driver.current_url

                # 實際點擊關鍵字，不只對 href 發送請求。
                anchor.click()
                WebDriverWait(driver, 20).until(
                    lambda d: d.current_url != before_url
                )
                if urlsplit(driver.current_url).path.endswith("/error.html"):
                    print("  [!] 網站回傳錯誤頁，等待 5 秒後重試這個關鍵字一次", flush=True)
                    time.sleep(5)
                    if not search_url or urlsplit(search_url).hostname != "aulib.asia.edu.tw":
                        raise RuntimeError("熱門關鍵字的搜尋網址不正確")
                    get_with_retries(driver, search_url)
                    if urlsplit(driver.current_url).path.endswith("/error.html"):
                        raise RuntimeError("圖書館搜尋結果頁發生錯誤（error.html），重試後仍失敗")
                result["url"] = driver.current_url
                print(f"  [+] 已跳轉：{result['url']}")

                if is_service_unavailable(driver):
                    raise RuntimeError("搜尋結果頁回傳 Service Unavailable")

                try:
                    WebDriverWait(driver, 20).until(
                        EC.presence_of_element_located((By.ID, "list"))
                    )
                except TimeoutException as exc:
                    raise RuntimeError("搜尋結果未在 20 秒內載入") from exc
                result["url"] = show_more_results(driver)
                result_count = len(driver.find_elements(By.CSS_SELECTOR, RESULT_TITLE_SELECTOR))
                print(f"  [+] 搜尋結果共載入 {result_count} 筆")

                eligible_indices = print_book_indices(driver)
                print(f"  [+] 符合印刷品單行本：{len(eligible_indices)} 筆")
                missing = []
                for position in REQUIRED_POSITIONS:
                    if len(eligible_indices) < position:
                        missing.append(f"第 {position} 筆符合條件的印刷品單行本不存在")
                        continue

                    # 詳情頁偶爾載入逾時；失敗時重試一次，再記入報告。
                    for detail_attempt in (1, 2):
                        try:
                            # 返回結果頁後重新定位，避免沿用失效的 WebElement。
                            title_anchor = driver.find_elements(
                                By.CSS_SELECTOR, RESULT_TITLE_SELECTOR
                            )[eligible_indices[position - 1]]
                            book_name = (
                                title_anchor.get_attribute("title")
                                or title_anchor.text
                                or ""
                            ).strip()
                            if not book_name:
                                raise RuntimeError("書名為空")
                            result["books"][position] = {
                                "name": book_name,
                                "opened": False,
                                "url": "",
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
                            if urlsplit(driver.current_url).path != "/webpac/content.cfm":
                                raise RuntimeError("未開啟書目詳情頁")

                            result["books"][position]["url"] = driver.current_url
                            result["books"][position]["opened"] = True
                            print(f"      第 {position:>2} 筆：{book_name}；書目詳情頁已開啟")
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
                    print("  [PASS] 三筆書目均已成功開啟詳情頁")

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
                    print(f"                詳情頁：{'已開啟' if book['opened'] else '未開啟'}")
                else:
                    print(f"         第 {position:>2} 筆：未取得")
            if item["reason"]:
                print(f"         原因：{item['reason']}")
            if item["url"]:
                print(f"         網址：{item['url']}")

        print("\n" + "─" * 55)
        if fail_count == 0:
            print("  [PASS] 全部關鍵字的三筆書目均成功開啟詳情頁")
        else:
            print(f"  [FAIL] 測試未完全通過，共 {fail_count} 個關鍵字失敗")
        print("█" * 55)
        if report_path:
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return total > 0 and fail_count == 0

    except Exception as e:
        print(f"[!] check_hot_keywords 發生錯誤：{e}")
        if report_path:
            report_path.write_text(json.dumps(report if 'report' in locals() else [], ensure_ascii=False, indent=2), encoding="utf-8")
        return False


def main(max_retries: int = 3, retry_interval: int = 10):
    parser = argparse.ArgumentParser(description="熱門關鍵字與書目詳情頁開啟測試")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--non-interactive", action="store_true", help="完成後直接關閉瀏覽器")
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    driver = None
    passed = False
    try:
      for attempt in range(1, max_retries + 1):
        print(f"\n{'='*40}")
        print(f"[+] 第 {attempt}/{max_retries} 次嘗試...")

        if driver is None:
            driver = open_page(headless=args.headless)
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
                print("[FAIL] 圖書館首頁持續回傳 Service Unavailable")
            continue

        print(f"[+] 頁面正常，開始測試...")
        passed = check_hot_keywords(driver, args.report_json)
        break
    except RuntimeError as exc:
      print(f"[FAIL] {exc}")
    finally:
      if not args.headless and not args.non_interactive and driver:
          input("\n[+] 完成，按 Enter 關閉瀏覽器...")
      if driver:
          driver.quit()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
