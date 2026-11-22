"""USA-Focused Automatic Publishing Calendar & Community Post Scheduling Engine.

Rules:
1. STRICT DAILY VIDEO LIMIT: Maximum 3 videos per PKT calendar day.
2. AUTOMATIC QUEUE / NEXT-DAY CALENDAR: If a day is full, auto-roll to next day.
3. USA-FOCUSED PUBLISHING TIMES (PKT / UTC+5):
   - Slot 1: 6:00 PM PKT (8:00 AM US Eastern / 5:00 AM US Pacific)
   - Slot 2: 12:00 AM PKT (2:00 PM US Eastern / 11:00 AM US Pacific)
   - Slot 3: 6:00 AM PKT (8:00 PM US Eastern / 5:00 PM US Pacific)
4. PREFERRED SLOT ORDER: 6:00 PM -> 12:00 AM -> 6:00 AM.
5. MINIMUM GAP: 5-6 hours minimum between video publications.
6. AUTOMATIC COMMUNITY POST: Exactly 30 minutes after each video goes live (does NOT count toward 3-video limit).
7. TIMEZONE & DST AWARE: Uses zoneinfo for Asia/Karachi, America/New_York, and America/Los_Angeles.
"""
from datetime import datetime, date, time as dtime, timedelta
import time
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any

PKT_TZ = ZoneInfo("Asia/Karachi")        # UTC+5
US_EAST_TZ = ZoneInfo("America/New_York") # EDT (UTC-4) / EST (UTC-5)
US_WEST_TZ = ZoneInfo("America/Los_Angeles") # PDT (UTC-7) / PST (UTC-8)

MAX_VIDEOS_PER_DAY = 3
MIN_GAP_SECONDS = 5 * 3600               # 5 hours minimum (prefer 6 hours)
COMMUNITY_OFFSET_SECONDS = 30 * 60       # exactly 30 minutes after video goes live
DEFAULT_MIN_LEAD_SECONDS = 180           # 3 minutes lead time for scheduling


def get_tz_now() -> datetime:
    """Returns current datetime in Pakistan Standard Time (PKT)."""
    return datetime.now(PKT_TZ)


def format_slot_info(video_ts: float, slot_num: int = 1, cycle_date: Optional[date] = None) -> Dict[str, Any]:
    """Generates rich timezone-aware human readable metadata for a scheduled slot."""
    dt_pkt = datetime.fromtimestamp(video_ts, tz=PKT_TZ)
    dt_ny = datetime.fromtimestamp(video_ts, tz=US_EAST_TZ)
    dt_la = datetime.fromtimestamp(video_ts, tz=US_WEST_TZ)
    comm_ts = video_ts + COMMUNITY_OFFSET_SECONDS
    dt_comm_pkt = datetime.fromtimestamp(comm_ts, tz=PKT_TZ)

    c_date = cycle_date or dt_pkt.date()
    return {
        "video_ts": round(video_ts, 1),
        "video_pkt_str": dt_pkt.strftime("%Y-%m-%d %I:%M %p PKT"),
        "video_time_pkt": dt_pkt.strftime("%I:%M %p"),
        "video_us_east_str": dt_ny.strftime("%I:%M %p %Z"),
        "video_us_west_str": dt_la.strftime("%I:%M %p %Z"),
        "video_label": f"Slot {slot_num}: {dt_pkt.strftime('%I:%M %p PKT')} ({dt_ny.strftime('%I:%M %p %Z')})",
        "community_ts": round(comm_ts, 1),
        "community_pkt_str": dt_comm_pkt.strftime("%Y-%m-%d %I:%M %p PKT"),
        "community_time_pkt": dt_comm_pkt.strftime("%I:%M %p"),
        "community_label": f"Community Post: {dt_comm_pkt.strftime('%I:%M %p PKT')} (+30m)",
        "cycle_date": c_date.isoformat(),
        "slot_num": slot_num,
    }


def get_slots_for_cycle(base_date: date) -> List[float]:
    """Generates the 3 preferred publishing slot timestamps for a given calendar day cycle in PKT:
    Slot 1: base_date at 18:00 PKT (6:00 PM PKT)
    Slot 2: (base_date + 1 day) at 00:00 PKT (12:00 AM midnight PKT)
    Slot 3: (base_date + 1 day) at 06:00 PKT (6:00 AM morning PKT)
    """
    s1 = datetime.combine(base_date, dtime(18, 0), tzinfo=PKT_TZ).timestamp()
    s2 = datetime.combine(base_date + timedelta(days=1), dtime(0, 0), tzinfo=PKT_TZ).timestamp()
    s3 = datetime.combine(base_date + timedelta(days=1), dtime(6, 0), tzinfo=PKT_TZ).timestamp()
    return [s1, s2, s3]


