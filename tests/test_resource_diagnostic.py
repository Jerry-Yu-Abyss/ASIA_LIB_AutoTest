"""題名診斷在跳回登入頁及列表更新時不得報告成功。"""

import unittest
from unittest.mock import Mock, patch
import threading

from 電子資源 import 資源診斷 as diagnostic


class ResourceDiagnosticTests(unittest.TestCase):
    def test_http_200_login_is_not_platform_success(self):
        result = diagnostic.classify_outcome({
            "success": True, "status": "HTTP 200",
            "connection_url": "https://erm.asia.edu.tw/login/",
        })
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "重新導向至登入頁")

    def test_document_redirect_keeps_status_without_login_query_or_headers(self):
        entry = diagnostic.network_entry({
            "method": "Network.requestWillBeSent",
            "params": {"type": "Document", "requestId": "1",
                       "request": {"url": "https://erm.asia.edu.tw/login/?token=secret",
                                   "method": "GET", "headers": {"Cookie": "secret"}},
                       "redirectResponse": {"url": "https://example.org/book/123?key=secret",
                                            "status": 307, "headers": {"Location":
                                                "https://erm.asia.edu.tw/login/?url=secret"}}}})
        self.assertEqual(entry["redirect_status"], 307)
        self.assertEqual(entry["redirect_location"], "https://erm.asia.edu.tw/login/")
        self.assertNotIn("secret", str(entry))

    def test_changed_candidate_blocks_click(self):
        original = {"category": "電子書", "position": 17, "title": "ZUM'97",
                    "href": "https://example.org/book/1", "key": "old"}
        driver = Mock()
        with patch.object(diagnostic, "prepare"), \
             patch.object(diagnostic, "item_at", return_value=(Mock(), "不同的書", "new")), \
             patch.object(diagnostic, "check_connection") as click:
            with self.assertRaisesRegex(RuntimeError, "列表在定位期間變動"):
                diagnostic.inspect_choice(driver, original, Mock())
            click.assert_not_called()

    def test_title_search_finds_partial_match_and_stops_at_last_page(self):
        driver = Mock(current_url="https://erm.asia.edu.tw/er/browse/eb/")
        book = Mock(text="ZUM'97: The Z Formal Specification Notation")
        book.get_attribute.side_effect = lambda key: "https://example.org/book/1" if key == "href" else ""
        other = Mock(text="Another book")
        other.get_attribute.side_effect = lambda key: "https://example.org/book/2" if key == "href" else ""
        report = Mock()
        with patch.object(diagnostic, "open_category"), \
             patch.object(diagnostic, "select_controls"), \
             patch.object(diagnostic, "read_total", return_value=2), \
             patch.object(diagnostic, "visible_resources", return_value=[other, book]), \
             patch.object(diagnostic, "go_to_page") as next_page:
            matches = diagnostic.find_candidates(driver, "電子書", "z formal specification", 5,
                                                  report, threading.Event())
        self.assertEqual([(entry["position"], entry["title"]) for entry in matches],
                         [(2, "ZUM'97: The Z Formal Specification Notation")])
        next_page.assert_not_called()


if __name__ == "__main__":
    unittest.main()
