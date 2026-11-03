"""亞洲大學圖書館測試帳號登入工具。

需要登入的測試才匯入此模組；一般館藏查詢不會讀取帳號設定。
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import random
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from selenium.common.exceptions import NoAlertPresentException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "測試帳號.local.json"
DEFAULT_MODEL = "gemini-flash-latest"
LIBRARY_DOMAIN = "aulib.asia.edu.tw"
MAX_CAPTCHA_ATTEMPTS = 5


class GeminiTransientError(RuntimeError):
    """Gemini 的暫時性錯誤，可在稍後更換驗證碼重試。"""


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


def recognize_captcha(png: bytes, settings: dict) -> str:
    """以 Gemini 辨識驗證碼；只傳送驗證碼圖片，不傳送帳密。"""
    api_key = os.environ.get("GEMINI_API_KEY") or settings.get("gemini_api_key", "")
    if not api_key:
        raise RuntimeError("缺少 Gemini API Key；請設定 GEMINI_API_KEY 或本機 JSON，或使用 manual 模式")
    model = settings.get("gemini_model") or DEFAULT_MODEL
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise RuntimeError("gemini_model 格式不正確")
    body = {
        "contents": [{"parts": [
            {"text": "Read the letters and digits in this verification image. Preserve case. Return only the code, without explanation or formatting."},
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode("ascii")}},
        ]}],
    }
    request = Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            data = json.load(response)
    except HTTPError as exc:
        # 不輸出原始回應／請求，避免金鑰出現在錯誤報告。
        if exc.code in (429, 500, 502, 503, 504):
            raise GeminiTransientError(f"Gemini 暫時無法回應（HTTP {exc.code}）") from None
        raise RuntimeError(f"Gemini 回傳 HTTP {exc.code}，請檢查金鑰、模型與配額") from None
    except (URLError, TimeoutError):
        raise GeminiTransientError("Gemini 辨識連線或回應失敗") from None
    except ValueError:
        raise RuntimeError("Gemini 回應格式不正確") from None
    try:
        answer = "".join(
            part.get("text", "") for part in data["candidates"][0]["content"]["parts"]
            if not part.get("thought", False)
        ).strip()
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Gemini 沒有回傳可用的驗證碼") from None
    if not re.fullmatch(r"[A-Za-z0-9]{3,10}", answer):
        raise RuntimeError("Gemini 回傳格式不是英數驗證碼，未送出登入")
    return answer


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
    driver.get(target_url)
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


def login(driver, target_url: str, config: dict, mode: str = "manual", allow_manual_fallback: bool = True) -> None:
    """在既有 Selenium 瀏覽器登入，成功後回到 ``target_url``。"""
    if mode not in ("manual", "gemini"):
        raise RuntimeError("captcha.mode 必須是 manual 或 gemini")
    if mode == "manual" and not allow_manual_fallback:
        raise RuntimeError("無人值守模式不可使用手動驗證碼；請改用 Gemini")
    parsed_target = urlparse(target_url)
    if parsed_target.scheme != "https" or parsed_target.netloc != LIBRARY_DOMAIN:
        raise RuntimeError("登入目標必須是亞洲大學圖書館的 HTTPS 網址")

    settings = config.get("captcha", {})
    if mode == "gemini" and not (os.environ.get("GEMINI_API_KEY") or settings.get("gemini_api_key")):
        raise RuntimeError("自動辨識需要 Gemini API Key；可改用 --captcha-mode manual")
    image = open_login_form(driver, target_url, config)
    for attempt in range(1, MAX_CAPTCHA_ATTEMPTS + 1):
        if mode == "gemini":
            print(f"正在辨識驗證碼（Gemini，第 {attempt}/{MAX_CAPTCHA_ATTEMPTS} 次）...", flush=True)
            png = image.screenshot_as_png
            try:
                answer = recognize_captcha(png, settings)
                confirm_model = "gemini-3.5-flash"
                if (settings.get("gemini_model") or DEFAULT_MODEL) == confirm_model:
                    confirm_model = "gemini-3.5-flash-lite"
                confirmation = recognize_captcha(png, {**settings, "gemini_model": confirm_model})
                if answer != confirmation:
                    raise RuntimeError(f"兩個模型辨識不同（{answer} / {confirmation}）")
            except RuntimeError as exc:
                if attempt < MAX_CAPTCHA_ATTEMPTS:
                    if isinstance(exc, GeminiTransientError):
                        delay = min(2 ** (attempt - 1), 8) + random.uniform(0, 0.5)
                        print(f"辨識未成功：{exc}；等待 {delay:.1f} 秒後更換驗證碼。", flush=True)
                        time.sleep(delay)
                    else:
                        print(f"辨識未成功：{exc}；正在更換驗證碼。", flush=True)
                    image = refresh_captcha(driver, image, target_url, config)
                    continue
                if not allow_manual_fallback:
                    raise RuntimeError(f"已達 {MAX_CAPTCHA_ATTEMPTS} 次上限，驗證碼仍未辨識成功：{exc}") from None
                answer = prompt_captcha(image, f"已達 {MAX_CAPTCHA_ATTEMPTS} 次上限：{exc}。請手動確認。")
        else:
            answer = prompt_captcha(image)
        if not re.fullmatch(r"[A-Za-z0-9]{3,10}", answer):
            raise RuntimeError("驗證碼格式不正確，未送出登入")
        driver.find_element(By.ID, "validateCode").send_keys(answer)
        driver.find_element(By.CSS_SELECTOR, "a[onclick*='submitForm']").click()
        try:
            driver.switch_to.default_content()
            # 網站可能保留登入 iframe，不能用密碼欄位是否消失判斷登入成功。
            WebDriverWait(driver, 30).until(EC.visibility_of_element_located((By.LINK_TEXT, "登出")))
            driver.get(target_url)
            WebDriverWait(driver, 15).until(EC.visibility_of_element_located((By.LINK_TEXT, "登出")))
        except Exception:
            try:
                alert = driver.switch_to.alert
                alert_text = alert.text
                alert.accept()
            except NoAlertPresentException:
                alert_text = ""
            if "驗證碼" in alert_text:
                if mode == "gemini" and attempt < MAX_CAPTCHA_ATTEMPTS:
                    print("網站判定驗證碼錯誤；正在更換驗證碼重新登入。", flush=True)
                    image = open_login_form(driver, target_url, config)
                    continue
                raise RuntimeError(f"網站判定驗證碼錯誤；已達 {attempt} 次上限") from None
            raise RuntimeError("登入未成功，請確認帳密及網站狀態") from None
        print("[PASS] 測試帳號已登入", flush=True)
        return
