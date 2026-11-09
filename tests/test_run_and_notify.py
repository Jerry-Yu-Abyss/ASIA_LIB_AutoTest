import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_and_notify as notify
from 圖書館 import 帳號登入 as login_module
from 圖書館 import 關鍵字查詢 as keyword_module
from 圖書館 import 網頁載入 as loading_module
from 圖書館.帳號登入 import login
from selenium.common.exceptions import WebDriverException


USER_ID = "U" + "a" * 32


class LineRunnerTests(unittest.TestCase):
    def test_print_book_positions_skip_electronic_resources(self):
        class Driver:
            def __init__(self):
                self.types = ["書目-電子資源:單行本"] + [keyword_module.PRINT_BOOK_TYPE] * 10

            def find_elements(self, by, selector):
                if selector == keyword_module.RESULT_BOX_SELECTOR:
                    return [Box(book_type) for book_type in self.types]
                return []

        class Box:
            def __init__(self, book_type):
                self.book_type = book_type

            def find_elements(self, by, selector):
                return [Icon(self.book_type)] if selector == keyword_module.BOOK_TYPE_SELECTOR else []

        class Icon:
            def __init__(self, alt):
                self.alt = alt

            def get_attribute(self, name):
                return self.alt if name == "alt" else None

        driver = Driver()
        self.assertEqual(keyword_module.print_book_indices(driver), list(range(1, 11)))

    def test_only_four_runnable_catalog_scripts_are_scheduled(self):
        self.assertEqual(
            [script for _, script, _ in notify.SUITES],
            ["關鍵字查詢.py", "館藏查詢.py", "網路書店推薦.py", "新書輪播.py"],
        )

    def test_only_one_suite_still_sends_three_line_messages(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(notify, "REPORT_DIR", Path(directory)), \
             patch.object(notify, "load_line_config", return_value=("token", USER_ID)), \
             patch.object(notify, "run_suite", return_value=(
                 1, [{"suite": "新書輪播", "name": "書名", "passed": False,
                      "reason": "缺圖", "classification": "不適用（封面測試）",
                      "url": notify.SUITES[3][2]}], Path(directory) / "test.log"
             )) as run, \
             patch.object(notify, "send_line_messages") as send, \
             patch.object(sys, "argv", ["run_and_notify.py", "--only", "新書輪播"]), \
             redirect_stdout(StringIO()):
            result = notify.main()
        self.assertEqual(result, 1)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][0], "新書輪播")
        messages = send.call_args.args[2]
        self.assertEqual(len(messages), 3)
        self.assertIn("整體：0/1 項通過", messages[0])
        self.assertIn("未通過❌:新書輪播", messages[0])
        self.assertIn("缺圖", messages[1])

    def test_load_config_from_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "line.local.json"
            path.write_text(json.dumps({"channel_access_token": "secret", "user_id": USER_ID}), encoding="utf-8")
            with patch.dict("os.environ", {"LINE_CHANNEL_ACCESS_TOKEN": "", "LINE_USER_ID": ""}):
                self.assertEqual(notify.load_line_config(path), ("secret", USER_ID))

    def test_send_three_messages_in_one_request(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        with patch.object(notify, "urlopen", return_value=Response()) as call:
            notify.send_line_messages("secret", USER_ID, ["摘要", "失敗", "通過"])
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, notify.LINE_PUSH_URL)
        self.assertEqual([m["text"] for m in json.loads(request.data)["messages"]], ["摘要", "失敗", "通過"])
        self.assertNotIn("secret", request.data.decode("utf-8"))

    def test_all_four_tests_show_browser_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "圖書館"
            scripts.mkdir()
            for _, script, _ in notify.SUITES:
                (scripts / script).write_text("import sys\nprint('PROGRESS', flush=True)\nprint(' '.join(sys.argv), flush=True)\n", encoding="utf-8")
            with patch.object(notify, "ROOT", root), patch.object(notify, "REPORT_DIR", root):
                for suite in notify.SUITES:
                    with redirect_stdout(StringIO()) as output:
                        code, _, log = notify.run_suite(suite, None, 180, 1800, "test")
                    self.assertEqual(code, 0)
                    self.assertIn("PROGRESS", output.getvalue())
                    self.assertNotIn("--headless", log.read_text(encoding="utf-8"))
                    self.assertIn("--non-interactive", log.read_text(encoding="utf-8"))
                    self.assertIn("--report-json", log.read_text(encoding="utf-8"))
                with redirect_stdout(StringIO()):
                    _, _, log = notify.run_suite(notify.SUITES[0], None, 180, 1800, "background", headless=True)
                self.assertIn("--headless", log.read_text(encoding="utf-8"))

    def test_runner_keeps_timeout_with_live_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "圖書館"
            scripts.mkdir()
            (scripts / "關鍵字查詢.py").write_text(
                "import time\nprint('STARTED', flush=True)\ntime.sleep(3)\n", encoding="utf-8"
            )
            with patch.object(notify, "ROOT", root), patch.object(notify, "REPORT_DIR", root), redirect_stdout(StringIO()) as output:
                code, _, log = notify.run_suite(notify.SUITES[0], None, 180, 1, "timeout")
            self.assertEqual(code, 1)
            self.assertIn("STARTED", output.getvalue())
            self.assertIn("執行超過 1 秒", log.read_text(encoding="utf-8"))

    def test_connection_timeout_is_reported_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "圖書館"
            scripts.mkdir()
            (scripts / "館藏查詢.py").write_text(
                "print('[FAIL] 圖書館網站連線逾時，請稍後再試或檢查網路')\nraise SystemExit(1)\n",
                encoding="utf-8",
            )
            with patch.object(notify, "ROOT", root), patch.object(notify, "REPORT_DIR", root), redirect_stdout(StringIO()):
                code, cases, _ = notify.run_suite(notify.SUITES[1], None, 180, 10, "offline")
        self.assertEqual(code, 1)
        self.assertIn("圖書館網站連線逾時", cases[0]["reason"])

    def test_browser_connection_timeout_closes_driver(self):
        class Driver:
            closed = False
            attempts = 0

            def execute_script(self, *_):
                pass

            def set_page_load_timeout(self, *_):
                pass

            def get(self, *_):
                self.attempts += 1
                raise WebDriverException("net::ERR_CONNECTION_TIMED_OUT")

            def quit(self):
                self.closed = True

        driver = Driver()
        with patch.object(keyword_module.ChromeDriverManager, "install", return_value="driver"), \
             patch.object(keyword_module.webdriver, "Chrome", return_value=driver), \
             redirect_stdout(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "圖書館網站連線逾時"):
                keyword_module.open_page()
        self.assertTrue(driver.closed)
        self.assertEqual(driver.attempts, 4)

    def test_connection_timeout_reloads_up_to_three_times(self):
        class Driver:
            attempts = 0

            def get(self, *_):
                self.attempts += 1
                if self.attempts < 3:
                    raise WebDriverException("net::ERR_CONNECTION_TIMED_OUT")

        driver = Driver()
        with redirect_stdout(StringIO()) as output:
            loading_module.get_with_retries(driver, "https://aulib.asia.edu.tw/webpac/search.cfm")
        self.assertEqual(driver.attempts, 3)
        self.assertIn("重新載入 2/3", output.getvalue())

    def test_other_browser_error_does_not_reload(self):
        class Driver:
            attempts = 0

            def get(self, *_):
                self.attempts += 1
                raise WebDriverException("invalid session id")

        driver = Driver()
        with self.assertRaises(WebDriverException):
            loading_module.get_with_retries(driver, "https://aulib.asia.edu.tw/webpac/search.cfm")
        self.assertEqual(driver.attempts, 1)

    def test_summary_and_details_include_codes_but_no_urls(self):
        from datetime import datetime, timezone
        cases = notify.normalize("館藏查詢", [{
            "language": "中文", "word": "歷史", "url": "https://aulib.asia.edu.tw/webpac/search.cfm?q=x",
            "books": {"1": {"classification": "123", "url": "https://aulib.asia.edu.tw/webpac/detail.cfm?id=1"},
                      "5": {"classification": "456", "url": "https://aulib.asia.edu.tw/webpac/detail.cfm?id=5"},
                      "10": {"classification": "789", "url": "https://aulib.asia.edu.tw/webpac/detail.cfm?id=10"}},
            "errors": []
        }], 0, notify.SUITES[1][2])
        messages = notify.build_messages([{"name": "館藏查詢", "code": 0, "cases": cases}], datetime.now(timezone.utc))
        self.assertEqual(len(messages), 3)
        self.assertIn("整體：1/1 項通過", messages[0])
        self.assertIn("未通過❌:無", messages[0])
        self.assertIn("✅ 第 1 筆｜書名：未取得\n    分類號：123", messages[2])
        self.assertNotIn("https://", "\n".join(messages))
        self.assertIn("detail.cfm?id=1", cases[0]["books"][0]["url"])
        self.assertIn("無", messages[1])

    def test_summary_lists_failed_suite_names_without_case_counts(self):
        from datetime import datetime, timezone
        runs = [
            {"name": "關鍵字查詢", "code": 1, "cases": [{"suite": "關鍵字查詢", "name": "A", "passed": False, "reason": "",
                                                     "classification": "未取得", "url": notify.SUITES[0][2]}]},
            {"name": "館藏查詢", "code": 1, "cases": [{"suite": "館藏查詢", "name": "B", "passed": False, "reason": "",
                                                     "classification": "未取得", "url": notify.SUITES[1][2]}]},
            {"name": "網路書店推薦", "code": 0, "cases": [{"suite": "網路書店推薦", "name": "C", "passed": True, "reason": "",
                                                       "classification": "不適用", "url": notify.SUITES[2][2]}]},
            {"name": "新書輪播", "code": 0, "cases": [{"suite": "新書輪播", "name": "D", "passed": True, "reason": "",
                                                   "classification": "不適用", "url": notify.SUITES[3][2]}]},
        ]
        summary = notify.build_messages(runs, datetime.now(timezone.utc))[0]
        self.assertEqual(len(summary.splitlines()), 4)
        self.assertIn("整體：2/4 項通過", summary)
        self.assertIn("未通過❌:關鍵字查詢, 館藏查詢", summary)

    def test_no_holdings_reports_book_title(self):
        cases = notify.normalize("關鍵字查詢", [{
            "keyword": "歷史", "success": False, "reason": "第 1 筆：查無館藏",
            "books": {"1": {"name": "台灣史", "classification": "查無館藏"},
                      "5": {"name": "世界史", "classification": "200"},
                      "10": {"name": "文化史", "classification": "300"}},
        }], 1, notify.SUITES[0][2])
        message = notify.detail_message("未通過", cases)
        self.assertIn("❌ 第 1 筆｜書名：台灣史\n    分類號：查無館藏", message)
        self.assertNotIn("原因：第 1 筆：查無館藏", message)
        self.assertIn("✅ 第 5 筆｜書名：世界史", message)
        self.assertNotIn("https://", message)

    def test_other_failure_reason_remains_after_no_holdings_is_marked(self):
        case = {"suite": "館藏查詢", "name": "中文 科技", "reason": "第 1 筆：查無館藏；第 5 筆：載入逾時",
                "books": [{"position": 1, "name": "台灣史", "classification": "查無館藏", "reason": ""},
                          {"position": 5, "name": "世界史", "classification": "未取得", "reason": ""}]}
        message = notify.detail_message("未通過", [case])
        self.assertIn("原因：第 5 筆：載入逾時", message)
        self.assertNotIn("原因：第 1 筆：查無館藏", message)

    def test_failed_case_does_not_include_url(self):
        cases = notify.normalize("新書輪播", [{"section": "新書", "name": "A", "success": False,
            "reason": "缺圖", "url": "https://evil.example/?token=secret"}], 1, notify.SUITES[3][2])
        message = notify.detail_message("失敗", cases)
        self.assertIn("缺圖", message)
        self.assertNotIn("secret", message)
        self.assertNotIn("https://", message)
        self.assertIn(notify.SUITES[3][2], cases[0]["url"])

    def test_url_embedded_in_reason_is_removed_from_line(self):
        case = {"suite": "新書輪播", "name": "測試", "reason": "失敗 https://example.test/path",
                "classification": "未取得", "url": "https://aulib.asia.edu.tw/webpac/search.cfm"}
        message = notify.detail_message("失敗", [case])
        self.assertNotIn("https://", message)
        self.assertIn("未取得", message)

    def test_gemini_503_is_transient(self):
        error = HTTPError("https://example.invalid", 503, "Unavailable", None, None)
        with patch.object(login_module, "urlopen", side_effect=error):
            with self.assertRaises(login_module.GeminiTransientError):
                login_module.recognize_captcha(b"png", {"gemini_api_key": "dummy"})

    def test_transient_error_uses_backoff_with_five_captcha_images(self):
        class Image:
            screenshot_as_png = b"png"

        config = {"captcha": {"gemini_api_key": "dummy"}}
        with patch.object(login_module, "open_login_form", return_value=Image()), \
             patch.object(login_module, "refresh_captcha", return_value=Image()) as refresh, \
             patch.object(login_module, "recognize_captcha", side_effect=login_module.GeminiTransientError("HTTP 503")) as recognize, \
             patch.object(login_module.random, "uniform", return_value=0), \
             patch.object(login_module.time, "sleep") as sleep, \
             redirect_stdout(StringIO()):
            with self.assertRaisesRegex(RuntimeError, "已達 5 次上限"):
                login(None, "https://aulib.asia.edu.tw/webpac/recommend.cfm", config, "gemini", False)
        self.assertEqual(recognize.call_count, 5)
        self.assertEqual(refresh.call_count, 4)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2, 4, 8])

    def test_captcha_waits_for_nonzero_loaded_image(self):
        class Image:
            def __init__(self, width):
                self.size = {"width": width, "height": 20}

            def is_displayed(self):
                return True

            def get_property(self, name):
                return {"complete": True, "naturalWidth": self.size["width"]}[name]

        first, second = Image(0), Image(40)

        class Driver:
            def __init__(self):
                self.images = iter((first, second))

            def find_element(self, *_):
                return next(self.images)

        class Wait:
            def __init__(self, driver, _timeout):
                self.driver = driver

            def until(self, condition):
                self.assertion = condition(self.driver)
                if self.assertion:
                    raise AssertionError("零寬圖片不應被接受")
                return condition(self.driver)

        with patch.object(login_module, "WebDriverWait", Wait):
            self.assertIs(login_module.wait_for_captcha_image(Driver()), second)

    def test_refresh_reopens_login_when_new_image_does_not_load(self):
        class Driver:
            def find_element(self, *_):
                return self

            def click(self):
                return None

        class Wait:
            def __init__(self, *_):
                pass

            def until(self, *_):
                return True

        marker = object()
        with patch.object(login_module, "WebDriverWait", Wait), \
             patch.object(login_module, "wait_for_captcha_image", side_effect=login_module.CaptchaImageTimeout("未載入")), \
             patch.object(login_module, "open_login_form", return_value=marker) as reopen:
            result = login_module.refresh_captcha(Driver(), object(), "https://aulib.asia.edu.tw/webpac/recommend.cfm", {})
        self.assertIs(result, marker)
        reopen.assert_called_once()

    def test_non_interactive_manual_captcha_stops_before_browser(self):
        with self.assertRaisesRegex(RuntimeError, "無人值守模式不可使用手動驗證碼"):
            login(None, "https://aulib.asia.edu.tw/webpac/recommend.cfm", {}, "manual", False)


if __name__ == "__main__":
    unittest.main()
