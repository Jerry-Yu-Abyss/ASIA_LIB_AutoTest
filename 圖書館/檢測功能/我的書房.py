"""登入測試帳號，點擊「我的書房」並確認會員頁成功開啟。"""

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from 圖書館.調用子程式.查詢共用 import TARGET_URL, open_page
from 圖書館.調用子程式.帳號登入 import DEFAULT_CONFIG, load_config, login, resolve_captcha_mode

SHELF_PATH = "/webpac/shelf_user.cfm"
SHELF_LINK = "#shelf_link[href='shelf_user.cfm']"


def check_shelf(driver) -> dict:
    result = {"success": False, "reason": "", "url": TARGET_URL}
    try:
        link = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, SHELF_LINK)))
        link.click()
        WebDriverWait(driver, 30).until(
            lambda d: urlsplit(d.current_url).path == SHELF_PATH
            and bool(d.find_elements(By.TAG_NAME, "body"))
        )
        result["url"] = driver.current_url
        WebDriverWait(driver, 15).until(EC.visibility_of_element_located((By.LINK_TEXT, "登出")))
        result["success"] = True
    except Exception as exc:
        result["url"] = driver.current_url
        result["reason"] = (str(exc).splitlines()[0] or "我的書房未能開啟或登入狀態未確認")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="登入後檢查我的書房會員頁")
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
    driver = None
    result = {"success": False, "reason": "", "url": TARGET_URL}
    try:
        config = load_config(args.config)
        mode = resolve_captcha_mode(config, args.captcha_mode)
        driver = open_page(headless=args.headless)
        driver.set_page_load_timeout(args.timeout)
        login(driver, TARGET_URL, config, mode, allow_manual_fallback=not args.non_interactive)
        result = check_shelf(driver)
    except Exception as exc:
        result["reason"] = str(exc).splitlines()[0] or type(exc).__name__
    finally:
        if driver is not None:
            driver.quit()
        if args.report_json:
            args.report_json.write_text(json.dumps([result], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{'PASS' if result['success'] else 'FAIL'}] 我的書房登入檢測：{result['reason'] or '登入後已開啟我的書房'}", flush=True)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
