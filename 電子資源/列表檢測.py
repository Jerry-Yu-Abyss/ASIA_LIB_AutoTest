"""四個電子資源列表各測接續的五筆資源連線，並記錄下次起點。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from selenium.common.exceptions import TimeoutException
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
INTRO_XPATH = ("//a[normalize-space()='簡介' or normalize-space()='Introduction' or @title='簡介'] | "
               "//button[normalize-space()='簡介' or normalize-space()='Introduction' or @title='簡介']")
NAV_ALIASES = {"資料庫": "Databases", "電子期刊": "E-Journals",
               "電子書": "E-Books", "網路資源": "Website"}
ACTION_NAMES = ("簡介", "Introduction", "問題通報", "期刊指標", "收藏", "Report", "Favorite")
ACCESS_NAMES = ("連線", "進入", "使用", "全文", "開啟", "前往", "Access", "Full Text", "Visit", "Go to")
ERROR_TITLES = ("無法連上", "無法存取", "找不到網頁", "This site can’t be reached",
                "This site can't be reached", "Access Denied", "Forbidden", "Not Found",
                "Service Unavailable", "Bad Gateway")


def same_site(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname == HOST and not parts.username


def controls(driver):
    for row in driver.find_elements(By.CSS_SELECTOR, CONTROL_ROW):
        selects = row.find_elements(By.TAG_NAME, "select")
        sort = next((element for element in selects if element.find_elements(
            By.CSS_SELECTOR, f"option[value='{SORT_VALUE}']")), None)
        size = next((element for element in selects if element.find_elements(
            By.CSS_SELECTOR, f"option[value='{PER_PAGE}']")), None)
        if sort is not None and size is not None:
            return row, sort, size
    return None


def open_category(driver, name: str) -> None:
    items = driver.find_elements(By.CSS_SELECTOR, ".nav-item")
    label = f".//a[normalize-space()='{name}' or normalize-space()='{NAV_ALIASES[name]}']"
    nav = next((item for item in items if item.find_elements(
        By.XPATH, label)), None)
    if nav is None:
        raise RuntimeError(f"導覽列找不到{name}")
    heading = nav.find_element(By.XPATH, label)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", heading)
    heading.click()
    try:
        WebDriverWait(driver, 8).until(lambda d: controls(d))
    except TimeoutException:
        # 有些主選單先展開子選單，題名瀏覽才會進入完整清單。
        submenu = nav.find_elements(By.XPATH,
            ".//a[normalize-space()='題名瀏覽' or normalize-space()='瀏覽題名' or normalize-space()='Browse Title']")
        if not submenu:
            raise RuntimeError(f"{name} 選單沒有進入結果列表") from None
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", submenu[0])
        submenu[0].click()
        WebDriverWait(driver, 20).until(lambda d: controls(d))
    if not same_site(driver.current_url):
        raise RuntimeError(f"{name} 清單跳至非預期網站")


def select_controls(driver) -> None:
    row, sort, size = WebDriverWait(driver, 20).until(lambda d: controls(d))
    if Select(sort).first_selected_option.get_attribute("value") != SORT_VALUE:
        Select(sort).select_by_value(SORT_VALUE)
        WebDriverWait(driver, 20).until(lambda d: controls(d) and controls(d)[1].get_attribute("value") == SORT_VALUE)
    row, sort, size = WebDriverWait(driver, 20).until(lambda d: controls(d))
    if Select(size).first_selected_option.get_attribute("value") != str(PER_PAGE):
        Select(size).select_by_value(str(PER_PAGE))
        WebDriverWait(driver, 20).until(lambda d: controls(d) and controls(d)[2].get_attribute("value") == str(PER_PAGE))
    row, _, _ = WebDriverWait(driver, 20).until(lambda d: controls(d))
    choose_list_view(driver, row)
    total = result_total(driver)
    WebDriverWait(driver, 20).until(lambda d: len(visible_intros(d)) == min(read_total(d) or total, PER_PAGE))
    row, sort, size = controls(driver)
    if sort.get_attribute("value") != SORT_VALUE or size.get_attribute("value") != str(PER_PAGE):
        raise RuntimeError("切換列表後排序或每頁顯示設定未保留")
    validate_page(driver)


def choose_list_view(driver, row) -> None:
    """網站用 label[for=bookInfo-list] 切換列表，對應的 radio 表示選取狀態。"""
    selector = 'label.btn.btn-outline-accessory.btn-sm[for="bookInfo-list"]'
    labels = [element for element in row.find_elements(By.CSS_SELECTOR, selector) if element.is_displayed()]
    if not labels:
        labels = [element for element in driver.find_elements(By.CSS_SELECTOR, selector) if element.is_displayed()]
    if len(labels) != 1:
        raise RuntimeError("找不到唯一的「列表」檢視標籤")
    selected = driver.find_element(By.ID, "bookInfo-list")
    if not selected.is_selected():
        labels[0].click()
    try:
        WebDriverWait(driver, 10).until(lambda d: d.find_element(By.ID, "bookInfo-list").is_selected())
    except TimeoutException:
        raise RuntimeError("列表檢視未成功啟用") from None


def visible_intros(driver) -> list:
    return [element for element in driver.find_elements(By.XPATH, INTRO_XPATH) if element.is_displayed()]


def read_total(driver) -> int | None:
    content = driver.find_element(By.TAG_NAME, "body").text
    match = re.search(r"(?:查詢結果|Search Results|Results?)\s*[:：]?\s*([\d,]+)\s*(?:筆|records?)",
                      content, flags=re.IGNORECASE)
    return int(match[1].replace(",", "")) if match else None


def result_total(driver) -> int:
    total = read_total(driver)
    if total is None:
        raise RuntimeError("無法讀取清單總筆數，已停止以免使用過期結果")
    return total


def resource_row(intro):
    """由簡介向外找同一筆結果，不假設網站使用 li/card 標籤。"""
    node = intro
    relative_intros = INTRO_XPATH.replace("//", ".//")
    for _ in range(10):
        node = node.find_element(By.XPATH, "..")
        if len([element for element in node.find_elements(By.XPATH, relative_intros)
                if element.is_displayed()]) != 1:
            continue
        headings = [element for element in node.find_elements(By.CSS_SELECTOR, "h2, h3, h4, h5, .title")
                    if element.is_displayed() and element.text.strip()]
        links = [element for element in node.find_elements(By.CSS_SELECTOR, "a[href]")
                 if element.is_displayed() and element.text.strip()
                 and not any(element.text.strip().casefold() == action.casefold() for action in ACTION_NAMES)]
        if headings or links:
            return node
    raise RuntimeError("無法辨識簡介所屬的清單項目，進度未前進")


def identity(intro) -> tuple[str, str]:
    """標題可重複，加入連結／列表整列內容產生檢查點。"""
    row = resource_row(intro)
    title = next((e.text.strip() for e in row.find_elements(By.CSS_SELECTOR, "h2, h3, h4, h5, .title")
                  if e.is_displayed() and e.text.strip()), "")
    title = title or next((e.text.strip() for e in row.find_elements(By.CSS_SELECTOR, "a[href]")
                           if e.is_displayed() and e.text.strip() and
                           not any(e.text.strip().casefold() == action.casefold() for action in ACTION_NAMES)), "")
    identifiers = [intro.get_attribute("data-id"), row.get_attribute("data-id")]
    href = intro.get_attribute("href") or ""
    if same_site(href):
        identifiers.append(href)
    if not any(identifiers):
        for link in row.find_elements(By.CSS_SELECTOR, "a[href]"):
            href = link.get_attribute("href") or ""
            if same_site(href):
                identifiers.append(href)
                break
    stable = next((value for value in identifiers if value), row.text.strip())
    raw = f"{title}\n{stable}"
    if not title or not raw.strip():
        raise RuntimeError("清單項目缺少可辨識的名稱或識別資料")
    return title, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def item_at(driver, position: int) -> tuple[object, str, str]:
    intros = visible_intros(driver)
    index = (position - 1) % PER_PAGE
    if index >= len(intros):
        raise RuntimeError(f"清單找不到第 {position} 筆（目前頁面僅 {len(intros)} 筆）")
    item = intros[index]
    title, key = identity(item)
    return item, title, key


def validate_page(driver) -> None:
    keys = [identity(element)[1] for element in visible_intros(driver)]
    if len(set(keys)) != len(keys):
        raise RuntimeError("清單存在無法區分的重複項目，已停止以免跳筆")


def page_input(driver):
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
    if page == 1:
        return
    before = identity(visible_intros(driver)[0])[1]
    field = page_input(driver)
    field.clear()
    field.send_keys(str(page), Keys.ENTER)
    try:
        WebDriverWait(driver, 20).until(lambda d: visible_intros(d)
            and identity(visible_intros(d)[0])[1] != before
            and read_total(d) is not None
            and len(visible_intros(d)) == min(max(read_total(d) - (page - 1) * PER_PAGE, 0), PER_PAGE))
    except TimeoutException:
        raise RuntimeError(f"無法確認已切換到第 {page} 頁") from None
    field = page_input(driver)
    if field.get_attribute("value") != str(page):
        raise RuntimeError(f"頁碼沒有停在第 {page} 頁")
    validate_page(driver)


def prepare(driver, category: str, position: int) -> None:
    open_category(driver, category)
    select_controls(driver)
    go_to_page(driver, (position - 1) // PER_PAGE + 1)


def configured(driver, page: int) -> bool:
    found = controls(driver)
    if not found or found[1].get_attribute("value") != SORT_VALUE or found[2].get_attribute("value") != str(PER_PAGE):
        return False
    if page > 1 and page_input(driver).get_attribute("value") != str(page):
        return False
    return bool(visible_intros(driver))


def connection_link(scope, title: str, *, detail: bool = False):
    """只選資源名稱／連線入口，避開問題通報、收藏與簡介操作。"""
    links = [e for e in scope.find_elements(By.CSS_SELECTOR, "a[href], button") if e.is_displayed()]
    candidates = []
    for link in links:
        label = " ".join((link.text, link.get_attribute("title") or "",
                          link.get_attribute("aria-label") or "")).strip()
        href = link.get_attribute("href") or ""
        if any(action.casefold() in label.casefold() for action in ACTION_NAMES):
            continue
        if not href and link.tag_name == "a":
            continue
        explicit = any(word.casefold() in label.casefold() for word in ACCESS_NAMES)
        is_title = bool(title and title.casefold() in label.casefold())
        external = urlsplit(href).scheme in ("http", "https") and not same_site(href)
        if explicit or external or (is_title and not detail):
            candidates.append((3 if explicit else 2 if is_title and not detail else 1, link))
    if not candidates:
        return None
    highest = max(rank for rank, _ in candidates)
    best = [link for rank, link in candidates if rank == highest]
    # 詳情頁若同時有多個外站網址，無法確定哪個才是資源入口。
    if detail and len(best) != 1:
        return None
    return best[0]


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


def check_connection(driver, intro, title: str) -> dict:
    origin = driver.current_url
    original_handle = driver.current_window_handle
    handles = set(driver.window_handles)
    row = resource_row(intro)
    link = connection_link(row, title)
    if link is None:
        raise RuntimeError("清單找不到該筆的資源連線入口；進度未前進")
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
        link.click()
        try:
            opened_page(driver, origin, handles)
        except TimeoutException:
            return {"success": False, "status": "點擊連結後未開啟頁面", "connection_url": ""}
        if same_site(driver.current_url):
            main = driver.find_elements(By.TAG_NAME, "main")
            detail = connection_link(main[0] if main else driver, title, detail=True)
            if detail is None:
                return {"success": False, "status": "館內詳情頁找不到資源連線入口", "connection_url": ""}
            before = driver.current_url
            current_handles = set(driver.window_handles)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", detail)
            detail.click()
            try:
                opened_page(driver, before, current_handles)
            except TimeoutException:
                return {"success": False, "status": "連線入口未開啟頁面", "connection_url": ""}
        return connection_result(driver)
    finally:
        for handle in set(driver.window_handles) - handles:
            driver.switch_to.window(handle)
            driver.close()
        driver.switch_to.window(original_handle)
        if driver.current_url != origin:
            driver.get(origin)
            WebDriverWait(driver, 20).until(lambda d: controls(d))


def check_category(driver, category: str, data: dict, output: list[dict], path: Path) -> None:
    record = data["categories"][category]
    last = record["last_completed"]
    start = last + 1
    prepare(driver, category, last if last else start)
    if record["last_key"]:
        _, _, key = item_at(driver, last)
        if key != record["last_key"]:
            raise RuntimeError(f"{category} 第 {last} 筆內容與上次檢查點不同，未往下測試；請在 GUI 檢查進度")
    print(f"{category}：本次從第 {start} 筆開始，最多測試 {PER_RUN} 筆。", flush=True)
    current_page = (last - 1) // PER_PAGE + 1 if last else 1
    for position in range(start, start + PER_RUN):
        page = (position - 1) // PER_PAGE + 1
        if not configured(driver, current_page):
            prepare(driver, category, position)
            current_page = page
        elif page != current_page:
            go_to_page(driver, page)
            current_page = page
        intro, title, key = item_at(driver, position)
        case = {"category": category, "position": position, "name": title,
                "success": False, "reason": "", "status": "未檢查", "connection_url": "",
                "url": driver.current_url}
        try:
            outcome = check_connection(driver, intro, title)
            case.update(outcome)
            case["reason"] = "" if case["success"] else case["status"]
        except Exception as exc:
            case["reason"] = str(exc).splitlines()[0] or "資源連線無法檢查"
        output.append(case)
        print(f"[{'PASS' if case['success'] else 'FAIL'}] {category} 第 {position} 筆｜{title}："
              f"{case['status'] if case['status'] != '未檢查' else case['reason']}"
              f"｜{case['connection_url'] or '未取得目的網址'}", flush=True)
        if case["status"] == "未檢查":
            # 找不到連線入口或無法完成操作時保留該筆；已取得連線失敗狀態則記錄並接續。
            break
        進度.advance(data, category, position, key, path)


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
                    results.append({"category": category, "position": data["categories"][category]["last_completed"] + 1,
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
