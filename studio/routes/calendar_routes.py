"""Calendar, analytics velocity, and community post API routes extracted from server.py."""
from __future__ import annotations

import time
from fastapi import APIRouter, Body, HTTPException

from .. import accounts, analytics, auth, calendar, creators, ctx, jobs, posting

router = APIRouter()


def _throttle(key: str, limit: int, window: int, msg: str = "Too many requests at once. Wait a moment."):
    try:
        auth.throttle(key, limit, window)
    except auth.AuthError:
        raise HTTPException(429, msg)


@router.get("/api/calendar/slots")
def get_calendar_slots(account_id: str = None, count: int = 6):
    """Return upcoming available publishing slots according to the USA-focused calendar."""
    _throttle("calslots:" + ctx.uid(), 60, 60)
    slots = calendar.assign_slots_to_videos(account_id, posting._mine(), count=min(max(count, 1), 30))
    return {
        "slots": slots,
        "max_per_day": calendar.MAX_VIDEOS_PER_DAY,
        "min_gap_hours": 6,
        "tz_pkt": "UTC+5 (Pakistan Standard Time)",
        "tz_us_east": "US Eastern Time",
        "tz_us_west": "US Pacific Time",
    }


@router.get("/api/creators/{cid}/calendar")
def get_creator_calendar(cid: str):
    """Return full publishing calendar schedule, slots, and queued videos for a creator."""
    _throttle("creatorcal:" + ctx.uid(), 60, 60)
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")

    now_ts = time.time()
    all_mine = posting._mine()
    c_posts = [p for p in all_mine if p.get("creator") == cid]

    scheduled_posts = []
    seen_post_ids = set()
    for p in c_posts:
        if p.get("status") in ("cancelled", "deleted"):
            continue
        cal_slot = p.get("calendar_slot")
        sched_t = float(p.get("scheduled_at") or p.get("due_at") or (cal_slot.get("video_ts") if isinstance(cal_slot, dict) else 0) or 0)
        is_future = sched_t > now_ts + 60
        if p.get("status") in posting.OPEN or is_future or p.get("is_scheduled"):
            scheduled_posts.append(p)
            seen_post_ids.add(p.get("id"))

    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())
    all_jobs = {j["id"]: j for j in jobs.list_jobs() if j.get("creator") == cid}
    for j in all_jobs.values():
        for clip in j.get("clips", []):
            for pid, pdata in (clip.get("posts") or {}).items():
                if pid not in seen_post_ids and isinstance(pdata, dict):
                    if pdata.get("status") in ("cancelled", "deleted"):
                        continue
                    cs = pdata.get("calendar_slot")
                    sched_t = float(pdata.get("scheduled_at") or pdata.get("due_at") or (cs.get("video_ts") if isinstance(cs, dict) else 0) or 0)
                    if pdata.get("status") in posting.OPEN or sched_t > now_ts + 60 or pdata.get("is_scheduled"):
                        post_copy = dict(pdata)
                        post_copy["id"] = pid
                        post_copy["job"] = j["id"]
                        post_copy["clip"] = clip.get("id")
                        post_copy["creator"] = cid
                        post_copy["cover"] = clip.get("cover") or f"{clip['id']}.jpg"
                        post_copy["file"] = clip.get("file") or ""
                        post_copy["hook"] = clip.get("hook") or ""
                        post_copy["title"] = clip.get("title") or clip.get("hook") or post_copy.get("title") or "Short"
                        post_copy["reason"] = clip.get("reason") or ""
                        post_copy["clip_status"] = clip.get("status") or "done"
                        scheduled_posts.append(post_copy)
                        seen_post_ids.add(pid)

    def _sched_key(p):
        cs = p.get("calendar_slot")
        return float(p.get("scheduled_at") or p.get("due_at") or (cs.get("video_ts") if isinstance(cs, dict) else 0) or 0)

    scheduled_posts.sort(key=_sched_key)

    recent_posted = [p for p in c_posts if p.get("status") in ("posted", "needs_manual_post") and p.get("id") not in seen_post_ids]
    recent_posted.sort(key=lambda p: -float(p.get("posted_at") or p.get("due_at") or 0))
    recent_posted = recent_posted[:10]

    for p in scheduled_posts + recent_posted:
        j = all_jobs.get(p.get("job"))
        if j:
            clip = next((k for k in j.get("clips", []) if k.get("id") == p.get("clip")), None)
            if clip:
                p["cover"] = clip.get("cover") or f"{clip['id']}.jpg"
                p["file"] = clip.get("file") or ""
                p["hook"] = clip.get("hook") or ""
                p["reason"] = clip.get("reason") or ""
                p["clip_status"] = clip.get("status") or "done"

    primary_acc = c["accounts"][0] if c.get("accounts") else None
    dedup_posts = list({(p.get("id") or id(p)): p for p in (all_mine + scheduled_posts)}.values())
    upcoming_slots = calendar.assign_slots_to_videos(primary_acc, dedup_posts, count=21, creator_id=cid)
    analytics_profile = analytics.get_analytics_profile(cid)

    return {
        "creator": {"id": c["id"], "name": c["name"], "accounts": c.get("accounts", [])},
        "scheduled": scheduled_posts,
        "recent_posted": recent_posted,
        "upcoming_slots": upcoming_slots,
        "max_per_day": calendar.MAX_VIDEOS_PER_DAY,
        "preferred_times_pkt": analytics_profile.get("primed_slots_pkt") or ["06:00 PM", "12:00 AM", "06:00 AM"],
        "min_gap_hours": analytics_profile.get("min_gap_hours", 5.0),
        "analytics": analytics_profile,
    }


