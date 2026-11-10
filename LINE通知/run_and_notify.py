"""執行圖書館的四項測試，分三則回報 LINE。"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Event, Timer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LINE_CONFIG = ROOT / "config" / "line.local.json"
REPORT_DIR = ROOT / ".local" / "reports"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
USER_ID_PATTERN = re.compile(r"U[0-9a-f]{32}")
LIMIT = 5000
TAIPEI_TIMEZONE = timezone(timedelta(hours=8))
EMOJI_PATTERN = re.compile(r"[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\ufe0f\u200d\u20e3]")
SUITES = (
    ("館藏查詢", "館藏查詢.py", "https://aulib.asia.edu.tw/webpac/search.cfm"),
    ("網路書店推薦", "網路書店推薦.py", "https://aulib.asia.edu.tw/webpac/recommend_book.cfm"),
    ("我的書房", "我的書房.py", "https://aulib.asia.edu.tw/webpac/shelf_user.cfm"),
    ("新書輪播", "新書輪播.py", "https://aulib.asia.edu.tw/webpac/search.cfm"),
)
SUITE_RUNTIME_LIMITS = {"館藏查詢": 240, "網路書店推薦": 480, "我的書房": 300, "新書輪播": 180}

def load_line_config(path: Path = LINE_CONFIG, *, broadcast: bool = False) -> tuple[str, str | None]:
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
    if not broadcast and (not isinstance(user_id, str) or not USER_ID_PATTERN.fullmatch(user_id.strip())):
        raise RuntimeError("缺少有效的 LINE User ID")
    return token.strip(), None if broadcast else user_id.strip()

def send_line_messages(token: str, user_id: str | None, messages: list[str], *, broadcast: bool = False) -> None:
    messages = [EMOJI_PATTERN.sub("", message) for message in messages]
    if not 1 <= len(messages) <= 5 or any(len(m) > LIMIT for m in messages):
        raise RuntimeError("LINE 訊息超過筆數或長度限制")
    body = {"messages": [{"type": "text", "text": m} for m in messages]}
    if not broadcast:
        if not isinstance(user_id, str) or not USER_ID_PATTERN.fullmatch(user_id):
            raise RuntimeError("缺少有效的 LINE User ID")
        body["to"] = user_id
    request = Request(LINE_BROADCAST_URL if broadcast else LINE_PUSH_URL,
                      data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
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
                 "reason": "未產生完整報告，請查本機紀錄", "url": fallback}]
    cases = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if name == "館藏查詢":
            label = f"{item.get('language', '')} {item.get('word', '')}"
            reason, books = "；".join(item.get("errors") or []), item.get("books", {})
            passed = not reason and all(
                books.get(str(p), {}).get("opened")
                for p in (1, 5, 10))
        elif name == "網路書店推薦":
            label = f"{item.get('language', '')} {item.get('word', '')}"
            reason, books = item.get("error", ""), item.get("books", [])
            passed = not reason and len(books) == 3 and all(b.get("loaded") for b in books)
            if not passed and not reason:
                reason = "；".join(
                    f"第 {book.get('position', '?')} 筆：{book.get('reason') or '推薦按鈕未載入'}"
                    for book in books if not book.get("loaded")
                ) or "推薦書目未完整載入"
        elif name == "我的書房":
            label, passed = "登入與我的書房", bool(item.get("success"))
            reason, books = item.get("reason", ""), []
        else:
            label = f"{item.get('section', '')} {item.get('name', '未知書名')}"
            reason, books, passed = item.get("reason", ""), [], bool(item.get("success"))
        case = {"suite": name, "name": short(label, 65), "passed": passed,
                "reason": short(reason, 120), "url": safe_url(item.get("url"), fallback)}
        if name in ("館藏查詢", "網路書店推薦"):
            case["books"] = []
            for position in (1, 5, 10):
                book = books.get(str(position), {}) if isinstance(books, dict) else next(
                    (b for b in books if b.get("position") == position), {})
                case["books"].append({"position": position,
                                      "name": short(book.get("name"), 45),
                                      "opened": bool(book.get("opened")),
                                      "loaded": bool(book.get("loaded")),
                                      "url": safe_url(book.get("url"), case["url"]),
                                      "reason": short(book.get("reason"), 70)})
        cases.append(case)
    if code != 0 and cases and all(c["passed"] for c in cases):
        cases.append({"suite": name, "name": "程式結束狀態", "passed": False,
                      "reason": "結束碼異常，請查本機紀錄", "url": fallback})
    return cases or normalize(name, None, code, fallback)

def run_suite(suite: tuple[str, str, str], seed: int | None, timeout: int,
              max_runtime: int, stamp: str, headless: bool = False) -> tuple[int, list[dict], Path]:
    name, script, fallback = suite
    stem = f"{stamp}_{Path(script).stem}"
    report = REPORT_DIR / f"{stem}.json"
    log = REPORT_DIR / f"{stem}.log"
    module = f"圖書館.檢測功能.{Path(script).stem}"
    cmd = [sys.executable, "-u", "-m", module,
           "--report-json", str(report), "--non-interactive"]
    if headless:
        cmd.append("--headless")
    if script in ("網路書店推薦.py", "我的書房.py"):
        cmd += ["--captcha-mode", "tesseract", "--timeout", str(timeout)]
    if seed is not None and script in ("館藏查詢.py", "網路書店推薦.py"):
        cmd += ["--seed", str(seed)]
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    connection_error = False
    try:
        with subprocess.Popen(cmd, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", bufsize=1) as process:
            timed_out = Event()
            def stop_on_timeout() -> None:
                if process.poll() is None:
                    timed_out.set()
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       capture_output=True, check=False)
                    if process.poll() is None:
                        process.kill()
            timer = Timer(max_runtime, stop_on_timeout)
            timer.start()
            try:
                with log.open("w", encoding="utf-8") as log_file:
                    for line in process.stdout:
                        if "圖書館網站連線逾時" in line or "ERR_CONNECTION_TIMED_OUT" in line:
                            connection_error = True
                        print(line, end="", flush=True)
                        log_file.write(line)
                        log_file.flush()
                    code = process.wait()
                    if timed_out.is_set():
                        code = 1
                        message = f"[FAIL] 執行超過 {max_runtime} 秒\n"
                        print(message, end="", flush=True)
                        log_file.write(message)
            finally:
                timer.cancel()
    except OSError:
        code = 1
        message = "[FAIL] 無法啟動測試程式\n"
        print(message, end="", flush=True)
        log.write_text(message, encoding="utf-8")
    try:
        data = json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
    except (OSError, ValueError):
        data = None
    cases = normalize(name, data, code, fallback)
    if data is None and connection_error:
        cases[0]["reason"] = "圖書館網站連線逾時，請稍後再試或檢查網路"
    elif data is None and log.exists():
        failures = [line.removeprefix("[FAIL] ").strip() for line in log.read_text(encoding="utf-8").splitlines()
                    if line.startswith("[FAIL] ")]
        if failures:
            cases[0]["reason"] = short(failures[-1], 120)
    return code, cases, log

def detail_message(title: str, cases: list[dict]) -> str:
    if not cases:
        return title + "\n\n無"
    lines = [title]
    suite_counts = {}
    for case in cases:
        suite_counts[case["suite"]] = suite_counts.get(case["suite"], 0) + 1
    current_suite = None
    position_in_suite = 0
    for index, case in enumerate(cases):
        if case["suite"] != current_suite:
            current_suite = case["suite"]
            position_in_suite = 0
            heading = f"【{line_text(current_suite)}】{suite_counts[current_suite]} 筆"
        else:
            heading = ""
        position_in_suite += 1
        entry = [f"{position_in_suite}. {line_text(case['name'])}"]
        if case["reason"]:
            entry.append(f"原因：{line_text(case['reason'])}")
        if case.get("books"):
            for book in case["books"]:
                book_name = line_text(book.get("name") or "未取得")
                if case["suite"] == "館藏查詢":
                    failed_book = not book.get("opened")
                else:
                    failed_book = not book.get("loaded") or bool(book["reason"])
                mark = "未通過" if failed_book else "通過"
                entry.append(f"  [{mark}] 第 {book['position']} 筆｜書名：{book_name}")
                if book["reason"]:
                    entry.append(f"    原因：{line_text(book['reason'])}")
        addition = ([heading] if heading else []) + ["\n".join(entry)]
        if len("\n\n".join(lines + addition)) + 80 > LIMIT:
            lines.append(f"另有 {len(cases)-index} 筆超過 LINE 字數上限；完整資料見本機 .local/reports 的 JSON 報告。")
            break
        lines.extend(addition)
    return "\n\n".join(lines)

def build_messages(runs: list[dict], when: datetime) -> list[str]:
    cases = [case for run in runs for case in run["cases"]]
    failed = [case for case in cases if not case["passed"]]
    passed = [case for case in cases if case["passed"]]
    passed_count = len(passed)
    new_book_passed = [case for case in passed if case["suite"] == "新書輪播"]
    if new_book_passed:
        passed = [case for case in passed if case["suite"] != "新書輪播"]
        passed.append({"suite": "新書輪播", "name": f"{len(new_book_passed)} 筆封面正常（逐筆資料見本機 JSON）",
                       "passed": True, "reason": "", "url": next(s[2] for s in SUITES if s[0] == "新書輪播")})
    failed_suites = [run["name"] for run in runs if run["code"] != 0 or any(not c["passed"] for c in run["cases"])]
    summary = "\n".join([
        "圖書館｜(1/3)測試摘要",
        f"時間：{when.astimezone(TAIPEI_TIMEZONE).strftime('%Y-%m-%d %H:%M')} 台北標準時間",
        f"整體：{len(runs)-len(failed_suites)}/{len(runs)} 項通過",
        "未通過：" + (", ".join(failed_suites) if failed_suites else "無"),
    ])
    return [summary, detail_message(f"未通過明細（2/3）｜{len(failed)} 筆", failed),
            detail_message(f"通過明細（3/3）｜{passed_count} 筆", passed)]

def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="執行圖書館測試並發送三則 LINE 回報")
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--send-test", action="store_true")
    options.add_argument("--no-line", action="store_true")
    parser.add_argument("--line-config", type=Path, default=LINE_CONFIG)
    parser.add_argument("--broadcast", action="store_true", help="將 LINE 回報傳給所有官方帳號好友；預設只傳給設定的 User ID")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-runtime", type=int, help="覆寫每項測試上限秒數；未指定時依項目設定")
    parser.add_argument("--headless", action="store_true", help="背景執行 Chrome；預設顯示瀏覽器")
    parser.add_argument("--only", choices=[suite[0] for suite in SUITES],
                        help="只執行指定測試並回報 LINE；未指定時執行全部四項")
    args = parser.parse_args()
    if args.timeout < 30 or (args.max_runtime is not None and args.max_runtime < args.timeout):
        parser.error("--timeout 至少 30 秒，--max-runtime 不得小於 --timeout")
    if args.send_test and args.only:
        parser.error("--send-test 只測 LINE 連線，不能與 --only 同時使用")
    if args.no_line and args.broadcast:
        parser.error("--no-line 不能與 --broadcast 同時使用")
    try:
        if args.send_test:
            credentials = load_line_config(args.line_config, broadcast=args.broadcast)
            send_line_messages(*credentials, ["亞洲大學圖書館自動測試：LINE 連線測試成功。"], broadcast=args.broadcast)
            print("LINE 測試訊息已群發。" if args.broadcast else "LINE 測試訊息已送出。")
            return 0
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        runs = []
        selected_suites = [suite for suite in SUITES if args.only is None or suite[0] == args.only]
        for suite in selected_suites:
            runtime_limit = args.max_runtime or max(
                SUITE_RUNTIME_LIMITS[suite[0]], 2 * args.timeout + 120 if suite[0] in ("網路書店推薦", "我的書房") else 0
            )
            print(f"正在執行：{suite[0]}（最多 {runtime_limit} 秒）...", flush=True)
            code, cases, log = run_suite(suite, args.seed, args.timeout, runtime_limit, stamp, args.headless)
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
            credentials = load_line_config(args.line_config, broadcast=args.broadcast)
            send_line_messages(*credentials, messages, broadcast=args.broadcast)
            print("LINE 三則測試結果已群發。" if args.broadcast else "LINE 三則測試結果已送出。")
        return int(any(run["code"] != 0 or any(not c["passed"] for c in run["cases"]) for run in runs))
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
