"""YouTube Channel Analytics & Hourly Views Velocity Tracker.

Implements:
1. Autonomous Hourly Views Delta Tracker (Option A):
   - Polls YouTube Data API v3 for creator's uploaded videos and view counts.
   - Computes delta views between snapshots (hourly velocity = views_t - views_{t-1}).
   - Attributes velocity to 24 hourly buckets in PKT (UTC+5).
2. Hybrid Algorithm Priming:
   - Detects the channel's top 3 peak view velocity hours using non-maximum suppression (respecting >= 4-5 hr gap).
   - Automatically offsets publishing time by 1.0 - 2.0 hours (default 1.5h) BEFORE the audience peak,
     giving YouTube's Shorts feed recommendation engine sufficient lead time to index and calibrate.
3. Cold-Start & Fallback Engine:
   - Provides smooth default curve matching gaming audience peaks if channel has no data yet.
   - Supports manual peak hours override from YouTube Studio "When your viewers are on YouTube".
"""
import copy
import json
import logging
import math
import os
import re
import threading
import time
from datetime import datetime, date, time as dtime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from zoneinfo import ZoneInfo

import httpx

from . import config, ctx

logger = logging.getLogger("studio.analytics")
PKT_TZ = ZoneInfo("Asia/Karachi")

_lock = threading.RLock()

# Default realistic hourly audience activity curve (indices 0..23 in PKT)
# Peaks naturally around 18:00 (6 PM), 23:00 (11 PM), and 05:00 (5 AM) for global/US gaming viewers
DEFAULT_HOURLY_WEIGHTS = [
    1400, 1100, 850, 600, 950, 2400,   # 00:00 - 05:00 PKT (Late night / US prime)
    1800, 1200, 900, 750, 650, 600,    # 06:00 - 11:00 PKT (Morning dip)
    850, 1100, 1450, 2100, 3100, 4200, # 12:00 - 17:00 PKT (Afternoon buildup)
    4800, 4100, 3500, 3900, 3600, 2200 # 18:00 - 23:00 PKT (Evening prime peaks)
]

DEFAULT_SETTINGS = {
    "mode": "analytics",             # "analytics" | "usa_default" | "custom"
    "priming_offset_hours": 1.5,     # 90 minutes before peak for algorithm indexation
    "min_gap_hours": 5.0,            # 5 hours minimum spacing between slots
    "custom_peaks_pkt": [18, 0, 6],  # Manual override peak hours in PKT
}


def _analytics_dir() -> Path:
    d = config.user_dir(ctx.uid()) / "analytics"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _analytics_file(cid: str) -> Path:
    clean_cid = re.sub(r"[^\w\-]", "", cid or "default")
    return _analytics_dir() / f"{clean_cid}_velocity.json"


def _load_data(cid: str) -> dict:
    f = _analytics_file(cid)
    if not f.exists():
        # Seed with initial default profile
        return {
            "creator_id": cid,
            "channel_id": "",
            "account_id": "",
            "last_sync_ts": 0.0,
            "last_sync_status": "never",
            "settings": copy.deepcopy(DEFAULT_SETTINGS),
            "snapshots": [],
            "hourly_velocity": list(DEFAULT_HOURLY_WEIGHTS),
            "total_tracked_views_48h": sum(DEFAULT_HOURLY_WEIGHTS) * 2,
            "detected_peaks_pkt": [18, 23, 5],
            "primed_slots_pkt": ["16:30", "21:30", "03:30"]
        }
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if "settings" not in data:
            data["settings"] = copy.deepcopy(DEFAULT_SETTINGS)
        if "hourly_velocity" not in data or len(data.get("hourly_velocity", [])) != 24:
            data["hourly_velocity"] = list(DEFAULT_HOURLY_WEIGHTS)
        return data
    except Exception as e:
        logger.warning("Error loading analytics for %s: %s", cid, e)
        return {
            "creator_id": cid,
            "settings": copy.deepcopy(DEFAULT_SETTINGS),
            "snapshots": [],
            "hourly_velocity": list(DEFAULT_HOURLY_WEIGHTS),
            "detected_peaks_pkt": [18, 23, 5],
            "primed_slots_pkt": ["16:30", "21:30", "03:30"]
        }


