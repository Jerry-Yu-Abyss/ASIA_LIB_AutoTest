# 測試成功標準：
# 1. 使用本機 JSON 的測試帳號登入，並完成驗證碼。
# 2. 從中文、英文各 10 個常見詞中各抽 1 個，在網路書店推薦頁查詢。
# 3. 實際點開每次搜尋的第 1、5、10 筆書目，確認對應書名及「推薦」按鈕可見。
# 4. 六筆均符合才算成功；全程不點擊「推薦」按鈕、不送出推薦。

"""網路書店推薦載入測試；驗證碼可手動輸入或透過 Gemini 辨識。"""

import argparse
import base64
import json
import os
from pathlib import Path
import random
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from 中英查詢 import CHINESE_WORDS, ENGLISH_WORDS
from 關鍵字查詢 import REQUIRED_POSITIONS, open_page

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "測試帳號.local.json"
RECOMMEND_URL = "https://aulib.asia.edu.tw/webpac/recommend.cfm"
BOOKSTORE_URL = "https://aulib.asia.edu.tw/webpac/recommend_book.cfm"
BOOK_LINKS = "a.add-recommend[href='pop_recommend.cfm']"
DETAIL_FRAME = "#colorbox iframe.cboxIframe[src*='pop_recommend.cfm']"
DEFAULT_MODEL = "gemini-flash-latest"


def clean_text(text: str) -> str:
    return " ".join(text.split())


def load_config(path: Path) -> dict:
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
    """採用文章的 Gemini 圖片辨識方式；只傳驗證碼圖片，不傳帳密。"""
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
        raise RuntimeError(f"Gemini 回傳 HTTP {exc.code}，請檢查金鑰、模型與配額") from None
    except (URLError, TimeoutError, ValueError):
        raise RuntimeError("Gemini 辨識連線或回應失敗") from None
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


def login(driver, config: dict, mode: str) -> None:
    settings = config.get("captcha", {})
    if mode == "gemini" and not (os.environ.get("GEMINI_API_KEY") or settings.get("gemini_api_key")):
        raise RuntimeError("自動辨識需要 Gemini API Key；可改用 --captcha-mode manual")
    driver.get(RECOMMEND_URL)
    driver.find_element(By.LINK_TEXT, "登入").click()
    frame = WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "iframe[src*='login_iframe.cfm']"))
    )
    if urlparse(frame.get_attribute("src")).netloc != "aulib.asia.edu.tw":
        raise RuntimeError("登入視窗不在預期的圖書館網域")
    driver.switch_to.frame(frame)
    WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.ID, "hidid")))
    driver.find_element(By.ID, "hidid").send_keys(config["username"])
    password_input = driver.find_element(By.ID, "password")
    password_input.send_keys(config["password"])
    image = driver.find_element(By.CSS_SELECTOR, "#captcha_span img")
    if mode == "gemini":
        print("正在辨識驗證碼（Gemini）...", flush=True)
        answer = recognize_captcha(image.screenshot_as_png, settings)
    else:
        screenshot = ROOT / ".local" / "captcha.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        image.screenshot(str(screenshot))
        print(f"驗證碼圖片：{screenshot}", flush=True)
        answer = input("請依瀏覽器或圖片輸入驗證碼：").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{3,10}", answer):
        raise RuntimeError("驗證碼格式不正確，未送出登入")
    driver.find_element(By.ID, "validateCode").send_keys(answer)
    driver.find_element(By.CSS_SELECTOR, "a[onclick*='submitForm']").click()
    try:
        WebDriverWait(driver, 30).until(EC.staleness_of(password_input))
        driver.switch_to.default_content()
        driver.get(RECOMMEND_URL)
        WebDriverWait(driver, 15).until(EC.visibility_of_element_located((By.LINK_TEXT, "登出")))
    except Exception:
        raise RuntimeError("登入未成功，請確認帳密及驗證碼；程式不會自動重試登入") from None
    print("[PASS] 測試帳號已登入", flush=True)


