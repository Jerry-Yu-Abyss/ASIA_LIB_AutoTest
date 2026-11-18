"""雙擊開啟圖書館檢測視窗。"""

from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from 排程設置 import schedule_tasks
from 圖書館.環境檢查 import environment_ready
from 電子資源 import 進度


ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
RUNNER = ROOT / "LINE通知" / "run_and_notify.py"
REPORT_DIR = ROOT / ".local" / "reports"
FUNCTIONS = {"圖書館": ("館藏查詢", "網路書店推薦", "我的書房", "新書輪播"),
             "電子資源": ("電子資源列表", "電子資源登入")}
SUITES = ("全部", *FUNCTIONS["圖書館"], *FUNCTIONS["電子資源"])
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def build_command(suite: str, send_line: bool, show_browser: bool, line_test: bool = False,
                  broadcast: bool = False) -> list[str]:
    command = [str(PYTHON), "-u", str(RUNNER)]
    if line_test:
        return command + ["--send-test"] + (["--broadcast"] if broadcast else [])
    if suite not in SUITES:
        raise ValueError("未知的測試項目")
    if suite != "全部":
        command += ["--only", suite]
    if not send_line:
        command.append("--no-line")
    elif broadcast:
        command.append("--broadcast")
    if not show_browser:
        command.append("--headless")
    return command


class TestWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("亞洲大學圖書館｜系統檢測")
        self.root.geometry("860x760")
        self.root.minsize(680, 620)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.running = False
        self.stop_requested = False
        self.closing = False

        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="圖書館與電子資源自動檢測", font=("Microsoft JhengHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="選擇檢測項目後按「開始檢測」；進度會顯示在下方。").pack(anchor="w", pady=(4, 16))

        choices = ttk.Frame(frame)
        choices.pack(fill="x")
        ttk.Label(choices, text="功能選單").pack(side="left", padx=(0, 8))
        self.category = tk.StringVar(value="圖書館")
        self.category_box = ttk.Combobox(choices, textvariable=self.category,
                                         values=tuple(FUNCTIONS), state="readonly", width=12)
        self.category_box.pack(side="left")
        self.category_box.bind("<<ComboboxSelected>>", self.change_category)
        ttk.Label(choices, text="檢測項目").pack(side="left", padx=(16, 8))
        self.suite = tk.StringVar(value=FUNCTIONS["圖書館"][0])
        self.suite_box = ttk.Combobox(choices, textvariable=self.suite,
                                      values=FUNCTIONS["圖書館"], state="readonly", width=18)
        self.suite_box.pack(side="left")
        self.all_suites = tk.BooleanVar(value=True)
        self.all_box = ttk.Checkbutton(choices, text="全部（圖書館＋電子資源）",
                                       variable=self.all_suites, command=self.refresh_choices)
        self.all_box.pack(side="left", padx=(18, 0))
        self.refresh_choices()

        progress_row = ttk.Frame(frame)
        progress_row.pack(fill="x", pady=(10, 0))
        self.progress_status = tk.StringVar(value="電子資源進度尚未讀取")
        ttk.Label(progress_row, textvariable=self.progress_status).pack(side="left")
        self.progress_button = ttk.Button(progress_row, text="查看／調整進度", command=self.edit_progress)
        self.progress_button.pack(side="left", padx=(10, 0))
        self.refresh_progress()

        self.send_line = tk.BooleanVar(value=True)
        self.broadcast = tk.BooleanVar(value=False)
        self.show_browser = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="完成後傳送 LINE 結果", variable=self.send_line).pack(anchor="w", pady=(14, 0))
        ttk.Checkbutton(frame, text="傳送給所有官方帳號好友（群發會使用訊息額度）",
                        variable=self.broadcast).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(frame, text="顯示瀏覽器操作", variable=self.show_browser).pack(anchor="w", pady=(4, 14))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(0, 12))
        self.start_button = ttk.Button(buttons, text="開始檢測", command=self.start)
        self.start_button.pack(side="left")
        self.line_button = ttk.Button(buttons, text="只測 LINE 連線", command=lambda: self.start(line_test=True))
        self.line_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(buttons, text="停止檢測", command=self.stop, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Button(buttons, text="開啟報告資料夾", command=self.open_reports).pack(side="right")

        schedule = ttk.LabelFrame(frame, text="自動排程（Windows 工作排程器）", padding=10)
        schedule.pack(fill="x", pady=(0, 12))
        row = ttk.Frame(schedule)
        row.pack(fill="x")
        self.frequency = tk.StringVar(value="daily")
        ttk.Radiobutton(row, text="每日", variable=self.frequency, value="daily",
                        command=self.refresh_schedule).pack(side="left")
        ttk.Radiobutton(row, text="每週", variable=self.frequency, value="weekly",
                        command=self.refresh_schedule).pack(side="left", padx=(12, 0))
        ttk.Label(row, text="時間（可填多個）").pack(side="left", padx=(20, 6))
        self.times = tk.StringVar(value="09:00")
        ttk.Entry(row, textvariable=self.times, width=24).pack(side="left")
        ttk.Label(row, text="例如 09:00, 18:30").pack(side="left", padx=8)
        day_row = ttk.Frame(schedule)
        day_row.pack(fill="x", pady=(7, 0))
        ttk.Label(day_row, text="星期").pack(side="left", padx=(0, 7))
        self.days = [tk.BooleanVar(value=index == 0) for index in range(7)]
        self.day_checks = []
        for index, label in enumerate(schedule_tasks.LABELS):
            check = ttk.Checkbutton(day_row, text=label, variable=self.days[index])
            check.pack(side="left", padx=(0, 8))
            self.day_checks.append(check)
        action_row = ttk.Frame(schedule)
        action_row.pack(fill="x", pady=(8, 0))
        ttk.Button(action_row, text="儲存／更新排程", command=self.save_schedule).pack(side="left")
        ttk.Button(action_row, text="移除排程", command=self.remove_schedule).pack(side="left", padx=8)
        self.schedule_status = tk.StringVar(value="尚未設定排程")
        ttk.Label(action_row, textvariable=self.schedule_status).pack(side="left", padx=12)
        ttk.Label(schedule, text="排程使用上方的檢測與 LINE 選項；電腦需開機且目前使用者已登入。"
                  ).pack(anchor="w", pady=(7, 0))
        self.refresh_schedule()
        self.load_schedule()

        self.status = tk.StringVar(value="尚未開始")
        ttk.Label(frame, textvariable=self.status).pack(anchor="w", pady=(0, 6))
        self.log = scrolledtext.ScrolledText(frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.drain_events)

    def append(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line)
        self.log.see("end")
        self.log.configure(state="disabled")

    def change_category(self, _event=None) -> None:
        self.suite.set(FUNCTIONS[self.category.get()][0])
        self.refresh_choices()

    def refresh_choices(self) -> None:
        choices = FUNCTIONS[self.category.get()]
        self.suite_box.configure(values=choices)
        if self.suite.get() not in choices:
            self.suite.set(choices[0])
        state = "disabled" if self.running or self.all_suites.get() else "readonly"
        self.category_box.configure(state=state)
        self.suite_box.configure(state=state)

    def refresh_progress(self) -> None:
        try:
            records = 進度.load()["categories"]
            self.progress_status.set("電子資源下次：" + "、".join(
                f"{name} {records[name]['last_completed'] + 1}" for name in 進度.CATEGORIES))
        except RuntimeError as exc:
            self.progress_status.set(str(exc))

    def edit_progress(self) -> None:
        if self.running:
            return
        try:
            current = 進度.load()["categories"]
        except RuntimeError as exc:
            messagebox.showerror("無法開啟進度", str(exc))
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("電子資源檢測進度")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="已測至第幾筆？下次會從下一筆開始，每類最多測 5 筆。").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12))
        entries = {}
        for index, name in enumerate(進度.CATEGORIES, start=1):
            ttk.Label(body, text=name).grid(row=index, column=0, sticky="w", pady=4)
            value = tk.StringVar(value=str(current[name]["last_completed"]))
            ttk.Entry(body, textvariable=value, width=12).grid(row=index, column=1, padx=12)
            ttk.Label(body, text=f"目前下次第 {current[name]['last_completed'] + 1} 筆").grid(
                row=index, column=2, sticky="w")
            entries[name] = value
        ttk.Label(body, text="手動變更筆數會清除該分類的順序檢查點。",
                  foreground="#9a5710").grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 6))

        def save_progress() -> None:
            if self.running:
                messagebox.showerror("檢測執行中", "請等待檢測結束再調整進度", parent=dialog)
                return
            try:
                values = {name: int(value.get()) for name, value in entries.items()}
                if any(count < 0 for count in values.values()):
                    raise ValueError("筆數不可小於 0")
                with 進度.exclusive():
                    data = 進度.load()
                    for name, count in values.items():
                        if count != data["categories"][name]["last_completed"]:
                            進度.set_completed(data, name, count)
            except (RuntimeError, ValueError, OSError) as exc:
                messagebox.showerror("無法儲存進度", str(exc), parent=dialog)
                return
            self.refresh_progress()
            dialog.destroy()

        def open_json() -> None:
            try:
                with 進度.exclusive():
                    if not 進度.PROGRESS_FILE.exists():
                        進度.save(進度.initial())
                os.startfile(進度.PROGRESS_FILE)
            except (RuntimeError, OSError) as exc:
                messagebox.showerror("無法開啟 JSON", str(exc), parent=dialog)

        actions = ttk.Frame(body)
        actions.grid(row=6, column=0, columnspan=3, sticky="e", pady=(8, 0))
        ttk.Button(actions, text="開啟 JSON", command=open_json).pack(side="left", padx=(0, 12))
        ttk.Button(actions, text="儲存", command=save_progress).pack(side="left")
        ttk.Button(actions, text="取消", command=dialog.destroy).pack(side="left", padx=(10, 0))
        dialog.grab_set()

    def refresh_schedule(self) -> None:
        state = "normal" if self.frequency.get() == "weekly" else "disabled"
        for check in self.day_checks:
            check.configure(state=state)

    def load_schedule(self) -> None:
        try:
            settings = schedule_tasks.load()
            present = schedule_tasks.exists()
        except (OSError, ValueError) as exc:
            self.schedule_status.set(f"無法讀取排程：{exc}")
            return
        if settings:
            self.frequency.set(settings["frequency"])
            self.times.set(settings["times"])
            for index, value in enumerate(self.days):
                value.set(index in settings["days"])
            self.all_suites.set(settings["run_all"])
            selected = settings["suite"] if settings["suite"] in SUITES[1:] else FUNCTIONS["圖書館"][0]
            self.category.set("電子資源" if selected in FUNCTIONS["電子資源"] else "圖書館")
            self.suite.set(selected)
            self.refresh_choices()
            self.send_line.set(settings["send_line"])
            self.broadcast.set(settings["broadcast"])
            self.show_browser.set(settings["show_browser"])
            self.refresh_schedule()
        self.schedule_status.set("排程已啟用" if present else "尚未設定排程")

    def save_schedule(self) -> None:
        settings = {"frequency": self.frequency.get(), "times": self.times.get(),
                    "days": [index for index, value in enumerate(self.days) if value.get()],
                    "suite": self.suite.get(), "run_all": self.all_suites.get(),
                    "send_line": self.send_line.get(),
                    "broadcast": self.broadcast.get(), "show_browser": self.show_browser.get()}
        try:
            settings = schedule_tasks.validate(settings)
            command = build_command("全部" if settings["run_all"] else settings["suite"], settings["send_line"],
                                    settings["show_browser"], broadcast=settings["broadcast"])
            schedule_tasks.save(settings, command)
        except (OSError, ValueError, RuntimeError) as exc:
            messagebox.showerror("無法儲存排程", str(exc))
            return
        self.schedule_status.set("排程已啟用")
        messagebox.showinfo("排程已儲存", "Windows 工作排程器已建立或更新自動檢測。")

    def remove_schedule(self) -> None:
        try:
            schedule_tasks.remove()
        except (OSError, RuntimeError) as exc:
            messagebox.showerror("無法移除排程", str(exc))
            return
        self.schedule_status.set("尚未設定排程")

    def start(self, line_test: bool = False) -> None:
        if self.running:
            return
        if not environment_ready(ROOT):
            messagebox.showerror("尚未安裝環境", "專案環境尚未在這台電腦及目前位置建立。\n請先開啟環境設置資料夾執行一鍵安裝。")
            return
        if not RUNNER.is_file():
            messagebox.showerror("找不到檢測程式", f"找不到 {RUNNER.name}")
            return
        selected = "全部" if self.all_suites.get() else self.suite.get()
        command = build_command(selected, self.send_line.get(), self.show_browser.get(),
                                line_test, self.broadcast.get())
        self.running = True
        self.stop_requested = False
        self.start_button.configure(state="disabled")
        self.line_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.suite_box.configure(state="disabled")
        self.category_box.configure(state="disabled")
        self.all_box.configure(state="disabled")
        self.progress_button.configure(state="disabled")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.status.set("正在執行 LINE 連線測試..." if line_test else f"正在執行：{selected}")
        self.append("開始執行，請稍候...\n\n")
        threading.Thread(target=self.worker, args=(command,), daemon=True).start()

    def worker(self, command: list[str]) -> None:
        try:
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "utf-8"
            process = subprocess.Popen(
                command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=NO_WINDOW, env=environment,
            )
            self.process = process
            if self.stop_requested:
                self.kill_process(process)
            for line in process.stdout:
                self.events.put(("output", line))
            process.stdout.close()
            code = process.wait()
            self.events.put(("done", code))
        except OSError as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.process = None

    def kill_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, creationflags=NO_WINDOW, check=False)

    def stop(self) -> None:
        if not self.running or self.stop_requested:
            return
        self.stop_requested = True
        self.status.set("正在停止檢測...")
        self.stop_button.configure(state="disabled")
        process = self.process
        if process is not None:
            threading.Thread(target=self.kill_process, args=(process,), daemon=True).start()

    def drain_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "output":
                    self.append(str(value))
                else:
                    self.running = False
                    self.start_button.configure(state="normal")
                    self.line_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.all_box.configure(state="normal")
                    self.progress_button.configure(state="normal")
                    self.refresh_choices()
                    self.refresh_progress()
                    if kind == "error":
                        self.status.set("無法啟動檢測")
                        self.append(f"\n[FAIL] {value}\n")
                    elif self.stop_requested:
                        self.status.set("已停止")
                    elif value == 0:
                        self.status.set("檢測通過")
                    elif value == 1:
                        self.status.set("檢測完成，部分項目未通過")
                    else:
                        self.status.set("檢測或 LINE 發送發生錯誤")
                    if self.closing:
                        self.root.destroy()
                        return
        except queue.Empty:
            pass
        self.root.after(100, self.drain_events)

    def open_reports(self) -> None:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(REPORT_DIR)

    def close(self) -> None:
        if self.running:
            self.closing = True
            self.stop()
        else:
            self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    TestWindow().run()
