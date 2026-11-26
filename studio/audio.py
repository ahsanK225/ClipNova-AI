"""Audio management engine for PeakCut / ClipNova AI.
Manages background music tracks, meme sound effects, safe path resolution,
and user-uploaded custom audio.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from . import config

BUILTIN_AUDIO_DIR = config.ROOT / "web" / "audio"
USER_AUDIO_DIR = config.DATA_DIR / "audio" / "uploads"

# Registry of curated built-in viral background tracks and meme sound effects
BUILTIN_TRACKS: list[dict[str, Any]] = [
    {
        "id": "none",
        "title": "None (Original Audio Only)",
        "emoji": "🚫",
        "category": "none",
        "desc": "No background music added; keeps only the original stream sound.",
        "duration": 0,
        "filename": "",
        "url": ""
    },
    {
        "id": "phonk_drift",
        "title": "Phonk Drift Beat",
        "emoji": "🏎️",
        "category": "music",
        "desc": "Fast 808 cowbell & heavy bass for car drifts, chases, and speed.",
        "duration": 24.0,
        "filename": "phonk_drift.mp3",
        "url": "/api/audio/track/phonk_drift"
    },
    {
        "id": "funny_sneaky",
        "title": "Sneaky Snitch (Funny)",
        "emoji": "🕵️",
        "category": "music",
        "desc": "Playful pizzicato tiptoe bounce for hilarious fails & NPC moments.",
        "duration": 20.0,
        "filename": "funny_sneaky.mp3",
        "url": "/api/audio/track/funny_sneaky"
    },
    {
        "id": "dramatic_suspense",
        "title": "Dramatic Suspense",
        "emoji": "🚨",
        "category": "music",
        "desc": "Dark pulsing heartbeat & cinematic tension swell for climax scenes.",
        "duration": 24.0,
        "filename": "dramatic_suspense.mp3",
        "url": "/api/audio/track/dramatic_suspense"
    },
    {
        "id": "hype_trap",
        "title": "Hype Trap Anthem",
        "emoji": "⚡",
        "category": "music",
        "desc": "Aggressive brass stabs & rolling 808s for victory and clutch kills.",
        "duration": 20.0,
        "filename": "hype_trap.mp3",
        "url": "/api/audio/track/hype_trap"
    },
    {
        "id": "chill_lofi",
        "title": "Chill Lo-Fi Breeze",
        "emoji": "☕",
        "category": "music",
        "desc": "Warm Rhodes chords & vinyl crackle for relaxing cruises & chat.",
        "duration": 24.0,
        "filename": "chill_lofi.mp3",
        "url": "/api/audio/track/chill_lofi"
    },
    {
        "id": "sad_violin_l",
        "title": "Sad Violin (L Moment)",
        "emoji": "🎻",
        "category": "music",
        "desc": "Melancholic minor violin phrase for tragic deaths & busted moments.",
        "duration": 18.0,
        "filename": "sad_violin_l.mp3",
        "url": "/api/audio/track/sad_violin_l"
    },
    {
        "id": "vine_boom",
        "title": "Vine Boom Impact",
        "emoji": "💥",
        "category": "meme",
        "desc": "Deep sub-bass explosion impact for punchlines & crazy reveals.",
        "duration": 2.8,
        "filename": "vine_boom.mp3",
        "url": "/api/audio/track/vine_boom"
    },
    {
        "id": "bruh_sound",
        "title": "Bruh Sound Effect",
        "emoji": "🗿",
        "category": "meme",
        "desc": "Classic vocal formant drop for utter disbelief and facepalms.",
        "duration": 1.2,
        "filename": "bruh_sound.mp3",
        "url": "/api/audio/track/bruh_sound"
    },
    {
        "id": "metal_pipe",
        "title": "Metal Pipe Falling",
        "emoji": "🔔",
        "category": "meme",
        "desc": "Chaotic reverberant metallic ringing clang on crashes and sudden hits.",
        "duration": 2.2,
        "filename": "metal_pipe.mp3",
        "url": "/api/audio/track/metal_pipe"
    },
    {
        "id": "airhorn_blast",
        "title": "MLG Airhorn Blast",
        "emoji": "🎺",
        "category": "meme",
        "desc": "3-shot high-energy trumpet fanfare for maximum hype moments.",
        "duration": 1.6,
        "filename": "airhorn_blast.mp3",
        "url": "/api/audio/track/airhorn_blast"
    }
]


def ensure_dirs():
    """Ensure upload directories exist."""
    USER_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


def list_tracks() -> list[dict[str, Any]]:
    """Lists built-in tracks + user-uploaded tracks."""
    ensure_dirs()
    tracks = list(BUILTIN_TRACKS)

    # Scan user uploads
    if USER_AUDIO_DIR.is_dir():
        for p in sorted(USER_AUDIO_DIR.iterdir()):
            if p.is_file() and p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg", ".aac"):
                track_id = f"custom_{p.stem}"
                # Clean title from filename
                display_title = p.stem.replace("_", " ").replace("-", " ").title()
                tracks.append({
                    "id": track_id,
                    "title": display_title,
                    "emoji": "📁",
                    "category": "custom",
                    "desc": f"Custom uploaded audio ({p.name})",
                    "duration": _probe_duration(p),
                    "filename": p.name,
                    "url": f"/api/audio/track/{track_id}"
                })

    return tracks


def get_track_path(track_id: str) -> Path | None:
    """Safely resolves an audio track file path with strict path traversal prevention."""
    if not track_id or track_id == "none":
        return None

    # Sanitize track_id
    if not re.fullmatch(r"[\w\-]+", track_id) or ".." in track_id:
        return None

    # Check built-in tracks
    for t in BUILTIN_TRACKS:
        if t["id"] == track_id and t.get("filename"):
            p = BUILTIN_AUDIO_DIR / t["filename"]
            if p.is_file():
                return p.resolve()

    # Check custom uploads
    if track_id.startswith("custom_"):
        raw_name = track_id[7:]
        ensure_dirs()
        for ext in (".mp3", ".wav", ".m4a", ".ogg", ".aac"):
            p = USER_AUDIO_DIR / f"{raw_name}{ext}"
            if p.is_file():
                return p.resolve()
            # Also check direct filename
            p2 = USER_AUDIO_DIR / raw_name
            if p2.is_file():
                return p2.resolve()

    # Check if track_id is a direct built-in filename
    direct_builtin = BUILTIN_AUDIO_DIR / f"{track_id}.mp3"
    if direct_builtin.is_file():
        return direct_builtin.resolve()

    return None


_DUR_CACHE: dict[str, float] = {}


def _probe_duration(path: Path) -> float:
    key = str(path)
    if key in _DUR_CACHE:
        return _DUR_CACHE[key]
    try:
        import json as _json
        import subprocess as _sp
        r = _sp.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", key],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout:
            d = round(float(_json.loads(r.stdout).get("format", {}).get("duration") or 0.0), 1)
            if d > 0:
                _DUR_CACHE[key] = d
                return d
    except Exception:
        pass
    return 0.0


def save_upload(filename: str, content: bytes) -> dict[str, Any]:
    """Validates and saves custom audio file, or extracts audio from an uploaded video (< 100MB)."""
    import subprocess
    import tempfile

    ensure_dirs()
    ext = Path(filename).suffix.lower()
    audio_exts = (".mp3", ".wav", ".m4a", ".ogg", ".aac")
    video_exts = (".mp4", ".mov", ".mkv", ".webm", ".avi")
    if ext not in audio_exts and ext not in video_exts:
        raise ValueError("Unsupported format. Upload MP3/WAV/M4A/OGG/AAC audio or MP4/MOV/MKV/WebM video.")

    is_video = ext in video_exts
    max_mb = 100 if is_video else 30
    if len(content) > max_mb * 1024 * 1024:
        raise ValueError(f"File is too large (maximum {max_mb}MB).")

    # Sanitize base stem
    stem = re.sub(r"[^\w\-]", "_", Path(filename).stem)[:40].strip("_") or "audio"
    save_ext = ".mp3" if is_video else ext
    target_name = f"{stem}{save_ext}"
    target_path = USER_AUDIO_DIR / target_name

    # Avoid overwrite collision if file with same name exists
    counter = 1
    while target_path.exists():
        target_name = f"{stem}_{counter}{save_ext}"
        target_path = USER_AUDIO_DIR / target_name
        counter += 1

    if is_video:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
            tf.write(content)
            tmp_vid = Path(tf.name)
        try:
            res = subprocess.run(
                ["ffmpeg", "-y", "-v", "error", "-i", str(tmp_vid), "-vn", "-acodec", "libmp3lame", "-q:a", "2", str(target_path)],
                capture_output=True, text=True, timeout=60,
            )
            if res.returncode != 0 or not target_path.is_file() or target_path.stat().st_size < 100:
                target_path.unlink(missing_ok=True)
                raise ValueError("Could not extract audio from this video (no audio track found).")
        finally:
            tmp_vid.unlink(missing_ok=True)
    else:
        target_path.write_bytes(content)

    track_id = f"custom_{target_path.stem}"
    display_title = target_path.stem.replace("_", " ").replace("-", " ").title()

    return {
        "id": track_id,
        "title": display_title,
        "emoji": "🎬" if is_video else "📁",
        "category": "custom",
        "desc": f"Extracted from video ({Path(filename).name})" if is_video else f"Custom uploaded audio ({target_path.name})",
        "duration": _probe_duration(target_path),
        "filename": target_path.name,
        "url": f"/api/audio/track/{track_id}"
    }
