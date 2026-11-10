"""複製到另一個路徑或電腦後，舊環境不能被當成可用。"""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from 圖書館.環境檢查 import environment_ready


class EnvironmentLocationTests(unittest.TestCase):
    def test_copy_to_other_path_or_machine_requires_reinstall(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "來源"
            destination = Path(directory) / "新位置"
            for root in (source, destination):
                scripts = root / ".venv" / "Scripts"
                scripts.mkdir(parents=True)
                (scripts / "python.exe").touch()
                (root / ".venv" / ".project-install.json").write_text(
                    json.dumps({"projectRoot": str(source), "machine": "OLD-PC"}), encoding="utf-8"
                )
            with patch.dict(os.environ, {"COMPUTERNAME": "OLD-PC"}):
                self.assertTrue(environment_ready(source))
                self.assertFalse(environment_ready(destination))
            with patch.dict(os.environ, {"COMPUTERNAME": "NEW-PC"}):
                self.assertFalse(environment_ready(source))


if __name__ == "__main__":
    unittest.main()
