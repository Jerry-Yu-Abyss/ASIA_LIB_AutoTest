"""四個電子資源列表各測接續的五筆資源連線，並記錄下次起點。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from selenium.common.exceptions import (ElementClickInterceptedException, StaleElementReferenceException,
                                        TimeoutException, WebDriverException)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait

from 圖書館.調用子程式.帳號登入 import DEFAULT_CONFIG, load_config, resolve_captcha_mode
from 圖書館.調用子程式.查詢共用 import open_page
from 電子資源.登入檢測 import HOST, TARGET_URL, authenticated, submit_login
from 電子資源 import 進度


PER_RUN = 5
PER_PAGE = 100
SORT_VALUE = "-mti.sort,-category"
CONTROL_ROW = ".row.g-2.g-lg-3.align-items-center"
RESOURCE_SELECTOR = "#content-list .link-main"
NAV_ALIASES = {"資料庫": "Databases", "電子期刊": "E-Journals",
               "電子書": "E-Books", "網路資源": "Website"}
CATEGORY_PATHS = {"資料庫": "/er/browse/db/", "電子期刊": "/er/browse/ej/",
                  "電子書": "/er/browse/eb/", "網路資源": "/er/browse/ir/"}
ERROR_TITLES = ("無法連上", "無法存取", "找不到網頁", "This site can’t be reached",
                "This site can't be reached", "Access Denied", "Forbidden", "Not Found",
                "Service Unavailable", "Bad Gateway")


def same_site(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname == HOST and not parts.username


def controls(driver):
    try:
        for row in driver.find_elements(By.CSS_SELECTOR, CONTROL_ROW):
            selects = row.find_elements(By.TAG_NAME, "select")
            sort = next((element for element in selects if element.find_elements(
                By.CSS_SELECTOR, f"option[value='{SORT_VALUE}']")), None)
            size = next((element for element in selects if element.find_elements(
                By.CSS_SELECTOR, f"option[value='{PER_PAGE}']")), None)
            if sort is not None and size is not None:
                return row, sort, size
    except StaleElementReferenceException:
        pass
    return None


def click_fresh(driver, xpath: str, description: str) -> None:
    """重新取得選單元素；固定選單擋住點擊時在該連結上觸發 click。"""
    def attempt(current):
        try:
            links = current.find_elements(By.XPATH, xpath)
            link = next((element for element in links if element.is_displayed()), None)
            if link is None:
                return False
            current.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
            try:
                link.click()
            except ElementClickInterceptedException:
                # 捲動後固定導覽列仍可能把 Selenium 的點擊座標推到畫面外。
                link = current.find_element(By.XPATH, xpath)
                current.execute_script("arguments[0].click();", link)
            return True
        except StaleElementReferenceException:
            return False
    try:
        WebDriverWait(driver, 15).until(attempt)
    except TimeoutException:
        raise RuntimeError(f"無法點擊{description}") from None


def category_ready(driver, name: str) -> bool:
    """分類連結是獨立網址；先確認網址，再讀取當頁的控件。"""
    return (urlsplit(driver.current_url).path.rstrip("/") == CATEGORY_PATHS[name].rstrip("/")
            and bool(controls(driver)))


def open_category(driver, name: str) -> None:
    if category_ready(driver, name):
        return
    nav_item = ("//*[contains(concat(' ', normalize-space(@class), ' '), ' nav-item ') and "
                f".//a[normalize-space()='{name}' or normalize-space()='{NAV_ALIASES[name]}']]")
    nav = nav_item + f"//a[normalize-space()='{name}' or normalize-space()='{NAV_ALIASES[name]}']"
    click_fresh(driver, nav, f"{name}導覽列")
    try:
        WebDriverWait(driver, 12).until(lambda d: category_ready(d, name))
    except TimeoutException:
        # 有些主選單先展開子選單，題名瀏覽才會進入完整清單。
        submenu = (nav_item + "//a[normalize-space()='題名瀏覽' or normalize-space()='瀏覽題名' "
                   "or normalize-space()='Browse Title']")
        if not driver.find_elements(By.XPATH, submenu):
            raise RuntimeError(f"{name} 選單沒有進入結果列表") from None
        click_fresh(driver, submenu, f"{name}題名瀏覽")
        try:
            WebDriverWait(driver, 20).until(lambda d: category_ready(d, name))
        except TimeoutException:
            raise RuntimeError(f"{name} 清單未完成更新") from None
    if not same_site(driver.current_url):
        raise RuntimeError(f"{name} 清單跳至非預期網站")


def set_dropdown(driver, index: int, value: str, description: str) -> None:
    def apply(current):
        try:
            found = controls(current)
            if not found:
                return False
            element = found[index]
            if element.get_attribute("value") == value:
                return True
            Select(element).select_by_value(value)
        except StaleElementReferenceException:
            pass
        return False
    try:
        WebDriverWait(driver, 20).until(apply)
    except TimeoutException:
        raise RuntimeError(f"{description}設定未成功更新") from None


def control_values(driver) -> bool:
    try:
        found = controls(driver)
        return bool(found and found[1].get_attribute("value") == SORT_VALUE
                    and found[2].get_attribute("value") == str(PER_PAGE))
    except StaleElementReferenceException:
        return False


def select_controls(driver) -> int:
    set_dropdown(driver, 1, SORT_VALUE, "排序")
    set_dropdown(driver, 2, str(PER_PAGE), "每頁筆數")
    choose_list_view(driver)
    total = result_total(driver)
    if total > PER_PAGE:
        go_to_page(driver, 1)
    try:
        WebDriverWait(driver, 20).until(
            lambda d: len(visible_resources(d)) == min(read_total(d) or total, PER_PAGE))
    except TimeoutException:
        raise RuntimeError(f"列表連線入口未更新至預期筆數（目前 {len(visible_resources(driver))} 筆）") from None
    try:
        WebDriverWait(driver, 20).until(control_values)
    except TimeoutException:
        raise RuntimeError("切換列表後排序或每頁顯示設定未保留")
    validate_page(driver)
    return total


def choose_list_view(driver) -> None:
    """網站用 label[for=bookInfo-list] 切換列表，對應的 radio 表示選取狀態。"""
    selector = 'label.btn.btn-outline-accessory.btn-sm[for="bookInfo-list"]'
    def attempt(current):
        try:
            found = controls(current)
            if not found:
                return False
            labels = [element for element in found[0].find_elements(By.CSS_SELECTOR, selector)
                      if element.is_displayed()]
            if not labels:
                labels = [element for element in current.find_elements(By.CSS_SELECTOR, selector)
                          if element.is_displayed()]
            if len(labels) != 1:
                return False
            if current.find_element(By.ID, "bookInfo-list").is_selected():
                return True
            labels[0].click()
        except StaleElementReferenceException:
            return False
        return False
    try:
        WebDriverWait(driver, 10).until(attempt)
    except TimeoutException:
        raise RuntimeError("找不到列表檢視標籤或列表檢視未成功啟用") from None


def visible_resources(driver) -> list:
    try:
        return [element for element in driver.find_elements(By.CSS_SELECTOR, RESOURCE_SELECTOR)
                if element.is_displayed()]
    except StaleElementReferenceException:
        return []


def read_total(driver) -> int | None:
    try:
        counts = driver.find_elements(By.ID, "search-count")
        if counts:
            count = counts[0].text.strip().replace(",", "")
            if count.isdigit():
                return int(count)
        content = driver.find_element(By.TAG_NAME, "body").text
    except StaleElementReferenceException:
        return None
    match = re.search(r"(?:查詢結果|Search Results|Results?)\s*[:：]?\s*([\d,]+)\s*(?:筆|records?)",
                      content, flags=re.IGNORECASE)
    return int(match[1].replace(",", "")) if match else None


def result_total(driver) -> int:
    try:
        return WebDriverWait(driver, 20).until(lambda current: read_total(current))
    except TimeoutException:
        if read_total(driver) == 0:
            raise RuntimeError("清單沒有資源可供測試") from None
        raise RuntimeError("無法讀取清單總筆數，已停止以免使用過期結果")


def identity(link) -> tuple[str, str]:
    """用每筆 .link-main 的名稱與識別資料保護下一次的接續位置。"""
    title = (link.text.strip() or link.get_attribute("title") or link.get_attribute("aria-label") or "").strip()
    stable = (link.get_attribute("data-id") or link.get_attribute("data-article-id")
              or link.get_attribute("href") or "").strip()
    if not title or not stable:
        raise RuntimeError("資源連線入口缺少名稱或識別資料，進度未前進")
    raw = f"{title}\n{stable}"
    return title, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def item_at(driver, position: int) -> tuple[object, str, str]:
    index = (position - 1) % PER_PAGE
    def locate(current):
        try:
            resources = visible_resources(current)
            if index >= len(resources):
                return False
            item = resources[index]
            title, key = identity(item)
            return item, title, key
        except StaleElementReferenceException:
            return False
    try:
        return WebDriverWait(driver, 20).until(locate)
    except TimeoutException:
        raise RuntimeError(f"清單找不到穩定的第 {position} 筆") from None


def validate_page(driver) -> None:
    def read_keys(current):
        try:
            resources = visible_resources(current)
            return [identity(element)[1] for element in resources] if resources else False
        except StaleElementReferenceException:
            return False
    try:
        keys = WebDriverWait(driver, 30).until(read_keys)
    except TimeoutException:
        raise RuntimeError("清單持續更新，無法確認項目順序") from None
    if len(set(keys)) != len(keys):
        raise RuntimeError("清單存在無法區分的重複項目，已停止以免跳筆")


def page_input(driver):
    footer = [element for element in driver.find_elements(
        By.CSS_SELECTOR, "#page_footer .change-page input[type='number']") if element.is_displayed()]
    if len(footer) == 1:
        return footer[0]
    inputs = [e for e in driver.find_elements(By.XPATH,
        "//input[@type='number' or @type='text' or @inputmode='numeric' or contains(@aria-label,'頁數')]")
        if e.is_displayed() and (e.get_attribute("value") or "").isdigit()]
    matches = [e for e in inputs if any(token in " ".join((e.get_attribute("aria-label") or "",
               e.get_attribute("title") or "", e.find_element(By.XPATH, "./..").text))
               for token in ("頁", "Page", "page"))]
    if len(matches) == 1:
        return matches[0]
    if len(inputs) == 1:
        return inputs[0]
    raise RuntimeError("找不到唯一的頁數輸入欄位")


def go_to_page(driver, page: int) -> None:
    if page == 1 and result_total(driver) <= PER_PAGE:
        return
    field = page_input(driver)
    if field.get_attribute("value") == str(page):
        return
    before = identity(visible_resources(driver)[0])[1]
    field.clear()
    field.send_keys(str(page), Keys.ENTER)
    try:
        WebDriverWait(driver, 20).until(lambda d: visible_resources(d)
            and identity(visible_resources(d)[0])[1] != before
            and read_total(d) is not None
            and len(visible_resources(d)) == min(max(read_total(d) - (page - 1) * PER_PAGE, 0), PER_PAGE))
    except TimeoutException:
        raise RuntimeError(f"無法確認已切換到第 {page} 頁") from None
    field = page_input(driver)
    if field.get_attribute("value") != str(page):
        raise RuntimeError(f"頁碼沒有停在第 {page} 頁")
    validate_page(driver)


def prepare(driver, category: str, position: int) -> int:
    stage = "進入分類"
    try:
        open_category(driver, category)
        stage = "設定列表"
        total = select_controls(driver)
        if position > total:
            raise RuntimeError(f"第 {position} 筆超出目前 {total} 筆，請檢查進度")
        if position > PER_PAGE:
            stage = "切換頁碼"
            go_to_page(driver, (position - 1) // PER_PAGE + 1)
        return total
    except Exception as exc:
        detail = str(exc).splitlines()[0] or type(exc).__name__
        raise RuntimeError(f"{category}{stage}失敗：{detail}") from exc


def configured(driver, page: int) -> bool:
    try:
        if not control_values(driver):
            return False
        if page > 1 and page_input(driver).get_attribute("value") != str(page):
            return False
        return bool(visible_resources(driver))
    except StaleElementReferenceException:
        return False


def opened_page(driver, origin: str, handles: set[str]) -> bool:
    """回傳是否開了新分頁；同分頁或新分頁都要有可讀的載入結果。"""
    WebDriverWait(driver, 25).until(lambda d: len(d.window_handles) > len(handles) or d.current_url != origin)
    extra = set(driver.window_handles) - handles
    if extra:
        driver.switch_to.window(next(iter(extra)))
    WebDriverWait(driver, 25).until(lambda d: d.current_url.startswith("chrome-error://") or
        d.execute_script("return document.readyState") in ("interactive", "complete"))
    return bool(extra)


def connection_result(driver) -> dict:
    url = driver.current_url
    safe_url = urlsplit(url)._replace(query="", fragment="").geturl()
    if url.startswith(("chrome-error://", "about:blank")):
        return {"success": False, "status": "瀏覽器連線錯誤", "connection_url": safe_url}
    if same_site(url):
        return {"success": False, "status": "連線後仍停留館內網站", "connection_url": safe_url}
    title = driver.title.strip()
    body = driver.find_element(By.TAG_NAME, "body").text.strip()
    try:
        status = driver.execute_script(
            "return performance.getEntriesByType('navigation')[0]?.responseStatus || 0")
    except Exception:
        status = 0
    status = int(status) if isinstance(status, (int, float)) else 0
    if status >= 400:
        return {"success": False, "status": f"HTTP {status}", "connection_url": safe_url}
    if any(error.casefold() in title.casefold() for error in ERROR_TITLES):
        return {"success": False, "status": title[:80], "connection_url": safe_url}
    if not body and status != 200:
        return {"success": False, "status": "目的頁沒有可讀內容", "connection_url": safe_url}
    return {"success": True, "status": f"HTTP {status}" if status else "頁面已載入（HTTP 狀態不可得）",
            "connection_url": safe_url}


def check_connection(driver, link, title: str) -> dict:
    """僅點擊當筆列表的 .link-main，檢查實際開啟的系統平台。"""
    origin = driver.current_url
    original_handle = driver.current_window_handle
    handles = set(driver.window_handles)
    href = link.get_attribute("href") or ""
    target = urlsplit(href)._replace(query="", fragment="").geturl()
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
        try:
            try:
                link.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", link)
        except TimeoutException:
            return {"success": False, "status": "平台連線逾時", "connection_url": target}
        except WebDriverException as exc:
            error = re.search(r"net::(ERR_[A-Z0-9_]+)", str(exc))
            if error:
                return {"success": False, "status": f"瀏覽器連線錯誤：{error[1]}",
                        "connection_url": target}
            raise
        try:
            opened_page(driver, origin, handles)
        except TimeoutException:
            return {"success": False, "status": "點擊平台連結後未開啟頁面", "connection_url": target}
        if same_site(driver.current_url):
            try:
                WebDriverWait(driver, 8).until(lambda current: not same_site(current.current_url))
            except TimeoutException:
                pass
        outcome = connection_result(driver)
        if outcome["connection_url"].startswith("chrome-error://") and target:
            outcome["connection_url"] = target
        return outcome
    finally:
        for handle in set(driver.window_handles) - handles:
            driver.switch_to.window(handle)
            driver.close()
        driver.switch_to.window(original_handle)
        if driver.current_url != origin:
            driver.get(origin)
            WebDriverWait(driver, 20).until(lambda d: controls(d))


def connection_state(status: str, success: bool) -> str:
    if success:
        return "可連線"
    if status in ("HTTP 401", "HTTP 403"):
        return "拒絕存取"
    if status == "HTTP 404":
        return "資源不存在"
    if status == "HTTP 429":
        return "請求受限"
    match = re.fullmatch(r"HTTP (\d{3})", status)
    if match and int(match[1]) >= 500:
        return "平台錯誤"
    return "連線失敗"


def connection_note(status: str, success: bool) -> str:
    """只說明平台連線結果。"""
    if success:
        return "連線成功。" if status.startswith("HTTP ") else "頁面可連線；HTTP 狀態未取得。"
    if status in ("HTTP 401", "HTTP 403"):
        return "平台已回應但拒絕存取；可能需要登入、授權或受到安全機制限制。"
    if status == "HTTP 404":
        return "平台已回應，但目的頁不存在。"
    if status == "HTTP 429":
        return "平台已回應但限制請求頻率；請降低檢測頻率。"
    match = re.fullmatch(r"HTTP (\d{3})", status)
    if match and int(match[1]) >= 500:
        return "平台伺服器回應錯誤。"
    return "平台未能正常開啟。"


def check_category(driver, category: str, data: dict, output: list[dict], path: Path) -> None:
    record = data["categories"][category]
    last = record["last_completed"]
    total = prepare(driver, category, last or 1)
    start = last % total + 1
    if record["last_key"]:
        _, _, key = item_at(driver, last)
        if key != record["last_key"]:
            raise RuntimeError(f"{category} 第 {last} 筆內容與上次檢查點不同，未往下測試；請在 GUI 檢查進度")
    print(f"{category}：本次從第 {start} 筆開始，最多測試 {PER_RUN} 筆。", flush=True)
    current_page = (last - 1) // PER_PAGE + 1 if last else 1
    for offset in range(PER_RUN):
        position = (last + offset) % total + 1
        page = (position - 1) // PER_PAGE + 1
        if not configured(driver, current_page):
            prepare(driver, category, position)
            current_page = page
        elif page != current_page:
            go_to_page(driver, page)
            current_page = page
        link, title, key = item_at(driver, position)
        case = {"category": category, "position": position, "name": title,
                "success": False, "reason": "", "status": "未檢查", "connection_state": "未檢查",
                "connection_note": "", "connection_url": "",
                "url": driver.current_url}
        try:
            outcome = check_connection(driver, link, title)
            case.update(outcome)
            case["connection_state"] = connection_state(case["status"], case["success"])
            case["connection_note"] = connection_note(case["status"], case["success"])
            case["reason"] = "" if case["success"] else case["status"]
        except Exception as exc:
            case["reason"] = str(exc).splitlines()[0] or "資源連線無法檢查"
            case["connection_note"] = f"尚未完成連線檢查：{case['reason']}"
        output.append(case)
        print(f"[{'PASS' if case['success'] else 'FAIL'}] {category} 第 {position} 筆｜{title}："
              f"狀態：{case['connection_state']}（{case['status']}）｜註解：{case['connection_note']}"
              f"｜{case['connection_url'] or '未取得目的網址'}", flush=True)
        if case["status"] == "未檢查":
            # 找不到連線入口或無法完成操作時保留該筆；已取得連線失敗狀態則記錄並接續。
            break
        進度.advance(data, category, position, key, path, total=total)


def main() -> int:
    parser = argparse.ArgumentParser(description="依序檢測四類電子資源各五筆對外連線")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--captcha-mode", choices=("manual", "tesseract"))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    if args.timeout < 30:
        parser.error("--timeout 至少為 30 秒")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    results = []
    driver = None
    try:
        with 進度.exclusive():
            data = 進度.load()
            config = load_config(args.config)
            mode = resolve_captcha_mode(config, args.captcha_mode)
            driver = open_page(headless=args.headless, target_url=TARGET_URL)
            driver.set_page_load_timeout(args.timeout)
            submit_login(driver, config, mode, not args.non_interactive)
            if not authenticated(driver):
                raise RuntimeError("登入狀態未確認，停止列表檢測")
            driver.set_page_load_timeout(min(args.timeout, 30))
            for category in 進度.CATEGORIES:
                try:
                    check_category(driver, category, data, results, 進度.PROGRESS_FILE)
                except Exception as exc:
                    reason = str(exc).splitlines()[0] or type(exc).__name__
                    results.append({"category": category, "position": 進度.next_position(data["categories"][category]),
                                    "name": "清單或進度檢查", "success": False, "reason": reason, "url": TARGET_URL})
                    print(f"[FAIL] {category}：{reason}", flush=True)
    except Exception as exc:
        reason = str(exc).splitlines()[0] or type(exc).__name__
        results.append({"category": "登入或進度", "position": 0, "name": "檢測準備", "success": False,
                        "reason": reason, "url": TARGET_URL})
        print(f"[FAIL] {reason}", flush=True)
    finally:
        if driver is not None:
            driver.quit()
        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if len(results) == len(進度.CATEGORIES) * PER_RUN and all(r["success"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
