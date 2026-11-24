"""Creator workspaces. Each user has their own: users/<user>/creators/<id>/{videos,live,creator.json,log.jsonl}."""
import copy
import json
import re
import threading
import time
from pathlib import Path

from . import config, ctx, safe


def _root() -> Path:
    return config.user_dir(ctx.uid()) / "creators"

_lock = threading.RLock()

MASTER_TRIGGER_WORDS = (
    "clip that, clip it, clip karo, ye clip karo, isko clip karo, clip this, clip this shit, clip that shit, "
    "someone clip that, somebody clip that, please clip that, you better clip that, that's a clip, that's clip worthy, "
    "clip worthy, highlight that, save that clip, omg clip that, wtf clip that, viral moment, clip this right now, "
    "oh my god clip that, clip clip clip, bro clip that, someone gotta clip that, yeh clip karo, isse clip karo, "
    "clip karo bhai, jaldi clip karo, koi clip karo, bhai clip karo, clip banao, iska clip banao, ye clip banta hai, "
    "yeh clip banta hai, viral clip hai, isko save karo, ye save karo, bhai save karo"
)

DEFAULTS = {"name": "", "channel": "", "style": "bounce", "layout": "split_half", "captions": True, "min_len": 15, "max_len": 60,
            "max_clips": 6, "min_score": 80, "auto_watch": False, "buffer_min": 20, "live_per_hour": 25, "ai_every_min": 3, "ai_only_on_spike": True, "auto_jump_pct": 60,
            "plan": "free", "decide_mode": "both", "must_clip_min": 0, "min_gap_min": 2,
            "game": "", "quality": 1080, "hook_text": "", "description_text": "",
            "trigger_words": MASTER_TRIGGER_WORDS,
            "autopost": False, "accounts": [], "post_min_score": 75, "post_gap_min": 45, "daily_cap": 6,
            "privacy": "public", "post_footer": "", "rate_per_1k": 0.0, "channels": {}, "active_preset": "",
            "facecam_pos": "top-right", "facecam_delay": 0.0, "audio_delay": 0.0, "hook_style": "neon", "outro_cta": True, "outro_text": "",
            "custom_layout": {"enabled": False, "mode": "split", "facecam": [0, 0, 480, 360], "gameplay": [0, 0, 1920, 1080], "split_ratio": 0.35, "pip_pos": "top-right", "pip_size": 380, "divider": True},
            "custom_presets": {},
            "post_cleanup": "ask", "trim_silence": False, "lang": "en"}
PLATFORMS = ("youtube", "twitch", "kick")


