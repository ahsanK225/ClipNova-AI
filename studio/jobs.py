"""Job pipeline: get video -> audio -> transcript -> AI picks -> rendered clips. One heavy task at a time."""
import collections
import json
import os
import math
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path

from . import ai, brain, config, creators, ctx, facecam, fetch_model, games, hashtags, load, media, quality, render, roman, safe, transcribe, usage

class _FairQueue:
    """Whose video is next. Each person has their own line and the lines take turns, so someone who adds ten
    videos does not make everyone else wait behind all ten. Small tasks (re-making one clip) go first."""

    def __init__(self):
        self.cv = threading.Condition()
        self.quick = collections.deque()
        self.lines = {}                       # user -> their waiting videos, oldest first
        self.turn = collections.deque()       # users with something waiting, in the order they will be served
        self.epoch = 0                        # goes up whenever the line moves
        self._pos = (0.0, {})
        self.running = 0                      # videos being worked on right now
        self.last_start = 0.0
        self.held = False                     # videos are waiting only because the machine is near full

    def _room(self) -> bool:
        """May one more video start? One always may. More only while the machine has room, and a few seconds
        after the last one started, so its weight is already showing in the measurements."""
        if self.running == 0:
            return True
        return self.running < config.JOB_WORKERS and time.time() - self.last_start > 6 and not load.busy()

    def done(self):
        with self.cv:
            self.running = max(0, self.running - 1)
            self.cv.notify_all()

    def put(self, item, user=None):
        with self.cv:
            if user is None:
                self.quick.append(item)
            else:
                if user not in self.lines:
                    self.lines[user] = collections.deque()
                    self.turn.append(user)
                self.lines[user].append(item)
            self.epoch += 1
            self.cv.notify()

    def get(self, quick_only=False):
        with self.cv:
            while True:
                if self.quick:
                    self.epoch += 1
                    return self.quick.popleft()
                if not quick_only and self.turn:
                    if self._room():
                        break
                    if not self.held:
                        self.held = True
                        self.epoch += 1
                elif self.held:
                    self.held = False
                    self.epoch += 1
                self.cv.wait(1.0)             # looked at again every second: the line moves the moment there is room
            self.epoch += 1
            self.held = False
            self.running += 1
            self.last_start = time.time()
            user = self.turn.popleft()
            item = self.lines[user].popleft()
            if self.lines[user]:
                self.turn.append(user)
            else:
                del self.lines[user]
            return item

    def ahead(self) -> dict:
        """job id -> how many videos will start before it. Worked out at most once a second."""
        with self.cv:
            if time.time() - self._pos[0] < 1:
                return self._pos[1]
            out, lines, order, n = {}, {u: list(q) for u, q in self.lines.items()}, list(self.turn), 0
            depth = 0
            while order:
                nxt = []
                for u in order:
                    if depth < len(lines[u]):
                        out[lines[u][depth][1]] = n
                        n += 1
                        if depth + 1 < len(lines[u]):
                            nxt.append(u)
                order, depth = nxt, depth + 1
            self._pos = (time.time(), out)
            return out


_q = _FairQueue()
_live_q: "queue.Queue" = queue.Queue()   # live clips never wait behind a long video
_jobs: dict = {}
_by_user: dict = {}                       # user -> {job id: job}: listing one person's videos never scans everyone's
_lock = threading.RLock()
on_clip_ready: list = []   # callbacks (job, clip), run once when a clip first finishes

DEFAULTS = {"max_clips": 6, "min_len": 15, "max_len": 60, "style": "bounce", "layout": "split_half", "quality": 1080,
            "range_start": None, "range_end": None, "captions": True, "facecam_pos": "top-right",
            "audio_delay": 0.0, "facecam_delay": 0.0, "hook_style": "neon", "outro_cta": True, "outro_text": "",
            "hook_text": "", "description_text": "", "trim_silence": False, "lang": "en"}


LIMITS = {"max_clips": (1, 20), "min_len": (5, 120), "max_len": (10, 180), "quality": (360, 1080)}


def clean_options(options) -> dict:
    """Only known settings, each inside its allowed range. Raises ValueError on nonsense."""
    out = {}
    for k, v in (options if isinstance(options, dict) else {}).items():
        if k == "captions":
            if not isinstance(v, bool):
                raise ValueError("Captions must be on or off.")
            out[k] = v
            continue
        if k in ("outro_cta", "trim_silence"):
            out[k] = bool(v)
            continue
        if k in ("hook_text", "description_text"):     # kept even when empty: it clears the creator's own text for this video
            out[k] = creators.clean_hook(v) if k == "hook_text" else creators.clean_description(v)
            continue
        if k not in DEFAULTS or v in ("", None):
            continue
        if k in LIMITS:
            lo, hi = LIMITS[k]
            v = max(lo, min(hi, int(float(v))))
        elif k in ("audio_delay", "facecam_delay"):
            v = float(v)
            if not math.isfinite(v) or v < -2.0 or v > 2.0:
                raise ValueError("Delay must be between -2.0s and +2.0s.")
            v = round(v, 3)
        elif k == "style":
            v = v if v in render.STYLES else DEFAULTS["style"]
        elif k == "layout":
            v = v if v in render.LAYOUTS else DEFAULTS["layout"]
        elif k == "hook_style":
            v = v if v in render.HOOK_STYLES else DEFAULTS["hook_style"]
        elif k == "facecam_pos":
            v = v if v in ("top-right", "top-left", "bottom-left", "bottom-right", "split") else DEFAULTS["facecam_pos"]
        elif k == "outro_text":
            v = str(v)[:60]
        elif k == "lang":
            v = v if fetch_model.known(v) else DEFAULTS["lang"]
        else:                                    # range_start, range_end: seconds into the video
            v = float(v)
            if not math.isfinite(v) or v < 0:
                raise ValueError("That part of the video isn't valid.")
        out[k] = v
    if out.get("range_end") is not None and out["range_end"] <= out.get("range_start", 0):
        raise ValueError("The end of the chosen part must be after its start.")
    return out


def job_dir(jid) -> Path:
    return Path(_jobs[jid]["dir"])


HIDDEN = ("dir", "user", "source_path", "recover")


def public(job) -> dict:
    """What the browser may see: no server paths, no owner id."""
    out = {k: v for k, v in job.items() if k not in HIDDEN}
    src_obj = job.get("source") if isinstance(job.get("source"), dict) else {}
    out["source"] = {k: v for k, v in src_obj.items() if k != "path"}
    if not out["source"].get("name"):
        out["source"]["name"] = job.get("title") or job.get("id") or "Video"
    out["clips"] = [{k: v for k, v in c.items() if k not in ("src", "fixed_words", "fixed_for", "_aligned_words")} for c in (job.get("clips") or [])]
    out["rev"] = int(job.get("_rev") or 0)
    ai = job.get("ai") or {}
    out["ai"] = {"tokens": ai.get("tokens", 0), "note": ai.get("note", ""), "used": bool(ai.get("model"))}   # never the model, never raw errors
    if job.get("status") == "queued":
        n = _q.ahead().get(job["id"])
        if n:
            out["stage"] = (f"High demand right now: {n} video{'s' if n != 1 else ''} ahead of yours" if _q.held else
                            f"Waiting in line: {n} video{'s' if n != 1 else ''} ahead of yours")
        elif n == 0 and _q.held:
            out["stage"] = "High demand right now: yours is next"
    return out


def save(job):
    ctx.bump(job.get("user"))
    with _lock:
        job["_rev"] = int(job.get("_rev") or 0) + 1
        d = Path(job["dir"])
        for _ in range(5):
            try:
                text = json.dumps(job, indent=1)
                break
            except RuntimeError:  # changed mid-dump by another thread
                time.sleep(0.05)
        else:
            return
        tmp = d / "job.json.tmp"
        tmp.write_text(text, encoding="utf-8")
        if _put_in_place(tmp, d / "job.json"):
            try:
                (d / "job.json.bak").write_bytes(text.encode("utf-8"))
            except OSError:
                pass


def _put_in_place(tmp: Path, target: Path) -> bool:
    """Move the freshly written job.json over the old one.

    Windows refuses this ("Access is denied") for a moment whenever anything else has the old file open: a virus
    scanner, the search indexer, or another part of PeakCut reading it. A download saves many times a second, so it
    happens, and it used to stop the whole video. So it is tried again a few times, and if the file is still busy
    it is written in place; as a last resort this save is skipped, because the next one carries the same news."""
    for i in range(8):
        try:
            tmp.replace(target)
            return True
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    try:
        target.write_text(tmp.read_text(encoding="utf-8"), encoding="utf-8")
        tmp.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _set(job, **kw):
    with _lock:
        job.update(kw)
    save(job)


def _remap(path, folder: Path):
    """Paths saved before data moved into per-user folders (or on another machine): find the file by name."""
    if path and not Path(path).exists():
        cand = folder / Path(str(path).replace("\\", "/")).name
        if cand.exists():
            return str(cand)
    return path


