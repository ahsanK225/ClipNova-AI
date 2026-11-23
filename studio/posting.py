"""Post queue: decides when each finished clip goes to which account, posts it, and tracks views."""
import secrets
import threading
import time
from pathlib import Path

import json

from . import accounts, alerts, calendar, config, creators, ctx, jobs, live, media

_lock = threading.RLock()
_FILE = config.DATA_DIR / "posts.json"
try:
    _posts: list = json.loads(_FILE.read_text(encoding="utf-8")) if _FILE.exists() else []
except ValueError:
    _posts = []


def _mine() -> list:
    u = ctx.uid()
    return [p for p in _posts if p.get("user") == u]
OPEN = ("scheduled", "posting")


def _save():
    with _lock:
        tmp = _FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(_posts, indent=1), encoding="utf-8")
        tmp.replace(_FILE)


def forget(uid: str):
    """Drop everything queued or recorded for a deleted account, so nothing is posted or retried for it any more."""
    with _lock:
        for p in _posts:
            if p.get("user") == uid:
                p["status"] = "deleted"          # the posting loop may be holding this one already: it then skips it
        _posts[:] = [p for p in _posts if p.get("user") != uid]
        _save()


def _day(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def _mirror(p):
    """Copy the post's state onto its clip so the clip card can show it."""
    jid = p.get("job")
    if not jid:
        return
    job = jobs.get(jid)
    clip = next((c for c in job["clips"] if c["id"] == p.get("clip")), None) if job else None
    if clip is not None:
        clip.setdefault("posts", {})[p["id"]] = {
            k: p.get(k) for k in ("account_name", "platform", "status", "url", "due_at",
                                  "scheduled_at", "error", "kind", "title", "formatted_text",
                                  "calendar_slot")
        }
        jobs.save(job)


def _next_slot(account_id, gap_min=None, cap=None):
    """USA-Focused Automatic Publishing Calendar slot engine.
    Finds the earliest valid slot (18:00 PKT / 00:00 PKT / 06:00 PKT)
    satisfying max 3 videos/day limit and 5-6 hour spacing."""
    try:
        slot = calendar.find_next_available_slot(account_id, _mine())
        return slot["video_ts"]
    except Exception:
        gap_sec = (gap_min or 60) * 60
        now = time.time()
        mine = [p for p in _mine() if p["account"] == account_id and p["status"] in OPEN + ("posted",)]
        future_posts = [p.get("scheduled_at") or p.get("due_at") for p in mine if (p.get("scheduled_at") or p.get("due_at") or 0) > now]
        if future_posts:
            t = max(future_posts) + gap_sec
        else:
            latest_past = max((p.get("posted_at") or p.get("due_at") or 0 for p in mine), default=0)
            t = max(now + gap_sec, latest_past + gap_sec)
        return t


def next_calendar_slot(account_id: str = None) -> dict:
    """Returns the full metadata dictionary for the next available publishing slot."""
    return calendar.find_next_available_slot(account_id, _mine())


def _post_community(p):
    """Executes or finalizes a YouTube Community Post 30 minutes after its video."""
    job = jobs.get(p["job"])
    clip = next((c for c in job["clips"] if c["id"] == p["clip"]), None) if job else None
    acc = accounts.get(p["account"])
    try:
        if not clip:
            raise RuntimeError("The clip no longer exists.")
        if not acc:
            raise RuntimeError("That account was disconnected.")

        video_url = p.get("video_url", "")
        if not video_url:
            vpost = next((op for op in _mine() if op.get("job") == p["job"] and op.get("clip") == p["clip"] and op.get("kind") != "community"), None)
            if vpost:
                video_url = vpost.get("url") or ""
                if not video_url and vpost.get("remote_id"):
                    video_url = f"https://www.youtube.com/shorts/{vpost['remote_id']}"

        title = clip.get("seo_title") or clip.get("title") or clip.get("hook") or "Clip"
        desc = clip.get("description") or ""
        pinned_comment = clip.get("pinned_comment") or ""
        tags = list(clip.get("seo_tags") or []) + list(clip.get("hashtags") or [])

        formatted_text = calendar.build_community_post_text(
            title=title,
            description=desc,
            video_url=video_url,
            pinned_comment=pinned_comment,
            hashtags=tags
        )
        p["formatted_text"] = formatted_text
        clip["community_text"] = formatted_text
        clip["community_posted"] = True

        res = accounts.youtube_post_community(acc, formatted_text, video_id=p.get("video_post_id"))
        p["remote_id"] = res.get("remote_id", "")
        p["url"] = res.get("url", "")
        p.update(status="posted", posted_at=time.time(), error=None)
        creators.log(p["creator"], f"📢 YouTube Community Post ready (+30m) for {acc['name']}: {title}")
        jobs.save(job)
    except Exception as e:
        p["tries"] += 1
        p["error"] = str(e)[-300:]
        if p["tries"] < 3 and clip and acc:
            p.update(status="scheduled", due_at=time.time() + 300)
        else:
            p["status"] = "failed"
            creators.log(p["creator"], f"Community post notice on {p['account_name']}: {p['error']}")
    _save()
    _mirror(p)


def _upload_worker(p):
    with _lock:
        if p["status"] != "scheduled":
            return
        p["status"] = "posting"
    _save()
    _mirror(p)
    if p.get("kind") == "community":
        _post_community(p)
    else:
        _post(p)


def enqueue(job, clip, account_ids, now=False, force=False, target_ts=None) -> list:
    c = creators.get(job["creator"]) or creators.DEFAULTS
    made = []
    with _lock:
        existing_mine = list(_mine())
        for aid in account_ids:
            acc = accounts.get(aid)
            if not acc:
                continue
            open_posts = [p for p in existing_mine if p["job"] == job["id"] and p["clip"] == clip["id"] and p["account"] == aid and p["status"] in OPEN]
            if open_posts:
                if now or force:
                    # User clicked "Post now": advance the existing open post to post immediately!
                    for ep in open_posts:
                        ep["due_at"] = time.time()
                        ep["now"] = True
                        ep["status"] = "scheduled"
                        ep["tries"] = 0
                        ep["error"] = None
                        ep["title"] = clip.get("title") or clip.get("hook") or ep["title"]
                        made.append(ep)
                    continue
                else:
                    continue  # already in the queue waiting to be posted

            already_posted = any(p["job"] == job["id"] and p["clip"] == clip["id"] and p["account"] == aid and p["status"] == "posted" for p in existing_mine)
            if already_posted and not (now or force):
                continue  # automatic autopost won't duplicate, but manual "Post now" / force will post directly

            # Compute slot using USA-Focused Automatic Publishing Calendar or target_ts
            cid_owner = job.get("creator")
            if target_ts:
                due = float(target_ts)
                slot_info = calendar.format_slot_info(due, creator_id=cid_owner)
            else:
                all_current = existing_mine + made
                slot_info = calendar.find_next_available_slot(aid, all_current, creator_id=cid_owner)
                due = time.time() if now else slot_info["video_ts"]

            p = {"id": secrets.token_hex(8), "user": ctx.uid(), "job": job["id"], "clip": clip["id"], "creator": job["creator"],
                 "account": aid, "account_name": acc["name"], "platform": acc["platform"], "status": "scheduled",
                 "due_at": due, "scheduled_at": due, "calendar_slot": slot_info, "kind": "video",
                 "now": now, "created": time.time(), "title": clip.get("title") or clip.get("hook") or "Clip",
                 "score": clip.get("score", 0), "tries": 0, "url": "", "remote_id": "", "error": None, "views": None}
            _posts.append(p)
            made.append(p)

            # Rule 6: AUTOMATIC COMMUNITY POST FOR YOUTUBE
            # Automatically schedule paired Community Post for exactly 30 minutes after video goes live
            if acc["platform"] == "youtube":
                comm_due = (time.time() + 30) if now else (due + calendar.COMMUNITY_OFFSET_SECONDS)
                comm_text = calendar.build_community_post_text(
                    title=clip.get("seo_title") or clip.get("title") or clip.get("hook") or "",
                    description=clip.get("description") or "",
                    video_url="",
                    pinned_comment=str(clip.get("pinned_comment") or ""),
                    hashtags=list(clip.get("seo_tags") or []) + list(clip.get("hashtags") or [])
                )
                comm_p = {
                    "id": secrets.token_hex(8), "user": ctx.uid(), "job": job["id"], "clip": clip["id"], "creator": job["creator"],
                    "account": aid, "account_name": acc["name"], "platform": acc["platform"], "status": "scheduled",
                    "due_at": comm_due, "scheduled_at": comm_due, "calendar_slot": slot_info,
                    "kind": "community", "is_community": True, "video_post_id": p["id"],
                    "now": now, "created": time.time(),
                    "title": f"📢 Community: {clip.get('title') or clip.get('hook') or 'Short'}",
                    "formatted_text": comm_text,
                    "score": clip.get("score", 0), "tries": 0, "url": "", "remote_id": "", "error": None, "views": None
                }
                _posts.append(comm_p)
                made.append(comm_p)
                clip["community_text"] = comm_text
                clip["community_scheduled_at"] = comm_due
        _save()
    for p in made:
        _mirror(p)
        # Directly upload video to YouTube cloud with native schedule (no local waiting required):
        if p.get("platform") == "youtube" and p.get("kind") != "community":
            threading.Thread(target=ctx.bind(lambda post=p: _upload_worker(post)), daemon=True).start()
    return made


def on_clip_ready(job, clip):
    """Called once when a clip first finishes rendering."""
    c = creators.get(job["creator"])
    if not c or not c["autopost"] or not c["accounts"]:
        return
    if clip.get("score", 0) < c["post_min_score"]:
        return  # includes hand-made clips (score 0): those wait for you to press Post
    made = enqueue(job, clip, c["accounts"])
    if made:
        creators.log(c["id"], f"Queued for {len(made)} account(s): {clip.get('title') or clip.get('hook')}")


def _caption(clip, creator):
    # A description the person wrote themselves is posted as it is, without the AI's hashtags added to it, and
    # one that already ends with its hashtags does not get them twice.
    tags = "" if clip.get("fixed_description") or clip.get("hashtags_in_description") else " ".join("#" + h for h in clip.get("hashtags", []))
    return "\n\n".join(x for x in (clip.get("description", ""), tags, creator.get("post_footer", "")) if x)


def _post(p):
    job = jobs.get(p["job"])
    clip = next((c for c in job["clips"] if c["id"] == p["clip"]), None) if job else None
    acc = accounts.get(p["account"])
    try:
        if not clip or clip.get("status") != "done":
            raise RuntimeError("The clip no longer exists or is not finished.")
        if not acc:
            raise RuntimeError("That account was disconnected.")
        path = Path(job["dir"]) / "clips" / clip["file"]
        creator = creators.get(job["creator"]) or dict(creators.DEFAULTS, name="clips")
        title = clip.get("seo_title") or clip.get("title") or clip.get("hook") or "Clip"
        cap = _caption(clip, creator)
        upload_path = path
        temp_yt2k = None
        if acc["platform"] == "youtube":
            try:
                probe = media.probe(path)
                # If vertical video is below 2K (e.g. 1080x1920), generate pristine 1440x2560 master.
                # YouTube strictly assigns VP9 / AV1 codec tier and high bitrate (15-25M) to 1440p+ uploads,
                # preventing YouTube mobile/desktop player from downscaling the Short to blurry 240p/360p!
                if probe.get("height", 0) < 2160 and probe.get("width", 0) < 1440:
                    temp_yt2k = path.with_name(f"{path.stem}_yt2k.mp4")
                    media.run(["ffmpeg", "-y", "-v", "error", "-i", str(path),
                               "-vf", "scale=1440:2560:flags=lanczos+accurate_rnd,cas=0.20",
                               "-c:v", "libx264", "-crf", "14", "-preset", "veryfast",
                               "-b:v", "25M", "-maxrate", "35M", "-bufsize", "50M",
                               "-tune", "film", "-c:a", "copy", str(temp_yt2k)])
                    if temp_yt2k.is_file() and temp_yt2k.stat().st_size > 1024:
                        upload_path = temp_yt2k
            except Exception as ue:
                creators.log(p["creator"], f"YouTube 2K VP9 pipeline notice: {ue}")

            yt_tags = list(clip.get("seo_tags") or [])
            for h in clip.get("hashtags", []):
                if h not in yt_tags:
                    yt_tags.append(h)
            pcomment = str(clip.get("pinned_comment") or "").strip()
            desc = cap + "\n\n#Shorts"
            if pcomment:
                desc = f"💬 Top Comment: {pcomment}\n\n" + desc
            publish_at = p.get("due_at") if (p.get("due_at", 0) > time.time() + 60 and not p.get("now")) else None
            privacy = "private" if publish_at else creator.get("privacy", "public")
            try:
                rid, url = accounts.youtube_upload(acc, upload_path, title, desc, yt_tags, privacy, publish_at=publish_at)
            finally:
                if temp_yt2k and temp_yt2k.is_file():
                    temp_yt2k.unlink(missing_ok=True)
            # Automatically set high-CTR cover thumbnail with hook banner & facecam on YouTube
            cover_file = clip.get("cover") or f"{clip['id']}.jpg"
            cover_path = Path(job["dir"]) / "clips" / cover_file
            if not cover_path.is_file():
                cover_path = Path(job["dir"]) / cover_file
            if cover_path.is_file():
                try:
                    if accounts.youtube_set_thumbnail(acc, rid, cover_path):
                        creators.log(p["creator"], f"Uploaded viral cover thumbnail to YouTube: {cover_file}")
                except Exception as te:
                    creators.log(p["creator"], f"YouTube thumbnail notice: {te}")
            if pcomment:
                try:
                    accounts.youtube_post_comment(acc, rid, pcomment)
                    creators.log(p["creator"], f"Posted top comment to {acc['name']}: {pcomment[:50]}")
                except Exception as ce:
                    err_msg = str(ce)
                    if "insufficient" in err_msg.lower() or "403" in err_msg:
                        creators.log(p["creator"], f"YouTube comment note: Channel account needs to be Reconnected in Accounts tab for comment posting permissions: {err_msg[:100]}")
                    else:
                        creators.log(p["creator"], f"YouTube comment note: {ce}")
        elif acc["platform"] == "instagram":
            rid, url = accounts.instagram_upload(acc, path, f"{title}\n\n{cap}", job["id"])
        elif acc["platform"] == "tiktok":
            rid, url = accounts.tiktok_upload(acc, path, f"{title}\n\n{cap}", creator["privacy"])
        else:
            raise RuntimeError("That kind of account is no longer supported.")
        p.update(status="posted", posted_at=time.time(), remote_id=rid, url=url, error=None)
        if acc["platform"] == "youtube" and p.get("due_at", 0) > time.time() + 60 and not p.get("now"):
            p["scheduled_at"] = p["due_at"]
            p["is_scheduled"] = True
            lt_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(p["due_at"]))
            creators.log(p["creator"], f"Uploaded & Scheduled natively on YouTube for {lt_str}: {title}")
        else:
            creators.log(p["creator"], f"Posted to {acc['name']}: {title}")

        # Single-channel exclusivity: once uploaded to one channel, cancel any pending video posts for this clip on other channels
        with _lock:
            for op in list(_posts):
                if op.get("job") == p["job"] and op.get("clip") == p["clip"] and op.get("id") != p["id"] and op.get("status") in OPEN:
                    if op.get("kind") != "community":
                        op["status"] = "cancelled"
                        _mirror(op)

        # Update paired community post with the real video URL and updated text
        with _lock:
            for op in list(_posts):
                if op.get("job") == p["job"] and op.get("clip") == p["clip"] and op.get("kind") == "community":
                    op["video_url"] = url
                    op["formatted_text"] = calendar.build_community_post_text(
                        title=title,
                        description=clip.get("description", ""),
                        video_url=url,
                        pinned_comment=str(clip.get("pinned_comment") or ""),
                        hashtags=yt_tags
                    )
                    _mirror(op)

        cleanup_mode = str(creator.get("post_cleanup", "ask")).lower()
        if cleanup_mode == "auto":
            try:
                from . import account as user_account
                user_account.delete_clip(p["job"], p["clip"])
                creators.log(p["creator"], f"Auto-deleted local clip files after upload to {acc['name']}: {title}")
            except Exception as de:
                creators.log(p["creator"], f"Auto-cleanup error: {de}")
        elif cleanup_mode == "ask":
            if clip:
                clip["cleanup_prompt"] = {
                    "account_name": acc["name"],
                    "title": title,
                    "url": url,
                    "posted_at": time.time()
                }
                jobs.save(job)
                ctx.bump()
    except Exception as e:  # noqa: BLE001
        p["tries"] += 1
        p["error"] = str(e)[-300:]
        if p["tries"] < 3 and clip and acc:
            p.update(status="scheduled", due_at=time.time() + 600)  # try again in 10 minutes
        else:
            p["status"] = "failed"
            creators.log(p["creator"], f"Post failed on {p['account_name']}: {p['error']}")
            alerts.notify(f"post failed on {p['account_name']} ({p['title']}): {p['error'][:200]}", kind="post")
    _save()
    _mirror(p)


