"""建立與移除本專案的 Windows 工作排程。"""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "排程.local.json"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
RUNNER = ROOT / "run_and_notify.py"
TASK_NAME = "AU Library Automated Test"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
LABELS = ("一", "二", "三", "四", "五", "六", "日")


def parse_times(value: str) -> list[str]:
    times = []
    for part in re.split(r"[,，;；\s]+", value.strip()):
        if not part:
            continue
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", part)
        if not match or int(match[1]) > 23 or int(match[2]) > 59:
            raise ValueError("時間請輸入 24 小時制 HH:MM，以逗號分隔，例如 09:00, 18:30")
        normalized = f"{int(match[1]):02d}:{int(match[2]):02d}"
        if normalized not in times:
            times.append(normalized)
    if not times:
        raise ValueError("請至少輸入一個執行時間")
    return sorted(times)


def validate(settings: dict) -> dict:
    if settings.get("frequency") not in ("daily", "weekly"):
        raise ValueError("請選擇每日或每週")
    times = parse_times(settings.get("times", ""))
    days = settings.get("days", [])
    if not isinstance(days, list) or any(not isinstance(d, int) or d not in range(7) for d in days):
        raise ValueError("星期設定不正確")
    days = sorted(set(days))
    if settings["frequency"] == "weekly" and not days:
        raise ValueError("每週排程請至少選擇一天")
    if settings.get("suite") not in ("全部", "館藏查詢", "網路書店推薦", "我的書房", "新書輪播"):
        raise ValueError("檢測項目不正確")
    return {"frequency": settings["frequency"], "times": ", ".join(times), "days": days,
            "suite": settings["suite"], "send_line": bool(settings.get("send_line")),
            "broadcast": bool(settings.get("broadcast")), "show_browser": bool(settings.get("show_browser"))}


def task_xml(settings: dict, command: list[str]) -> bytes:
    settings = validate(settings)
    ET.register_namespace("", NS)
    def add(parent, tag, value=None):
        node = ET.SubElement(parent, f"{{{NS}}}{tag}")
        if value is not None:
            node.text = str(value)
        return node

    task = ET.Element(f"{{{NS}}}Task", {"version": "1.2"})
    info = add(task, "RegistrationInfo")
    add(info, "Description", "亞洲大學圖書館自動檢測；由啟動檢測.pyw 管理")
    triggers = add(task, "Triggers")
    for time in parse_times(settings["times"]):
        trigger = add(triggers, "CalendarTrigger")
        add(trigger, "StartBoundary", f"{date.today().isoformat()}T{time}:00")
        add(trigger, "Enabled", "true")
        if settings["frequency"] == "daily":
            add(add(trigger, "ScheduleByDay"), "DaysInterval", "1")
        else:
            week = add(trigger, "ScheduleByWeek")
            add(week, "WeeksInterval", "1")
            days = add(week, "DaysOfWeek")
            for index in settings["days"]:
                add(days, WEEKDAYS[index])
    principals = add(task, "Principals")
    principal = add(principals, "Principal")
    domain, user = os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", "")
    if user:
        add(principal, "UserId", f"{domain}\\{user}" if domain else user)
    add(principal, "LogonType", "InteractiveToken")
    add(principal, "RunLevel", "LeastPrivilege")
    options = add(task, "Settings")
    add(options, "MultipleInstancesPolicy", "IgnoreNew")
    add(options, "DisallowStartIfOnBatteries", "false")
    add(options, "StopIfGoingOnBatteries", "false")
    add(options, "AllowHardTerminate", "true")
    add(options, "StartWhenAvailable", "true")
    add(options, "ExecutionTimeLimit", "PT3H")
    add(options, "Enabled", "true")
    actions = add(task, "Actions")
    action = add(actions, "Exec")
    add(action, "Command", command[0])
    add(action, "Arguments", subprocess.list2cmdline(command[1:]))
    add(action, "WorkingDirectory", str(ROOT))
    return ET.tostring(task, encoding="utf-16", xml_declaration=True)


def _schtasks(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["schtasks.exe", *args], capture_output=True, text=True,
                            errors="replace", creationflags=NO_WINDOW, check=False)
    return result


def exists() -> bool:
    return _schtasks("/Query", "/TN", TASK_NAME).returncode == 0


def save(settings: dict, command: list[str]) -> None:
    settings = validate(settings)
    if not PYTHON.is_file():
        raise RuntimeError("找不到專案 Python，請先執行 setup.ps1")
    if not RUNNER.is_file():
        raise RuntimeError("找不到檢測程式 run_and_notify.py")
    xml = task_xml(settings, command)
    with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as file:
        path = Path(file.name)
        file.write(xml)
    try:
        result = _schtasks("/Create", "/TN", TASK_NAME, "/XML", str(path), "/F")
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip() or "無法建立工作排程")
    finally:
        path.unlink(missing_ok=True)
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


def remove() -> None:
    if exists():
        result = _schtasks("/Delete", "/TN", TASK_NAME, "/F")
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip() or "無法移除工作排程")
    CONFIG.unlink(missing_ok=True)


def load() -> dict | None:
    if not CONFIG.is_file():
        return None
    return validate(json.loads(CONFIG.read_text(encoding="utf-8-sig")))
