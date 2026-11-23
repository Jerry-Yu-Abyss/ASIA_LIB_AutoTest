"""四個電子資源列表的本機檢測進度；逐筆安全寫入。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile


CATEGORIES = ("資料庫", "電子期刊", "電子書", "網路資源")
ROOT = Path(__file__).resolve().parents[1]
PROGRESS_FILE = ROOT / ".local" / "電子資源進度.json"
LOCK_FILE = ROOT / ".local" / "電子資源進度.lock"


def initial() -> dict:
    return {"version": 1, "categories": {
        name: {"last_completed": 0, "last_key": None, "updated_at": None}
        for name in CATEGORIES
    }}


def validate(data: object) -> dict:
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("categories"), dict):
        raise ValueError("電子資源進度 JSON 格式不正確")
    categories = data["categories"]
    if set(categories) != set(CATEGORIES):
        raise ValueError("電子資源進度缺少分類或含未知分類")
    for name in CATEGORIES:
        record = categories[name]
        if not isinstance(record, dict) or type(record.get("last_completed")) is not int or record["last_completed"] < 0:
            raise ValueError(f"{name} 的已測筆數必須是非負整數")
        key = record.get("last_key")
        total = record.get("last_total")
        if total is not None and (type(total) is not int or total <= 0 or record["last_completed"] > total):
            raise ValueError(f"{name} 的清單總筆數不正確")
        if key is not None and (not isinstance(key, str) or len(key) != 64 or
                                any(ch not in "0123456789abcdef" for ch in key)):
            raise ValueError(f"{name} 的檢查點格式不正確")
        if key and record["last_completed"] == 0:
            raise ValueError(f"{name} 的檢查點與筆數不一致")
    return data


def load(path: Path = PROGRESS_FILE) -> dict:
    if not path.exists():
        return initial()
    try:
        return validate(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"無法讀取電子資源進度：{exc}；為避免跳筆，請先修正 JSON") from exc


def save(data: dict, path: Path = PROGRESS_FILE) -> None:
    validate(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".tmp",
                                         prefix="erm_", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def exclusive(path: Path = LOCK_FILE):
    """防止 GUI、排程或第二個視窗同時修改同一份 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as file:
        if file.tell() == 0 and path.stat().st_size == 0:
            file.write(b"0")
            file.flush()
        file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("電子資源進度正在被另一個檢測或視窗使用") from exc
        try:
            yield
        finally:
            file.seek(0)
            if os.name == "nt":
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def next_position(record: dict) -> int:
    return 1 if record["last_completed"] == record.get("last_total") else record["last_completed"] + 1


def advance(data: dict, category: str, position: int, key: str, path: Path = PROGRESS_FILE,
            *, total: int | None = None) -> None:
    record = data["categories"][category]
    expected = 1 if record["last_completed"] == total else record["last_completed"] + 1
    if position != expected:
        raise RuntimeError(f"{category} 進度不連續，未寫入檢查點")
    record.update(last_completed=position, last_key=key, last_total=total,
                  updated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    save(data, path)


def set_completed(data: dict, category: str, count: int, path: Path = PROGRESS_FILE) -> None:
    """人工指定下次起點；清除舊清單的比對檢查點。"""
    if category not in CATEGORIES or type(count) is not int or count < 0:
        raise ValueError("分類或筆數不正確")
    data["categories"][category].update(last_completed=count, last_key=None, last_total=None,
                                         updated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    save(data, path)
