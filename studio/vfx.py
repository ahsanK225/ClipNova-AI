"""Custom VFX overlay manager for PeakCut / ClipNova AI.
Stores user-uploaded VFX overlay videos/GIFs (.mp4, .mov, .webm, .gif)
and resolves paths safely for Studio live preview and FFmpeg rendering.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from . import config

USER_VFX_DIR = config.DATA_DIR / "vfx" / "uploads"
ALLOWED_VFX_EXTS = (".mp4", ".mov", ".webm", ".gif")


def ensure_dirs() -> None:
    USER_VFX_DIR.mkdir(parents=True, exist_ok=True)


def _probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0 and r.stdout:
            dur = float(json.loads(r.stdout).get("format", {}).get("duration") or 0.0)
            if dur > 0:
                return round(min(15.0, max(0.3, dur)), 2)
    except Exception:
        pass
    return 2.0


def list_custom() -> list[dict[str, Any]]:
    ensure_dirs()
    out: list[dict[str, Any]] = []
    for p in sorted(USER_VFX_DIR.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or p.suffix.lower() not in ALLOWED_VFX_EXTS:
            continue
        vid = f"custom_{p.stem}"
        title = p.stem.replace("_", " ").replace("-", " ").title()
        out.append({
            "id": vid,
            "name": f"✨ {title}",
            "cat": "Custom",
            "desc": f"Custom uploaded VFX ({p.name})",
            "url": f"/api/vfx/file/{vid}",
            "ext": p.suffix.lower(),
            "custom": True,
            "duration": _probe_duration(p),
        })
    return out


def resolve_path(vfx_id: str) -> Path | None:
    if not vfx_id or not vfx_id.startswith("custom_"):
        return None
    ensure_dirs()
    stem = vfx_id[len("custom_"):]
    for p in USER_VFX_DIR.iterdir():
        if p.is_file() and p.stem == stem and p.suffix.lower() in ALLOWED_VFX_EXTS:
            return p
    return None


def save_upload(filename: str, content: bytes) -> dict[str, Any]:
    """Validate and save a custom VFX video/GIF (< 50MB)."""
    ensure_dirs()
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_VFX_EXTS:
        raise ValueError("Unsupported VFX format. Please upload MP4, MOV, WebM, or GIF.")
    if len(content) > 50 * 1024 * 1024:
        raise ValueError("VFX file is too large (maximum 50MB).")

    stem = re.sub(r"[^\w\-]", "_", Path(filename).stem)[:40].strip("_") or "vfx"
    target_path = USER_VFX_DIR / f"{stem}{ext}"
    counter = 1
    while target_path.exists():
        target_path = USER_VFX_DIR / f"{stem}_{counter}{ext}"
        counter += 1

    target_path.write_bytes(content)
    vid = f"custom_{target_path.stem}"
    title = target_path.stem.replace("_", " ").replace("-", " ").title()
    return {
        "id": vid,
        "name": f"✨ {title}",
        "cat": "Custom",
        "desc": f"Custom uploaded VFX ({target_path.name})",
        "url": f"/api/vfx/file/{vid}",
        "ext": ext,
        "custom": True,
        "duration": _probe_duration(target_path),
    }
