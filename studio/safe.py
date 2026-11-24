"""Small helpers for safe errors and crash-safe atomic file persistence."""
import json
import os
import re
import threading
import time
from pathlib import Path

_PATH = re.compile(r"(?:[A-Za-z]:)?[\\/][^\s'\"]*[\\/][^\s'\"]+")


def friendly(e, limit=600) -> str:
    """An error message for the user: trimmed, with any server file paths removed. A missing ffmpeg, which Windows
    reports only as "the system cannot find the file specified", is said in plain words with what to do."""
    from . import tools
    return tools.explain(e) or _PATH.sub("[file]", str(e)[-limit:])


def atomic_replace(tmp: Path, target: Path, backup: bool = False, attempts: int = 8) -> None:
    """Swap tmp into target safely on Windows with transient PermissionError backoff and optional .bak."""
    if backup and target.is_file():
        bak = target.with_name(f"{target.name}.bak")
        try:
            raw = target.read_bytes()
            stripped = raw.lstrip()
            if raw and b"\x00" not in raw and stripped[:1] in (b"{", b"["):
                bak.write_bytes(raw)
        except OSError:
            pass
    for i in range(attempts):
        try:
            tmp.replace(target)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.05 * (i + 1))


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8", backup: bool = False,
                      mode: int | None = None) -> None:
    """Write text to a unique .tmp sibling and atomically replace target (Windows lock-safe)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding=encoding)
        if mode is not None:
            try:
                tmp.chmod(mode)
            except OSError:
                pass
        atomic_replace(tmp, path, backup=backup)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def load_json_with_backup(path: Path, encoding: str = "utf-8", default=None):
    """Read JSON from path, automatically falling back to sibling .bak if primary is corrupted."""
    path = Path(path)
    for candidate in (path, path.with_name(f"{path.name}.bak")):
        if not candidate.is_file():
            continue
        try:
            raw = candidate.read_text(encoding=encoding)
            if not raw or "\x00" in raw:
                continue
            return json.loads(raw)
        except (OSError, ValueError, TypeError):
            continue
    return default