def _run():
    while True:
        time.sleep(15)
        due = [p for p in list(_posts) if p["status"] == "scheduled" and p["due_at"] <= time.time() and p.get("user")]
        for p in due:
            try:
                with ctx.as_user(p["user"]):
                    if accounts.settings()["paused"]:
                        continue
                    with _lock:
                        if p["status"] != "scheduled":
                            continue
                        p["status"] = "posting"
                    if p.get("kind") == "community":
                        _post_community(p)
                    else:
                        _post(p)
            except Exception:  # noqa: BLE001
                pass


def _stats_for(recent):
    for aid in {p["account"] for p in recent if p["platform"] == "youtube"}:
        acc = accounts.get(aid)
        if acc:
            views = accounts.youtube_views(acc, [p["remote_id"] for p in recent if p["account"] == aid])
            for p in recent:
                if p["account"] == aid and p["remote_id"] in views:
                    p["views"] = views[p["remote_id"]]
    for p in recent:
        acc = accounts.get(p["account"]) if p["platform"] == "instagram" else None
        if acc:
            v = accounts.instagram_views(acc, p["remote_id"])
            if v is not None:
                p["views"] = v


def _stats():
    while True:
        for uid in {p.get("user") for p in _posts if p.get("user")}:
            try:
                with ctx.as_user(uid):
                    _stats_for([p for p in _mine() if p["status"] == "posted" and time.time() - p["posted_at"] < 14 * 86400])
            except Exception:  # noqa: BLE001
                pass
        _save()
        time.sleep(1800)


