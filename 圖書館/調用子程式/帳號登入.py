"""亞洲大學圖書館測試帳號登入工具。

需要登入的測試才匯入此模組；一般館藏查詢不會讀取帳號設定。
"""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import re
from urllib.parse import urlparse

from selenium.common.exceptions import NoAlertPresentException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

if __package__:
    from .本機驗證碼 import recognize_tesseract, tesseract_command
    from .網頁載入 import get_with_retries
else:
    from 本機驗證碼 import recognize_tesseract, tesseract_command
    from 網頁載入 import get_with_retries

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config" / "測試帳號.local.json"
LIBRARY_DOMAIN = "aulib.asia.edu.tw"
MAX_CAPTCHA_ATTEMPTS = 5


class CaptchaImageTimeout(RuntimeError):
    """驗證碼圖片沒有在時間內變成可截取狀態。"""


def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    """讀取並驗證僅存於本機的測試帳號設定。"""
    try:
        config = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("無法讀取帳號設定，請參考 config/測試帳號.example.json") from exc
    if not isinstance(config, dict) or not all(
        isinstance(config.get(key), str) and config[key].strip()
        for key in ("username", "password")
    ):
        raise RuntimeError("JSON 必須填入 username 與 password")
    if not isinstance(config.get("captcha", {}), dict):
        raise RuntimeError("captcha 必須是 JSON 物件")
    return config


def resolve_captcha_mode(config: dict, override: str | None = None) -> str:
    """舊設定的 gemini 模式直接轉成本機辨識，不再呼叫外部模型。"""
    mode = override or config.get("captcha", {}).get("mode", "tesseract")
    if mode == "gemini":
        mode = "tesseract"
    if mode not in ("manual", "tesseract"):
        raise RuntimeError("captcha.mode 必須是 manual 或 tesseract")
    return mode


def prompt_captcha(image, message: str = "") -> str:
    """顯示目前的驗證碼圖片，讓使用者確認後輸入。"""
    screenshot = ROOT / ".local" / "captcha.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    image.screenshot(str(screenshot))
    if message:
        print(message, flush=True)
    print(f"驗證碼圖片：{screenshot}", flush=True)
    try:
        return input("請依瀏覽器或圖片輸入驗證碼：").strip()
    except EOFError:
        raise RuntimeError("無法從目前終端機輸入驗證碼；請在可互動的終端機執行") from None


def wait_for_captcha_image(driver, timeout: int = 20):
    """驗證碼元素出現不代表圖片可截取；須等到實際尺寸非零。"""
    def ready(current_driver):
        try:
            image = current_driver.find_element(By.CSS_SELECTOR, "#captcha_span img")
            if not image.is_displayed():
                return False
            size = image.size
            if size["width"] <= 0 or size["height"] <= 0:
                return False
            if not image.get_property("complete") or image.get_property("naturalWidth") <= 0:
                return False
            return image
        except StaleElementReferenceException:
            return False

    try:
        return WebDriverWait(driver, timeout).until(ready)
    except TimeoutException:
        raise CaptchaImageTimeout("驗證碼圖片未能載入") from None


def open_login_form(driver, target_url: str, config: dict):
    """開啟登入視窗並填入帳密，回傳目前的驗證碼圖片元素。"""
    driver.switch_to.default_content()
    get_with_retries(driver, target_url)
    driver.find_element(By.LINK_TEXT, "登入").click()
    frame = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='login_iframe.cfm']"))
    )
    if urlparse(frame.get_attribute("src")).netloc != LIBRARY_DOMAIN:
        raise RuntimeError("登入視窗不在預期的圖書館網域")
    driver.switch_to.frame(frame)
    WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.ID, "hidid")))
    driver.find_element(By.ID, "hidid").send_keys(config["username"])
    driver.find_element(By.ID, "password").send_keys(config["password"])
    return wait_for_captcha_image(driver)


def refresh_captcha(driver, image, target_url: str, config: dict):
    """點擊網站的驗證碼換圖；若換圖逾時，重新開啟登入視窗。"""
    try:
        driver.find_element(By.ID, "captcha_span").click()
        WebDriverWait(driver, 15).until(EC.staleness_of(image))
        return wait_for_captcha_image(driver, timeout=15)
    except (TimeoutException, CaptchaImageTimeout):
        return open_login_form(driver, target_url, config)


