import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from 圖書館 import 新書輪播


DETAIL_URL = "https://aulib.asia.edu.tw/webpac/content.cfm?mid=123"


class SanminCoverTests(unittest.TestCase):
    def check_page(self, markup: str) -> bool:
        class Response:
            content = markup.encode("utf-8")

            def raise_for_status(self):
                pass

        with patch.object(新書輪播.requests, "get", return_value=Response()) as get:
            result = 新書輪播.has_sanmin_cover_source(DETAIL_URL)
        get.assert_called_once_with(DETAIL_URL, timeout=20)
        return result

    def test_missing_cover_without_sanmin_source_is_expected(self):
        self.assertFalse(self.check_page(
            '<div class="photo"><img src="templates/img/product_img.jpg"></div>'
        ))

    def test_sanmin_link_means_cover_source_exists(self):
        self.assertTrue(self.check_page(
            '<div class="photo"><a class="btn-light online-book" '
            'href="https://www.sanmin.com.tw/search/index/?ct=ISBN">三民</a></div>'
        ))

    def test_sanmin_image_means_cover_source_exists(self):
        self.assertTrue(self.check_page(
            '<div class="photo"><img src="https://cdnec.sanmin.com.tw/product_images/123/a.jpg"></div>'
        ))

    def test_external_detail_url_is_rejected(self):
        with self.assertRaises(ValueError):
            新書輪播.has_sanmin_cover_source("https://example.com/webpac/content.cfm")

    def test_missing_photo_section_cannot_be_treated_as_no_source(self):
        with self.assertRaises(ValueError):
            self.check_page("<html><body>Service Unavailable</body></html>")


if __name__ == "__main__":
    unittest.main()