def delete_post(pid: str, delete_remote: bool = True) -> dict:
    """Permanently deletes a post from schedule. If it was already uploaded/scheduled to YouTube,
    also deletes the video from the user's YouTube channel via YouTube Data API v3."""
    deleted_youtube = False
    with _lock:
        p = next((p for p in _mine() if p["id"] == pid), None)
        if not p:
            raise KeyError(f"Post {pid} not found")

        # Delete from YouTube if uploaded
        if delete_remote and p.get("platform") == "youtube" and p.get("remote_id"):
            acc = accounts.get(p.get("account")) or next((a for a in accounts._all() if a.get("platform") == "youtube"), None)
            if acc:
                try:
                    accounts.youtube_delete(acc, p["remote_id"])
                    deleted_youtube = True
                    creators.log(p.get("creator", ""), f"Deleted video {p['remote_id']} from YouTube: {p.get('title')}")
                except Exception as e:
                    if "404" in str(e):
                        deleted_youtube = True
                    else:
                        creators.log(p.get("creator", ""), f"Notice deleting YouTube video {p.get('remote_id')}: {e}")

        # Mark post as cancelled / deleted
        p["status"] = "cancelled"
        p["deleted_at"] = time.time()
        p["error"] = "Deleted by user"

        # Also cancel any paired community post
        to_mirror = [p]
        for cp in _mine():
            if cp.get("video_post_id") == pid or (cp.get("job") == p.get("job") and cp.get("clip") == p.get("clip") and cp.get("kind") == "community"):
                cp["status"] = "cancelled"
                to_mirror.append(cp)

        _save()
    for item in to_mirror:
        _mirror(item)
    return {"ok": True, "deleted_youtube": deleted_youtube, "video_id": p.get("remote_id")}