def _save_data(cid: str, data: dict):
    with _lock:
        f = _analytics_file(cid)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(f)


def circular_hour_diff(h1: float, h2: float) -> float:
    """Returns minimum circular distance between two hours on a 24-hour clock."""
    diff = abs(h1 - h2) % 24
    return min(diff, 24 - diff)


def detect_peak_hours(hourly_velocity: List[float], count: int = 3, min_gap_hours: float = 4.5) -> List[int]:
    """Detects top `count` peak hours using non-maximum suppression ensuring min_gap_hours."""
    if not hourly_velocity or len(hourly_velocity) != 24:
        return [18, 0, 6]

    # Rank candidate hours by velocity descending
    indexed = [(val, h) for h, val in enumerate(hourly_velocity)]
    indexed.sort(key=lambda x: -x[0])

    selected: List[int] = []
    for val, h in indexed:
        # Check if hour h is at least min_gap_hours away from already selected peaks
        if all(circular_hour_diff(h, s) >= min_gap_hours for s in selected):
            selected.append(h)
            if len(selected) == count:
                break

    # If strict min_gap prevented finding `count` peaks, relax gap slightly
    if len(selected) < count:
        relaxed_gap = max(3.5, min_gap_hours - 1.0)
        for val, h in indexed:
            if h not in selected and all(circular_hour_diff(h, s) >= relaxed_gap for s in selected):
                selected.append(h)
                if len(selected) == count:
                    break

    # Final fallback if still short
    if len(selected) < count:
        defaults = [18, 0, 6]
        for d in defaults:
            if d not in selected:
                selected.append(d)
            if len(selected) == count:
                break

    selected.sort()
    return selected


def calculate_primed_slot_times(peak_hours: List[int], priming_offset_hours: float = 1.5) -> List[str]:
    """Applies priming offset to peak hours.
    e.g. peak at 18:00 (6 PM) with 1.5h offset -> 16:30 PKT (4:30 PM)."""
    slots = []
    for h in peak_hours:
        total_minutes = int(round((h - priming_offset_hours) * 60)) % (24 * 60)
        hh = total_minutes // 60
        mm = total_minutes % 60
        period = "AM" if hh < 12 else "PM"
        display_h = hh % 12
        if display_h == 0:
            display_h = 12
        slots.append(f"{display_h:02d}:{mm:02d} {period}")
    return slots


def get_analytics_profile(cid: str) -> dict:
    """Returns rich public analytics metadata and curve for creator UI."""
    data = _load_data(cid)
    settings = data.get("settings", DEFAULT_SETTINGS)
    mode = settings.get("mode", "analytics")
    offset = float(settings.get("priming_offset_hours", 1.5))
    gap = float(settings.get("min_gap_hours", 5.0))
    velocity = data.get("hourly_velocity", DEFAULT_HOURLY_WEIGHTS)

    if mode == "custom":
        active_peaks = [int(h) % 24 for h in settings.get("custom_peaks_pkt", [18, 0, 6])][:3]
    elif mode == "usa_default":
        active_peaks = [18, 0, 6]
    else: # "analytics"
        active_peaks = detect_peak_hours(velocity, count=3, min_gap_hours=gap)

    primed_slots = calculate_primed_slot_times(active_peaks, offset)

    return {
        "creator_id": cid,
        "mode": mode,
        "settings": settings,
        "hourly_velocity": velocity,
        "detected_peaks_pkt": active_peaks,
        "primed_slots_pkt": primed_slots,
        "priming_offset_hours": offset,
        "min_gap_hours": gap,
        "total_tracked_views_48h": data.get("total_tracked_views_48h", sum(velocity) * 2),
        "last_sync_ts": data.get("last_sync_ts", 0),
        "last_sync_status": data.get("last_sync_status", "never"),
        "snapshots_count": len(data.get("snapshots", []))
    }


