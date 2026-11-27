"""Signature Brand Auto-Editing Engine for PeakCut / ClipNova AI.

Gives every creator a consistent, recognizable, high-retention YouTube Shorts editing style:
- Smart mid-clip pause tightening (`tighten_clip_segments`) keeping 1:1 subtitle word sync
- Real climax beat detection from speech loudness/energy + reaction cues
- Automatic placement of real motion VFX (`zoom_punch`, `slow_zoom`, `shake`, `flash`)
- Automatic placement of short punchy SFX from the user's own custom Sounds folder
- Signature color polish (`brand_pop`, `vibrant`, `cinematic`) & optional `@handle` watermark
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

BRAND_PROFILES: dict[str, dict[str, Any]] = {
    "viral_gaming": {
        "label": "🔥 Viral Gaming Signature (Recommended)",
        "filter": "brand_pop",
        "max_gap": 0.85,
        "keep_pad": 0.24,
        "opening_vfx": "zoom_punch",
        "climax_vfx": ("zoom_punch", "shake"),
        "max_vfx": 3,
        "max_sfx": 2,
    },
    "chaos_meme": {
        "label": "💀 Unhinged Meme Energy (Fast Cuts + Shake + Flash)",
        "filter": "vibrant",
        "max_gap": 0.65,
        "keep_pad": 0.18,
        "opening_vfx": "zoom_punch",
        "climax_vfx": ("shake", "flash"),
        "max_vfx": 4,
        "max_sfx": 2,
    },
    "cinematic": {
        "label": "🎬 Cinematic Storyteller (Slow Zoom + Film Grade)",
        "filter": "cinematic",
        "max_gap": 0.95,
        "keep_pad": 0.28,
        "opening_vfx": "slow_zoom",
        "climax_vfx": ("slow_zoom", "zoom_punch"),
        "max_vfx": 2,
        "max_sfx": 1,
    },
    "clean": {
        "label": "✨ Clean Minimal Pro (Tight Pauses + Crisp Color)",
        "filter": "brand_pop",
        "max_gap": 0.95,
        "keep_pad": 0.26,
        "opening_vfx": "slow_zoom",
        "climax_vfx": ("zoom_punch",),
        "max_vfx": 2,
        "max_sfx": 0,
    },
    "off": {
        "label": "Raw / Manual Studio Only (No Auto-FX)",
        "filter": None,
        "max_gap": 999.0,
        "keep_pad": 0.30,
        "opening_vfx": None,
        "climax_vfx": (),
        "max_vfx": 0,
        "max_sfx": 0,
    },
}


def _f(v: Any, default: float = -1.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def tighten_clip_segments(
    words: list[dict[str, Any]],
    start: float,
    end: float,
    max_gap: float = 0.85,
    keep_pad: float = 0.24,
    min_out_dur: float = 12.0,
    max_segments: int = 8,
) -> list[dict[str, float]]:
    """Cut long mid-clip dead pauses (`> max_gap`) into snappy jump-cut segments.

    Returns an empty list when tightening would save `< 1.2s` or shrink below `min_out_dur`.
    Each segment carries `{start, end, orig_start, orig_end}` compatible with `render.render_clip()`.
    """
    s, e = float(start), float(end)
    orig_dur = e - s
    if orig_dur <= min_out_dur + 1.2 or not words or max_gap >= 50.0:
        return []

    in_span = []
    for w in words:
        if not isinstance(w, dict) or not str(w.get("w") or "").strip():
            continue
        ws = _f(w.get("s"))
        we = _f(w.get("e"), ws + 0.2)
        if ws >= s - 0.1 and ws <= e + 0.1:
            in_span.append((max(s, ws), min(e, max(ws + 0.05, we))))

    if len(in_span) < 4:
        return []
    in_span.sort(key=lambda x: x[0])

    # Merge tiny inter-word breaks so only real dead-air pauses (> max_gap) trigger a jump cut
    blocks: list[list[float]] = []
    for ws, we in in_span:
        if not blocks or (ws - blocks[-1][1]) > max_gap:
            blocks.append([ws, we])
        else:
            blocks[-1][1] = max(blocks[-1][1], we)

    if len(blocks) < 2:
        return []

    # Include slight opening & trailing room while tightening interior gaps
    raw_segs: list[list[float]] = []
    for i, (bs, be) in enumerate(blocks):
        seg_s = s if i == 0 else max(s, bs - keep_pad)
        seg_e = e if i == len(blocks) - 1 else min(e, be + keep_pad)
        if raw_segs and seg_s <= raw_segs[-1][1] + 0.15:
            raw_segs[-1][1] = max(raw_segs[-1][1], seg_e)
        else:
            raw_segs.append([seg_s, seg_e])

    if len(raw_segs) < 2 or len(raw_segs) > max_segments:
        return []
    new_dur = sum(max(0.2, b - a) for a, b in raw_segs)
    if new_dur < min_out_dur or (orig_dur - new_dur) < 1.2:
        return []
    # Emit clip-relative start/end [0..orig_dur] for jobs.py resolver + absolute orig_start/orig_end
    return [
        {
            "start": round(a - s, 3),
            "end": round(b - s, 3),
            "orig_start": round(a, 3),
            "orig_end": round(b, 3),
        }
        for a, b in raw_segs
    ]


def _audio_rms_peaks(src: Path, start: float, end: float, bucket_sec: float = 0.5) -> list[tuple[float, float]]:
    """Sample audio energy across [start, end] using ffmpeg astats when available; returns [(rel_t, rms_db)]."""
    dur = max(0.5, end - start)
    if not src or not src.is_file() or dur > 180.0:
        return []
    try:
        r = subprocess.run(
            [
                "ffmpeg", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{dur:.2f}",
                "-i", str(src), "-vn",
                "-af", f"asetnsamples=n={int(48000 * bucket_sec)}:p=0,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
                "-f", "null", "-",
            ],
            capture_output=True, text=True, timeout=8,
        )
        if r.returncode != 0:
            return []
        peaks: list[tuple[float, float]] = []
        cur_t = 0.0
        for line in (r.stdout or "").splitlines():
            m_t = re.search(r"pts_time:([\d.]+)", line)
            if m_t:
                cur_t = float(m_t.group(1))
            m_db = re.search(r"RMS_level=(-?[\d.]+)", line)
            if m_db:
                val = float(m_db.group(1))
                if val > -90.0:
                    peaks.append((round(cur_t, 2), val))
        return peaks
    except Exception:
        return []


def detect_climax_times(
    src: Path | None,
    start: float,
    end: float,
    words: list[dict[str, Any]] | None = None,
    segments: list[dict[str, Any]] | None = None,
    max_beats: int = 2,
) -> list[float]:
    """Identify 1-2 climax timestamps mapped onto the rendered output timeline [0..out_dur]."""
    out_dur = (
        sum(max(0.2, float(sg["end"]) - float(sg["start"])) for sg in segments)
        if segments else max(1.0, end - start)
    )

    def _to_out_t(abs_t: float) -> float | None:
        if not segments:
            if start <= abs_t <= end:
                return round(abs_t - start, 2)
            return None
        cum = 0.0
        for sg in segments:
            os_t = float(sg.get("orig_start", sg["start"]))
            oe_t = float(sg.get("orig_end", sg["end"]))
            sd = max(0.2, float(sg["end"]) - float(sg["start"]))
            if os_t - 0.15 <= abs_t <= oe_t + 0.15:
                return round(cum + max(0.0, min(sd, abs_t - os_t)), 2)
            cum += sd
        return None

    candidates: list[tuple[float, float]] = []

    # 1. Transcript excitement/loudness cues
    hype_re = re.compile(r"(no way|what|bro|holy|oh my|wtf|clip|dead|lost|insane|crazy|wait|run|help|haha|lmao|[!?]{1})", re.I)
    for w in (words or []):
        if not isinstance(w, dict):
            continue
        ws = _f(w.get("s"))
        if ws < start or ws > end:
            continue
        wt = str(w.get("w") or "")
        if hype_re.search(wt) or wt.isupper() and len(wt) >= 3:
            ot = _to_out_t(ws)
            if ot is not None and 1.8 <= ot <= max(2.0, out_dur - 1.5):
                candidates.append((1.0, ot))

    # 2. True audio RMS energy spikes
    rms = _audio_rms_peaks(src, start, end) if src else []
    if rms:
        rms_sorted = sorted(rms, key=lambda kv: -kv[1])
        for rel_t, db_val in rms_sorted[:6]:
            ot = _to_out_t(start + rel_t)
            if ot is not None and 1.8 <= ot <= max(2.0, out_dur - 1.4):
                candidates.append((100.0 + db_val, ot))

    # Fallback evenly paced climax beat when audio/transcript had no strong peak
    if not candidates and out_dur >= 6.0:
        candidates.append((10.0, round(out_dur * 0.55, 2)))
        if out_dur >= 18.0:
            candidates.append((8.0, round(out_dur * 0.80, 2)))

    candidates.sort(key=lambda x: -x[0])
    chosen: list[float] = []
    for _, ot in candidates:
        if all(abs(ot - c) >= 4.5 for c in chosen):
            chosen.append(ot)
            if len(chosen) >= max_beats:
                break
    chosen.sort()
    return chosen


def pick_custom_sfx_tracks(max_count: int = 2) -> list[dict[str, Any]]:
    """Return short punchy SFX ONLY from the user's custom Sounds directory (never deleted built-ins)."""
    try:
        from . import audio
        tracks = audio.list_tracks()
    except Exception:
        return []
    customs = [
        t for t in tracks
        if t.get("category") == "custom" and 0.1 <= float(t.get("duration") or 1.2) <= 5.0
    ]
    if not customs:
        return []
    # Prefer punchy impact/whoosh/boom/laugh names first, then deterministic order
    prio_re = re.compile(r"(whoosh|boom|vine|impact|hit|slam|pop|bruh|rizz|laugh|ding|horn|alert)", re.I)
    customs.sort(key=lambda t: (0 if prio_re.search(str(t.get("title") or "")) else 1, float(t.get("duration") or 2.0)))
    return customs[:max_count]