def clean_hook(v) -> str:
    """The big text a person typed for their clips: one line, as they wrote it (links and @names stay, a campaign
    may need them), and short enough to sit in the box on the video."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in str(v or "")).split())[:60]


def clean_description(v) -> str:
    """The description a person typed for their clips: as they wrote it, line breaks included, so a campaign's
    set text (links, @names, hashtags) is not changed. Control characters go, and it is cut at 2000 characters."""
    nl, cr, tab = chr(10), chr(13), chr(9)
    lines = ("".join(ch if ch.isprintable() or ch == tab else " " for ch in line).rstrip()
             for line in str(v or "").replace(cr + nl, nl).replace(cr, nl).split(nl))
    return nl.join(lines).strip()[:2000]


def platform_key(url: str) -> str:
    from urllib.parse import urlparse
    h = (urlparse(url if "://" in url else "https://" + url).hostname or "").lower()
    return "youtube" if "youtube" in h or h == "youtu.be" else "twitch" if "twitch" in h else "kick" if "kick" in h else ""


def _fix(c: dict) -> dict:
    """One channel per platform in `channels`; `channel` is the one to record from and is always one of them."""
    ch = {k: v for k, v in (c.get("channels") or {}).items() if k in PLATFORMS and v}
    if c.get("channel") and platform_key(c["channel"]) and c["channel"] not in ch.values():
        ch.setdefault(platform_key(c["channel"]), c["channel"])
    c["channels"] = ch
    if not c.get("ai_every_min"):
        c["ai_every_min"] = 3       # "Auto" (0) is gone: jumps in loudness and chat are now always checked
    if c.get("channel") not in ch.values():
        c["channel"] = next((ch[k] for k in PLATFORMS if k in ch), "")
    if not c.get("layout"):
        c["layout"] = "split"
    if "trigger_words" not in c or c["trigger_words"] is None:
        c["trigger_words"] = MASTER_TRIGGER_WORDS
    else:
        c["trigger_words"] = str(c["trigger_words"]).strip()[:5000]
    return c
NUMERIC = {"min_len": (5, 120), "max_len": (10, 180), "max_clips": (1, 20), "min_score": (0, 100), "buffer_min": (5, 120), "live_per_hour": (1, 60), "ai_every_min": (1, 30), "auto_jump_pct": (20, 300), "must_clip_min": (0, 240), "min_gap_min": (0, 60),
           "post_min_score": (0, 100), "post_gap_min": (5, 1440), "daily_cap": (1, 50), "quality": (360, 1080)}


def root(cid) -> Path:
    if not re.fullmatch(r"[\w\-]{1,60}", cid or ""):
        raise ValueError("bad creator id")
    return _root() / cid


def _clean(data: dict) -> dict:
    out = {}
    for k in DEFAULTS:
        if k == "captions":
            if k in data:
                if not isinstance(data[k], bool):
                    raise ValueError("Captions must be on or off.")
                out[k] = data[k]
            continue
        if k not in data or data[k] is None:
            continue
        v = data[k]
        if k in NUMERIC:
            lo, hi = NUMERIC[k]
            v = max(lo, min(hi, int(float(v))))
        elif k in ("auto_watch", "autopost", "ai_only_on_spike", "trim_silence"):
            v = bool(v)
        elif k == "channels":
            v = {p: str(u).strip()[:300] for p, u in (v.items() if isinstance(v, dict) else []) if p in PLATFORMS and str(u).strip()}
        elif k == "accounts":
            v = [str(x) for x in v][:20] if isinstance(v, list) else []
        elif k in ("facecam_delay", "audio_delay"):
            try:
                v = max(-1.0, min(1.0, float(v or 0.0)))
            except (ValueError, TypeError):
                v = 0.0
        elif k == "outro_cta":
            v = bool(v)
        elif k == "active_preset":
            v = str(v).strip()[:60]
        elif k == "hook_text":
            v = clean_hook(v)
        elif k == "description_text":
            v = clean_description(v)
        elif k == "rate_per_1k":
            v = max(0.0, min(1000.0, float(v or 0)))
        elif k == "plan":
            v = v if v in ("free", "pro", "max") else "free"
        elif k == "decide_mode":
            v = v if v in ("both", "either") else "both"
        elif k == "privacy":
            v = v if v in ("public", "unlisted", "private") else "public"
        elif k == "post_cleanup":
            v = str(v).lower() if str(v).lower() in ("ask", "auto", "keep") else "ask"
        elif k == "trigger_words":
            v = str(v).strip()[:5000]
        elif k == "custom_layout":
            if isinstance(v, dict):
                cl = {}
                cl["enabled"] = bool(v.get("enabled", False))
                cl["mode"] = str(v.get("mode", "split")).lower()
                cl["split_ratio"] = max(0.15, min(0.85, float(v.get("split_ratio", 0.35))))
                cl["pip_pos"] = str(v.get("pip_pos", "top-right")).lower()
                cl["pip_size"] = max(100, min(800, int(v.get("pip_size", 380))))
                cl["divider"] = bool(v.get("divider", True))
                try:
                    cl["facecam"] = [max(0, int(x)) for x in v.get("facecam", [0, 0, 480, 360])[:4]]
                except Exception:
                    cl["facecam"] = [0, 0, 480, 360]
                try:
                    cl["gameplay"] = [max(0, int(x)) for x in v.get("gameplay", [0, 0, 1920, 1080])[:4]]
                except Exception:
                    cl["gameplay"] = [0, 0, 1920, 1080]
                v = cl
            else:
                v = copy.deepcopy(DEFAULTS["custom_layout"])
        elif k == "custom_presets":
            cleaned_presets = {}
            if isinstance(v, dict):
                for pname, pdata in v.items():
                    pname_clean = str(pname).strip()[:50]
                    if not pname_clean or not isinstance(pdata, dict):
                        continue
                    p_obj = {
                        "name": pname_clean,
                        "mode": str(pdata.get("mode", "split")).lower(),
                        "split_ratio": max(0.15, min(0.85, float(pdata.get("split_ratio", 0.35)))),
                        "pip_pos": str(pdata.get("pip_pos", "top-right")).lower(),
                        "pip_size": max(100, min(800, int(pdata.get("pip_size", 380)))),
                        "divider": bool(pdata.get("divider", True))
                    }
                    try:
                        p_obj["facecam"] = [max(0, int(x)) for x in pdata.get("facecam", [0, 0, 480, 360])[:4]]
                    except Exception:
                        p_obj["facecam"] = [0, 0, 480, 360]
                    try:
                        p_obj["gameplay"] = [max(0, int(x)) for x in pdata.get("gameplay", [0, 0, 1920, 1080])[:4]]
                    except Exception:
                        p_obj["gameplay"] = [0, 0, 1920, 1080]
                    cleaned_presets[pname_clean] = p_obj
            v = cleaned_presets
        elif k in ("facecam_pos", "hook_style", "outro_text"):
            v = str(v).strip()[:100]
        elif k == "lang":
            from . import fetch_model
            v = v if fetch_model.known(v) else "en"
        else:
            v = str(v).strip()[:300]
        out[k] = v
    return out


_mem: dict = {}   # user -> {creator id: creator}. The files stay the truth; this saves re-reading them on every page check.


def _mine() -> dict:
    u = ctx.uid()
    got = _mem.get(u)
    if got is None:
        got = {}
        for f in sorted(_root().glob("*/creator.json")):
            raw = safe.load_json_with_backup(f)
            if isinstance(raw, dict):
                c = _fix({**DEFAULTS, **raw})
                got[c.get("id") or f.parent.name] = c
        with _lock:
            got = _mem.setdefault(u, got)
    return got


def forget(uid: str):
    """Files were changed from outside this module (old data moved in): read them again next time."""
    _mem.pop(uid, None)
    ctx.bump(uid)


def all_creators() -> list:
    return [copy.deepcopy(c) for c in list(_mine().values())]


def get(cid):
    if not cid or not re.fullmatch(r"[\w\-]{1,60}", str(cid)):
        return None
    c = _mine().get(str(cid))
    return copy.deepcopy(c) if c else None


def _write(c):
    with _lock:
        d = root(c["id"])
        for sub in ("videos", "live"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        safe.atomic_write_text(d / "creator.json", json.dumps(c, indent=1), backup=True)
        _mine()[c["id"]] = copy.deepcopy(c)
    ctx.bump()


def create(data: dict) -> dict:
    c = _fix({**DEFAULTS, **_clean(data)})
    if not c["name"]:
        raise ValueError("Give the creator a name.")
    slug = re.sub(r"[^a-z0-9]+", "-", c["name"].lower()).strip("-")[:40] or "creator"
    cid, n = slug, 2
    while root(cid).exists():
        cid, n = f"{slug}-{n}", n + 1
    c.update(id=cid, created=time.time())
    _write(c)
    log(cid, f"Workspace created for {c['name']}")
    return c


def update(cid, data: dict) -> dict:
    c = get(cid)
    if not c:
        raise KeyError(cid)
    new = _clean(data)
    if "channels" in new and "channel" not in new and c["channel"] not in new["channels"].values():
        c["channel"] = ""  # the recording channel was removed: fall back to another one
    if "channel" in new and new["channel"] and "channels" not in new:
        new["channels"] = {**c["channels"], platform_key(new["channel"]): new["channel"]}
    c.update(new)
    _fix(c)
    if c["min_len"] >= c["max_len"]:
        raise ValueError("Shortest clip must be shorter than longest clip.")
    _write(c)
    return c


def set_profiles(cid, profiles: dict, extra: dict = None):
    """Each channel's public profile and live state, written by profiles.refresh. `profile` is the recording
    channel's one, used for the creator's picture."""
    with _lock:
        c = get(cid)
        if not c:
            return
        before = json.dumps([c.get("profiles"), {k: c.get(k) for k in (extra or {})}], sort_keys=True, default=str)
        c["profiles"] = {k: v for k, v in profiles.items() if k in c["channels"]}
        main = platform_key(c["channel"]) if c["channel"] else ""
        c["profile"] = c["profiles"].get(main) or next(iter(c["profiles"].values()), {})
        c.update(extra or {})
        same = re.sub(r'"live_at": [\d.]+', "", before) == re.sub(
            r'"live_at": [\d.]+', "", json.dumps([c["profiles"], {k: c.get(k) for k in (extra or {})}], sort_keys=True, default=str))
        if same:       # only "checked just now" moved on: remember it, but there is nothing new to save or show
            _mine()[c["id"]] = copy.deepcopy(c)
            return
        _write(c)


def log(cid, msg: str):
    if not cid or ctx.uid_or_none() is None or not root(cid).exists():
        return
    path = root(cid) / "log.jsonl"
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"t": time.time(), "msg": msg}) + "\n")
        try:
            if path.stat().st_size > LOG_MAX_BYTES:         # a stream that runs for weeks must not grow this for ever
                keep = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-LOG_KEEP_LINES:]
                path.write_text("\n".join(keep) + "\n", encoding="utf-8")
        except OSError:
            pass
    ctx.bump()


LOG_MAX_BYTES, LOG_KEEP_LINES, LOG_TAIL_BYTES = 1_000_000, 500, 64 * 1024


def read_log(cid, n=40) -> list:
    """The newest n lines, newest first. Only the end of the file is read: the page asks for this all the time."""
    f = root(cid) / "log.jsonl"
    try:
        size = f.stat().st_size
        with f.open("rb") as h:
            h.seek(max(0, size - LOG_TAIL_BYTES))
            raw = h.read()
    except OSError:
        return []
    lines = raw.decode("utf-8", errors="ignore").splitlines()
    if size > LOG_TAIL_BYTES:
        lines = lines[1:]                                   # the first one starts in the middle of a line
    out = []
    for x in reversed(lines[-n:]):
        try:
            out.append(json.loads(x))
        except ValueError:
            pass
    return out
