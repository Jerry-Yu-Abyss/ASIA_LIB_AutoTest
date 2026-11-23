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

    def test_captcha_requires_four_ascii_digits_before_submission(self):
        config = {"username": "example", "password": "example"}
        for mode in ("manual", "tesseract"):
            for answer in ("0123", "123", "12345", "1A23", "１２３４"):
                with self.subTest(mode=mode, answer=answer):
                    form, field, button = Mock(), Mock(), Mock()
                    form.find_elements.return_value = [button]
                    with patch.object(erm, "login_form", return_value=(form, Mock(), Mock())), \
                         patch.object(erm, "captcha_controls", return_value=(field, Mock())), \
                         patch.object(erm, "tesseract_command"), \
                         patch.object(erm, "recognize_tesseract", return_value=[answer] * 3), \
                         patch.object(erm, "WebDriverWait"):
                        prompt = Mock(return_value=answer)
                        if answer == "0123":
                            erm.submit_login(Mock(), config, mode, True, prompt)
                            field.send_keys.assert_called_once_with("0123")
                            button.click.assert_called_once()
                        else:
                            with self.assertRaisesRegex(RuntimeError, "4 位半形數字"):
                                erm.submit_login(Mock(), config, mode, True, prompt)
                            field.send_keys.assert_not_called()
                            button.click.assert_not_called()

    def test_report_and_url_use_electronic_resource_suite(self):
        suite = notify.SUITES[-1]
        self.assertEqual(suite[0], "電子資源登入")
        cases = notify.normalize("電子資源登入", [{"success": True, "url": "https://erm.asia.edu.tw/user/profile/"}], 0, suite[2])
        self.assertTrue(cases[0]["passed"])
        self.assertEqual(cases[0]["url"], "https://erm.asia.edu.tw/user/profile/")
        self.assertEqual(notify.safe_url("https://example.org/", suite[2]), suite[2])


if __name__ == "__main__":
    unittest.main()
