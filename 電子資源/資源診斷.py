"""以既有帳號登入電子資源，尋找指定題名並保留瀏覽器連線診斷。"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import threading
import traceback
from urllib.parse import urlsplit, urlunsplit

from selenium.common.exceptions import StaleElementReferenceException

from 圖書館.調用子程式.帳號登入 import DEFAULT_CONFIG, load_config, resolve_captcha_mode
from 圖書館.調用子程式.查詢共用 import open_page
from 電子資源.登入檢測 import TARGET_URL, authenticated, submit_login
from 電子資源.列表檢測 import (CATEGORY_PATHS, PER_PAGE, check_connection, identity,
                            item_at, open_category, prepare, read_total, select_controls,
                            visible_resources, go_to_page)


ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / ".local" / "reports"
MAX_NETWORK_EVENTS = 2000


def safe_url(raw: str) -> str:
    """保留網址與路徑，但不把登入參數、票證或片段寫入報告。"""
    try:
        parts = urlsplit(raw)
        if not parts.scheme or not parts.netloc:
            return raw[:250].split("?", 1)[0].split("#", 1)[0]
        host = parts.hostname or ""
        authority = host + (f":{parts.port}" if parts.port else "")
        return urlunsplit((parts.scheme, authority, parts.path, "", ""))
    except ValueError:
        return "[無法解析的網址]"


def safe_message(message: str, secrets: tuple[str, ...] = (), limit: int = 1200) -> str:
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[已遮蔽]")
    return re.sub(r"https?://[^\s\"'<>]+", lambda m: safe_url(m.group()), message)[:limit]


def matching_title(title: str, query: str) -> bool:
    normalize = lambda value: " ".join(value.casefold().split())
    return normalize(query) in normalize(title)


def classify_outcome(outcome: dict) -> dict:
    """登入頁可能回 HTTP 200，不能算成書籍平台連線成功。"""
    result = dict(outcome)
    path = urlsplit(result.get("connection_url", "")).path.rstrip("/").casefold()
    if path in ("/login", "/user/login", "/signin", "/sign-in"):
        result.update(success=False, status="重新導向至登入頁")
    return result


def network_entry(event: dict) -> dict | None:
    """擷取文件請求、回應、跳轉與失敗；不儲存 Cookie、標頭或本文。"""
    method = event.get("method", "")
    params = event.get("params", {})
    request = params.get("request") or {}
    response = params.get("response") or {}
    redirect = params.get("redirectResponse") or {}
    if method == "Network.requestWillBeSent":
        if params.get("type") != "Document" and not redirect:
            return None
        item = {"event": "request", "request_id": params.get("requestId"),
                "url": safe_url(request.get("url", "")), "method": request.get("method")}
        if redirect:
            location = next((value for key, value in redirect.get("headers", {}).items()
                             if key.casefold() == "location"), "")
            item["redirect_from"] = safe_url(redirect.get("url", ""))
            item["redirect_status"] = redirect.get("status")
            item["redirect_location"] = safe_url(location)
        return item
    if method == "Network.responseReceived" and (params.get("type") == "Document"
                                                   or response.get("status", 0) >= 400):
        return {"event": "response", "request_id": params.get("requestId"),
                "url": safe_url(response.get("url", "")), "status": response.get("status"),
                "status_text": response.get("statusText", ""), "mime_type": response.get("mimeType", ""),
                "resource_type": params.get("type", "")}
    if method == "Network.loadingFailed":
        return {"event": "failed", "request_id": params.get("requestId"),
                "error": params.get("errorText", ""), "blocked_reason": params.get("blockedReason", "")}
    return None


class Diagnostic:
    def __init__(self, category: str, query: str, max_pages: int, on_event):
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        self.path = REPORT_DIR / f"電子資源診斷_{datetime.now():%Y%m%d_%H%M%S_%f}.json"
        self.on_event = on_event
        self._requests = {}
        self.data = {"category": category, "query": query, "max_pages": max_pages,
                     "started_at": datetime.now().isoformat(timespec="seconds"),
                     "stages": [], "network": [], "network_dropped": 0, "browser_errors": [],
                     "candidates": [], "selection": None, "outcome": None,
                     "error": None, "error_detail": None}
        self.save()

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def stage(self, name: str, **info):
        detail = {"time": datetime.now().isoformat(timespec="seconds"), "stage": name, **info}
        self.data["stages"].append(detail)
        self.save()
        self.on_event("log", f"{name}：{json.dumps(info, ensure_ascii=False)}" if info else name)

    def capture(self, driver, stage: str):
        try:
            raw = driver.get_log("performance")
            for item in raw:
                try:
                    event = json.loads(item["message"])["message"]
                    if event.get("method") == "Network.requestWillBeSent":
                        params = event.get("params", {})
                        self._requests[params.get("requestId")] = safe_url(
                            params.get("request", {}).get("url", ""))
                    parsed = network_entry(event)
                except (ValueError, KeyError, TypeError):
                    continue
                if parsed:
                    if parsed["event"] == "failed":
                        parsed["url"] = self._requests.get(parsed["request_id"], "")
                    if len(self.data["network"]) < MAX_NETWORK_EVENTS:
                        self.data["network"].append({"stage": stage, **parsed})
                        if parsed["event"] in ("failed", "response") or parsed.get("redirect_status"):
                            self.on_event("log", f"網路 {parsed['event']}：{json.dumps(parsed, ensure_ascii=False)}")
                    else:
                        self.data["network_dropped"] += 1
            for item in driver.get_log("browser"):
                if item.get("level") == "SEVERE":
                    self.data["browser_errors"].append({"stage": stage,
                        "message": safe_message(item.get("message", ""))})
            self.save()
        except Exception as exc:
            self.stage("網路紀錄讀取失敗", reason=safe_message(str(exc)))


def find_candidates(driver, category: str, query: str, max_pages: int,
                    diagnostic: Diagnostic, stop: threading.Event) -> list[dict]:
    open_category(driver, category)
    select_controls(driver)
    diagnostic.stage("列表已設定", url=safe_url(driver.current_url), total=read_total(driver),
                     page_size=PER_PAGE)
    diagnostic.capture(driver, "列表")
    found = []
    for page in range(1, max_pages + 1):
        if stop.is_set():
            raise RuntimeError("操作已取消")
        if page > 1:
            go_to_page(driver, page)
        resources = visible_resources(driver)
        if not resources:
            raise RuntimeError(f"第 {page} 頁沒有可見的列表連結")
        for index in range(len(resources)):
            try:
                link = resources[index]
                title, key = identity(link)
                if matching_title(title, query):
                    found.append({"category": category, "position": (page - 1) * PER_PAGE + index + 1,
                                  "title": title, "href": safe_url(link.get_attribute("href") or ""),
                                  "key": key})
            except StaleElementReferenceException:
                raise RuntimeError(f"第 {page} 頁列表在搜尋期間更新，請重新搜尋") from None
        diagnostic.stage("搜尋頁面", page=page, scanned=len(resources), matches=len(found))
        diagnostic.capture(driver, f"搜尋第 {page} 頁")
        total = read_total(driver)
        if len(resources) < PER_PAGE or (total is not None and page * PER_PAGE >= total):
            break
    return sorted(found, key=lambda item: (" ".join(item["title"].casefold().split()) !=
                                           " ".join(query.casefold().split()), item["position"]))


def inspect_choice(driver, candidate: dict, diagnostic: Diagnostic) -> dict:
    category = candidate["category"]
    position = candidate["position"]
    prepare(driver, category, position)
    link, title, key = item_at(driver, position)
    if key != candidate["key"]:
        raise RuntimeError("列表在定位期間變動，已停止以免分析錯誤資源")
    diagnostic.stage("已定位資源", category=category, position=position,
                     title=title, href=candidate["href"])
    diagnostic.capture(driver, "點擊前")
    outcome = classify_outcome(check_connection(driver, link, title))
    diagnostic.capture(driver, "點擊後")
    return {"title": title, "position": position, "source_url": candidate["href"],
            **outcome}


def run(category: str, query: str, max_pages: int, captcha_mode: str | None,
        prompt, choose, on_event, stop: threading.Event,
        config_path: Path = DEFAULT_CONFIG) -> Path:
    if category not in CATEGORY_PATHS or not query.strip() or not 1 <= max_pages <= 30:
        raise ValueError("請指定資源類型、題名與 1～30 頁搜尋範圍")
    diagnostic = Diagnostic(category, query.strip(), max_pages, on_event)
    driver = None
    secrets = ()
    try:
        config = load_config(config_path)
        secrets = (config["username"], config["password"])
        mode = resolve_captcha_mode(config, captcha_mode)
        diagnostic.stage("開始登入", url=TARGET_URL, captcha_mode=mode)
        driver = open_page(target_url=TARGET_URL, capture_network=True)
        driver.set_page_load_timeout(45)
        diagnostic.capture(driver, "登入頁")
        submit_login(driver, config, mode, True, captcha_prompt=prompt)
        if not authenticated(driver):
            raise RuntimeError("無法確認電子資源登入狀態")
        diagnostic.stage("登入成功", url=safe_url(driver.current_url))
        diagnostic.capture(driver, "登入")
        candidates = find_candidates(driver, category, query.strip(), max_pages, diagnostic, stop)
        diagnostic.data["candidates"] = candidates
        diagnostic.save()
        on_event("candidates", candidates)
        if not candidates:
            diagnostic.stage("未找到題名", query=query.strip(), pages=max_pages)
            return diagnostic.path
        index = choose(candidates)
        if stop.is_set() or index is None:
            diagnostic.stage("未選擇資源")
            return diagnostic.path
        if not 0 <= index < len(candidates):
            raise RuntimeError("選擇的資源項目不在結果清單內")
        diagnostic.data["selection"] = candidates[index]
        diagnostic.save()
        outcome = inspect_choice(driver, candidates[index], diagnostic)
        diagnostic.data["outcome"] = outcome
        diagnostic.stage("連線分析完成", **outcome)
        return diagnostic.path
    except Exception as exc:
        diagnostic.data["error"] = safe_message(str(exc).splitlines()[0] or type(exc).__name__, secrets)
        diagnostic.data["error_detail"] = safe_message(traceback.format_exc(), secrets, limit=12000)
        diagnostic.stage("分析失敗", reason=diagnostic.data["error"],
                         error_type=type(exc).__name__,
                         url=safe_url(driver.current_url) if driver is not None else TARGET_URL)
        return diagnostic.path
    finally:
        if driver is not None:
            diagnostic.capture(driver, "結束")
            try:
                driver.quit()
            except Exception as exc:
                diagnostic.stage("瀏覽器結束失敗", reason=safe_message(str(exc), secrets))
        diagnostic.data["finished_at"] = datetime.now().isoformat(timespec="seconds")
        diagnostic.save()