def _load_file(f: Path, uid: str):
    job = safe.load_json_with_backup(f)
    if not isinstance(job, dict):
        return
    job.update(dir=str(f.parent), user=uid)
    job.setdefault("kind", "video")
    job.setdefault("creator", None)
    job.setdefault("clips", [])
    job.setdefault("_rev", 1)
    if not isinstance(job.get("source"), dict):
        job["source"] = {"type": "live" if job.get("kind") == "live" else "url",
                         "url": job.get("url") or "", "name": job.get("title") or job.get("id") or "Video"}
    if not job.get("canonical_source_id"):
        job["canonical_source_id"] = media.canonical_source_id(
            job["source"].get("url") or "", job["source"].get("name") or job.get("title") or ""
        )
    job.setdefault("options", {}).setdefault("captions", True)
    if job.get("source_path"):
        job["source_path"] = _remap(job["source_path"], f.parent)
    if job.get("source", {}).get("path"):
        job["source"]["path"] = _remap(job["source"]["path"], f.parent)
    if job.get("status") in ("queued", "running") and job.get("kind") != "live":
        # Picked up again as soon as the server is back (jobs.start), from the last finished part of the transcript.
        job.update(status="queued", stage="Picking up where it stopped", error=None, resume=True)
    if job.get("status") == "live":
        job.update(status="done", stage="Recording paused by a server update", was_live=True)
    buffered = job.get("kind") == "live" and any((f.parent / "buffer").glob("*.ts"))
    for c in job.get("clips", []):
        c.setdefault("captions", job["options"]["captions"])
        if c.get("src"):
            c["src"] = _remap(c["src"], f.parent / "clips")
        if c.get("status") in ("rendering", "queued"):
            if buffered and not c.get("src"):
                c["status"] = "queued"  # the stream is still on disk: live.recover() finishes these
                job["recover"] = True
            elif job.get("resume"):
                c["status"] = "queued"  # the video is being picked up again: this clip is made then
            elif job.get("kind") != "live" and (f.parent / "words.json").is_file():
                c["status"] = "queued"  # a single clip being re-made: jobs.start() makes it again
                job.setdefault("remake", []).append(c["id"])
            else:
                c.update(status="error", error="Interrupted by a restart. Open it and press Save and re-make.")
    _jobs[job["id"]] = job
    _by_user.setdefault(uid, {})[job["id"]] = job


def load_user(uid: str):
    d = config.USERS_DIR / uid
    seen_dirs = set()
    candidates = (list((d / "jobs").glob("*/job.json")) + list((d / "creators").glob("*/*/*/job.json"))
                  + list((d / "jobs").glob("*/job.json.bak")) + list((d / "creators").glob("*/*/*/job.json.bak")))
    for f in candidates:
        pdir = f.parent.resolve()
        if pdir in seen_dirs:
            continue
        seen_dirs.add(pdir)
        target = f.parent / "job.json"
        _load_file(target if target.is_file() else f, uid)


def load_all():
    for d in config.USERS_DIR.iterdir():
        if d.is_dir():
            load_user(d.name)


def all_jobs() -> list:
    """Every user's jobs. Only for background work; never send this to a browser."""
    with _lock:
        return list(_jobs.values())


def list_jobs():
    u = ctx.uid()
    with _lock:
        return sorted((dict(j) for j in _by_user.get(u, {}).values()), key=lambda j: -j["created"])


def get(jid):
    """The job, only if it belongs to whoever this code is running for."""
    job = _jobs.get(jid)
    return job if job and job["user"] == ctx.uid() else None


def busy_count() -> int:
    u = ctx.uid()
    return sum(1 for j in list(_by_user.get(u, {}).values()) if j["kind"] == "video" and j["status"] in ("queued", "running"))


def waiting_total() -> int:
    return sum(1 for j in list(_jobs.values()) if j["kind"] == "video" and j["status"] == "queued")


def queue_epoch() -> int:
    return _q.epoch


def running_now() -> int:
    return _q.running


def create(source: dict, options: dict, enqueue=True, creator=None, kind="video") -> dict:
    jid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:10]
    c = creators.get(creator) if creator else None
    if c:
        d = creators.root(c["id"]) / ("live" if kind == "live" else "videos") / jid
        base = {**DEFAULTS, **{k: c[k] for k in ("max_clips", "min_len", "max_len", "style", "layout", "captions", "quality",
                                                 "audio_delay", "facecam_delay", "facecam_pos", "hook_style", "outro_cta", "outro_text", "lang") if k in c},
                "hook_text": creators.clean_hook(c.get("hook_text")),
                "description_text": creators.clean_description(c.get("description_text"))}
    else:
        d, base, creator = config.user_dir(ctx.uid()) / "jobs" / jid, dict(DEFAULTS), None
    opts = {**base, **clean_options(options)}
    if opts["min_len"] >= opts["max_len"]:
        opts["min_len"] = max(5, opts["max_len"] - 5)
    canon_id = media.canonical_source_id(source.get("url") or "", source.get("name") or "")
    job = {"id": jid, "user": ctx.uid(), "kind": kind, "creator": creator, "dir": str(d), "created": time.time(), "source": source,
           "canonical_source_id": canon_id,
           "options": opts, "status": "queued", "stage": "Waiting", "progress": 0.0,
           "title": source.get("name", ""), "uploader": "", "duration": 0, "clips": [], "error": None, "ai": {}}
    d.mkdir(parents=True)
    with _lock:
        _jobs[jid] = job
        _by_user.setdefault(job["user"], {})[jid] = job
    save(job)
    if enqueue:
        _q.put(("job", jid, None), user=job["user"])
    return job


def enqueue(job):
    save(job)
    _q.put(("job", job["id"], None), user=job["user"])


def submit(fn):
    """Run any heavy task (a render, a cleanup) on the single worker, in order."""
    _q.put(("fn", ctx.bind(fn), None))


def submit_live(fn):
    """Live-stream renders and cleanups: their own worker, so a long video can never hold them up."""
    _live_q.put(ctx.bind(fn))


def _live_worker():
    while True:
        fn = _live_q.get()
        try:
            fn()
        except Exception:  # noqa: BLE001
            traceback.print_exc()


def delete(jid):
    with _lock:
        job = _jobs.pop(jid, None)
        if job:
            _by_user.get(job["user"], {}).pop(jid, None)
    if job:
        ctx.bump(job["user"])
        shutil.rmtree(job["dir"], ignore_errors=True)
    return bool(job)


