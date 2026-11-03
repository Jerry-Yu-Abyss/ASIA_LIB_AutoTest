"""執行網路書店推薦測試，將精簡結果傳到個人 LINE。"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import json
import os
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
TEST_SCRIPT = ROOT / "館藏查詢" / "網路書店推薦.py"
LINE_CONFIG = ROOT / "config" / "line.local.json"
REPORT_DIR = ROOT / ".local" / "reports"
LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
USER_ID_PATTERN = re.compile(r"U[0-9a-f]{32}")
SUMMARY_PATTERN = re.compile(r"查詢通過：(\d+)/(\d+)；推薦送出：0 筆")


def load_line_config(path: Path = LINE_CONFIG) -> tuple[str, str]:
    """環境變數優先；沒有時才讀取不納入 Git 的本機 JSON。"""
    settings = {}
    if path.exists():
        try:
            settings = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise RuntimeError("LINE 設定檔無法讀取，請參考 config/line.example.json") from exc
        if not isinstance(settings, dict):
            raise RuntimeError("LINE 設定檔必須是 JSON 物件")
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN") or settings.get("channel_access_token")
    user_id = os.environ.get("LINE_USER_ID") or settings.get("user_id")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError("缺少 LINE Channel access token；請填入本機設定檔或環境變數")
    if not isinstance(user_id, str) or not USER_ID_PATTERN.fullmatch(user_id.strip()):
        raise RuntimeError("缺少有效的 LINE User ID；格式應為 U 開頭的 33 個字元")
    return token.strip(), user_id.strip()


def send_line_message(token: str, user_id: str, message: str) -> None:
    """只發送精簡報告，不發送測試日誌、帳密或金鑰。"""
    body = {"to": user_id, "messages": [{"type": "text", "text": message}]}
    request = Request(
        LINE_PUSH_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError(f"LINE API 回傳 HTTP {response.status}")
    except HTTPError as exc:
        raise RuntimeError(f"LINE API 回傳 HTTP {exc.code}；請檢查 token、User ID 與訊息額度") from None
    except (URLError, TimeoutError):
        raise RuntimeError("無法連線至 LINE API，請檢查網路") from None


def run_test(seed: int | None, timeout: int, max_runtime: int) -> tuple[int, str]:
    command = [
        sys.executable, str(TEST_SCRIPT), "--captcha-mode", "gemini",
        "--headless", "--non-interactive", "--timeout", str(timeout),
    ]
    if seed is not None:
        command.extend(("--seed", str(seed)))
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            command, cwd=ROOT, env=environment, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=max_runtime,
            check=False,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        return 1, output + f"\n[FAIL] 總執行時間超過 {max_runtime} 秒\n"
    except OSError:
        return 1, "[FAIL] 無法啟動本機測試程式\n"


def build_summary(exit_code: int, output: str, when: datetime) -> str:
    passed = exit_code == 0
    lines = [
        "亞洲大學圖書館｜網路書店推薦測試",
        f"時間：{when.astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
        f"結果：{'通過' if passed else '失敗'}",
    ]
    match = SUMMARY_PATTERN.search(output)
    if match:
        lines.append(f"查詢通過：{match.group(1)}/{match.group(2)}")
    else:
        # 只從已知錯誤分類產生短訊，不將網站輸出或例外內容送到 LINE。
        if "Gemini" in output and "HTTP 503" in output:
            lines.append("原因：Gemini 暫時無法回應（HTTP 503）")
        elif "Gemini" in output or "驗證碼" in output:
            lines.append("階段：登入／驗證碼")
        elif "總執行時間超過" in output:
            lines.append("階段：執行逾時")
        else:
            lines.append("階段：啟動或登入；詳情請看本機紀錄")
    lines.append("推薦送出：0 筆")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="執行無人值守測試並回報至 LINE")
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--send-test", action="store_true", help="只送一則 LINE 連線測試訊息，不執行網站測試")
    options.add_argument("--no-line", action="store_true", help="執行網站測試但不發 LINE")
    parser.add_argument("--line-config", type=Path, default=LINE_CONFIG)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--timeout", type=int, default=180, help="單次網站查詢上限秒數")
    parser.add_argument("--max-runtime", type=int, default=1800, help="整體測試上限秒數")
    args = parser.parse_args()
    if args.timeout < 30 or args.max_runtime < args.timeout:
        parser.error("--timeout 至少 30 秒，--max-runtime 不得小於 --timeout")

    try:
        credentials = None if args.no_line else load_line_config(args.line_config)
        if args.send_test:
            send_line_message(*credentials, "亞洲大學圖書館自動測試：LINE 連線測試成功。")
            print("LINE 測試訊息已送出；請確認手機是否收到。")
            return 0

        print("正在執行網路書店推薦測試；此模式不會等待人工輸入驗證碼...", flush=True)
        exit_code, output = run_test(args.seed, args.timeout, args.max_runtime)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = REPORT_DIR / f"bookstore_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.log"
        report_path.write_text(output, encoding="utf-8")
        summary = build_summary(exit_code, output, datetime.now().astimezone())
        print(summary)
        print(f"詳細紀錄：{report_path}")
        if args.no_line:
            print("未發送 LINE（--no-line）。")
        else:
            send_line_message(*credentials, summary)
            print("LINE 測試結果已送出；請確認手機是否收到。")
        return 0 if exit_code == 0 else 1
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