def cancel(pid):
    with _lock:
        p = next((p for p in _mine() if p["id"] == pid), None)
        if not p:
            raise KeyError(pid)
        # If it's already posted/cloud-scheduled on YouTube, route to delete_post
        if p.get("remote_id") or p.get("status") == "posted":
            return delete_post(pid, delete_remote=True)
        if p["status"] == "cancelled":
            return {"ok": True}
        if p["status"] not in ("scheduled", "waiting", "queued"):
            raise ValueError(f"Post is {p['status']} and cannot be cancelled.")
        p["status"] = "cancelled"

        to_mirror = [p]
        for cp in _mine():
            if cp.get("video_post_id") == pid or (cp.get("job") == p.get("job") and cp.get("clip") == p.get("clip") and cp.get("kind") == "community"):
                cp["status"] = "cancelled"
                to_mirror.append(cp)
        _save()
    for item in to_mirror:
        _mirror(item)
    return {"ok": True}


def cancel_clip(job_id: str, clip_id: str) -> int:
    """Cancels all scheduled posts for a specific clip."""
    cancelled = 0
    to_mirror = []
    with _lock:
        for p in _mine():
            if p.get("job") == job_id and p.get("clip") == clip_id and p.get("status") in OPEN:
                p["status"] = "cancelled"
                cancelled += 1
                to_mirror.append(p)
        if cancelled:
            _save()
    for p in to_mirror:
        _mirror(p)
    return cancelled