def request_render(jid, cid, changes: dict):
    job = _jobs[jid]
    clip = next(c for c in job["clips"] if c["id"] == cid)
    new = dict(clip)
    if "captions" in changes:
        new.update(clean_options({"captions": changes["captions"]}))
    trimmed = False
    for k in ("start", "end"):
        if k in changes:
            val = round(float(changes[k]), 2)
            if new.get(k) != val:
                if abs(float(new.get(k) or 0.0) - val) >= 0.5:
                    trimmed = True
                new[k] = val
                new.pop("fixed_words", None)
                new.pop("fixed_for", None)
    if trimmed:
        new["seo_stale"] = True
        new["seo_stale_reason"] = "Clip timing changed; refresh the Shorts package to match the new cut."
    if "src_offset" in clip:  # live clip: can only move inside the saved piece of stream
        new["start"] = max(new["start"], clip["src_offset"])
        new["end"] = min(new["end"], clip["src_end"])
    if not (math.isfinite(new["start"]) and math.isfinite(new["end"])) or new["start"] < 0:
        raise ValueError("Those times aren't valid.")
    if not 3 <= new["end"] - new["start"] <= 180:
        raise ValueError("A clip can be 3 to 180 seconds long.")
    for k in ("hook", "title", "description", "style", "layout", "seo_title", "pinned_comment", "hook_style", "outro_text", "facecam_pos", "bgm_track", "video_filter"):
        if k in changes:
            new[k] = str(changes[k])[:{"hook": 120, "title": 100, "description": 2000, "seo_title": 100, "pinned_comment": 500, "hook_style": 40, "outro_text": 100, "facecam_pos": 20, "bgm_track": 50, "video_filter": 50}.get(k, 20)]
    if "bgm_volume" in changes:
        try:
            new["bgm_volume"] = max(0.0, min(1.0, round(float(changes["bgm_volume"]), 2)))
        except (ValueError, TypeError):
            new["bgm_volume"] = 0.18
    if "bgm_offset" in changes:
        try:
            new["bgm_offset"] = max(0.0, min(3600.0, round(float(changes["bgm_offset"]), 3)))
        except (ValueError, TypeError):
            new["bgm_offset"] = 0.0
    if "speed" in changes:
        try:
            new["speed"] = max(0.25, min(4.0, round(float(changes["speed"]), 2)))
        except (ValueError, TypeError):
            new["speed"] = 1.0
    if "words" in changes and isinstance(changes["words"], list):
        cleaned_w = _sanitize_words(changes["words"])
        new["words"] = cleaned_w
        if cleaned_w:
            new["fixed_words"] = cleaned_w
            new["fixed_for"] = [round(new["start"], 2), round(new["end"], 2), "en2"]
            new["manual_words"] = True
    if "hashtags" in changes:
        new["hashtags"] = clean_hashtags(changes["hashtags"])
    if "outro_cta" in changes:
        new["outro_cta"] = bool(changes["outro_cta"])
    if "quality" in changes:
        try:
            q = int(float(changes["quality"]))
            if q in (720, 1080):
                new["quality"] = q
                job.setdefault("options", {})["quality"] = q
        except (ValueError, TypeError):
            pass
    if "audio_delay" in changes:
        try:
            new["audio_delay"] = round(float(changes["audio_delay"]), 3)
        except (ValueError, TypeError):
            new["audio_delay"] = 0.0
    if "facecam_delay" in changes:
        try:
            new["facecam_delay"] = round(float(changes["facecam_delay"]), 3)
        except (ValueError, TypeError):
            new["facecam_delay"] = 0.0
    if "facecam_offset_y" in changes:
        try:
            new["facecam_offset_y"] = int(float(changes["facecam_offset_y"]))
        except (ValueError, TypeError):
            pass
    if "game_offset_x" in changes:
        try:
            new["game_offset_x"] = int(float(changes["game_offset_x"]))
        except (ValueError, TypeError):
            pass
    if "zoom" in changes:
        try:
            new["zoom"] = round(float(changes["zoom"]), 2)
        except (ValueError, TypeError):
            pass
    for hk in ("hook_y", "hook_w", "hook_font_size"):
        if hk in changes:
            try:
                new[hk] = int(float(changes[hk]))
            except (ValueError, TypeError):
                pass
    if "teaser_enabled" in changes:
        new["teaser_enabled"] = bool(changes["teaser_enabled"])
    if "teaser_dur" in changes:
        try:
            new["teaser_dur"] = max(1.0, min(10.0, round(float(changes["teaser_dur"]), 2)))
        except (ValueError, TypeError):
            new["teaser_dur"] = 4.0
    if "teaser_start" in changes and changes["teaser_start"] is not None:
        try:
            new["teaser_start"] = round(float(changes["teaser_start"]), 2)
        except (ValueError, TypeError):
            new.pop("teaser_start", None)
    if "seo_tags" in changes:
        raw_tags = changes["seo_tags"]
        if isinstance(raw_tags, str):
            new["seo_tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()][:25]
        elif isinstance(raw_tags, list):
            new["seo_tags"] = [str(t).strip() for t in raw_tags if str(t).strip()][:25]
    cr = {}
    if job.get("creator"):
        try:
            cr = creators.get(job["creator"]) or {}
        except Exception:
            cr = {}
    if "active_preset" in changes and changes["active_preset"]:
        pname = str(changes["active_preset"]).strip()
        new["active_preset"] = pname
        preset = cr.get("custom_presets", {}).get(pname)
        if preset:
            new["custom_layout"] = {**preset, "enabled": True}
            new["layout"] = "custom"
    if "custom_layout" in changes:
        new["custom_layout"] = changes["custom_layout"]
    elif new.get("layout") == "custom" and not new.get("custom_layout"):
        cl = job.get("options", {}).get("custom_layout") or cr.get("custom_layout")
        if cl:
            new["custom_layout"] = cl
    if new.get("style") not in render.STYLES:
        new["style"] = DEFAULTS["style"]
    if new.get("layout") not in render.LAYOUTS:
        new["layout"] = DEFAULTS["layout"]
    if new.get("layout") in ("gameplay", "split", "split_half") and not new.get("facecam"):
        if job.get("facecam"):
            new["facecam"] = job["facecam"]
        elif clip.get("facecam"):
            new["facecam"] = clip["facecam"]
    clip.update(new, status="queued")
    save(job)
    _q.put(("clip", jid, cid))


def _extract_frame_bytes(src: Path, t: float) -> bytes | None:
    try:
        t_clean = max(0.0, float(t))
        cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{t_clean:.3f}", "-i", str(src), "-frames:v", "1", "-f", "image2", "-c:v", "mjpeg", "pipe:1"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=5)
        if res.returncode == 0 and len(res.stdout) > 1000:
            return res.stdout
    except Exception:
        pass
    return None


def extract_clip_frames_bytes(src: Path, start: float, end: float, n_frames: int = 6) -> list[bytes]:
    """Extract n_frames representative timestamped frames across the clip timeline for true multimodal video analysis."""
    dur = max(1.0, float(end) - float(start))
    ratios = [0.15, 0.35, 0.55, 0.70, 0.85, 0.95] if n_frames == 6 else [(i + 1) / (n_frames + 1) for i in range(min(12, max(2, n_frames)))]
    frames = []
    for r in ratios:
        t = float(start) + dur * r
        b = _extract_frame_bytes(src, t)
        if b:
            frames.append(b)
    return frames


def get_clip_frames_payload(job: dict, clip: dict, n_frames: int = 6) -> list[bytes] | bytes | None:
    """Finds the video file or cover JPEG for this clip and extracts physical visual frames for Gemini vision."""
    d = Path(job.get("dir", ""))
    cid = clip.get("id", "")

    # 1. Try clip source video or job source video
    src = Path(clip["src"]) if clip.get("src") else (Path(job.get("source_path")) if job.get("source_path") else None)
    if src and src.is_file():
        off = float(clip.get("src_offset", 0.0))
        local_start = max(0.0, float(clip.get("start", 0.0)) - off)
        local_end = max(local_start + 1.0, float(clip.get("end", local_start + 30.0)) - off)
        extracted = extract_clip_frames_bytes(src, local_start, local_end, n_frames=n_frames)
        if extracted:
            return extracted

    # 2. Try the rendered or sliced clip MP4
    candidates = [
        d / "clips" / f"{cid}.mp4",
        d / "clips" / f"{cid}.src.mp4",
        d / f"{cid}.mp4",
    ]
    if clip.get("file"):
        candidates.insert(0, Path(clip["file"]))
        candidates.insert(1, d / "clips" / Path(clip["file"]).name)

    for cand in candidates:
        if cand.is_file() and cand.stat().st_size > 10000:
            dur = max(1.0, float(clip.get("end", 30.0)) - float(clip.get("start", 0.0)))
            extracted = extract_clip_frames_bytes(cand, 0.0, dur, n_frames=n_frames)
            if extracted:
                return extracted

    # 3. Try the clip cover JPEG
    cover_candidates = [
        d / "clips" / f"{cid}.jpg",
        d / "clips" / f"{cid}.png",
        d / f"{cid}.jpg",
    ]
    for cov in cover_candidates:
        if cov.is_file() and cov.stat().st_size > 1000:
            return cov.read_bytes()

    return None


def get_clip_media_payload(job: dict, clip: dict, include_video_proxy: bool = True) -> list[tuple[str, bytes]]:
    """Build exact final-cut multimodal media parts (compact 360p MP4 with audio when available,
    plus fallback sampled JPEG frames) for grounded Gemini review."""
    d = Path(job.get("dir", ""))
    cid = clip.get("id", "")
    parts: list[tuple[str, bytes]] = []
    if include_video_proxy:
        # 1. Prefer the exact exported/rendered cut MP4 so final audio/video matches user trims
        rendered_candidates = [
            d / "clips" / f"{cid}.mp4",
            d / f"{cid}.mp4",
        ]
        if clip.get("file"):
            rendered_candidates.insert(0, d / "clips" / Path(clip["file"]).name)
        proxy_bytes = None
        for rc in rendered_candidates:
            if rc.is_file() and rc.stat().st_size > 10000:
                meta = media.probe(rc)
                dur = float(meta.get("duration") or max(1.0, float(clip.get("end", 30.0)) - float(clip.get("start", 0.0))))
                proxy_bytes = media.extract_proxy_clip(rc, 0.0, dur)
                break
        # 2. Fall back to slicing proxy from clip.src / job.source_path
        if not proxy_bytes:
            src = Path(clip["src"]) if clip.get("src") else (Path(job.get("source_path")) if job.get("source_path") else None)
            if src and src.is_file():
                off = float(clip.get("src_offset", 0.0))
                loc_s = max(0.0, float(clip.get("start", 0.0)) - off)
                loc_e = max(loc_s + 1.0, float(clip.get("end", loc_s + 30.0)) - off)
                proxy_bytes = media.extract_proxy_clip(src, loc_s, loc_e)
        if proxy_bytes:
            parts.append(("video/mp4", proxy_bytes))

    frames = get_clip_frames_payload(job, clip, n_frames=6)
    if isinstance(frames, list):
        for fb in frames[:6]:
            if fb:
                parts.append(("image/jpeg", fb))
    elif isinstance(frames, bytes) and frames:
        parts.append(("image/jpeg", frames))
    return parts


def clean_hashtags(v) -> list:
    """Hashtags typed by a person ("#funny gaming") or sent by the page as a list: plain words, at most 8."""
    if isinstance(v, str):
        v = v.split()
    if not isinstance(v, list):
        raise ValueError("Hashtags must be words separated by spaces.")
    out, seen = [], set()
    for h in v[:50]:
        if not isinstance(h, (str, int)):
            continue
        t = re.sub(r"\W", "", str(h))[:30]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:8]


def _published_short_url(clip: dict) -> str:
    for p in (clip.get("posts") or {}).values():
        if isinstance(p, dict):
            if p.get("url") and "youtu" in str(p.get("url")):
                return str(p["url"])
            if p.get("remote_id"):
                return f"https://youtube.com/shorts/{p['remote_id']}"
    return ""