def login(driver, target_url: str, config: dict, mode: str = "manual", allow_manual_fallback: bool = True,
          diagnostic: Callable[[dict, bytes | None], None] | None = None) -> None:
    """在既有 Selenium 瀏覽器登入，成功後回到 ``target_url``。"""
    if mode not in ("manual", "tesseract"):
        raise RuntimeError("captcha.mode 必須是 manual 或 tesseract")
    if mode == "manual" and not allow_manual_fallback:
        raise RuntimeError("無人值守模式不可使用手動驗證碼；請改用 Tesseract")
    parsed_target = urlparse(target_url)
    if parsed_target.scheme != "https" or parsed_target.netloc != LIBRARY_DOMAIN:
        raise RuntimeError("登入目標必須是亞洲大學圖書館的 HTTPS 網址")
    if mode == "tesseract":
        tesseract_command()

    image = open_login_form(driver, target_url, config)
    for attempt in range(1, MAX_CAPTCHA_ATTEMPTS + 1):
        answer_source = "manual"
        png = image.screenshot_as_png if diagnostic or mode == "tesseract" else None
        if diagnostic:
            diagnostic({"attempt": attempt, "stage": "image_ready"}, png)
        if mode == "tesseract":
            print(f"正在辨識驗證碼（Tesseract，第 {attempt}/{MAX_CAPTCHA_ATTEMPTS} 次）...", flush=True)
            try:
                answers = recognize_tesseract(png)
                if diagnostic:
                    diagnostic({"attempt": attempt, "stage": "recognition", "model": "Tesseract",
                                "answers": answers}, None)
                answer = next((candidate for candidate in answers
                               if candidate and answers.count(candidate) >= 2), "")
                if not answer:
                    raise RuntimeError("Tesseract 三次辨識未能取得至少兩次一致的英數結果")
                answer_source = "tesseract"
            except RuntimeError as exc:
                if diagnostic:
                    diagnostic({"attempt": attempt, "stage": "recognition_error", "reason": str(exc)}, None)
                if attempt < MAX_CAPTCHA_ATTEMPTS:
                    print(f"辨識未成功：{exc}；正在更換驗證碼。", flush=True)
                    image = refresh_captcha(driver, image, target_url, config)
                    continue
                if not allow_manual_fallback:
                    raise RuntimeError(f"已達 {MAX_CAPTCHA_ATTEMPTS} 次上限，驗證碼仍未辨識成功：{exc}") from None
                answer = prompt_captcha(image, f"已達 {MAX_CAPTCHA_ATTEMPTS} 次上限：{exc}。請手動確認。")
        else:
            answer = prompt_captcha(image)
        if not re.fullmatch(r"[A-Za-z0-9]{3,10}", answer):
            if diagnostic:
                diagnostic({"attempt": attempt, "stage": "invalid_answer", "answer": answer}, None)
            raise RuntimeError("驗證碼格式不正確，未送出登入")
        if diagnostic:
            diagnostic({"attempt": attempt, "stage": "submitted", "answer": answer,
                        "source": answer_source}, None)
        driver.find_element(By.ID, "validateCode").send_keys(answer)
        driver.find_element(By.CSS_SELECTOR, "a[onclick*='submitForm']").click()
        try:
            driver.switch_to.default_content()
            # 網站可能保留登入 iframe，不能用密碼欄位是否消失判斷登入成功。
            WebDriverWait(driver, 30).until(EC.visibility_of_element_located((By.LINK_TEXT, "登出")))
            get_with_retries(driver, target_url)
            WebDriverWait(driver, 15).until(EC.visibility_of_element_located((By.LINK_TEXT, "登出")))
        except Exception:
            try:
                alert = driver.switch_to.alert
                alert_text = alert.text
                alert.accept()
            except NoAlertPresentException:
                alert_text = ""
            if "驗證碼" in alert_text:
                if diagnostic:
                    diagnostic({"attempt": attempt, "stage": "rejected", "reason": "網站判定驗證碼錯誤"}, None)
                if mode == "tesseract" and attempt < MAX_CAPTCHA_ATTEMPTS:
                    print("網站判定驗證碼錯誤；正在更換驗證碼重新登入。", flush=True)
                    image = open_login_form(driver, target_url, config)
                    continue
                raise RuntimeError(f"網站判定驗證碼錯誤；已達 {attempt} 次上限") from None
            if diagnostic:
                diagnostic({"attempt": attempt, "stage": "login_error",
                            "reason": alert_text[:120] or "未確認登入成功"}, None)
            if mode == "tesseract" and attempt < MAX_CAPTCHA_ATTEMPTS and not any(
                word in alert_text for word in ("帳號", "密碼", "停用", "鎖定")
            ):
                print("網站未確認登入成功；正在更換驗證碼重新登入。", flush=True)
                image = open_login_form(driver, target_url, config)
                continue
            raise RuntimeError("登入未成功，請確認帳密及網站狀態") from None
        if diagnostic:
            diagnostic({"attempt": attempt, "stage": "accepted"}, None)
        print("[PASS] 測試帳號已登入", flush=True)
        return
