"""驗證碼排錯報告應包含圖片與辨識狀態，不能洩露帳密。"""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from 圖書館.檢測功能 import 驗證碼認證 as diagnostic_script


class CaptchaDiagnosticTests(unittest.TestCase):
    def test_report_saves_image_and_model_results_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(sys, "argv", ["驗證碼認證.py", "--captcha-mode", "tesseract",
                                       "--output-dir", directory]), \
             patch.object(diagnostic_script, "load_config", return_value={
                 "username": "private-user", "password": "private-password", "captcha": {}}), \
             patch.object(diagnostic_script, "open_page", return_value=Mock()), \
             patch.object(diagnostic_script, "login") as login, redirect_stdout(StringIO()):
            def record_events(_driver, _target, _config, _mode, **kwargs):
                recorder = kwargs["diagnostic"]
                recorder({"attempt": 1, "stage": "image_ready"}, b"png")
                recorder({"attempt": 1, "stage": "recognition", "model": "model-a", "answer": "AB12"}, None)
                recorder({"attempt": 1, "stage": "accepted"}, None)
            login.side_effect = record_events
            self.assertEqual(diagnostic_script.main(), 0)
            run_dir = next(Path(directory).iterdir())
            report = (run_dir / "驗證碼報告.json").read_text(encoding="utf-8")
            self.assertEqual((run_dir / "驗證碼_1.png").read_bytes(), b"png")
            self.assertTrue(json.loads(report)["success"])
            self.assertNotIn("private-user", report)
            self.assertNotIn("private-password", report)


if __name__ == "__main__":
    unittest.main()