def save_post_text(job, clip, changes: dict):
    """Change a clip's title, description, SEO, hook and tags without making the clip again.
    Tracks manually edited fields so partial AI regenerations preserve them."""
    text = {}
    edited = set(clip.get("edited_fields") or [])
    for k in ("title", "description", "seo_title", "pinned_comment", "hook", "hook_style", "style", "outro_text", "bgm_track", "video_filter", "community_text"):
        if k in changes:
            max_len = {"title": 100, "description": 2000, "seo_title": 100, "pinned_comment": 500, "hook": 120, "hook_style": 40, "style": 30, "outro_text": 100, "bgm_track": 50, "video_filter": 50, "community_text": 1500}.get(k, 100)
            val = str(changes[k] or "")[:max_len]
            text[k] = val
            if val != str(clip.get(k) or ""):
                edited.add(k)
    if "title" in text and "seo_title" not in text:
        tval = text["title"]
        text["seo_title"] = tval if "#shorts" in tval.lower() else f"{tval} #Shorts"[:100].strip()
    elif "seo_title" in text and "title" not in text:
        text["title"] = text["seo_title"]
    if "hashtags" in changes:
        ht = clean_hashtags(changes["hashtags"])
        text["hashtags"] = ht
        if ht != (clip.get("hashtags") or []):
            edited.add("hashtags")
    if "seo_tags" in changes:
        st = changes["seo_tags"]
        if isinstance(st, str):
            text["seo_tags"] = [t.strip() for t in st.split(",") if t.strip()][:30]
        elif isinstance(st, list):
            text["seo_tags"] = [str(t).strip() for t in st if str(t).strip()][:30]
        if text["seo_tags"] != (clip.get("seo_tags") or []):
            edited.add("seo_tags")
    for b in ("captions", "outro_cta"):
        if b in changes:
            text[b] = bool(changes[b])
    if "bgm_volume" in changes:
        try:
            text["bgm_volume"] = max(0.0, min(1.0, round(float(changes["bgm_volume"]), 2)))
        except (ValueError, TypeError):
            pass
    if "bgm_offset" in changes:
        try:
            text["bgm_offset"] = max(0.0, min(3600.0, round(float(changes["bgm_offset"]), 3)))
        except (ValueError, TypeError):
            pass
    if clip.get("hashtags_in_description") and not clip.get("fixed_description") and "description" in text:
        desc = hashtags._TAG_IN_TEXT.sub("", text.get("description", clip.get("description") or "")).strip()
        line = " ".join("#" + t for t in text.get("hashtags", clip.get("hashtags") or []))
        text["description"] = ((desc + "\n\n" + line).strip() if desc else line)[:2000]
    if "community_text" not in text and any(k in text for k in ("title", "description", "pinned_comment", "hashtags")):
        short_url = _published_short_url(clip)
        if not clip.get("community_text") or "community_text" not in edited:
            text["community_text"] = brain.build_community_post(
                text.get("title", clip.get("title") or ""),
                text.get("description", clip.get("description") or ""),
                text.get("pinned_comment", clip.get("pinned_comment") or ""),
                text.get("hashtags", clip.get("hashtags") or []),
                short_url=short_url,
            )
    if edited:
        text["edited_fields"] = sorted(edited)
    if changes.get("clear_stale"):
        text["seo_stale"] = False
        text.pop("seo_stale_reason", None)
    with _lock:
        clip.update(text)
    save(job)
    side = Path(job["dir"]) / "clips" / f"{clip['id']}.json"   # the copy that sits next to the video file
    try:
        if side.is_file() or side.with_name(f"{side.name}.bak").is_file():
            prev = safe.load_json_with_backup(side, default={}) or {}
            safe.atomic_write_text(side, json.dumps({**prev, **text}, indent=1), backup=True)
    except (OSError, ValueError):
        pass


def spoken_in(job, clip) -> str:
    """What is said during a clip, from the video's transcript."""
    words = safe.load_json_with_backup(Path(job["dir"]) / "words.json", default=None)
    if not isinstance(words, list):
        return ""
    return " ".join(str(w.get("w", "")) for w in words
                    if isinstance(w, dict) and clip["start"] - 0.5 <= _f(w.get("s")) <= clip["end"] + 0.5)


def _sanitize_words(words_in: list) -> list[dict]:
    """Validate and Roman-normalize user-edited caption words while keeping finite increasing timings."""
    cleaned = []
    for item in words_in[:600]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("w") or "").strip()[:60]
        if not text:
            continue
        s = _f(item.get("s"))
        e = _f(item.get("e"))
        if s < 0 or not math.isfinite(s):
            s = cleaned[-1]["e"] if cleaned else 0.0
        if e < s or not math.isfinite(e):
            e = round(s + 0.35, 2)
        cleaned.append({"w": text, "s": round(s, 2), "e": round(max(s + 0.05, e), 2)})
    return roman.words(cleaned) if cleaned else []


def get_clip_words(job: dict, clip: dict) -> dict:
    """Return editable timestamped words for a clip (prefers user-edited/fixed words, else transcript slice)."""
    span = [round(clip["start"], 2), round(clip["end"], 2), "en2"]
    fixed = clip.get("fixed_words")
    if isinstance(fixed, list) and fixed and (clip.get("fixed_for") == span or clip.get("manual_words")):
        return {"words": _sanitize_words(fixed), "start": clip["start"], "end": clip["end"],
                "source": "edited" if clip.get("manual_words") else "fixed"}
    words = safe.load_json_with_backup(Path(job["dir"]) / "words.json", default=None)
    if isinstance(words, list):
        sliced = [w for w in words if isinstance(w, dict) and clip["start"] - 0.5 <= _f(w.get("s")) <= clip["end"] + 0.5]
        if sliced:
            return {"words": _sanitize_words(sliced), "start": clip["start"], "end": clip["end"], "source": "transcript"}
    if isinstance(fixed, list) and fixed:
        return {"words": _sanitize_words(fixed), "start": clip["start"], "end": clip["end"], "source": "fixed"}
    return {"words": [], "start": clip["start"], "end": clip["end"], "source": "empty"}


def save_clip_words(job: dict, clip: dict, words_in: list) -> list[dict]:
    """Persist user-edited caption words onto a clip so the next render burns those exact words."""
    cleaned = _sanitize_words(words_in)
    span = [round(clip["start"], 2), round(clip["end"], 2), "en2"]
    with _lock:
        clip["fixed_words"] = cleaned
        clip["fixed_for"] = span
        clip["manual_words"] = True
        clip["words"] = cleaned
    save(job)
    return cleaned


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return -1.0


def trim_dead_air(words: list, start: float, end: float, lead_pad: float = 0.8,
                  tail_pad: float = 1.2, min_len: float = 12.0) -> tuple[float, float]:
    """Trim >2s silent dead air from clip start/end while keeping >=min_len duration and exact timeline sync."""
    s, e = float(start), float(end)
    if e - s <= min_len or not words:
        return round(s, 2), round(e, 2)
    in_span = [w for w in words if isinstance(w, dict) and s <= _f(w.get("s")) <= e]
    if not in_span:
        return round(s, 2), round(e, 2)
    first_t = min(_f(w.get("s")) for w in in_span)
    last_t = max(_f(w.get("e")) if _f(w.get("e")) > 0 else _f(w.get("s")) for w in in_span)
    if first_t - s > 2.0:
        cand_s = max(s, first_t - lead_pad)
        if e - cand_s >= min_len:
            s = cand_s
    if e - last_t > 2.5:
        cand_e = min(e, last_t + tail_pad)
        if cand_e - s >= min_len:
            e = cand_e
    return round(s, 2), round(e, 2)


