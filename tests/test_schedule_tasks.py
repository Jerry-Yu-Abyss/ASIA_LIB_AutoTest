"""排程設定與 Windows 工作 XML 的檢查。"""

import sys
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from 排程設置 import schedule_tasks as schedule


class ScheduleTests(unittest.TestCase):
    def test_schedule_paths_still_point_to_project_root(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(schedule.ROOT, root)
        self.assertEqual(schedule.RUNNER, root / "LINE通知" / "run_and_notify.py")
        self.assertEqual(schedule.CONFIG, root / "config" / "排程.local.json")

    def test_multiple_times_and_weekdays(self):
        settings = {"frequency": "weekly", "times": "18:30，9:00; 18:30", "days": [4, 0],
                    "suite": "館藏查詢", "send_line": False, "broadcast": False,
                    "show_browser": False}
        validated = schedule.validate(settings)
        self.assertEqual(validated["times"], "09:00, 18:30")
        xml = ET.fromstring(schedule.task_xml(validated, [str(schedule.PYTHON), "-u", str(schedule.RUNNER),
                                                               "--only", "館藏查詢", "--no-line", "--headless"]))
        ns = {"t": schedule.NS}
        triggers = xml.findall("t:Triggers/t:CalendarTrigger", ns)
        self.assertEqual(len(triggers), 2)
        for trigger in triggers:
            days = trigger.find("t:ScheduleByWeek/t:DaysOfWeek", ns)
            self.assertEqual([node.tag.rsplit("}", 1)[-1] for node in days], ["Monday", "Friday"])
        self.assertIn("--headless", xml.findtext("t:Actions/t:Exec/t:Arguments", namespaces=ns))

    def test_bad_time_and_missing_weekday(self):
        with self.assertRaises(ValueError):
            schedule.parse_times("25:00")
        with self.assertRaises(ValueError):
            schedule.validate({"frequency": "weekly", "times": "09:00", "days": [], "suite": "全部"})


if __name__ == "__main__":
    unittest.main()
