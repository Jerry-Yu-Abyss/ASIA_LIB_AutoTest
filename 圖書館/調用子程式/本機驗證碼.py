"""使用本機 Tesseract 對同一張驗證碼做保守的交叉確認。"""

from io import BytesIO
import os
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image, ImageOps


def tesseract_command() -> str:
    configured = os.environ.get("TESSERACT_CMD")
    candidates = [configured, shutil.which("tesseract")]
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(key)
        if base:
            candidates.append(str(Path(base) / "Tesseract-OCR" / "tesseract.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError("找不到 Tesseract；請安裝後設定 TESSERACT_CMD，或將其加入 PATH")


def recognize_tesseract(png: bytes) -> list[str]:
    """以三種放大倍率辨識；呼叫端須自行判定結果是否足夠一致。"""
    command = tesseract_command()
    try:
        original = Image.open(BytesIO(png)).convert("L")
    except (OSError, ValueError):
        raise RuntimeError("驗證碼圖片無法供 Tesseract 讀取") from None
    answers = []
    for scale in (3, 5, 8):
        image = ImageOps.expand(
            original.resize((original.width * scale, original.height * scale), Image.Resampling.LANCZOS),
            border=20, fill=255,
        )
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        try:
            result = subprocess.run(
                [command, "stdin", "stdout", "-l", "eng", "--psm", "8",
                 "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"],
                input=buffer.getvalue(), capture_output=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise RuntimeError("Tesseract 無法執行或辨識逾時") from None
        if result.returncode:
            raise RuntimeError("Tesseract 辨識失敗；請確認英文語言資料已安裝")
        candidate = result.stdout.decode("utf-8", errors="replace").strip()
        answers.append(candidate if re.fullmatch(r"[A-Z0-9]{3,10}", candidate) else "")
    return answers
