"""檢查專案環境是否為目前電腦及目前資料夾建立。"""

import json
import os
from pathlib import Path
import socket


def environment_ready(root: Path) -> bool:
    root = root.resolve()
    venv = root / ".venv"
    python = venv / "Scripts" / "python.exe"
    marker = venv / ".project-install.json"
    if not python.is_file() or not marker.is_file():
        return False
    try:
        data = json.loads(marker.read_text(encoding="utf-8-sig"))
        return (isinstance(data, dict)
                and os.path.normcase(os.path.abspath(data.get("projectRoot", ""))) == os.path.normcase(str(root))
                and data.get("machine", "").casefold() == os.environ.get("COMPUTERNAME", socket.gethostname()).casefold())
    except (OSError, ValueError, TypeError, AttributeError):
        return False
