"""亞洲大學圖書館個人書單分類號擷取工具。

使用者可以把網站匯出的 Excel 放進「待處理」資料夾後執行；也可以用
--live 開啟 Chrome，自行登入後讓程式收集目前書單的書目連結。
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
import math
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse
from unicodedata import east_asian_width

import requests
from lxml import html
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill


BASE_URL = "https://aulib.asia.edu.tw/webpac/"
SHELF_URL = urljoin(BASE_URL, "shelf_personalbook_list.cfm")
ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "待處理"
OUTPUT_DIR = ROOT / "完成"
HEADERS = ("書目資訊", "在架/館藏量", "分類號", "URL")
CALL_NUMBER_PREFIX = re.compile(r"^\s*([A-Za-z]{0,3}\d+(?:\.\d+)?[A-Za-z0-9]*)")


@dataclass(frozen=True)
class Book:
    description: str
    availability: str
    url: str


def clean_text(value: str) -> str:
    return " ".join((value or "").split())


def valid_book_url(value: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "aulib.asia.edu.tw"
        and parsed.path.lower().endswith(("/ele_content.cfm", "/content.cfm"))
        and re.search(r"(?:^|&)mid=\d+(?:&|$)", parsed.query, re.I) is not None
    )


def read_xlsx(path: Path) -> list[Book]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = wb.active
        header = [clean_text(str(c.value or "")) for c in sheet[1]]
        try:
            title_col = header.index("書目資訊")
            availability_col = header.index("在架/館藏量")
            url_col = header.index("URL")
        except ValueError as exc:
            raise ValueError(f"缺少必要欄位：{exc}") from exc
        books = []
        for row in sheet.iter_rows(min_row=2, values_only=True):
            url = str(row[url_col] or "").strip() if len(row) > url_col else ""
            if not url:
                continue
            if not valid_book_url(url):
                raise ValueError(f"無效的書目網址：{url}")
            books.append(Book(
                clean_text(str(row[title_col] or "")),
                clean_text(str(row[availability_col] or "")),
                url,
            ))
        return books
    finally:
        wb.close()


def read_html_xls(path: Path) -> list[Book]:
    source = path.read_text(encoding="utf-8-sig")
    doc = html.fromstring(source)
    rows = doc.xpath("//tr")
    if not rows:
        match = re.search(r'href=["\']([^"\']*sheet\d+\.htm)["\']', source, re.I)
        if not match:
            raise ValueError("此 .xls 是 Excel 網頁封裝，但找不到工作表檔案。")
        sheet_path = (path.parent / match.group(1).replace("/", "\\")).resolve()
        if not sheet_path.is_file():
            raise FileNotFoundError(f"缺少 Excel 附屬資料夾中的工作表：{sheet_path}")
        source = sheet_path.read_text(encoding="utf-8-sig")
        doc = html.fromstring(source)
        rows = doc.xpath("//tr")
    if not rows:
        raise ValueError("工作表沒有資料列。")
    header = [clean_text(c.text_content()) for c in rows[0].xpath("./th|./td")]
    try:
        title_col = header.index("書目資訊")
        availability_col = header.index("在架/館藏量")
        url_col = header.index("URL")
    except ValueError as exc:
        raise ValueError(f"缺少必要欄位：{exc}") from exc
    books = []
    for row in rows[1:]:
        cells = [clean_text(c.text_content()) for c in row.xpath("./th|./td")]
        if len(cells) <= url_col or not cells[url_col]:
            continue
        url = cells[url_col]
        if not valid_book_url(url):
            raise ValueError(f"無效的書目網址：{url}")
        books.append(Book(cells[title_col], cells[availability_col], url))
    return books


def read_input(path: Path) -> list[Book]:
    if path.suffix.lower() == ".xlsx":
        return read_xlsx(path)
    if path.suffix.lower() == ".xls":
        return read_html_xls(path)
    raise ValueError("只支援 .xlsx 或網站匯出的 HTML 格式 .xls。")


def extract_class_numbers(page: bytes) -> list[str]:
    doc = html.fromstring(page)
    found: list[str] = []
    for table in doc.xpath("//table"):
        head_rows = table.xpath("./thead/tr")
        if not head_rows:
            continue
        labels = [clean_text(c.text_content()) for c in head_rows[0].xpath("./th|./td")]
        if "索書號(卷期)" not in labels:
            continue
        number_col = labels.index("索書號(卷期)")
        for row in table.xpath("./tbody/tr"):
            cells = row.xpath("./th|./td")
            if number_col >= len(cells):
                continue
            raw = clean_text(cells[number_col].text_content())
            match = CALL_NUMBER_PREFIX.match(raw)
            if match and match.group(1) not in found:
                found.append(match.group(1))
    return found


def collect_live_books() -> tuple[list[Book], requests.Session]:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    try:
        driver.get(SHELF_URL)
        print("Chrome 已開啟。請自行登入並進入『個人化書單』，確認書目可見。")
        input("完成後回到此視窗按 Enter：")
        if "登入時間已過" in driver.page_source or "login" in driver.current_url.lower():
            raise RuntimeError("目前仍在登入頁，請先完成登入。")

        books: list[Book] = []
        seen: set[str] = set()
        visited_pages: set[tuple[str, tuple[str, ...]]] = set()
        for _ in range(100):
            page_links = [
                urljoin(driver.current_url, a.get_attribute("href") or "")
                for a in driver.find_elements(By.CSS_SELECTOR, "a[href]")
            ]
            signature = (driver.current_url, tuple(u for u in page_links if valid_book_url(u)))
            if signature in visited_pages:
                break
            visited_pages.add(signature)
            for anchor in driver.find_elements(By.CSS_SELECTOR, "a[href]"):
                url = urljoin(driver.current_url, anchor.get_attribute("href") or "")
                if not valid_book_url(url) or url in seen:
                    continue
                seen.add(url)
                title = clean_text(anchor.text or anchor.get_attribute("title") or "")
                parent_text = clean_text(anchor.find_element(By.XPATH, "..").text)
                availability = re.search(r"\b\d+\s*,\s*\d+\b", parent_text)
                books.append(Book(title or parent_text, availability.group().replace(" ", "") if availability else "", url))
            next_links = driver.find_elements(
                By.XPATH,
                "//a[contains(normalize-space(.),'下一頁') or contains(normalize-space(.),'下頁') or @rel='next']",
            )
            next_link = next((a for a in next_links if a.is_displayed() and a.is_enabled()), None)
            if next_link is None:
                break
            next_link.click()
            try:
                WebDriverWait(driver, 15).until(
                    lambda d: (
                        d.current_url,
                        tuple(
                            u for u in (
                                urljoin(d.current_url, a.get_attribute("href") or "")
                                for a in d.find_elements(By.CSS_SELECTOR, "a[href]")
                            )
                            if valid_book_url(u)
                        ),
                    ) != signature
                )
            except Exception:
                break

        if not books:
            raise RuntimeError("登入後的頁面沒有找到書目連結。請改用網站匯出的 Excel 放在『待處理』資料夾。")
        session = requests.Session()
        for cookie in driver.get_cookies():
            session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain", "aulib.asia.edu.tw"), path=cookie.get("path", "/"))
        return books, session
    finally:
        driver.quit()


def fetch_results(books: list[Book], session: requests.Session, delay: float) -> tuple[list[list[str]], list[list[str]]]:
    rows: list[list[str]] = []
    issues: list[list[str]] = []
    for position, book in enumerate(books, 1):
        number = ""
        reason = ""
        try:
            response = session.get(book.url, timeout=30)
            response.raise_for_status()
            found = extract_class_numbers(response.content)
            if not found:
                reason = "未找到索書號(卷期)"
            else:
                number = "、".join(found)
                if len(found) > 1:
                    reason = f"多個不同分類號：{number}"
        except requests.RequestException as exc:
            reason = f"連線失敗：{exc}"
        rows.append([book.description, book.availability, number, book.url])
        if reason:
            issues.append([str(position), book.description, book.url, reason])
        print(f"[{position}/{len(books)}] {number or '未取得'}  {book.description[:30]}")
        if delay and position < len(books):
            time.sleep(delay)
    return rows, issues


def save_results(output: Path, rows: list[list[str]], issues: list[list[str]]) -> None:
    wb = Workbook()
    sheet = wb.active
    sheet.title = "工作表1"
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
        sheet.cell(sheet.max_row, 4).hyperlink = row[3]
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:D{sheet.max_row}"
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="274A70")
        cell.alignment = Alignment(vertical="center")
    for column, width in {"A": 80, "B": 16, "C": 20, "D": 80}.items():
        sheet.column_dimensions[column].width = width
    for row_number, row in enumerate(sheet.iter_rows(min_row=2), 2):
        for cell in row:
            cell.alignment = Alignment(vertical="top")
        row[0].alignment = Alignment(vertical="top", wrap_text=True)
        visual_length = sum(2 if east_asian_width(char) in "WF" else 1 for char in str(row[0].value or ""))
        sheet.row_dimensions[row_number].height = max(29, math.ceil(visual_length / 74) * 18)
        row[2].number_format = "@"  # 分類號是識別碼，保留字母和前導零。
    wb.save(output)
    if issues:
        with output.with_name(output.stem + "_待核對.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(("序號", "書目資訊", "URL", "原因"))
            writer.writerows(issues)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="網站匯出的 .xls/.xlsx 路徑；省略時使用『待處理』中最新的檔案")
    parser.add_argument("--live", action="store_true", help="開啟 Chrome，由使用者登入後直接讀取個人書單")
    parser.add_argument("--delay", type=float, default=0.5, help="書目頁請求間隔（秒）")
    args = parser.parse_args()
    if args.live and args.input:
        parser.error("--live 與 --input 不可同時使用")
    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    if args.live:
        books, session = collect_live_books()
        today = date.today()
        label = f"個人書單{today.year - 1911:03d}{today.month:02d}{today.day:02d}"
    else:
        candidates = [p for p in INPUT_DIR.iterdir() if p.suffix.lower() in (".xls", ".xlsx")]
        source = args.input or (max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None)
        if source is None:
            parser.error(f"請把匯出的檔案放在 {INPUT_DIR}，或指定 --input")
        books = read_input(source)
        session = requests.Session()
        label = source.stem
    if not books:
        raise RuntimeError("來源中沒有書目。")
    rows, issues = fetch_results(books, session, max(args.delay, 0))
    output = OUTPUT_DIR / f"{label}_已填分類號.xlsx"
    save_results(output, rows, issues)
    print(f"完成：{len(rows)} 筆，待核對 {len(issues)} 筆。\n{output}")
    return 0 if not issues else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"錯誤：{error}", file=sys.stderr)
        sys.exit(1)
