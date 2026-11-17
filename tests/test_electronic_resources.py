"""電子資源登入與報告的關鍵判定。"""

import unittest
from unittest.mock import Mock, patch

from LINE通知 import run_and_notify as notify
from 電子資源 import 登入檢測 as erm


class ElectronicResourcesTests(unittest.TestCase):
    def test_redirect_to_member_page_without_password_confirms_login(self):
        driver = Mock(current_url="https://erm.asia.edu.tw/user/profile/")
        driver.find_elements.return_value = []
        self.assertTrue(erm.authenticated(driver))
        driver.current_url = "https://erm.asia.edu.tw/user/login/"
        self.assertFalse(erm.authenticated(driver))
        driver.current_url = "https://example.org/user/profile/"
        self.assertFalse(erm.authenticated(driver))

    def test_no_captcha_does_not_invoke_ocr(self):
        form, username, password, button = (Mock() for _ in range(4))
        form.find_elements.return_value = [button]
        with patch.object(erm, "login_form", return_value=(form, username, password)), \
             patch.object(erm, "captcha_controls", return_value=(None, None)), \
             patch.object(erm, "tesseract_command") as ocr, \
             patch.object(erm, "WebDriverWait") as wait:
            wait.return_value.until.return_value = True
            erm.submit_login(Mock(), {"username": "example", "password": "example"}, "tesseract", False)
        button.click.assert_called_once()
        ocr.assert_not_called()

    def test_manual_captcha_rejected_before_opening_form_in_scheduled_run(self):
        with patch.object(erm, "login_form") as form:
            with self.assertRaisesRegex(RuntimeError, "無人值守模式"):
                erm.submit_login(None, {}, "manual", False)
        form.assert_not_called()

    def test_report_and_url_use_electronic_resource_suite(self):
        suite = notify.SUITES[-1]
        self.assertEqual(suite[0], "電子資源")
        cases = notify.normalize("電子資源", [{"success": True, "url": "https://erm.asia.edu.tw/user/profile/"}], 0, suite[2])
        self.assertTrue(cases[0]["passed"])
        self.assertEqual(cases[0]["url"], "https://erm.asia.edu.tw/user/profile/")
        self.assertEqual(notify.safe_url("https://example.org/", suite[2]), suite[2])


if __name__ == "__main__":
    unittest.main()
