import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import run_and_notify as notify
from 館藏查詢 import 帳號登入 as login_module
from 館藏查詢.帳號登入 import login


USER_ID = "U" + "a" * 32


class LineRunnerTests(unittest.TestCase):
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

    def test_all_four_tests_run_in_background(self):
        result = subprocess.CompletedProcess([], 1, stdout="[FAIL] 驗證碼\n", stderr="")
        with tempfile.TemporaryDirectory() as directory, patch.object(notify, "REPORT_DIR", Path(directory)):
            with patch.object(notify.subprocess, "run", return_value=result) as call:
                for suite in notify.SUITES:
                    notify.run_suite(suite, None, 180, 1800, "test")
                    command = call.call_args.args[0]
                    self.assertIn("--headless", command)
                    self.assertIn("--report-json", command)
                    if suite[1] == "網路書店推薦.py":
                        self.assertIn("--non-interactive", command)

    def test_summary_and_details_include_codes_but_no_urls(self):
        from datetime import datetime, timezone
        cases = notify.normalize("中英文查詢", [{
            "language": "中文", "word": "歷史", "url": "https://aulib.asia.edu.tw/webpac/search.cfm?q=x",
            "books": {"1": {"classification": "123", "url": "https://aulib.asia.edu.tw/webpac/detail.cfm?id=1"},
                      "5": {"classification": "456", "url": "https://aulib.asia.edu.tw/webpac/detail.cfm?id=5"},
                      "10": {"classification": "789", "url": "https://aulib.asia.edu.tw/webpac/detail.cfm?id=10"}},
            "errors": []
        }], 0, notify.SUITES[1][2])
        messages = notify.build_messages([{"name": "中英文查詢", "code": 0, "cases": cases}], datetime.now(timezone.utc))
        self.assertEqual(len(messages), 3)
        self.assertIn("未通過：0", messages[0])
        self.assertIn("第1筆 分類號：123", messages[2])
        self.assertNotIn("https://", "\n".join(messages))
        self.assertIn("detail.cfm?id=1", cases[0]["books"][0]["url"])
        self.assertIn("無", messages[1])

    def test_failed_case_does_not_include_url(self):
        cases = notify.normalize("新書封面", [{"section": "新書", "name": "A", "success": False,
            "reason": "缺圖", "url": "https://evil.example/?token=secret"}], 1, notify.SUITES[3][2])
        message = notify.detail_message("失敗", cases)
        self.assertIn("缺圖", message)
        self.assertNotIn("secret", message)
        self.assertNotIn("https://", message)
        self.assertIn(notify.SUITES[3][2], cases[0]["url"])

    def test_url_embedded_in_reason_is_removed_from_line(self):
        case = {"suite": "新書封面", "name": "測試", "reason": "失敗 https://example.test/path",
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
