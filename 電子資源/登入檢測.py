"""以同一組本機測試帳密登入電子資源，確認會員狀態。"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

from selenium.common.exceptions import NoAlertPresentException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from 圖書館.調用子程式.帳號登入 import (
    DEFAULT_CONFIG, MAX_CAPTCHA_ATTEMPTS, load_config, prompt_captcha, resolve_captcha_mode,
)
from 圖書館.調用子程式.本機驗證碼 import recognize_tesseract, tesseract_command
from 圖書館.調用子程式.查詢共用 import open_page
from 圖書館.調用子程式.網頁載入 import get_with_retries

TARGET_URL = "https://erm.asia.edu.tw/user/login/"
HOST = "erm.asia.edu.tw"
LOGIN_PATH = "/user/login/"
ACCOUNT_SELECTOR = (
    "input[name*='account' i], input[id*='account' i], "
    "input[name*='username' i], input[id*='username' i], "
    "input[name*='userid' i], input[id*='userid' i], "
    "input[placeholder='ID' i]"
)
CAPTCHA_INPUT = (
    "input[name*='captcha' i], input[id*='captcha' i], "
    "input[name*='verify' i], input[id*='verify' i], "
    "input[name*='validate' i], input[id*='validate' i], "
    "input[placeholder*='驗證碼'], input[placeholder*='captcha' i]"
)
CAPTCHA_IMAGE = "img[src*='captcha' i], img[src*='verify' i], img[alt*='驗證碼'], img[alt*='captcha' i]"


def login_form(driver):
    """限制搜尋範圍為含密碼欄位的登入表單，避免填入頁首搜尋框。"""
    password = WebDriverWait(driver, 20).until(
        lambda d: next((e for e in d.find_elements(By.CSS_SELECTOR, "input[type='password']") if e.is_displayed()), False)
    )
    form = password.find_element(By.XPATH, "./ancestor::form[1]")
    candidates = form.find_elements(By.CSS_SELECTOR, ACCOUNT_SELECTOR)
    if not candidates:
        candidates = form.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email']")
    username = next((e for e in candidates if e.is_displayed() and e.is_enabled()), None)
    if username is None:
        raise RuntimeError("電子資源登入頁找不到帳號欄位")
    return form, username, password


def captcha_controls(form):
    fields = form.find_elements(By.CSS_SELECTOR, CAPTCHA_INPUT)
    field = next((e for e in fields if e.is_displayed() and e.is_enabled()), None)
    if field is None:
        return None, None
    images = form.find_elements(By.CSS_SELECTOR, CAPTCHA_IMAGE)
    image = next((e for e in images if e.is_displayed()), None)
    if image is None:
        raise RuntimeError("電子資源頁面有驗證碼欄位，但找不到驗證碼圖片")
    WebDriverWait(form.parent, 15).until(
        lambda _: image.get_property("complete") and image.get_property("naturalWidth") > 0
    )
    return field, image


def authenticated(driver) -> bool:
    url = urlsplit(driver.current_url)
    if url.scheme != "https" or url.hostname != HOST:
        return False
    if any(e.is_displayed() for e in driver.find_elements(
        By.XPATH, "//a[contains(., '登出') or contains(., 'Log out') or contains(., 'Sign out')]"
    )):
        return True
    return url.path.rstrip("/") != LOGIN_PATH.rstrip("/") and not any(
        e.is_displayed() for e in driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    )


def submit_login(driver, config: dict, mode: str, allow_manual_fallback: bool,
                 captcha_prompt: Callable | None = None) -> None:
    captcha_prompt = captcha_prompt or prompt_captcha
    if mode == "manual" and not allow_manual_fallback:
        raise RuntimeError("無人值守模式不可使用手動驗證碼；請改用 Tesseract")
    for attempt in range(1, MAX_CAPTCHA_ATTEMPTS + 1):
        if attempt > 1:
            get_with_retries(driver, TARGET_URL)
        form, username, password = login_form(driver)
        username.clear()
        username.send_keys(config["username"])
        password.clear()
        password.send_keys(config["password"])
        field, image = captcha_controls(form)
        if field is not None:
            if mode == "manual":
                answer = captcha_prompt(image)
            else:
                tesseract_command()
                answers = recognize_tesseract(image.screenshot_as_png)
                answer = next((value for value in answers if value and answers.count(value) >= 2), "")
                if not answer:
                    if attempt < MAX_CAPTCHA_ATTEMPTS:
                        print(f"驗證碼辨識未一致，重新取得圖片（{attempt}/{MAX_CAPTCHA_ATTEMPTS}）。", flush=True)
                        continue
                    if not allow_manual_fallback:
                        raise RuntimeError("驗證碼多次辨識未一致，未送出登入")
                    answer = captcha_prompt(image, "自動辨識未成功，請手動確認驗證碼。")
            if not re.fullmatch(r"[A-Za-z0-9]{3,10}", answer):
                raise RuntimeError("驗證碼格式不正確，未送出登入")
            field.clear()
            field.send_keys(answer)
        buttons = form.find_elements(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        button = next((e for e in buttons if e.is_displayed() and e.is_enabled()), None)
        if button is None:
            raise RuntimeError("電子資源登入表單找不到送出按鈕")
        button.click()
        try:
            WebDriverWait(driver, 20).until(authenticated)
            return
        except TimeoutException:
            try:
                alert = driver.switch_to.alert
                message = alert.text
                alert.accept()
            except NoAlertPresentException:
                message = ""
            if any(word in message for word in ("帳號", "密碼", "password", "account", "鎖定")):
                raise RuntimeError("電子資源登入失敗，請確認帳密或帳號狀態") from None
            if field is None or mode == "manual" or attempt == MAX_CAPTCHA_ATTEMPTS:
                raise RuntimeError("電子資源登入未能確認成功，請檢查網站狀態與驗證碼") from None
    raise RuntimeError("電子資源登入未能確認成功")


def main() -> int:
    parser = argparse.ArgumentParser(description="檢查電子資源系統登入")
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
        driver = open_page(headless=args.headless, target_url=TARGET_URL)
        driver.set_page_load_timeout(args.timeout)
        submit_login(driver, config, mode, not args.non_interactive)
        result["url"] = driver.current_url
        result["success"] = True
    except Exception as exc:
        result["reason"] = str(exc).splitlines()[0] or type(exc).__name__
    finally:
        if driver is not None:
            driver.quit()
        if args.report_json:
            args.report_json.parent.mkdir(parents=True, exist_ok=True)
            args.report_json.write_text(json.dumps([result], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[{'PASS' if result['success'] else 'FAIL'}] 電子資源登入：{result['reason'] or '已確認登入'}", flush=True)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