def forget_clip(job_id: str, clip_id: str):
    """Mark all open posts for a deleted clip as cancelled so they never fire."""
    with _lock:
        changed = False
        for p in _posts:
            if p.get("job") == job_id and p.get("clip") == clip_id and p.get("status") in OPEN:
                p["status"] = "cancelled"
                changed = True
        if changed:
            _save()


def retry(pid):
    with _lock:
        p = next((p for p in _mine() if p["id"] == pid), None)
        if not p or p["status"] not in ("failed", "cancelled"):
            raise ValueError("Only failed or cancelled posts can be retried.")
        p.update(status="scheduled", due_at=time.time(), tries=0, error=None)
        _save()
    _mirror(p)


def overview() -> dict:
    today = _day(time.time())
    _posts = _mine()  # everything below is about the signed-in user only
    rows = []
    all_cs, all_js = creators.all_creators(), jobs.list_jobs()
    for c in all_cs:
        js = [j for j in all_js if j["creator"] == c["id"]]
        clips = [k for j in js for k in j["clips"] if k.get("status") == "done"]
        ps = [p for p in _posts if p["creator"] == c["id"]]
        views = sum(p["views"] or 0 for p in ps)
        rows.append({
            "id": c["id"], "name": c["name"],
            "state": "recording" if live.active_for(c["id"]) else "waiting" if c["auto_watch"] and c["channel"] else "idle",
            "autopost": c["autopost"] and bool(c["accounts"]),
            "clips_today": sum(1 for k in clips if _day(k.get("made_at", 0)) == today), "clips_total": len(clips),
            "posted_today": sum(1 for p in ps if p["status"] == "posted" and _day(p["posted_at"]) == today),
            "posted_total": sum(1 for p in ps if p["status"] == "posted"),
            "queued": sum(1 for p in ps if p["status"] in OPEN), "failed": sum(1 for p in ps if p["status"] == "failed"),
            "views": views, "earnings": round(views / 1000 * c["rate_per_1k"], 2)})
    names = {c["id"]: c["name"] for c in all_cs}
    queue = sorted((p for p in _posts if p["status"] in OPEN), key=lambda p: p["due_at"])
    done = sorted((p for p in _posts if p["status"] in ("posted", "failed")), key=lambda p: -(p.get("posted_at") or p["due_at"]))[:15]
    show = [{**{k: v for k, v in p.items() if k != "user"}, "creator_name": names.get(p["creator"], "")} for p in queue + done]
    # last 14 days, oldest first, for the home graph
    days = [_day(time.time() - 86400 * i) for i in range(13, -1, -1)]
    made, posted, views = {d: 0 for d in days}, {d: 0 for d in days}, {d: 0 for d in days}
    for j in all_js:
        for k in j["clips"]:
            d = _day(k.get("made_at") or j["created"])
            if k.get("status") == "done" and d in made:
                made[d] += 1
    for p in _posts:
        if p["status"] == "posted" and _day(p["posted_at"]) in posted:
            posted[_day(p["posted_at"])] += 1
            views[_day(p["posted_at"])] += p["views"] or 0
    daily = [{"day": d, "clips": made[d], "posted": posted[d], "views": views[d]} for d in days]
    return {"paused": accounts.settings()["paused"], "creators": rows, "posts": show, "daily": daily,
            "alerts": alerts.configured(), "recording": len(live.active_mine())}


def digest_text() -> str:
    o = overview()
    lines = ["PeakCut daily summary"]
    for r in o["creators"]:
        lines.append(f"- {r['name']}: {r['state']}, {r['clips_today']} clips today, {r['posted_today']} posted today, "
                     f"{r['queued']} waiting, {r['failed']} failed, {r['views']} views")
    if not o["creators"]:
        lines.append("No creators set up yet.")
    if o["paused"]:
        lines.append("Posting is paused.")
    return "\n".join(lines)


def start():
    with _lock:
        for p in _posts:
            if p["status"] == "posting":  # interrupted mid-upload last time
                p.update(status="failed", error="The studio closed during this upload. Check the account, then retry.")
        _save()
    jobs.on_clip_ready.append(on_clip_ready)
    threading.Thread(target=_run, daemon=True).start()
    threading.Thread(target=_stats, daemon=True).start()
    threading.Thread(target=alerts.digest_loop, args=(digest_text,), daemon=True).start()
    threading.Thread(target=alerts.keep_awake_loop,
                     args=(lambda: bool(live.active()) or any(p["status"] in OPEN for p in _posts),), daemon=True).start()
