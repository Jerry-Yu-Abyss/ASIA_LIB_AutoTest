"""執行館藏查詢的四項測試，分三則回報個人 LINE。"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
LINE_CONFIG = ROOT / "config" / "line.local.json"
REPORT_DIR = ROOT / ".local" / "reports"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
USER_ID_PATTERN = re.compile(r"U[0-9a-f]{32}")
LIMIT = 5000
SUITES = (
    ("熱門關鍵字", "關鍵字查詢.py", "https://aulib.asia.edu.tw/webpac/search.cfm"),
    ("中英文查詢", "中英查詢.py", "https://aulib.asia.edu.tw/webpac/search.cfm"),
    ("網路書店推薦", "網路書店推薦.py", "https://aulib.asia.edu.tw/webpac/recommend_book.cfm"),
    ("新書封面", "新書報報.py", "https://aulib.asia.edu.tw/webpac/search.cfm"),
)

def load_line_config(path: Path = LINE_CONFIG) -> tuple[str, str]:
    settings = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("LINE 設定檔無法讀取") from exc
        if not isinstance(settings, dict):
            raise RuntimeError("LINE 設定檔必須是 JSON 物件")
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or settings.get("channel_access_token")
    user_id = os.environ.get("LINE_USER_ID") or settings.get("user_id")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("缺少 LINE Channel access token")
    if not isinstance(user_id, str) or not USER_ID_PATTERN.fullmatch(user_id.strip()):
        raise RuntimeError("缺少有效的 LINE User ID")
    return token.strip(), user_id.strip()

def send_line_messages(token: str, user_id: str, messages: list[str]) -> None:
    if not 1 <= len(messages) <= 5 or any(len(m) > LIMIT for m in messages):
        raise RuntimeError("LINE 訊息超過筆數或長度限制")
    body = {"to": user_id, "messages": [{"type": "text", "text": m} for m in messages]}
    request = Request(LINE_PUSH_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"LINE API 回傳 HTTP {response.status}")
    except HTTPError as exc:
        raise RuntimeError(f"LINE API 回傳 HTTP {exc.code}；請檢查 token 與訊息額度") from None
    except (URLError, TimeoutError):
        raise RuntimeError("無法連線至 LINE API") from None

def safe_url(value: object, fallback: str) -> str:
    if isinstance(value, str):
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.hostname == "aulib.asia.edu.tw" and not parsed.username:
            return value
    return fallback

def short(value: object, limit: int = 90) -> str:
    value = " ".join(str(value or "").split())
    return value[:limit] + ("…" if len(value) > limit else "")

def line_text(value: object) -> str:
    """避免網站回傳的欄位把網址夾帶進 LINE 文字。"""
    return re.sub(r"https?://\S+", "（網址已省略）", str(value or ""))

def normalize(name: str, data: object, code: int, fallback: str) -> list[dict]:
    if not isinstance(data, list) or not data:
        return [{"suite": name, "name": "執行或資料擷取", "passed": False,
                 "reason": "未產生完整報告，請查本機紀錄", "url": fallback, "classification": "未取得"}]
    cases = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if name == "熱門關鍵字":
            label, passed = item.get("keyword", "未知關鍵字"), bool(item.get("success"))
            reason, books = item.get("reason", ""), item.get("books", {})
        elif name == "中英文查詢":
            label = f"{item.get('language', '')} {item.get('word', '')}"
            reason, books = "；".join(item.get("errors") or []), item.get("books", {})
            passed = not reason and all(
                books.get(str(p), {}).get("classification") not in (None, "查無館藏", "（未取得）")
                for p in (1, 5, 10))
        elif name == "網路書店推薦":
            label = f"{item.get('language', '')} {item.get('word', '')}"
            reason, books = item.get("error", ""), item.get("books", [])
            passed = not reason and len(books) == 3 and all(b.get("loaded") for b in books)
        else:
            label = f"{item.get('section', '')} {item.get('name', '未知書名')}"
            reason, books, passed = item.get("reason", ""), [], bool(item.get("success"))
        case = {"suite": name, "name": short(label, 65), "passed": passed,
                "reason": short(reason, 120), "url": safe_url(item.get("url"), fallback)}
        if name == "新書封面":
            case["classification"] = "不適用（封面測試）"
        else:
            case["books"] = []
            for position in (1, 5, 10):
                book = books.get(str(position), {}) if isinstance(books, dict) else next(
                    (b for b in books if b.get("position") == position), {})
                case["books"].append({"position": position,
                                      "name": short(book.get("name"), 45),
                                      "classification": short(book.get("classification") or "未取得", 40),
                                      "url": safe_url(book.get("url"), case["url"]),
                                      "reason": short(book.get("reason"), 70)})
        cases.append(case)
    if code != 0 and cases and all(c["passed"] for c in cases):
        cases.append({"suite": name, "name": "程式結束狀態", "passed": False,
                      "reason": "結束碼異常，請查本機紀錄", "url": fallback, "classification": "未取得"})
    return cases or normalize(name, None, code, fallback)

def run_suite(suite: tuple[str, str, str], seed: int | None, timeout: int,
              max_runtime: int, stamp: str) -> tuple[int, list[dict], Path]:
    name, script, fallback = suite
    stem = f"{stamp}_{Path(script).stem}"
    report = REPORT_DIR / f"{stem}.json"
    log = REPORT_DIR / f"{stem}.log"
    cmd = [sys.executable, str(ROOT / "館藏查詢" / script), "--headless", "--report-json", str(report)]
    if script == "網路書店推薦.py":
        cmd += ["--captcha-mode", "gemini", "--non-interactive", "--timeout", str(timeout)]
    if seed is not None and script in ("中英查詢.py", "網路書店推薦.py"):
        cmd += ["--seed", str(seed)]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=max_runtime, check=False)
        code, output = result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired as exc:
        code, output = 1, exc.stdout or b""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        output += f"\n[FAIL] 執行超過 {max_runtime} 秒\n"
    except OSError:
        code, output = 1, "[FAIL] 無法啟動測試程式\n"
    log.write_text(output, encoding="utf-8")
    try:
        data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
    except (OSError, ValueError):
        data = None
    return code, normalize(name, data, code, fallback), log

def detail_message(title: str, cases: list[dict]) -> str:
    if not cases:
        return title + "\n無"
    lines = [title]
    for index, case in enumerate(cases):
        entry = [f"【{case['suite']}】{line_text(case['name'])}"]
        if case["reason"]:
            entry.append(f"原因：{line_text(case['reason'])}")
        if case.get("books"):
            for book in case["books"]:
                book_name = f" {line_text(book['name'])}｜" if book.get("name") else " "
                entry.append(f"第{book['position']}筆{book_name}分類號：{line_text(book['classification'])}")
                if book["reason"]:
                    entry.append(f"  {line_text(book['reason'])}")
        else:
            entry.append(f"分類號：{line_text(case['classification'])}")
        if len("\n\n".join(lines + ["\n".join(entry)])) + 80 > LIMIT:
            lines.append(f"另有 {len(cases)-index} 筆超過 LINE 字數上限；完整資料見本機 .local/reports 的 JSON 報告。")
            break
        lines.append("\n".join(entry))
    return "\n\n".join(lines)

def build_messages(runs: list[dict], when: datetime) -> list[str]:
    cases = [case for run in runs for case in run["cases"]]
    failed = [case for case in cases if not case["passed"]]
    passed = [case for case in cases if case["passed"]]
    passed_count = len(passed)
    new_book_passed = [case for case in passed if case["suite"] == "新書封面"]
    if new_book_passed:
        passed = [case for case in passed if case["suite"] != "新書封面"]
        passed.append({"suite": "新書封面", "name": f"{len(new_book_passed)} 筆封面正常（逐筆資料見本機 JSON）",
                       "passed": True, "reason": "", "classification": "不適用（封面測試）",
                       "url": SUITES[3][2]})
    failed_suites = [run["name"] for run in runs if run["code"] != 0 or any(not c["passed"] for c in run["cases"])]
    summary = "\n".join([
        "亞洲大學圖書館｜館藏查詢自動測試摘要",
        f"時間：{when.astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
        f"測試項目：{len(runs)}；未通過：{len(failed_suites)}；通過：{len(runs)-len(failed_suites)}",
        f"資料筆數：未通過 {len(failed)}；通過 {passed_count}",
        "未通過項目：" + ("、".join(failed_suites) if failed_suites else "無"),
    ])
    return [summary, detail_message("館藏查詢｜未通過測試詳細資訊", failed),
            detail_message("館藏查詢｜通過測試詳細資訊", passed)]

def main() -> int:
    parser = argparse.ArgumentParser(description="執行館藏查詢全部測試並發送三則 LINE 回報")
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--send-test", action="store_true")
    options.add_argument("--no-line", action="store_true")
    parser.add_argument("--line-config", type=Path, default=LINE_CONFIG)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-runtime", type=int, default=1800, help="每項測試上限秒數")
    args = parser.parse_args()
    if args.timeout < 30 or args.max_runtime < args.timeout:
        parser.error("--timeout 至少 30 秒，--max-runtime 不得小於 --timeout")
    try:
        credentials = None if args.no_line else load_line_config(args.line_config)
        if args.send_test:
            send_line_messages(*credentials, ["亞洲大學圖書館自動測試：LINE 連線測試成功。"])
            print("LINE 測試訊息已送出。")
            return 0
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        runs = []
        for suite in SUITES:
            print(f"正在執行：{suite[0]}...", flush=True)
            code, cases, log = run_suite(suite, args.seed, args.timeout, args.max_runtime, stamp)
            runs.append({"name": suite[0], "code": code, "cases": cases})
            print(f"{suite[0]}：{'通過' if code == 0 else '失敗'}；紀錄：{log}", flush=True)
        messages = build_messages(runs, datetime.now().astimezone())
        combined = REPORT_DIR / f"{stamp}_完整報告.json"
        combined.write_text(json.dumps(runs, ensure_ascii=False, indent=2), encoding="utf-8")
        for message in messages:
            print("\n" + message)
        print(f"\n完整報告：{combined}")
        if args.no_line:
            print("未發送 LINE（--no-line）。")
        else:
            send_line_messages(*credentials, messages)
            print("LINE 三則測試結果已送出。")
        return int(any(run["code"] != 0 or any(not c["passed"] for c in run["cases"]) for run in runs))
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
