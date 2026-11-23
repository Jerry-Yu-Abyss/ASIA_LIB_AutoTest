"""雙擊執行：登入、搜尋指定電子資源題名並檢查平台連線。"""

from __future__ import annotations

import base64
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from 電子資源.列表檢測 import CATEGORY_PATHS
from 電子資源.資源診斷 import run


class Window:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("電子資源｜題名連線診斷")
        self.root.geometry("980x780")
        self.root.minsize(760, 610)
        self.events = queue.Queue()
        self.selection = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.report = None
        self.prompt_event = None
        self.dialog = None
        self.closing = False

        area = ttk.Frame(self.root, padding=16)
        area.pack(fill="both", expand=True)
        ttk.Label(area, text="電子資源題名搜尋與連線分析", font=("Microsoft JhengHei UI", 17, "bold")).pack(anchor="w")
        ttk.Label(area, text="使用既有測試帳號登入；逐頁搜尋指定題名，選取結果後才開啟平台。報告儲存於 .local/reports。")\
            .pack(anchor="w", pady=(4, 12))

        row = ttk.Frame(area)
        row.pack(fill="x")
        ttk.Label(row, text="資源類型").pack(side="left")
        self.category = tk.StringVar(value="電子書")
        self.category_box = ttk.Combobox(row, textvariable=self.category, values=tuple(CATEGORY_PATHS),
                                         state="readonly", width=11)
        self.category_box.pack(side="left", padx=(8, 18))
        ttk.Label(row, text="指定題名").pack(side="left")
        self.title = tk.StringVar()
        self.title_entry = ttk.Entry(row, textvariable=self.title)
        self.title_entry.pack(side="left", fill="x", expand=True, padx=(8, 18))
        ttk.Label(row, text="最多搜尋頁數").pack(side="left")
        self.max_pages = tk.StringVar(value="3")
        self.page_box = ttk.Spinbox(row, from_=1, to=30, width=5, textvariable=self.max_pages)
        self.page_box.pack(side="left", padx=(8, 0))

        actions = ttk.Frame(area)
        actions.pack(fill="x", pady=12)
        ttk.Label(actions, text="驗證碼").pack(side="left")
        self.captcha = tk.StringVar(value="自動辨識（失敗時手動輸入）")
        self.captcha_box = ttk.Combobox(actions, textvariable=self.captcha, state="readonly", width=27,
                                        values=("自動辨識（失敗時手動輸入）", "手動輸入"))
        self.captcha_box.pack(side="left", padx=(8, 18))
        self.start_button = ttk.Button(actions, text="登入並搜尋", command=self.start)
        self.start_button.pack(side="left")
        self.inspect_button = ttk.Button(actions, text="分析選取資源", command=self.inspect, state="disabled")
        self.inspect_button.pack(side="left", padx=(8, 0))
        self.stop_button = ttk.Button(actions, text="停止", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="開啟報告資料夾", command=self.open_reports).pack(side="right")

        ttk.Label(area, text="找到的資源（可選取要開啟的那一筆）").pack(anchor="w")
        self.table = ttk.Treeview(area, columns=("position", "title", "url"), show="headings", height=8)
        for key, label, width in (("position", "清單位置", 90), ("title", "題名", 390),
                                  ("url", "資源網址", 400)):
            self.table.heading(key, text=label)
            self.table.column(key, width=width, stretch=key != "position")
        self.table.pack(fill="x", pady=(4, 12))
        self.table.bind("<Double-1>", lambda _event: self.inspect())

        self.status = tk.StringVar(value="尚未開始")
        ttk.Label(area, textvariable=self.status).pack(anchor="w", pady=(0, 6))
        self.log = scrolledtext.ScrolledText(area, wrap="word", state="disabled", font=("Consolas", 10))
        self.log.pack(fill="both", expand=True)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.process_events)

    def append(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self):
        title = self.title.get().strip()
        try:
            pages = int(self.max_pages.get())
        except ValueError:
            pages = 0
        if not title or not 1 <= pages <= 30:
            messagebox.showerror("輸入錯誤", "請填入題名，以及 1～30 頁的搜尋範圍。")
            return
        self.stop_event.clear()
        self.prompt_event = None
        while not self.selection.empty():
            self.selection.get_nowait()
        for entry in self.table.get_children():
            self.table.delete(entry)
        self.start_button.configure(state="disabled")
        self.inspect_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        for control in (self.category_box, self.title_entry, self.page_box, self.captcha_box):
            control.configure(state="disabled")
        self.status.set("正在登入電子資源…")
        self.report = None
        mode = "manual" if self.captcha.get() == "手動輸入" else "tesseract"
        category = self.category.get()

        def job():
            try:
                path = run(category, title, pages, mode, self.ask_captcha,
                           self.choose_candidate, self.send_event, self.stop_event)
                self.send_event("finished", str(path))
            except Exception as exc:
                self.send_event("failure", str(exc).splitlines()[0] or type(exc).__name__)

        self.worker = threading.Thread(target=job, daemon=True)
        self.worker.start()

    def send_event(self, kind, value):
        self.events.put((kind, value))

    def ask_captcha(self, image, message=""):
        signal = threading.Event()
        reply = {}
        self.send_event("captcha", (image.screenshot_as_png, message, signal, reply))
        while not signal.wait(0.2):
            if self.stop_event.is_set():
                raise RuntimeError("操作已取消")
        if not reply.get("answer"):
            raise RuntimeError("驗證碼輸入已取消")
        return reply["answer"]

    def show_captcha(self, value):
        png, message, signal, reply = value
        self.prompt_event = signal
        dialog = tk.Toplevel(self.root)
        self.dialog = dialog
        dialog.title("輸入電子資源驗證碼")
        dialog.transient(self.root)
        dialog.grab_set()
        area = ttk.Frame(dialog, padding=16)
        area.pack(fill="both", expand=True)
        ttk.Label(area, text=message or "請輸入圖片顯示的驗證碼").pack(anchor="w", pady=(0, 10))
        try:
            picture = tk.PhotoImage(data=base64.b64encode(png).decode("ascii"))
            label = ttk.Label(area, image=picture)
            label.image = picture
            label.pack(pady=(0, 10))
        except tk.TclError:
            ttk.Label(area, text="圖片無法顯示；請查看已開啟的瀏覽器。", foreground="red").pack()
        answer = tk.StringVar()
        field = ttk.Entry(area, textvariable=answer)
        field.pack(fill="x")
        field.focus_set()

        def submit():
            reply["answer"] = answer.get().strip()
            signal.set()
            dialog.destroy()
            self.dialog = None

        ttk.Button(area, text="確認", command=submit).pack(pady=(10, 0))
        dialog.bind("<Return>", lambda _event: submit())
        dialog.protocol("WM_DELETE_WINDOW", submit)

    def choose_candidate(self, candidates):
        if not candidates:
            return None
        while not self.stop_event.is_set():
            try:
                return self.selection.get(timeout=0.2)
            except queue.Empty:
                continue
        return None

    def inspect(self):
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo("選擇資源", "請先選取一筆搜尋結果。")
            return
        self.inspect_button.configure(state="disabled")
        self.status.set("正在開啟並分析選取的資源…")
        self.selection.put(int(selected[0]))

    def stop(self):
        self.stop_event.set()
        self.inspect_button.configure(state="disabled")
        self.status.set("正在停止；等待目前瀏覽器操作結束…")
        if self.dialog is not None:
            self.dialog.destroy()
            self.dialog = None
        if self.prompt_event is not None:
            self.prompt_event.set()

    def open_reports(self):
        folder = ROOT / ".local" / "reports"
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def process_events(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append(value)
            elif kind == "captcha":
                if self.stop_event.is_set():
                    value[2].set()
                else:
                    self.show_captcha(value)
            elif kind == "candidates":
                for index, candidate in enumerate(value):
                    self.table.insert("", "end", iid=str(index), values=(
                        candidate["position"], candidate["title"], candidate["href"]))
                if value and not self.stop_event.is_set():
                    self.table.selection_set("0")
                    self.inspect_button.configure(state="normal")
                    self.status.set(f"找到 {len(value)} 筆；請選取後按「分析選取資源」。")
                elif not value:
                    self.status.set("搜尋完成；指定頁數內沒有符合題名的資源。")
            elif kind in ("finished", "failure"):
                if self.closing:
                    self.root.destroy()
                    return
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.inspect_button.configure(state="disabled")
                for control in (self.title_entry, self.page_box):
                    control.configure(state="normal")
                for control in (self.category_box, self.captcha_box):
                    control.configure(state="readonly")
                if kind == "finished":
                    self.report = value
                    self.status.set("分析結束；請查看下方紀錄與 JSON 報告。")
                    self.append(f"完整診斷報告：{value}")
                else:
                    self.status.set("分析失敗")
                    self.append(f"執行錯誤：{value}")
        self.root.after(100, self.process_events)

    def close(self):
        if self.worker is not None and self.worker.is_alive():
            self.closing = True
            self.stop_event.set()
            if self.prompt_event is not None:
                self.prompt_event.set()
            if self.dialog is not None:
                self.dialog.destroy()
                self.dialog = None
            self.status.set("正在結束瀏覽器並寫入報告…")
        else:
            self.root.destroy()


if __name__ == "__main__":
    Window().root.mainloop()
