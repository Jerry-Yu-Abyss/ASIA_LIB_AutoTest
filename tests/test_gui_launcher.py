"""確認雙擊視窗產生的檢測指令。"""

import importlib.machinery
import importlib.util
from pathlib import Path
import queue
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("gui_launcher", str(ROOT / "啟動檢測.pyw"))
spec = importlib.util.spec_from_loader(loader.name, loader)
gui = importlib.util.module_from_spec(spec)
loader.exec_module(gui)


class GuiCommandTests(unittest.TestCase):
    def test_single_suite_shows_browser_and_sends_line(self):
        command = gui.build_command("網路書店推薦", send_line=True, show_browser=True)
        self.assertEqual(command[-2:], ["--only", "網路書店推薦"])
        self.assertNotIn("--headless", command)
        self.assertNotIn("--no-line", command)

    def test_all_suites_without_line_and_browser(self):
        command = gui.build_command("全部", send_line=False, show_browser=False)
        self.assertNotIn("--only", command)
        self.assertIn("--no-line", command)
        self.assertIn("--headless", command)

    def test_line_connection_button_only_sends_test(self):
        command = gui.build_command("全部", send_line=False, show_browser=False, line_test=True)
        self.assertEqual(command[-1], "--send-test")
        self.assertNotIn("--no-line", command)

    def test_broadcast_is_explicit_in_gui_command(self):
        command = gui.build_command("全部", send_line=True, show_browser=True, broadcast=True)
        self.assertIn("--broadcast", command)
        self.assertNotIn("--no-line", command)
        test_command = gui.build_command("全部", send_line=False, show_browser=True,
                                         line_test=True, broadcast=True)
        self.assertEqual(test_command[-2:], ["--send-test", "--broadcast"])

    def test_gui_decodes_unicode_output_when_parent_uses_cp950(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "output.py"
            script.write_text("print('中文📚', flush=True)\n", encoding="utf-8")
            window = object.__new__(gui.TestWindow)
            window.events = queue.Queue()
            window.process = None
            window.stop_requested = False
            with patch.dict("os.environ", {"PYTHONIOENCODING": "cp950"}):
                window.worker([sys.executable, "-u", str(script)])
            events = []
            while not window.events.empty():
                events.append(window.events.get())
        self.assertIn(("output", "中文📚\n"), events)
        self.assertIn(("done", 0), events)


if __name__ == "__main__":
    unittest.main()
