"""電子資源逐批接續及順序變更時的保護。"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from selenium.common.exceptions import (ElementClickInterceptedException,
                                        StaleElementReferenceException, WebDriverException)
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
                for _ in range(3):
                    result = condition(self.driver)
                    if result:
                        return result
                raise AssertionError("列表檢視沒有切換")

        with patch.object(listing, "WebDriverWait", Wait), \
             patch.object(listing, "controls", return_value=(row, Mock(), Mock())):
            listing.choose_list_view(driver)
        row.find_elements.assert_called_with(
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

        with patch.object(listing, "WebDriverWait", Wait), \
             patch.object(listing, "controls", return_value=(row, Mock(), Mock())):
            listing.choose_list_view(driver)
        label.click.assert_not_called()

    def test_dropdown_relocates_element_after_page_replaces_it(self):
        driver, old, fresh = Mock(), Mock(), Mock()
        old.get_attribute.side_effect = StaleElementReferenceException("replaced")
        fresh.get_attribute.return_value = listing.SORT_VALUE
        found = [(Mock(), old, Mock()), (Mock(), fresh, Mock())]

        class Wait:
            def __init__(self, current_driver, _timeout):
                self.driver = current_driver

            def until(self, condition):
                for _ in range(3):
                    result = condition(self.driver)
                    if result:
                        return result
                raise AssertionError("設定值沒有恢復")

        with patch.object(listing, "WebDriverWait", Wait), \
             patch.object(listing, "controls", side_effect=found) as locate:
            listing.set_dropdown(driver, 1, listing.SORT_VALUE, "排序")
        self.assertEqual(locate.call_count, 2)

    def test_navigation_uses_fresh_link_when_click_intercepted(self):
        driver, old, fresh = Mock(), Mock(), Mock()
        old.is_displayed.return_value = True
        old.click.side_effect = ElementClickInterceptedException("offscreen")
        driver.find_elements.return_value = [old]
        driver.find_element.return_value = fresh

        class Wait:
            def __init__(self, current_driver, _timeout):
                self.driver = current_driver

            def until(self, condition):
                return condition(self.driver)

        with patch.object(listing, "WebDriverWait", Wait):
            listing.click_fresh(driver, "//a[@id='nav']", "分類")
        driver.execute_script.assert_any_call("arguments[0].click();", fresh)

    def test_old_category_controls_do_not_count_as_new_list(self):
        driver = Mock(current_url="https://erm.asia.edu.tw/er/browse/db/")
        with patch.object(listing, "controls", return_value=(Mock(), Mock(), Mock())):
            self.assertFalse(listing.category_ready(driver, "電子期刊"))
            self.assertTrue(listing.category_ready(driver, "資料庫"))

    def test_result_count_parses_both_site_languages(self):
        driver = Mock()
        driver.find_elements.return_value = []
        driver.find_element.return_value.text = "查詢結果: 57,159 筆資料"
        self.assertEqual(listing.result_total(driver), 57159)
        driver.find_element.return_value.text = "Search Results: 20 records"
        self.assertEqual(listing.result_total(driver), 20)
        driver.find_elements.return_value = [Mock(text="56,000")]
        self.assertEqual(listing.result_total(driver), 56000)

    def test_visible_resources_use_only_list_main_links(self):
        driver, visible, hidden = Mock(), Mock(), Mock()
        driver.find_elements.return_value = [visible, hidden]
        visible.is_displayed.return_value = True
        hidden.is_displayed.return_value = False
        self.assertEqual(listing.visible_resources(driver), [visible])
        driver.find_elements.assert_called_once_with(By.CSS_SELECTOR, "#content-list .link-main")

    def test_sixty_resumes_at_sixty_one_and_persists_each_item(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            data = 進度.initial()
            進度.set_completed(data, "資料庫", 60, path)
            output = []
            driver = Mock(current_url="https://erm.asia.edu.tw/er/browse/")
            with patch.object(listing, "prepare", return_value=200), patch.object(listing, "configured", return_value=True), \
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
            with patch.object(listing, "prepare", return_value=200), patch.object(listing, "item_at", return_value=(Mock(), "改名", "b" * 64)):
                with self.assertRaisesRegex(RuntimeError, "檢查點不同"):
                    listing.check_category(Mock(), "電子書", data, [], path)
            self.assertEqual(進度.load(path)["categories"]["電子書"]["last_completed"], 1)

    def test_missing_access_link_is_reported_and_retried_next_run(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            data = 進度.initial()
            output = []
            with patch.object(listing, "prepare", return_value=200), patch.object(listing, "configured", return_value=True), \
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
            with patch.object(listing, "prepare", return_value=200), patch.object(listing, "configured", return_value=True), \
                 patch.object(listing, "item_at", side_effect=lambda _, pos: (Mock(), f"條目{pos}", f"{pos:064x}")), \
                 patch.object(listing, "check_connection", side_effect=outcomes):
                listing.check_category(Mock(current_url="https://erm.asia.edu.tw/er/browse/"),
                                       "資料庫", data, output, path)
            self.assertEqual([case["position"] for case in output], [1, 2, 3, 4, 5])
            self.assertEqual(output[0]["reason"], "HTTP 404")
            self.assertEqual(output[0]["connection_state"], "資源不存在")
            self.assertIn("目的頁不存在", output[0]["connection_note"])
            self.assertEqual(output[1]["connection_state"], "可連線")
            self.assertEqual(output[1]["connection_note"], "連線成功。")
            self.assertEqual(進度.load(path)["categories"]["資料庫"]["last_completed"], 5)

    def test_page_boundary_after_one_hundred_requests_page_two(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            data = 進度.initial()
            進度.set_completed(data, "電子期刊", 100, path)
            output = []
            with patch.object(listing, "prepare", return_value=200), patch.object(listing, "configured", return_value=True), \
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

    def test_circular_batches_resume_from_saved_position(self):
        scenarios = [
            (3, 0, [[1, 2, 3, 1, 2], [3, 1, 2, 3, 1]]),
            (1, 0, [[1, 1, 1, 1, 1]]),
            (103, 101, [[102, 103, 1, 2, 3]]),
            (5, 0, [[1, 2, 3, 4, 5], [1, 2, 3, 4, 5]]),
        ]
        for total, last, batches in scenarios:
            with self.subTest(total=total), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "progress.json"
                category = "網路資源"
                進度.set_completed(進度.initial(), category, last, path)
                driver = Mock(current_url="https://erm.asia.edu.tw/er/browse/ir/")
                with patch.object(listing, "prepare", return_value=total), \
                     patch.object(listing, "configured", return_value=True), \
                     patch.object(listing, "go_to_page") as navigate, \
                     patch.object(listing, "item_at", side_effect=lambda _, p: (p, str(p), f"{p:064x}")), \
                     patch.object(listing, "check_connection", return_value={
                         "success": True, "status": "HTTP 200", "connection_url": "https://vendor.example/"
                     }) as check:
                    for expected in batches:
                        output = []
                        listing.check_category(driver, category, 進度.load(path), output, path)
                        self.assertEqual([case["position"] for case in output], expected)
                        self.assertEqual([c.args[1] for c in check.call_args_list], expected)
                        check.reset_mock()
                        record = 進度.load(path)["categories"][category]
                        self.assertEqual(record["last_completed"], expected[-1])
                        self.assertEqual(進度.next_position(record), expected[-1] % total + 1)
                    if total > listing.PER_PAGE:
                        navigate.assert_called_once_with(driver, 1)

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

    def test_http_200_note_is_connection_only(self):
        self.assertEqual(listing.connection_note("HTTP 200", True), "連線成功。")
        self.assertNotIn("HTTP 200", listing.connection_note("HTTP 200", True))
        self.assertIn("拒絕存取", listing.connection_note("HTTP 403", False))
        self.assertIn("伺服器回應錯誤", listing.connection_note("HTTP 503", False))
        self.assertIn("HTTP 狀態未取得", listing.connection_note("頁面已載入（HTTP 狀態不可得）", True))
        self.assertEqual(listing.connection_state("HTTP 403", False), "拒絕存取")
        self.assertEqual(listing.connection_state("HTTP 404", False), "資源不存在")
        self.assertEqual(listing.connection_state("HTTP 429", False), "請求受限")
        self.assertIn("降低檢測頻率", listing.connection_note("HTTP 429", False))

    def test_connection_clicks_only_the_selected_link_main(self):
        driver = Mock(current_url="https://erm.asia.edu.tw/er/browse/db/",
                      current_window_handle="main", window_handles=["main"])
        link = Mock()
        link.get_attribute.return_value = "https://platform.example/resource"
        outcome = {"success": True, "status": "HTTP 200", "connection_url": "https://platform.example/resource"}
        with patch.object(listing, "opened_page"), patch.object(listing, "connection_result", return_value=outcome):
            self.assertEqual(listing.check_connection(driver, link, "資料庫名稱"), outcome)
        link.click.assert_called_once_with()
        driver.find_elements.assert_not_called()

    def test_browser_network_error_is_recorded_for_this_resource(self):
        driver = Mock(current_url="https://erm.asia.edu.tw/er/browse/db/",
                      current_window_handle="main", window_handles=["main"])
        link = Mock()
        link.get_attribute.return_value = "https://platform.example/resource?token=private"
        link.click.side_effect = WebDriverException("net::ERR_CONNECTION_REFUSED")
        result = listing.check_connection(driver, link, "資料庫名稱")
        self.assertEqual(result["status"], "瀏覽器連線錯誤：ERR_CONNECTION_REFUSED")
        self.assertFalse(result["success"])
        self.assertEqual(result["connection_url"], "https://platform.example/resource")

    def test_identity_uses_link_main_name_and_stable_target(self):
        link = Mock(text="資料庫名稱")
        link.get_attribute.side_effect = lambda key: "https://platform.example/item" if key == "href" else ""
        title, key = listing.identity(link)
        self.assertEqual(title, "資料庫名稱")
        self.assertEqual(len(key), 64)
        link.text = ""
        with self.assertRaisesRegex(RuntimeError, "缺少名稱"):
            listing.identity(link)

    def test_list_results_are_individual_line_cases(self):
        fallback = notify.SUITES[-2][2]
        cases = notify.normalize("電子資源列表", [
            {"category": "資料庫", "position": 61, "name": "A", "success": True,
              "reason": "", "status": "HTTP 200", "connection_state": "可連線",
              "connection_note": "連線成功。",
              "url": fallback},
            {"category": "資料庫", "position": 62, "name": "B", "success": False,
              "reason": "HTTP 404", "status": "HTTP 404", "connection_state": "資源不存在",
              "connection_note": "平台已回應，但目的頁不存在。",
              "url": fallback},
        ], 1, fallback)
        self.assertEqual([item["passed"] for item in cases], [True, False])
        self.assertIn("第 61 筆", cases[0]["name"])
        self.assertIn("連線註解：可連線（HTTP 200）：連線成功", notify.detail_message("通過", cases[:1]))
        self.assertIn("連線註解：資源不存在（HTTP 404）：平台已回應，但目的頁不存在", notify.detail_message("失敗", cases[1:]))


if __name__ == "__main__":
    unittest.main()