def render_one(job, clip, words):
    user = job.get("user") or "u_local"
    try:
        ctx.uid()
    except RuntimeError:
        ctx._uid.set(user)
    d = Path(job["dir"])
    clip["status"] = "rendering"
    save(job)
    try:
        if not clip.get("src") and not job.get("source_path"):
            _piece_again(job, clip)
        off = clip.get("src_offset", 0.0)
        src = Path(clip["src"]) if clip.get("src") else Path(job["source_path"])
        if not clip.get("src"):
            clip["end"] = min(clip["end"], job["duration"])
        if clip.get("layout") in ("gameplay", "split", "split_half") and not clip.get("facecam"):
            fc = job.get("facecam") or _facecam(job)
            if not fc and src.is_file():
                try:
                    box = facecam.detect(src, ask=brain.look_for_facecam)
                    if box:
                        fc = [box["x"], box["y"], box["w"], box["h"]]
                except Exception:
                    pass
            if fc:
                clip["facecam"] = fc
                job.setdefault("facecam", fc)
        o = job.get("options") or {}
        cr = creators.get(job.get("creator")) or {}
        cl_opt = o.get("custom_layout") or cr.get("custom_layout")
        act_pre = o.get("active_preset") or cr.get("active_preset")
        if act_pre and cr.get("custom_presets", {}).get(act_pre):
            cl_opt = {**cr["custom_presets"][act_pre], "enabled": True}
        if cl_opt:
            clip.setdefault("custom_layout", cl_opt)
            if act_pre:
                clip.setdefault("active_preset", act_pre)
            if (o.get("layout") == "custom" or cr.get("layout") == "custom" or act_pre) and cl_opt.get("enabled", True):
                clip.setdefault("layout", "custom")
            if cl_opt.get("facecam"):
                clip.setdefault("facecam", cl_opt["facecam"])
            if cl_opt.get("hook_style"):
                clip.setdefault("hook_style", cl_opt["hook_style"])
            if cl_opt.get("caption_style"):
                clip.setdefault("style", cl_opt["caption_style"])
            if cl_opt.get("hook_y") is not None:
                clip.setdefault("hook_y", cl_opt["hook_y"])
            if cl_opt.get("hook_w") is not None:
                clip.setdefault("hook_w", cl_opt["hook_w"])
        clip.setdefault("facecam_pos", o.get("facecam_pos") or cr.get("facecam_pos") or "top-right")
        clip.setdefault("facecam_delay", float(o.get("facecam_delay") if o.get("facecam_delay") is not None else (cr.get("facecam_delay") or 0.0)))
        raw_adelay = o.get("audio_delay") if o.get("audio_delay") is not None else (cr.get("audio_delay") if cr.get("audio_delay") is not None else 0.0)
        clip.setdefault("audio_delay", float(raw_adelay if raw_adelay is not None else 0.0))
        clip.setdefault("hook_style", o.get("hook_style") or cr.get("hook_style") or "neon")
        clip.setdefault("outro_cta", o.get("outro_cta", cr.get("outro_cta", True)))
        clip.setdefault("outro_text", o.get("outro_text") or cr.get("outro_text"))
        if (clip.get("version", 0) == 0 and not clip.get("manual_words")
                and (clip.get("trim_silence") or o.get("trim_silence") or cr.get("trim_silence"))):
            ns, ne = trim_dead_air(words or [], clip["start"], clip["end"], min_len=min(12.0, float(o.get("min_len") or 12.0)))
            if ns >= clip["start"] and ne <= clip["end"] and ne - ns >= 5.0:
                clip["start"], clip["end"] = ns, ne

        # Grounded Final-Cut Shorts Package (uses actual cut video+audio/frames + exact cut transcript)
        cur_hook = (clip.get("hook") or "").strip().upper()
        cur_span = [round(clip["start"], 2), round(clip["end"], 2)]
        seo_current = clip.get("seo_for") == cur_span and not clip.get("seo_stale")
        needs_visual_seo = (not seo_current) and (
            not cur_hook or cur_hook in ("WAIT FOR IT", "AUTO-GENERATED") or
            "NO CHILL" in cur_hook or "WAY TOO REAL" in cur_hook or
            clip.get("needs_ai_seo") or clip.get("version", 0) == 0
        )
        if needs_visual_seo and src.is_file() and ai.ready():
            try:
                mparts = get_clip_media_payload(job, clip, include_video_proxy=True)
                if mparts:
                    clip_text = " ".join(w.get("w", "") for w in (words or []) if clip["start"] - 0.5 <= _f(w.get("s")) <= clip["end"] + 0.5)
                    edited_map = {k: clip[k] for k in (clip.get("edited_fields") or []) if k in clip}
                    lang_set = o.get("lang") or cr.get("lang") or "en"
                    pkg = brain.generate_final_cut_package(
                        mparts,
                        transcript_text=clip_text,
                        duration=max(1.0, float(clip["end"]) - float(clip["start"])),
                        title=job.get("title", ""),
                        uploader=job.get("uploader", ""),
                        game=job.get("game"),
                        lang=lang_set,
                        short_url=_published_short_url(clip),
                        preserve_fields=edited_map,
                    )
                    if pkg:
                        for k in ("hook", "hooks", "title", "seo_title", "titles", "description", "hashtags", "seo_tags", "pinned_comment", "community_text", "analysis_mode", "analysis_model"):
                            if k in pkg and pkg[k] is not None:
                                clip[k] = pkg[k]
                        if pkg.get("reason") and not clip.get("reason"):
                            clip["reason"] = pkg["reason"]
                        clip["seo_for"] = cur_span
                        clip["seo_stale"] = False
                        clip.pop("seo_stale_reason", None)
                        clip.pop("needs_ai_seo", None)
            except Exception:
                pass
        elif not clip.get("community_text"):
            clip["community_text"] = brain.build_community_post(
                clip.get("seo_title") or clip.get("title") or "",
                clip.get("description") or "",
                clip.get("pinned_comment") or "",
                clip.get("hashtags") or [],
                short_url=_published_short_url(clip),
            )

        use_caps = clip.get("captions")
        if use_caps is None:
            use_caps = job.get("options", {}).get("captions")
        if use_caps is None and job.get("creator"):
            c_prof = creators.get(job["creator"])
            if c_prof and "captions" in c_prof:
                use_caps = c_prof["captions"]
        if use_caps is None:
            use_caps = True
        clip["captions"] = bool(use_caps)

        local = dict(clip, start=clip["start"] - off, end=clip["end"] - off, hook=roman.to_roman(clip.get("hook") or ""))
        near = _caption_words(job, clip, words, off, src=src, local_start=local["start"], local_end=local["end"]) if use_caps else []
        out = render.render_clip(src, d / "clips", clip["id"], local, near, job["width"], job["height"])
        # Quality Control Gate on final exported MP4
        qg_warnings = []
        out_mp4 = (d / "clips" / Path(out.get("file", "")).name) if out.get("file") else None
        if not out_mp4 or not out_mp4.is_file() or out_mp4.stat().st_size < 10_000:
            qg_warnings.append("Output MP4 missing or unexpectedly small.")
        if float(out.get("dur") or 0.0) < max(2.5, (clip["end"] - clip["start"]) * 0.75):
            qg_warnings.append("Rendered duration shorter than expected cut span.")
        payoff_t = clip.get("payoff_at")
        if payoff_t is not None and not (clip["start"] <= float(payoff_t) <= clip["end"] + 0.5):
            qg_warnings.append("Payoff timestamp lies outside final cut boundaries.")
        clip["quality_gate"] = {"ok": len(qg_warnings) == 0, "warnings": qg_warnings}
        clip.update(out, status="done", version=clip.get("version", 0) + 1, error=None, rendered_hook=local.get("hook", ""), rendered_hook_style=clip.get("hook_style", ""))
        post = {k: clip[k] for k in ("title", "description", "hashtags", "hook", "start", "end", "payoff_at", "score", "seo_title", "seo_tags", "pinned_comment", "community_text", "hook_style", "outro_cta", "outro_text", "audio_delay", "facecam_pos", "facecam_delay", "analysis_mode", "seo_stale") if k in clip}
        safe.atomic_write_text(d / "clips" / f"{clip['id']}.json", json.dumps(post, indent=1), backup=True)
        if clip["version"] == 1:
            clip.setdefault("made_at", time.time())
            creators.log(job["creator"], f"Clip ready (score {clip['score']}): {clip['title'] or clip['hook']}")
            save(job)
            for fn in on_clip_ready:
                try:
                    fn(job, clip)
                except Exception:  # noqa: BLE001
                    traceback.print_exc()
    except Exception as e:  # noqa: BLE001
        clip.update(status="error", error=safe.friendly(e, 400))
        creators.log(job["creator"], f"Clip failed: {safe.friendly(e, 200)}")
    save(job)


def _caption_words(job, clip, words, off, src=None, local_start=0.0, local_end=None):
    aligned = clip.pop("_aligned_words", None)
    span = [round(clip["start"], 2), round(clip["end"], 2), "en2"]      # "en2": captions made always-English
    if clip.get("fixed_for") == span and clip.get("fixed_words") and not any(
            roman.needs_roman(w.get("w", "")) for w in clip["fixed_words"]):
        raw = clip["fixed_words"]          # already tidied for this exact span: no second AI call
    else:
        raw = [dict(w) for w in aligned] if isinstance(aligned, list) and aligned else None
        # Direct slice transcription (VOD / misses): extract and transcribe the clip's exact audio slice once.
        # Live clips already pass aligned ASR words via _aligned_words, skipping redundant ffmpeg + Whisper work.
        if raw is None and src and Path(src).is_file() and local_end and local_end > local_start:
            tmp_wav = None
            try:
                tmp_wav = Path(tempfile.gettempdir()) / f"pk_cap_{clip.get('id', 'c')}_{int(time.time() * 1000)}.wav"
                dur = local_end - local_start
                media.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ss", f"{local_start:.3f}",
                           "-t", f"{dur:.3f}", "-vn", "-ac", "1", "-ar", "16000",
                           "-af", "aresample=async=1:first_pts=0", "-c:a", "pcm_s16le", str(tmp_wav)])
                if tmp_wav.is_file() and tmp_wav.stat().st_size > 1000:
                    audio = media.load_audio(tmp_wav)
                    heard = transcribe.transcribe(audio)
                    if heard:
                        # Normalize to full source timeline (matching words list): w["s"] + clip["start"]
                        clip_base = float(clip["start"])
                        raw = [dict(w, s=w["s"] + clip_base, e=w["e"] + clip_base) for w in heard]
            except Exception:  # noqa: BLE001
                raw = None
            finally:
                if tmp_wav and tmp_wav.exists():
                    tmp_wav.unlink(missing_ok=True)

        if not raw:
            raw = [w for w in words if clip["start"] - 1 <= w["s"] <= clip["end"] + 1]
        try:
            usage.set_context(job.get("creator"), job.get("title") or "")
            raw = brain.english_captions(raw, job.get("lang") or "", job.get("title") or "",
                                         youtube_english=lambda: _english_part(job, clip))
            clip.update(fixed_words=raw, fixed_for=span)
        except Exception:  # noqa: BLE001 - captions still render with the words as heard
            pass
    # the last word on it: whatever was said, nothing is drawn in Hindi or Urdu script
    return [dict(w, s=w["s"] - off, e=w["e"] - off) for w in roman.words(raw)]


CLIP_MINUTES = float(config.env("PEAKCUT_CLIP_MINUTES", "15"))     # the longest one clip may take to make


def _wait_for_clips(job, futures, began, workers):
    """Wait for a video's clips, but not for ever. A clip that hangs (a download that stalls, an encoder that
    freezes) used to keep the whole video "in progress", and no other clip could be re-made. Now it is marked as
    failed after CLIP_MINUTES and the video finishes with the clips that did work."""
    left, given_up = list(futures), 0
    late = "This clip took too long and was stopped. Open it and press Save and re-make to try again."
    while left:
        still = []
        for f, clip in left:
            if f.done():
                f.result()
                continue
            t = began.get(clip["id"])
            if (t and time.time() - t > CLIP_MINUTES * 60) or (not t and given_up >= workers):
                given_up += 1
                clip.update(status="error", error=late)
                creators.log(job["creator"], f"Clip stopped after {CLIP_MINUTES:g} minutes: {clip.get('title') or clip.get('hook') or clip['id']}")
                save(job)
                continue
            still.append((f, clip))
        left = still
        if left:
            time.sleep(1)