def check_book(driver, position: int) -> dict:
    book = {"position": position, "name": "（未取得）", "loaded": False, "reason": ""}
    links = driver.find_elements(By.CSS_SELECTOR, BOOK_LINKS)
    if len(links) < position:
        book["reason"] = "搜尋結果不足，該筆不存在"
        return book
    book["name"] = clean_text(links[position - 1].text)
    try:
        links[position - 1].click()
        WebDriverWait(driver, 30).until(EC.frame_to_be_available_and_switch_to_it((By.CSS_SELECTOR, DETAIL_FRAME)))
        WebDriverWait(driver, 30).until(
            lambda d: clean_text(d.find_element(By.ID, "title").get_attribute("value") or "") == book["name"]
            and bool(book["name"])
        )
        # 僅讀取「推薦」按鈕的顯示狀態與文字，絕不可呼叫 click()。
        button = WebDriverWait(driver, 30).until(EC.visibility_of_element_located((By.ID, "btn1")))
        if clean_text(button.text) != "推薦":
            raise RuntimeError("按鈕文字不是「推薦」")
        book["loaded"] = True
    except TimeoutException:
        book["reason"] = "書目視窗、對應書名或推薦按鈕未在時間內載入"
    except Exception as exc:
        book["reason"] = str(exc).splitlines()[0] or type(exc).__name__
    finally:
        driver.switch_to.default_content()
        dialogs = driver.find_elements(By.ID, "colorbox")
        if dialogs and dialogs[0].is_displayed():
            # 只按彈窗的關閉按鈕，回到原搜尋結果。
            driver.find_element(By.ID, "cboxClose").click()
            WebDriverWait(driver, 15).until(EC.invisibility_of_element_located((By.ID, "colorbox")))
    return book


def check_search(driver, language: str, word: str, timeout: int) -> dict:
    result = {"language": language, "word": word, "books": [], "error": ""}
    print(f"\n[{language}] 搜尋：{word}（等待網路書店回應，最多 {timeout} 秒）", flush=True)
    try:
        driver.get(BOOKSTORE_URL)
        keyword = WebDriverWait(driver, 20).until(EC.visibility_of_element_located((By.ID, "keyword")))
        keyword.clear()
        keyword.send_keys(word)
        driver.find_element(By.CSS_SELECTOR, "a[onclick='form1Submit();']").click()
        # 表單 POST 後網址不變，須確認舊輸入框已被新頁面替換。
        WebDriverWait(driver, timeout).until(EC.staleness_of(keyword))
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "keyword")))
        count = len(driver.find_elements(By.CSS_SELECTOR, BOOK_LINKS))
        print(f"  已載入 {count} 筆書目", flush=True)
        for position in REQUIRED_POSITIONS:
            book = check_book(driver, position)
            result["books"].append(book)
            status = "PASS" if book["loaded"] else "FAIL"
            print(f"  [{status}] 第 {position} 筆：{book['name']}；{book['reason'] or '推薦按鈕已載入（未點擊）'}", flush=True)
    except TimeoutException:
        result["error"] = "網路書店查詢或頁面載入逾時"
    except Exception as exc:
        result["error"] = str(exc).splitlines()[0] or type(exc).__name__
    return result


def print_report(results: list[dict]) -> bool:
    passed = 0
    print("\n網路書店推薦簡易報告\n" + "=" * 55)
    for result in results:
        ok = not result["error"] and len(result["books"]) == 3 and all(b["loaded"] for b in result["books"])
        passed += int(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {result['language']}：{result['word']}")
        for book in result["books"]:
            print(f"  第 {book['position']} 筆：{book['name']}；{book['reason'] or '推薦按鈕已載入（未點擊）'}")
        if result["error"]:
            print(f"  原因：{result['error']}")
    print(f"查詢通過：{passed}/{len(results)}；推薦送出：0 筆")
    return len(results) == 2 and passed == 2


def main() -> int:
    parser = argparse.ArgumentParser(description="登入後抽取中英文詞，檢查書目推薦按鈕載入；不送出推薦")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--captcha-mode", choices=("manual", "gemini"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--timeout", type=int, default=180, help="網路書店頁面載入上限秒數（預設 180）")
    args = parser.parse_args()
    if args.timeout < 30:
        parser.error("--timeout 至少為 30 秒")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    driver = None
    try:
        config = load_config(args.config)
        mode = args.captcha_mode or config.get("captcha", {}).get("mode", "manual")
        if mode not in ("manual", "gemini"):
            raise RuntimeError("captcha.mode 必須是 manual 或 gemini")
        rng = random.Random(args.seed)
        selected = (("中文", rng.choice(CHINESE_WORDS)), ("英文", rng.choice(ENGLISH_WORDS)))
        print("抽中的詞：" + "、".join(f"{language} {word}" for language, word in selected), flush=True)
        driver = open_page(headless=args.headless)
        driver.set_page_load_timeout(args.timeout)
        login(driver, config, mode)
        results = [check_search(driver, language, word, args.timeout) for language, word in selected]
        return 0 if print_report(results) else 1
    except Exception as exc:
        print(f"[FAIL] {str(exc).splitlines()[0] or type(exc).__name__}")
        return 1
    finally:
        if driver is not None:
            driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