def save_analytics_settings(cid: str, patch: dict) -> dict:
    """Updates scheduling mode, custom peak hours, or priming parameters."""
    with _lock:
        data = _load_data(cid)
        s = data.setdefault("settings", copy.deepcopy(DEFAULT_SETTINGS))

        if "mode" in patch:
            mode = str(patch["mode"]).lower()
            if mode in ("analytics", "usa_default", "custom"):
                s["mode"] = mode

        if "priming_offset_hours" in patch:
            try:
                val = float(patch["priming_offset_hours"])
                s["priming_offset_hours"] = max(0.5, min(3.0, round(val, 1)))
            except (ValueError, TypeError):
                pass

        if "min_gap_hours" in patch:
            try:
                val = float(patch["min_gap_hours"])
                s["min_gap_hours"] = max(3.0, min(8.0, round(val, 1)))
            except (ValueError, TypeError):
                pass

        if "custom_peaks_pkt" in patch and isinstance(patch["custom_peaks_pkt"], list):
            peaks = []
            for p in patch["custom_peaks_pkt"]:
                try:
                    peaks.append(int(p) % 24)
                except (ValueError, TypeError):
                    pass
            if len(peaks) >= 1:
                s["custom_peaks_pkt"] = peaks[:3]

        _save_data(cid, data)
        return get_analytics_profile(cid)


def record_views_snapshot(cid: str, aid: str, video_stats: Dict[str, int]) -> dict:
    """Records an hourly snapshot of video views and updates the rolling 24-hour velocity curve."""
    with _lock:
        data = _load_data(cid)
        now_ts = time.time()
        dt_pkt = datetime.fromtimestamp(now_ts, tz=PKT_TZ)
        cur_hour = dt_pkt.hour

        snapshots = data.setdefault("snapshots", [])
        last_snap = snapshots[-1] if snapshots else None

        delta_views = 0
        if last_snap and "videos" in last_snap:
            prev_vids = last_snap["videos"]
            for vid, count in video_stats.items():
                if vid in prev_vids:
                    diff = max(0, count - prev_vids[vid])
                    delta_views += diff

        # If this is the very first snapshot or delta is 0, give reasonable observation
        total_views_sum = sum(video_stats.values()) if video_stats else 0
        new_snap = {
            "ts": now_ts,
            "hour_pkt": cur_hour,
            "total_views": total_views_sum,
            "delta": delta_views,
            "videos": {k: int(v) for k, v in list(video_stats.items())[:30]}
        }
        snapshots.append(new_snap)
        if len(snapshots) > 168: # Keep 7 days of hourly snapshots (7 * 24 = 168)
            snapshots.pop(0)

        # Update hourly velocity distribution if delta > 0
        velocity = data.setdefault("hourly_velocity", list(DEFAULT_HOURLY_WEIGHTS))
        if delta_views > 0:
            # Exponential moving average blending
            old_val = velocity[cur_hour]
            velocity[cur_hour] = int(round(old_val * 0.7 + delta_views * 0.3))

        # Re-evaluate peaks
        gap = float(data.get("settings", {}).get("min_gap_hours", 5.0))
        peaks = detect_peak_hours(velocity, count=3, min_gap_hours=gap)
        offset = float(data.get("settings", {}).get("priming_offset_hours", 1.5))

        data["last_sync_ts"] = now_ts
        data["last_sync_status"] = "success"
        data["total_tracked_views_48h"] = sum(v.get("delta", 0) for v in snapshots[-48:]) if len(snapshots) >= 2 else (total_views_sum or sum(velocity)*2)
        data["detected_peaks_pkt"] = peaks
        data["primed_slots_pkt"] = calculate_primed_slot_times(peaks, offset)

        _save_data(cid, data)
        return get_analytics_profile(cid)


