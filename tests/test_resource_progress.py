"""電子資源逐批接續及順序變更時的保護。"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from selenium.webdriver.common.by import By

from LINE通知 import run_and_notify as notify
from 電子資源 import 列表檢測 as listing, 進度


class ResourceProgressTests(unittest.TestCase):
    def test_list_view_clicks_label_for_book_info_radio(self):
        driver, row, label, radio = Mock(), Mock(), Mock(), Mock()
        row.find_elements.return_value = [label]
        label.is_displayed.return_value = True
        driver.find_element.return_value = radio
        radio.is_selected.side_effect = [False, True]

        class Wait:
            def __init__(self, current_driver, _timeout):
                self.driver = current_driver

            def until(self, condition):
                return condition(self.driver)

        with patch.object(listing, "WebDriverWait", Wait):
            listing.choose_list_view(driver, row)
        row.find_elements.assert_called_once_with(
            By.CSS_SELECTOR, 'label.btn.btn-outline-accessory.btn-sm[for="bookInfo-list"]')
        label.click.assert_called_once_with()

    def test_list_view_already_selected_does_not_click_again(self):
        driver, row, label = Mock(), Mock(), Mock()
        row.find_elements.return_value = [label]
        label.is_displayed.return_value = True
        driver.find_element.return_value.is_selected.return_value = True

        class Wait:
            def __init__(self, current_driver, _timeout):
                self.driver = current_driver

            def until(self, condition):
                return condition(self.driver)

        with patch.object(listing, "WebDriverWait", Wait):
            listing.choose_list_view(driver, row)
        label.click.assert_not_called()

    def test_result_count_parses_both_site_languages(self):
        driver = Mock()
        driver.find_element.return_value.text = "查詢結果: 57,159 筆資料"
        self.assertEqual(listing.result_total(driver), 57159)
        driver.find_element.return_value.text = "Search Results: 20 records"
        self.assertEqual(listing.result_total(driver), 20)

    def test_resource_row_accepts_plain_div_without_card_or_list_item(self):
        intro, row, title = Mock(), Mock(), Mock()
        intro.find_element.return_value = row
        intro.is_displayed.return_value = True
        title.is_displayed.return_value = True
        title.text = "資料庫名稱"
        row.find_elements.side_effect = lambda by, selector: (
            [intro] if by == By.XPATH else [title] if selector == "h2, h3, h4, h5, .title" else [])
        self.assertIs(listing.resource_row(intro), row)

    def test_sixty_resumes_at_sixty_one_and_persists_each_item(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            data = 進度.initial()
            進度.set_completed(data, "資料庫", 60, path)
            output = []
            driver = Mock(current_url="https://erm.asia.edu.tw/er/browse/")
            with patch.object(listing, "prepare"), patch.object(listing, "configured", return_value=True), \
                 patch.object(listing, "item_at", side_effect=lambda _, pos: (Mock(), f"書目{pos}", f"{pos:064x}")), \
                  patch.object(listing, "check_connection", return_value={
                      "success": True, "status": "HTTP 200", "connection_url": "https://vendor.example/"}):
                listing.check_category(driver, "資料庫", data, output, path)
            self.assertEqual([case["position"] for case in output], list(range(61, 66)))
            self.assertEqual(進度.load(path)["categories"]["資料庫"]["last_completed"], 65)
            self.assertEqual(進度.load(path)["categories"]["電子書"]["last_completed"], 0)

    def test_changed_previous_item_stops_without_advancing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            data = 進度.initial()
            進度.advance(data, "電子書", 1, "a" * 64, path)
            with patch.object(listing, "prepare"), patch.object(listing, "item_at", return_value=(Mock(), "改名", "b" * 64)):
                with self.assertRaisesRegex(RuntimeError, "檢查點不同"):
                    listing.check_category(Mock(), "電子書", data, [], path)
            self.assertEqual(進度.load(path)["categories"]["電子書"]["last_completed"], 1)

    def test_missing_access_link_is_reported_and_retried_next_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            data = 進度.initial()
            output = []
            with patch.object(listing, "prepare"), patch.object(listing, "configured", return_value=True), \
                  patch.object(listing, "item_at", return_value=(Mock(), "入口未找到", "a" * 64)), \
                  patch.object(listing, "check_connection", side_effect=RuntimeError("找不到資源入口")):
                listing.check_category(Mock(current_url="https://erm.asia.edu.tw/er/browse/"),
                                       "網路資源", data, output, path)
            self.assertEqual(len(output), 1)
            self.assertFalse(output[0]["success"])
            self.assertEqual(output[0]["status"], "未檢查")
            self.assertEqual(進度.load(path)["categories"]["網路資源"]["last_completed"], 0)

    def test_http_failure_is_recorded_and_batch_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            data = 進度.initial()
            output = []
            outcomes = [{"success": False, "status": "HTTP 404", "connection_url": "https://vendor.example/missing"}]
            outcomes.extend({"success": True, "status": "HTTP 200", "connection_url": "https://vendor.example/"}
                            for _ in range(4))
            with patch.object(listing, "prepare"), patch.object(listing, "configured", return_value=True), \
                 patch.object(listing, "item_at", side_effect=lambda _, pos: (Mock(), f"條目{pos}", f"{pos:064x}")), \
                 patch.object(listing, "check_connection", side_effect=outcomes):
                listing.check_category(Mock(current_url="https://erm.asia.edu.tw/er/browse/"),
                                       "資料庫", data, output, path)
            self.assertEqual([case["position"] for case in output], [1, 2, 3, 4, 5])
            self.assertEqual(output[0]["reason"], "HTTP 404")
            self.assertEqual(進度.load(path)["categories"]["資料庫"]["last_completed"], 5)

    def test_page_boundary_after_one_hundred_requests_page_two(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            data = 進度.initial()
            進度.set_completed(data, "電子期刊", 100, path)
            output = []
            with patch.object(listing, "prepare"), patch.object(listing, "configured", return_value=True), \
                 patch.object(listing, "go_to_page") as next_page, \
                 patch.object(listing, "item_at", side_effect=lambda _, pos: (Mock(), f"條目{pos}", f"{pos:064x}")), \
                  patch.object(listing, "check_connection", return_value={
                      "success": True, "status": "HTTP 200", "connection_url": "https://vendor.example/"}):
                listing.check_category(Mock(current_url="https://erm.asia.edu.tw/er/browse/"),
                                       "電子期刊", data, output, path)
            next_page.assert_called_once_with(unittest.mock.ANY, 2)
            self.assertEqual([case["position"] for case in output], [101, 102, 103, 104, 105])

    def test_invalid_json_and_nonsequential_save_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "修正 JSON"):
                進度.load(path)
            data = 進度.initial()
            with self.assertRaisesRegex(RuntimeError, "不連續"):
                進度.advance(data, "網路資源", 3, "c" * 64, path)
            self.assertEqual(path.read_text(encoding="utf-8"), "{broken")

    def test_external_page_http_status_and_browser_errors(self):
        driver = Mock()
        driver.current_url = "https://publisher.example/item?token=secret"
        driver.title = "Resource homepage"
        driver.find_element.return_value.text = "Available"
        driver.execute_script.return_value = 200
        result = listing.connection_result(driver)
        self.assertEqual(result, {"success": True, "status": "HTTP 200",
                                  "connection_url": "https://publisher.example/item"})
        driver.execute_script.return_value = 404
        self.assertEqual(listing.connection_result(driver)["status"], "HTTP 404")
        self.assertFalse(listing.connection_result(driver)["success"])
        driver.current_url = "chrome-error://chromewebdata/"
        self.assertEqual(listing.connection_result(driver)["status"], "瀏覽器連線錯誤")

    def test_connection_link_prefers_resource_title_over_unrelated_external_link(self):
        scope = Mock()
        report, external, title = Mock(), Mock(), Mock()
        scope.find_elements.return_value = [report, external, title]
        for link in (report, external, title):
            link.is_displayed.return_value = True
            link.tag_name = "a"
            link.get_attribute.side_effect = lambda attribute: "" if attribute != "href" else "https://publisher.example/"
        report.text = "問題通報"
        external.text = "出版社"
        title.text = "資料庫名稱"
        self.assertIs(listing.connection_link(scope, "資料庫名稱"), title)

    def test_detail_page_with_multiple_unlabelled_external_links_is_ambiguous(self):
        scope = Mock()
        links = [Mock(text="Publisher"), Mock(text="Support")]
        scope.find_elements.return_value = links
        for link in links:
            link.is_displayed.return_value = True
            link.tag_name = "a"
            link.get_attribute.side_effect = lambda attribute: "" if attribute != "href" else "https://vendor.example/"
        self.assertIsNone(listing.connection_link(scope, "條目名稱", detail=True))

    def test_list_results_are_individual_line_cases(self):
        fallback = notify.SUITES[-2][2]
        cases = notify.normalize("電子資源列表", [
            {"category": "資料庫", "position": 61, "name": "A", "success": True,
             "reason": "", "url": fallback},
            {"category": "資料庫", "position": 62, "name": "B", "success": False,
             "reason": "簡介未載入", "url": fallback},
        ], 1, fallback)
        self.assertEqual([item["passed"] for item in cases], [True, False])
        self.assertIn("第 61 筆", cases[0]["name"])
        self.assertIn("簡介未載入", notify.detail_message("失敗", cases[1:]))


if __name__ == "__main__":
    unittest.main()