def _english_part(job, clip):
    """YouTube's English captions for just this clip, for a video in another language. Fetched once per video."""
    if (job.get("source") or {}).get("type") != "url":
        return None
    f = Path(job["dir"]) / "words_en.json"
    if f.is_file() or f.with_name(f"{f.name}.bak").is_file():
        en = safe.load_json_with_backup(f, default=[]) or []
    else:
        try:
            en = media.youtube_english_words(job["source"]["url"]) or []
        except Exception:  # noqa: BLE001 - YouTube often refuses its translations: the AI translates instead
            en = []
        safe.atomic_write_text(f, json.dumps(en), backup=False)       # asked once per video, refused or not
    return [w for w in en if clip["start"] - 0.5 <= w["s"] <= clip["end"] + 0.5]


LONG_VIDEO = 40 * 60   # above this, fetch only the pieces that become clips
PAD = 8                # seconds kept either side of a fetched piece, so clips can be re-trimmed


def _piece_again(job, clip):
    """Remaking a clip whose own piece of the video was never fetched (its first try failed) and whose whole video
    is not here: fetch the piece now, cut exactly at the asked time, so no sound matching is needed."""
    src = job.get("source") or {}
    if src.get("type") != "url" or not src.get("url"):
        raise RuntimeError("The original video is no longer here, so this clip can't be made again. Add the video again.")
    d = Path(job["dir"])
    want = max(0.0, clip["start"] - PAD)
    until = clip["end"] + PAD if not job.get("duration") else min(job["duration"], clip["end"] + PAD)
    try:
        piece = media.download_section(src["url"], d / "clips", f"{clip['id']}.src", want, until,
                                       int(job["options"]["quality"]), exact=True)
        meta = media.probe(piece)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Could not fetch this part of the video: {safe.friendly(e, 250)}") from e
    clip.update(src=str(piece), src_offset=round(want, 2), src_end=round(want + meta["duration"], 2))
    clip["end"] = min(clip["end"], clip["src_end"])
    job.setdefault("width", meta["width"])
    job.setdefault("height", meta["height"])


def _fetch_piece(job, clip, full_audio):
    """Long videos: download just this clip's stretch and pin down exactly where it starts."""
    d = Path(job["dir"])
    o = job["options"]
    try:
        want = max(0.0, clip["start"] - PAD)
        piece = media.download_section(job["source"]["url"], d / "clips", f"{clip['id']}.src", want,
                                       min(job["duration"], clip["end"] + PAD), int(o["quality"]))
        wav = d / "clips" / f"{clip['id']}.wav"
        media.extract_audio(piece, wav)
        part = media.load_audio(wav)
        wav.unlink(missing_ok=True)
        meta = media.probe(piece)
        off = media.find_offset(full_audio, part, want)
        clip.update(src=str(piece), src_offset=round(off, 2), src_end=round(off + meta["duration"], 2))
        clip["start"], clip["end"] = max(clip["start"], clip["src_offset"]), min(clip["end"], clip["src_end"])
        job.setdefault("width", meta["width"])
        job.setdefault("height", meta["height"])
    except Exception as e:  # noqa: BLE001
        clip.update(status="error", error=f"Could not fetch this part of the video: {safe.friendly(e, 250)}")


BLOCK = 10 * 60         # long videos are transcribed and clipped one block at a time
PROGRESSIVE_FROM = 20 * 60


def _covers(words: list, start: float, end: float) -> bool:
    """Is a borrowed transcript good enough to find clips with? It has to reach the end of the part being clipped
    and have a normal amount of talking in it; otherwise our own model writes the transcript."""
    inside = [w for w in words if start <= w["s"] <= end]
    minutes = max(0.5, (end - start) / 60)
    return len(inside) >= 25 * minutes and inside[-1]["s"] >= start + 0.85 * (end - start)


def _facecam(job) -> list | None:
    """Where the webcam is in the source: once for the whole video, for every clip of it.

    Only a sure answer is used. A box that is a scoreboard drawn over the game would
    put a picture of a scoreboard in the corner of the clip. One frame is also shown to
    the AI, which tells a person from a game character better than any measurement can;
    what it says is measured again on the picture, so it cannot do any harm."""
    if job.get("facecam") and isinstance(job["facecam"], list) and len(job["facecam"]) == 4:
        return job["facecam"]
    path = job.get("source_path") or (job.get("source", {}).get("path") if isinstance(job.get("source"), dict) else None)
    if not path or not Path(path).is_file():
        return None
    try:
        box = facecam.detect(path, ask=brain.look_for_facecam)
    except Exception:  # noqa: BLE001 - a missing facecam is not a failure
        return None
    if not box:
        return None
    job["facecam"] = [box["x"], box["y"], box["w"], box["h"]]
    return job["facecam"]