def sync_youtube_stats(cid: str, aid: Optional[str] = None) -> dict:
    """Connects to YouTube Data API v3 and fetches latest video views for creator's connected account."""
    from . import accounts, creators

    c = creators.get(cid)
    if not c:
        raise ValueError("Creator not found")

    target_aid = aid or (c.get("accounts", [])[0] if c.get("accounts") else None)
    if not target_aid:
        # No account connected yet, return seeded profile
        return get_analytics_profile(cid)

    acc = accounts.get(target_aid)
    if not acc or acc.get("platform") != "youtube":
        return get_analytics_profile(cid)

    try:
        # Use accounts._yt_token to obtain valid OAuth token
        token = accounts._yt_token(acc)
    except Exception as e:
        logger.warning("Failed to get YouTube token for %s: %s", target_aid, e)
        # Update sync status to error
        with _lock:
            data = _load_data(cid)
            data["last_sync_ts"] = time.time()
            data["last_sync_status"] = f"error: {str(e)[:120]}"
            _save_data(cid, data)
        return get_analytics_profile(cid)

    video_stats: Dict[str, int] = {}
    try:
        headers = {"Authorization": f"Bearer {token}"}
        # 1. Get channel uploads playlist ID
        ch_resp = httpx.get("https://www.googleapis.com/youtube/v3/channels",
                            params={"part": "contentDetails", "mine": "true"},
                            headers=headers, timeout=15)
        if ch_resp.status_code == 200:
            items = ch_resp.json().get("items", [])
            if items:
                uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]

                # 2. Get last 15 uploaded videos
                pl_resp = httpx.get("https://www.googleapis.com/youtube/v3/playlistItems",
                                    params={"part": "contentDetails", "playlistId": uploads_id, "maxResults": 15},
                                    headers=headers, timeout=15)
                if pl_resp.status_code == 200:
                    vid_ids = [it["contentDetails"]["videoId"] for it in pl_resp.json().get("items", []) if "contentDetails" in it]
                    if vid_ids:
                        # 3. Get statistics for videos in 1 batch call (1 unit quota!)
                        v_resp = httpx.get("https://www.googleapis.com/youtube/v3/videos",
                                           params={"part": "statistics,snippet", "id": ",".join(vid_ids)},
                                           headers=headers, timeout=15)
                        if v_resp.status_code == 200:
                            for vit in v_resp.json().get("items", []):
                                vid = vit["id"]
                                views = int(vit.get("statistics", {}).get("viewCount", 0))
                                video_stats[vid] = views
    except Exception as e:
        logger.warning("Error fetching YouTube stats from API: %s", e)

    # Record snapshot with fetched or fallback stats
    return record_views_snapshot(cid, target_aid, video_stats)


def get_primed_slot_timestamps(base_date: date, cid: Optional[str] = None) -> List[float]:
    """Generates the 3 publishing slot timestamps for a given PKT day cycle,
    dynamically calculated from the channel's audience velocity peaks and priming offset."""
    profile = get_analytics_profile(cid) if cid else None
    if not profile:
        # Default USA slots (18:00 PKT, 00:00 PKT next day, 06:00 PKT next day)
        s1 = datetime.combine(base_date, dtime(18, 0), tzinfo=PKT_TZ).timestamp()
        s2 = datetime.combine(base_date + timedelta(days=1), dtime(0, 0), tzinfo=PKT_TZ).timestamp()
        s3 = datetime.combine(base_date + timedelta(days=1), dtime(6, 0), tzinfo=PKT_TZ).timestamp()
        return [s1, s2, s3]

    mode = profile.get("mode", "analytics")
    if mode == "usa_default":
        s1 = datetime.combine(base_date, dtime(18, 0), tzinfo=PKT_TZ).timestamp()
        s2 = datetime.combine(base_date + timedelta(days=1), dtime(0, 0), tzinfo=PKT_TZ).timestamp()
        s3 = datetime.combine(base_date + timedelta(days=1), dtime(6, 0), tzinfo=PKT_TZ).timestamp()
        return [s1, s2, s3]

    peaks = profile.get("detected_peaks_pkt", [18, 0, 6])
    offset_h = profile.get("priming_offset_hours", 1.5)

    timestamps = []
    for peak_h in peaks:
        # Prime slot: peak_h - offset_h
        total_minutes = int(round((peak_h - offset_h) * 60))
        # Determine day offset: if peak is early morning (e.g. 05:00 or 00:00), it's the next day of the cycle
        day_offset = 0
        if peak_h < 12: # Morning / Midnight belongs to next day in standard cycle
            day_offset = 1

        slot_m = total_minutes % (24 * 60)
        hh = slot_m // 60
        mm = slot_m % 60
        target_day = base_date + timedelta(days=day_offset)
        slot_dt = datetime.combine(target_day, dtime(hh, mm), tzinfo=PKT_TZ)
        timestamps.append(slot_dt.timestamp())

    timestamps.sort()
    return timestamps
