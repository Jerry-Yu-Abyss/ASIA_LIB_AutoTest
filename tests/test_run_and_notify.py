import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_and_notify as notify
from 館藏查詢.帳號登入 import login


USER_ID = "U" + "a" * 32


class LineRunnerTests(unittest.TestCase):
    def test_load_config_from_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "line.local.json"
            path.write_text(json.dumps({"channel_access_token": "secret", "user_id": USER_ID}), encoding="utf-8")
            with patch.dict("os.environ", {"LINE_CHANNEL_ACCESS_TOKEN": "", "LINE_USER_ID": ""}):
                self.assertEqual(notify.load_line_config(path), ("secret", USER_ID))

    def test_send_message_only_includes_summary(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

        with patch.object(notify, "urlopen", return_value=Response()) as call:
            notify.send_line_message("secret", USER_ID, "測試通過")
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, notify.LINE_PUSH_URL)
        self.assertEqual(json.loads(request.data)["messages"][0]["text"], "測試通過")
        self.assertNotIn("secret", request.data.decode("utf-8"))

    def test_run_test_is_non_interactive(self):
        result = subprocess.CompletedProcess([], 1, stdout="[FAIL] 驗證碼\n", stderr="")
        with patch.object(notify.subprocess, "run", return_value=result) as call:
            code, output = notify.run_test(None, 180, 1800)
        self.assertEqual(code, 1)
        self.assertIn("驗證碼", output)
        command = call.call_args.args[0]
        self.assertIn("--non-interactive", command)
        self.assertIn("--headless", command)

    def test_summary_does_not_forward_raw_output(self):
        from datetime import datetime, timezone

        summary = notify.build_summary(1, "[FAIL] 驗證碼；password=secret", datetime.now(timezone.utc))
        self.assertIn("登入／驗證碼", summary)
        self.assertNotIn("secret", summary)

    def test_non_interactive_manual_captcha_stops_before_browser(self):
        with self.assertRaisesRegex(RuntimeError, "無人值守模式不可使用手動驗證碼"):
            login(None, "https://aulib.asia.edu.tw/webpac/recommend.cfm", {}, "manual", False)


if __name__ == "__main__":
    unittest.main()