def _is_video_post(p: dict) -> bool:
    """Returns True if the post is a video publication (not a community post)."""
    return p.get("kind") != "community" and not p.get("is_community", False)


def find_next_available_slot(account_id: Optional[str],
                             existing_posts: List[dict],
                             from_ts: Optional[float] = None,
                             min_lead_sec: int = DEFAULT_MIN_LEAD_SECONDS) -> Dict[str, Any]:
    """Finds the next valid publishing slot adhering to the 3 videos/day limit and 5-6 hr gap."""
    slots = assign_slots_to_videos(account_id, existing_posts, count=1, from_ts=from_ts, min_lead_sec=min_lead_sec)
    return slots[0]


def assign_slots_to_videos(account_id: Optional[str],
                           existing_posts: List[dict],
                           count: int = 1,
                           from_ts: Optional[float] = None,
                           min_lead_sec: int = DEFAULT_MIN_LEAD_SECONDS) -> List[Dict[str, Any]]:
    """Assigns calendar publishing slots to N videos automatically across future days.
    Guarantees:
    - Never more than 3 videos per day cycle.
    - Minimum 5-6 hours spacing between any two videos.
    - Automatic roll to next day when today's slots are filled or passed.
    - Pair each video with an automated Community Post scheduled exactly 30 minutes later.
    """
    if count <= 0:
        return []

    now_ts = from_ts if from_ts is not None else time.time()
    min_valid_ts = now_ts + max(60, min_lead_sec)

    # Filter active video publications (Community Posts do not count against the limit)
    active_videos = []
    for p in existing_posts or []:
        if account_id and p.get("account") != account_id:
            continue
        if p.get("status") in ("scheduled", "posted", "queued") and _is_video_post(p):
            t = p.get("scheduled_at") or p.get("due_at") or p.get("posted_at")
            if t:
                active_videos.append(float(t))

    active_videos.sort()

    assigned_slots: List[Dict[str, Any]] = []
    cur_date = datetime.fromtimestamp(now_ts, tz=PKT_TZ).date()

    # Search up to 365 days into the future until all slots are assigned
    for _ in range(365):
        cycle_slot_timestamps = get_slots_for_cycle(cur_date)

        # Count how many video posts already exist for this day cycle
        cycle_start_ts = cycle_slot_timestamps[0] - 3600 # 17:00 PKT
        cycle_end_ts = cycle_slot_timestamps[2] + 3600   # 07:00 PKT next morning
        existing_in_cycle = [t for t in active_videos if cycle_start_ts <= t <= cycle_end_ts]
        videos_in_cycle_count = len(existing_in_cycle)

        if videos_in_cycle_count < MAX_VIDEOS_PER_DAY:
            for slot_idx, slot_ts in enumerate(cycle_slot_timestamps, 1):
                if videos_in_cycle_count >= MAX_VIDEOS_PER_DAY:
                    break

                # 1. Must be in the future
                if slot_ts < min_valid_ts:
                    continue

                # 2. Must not be already booked (within 90 minutes of an existing post)
                if any(abs(slot_ts - t) < 5400 for t in active_videos):
                    continue

                # 3. Must respect minimum 5-hour spacing (prefer 6 hours) from any other video
                if any(abs(slot_ts - t) < MIN_GAP_SECONDS for t in active_videos):
                    continue

                # Slot is valid! Assign it.
                slot_info = format_slot_info(slot_ts, slot_num=slot_idx, cycle_date=cur_date)
                assigned_slots.append(slot_info)
                active_videos.append(slot_ts)
                active_videos.sort()
                videos_in_cycle_count += 1

                if len(assigned_slots) == count:
                    return assigned_slots

        # Move to next calendar day cycle automatically
        cur_date += timedelta(days=1)

    return assigned_slots


def build_community_post_text(title: str,
                              description: str,
                              video_url: str,
                              pinned_comment: Optional[str] = None,
                              hashtags: Optional[List[str]] = None) -> str:
    """Builds an optimized, high-CTR YouTube Community Post text payload matching the video's SEO."""
    parts = []
    if title:
        parts.append(f"🔥 {title.strip()}")

    clean_desc = (description or "").strip()
    # Strip redundant trailing hashtag blocks if already present
    clean_desc = clean_desc.replace("#Shorts", "").strip()
    if clean_desc:
        parts.append(clean_desc)

    if video_url:
        parts.append(f"▶️ Watch the full Short here:\n{video_url.strip()}")

    if pinned_comment:
        clean_pin = pinned_comment.strip()
        parts.append(f"💬 Community Discussion:\n{clean_pin}")

    if hashtags:
        clean_tags = ["#" + h.lstrip("#") for h in hashtags if h.strip()]
        if "#Shorts" not in clean_tags:
            clean_tags.insert(0, "#Shorts")
        parts.append(" ".join(clean_tags[:10]))

    return "\n\n".join(parts).strip()
