"""
爬蟲目標：https://aulib.asia.edu.tw/webpac/search.cfm
需求套件：pip install selenium webdriver-manager
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

TARGET_URL = "https://aulib.asia.edu.tw/webpac/search.cfm"


def open_page(headless: bool = False) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    print(f"[+] 正在開啟頁面：{TARGET_URL}")
    driver.get(TARGET_URL)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        print(f"[+] 頁面載入成功！標題：{driver.title}")
    except Exception as e:
        print(f"[!] 等待逾時：{e}")
    return driver


def diagnose(driver: webdriver.Chrome):
    """
    診斷模式：
    1. 等待頁面動態內容載入（額外等 5 秒）
    2. 列出頁面上所有 id
    3. 檢查是否有 iframe，若有則切入掃描
    4. 嘗試用多種方式找 #newbooks / .slideMain
    """
    print("\n[診斷] 額外等待 5 秒讓動態內容載入...")
    time.sleep(5)

    # ── 1. 列出頁面所有有 id 的元素 ──
    ids = driver.execute_script(
        "return Array.from(document.querySelectorAll('[id]')).map(el => el.id);"
    )
    print(f"\n[診斷] 頁面上共有 {len(ids)} 個帶 id 的元素：")
    for el_id in ids:
        print(f"  #{el_id}")

    # ── 2. 檢查是否存在 iframe ──
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    print(f"\n[診斷] 共找到 {len(iframes)} 個 <iframe>")
    for i, iframe in enumerate(iframes, start=1):
        src = iframe.get_attribute("src") or "（無 src）"
        name = iframe.get_attribute("name") or "（無 name）"
        print(f"  iframe [{i}]  name={name}  src={src}")

    # ── 3. 直接搜尋目標 class ──
    for cls in ["slideMain", "slideBlock", "slideBooks", "bookDetail"]:
        els = driver.find_elements(By.CLASS_NAME, cls)
        print(f"\n[診斷] .{cls} → 找到 {len(els)} 個")

    # ── 4. 嘗試切入第一個 iframe 再搜尋 ──
    if iframes:
        print("\n[診斷] 嘗試切入 iframe[0] 再搜尋...")
        try:
            driver.switch_to.frame(iframes[0])
            for cls in ["slideMain", "slideBlock", "slideBooks", "bookDetail"]:
                els = driver.find_elements(By.CLASS_NAME, cls)
                print(f"  (iframe內) .{cls} → 找到 {len(els)} 個")
            driver.switch_to.default_content()   # 切回主頁面
        except Exception as e:
            print(f"  [!] 切換 iframe 失敗：{e}")
            driver.switch_to.default_content()


def scan_slide_main(driver: webdriver.Chrome):
    """
    完整掃描結構：
        #newbooks  (id)
          └─ .slideMain
               └─ .slideBlock      (多筆)
                    └─ .slideBooks  (多筆)
                         └─ .bookDetail (多筆)
                              └─ <a> → <img> → src
    最後輸出完整報告。
    """
    report        = []   # 每個 slideBlock 的統計
    grand_total   = 0   # 全站應有總數
    grand_missing = 0   # 全站缺少總數

    try:
        # 額外等待動態內容（AJAX / JS render）
        print("\n[+] 等待動態內容載入（5 秒）...")
        time.sleep(5)

        # ── 最上層：#newbooks ──
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "newBooks"))
        )
        newbooks   = driver.find_element(By.ID, "newBooks")
        slide_main = newbooks.find_element(By.CSS_SELECTOR, ".slideMain")
        print(f"[+] 找到 #newbooks > .slideMain")

        # ── slideBlock ──
        slide_blocks = slide_main.find_elements(By.CSS_SELECTOR, ".slideBlock")
        print(f"[+] 共找到 {len(slide_blocks)} 個 .slideBlock\n")
        print("=" * 55)

        for sb_idx, slide_block in enumerate(slide_blocks, start=1):
            try:
                title_el    = slide_block.find_element(
                    By.XPATH, ".//*[self::h2 or self::h3 or self::h4 or self::p[@class]]"
                )
                block_title = title_el.text.strip() or f"slideBlock {sb_idx}"
            except Exception:
                block_title = f"slideBlock {sb_idx}"

            print(f"\n▌slideBlock [{sb_idx}]  {block_title}")

            block_total   = 0
            block_missing = 0
            block_missing_books = []   # 缺少封面的書名清單

            slide_books_list = slide_block.find_elements(By.CSS_SELECTOR, ".slideBooks")
            print(f"  .slideBooks 數量：{len(slide_books_list)}")

            for books_idx, slide_books in enumerate(slide_books_list, start=1):
                print(f"\n  ┌─ slideBooks [{sb_idx}-{books_idx}]")
                book_details = slide_books.find_elements(By.CSS_SELECTOR, ".bookDetail")
                print(f"  │  .bookDetail 數量：{len(book_details)}")

                PLACEHOLDER = "templates/img/product_img.jpg"

                for bd_idx, book_detail in enumerate(book_details, start=1):
                    anchors        = book_detail.find_elements(By.TAG_NAME, "a")
                    found_src      = False  # 有真實封面圖
                    is_placeholder = False  # 是佔位預設圖

                    # 嘗試取得書名（title 或 alt 或 文字）
                    book_name = book_detail.text.strip().splitlines()[0] if book_detail.text.strip() else ""
                    if not book_name:
                        try:
                            first_a = book_detail.find_element(By.TAG_NAME, "a")
                            book_name = first_a.get_attribute("title") or first_a.text.strip() or f"書籍 {bd_idx}"
                        except Exception:
                            book_name = f"書籍 {bd_idx}"

                    for a_idx, anchor in enumerate(anchors, start=1):
                        imgs = anchor.find_elements(By.TAG_NAME, "img")
                        for img_idx, img in enumerate(imgs, start=1):
                            src = img.get_attribute("src") or ""

                            if not src:
                                print(f"  │    [{sb_idx}-{books_idx}-{bd_idx}-{a_idx}-{img_idx}] src = （無 src）")
                            elif PLACEHOLDER in src:
                                print(f"  │    [{sb_idx}-{books_idx}-{bd_idx}-{a_idx}-{img_idx}] src = ⚠ 預設佔位圖（缺封面）")
                                is_placeholder = True
                            else:
                                print(f"  │    [{sb_idx}-{books_idx}-{bd_idx}-{a_idx}-{img_idx}] src = {src}")
                                found_src = True

                    block_total += 1
                    if not found_src or is_placeholder:
                        block_missing += 1
                        reason = "預設佔位圖" if is_placeholder else "無任何圖片"
                        print(f"  │    ❌ [{bd_idx}] {book_name}（{reason}）")
                        block_missing_books.append(f"{book_name}（{reason}）")

                print(f"  └─ slideBooks [{sb_idx}-{books_idx}] 結束")

            grand_total   += block_total
            grand_missing += block_missing
            report.append({
                "idx":           sb_idx,
                "title":         block_title,
                "total":         block_total,
                "missing":       block_missing,
                "missing_books": block_missing_books,
            })

        # ── 最終報告 ──
        grand_actual = grand_total - grand_missing

        print("\n\n" + "█" * 55)
        print("  📋  完整掃描報告")
        print("█" * 55)

        for r in report:
            actual = r["total"] - r["missing"]
            print(f"  [{r['idx']:02d}] {r['title'][:28]:<28}")
            print(f"       應該有 {r['total']} 筆  │  實際有 {actual} 筆  │  缺少 {r['missing']} 筆")
            if r["missing_books"]:
                print(f"       缺少的書：")
                for bname in r["missing_books"]:
                    print(f"         • {bname}")

        print("─" * 55)
        print(f"  【全站統計】")
        print(f"  應該有：{grand_total} 筆")
        print(f"  實際有：{grand_actual} 筆")
        print(f"  缺少：  {grand_missing} 筆")
        if grand_missing == 0:
            print(f"  ✅ 所有新書均有封面圖片")
        else:
            print(f"  ❌ 共缺少 {grand_missing} 張封面")
        print("█" * 55)

    except Exception as e:
        print(f"\n[!] scan_slide_main 發生錯誤，切換為診斷模式...\n")
        diagnose(driver)


def is_service_unavailable(driver: webdriver.Chrome) -> bool:
    """檢查目前頁面是否為 503 Service Unavailable。"""
    return "Service Unavailable" in driver.page_source


def main(max_retries: int = 10, retry_interval: int = 30):
    """
    開啟頁面並執行掃描。
    若遇到 Service Unavailable，每隔 retry_interval 秒自動重試，
    最多重試 max_retries 次。
    """
    driver = None

    for attempt in range(1, max_retries + 1):
        print(f"\n{'='*40}")
        print(f"[+] 第 {attempt}/{max_retries} 次嘗試...")

        # 第一次建立 driver，之後重用同一個視窗直接重新整理
        if driver is None:
            driver = open_page(headless=False)
        else:
            print(f"[+] 重新整理頁面...")
            driver.refresh()
            try:
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                pass

        # 檢查是否 503
        if is_service_unavailable(driver):
            print(f"[!] 伺服器回傳 Service Unavailable")
            if attempt < max_retries:
                print(f"[+] {retry_interval} 秒後自動重試...")
                time.sleep(retry_interval)
            else:
                print(f"[!] 已達最大重試次數（{max_retries}），放棄。")
            continue

        # 頁面正常 → 執行掃描
        print(f"[+] 頁面正常，開始掃描...")
        scan_slide_main(driver)
        break   # 掃描完成，跳出迴圈

    print("\n[+] 完成，按 Enter 關閉瀏覽器...")
    input()
    if driver:
        driver.quit()
    print("[+] 瀏覽器已關閉。")


if __name__ == "__main__":
    main()