"""我的書房登入後導覽與報告格式。"""

import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from 圖書館.檢測功能 import 我的書房 as shelf
import run_and_notify as notify


class ShelfTests(unittest.TestCase):
    def test_shelf_runs_after_bookstore_with_automatic_captcha(self):
        names = [suite[0] for suite in notify.SUITES]
        self.assertEqual(names, ["館藏查詢", "網路書店推薦", "我的書房", "新書輪播"])
        from contextlib import redirect_stdout
        from io import StringIO
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "圖書館" / "檢測功能"
            scripts.mkdir(parents=True)
            (scripts / "我的書房.py").write_text("import sys\nprint(' '.join(sys.argv))\n", encoding="utf-8")
            with patch.object(notify, "ROOT", root), patch.object(notify, "REPORT_DIR", root), redirect_stdout(StringIO()):
                _, _, log = notify.run_suite(notify.SUITES[2], None, 180, 480, "test")
            output = log.read_text(encoding="utf-8")
            self.assertIn("--captcha-mode tesseract", output)
            self.assertIn("--non-interactive", output)

    def test_clicks_shelf_link_and_confirms_logged_in_page(self):
        driver = Mock()
        driver.current_url = "https://aulib.asia.edu.tw/webpac/shelf_user.cfm"
        link = Mock()
        with patch.object(shelf, "WebDriverWait") as wait:
            wait.return_value.until.side_effect = [link, True, True]
            result = shelf.check_shelf(driver)
        link.click.assert_called_once_with()
        self.assertTrue(result["success"])
        self.assertEqual(result["url"], driver.current_url)

    def test_failure_is_reported_without_book_positions(self):
        cases = notify.normalize("我的書房", [{"success": False, "reason": "尚未登入",
            "url": "https://aulib.asia.edu.tw/webpac/shelf_user.cfm"}],
            1, "https://aulib.asia.edu.tw/webpac/shelf_user.cfm")
        self.assertFalse(cases[0]["passed"])
        self.assertEqual(cases[0]["reason"], "尚未登入")
        self.assertNotIn("books", cases[0])


if __name__ == "__main__":
    unittest.main()
