"""單獨重現圖書館登入驗證碼問題，保存每次圖片與辨識／驗證結果。"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from 圖書館.調用子程式.帳號登入 import DEFAULT_CONFIG, load_config, login, resolve_captcha_mode
from 圖書館.調用子程式.查詢共用 import TARGET_URL, open_page

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / ".local" / "captcha_debug"


def main() -> int:
    parser = argparse.ArgumentParser(description="排查測試帳號的登入驗證碼")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--captcha-mode", choices=("manual", "tesseract"))
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--allow-manual-fallback", action="store_true",
                        help="Tesseract 五次失敗後，改由人工輸入最後一張驗證碼")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    run_dir = args.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "驗證碼報告.json"
    report = {"mode": "", "success": False, "reason": "", "events": []}

    def record(event: dict, image: bytes | None) -> None:
        entry = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), **event}
        if image is not None:
            image_path = run_dir / f"驗證碼_{event['attempt']}.png"
            image_path.write_bytes(image)
            entry["image"] = image_path.name
        report["events"].append(entry)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        message = f"第 {event['attempt']} 次｜{event['stage']}"
        if "model" in event:
            message += f"｜{event['model']}: {event.get('answer', event.get('answers', ''))}"
        if "reason" in event:
            message += f"｜{event['reason']}"
        print(message, flush=True)

    driver = None
    try:
        config = load_config(args.config)
        mode = resolve_captcha_mode(config, args.captcha_mode)
        report["mode"] = mode
        driver = open_page(headless=args.headless)
        login(driver, TARGET_URL, config, mode,
              allow_manual_fallback=mode == "manual" or args.allow_manual_fallback,
              diagnostic=record)
        report["success"] = True
        print("[PASS] 驗證碼通過，測試帳號登入成功。", flush=True)
    except Exception as exc:
        report["reason"] = str(exc).splitlines()[0] or type(exc).__name__
        print(f"[FAIL] {report['reason']}", flush=True)
    finally:
        if driver is not None:
            driver.quit()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"排錯報告：{report_path}", flush=True)
    return 0 if report["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
