"""雙擊開啟圖書館檢測視窗。"""

from __future__ import annotations

import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
RUNNER = ROOT / "run_and_notify.py"
REPORT_DIR = ROOT / ".local" / "reports"
SUITES = ("全部", "關鍵字查詢", "館藏查詢", "網路書店推薦", "新書輪播")
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
        self.root.title("亞洲大學圖書館｜圖書館檢測")
        self.root.geometry("860x620")
        self.root.minsize(680, 460)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.running = False
        self.stop_requested = False
        self.closing = False

        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="圖書館自動檢測", font=("Microsoft JhengHei UI", 18, "bold")).pack(anchor="w")
        ttk.Label(frame, text="選擇檢測項目後按「開始檢測」；進度會顯示在下方。").pack(anchor="w", pady=(4, 16))

        choices = ttk.Frame(frame)
        choices.pack(fill="x")
        ttk.Label(choices, text="檢測項目").pack(side="left", padx=(0, 8))
        self.suite = tk.StringVar(value="全部")
        self.suite_box = ttk.Combobox(choices, textvariable=self.suite, values=SUITES, state="readonly", width=20)
        self.suite_box.pack(side="left")

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

    def start(self, line_test: bool = False) -> None:
        if self.running:
            return
        if not PYTHON.is_file():
            messagebox.showerror("尚未安裝環境", "找不到專案的 .venv\\Scripts\\python.exe。\n請先依 README 執行 setup.ps1。")
            return
        if not RUNNER.is_file():
            messagebox.showerror("找不到檢測程式", f"找不到 {RUNNER.name}")
            return
        command = build_command(self.suite.get(), self.send_line.get(), self.show_browser.get(),
                                line_test, self.broadcast.get())
        self.running = True
        self.stop_requested = False
        self.start_button.configure(state="disabled")
        self.line_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.suite_box.configure(state="disabled")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.status.set("正在執行 LINE 連線測試..." if line_test else f"正在執行：{self.suite.get()}")
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
                    self.suite_box.configure(state="readonly")
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
