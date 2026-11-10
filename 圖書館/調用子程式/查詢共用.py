"""館藏與網路書店檢測共用的瀏覽器及搜尋結果工具。"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

if __package__:
    from .網頁載入 import ConnectionTimeout, get_with_retries
else:
    from 網頁載入 import ConnectionTimeout, get_with_retries

TARGET_URL = "https://aulib.asia.edu.tw/webpac/search.cfm"
RESULT_TITLE_SELECTOR = "#list .list_box .title ul li:last-child a"
RESULT_BOX_SELECTOR = "#list .list_box"
REQUIRED_POSITIONS = (1, 5, 10)
PRINT_BOOK_TYPE = "書目-語言資料,印刷品:單行本"
BOOK_TYPE_SELECTOR = ".product_info .product_info_content img[alt]"


def show_more_results(driver: webdriver.Chrome) -> str:
    url = urlsplit(driver.current_url)
    params = dict(parse_qsl(url.query, keep_blank_values=True))
    params.update(list_num="100", current_page="1")
    expanded_url = urlunsplit((url.scheme, url.netloc, url.path, urlencode(params), url.fragment))
    get_with_retries(driver, expanded_url)
    if urlsplit(driver.current_url).path.endswith("/error.html"):
        raise RuntimeError("圖書館搜尋結果頁發生錯誤（error.html）")
    WebDriverWait(driver, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, RESULT_TITLE_SELECTOR) or False
    )
    return driver.current_url


def print_book_indices(driver: webdriver.Chrome) -> list[int]:
    indices = []
    for index, box in enumerate(driver.find_elements(By.CSS_SELECTOR, RESULT_BOX_SELECTOR)):
        icons = box.find_elements(By.CSS_SELECTOR, BOOK_TYPE_SELECTOR)
        book_type = (icons[0].get_attribute("alt") or "").strip() if icons else ""
        if book_type == PRINT_BOOK_TYPE:
            indices.append(index)
            if len(indices) == max(REQUIRED_POSITIONS):
                break
        else:
            print(f"      略過搜尋結果第 {index + 1} 筆：{book_type or '未標示書目類型'}")
    return indices


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
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    print(f"[+] 正在開啟頁面：{TARGET_URL}")
    driver.set_page_load_timeout(45)
    try:
        get_with_retries(driver, TARGET_URL)
    except ConnectionTimeout:
        driver.quit()
        raise
    except WebDriverException:
        driver.quit()
        raise RuntimeError("無法開啟圖書館網站，請稍後再試或檢查網路") from None
    try:
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        print(f"[+] 頁面載入成功！標題：{driver.title}")
    except Exception as exc:
        print(f"[!] 等待逾時：{exc}")
    return driver


def is_service_unavailable(driver: webdriver.Chrome) -> bool:
    return "Service Unavailable" in driver.page_source