def _run_job(job):
    import math
    from concurrent.futures import ThreadPoolExecutor
    d = Path(job["dir"])
    o = job["options"]
    src = job["source"]
    # Which game this is: what the creator set, or what the title says. It decides the extra rules the AI
    # reads and the tags every post carries.
    game = job.get("game") or ""
    if not game and job.get("creator"):
        try:
            game = (creators.get(job["creator"]) or {}).get("game") or ""
        except Exception:  # noqa: BLE001
            game = ""
    if not game:
        game = games.detect(job["title"], src.get("name"))[0] or ""
    if game and job.get("game") != game:
        job["game"] = game
    t0 = time.time()
    notes = []
    face = False       # where the webcam is in the source, found once; False means not looked for yet
    usage.set_context(job["creator"], job["title"] or src.get("name"))
    resuming = bool(job.pop("resume", False)) and (d / "words.json").is_file()
    if resuming:   # after a restart: keep the transcript parts, clips and AI answers already made, and carry on
        _set(job, status="running", stage="Picking up where it stopped", error=None)
    else:
        _set(job, status="running", stage="Getting the audio", progress=0.03, error=None, clips=[], ai={}, done_blocks=0)
    speech = o.get("lang") if fetch_model.known(o.get("lang")) else fetch_model.DEFAULT   # the language spoken
    if speech == fetch_model.DEFAULT and not transcribe.model_ready() and not transcribe.REMOTE:
        _set(job, stage="Getting the speech model (one time, about 480 MB)")
        fetch_model.ensure()
        _set(job, stage="Getting the audio")
    could_borrow = src["type"] == "url" and config.YT_TRANSCRIPT and media.is_youtube(src["url"])
    if speech != fetch_model.DEFAULT and not transcribe.REMOTE and not could_borrow and fetch_model.status(speech) == "missing":
        fetch_model.ensure(speech, start=False)      # says what to do, before any time is spent on the download
    fetch = ThreadPoolExecutor(1)
    video = None
    if src["type"] == "url":
        meta = media.info(src["url"])
        if meta["kind"] != "video":
            raise RuntimeError("That link is a channel or playlist, not a single video. Paste the link of one video.")
        if ((o["range_end"] or meta["duration"]) - (o["range_start"] or 0)) > config.MAX_VIDEO_HOURS * 3600:
            raise RuntimeError(f"That is longer than {config.MAX_VIDEO_HOURS:g} hours. Choose a shorter part of it under Options.")
        if meta["is_live"]:
            from . import live
            c = creators.get(job.get("creator"))
            if not c:
                up_name = (meta.get("uploader") or "").strip() or "Live Streamer"
                c = next((cr for cr in creators.all_creators() if cr.get("name", "").strip().lower() == up_name.lower()), None)
                if not c:
                    c = creators.create({"name": up_name, "channel": src["url"]})
            job["creator"] = c["id"]
            job.update(kind="live", status="live", stage="Connecting to the live stream",
                       title=meta.get("title") or "Live Stream", uploader=meta.get("uploader") or "",
                       duration=0, error=None)
            if not job.get("thumb") and media.save_thumb(d, url=src["url"]):
                job["thumb"] = True
            save(job)
            live.Session(job, c).start()
            return
        _set(job, title=meta["title"], uploader=meta["uploader"], duration=meta["duration"])
        if not job.get("thumb") and media.save_thumb(d, url=src["url"]):
            _set(job, thumb=True)
        usage.set_context(job["creator"], meta["title"])
        span = (o["range_end"] or meta["duration"]) - (o["range_start"] or 0)
        pieces = span > LONG_VIDEO or meta["duration"] <= 0
        if not pieces:  # shorter video: fetch all of it in the background while the audio is worked on
            video = fetch.submit(media.download, src["url"], d, int(o["quality"]))
        seen = [-1.0]

        def got(p):                       # the bar moves in whole percents: no need to save the file a hundred times a second
            if p - seen[0] >= 0.01 or p >= 1:
                seen[0] = p
                _set(job, progress=0.03 + 0.1 * p)

        audio_file = media.download_audio(src["url"], d, got)
    else:
        pieces, audio_file = False, Path(src["path"])
        info = media.probe(audio_file)
        if info["duration"] > config.MAX_VIDEO_HOURS * 3600:
            raise RuntimeError(f"That video is longer than {config.MAX_VIDEO_HOURS:g} hours, which is the limit.")
        _set(job, source_path=str(audio_file), width=info["width"], height=info["height"], duration=info["duration"])
        if not job.get("thumb") and media.save_thumb(d, video=audio_file):
            _set(job, thumb=True)
    wav = d / "audio.wav"
    media.extract_audio(audio_file, wav)
    audio = media.load_audio(wav)
    wav.unlink(missing_ok=True)
    if src["type"] == "url":
        audio_file.unlink(missing_ok=True)
    if not job["duration"]:
        job["duration"] = len(audio) / 16000
    lo = int((o["range_start"] or 0) * 16000)
    hi = min(len(audio), int(o["range_end"] * 16000)) if o["range_end"] else len(audio)
    span = (hi - lo) / 16000
    db = media.loudness_per_second(audio[lo:hi])

    vlock, vstate = threading.Lock(), {}

    def whole_video():
        """Wait for the background download once; retry it, or give up and use pieces."""
        with vlock:
            if "path" not in vstate:
                path = None
                try:
                    path = video.result()
                except Exception as e:  # noqa: BLE001 - sites sometimes refuse a download
                    notes.append(f"Video download refused once ({str(e)[-80:]}), retrying")
                    try:
                        path = media.download(src["url"], d, int(o["quality"]))
                    except Exception as e2:  # noqa: BLE001
                        notes.append(f"Whole-video download failed ({str(e2)[-80:]}), fetching clip parts instead")
                if path:
                    info = media.probe(path)
                    job.update(source_path=str(path), width=info["width"], height=info["height"])
                vstate["path"] = path
            return vstate["path"]

    exact = {}      # clip id -> (from, to, words): our own model's words for just that clip

    began = {}      # clip id -> when work on it started

    def make(clip, words_now):
        began[clip["id"]] = time.time()
        if src["type"] == "url" and (pieces or not whole_video()):
            _fetch_piece(job, clip, audio)
        if clip["status"] != "error" and clip.get("captions", True) and yt_model:
            # The clip was found with YouTube's transcript. What is shown on screen comes from our own model,
            # run on just this clip: full punctuation, nothing blanked out, timings to the word.
            a0, b0 = max(lo, int((clip["start"] - 1.5) * 16000)), min(hi, int((clip["end"] + 1.5) * 16000))
            try:
                tw = [dict(w, s=round(w["s"] + a0 / 16000, 2), e=round(w["e"] + a0 / 16000, 2))
                      for w in transcribe.transcribe(audio[a0:b0], lang=yt_model)]
            except Exception:  # noqa: BLE001 - the clip is still made, with YouTube's words
                tw = []
            if len(tw) >= 3:
                exact[clip["id"]] = (a0 / 16000, b0 / 16000, tw)
                words_now = tw
        if clip["status"] != "error":
            render_one(job, clip, words_now)

    cpus = os.cpu_count() or 4
    renders = ThreadPoolExecutor(2 if cpus < 8 else min(6, cpus // 6))  # more clips made at once on a bigger machine
    futures = []
    step = BLOCK * 16000 if span > PROGRESSIVE_FROM else hi - lo
    blocks = [(x, min(hi, x + step)) for x in range(lo, hi, step)] or [(lo, hi)]
    words, tokens, model = [], 0, None
    done_blocks = 0
    yt = None
    if src["type"] == "url" and config.YT_TRANSCRIPT and media.is_youtube(src["url"]):
        try:
            yt = media.youtube_words(src["url"])
        except Exception:  # noqa: BLE001 - no transcript to borrow: ours is written as usual
            yt = None
        if yt and not _covers(yt[0], lo / 16000, hi / 16000):
            yt = None
        job["transcript_from"] = "youtube" if yt else "own"
    # The language spoken decides the captions: YouTube's word for it when its transcript is used, else the choice made.
    job["lang"] = yt[1] if yt else speech
    # A clip found with YouTube's transcript gets its on-screen words from our own model, when there is one here
    # for the language YouTube says was spoken (English always; others once they are downloaded).
    yt_code = (yt[1].lower().split("-")[0] if yt else "")
    yt_model = yt_code if fetch_model.known(yt_code) and (yt_code == fetch_model.DEFAULT or fetch_model.ready(yt_code)) else ""
    if not yt and speech != fetch_model.DEFAULT and not transcribe.REMOTE and not fetch_model.ready(speech):
        if fetch_model.state[speech]["doing"]:
            _set(job, stage=f"Waiting for the {fetch_model.label(speech)} speech model to finish downloading")
        fetch_model.ensure(speech, start=False)      # waits for a download already running, else says what to do
    if resuming:
        try:
            words = json.loads((d / "words.json").read_text(encoding="utf-8"))
        except ValueError:
            words = []
        done_blocks = min(int(job.get("done_blocks", 0)), len(blocks)) if words else 0
        tokens, model = int((job.get("ai") or {}).get("tokens", 0)), (job.get("ai") or {}).get("model")
        if done_blocks < len(blocks):     # words past the last finished part are transcribed again
            cut = blocks[done_blocks][0] / 16000
            words = [w for w in words if w["s"] < cut]
        for c in job["clips"]:            # clips found before the restart that were not finished yet
            if c.get("status") not in ("done", "error"):
                c["status"] = "queued"
                futures.append((renders.submit(ctx.bind(make), c, list(words)), c))
        save(job)
    # The transcript of the next part is written while the AI is still reading this one (the AI is a wait on the
    # network, the transcript is work on this machine), so neither waits for the other.
    ahead = ThreadPoolExecutor(2, thread_name_prefix="ahead")
    heard, now_on = {}, [done_blocks]

    def hear(i):
        if i < len(blocks) and i >= done_blocks and i not in heard:
            a_, b_ = blocks[i]
            last = [0.0]

            def tp(p, i=i, a_=a_, b_=b_):
                if now_on[0] == i and p - last[0] > 0.05:      # only the part being shown moves the bar
                    last[0] = p
                    _set(job, progress=max(job["progress"], 0.14 + 0.78 * ((a_ - lo) + p * (b_ - a_)) / max(1, hi - lo)))
            heard[i] = ahead.submit(ctx.bind(transcribe.transcribe), audio[a_:b_], tp, speech)

    # The ad breaks and static screens of the whole video, found once. It reads the video end to end,
    # so it is done here rather than for each clip, and only when asked for.
    statics = quality.static_ranges(job.get("source_path") or "") if config.SKIP_STATIC else []

    # Collect previously exported clip spans & text fingerprints across canonical source IDs
    # (equivalent YouTube links like watch?v= and youtu.be/ resolve to the same canonical ID).
    # Failed exports (status == "error") stay retryable and do NOT block re-clipping.
    canon_id = job.get("canonical_source_id") or media.canonical_source_id(
        src.get("url") or "", src.get("name") or job.get("title") or ""
    )
    job["canonical_source_id"] = canon_id
    prior_spans, prior_word_sets = [], []
    if ai.skip_duplicates():
        for prev_j in _jobs.values():
            if prev_j.get("id") == job.get("id"):
                continue
            prev_canon = prev_j.get("canonical_source_id") or media.canonical_source_id(
                (prev_j.get("source") or {}).get("url") or "", (prev_j.get("source") or {}).get("name") or prev_j.get("title") or ""
            )
            same_source = bool(canon_id and prev_canon and canon_id == prev_canon)
            if same_source:
                prev_words = safe.load_json_with_backup(Path(prev_j["dir"]) / "words.json", default=[]) if prev_j.get("dir") else []
                for pc in prev_j.get("clips", []):
                    if pc.get("status") == "error":
                        continue
                    ps, pe = pc.get("start"), pc.get("end")
                    if ps is not None and pe is not None and pe > ps:
                        prior_spans.append((float(ps), float(pe)))
                        p_tokens = {re.sub(r"\W+", "", str(w.get("w", "")).lower())
                                    for w in (prev_words or [])
                                    if ps - 1.0 <= _f(w.get("s")) <= pe + 1.0}
                        p_tokens.discard("")
                        if len(p_tokens) >= 4:
                            prior_word_sets.append(p_tokens)

    # Sample keyframes if whole source video is already local (for quiet visual moments in Pass 1/2)
    vid_local_path = Path(job["source_path"]) if job.get("source_path") and Path(job["source_path"]).is_file() else None
    if not vid_local_path and video is not None and not pieces:
        try:
            vp = whole_video()
            if vp and Path(vp).is_file():
                vid_local_path = Path(vp)
        except Exception:
            vid_local_path = None

    for bi, (a, b) in enumerate(blocks):
        if bi < done_blocks:
            continue                      # transcribed and checked by the AI before the restart
        shift = a / 16000
        where = f" (minute {round((a - lo) / 16000 / 60)} of {round(span / 60)})" if len(blocks) > 1 else ""
        if yt:
            _set(job, stage="Reading the transcript" + where)
            bw = [dict(w, s=round(w["s"] - shift, 2), e=round(w["e"] - shift, 2)) for w in yt[0] if a / 16000 <= w["s"] < b / 16000]
        else:
            _set(job, stage="Writing the transcript" + where)
            now_on[0] = bi
            hear(bi)
            hear(bi + 1)
            bw = heard.pop(bi).result()
        _set(job, progress=max(job["progress"], 0.14 + 0.78 * (b - lo) / max(1, hi - lo)))
        words += [dict(w, s=round(w["s"] + shift, 2), e=round(w["e"] + shift, 2)) for w in bw]
        safe.atomic_write_text(d / "words.json", json.dumps(words), backup=True)
        _set(job, stage="Finding the best moments" + where, word_count=len(words))
        left = int(o["max_clips"]) - len(job["clips"])
        if left <= 0 or (len(bw) < 8 and not vid_local_path):
            job["done_blocks"] = bi + 1
            save(job)
            continue
        quota = max(1, math.ceil(left / (len(blocks) - bi)))
        s0 = int((a - lo) / 16000)
        block_dur = (b - a) / 16000
        block_keyframes = []
        if vid_local_path:
            raw_kf = media.extract_overview_keyframes(vid_local_path, shift, shift + block_dur, count=8)
            block_keyframes = [(round(t - shift, 2), kb) for t, kb in raw_kf]

        def _review_window_media(wa: float, wb: float) -> list[tuple[str, bytes]]:
            if not vid_local_path or not vid_local_path.is_file():
                return []
            proxy = media.extract_proxy_clip(vid_local_path, shift + wa, shift + wb)
            if proxy:
                return [("video/mp4", proxy)]
            f_bytes = extract_clip_frames_bytes(vid_local_path, shift + wa, shift + wb, n_frames=6)
            return [("image/jpeg", fb) for fb in f_bytes]

        found, ai_info = brain.find_clips(
            bw, db[s0: s0 + int(block_dur) + 1], block_dur, job["title"],
            job["uploader"], quota, int(o["min_len"]), int(o["max_len"]), notes.append, game=game,
            keyframes=block_keyframes, review_media=_review_window_media if vid_local_path else None,
        )
        tokens += ai_info.get("tokens", 0)
        model = ai_info.get("model") or model
        if ai_info.get("note"):
            notes.append(ai_info["note"])
        if found:
            keep = []
            for c in found:
                a_s, b_s = c["start"] + shift, c["end"] + shift
                if statics:
                    inside = quality.static_overlap(a_s, b_s, statics)
                    if inside > 0.5 * max(1.0, b_s - a_s):
                        notes.append(f"A clip from {round(a_s)}s was left out: it sat in an ad break or a static screen.")
                        continue
                if prior_spans:
                    # Check both temporal overlap AND transcript Jaccard similarity for shifted duplicates
                    overlapped = any(max(0.0, min(b_s, pe) - max(a_s, ps)) >= min(4.0, 0.25 * (b_s - a_s)) for ps, pe in prior_spans)
                    if not overlapped and prior_word_sets:
                        c_tokens = {re.sub(r"\W+", "", str(w.get("w", "")).lower())
                                    for w in words if a_s - 1.0 <= _f(w.get("s")) <= b_s + 1.0}
                        c_tokens.discard("")
                        if len(c_tokens) >= 4:
                            overlapped = any(
                                len(c_tokens & pw) / max(1, len(c_tokens | pw)) >= 0.50
                                for pw in prior_word_sets
                            )
                    if overlapped:
                        notes.append(f"Skipping {round(a_s)}s-{round(b_s)}s: already exported for this source.")
                        continue
                keep.append(c)
            found = keep
        for c in found:
            c_start, c_end = round(c["start"] + shift, 2), round(c["end"] + shift, 2)
            p_at = round(float(c["payoff_at"]) + shift, 2) if c.get("payoff_at") is not None else round(c_start + (c_end - c_start) * 0.65, 2)
            p_at = max(c_start, min(c_end, p_at))
            c.update(id=f"clip{len(job['clips']) + 1:02d}", start=c_start,
                     end=c_end, payoff_at=p_at, style=o["style"], layout=o["layout"],
                     captions=o.get("captions", True), status="queued", version=0)
            c.setdefault("community_text", brain.build_community_post(
                c.get("seo_title") or c.get("title") or "",
                c.get("description") or "",
                c.get("pinned_comment") or "",
                c.get("hashtags") or [],
            ))
            if o.get("hook_text"):        # the person's own big text, on every clip, in place of the AI's
                c["hook"] = o["hook_text"]
            if o.get("description_text"):  # ...and their own description, exactly as written
                c["description"], c["fixed_description"] = o["description_text"], True
            else:                          # no description of their own: 3 to 5 fitting hashtags go at the end of the AI's
                hashtags.apply(c, words, job["title"], job["uploader"], game)
            if o.get("layout") in ("gameplay", "split", "split_half"):
                if not face:
                    face = _facecam(job)
                if face:
                    c["facecam"] = face
                    if o.get("facecam_pos"):
                        c["facecam_pos"] = o["facecam_pos"]
            job["clips"].append(c)
            futures.append((renders.submit(ctx.bind(make), c, list(words)), c))
        job["ai"] = {"model": model, "tokens": tokens, "note": "", "log": notes[-5:]}
        job["done_blocks"] = bi + 1       # a restart from here on carries on with the next part
        save(job)
    already_short_exported = bool(prior_spans) and any(
        max(0.0, min(float(job.get("duration") or 0), pe) - max(0.0, ps)) >= 3.0 for ps, pe in prior_spans
    )
    if not job["clips"] and job.get("duration", 0) <= 90 and not already_short_exported:
        # Short video or highlight submitted: automatically format and render the whole clip
        v_dur = float(job["duration"])
        desc_text = " ".join(w["w"] for w in words) if words else (job.get("title") or "Gaming Short")
        c_info = brain.describe(desc_text, job.get("title", ""), job.get("uploader", ""), game=game)
        c_info.update(id="clip01", start=0.0, end=round(v_dur, 2), payoff_at=round(v_dur * 0.65, 2),
                      style=o["style"], layout=o["layout"],
                      captions=o.get("captions", True), status="queued", version=0,
                      analysis_mode="transcript_only" if ai.ready() else "offline_fallback")
        c_info.setdefault("community_text", brain.build_community_post(
            c_info.get("seo_title") or c_info.get("title") or "",
            c_info.get("description") or "",
            c_info.get("pinned_comment") or "",
            c_info.get("hashtags") or [],
        ))
        if o.get("layout") in ("gameplay", "split", "split_half"):
            if not face:
                face = _facecam(job)
            if face:
                c_info["facecam"] = face
                if o.get("facecam_pos"):
                    c_info["facecam_pos"] = o["facecam_pos"]
        job["clips"].append(c_info)
        futures.append((renders.submit(ctx.bind(make), c_info, list(words)), c_info))
    if futures:
        _set(job, stage="Finishing the clips", progress=max(job["progress"], 0.92))
    _wait_for_clips(job, futures, began, renders._max_workers)
    if exact:           # keep our own words for the clips in the saved transcript, so editing a clip later uses them
        for a_s, b_s, tw in exact.values():
            words = [w for w in words if not a_s <= w["s"] < b_s] + tw
        words.sort(key=lambda w: w["s"])
        safe.atomic_write_text(d / "words.json", json.dumps(words), backup=True)
    renders.shutdown(wait=False)
    ahead.shutdown(wait=False)
    fetch.shutdown(wait=False)
    del audio
    clips = job["clips"]
    job["ai"] = {"model": model, "tokens": tokens, "log": notes[-5:],
                 "note": "The AI was unavailable, so clips were picked by loudness only." if clips and not model else ""}
    stage = "Done" if clips else "Done, but nothing clip-worthy was found"
    _set(job, status="done", stage=stage, progress=1.0, took=round(time.time() - t0))
    try:
        from . import notices
        name = job.get("title") or job["source"].get("name") or "your video"
        notices.add(job.get("user"), "clips", f"{len(clips)} clip{'s' if len(clips) != 1 else ''} ready" if clips else "Nothing clip-worthy found",
                    name, f"/app/creators/{job['creator']}" if job.get("creator") else "/app/videos")
    except Exception:  # noqa: BLE001
        pass
    creators.log(job["creator"], f"Video finished with {len(clips)} clips in {round(time.time() - t0)}s: {job['title']}")


def _worker(quick_only=False):
    while True:
        kind, a, cid = _q.get(quick_only)
        if kind == "fn":
            try:
                a()
            except Exception:  # noqa: BLE001
                traceback.print_exc()
            continue
        job = _jobs.get(a)
        if not job:
            if kind == "job":
                _q.done()
            continue
        token = ctx._uid.set(job["user"])  # everything this job does runs as its owner
        try:
            if kind == "job":
                _run_job(job)
            else:
                clip = next(c for c in job["clips"] if c["id"] == cid)
                words = []
                use_caps = clip.get("captions")
                if use_caps is None:
                    use_caps = job.get("options", {}).get("captions", True)
                if use_caps and (Path(job["dir"]) / "words.json").exists():
                    words = json.loads((Path(job["dir"]) / "words.json").read_text(encoding="utf-8"))
                render_one(job, clip, words)
        except Exception as e:  # noqa: BLE001
            (Path(job["dir"]) / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            if kind == "job":
                for c in job["clips"]:
                    if c.get("status") in ("queued", "rendering"):
                        c.update(status="error", error="The video stopped before this clip was made.")
                _set(job, status="error", error=safe.friendly(e), stage="Stopped")
                creators.log(job["creator"], f"Video failed: {safe.friendly(e)[:200]}")
        finally:
            ctx._uid.reset(token)
            if kind == "job":
                _q.done()


def _pick_up_after_restart():
    """Videos and single clips that were being made when the server stopped: queued again, oldest first."""
    waiting = sorted((j for j in all_jobs() if j.get("status") == "queued" and j.get("resume")), key=lambda j: j["created"])
    for j in waiting:
        _q.put(("job", j["id"], None), user=j["user"])
    for j in all_jobs():
        for cid in j.pop("remake", []):
            _q.put(("clip", j["id"], cid))
        if j.get("status") == "done":
            save(j)


def start():
    load.start()
    load_all()
    _pick_up_after_restart()
    for _ in range(max(1, config.JOB_WORKERS)):
        threading.Thread(target=_worker, daemon=True).start()
    threading.Thread(target=_worker, args=(True,), daemon=True).start()   # re-making a single clip never waits behind whole videos
    threading.Thread(target=_live_worker, daemon=True).start()