def apply_brand_edit(
    clip: dict[str, Any],
    job: dict[str, Any],
    creator: dict[str, Any] | None,
    src: Path | None,
    words: list[dict[str, Any]],
) -> dict[str, Any]:
    """Enrich a clip with signature brand editing (tight jump cuts, motion VFX, custom SFX, color & watermark).

    Strictly non-destructive: preserves any manual Studio VFX/SFX/filter/segments edits already set on `clip`.
    """
    o = (job or {}).get("options") or {}
    cr = creator or {}
    profile_id = str(clip.get("brand_style") or o.get("brand_style") or cr.get("brand_style") or "viral_gaming").strip().lower()
    if profile_id not in BRAND_PROFILES:
        profile_id = "viral_gaming"
    prof = BRAND_PROFILES[profile_id]
    clip["brand_style"] = profile_id

    # Watermark signature handle (creator setting -> job option -> clip)
    wm = str(clip.get("brand_watermark") if "brand_watermark" in clip else (o.get("brand_watermark") or cr.get("brand_watermark") or "")).strip()
    if wm:
        clip["brand_watermark"] = wm[:32]

    if profile_id == "off":
        return {"applied": False, "profile": "off"}

    # 1. Smart mid-clip jump-cut tightening (only on single-span auto/manual clips when not manually re-segmented)
    auto_tighten = bool(clip.get("auto_tighten", o.get("auto_tighten", cr.get("auto_tighten", True))))
    segs = clip.get("segments")
    if auto_tighten and not (isinstance(segs, list) and segs) and not clip.get("manual_words") and not clip.get("teaser_enabled"):
        tight_segs = tighten_clip_segments(
            words,
            float(clip.get("start") or 0.0),
            float(clip.get("end") or 0.0),
            max_gap=float(prof["max_gap"]),
            keep_pad=float(prof["keep_pad"]),
        )
        if tight_segs:
            clip["segments"] = tight_segs
            segs = tight_segs

    # 2. Brand color polish (preserve explicit user filter choice)
    if "video_filter" not in clip and prof.get("filter"):
        clip["video_filter"] = prof["filter"]

    # 3. Motion & Impact VFX cues (preserve manual Studio vfx_cues even if user cleared to [])
    beats = detect_climax_times(
        src,
        float(clip.get("start") or 0.0),
        float(clip.get("end") or 0.0),
        words=words,
        segments=segs if isinstance(segs, list) else None,
        max_beats=2,
    )
    if "vfx_cues" not in clip:
        vfx_list: list[dict[str, Any]] = []
        if prof.get("opening_vfx"):
            vfx_list.append({"type": prof["opening_vfx"], "time": 0.12, "auto": True})
        climax_types = prof.get("climax_vfx") or ()
        for idx, bt in enumerate(beats):
            if len(vfx_list) >= int(prof["max_vfx"]) or not climax_types:
                break
            vt = climax_types[idx % len(climax_types)]
            vfx_list.append({"type": vt, "time": round(bt, 2), "auto": True})
        clip["vfx_cues"] = vfx_list

    # 4. Custom SFX cues from user's own Sounds folder (preserve manual Studio sfx_cues)
    auto_sfx = bool(clip.get("auto_sfx", o.get("auto_sfx", cr.get("auto_sfx", True))))
    if auto_sfx and int(prof["max_sfx"]) > 0 and "sfx_cues" not in clip:
        custom_sfx = pick_custom_sfx_tracks(max_count=int(prof["max_sfx"]))
        sfx_list: list[dict[str, Any]] = []
        for idx, bt in enumerate(beats[:int(prof["max_sfx"])]):
            if not custom_sfx:
                break
            trk = custom_sfx[idx % len(custom_sfx)]
            sfx_list.append({
                "track_id": trk["id"],
                "time": round(max(0.15, bt - 0.08), 2),
                "volume": 0.85,
                "duration": min(2.2, float(trk.get("duration") or 1.8)),
                "auto": True,
            })
        if sfx_list:
            clip["sfx_cues"] = sfx_list

    return {
        "applied": True,
        "profile": profile_id,
        "jump_cuts": len(segs) if isinstance(segs, list) else 0,
        "vfx_count": len(clip.get("vfx_cues") or []),
        "sfx_count": len(clip.get("sfx_cues") or []),
    }