@router.get("/api/creators/{cid}/analytics/velocity")
def get_creator_velocity(cid: str):
    """Return 24-hour hourly view velocity profile, detected audience peaks, and priming parameters."""
    _throttle("creatorvelocity:" + ctx.uid(), 60, 60)
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    return analytics.get_analytics_profile(cid)


@router.post("/api/creators/{cid}/analytics/sync")
def sync_creator_analytics(cid: str):
    """Poll YouTube Data API v3 for latest video view snapshots and compute delta velocity."""
    _throttle("creatoranalyticsync:" + ctx.uid(), 30, 60)
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    try:
        profile = analytics.sync_youtube_stats(cid)
        return {"ok": True, "profile": profile}
    except Exception as e:
        raise HTTPException(500, f"Sync error: {e}")


@router.post("/api/creators/{cid}/analytics/settings")
def update_creator_analytics_settings(cid: str, payload: dict = Body(...)):
    """Update analytics scheduling mode, priming offset, min gap, or manual peak hours."""
    _throttle("creatoranalyticsettings:" + ctx.uid(), 60, 60)
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    profile = analytics.save_analytics_settings(cid, payload)
    return {"ok": True, "profile": profile}


@router.get("/api/creators/{cid}/ready-clips")
def get_creator_ready_clips(cid: str):
    """Return all rendered/completed clips for a creator ready for calendar scheduling."""
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")

    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())
    all_jobs = [j for j in jobs.list_jobs() if j.get("creator") == cid]
    ready_clips = []
    now_ts = time.time()

    for j in all_jobs:
        for clip in j.get("clips", []):
            if clip.get("status") == "done":
                sched_info = None
                for _pid, pdata in (clip.get("posts") or {}).items():
                    if isinstance(pdata, dict):
                        cs = pdata.get("calendar_slot")
                        st = float(pdata.get("scheduled_at") or pdata.get("due_at") or (cs.get("video_ts") if isinstance(cs, dict) else 0) or 0)
                        if st > now_ts + 60 or pdata.get("status") in posting.OPEN:
                            sched_info = {
                                "scheduled_at": st,
                                "slot": pdata.get("calendar_slot"),
                                "account_name": pdata.get("account_name"),
                            }
                            break

                ready_clips.append({
                    "id": clip["id"],
                    "job_id": j["id"],
                    "title": clip.get("title") or clip.get("hook") or "Clip",
                    "hook": clip.get("hook") or "",
                    "duration": round(clip.get("end", 0) - clip.get("start", 0), 1),
                    "score": clip.get("score", 70),
                    "cover": clip.get("cover") or f"{clip['id']}.jpg",
                    "file": clip.get("file") or "",
                    "scheduled": sched_info,
                    "created": j.get("created", 0),
                })

    ready_clips.sort(key=lambda x: -x["created"])
    return {"clips": ready_clips}


@router.post("/api/calendar/schedule-clip")
def schedule_clip_to_slot(payload: dict = Body(...)):
    """Schedule a specific clip directly to a specific USA publishing calendar slot."""
    cid = payload.get("creator") or payload.get("creator_id")
    jid = payload.get("job_id")
    clip_id = payload.get("clip_id")
    slot_ts = float(payload.get("slot_ts") or 0)

    if not (cid and jid and clip_id and slot_ts):
        raise HTTPException(400, "creator, job_id, clip_id, and slot_ts are required")

    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())

    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")
    clip = next((k for k in job.get("clips", []) if k.get("id") == clip_id), None)
    if not clip:
        raise HTTPException(404, "Clip not found")

    c = creators.get(cid)
    acc_id = None
    if c and c.get("accounts"):
        acc_id = c["accounts"][0]
    else:
        user_accs = accounts.list_accounts()
        yt_accs = [a for a in user_accs if a.get("platform") == "youtube"]
        acc_id = yt_accs[0]["id"] if yt_accs else (user_accs[0]["id"] if user_accs else None)

    if not acc_id:
        raise HTTPException(400, "No connected social account found. Please connect your YouTube account in the Accounts tab first.")

    made = posting.enqueue(job, clip, [acc_id], target_ts=slot_ts, force=True)
    slot_info = calendar.format_slot_info(slot_ts, creator_id=cid)
    return {
        "ok": True,
        "slot": slot_info,
        "title": clip.get("title") or clip.get("hook") or "Short",
        "posts_created": len(made),
    }


@router.get("/api/jobs/{jid}/clips/{cid}/community")
def get_clip_community_post(jid: str, cid: str):
    """Return pre-formatted community post text, Short URL, and schedule information."""
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "No such video")
    clip = next((c for c in job["clips"] if c["id"] == cid), None)
    if not clip:
        raise HTTPException(404, "Clip not found")

    vpost = next((p for p in posting._mine() if p.get("job") == jid and p.get("clip") == cid and p.get("kind") != "community"), None)
    short_url = (vpost.get("url") or "") if vpost else ""
    if not short_url and vpost and vpost.get("remote_id"):
        short_url = f"https://www.youtube.com/shorts/{vpost['remote_id']}"
    if not short_url and clip.get("posts"):
        for pdata in clip["posts"].values():
            if pdata.get("url") and "youtu" in pdata.get("url", ""):
                short_url = pdata["url"]
                break

    title = clip.get("seo_title") or clip.get("title") or clip.get("hook") or "Clip"
    desc = clip.get("description") or ""
    comment = str(clip.get("pinned_comment") or "").strip()
    tags = list(clip.get("seo_tags") or []) + list(clip.get("hashtags") or [])
    comm_text = calendar.build_community_post_text(title, desc, short_url, comment, tags)

    return {
        "title": title,
        "text": comm_text,
        "short_url": short_url,
        "video_post": vpost,
        "community_scheduled_at": clip.get("community_scheduled_at"),
    }
