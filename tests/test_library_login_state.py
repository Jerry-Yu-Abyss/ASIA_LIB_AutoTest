"""登入送出後，分辨網站提示、登入狀態與目標頁連線問題。"""

import unittest
from unittest.mock import Mock, PropertyMock, patch

from selenium.common.exceptions import NoAlertPresentException, TimeoutException, UnexpectedAlertPresentException

from 圖書館.調用子程式 import 帳號登入 as auth
from 圖書館.調用子程式.網頁載入 import ConnectionTimeout


class LibraryLoginStateTests(unittest.TestCase):
    def setUp(self):
        self.driver = Mock()
        type(self.driver.switch_to).alert = PropertyMock(side_effect=NoAlertPresentException())
        self.events = []
        self.form = self.start_patch("open_login_form")
        self.start_patch("prompt_captcha").return_value = "AB12"
        self.wait = self.start_patch("WebDriverWait").return_value.until
        self.navigate = self.start_patch("get_with_retries")

    def start_patch(self, name):
        patcher = patch.object(auth, name)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def login(self):
        auth.login(self.driver, "https://aulib.asia.edu.tw/webpac/search.cfm", {},
                   diagnostic=lambda event, _: self.events.append(event))

    def test_missing_initial_indicator_can_be_confirmed_on_target(self):
        self.wait.side_effect = [TimeoutException(), True]
        self.login()
        self.form.assert_called_once()
        self.assertEqual(self.events[-1]["stage"], "accepted")

    def test_target_connection_timeout_has_its_own_diagnosis(self):
        self.navigate.side_effect = ConnectionTimeout("連線逾時")
        with self.assertRaisesRegex(RuntimeError, "目標頁連線逾時"):
            self.login()
        self.assertEqual(self.events[-1]["stage"], "target_unavailable")

    def test_target_without_session_reports_missing_indicator(self):
        self.wait.side_effect = [True, TimeoutException()]
        with self.assertRaisesRegex(RuntimeError, "目標頁未顯示登出"):
            self.login()
        self.assertEqual(self.events[-1]["stage"], "session_unconfirmed")

    def test_dismissed_account_alert_still_stops_login(self):
        self.wait.side_effect = UnexpectedAlertPresentException("alert", alert_text="帳號已鎖定")
        with self.assertRaisesRegex(RuntimeError, "帳號"):
            self.login()
        self.navigate.assert_not_called()
        self.assertEqual(self.events[-1]["stage"], "account_rejected")
