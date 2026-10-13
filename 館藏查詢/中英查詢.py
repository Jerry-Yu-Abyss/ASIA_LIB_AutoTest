# 測試成功標準：
# 1. 從 10 個中文詞和 10 個英文詞中，各隨機抽出 1 個並在搜尋框查詢。
# 2. 每次搜尋都能開啟第 1、5、10 筆書目的詳情頁。
# 3. 六筆書目都能從「索書號(卷期)」取得分類號，整體才算成功。
# 4. 找不到分類號時回傳「查無館藏」，該筆判定失敗。

"""亞洲大學圖書館中英文詞搜尋測試。"""

import argparse
import random
import sys

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from 關鍵字查詢 import (
    NO_HOLDINGS,
    REQUIRED_POSITIONS,
    RESULT_TITLE_SELECTOR,
    TARGET_URL,
    get_classification_result,
    is_service_unavailable,
    open_page,
)

CHINESE_WORDS = (
    "心理", "設計", "管理", "科技", "藝術",
    "文學", "歷史", "教育", "健康", "社會",
)
ENGLISH_WORDS = (
    "computer", "food", "history", "science", "music",
    "business", "health", "education", "design", "language",
)


def check_search(driver, language: str, word: str) -> dict:
    """在輸入框查詢一個詞，點開指定書目並取得分類號。"""
    result = {
        "language": language,
        "word": word,
        "url": "",
        "books": {},
        "errors": [],
    }
    print(f"\n[{language}] 搜尋：{word}")

    try:
        driver.get(TARGET_URL)
        search_input = WebDriverWait(driver, 20).until(
            lambda d: d.find_element(By.ID, "ss_keyword")
        )
        search_input.clear()
        search_input.send_keys(word)
        if search_input.get_attribute("value") != word:
            raise RuntimeError("搜尋框輸入內容不符")

        before_url = driver.current_url
        driver.find_element(
            By.CSS_SELECTOR, "#singalSearch input[name='searchBtn']"
        ).click()
        try:
            WebDriverWait(driver, 20).until(
                lambda d: d.current_url != before_url
            )
        except TimeoutException as exc:
            raise RuntimeError("按下搜尋後未跳轉") from exc

        result["url"] = driver.current_url
        if is_service_unavailable(driver):
            raise RuntimeError("搜尋結果頁回傳 Service Unavailable")
        WebDriverWait(driver, 20).until(
            lambda d: d.find_elements(By.ID, "list")
        )
        result_count = len(driver.find_elements(By.CSS_SELECTOR, RESULT_TITLE_SELECTOR))
        print(f"  搜尋結果：{result_count} 筆；網址：{result['url']}")

        for position in REQUIRED_POSITIONS:
            if result_count < position:
                result["errors"].append(f"第 {position} 筆不存在")
                continue

            # 網站偶爾未載入館藏表格；最多點開兩次再判定。
            for attempt in (1, 2):
                try:
                    anchor = driver.find_elements(
                        By.CSS_SELECTOR, RESULT_TITLE_SELECTOR
                    )[position - 1]
                    book_name = (
                        anchor.get_attribute("title") or anchor.text or ""
                    ).strip()
                    if not book_name:
                        raise RuntimeError("書名為空")
                    result["books"][position] = {
                        "name": book_name,
                        "classification": "（未取得）",
                    }

                    before_detail_url = driver.current_url
                    anchor.click()
                    try:
                        WebDriverWait(driver, 20).until(
                            lambda d: d.current_url != before_detail_url
                        )
                    except TimeoutException as exc:
                        raise RuntimeError("點擊書目後未跳轉") from exc
                    if is_service_unavailable(driver):
                        raise RuntimeError("書目詳情頁回傳 Service Unavailable")

                    classification = get_classification_result(driver)
                    result["books"][position]["classification"] = classification
                    if classification == NO_HOLDINGS:
                        raise RuntimeError(NO_HOLDINGS)
                    print(f"  第 {position:>2} 筆：{book_name}；分類號：{classification}")
                    break
                except Exception as exc:
                    reason = (
                        "書目詳情頁載入逾時"
                        if isinstance(exc, TimeoutException)
                        else str(exc).strip() or type(exc).__name__
                    )
                    if attempt == 2:
                        result["errors"].append(f"第 {position} 筆：{reason}")
                    else:
                        print(f"  第 {position:>2} 筆重試：{reason}")
                finally:
                    if driver.current_url != result["url"]:
                        driver.back()
                        WebDriverWait(driver, 20).until(
                            lambda d: d.current_url == result["url"]
                            and bool(d.find_elements(By.CSS_SELECTOR, RESULT_TITLE_SELECTOR))
                        )
    except Exception as exc:
        result["errors"].append(str(exc).strip() or type(exc).__name__)

    return result


def print_report(results: list[dict]) -> bool:
    def passed(result: dict) -> bool:
        return not result["errors"] and all(
            result["books"].get(position, {}).get("classification")
            not in (None, "（未取得）", NO_HOLDINGS)
            for position in REQUIRED_POSITIONS
        )

    print("\n" + "=" * 55)
    print("  中英文查詢測試報告")
    print("=" * 55)
    for result in results:
        status = "PASS" if passed(result) else "FAIL"
        print(f"\n[{status}] {result['language']}：{result['word']}")
        for position in REQUIRED_POSITIONS:
            book = result["books"].get(position)
            if book:
                print(f"  第 {position:>2} 筆：{book['name']}")
                print(f"          分類號：{book['classification']}")
            else:
                print(f"  第 {position:>2} 筆：未取得")
        for error in result["errors"]:
            print(f"  原因：{error}")
    all_passed = len(results) == 2 and all(passed(result) for result in results)
    print("\n" + ("[PASS] 中、英文查詢均通過" if all_passed else "[FAIL] 中、英文查詢未全部通過"))
    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(description="隨機抽取中英文詞搜尋並檢查書目分類號")
    parser.add_argument("--seed", type=int, help="固定隨機抽詞結果，方便重複測試")
    parser.add_argument("--headless", action="store_true", help="背景執行 Chrome")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    rng = random.Random(args.seed)
    selected = (
        ("中文", rng.choice(CHINESE_WORDS)),
        ("英文", rng.choice(ENGLISH_WORDS)),
    )
    print("本次抽中的詞：" + "、".join(f"{language} {word}" for language, word in selected))

    driver = open_page(headless=args.headless)
    try:
        results = [check_search(driver, language, word) for language, word in selected]
        return 0 if print_report(results) else 1
    finally:
        if not args.headless and sys.stdin.isatty():
            input("\n按 Enter 關閉瀏覽器...")
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
