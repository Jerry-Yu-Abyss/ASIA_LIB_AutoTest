# 測試成功標準：
# 1. 使用本機 JSON 的測試帳號登入，並完成驗證碼。
# 2. 從中文、英文各 10 個常見詞中各抽 1 個，在網路書店推薦頁查詢。
# 3. 實際點開每次搜尋的第 1、5、10 筆書目，確認對應書名及「推薦」按鈕可見。
# 4. 六筆均符合才算成功；全程不點擊「推薦」按鈕、不送出推薦。

"""網路書店推薦載入測試；驗證碼可手動輸入或透過 Gemini 辨識。"""

import argparse
from pathlib import Path
import random
import sys

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from 中英查詢 import CHINESE_WORDS, ENGLISH_WORDS
from 關鍵字查詢 import REQUIRED_POSITIONS, open_page

DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "測試帳號.local.json"
RECOMMEND_URL = "https://aulib.asia.edu.tw/webpac/recommend.cfm"
BOOKSTORE_URL = "https://aulib.asia.edu.tw/webpac/recommend_book.cfm"
BOOK_LINKS = "a.add-recommend[href='pop_recommend.cfm']"
DETAIL_FRAME = "#colorbox iframe.cboxIframe[src*='pop_recommend.cfm']"


def clean_text(text: str) -> str:
    return " ".join(text.split())


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
        from 帳號登入 import load_config, login

        config = load_config(args.config)
        mode = args.captcha_mode or config.get("captcha", {}).get("mode", "manual")
        if mode not in ("manual", "gemini"):
            raise RuntimeError("captcha.mode 必須是 manual 或 gemini")
        rng = random.Random(args.seed)
        selected = (("中文", rng.choice(CHINESE_WORDS)), ("英文", rng.choice(ENGLISH_WORDS)))
        print("抽中的詞：" + "、".join(f"{language} {word}" for language, word in selected), flush=True)
        driver = open_page(headless=args.headless)
        driver.set_page_load_timeout(args.timeout)
        login(driver, RECOMMEND_URL, config, mode)
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
