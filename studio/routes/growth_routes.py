"""Growth & Pro Creator Workflow API routes (Steps 3-7):
- Step 3: Hybrid Manual VOD Clipper (transcript jump + batch manual ranges)
- Step 4: Shorts Cover Frame Picker & Title CTR Scorer
- Step 5: Winner-Pattern AI Learning Loop
- Step 6: 1-Click Best-of-Stream Compilation Stitcher
- Step 7: Smart Disk & Buffer Auto-Cleaner
"""
import re
import threading
import time
from pathlib import Path
from typing import List

from fastapi import APIRouter, Body, HTTPException

from .. import auth, config, creators, ctx, jobs, posting, safe

router = APIRouter()


def _throttle(key: str, limit: int, window: int, msg: str = "Too many requests at once. Wait a moment."):
    try:
        auth.throttle(key, limit, window)
    except auth.AuthError:
        raise HTTPException(429, msg)


# ---------------------------------------------------------------------------
# STEP 3: HYBRID MANUAL VOD CLIPPER
# ---------------------------------------------------------------------------

@router.get("/api/jobs/{jid}/transcript")
def get_job_transcript(jid: str):
    """Return searchable grouped dialogue segments from job['words'] for Transcript-Click Jump."""
    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")
    words = job.get("words") or []
    segments = []
    cur_words: List[str] = []
    seg_start = 0.0
    seg_end = 0.0
    for w in words:
        wt = str(w.get("w") or w.get("word") or "").strip()
        ws = float(w.get("s") or w.get("start") or 0.0)
        we = float(w.get("e") or w.get("end") or ws + 0.3)
        if not wt:
            continue
        if not cur_words:
            seg_start = ws
        if cur_words and (ws - seg_end > 1.8 or len(cur_words) >= 14):
            segments.append({"start": round(seg_start, 2), "end": round(seg_end, 2), "text": " ".join(cur_words)})
            cur_words = []
            seg_start = ws
        cur_words.append(wt)
        seg_end = we
    if cur_words:
        segments.append({"start": round(seg_start, 2), "end": round(seg_end, 2), "text": " ".join(cur_words)})
    return {"ok": True, "segments": segments, "duration": float(job.get("duration") or 0.0)}


@router.post("/api/jobs/{jid}/manual-clips")
def add_manual_vod_clips(jid: str, body: dict = Body(...)):
    """Create and render one or more manual [start, end] clips from a job's original source video."""
    _throttle("manualclips:" + ctx.uid(), 20, 60)
    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")

    ranges = body.get("ranges") or []
    if not isinstance(ranges, list) or not ranges:
        raise HTTPException(400, "Provide at least one {start, end} range")

    src = Path(job.get("source_path") or job.get("src") or "")
    jdir = Path(job.get("dir", ""))
    fallback_src = next(iter(sorted((jdir / "clips").glob("*.src.mp4"))), None) if (jdir / "clips").is_dir() else None
    if not src.is_file() and not (fallback_src and fallback_src.is_file()):
        raise HTTPException(404, "Original source video not found on disk for this job")

    cr = creators.get(job.get("creator") or "") or {}
    base_opts = dict(job.get("options") or {})
    created_ids = []
    words = job.get("words") or []
    ts_tag = int(time.time()) % 100000

    for idx, r in enumerate(ranges[:12], 1):
        try:
            s = max(0.0, float(r.get("start", 0)))
            e = float(r.get("end", 0))
        except (ValueError, TypeError):
            continue
        dur = e - s
        if dur < 3.0 or dur > 300.0:
            raise HTTPException(400, f"Range #{idx} duration must be between 3s and 300s (got {dur:.1f}s)")

        cid = f"mclip{ts_tag}_{idx:02d}"
        title = str(r.get("title") or "").strip() or f"Manual Highlight ({int(s)}s-{int(e)}s) #Shorts"
        hook = str(r.get("hook") or "").strip() or "WAIT FOR THIS *MOMENT*!"
        new_clip = {
            "id": cid,
            "start": round(s, 2),
            "end": round(e, 2),
            "dur": round(dur, 2),
            "title": title,
            "hook": hook,
            "reason": f"Manual VOD cut ({int(s)}s -> {int(e)}s)",
            "source": "manual_vod",
            "score": 85,
            "status": "queued",
            "layout": r.get("layout") or base_opts.get("layout") or cr.get("layout") or "split_half",
            "style": r.get("style") or base_opts.get("style") or cr.get("style") or "bounce",
            "hook_style": base_opts.get("hook_style") or cr.get("hook_style") or "purple_whip",
            "captions": base_opts.get("captions", cr.get("captions", True)),
            "facecam": job.get("facecam") or cr.get("facecam"),
            "custom_layout": base_opts.get("custom_layout") or cr.get("custom_layout"),
            "swipe_stop_boost": bool(base_opts.get("swipe_stop_boost", cr.get("swipe_stop_boost", True))),
            "version": 1,
        }
        if not src.is_file() and fallback_src:
            new_clip["src"] = str(fallback_src)
        job.setdefault("clips", []).append(new_clip)
        created_ids.append(cid)

    if not created_ids:
        raise HTTPException(400, "No valid ranges supplied")

    jobs.save(job)
    ctx.bump()

    def _run_batch():
        for cid in created_ids:
            clp = next((c for c in job.get("clips", []) if c.get("id") == cid), None)
            if clp:
                try:
                    jobs.render_one(job, clp, words)
                except Exception:
                    pass

    threading.Thread(target=ctx.bind(_run_batch), daemon=True).start()
    return {"ok": True, "created": created_ids, "count": len(created_ids)}


# ---------------------------------------------------------------------------
# STEP 4: SHORTS COVER FRAME PICKER & TITLE CTR SCORER
# ---------------------------------------------------------------------------

@router.post("/api/jobs/{jid}/clips/{cid}/cover")
def pick_clip_cover_frame(jid: str, cid: str, body: dict = Body(...)):
    """Extract an exact timestamp frame from the clip video and set it as the cover JPG."""
    _throttle("clipcover:" + ctx.uid(), 30, 60)
    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")
    clip = next((c for c in job.get("clips", []) if c.get("id") == cid), None)
    if not clip:
        raise HTTPException(404, "Clip not found")

    t_sec = max(0.0, float(body.get("t", 1.0) or 1.0))
    jdir = Path(job.get("dir", ""))
    vid = jdir / "clips" / f"{cid}.mp4"
    if not vid.is_file():
        vid = jdir / "clips" / f"{cid}.src.mp4"
    if not vid.is_file():
        raise HTTPException(404, "Clip video file not found")

    frame_bytes = jobs._extract_frame_bytes(vid, t_sec) or jobs._extract_frame_bytes(vid, 0.5)
    if not frame_bytes:
        raise HTTPException(422, "Could not extract frame at this timestamp")

    cover_path = jdir / "clips" / f"{cid}.jpg"
    tmp_path = cover_path.with_suffix(".tmp.jpg")
    tmp_path.write_bytes(frame_bytes)
    tmp_path.replace(cover_path)
    clip["cover"] = f"{cid}.jpg"
    clip["version"] = int(clip.get("version") or 0) + 1
    jobs.save(job)
    ctx.bump()
    return {"ok": True, "cover": clip["cover"], "version": clip["version"], "t": t_sec}


def _score_title_ctr(title: str) -> dict:
    t = title.strip()
    score = 62
    reasons = []
    if 24 <= len(t) <= 62:
        score += 12
        reasons.append("Ideal Shorts length")
    elif len(t) > 75:
        score -= 8
        reasons.append("Too long (may truncate)")
    if "#Shorts" in t or "#shorts" in t:
        score += 6
        reasons.append("Has #Shorts tag")
    power = ("insane", "crazy", "never", "secret", "actually", "caught", "wasted", "first", "impossible", "broken", "best", "worst", "leaked")
    if any(w in t.lower() for w in power):
        score += 10
        reasons.append("High-curiosity power word")
    if any(ch in t for ch in ("!", "?", "💀", "😂", "🤯", "🔥", "😱")):
        score += 6
        reasons.append("Emotional hook punctuation")
    return {"title": t, "ctr_score": max(30, min(98, score)), "reason": " · ".join(reasons) or "Clean descriptive title"}


@router.post("/api/jobs/{jid}/clips/{cid}/title-score")
def score_clip_titles(jid: str, cid: str, body: dict = Body(default={})):
    """Generate and CTR-score 3 viral Shorts title candidates for a clip."""
    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")
    clip = next((c for c in job.get("clips", []) if c.get("id") == cid), None)
    if not clip:
        raise HTTPException(404, "Clip not found")

    cur_title = str(body.get("title") or clip.get("title") or clip.get("hook") or "Insane GTA 6 Moment").strip()
    clean_base = re.sub(r"#Shorts", "", cur_title, flags=re.I).strip(" !.-")
    cr_name = (creators.get(job.get("creator") or "") or {}).get("name") or ""

    raw_candidates = [cur_title]
    if clean_base:
        raw_candidates.append(f"Wait Until You See {clean_base}! 😱 #Shorts")
        if cr_name and cr_name.lower() not in clean_base.lower():
            raw_candidates.append(f"{cr_name} Couldn't Believe This: {clean_base} 🔥 #Shorts")
        else:
            raw_candidates.append(f"This Actually Happened: {clean_base} 💀 #Shorts")

    seen = set()
    scored = []
    for cand in raw_candidates:
        if cand not in seen:
            seen.add(cand)
            scored.append(_score_title_ctr(cand))
    scored.sort(key=lambda x: -x["ctr_score"])
    return {"ok": True, "candidates": scored}


# ---------------------------------------------------------------------------
# STEP 5: WINNER-PATTERN AI LEARNING LOOP
# ---------------------------------------------------------------------------

@router.get("/api/creators/{cid}/winner-insights")
def get_winner_insights(cid: str):
    """Analyze top-performing Shorts for a creator to surface winning length, hook style & cadence."""
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())

    c_posts = [p for p in posting._mine() if p.get("creator") == cid and p.get("kind") != "community"]
    c_jobs = {j["id"]: j for j in jobs.list_jobs() if j.get("creator") == cid}

    winners = []
    for p in c_posts:
        views = int(p.get("views") or 0)
        j = c_jobs.get(p.get("job"))
        clp = next((k for k in (j or {}).get("clips", []) if k.get("id") == p.get("clip")), None)
        dur = float((clp or {}).get("dur") or ((clp or {}).get("end", 0) - (clp or {}).get("start", 0)) or 0)
        winners.append({
            "title": p.get("title") or (clp or {}).get("title") or "Short",
            "views": views,
            "dur": round(dur, 1),
            "style": (clp or {}).get("style") or c.get("style") or "bounce",
            "hook_style": (clp or {}).get("hook_style") or c.get("hook_style") or "purple_whip",
            "layout": (clp or {}).get("layout") or c.get("layout") or "split_half",
        })

    winners.sort(key=lambda x: -x["views"])
    top = [w for w in winners if w["views"] > 0][:5] or winners[:5]
    avg_dur = round(sum(w["dur"] for w in top if w["dur"] > 0) / max(1, len([w for w in top if w["dur"] > 0])), 1) if top else 35.0
    best_hook = top[0]["hook_style"] if top else (c.get("hook_style") or "purple_whip")
    best_style = top[0]["style"] if top else (c.get("style") or "bounce")

    insights = {
        "analyzed_posts": len(winners),
        "top_views": top[0]["views"] if top else 0,
        "sweet_spot_dur_sec": avg_dur or 35.0,
        "winning_hook_style": best_hook,
        "winning_caption_style": best_style,
        "top_clips": top[:3],
        "recommendation": f"Keep clips near ~{int(avg_dur or 35)}s using '{best_hook}' hook & '{best_style}' captions.",
    }
    c["winner_insights"] = insights
    creators.save_all() if hasattr(creators, "save_all") else None
    return {"ok": True, "insights": insights}


# ---------------------------------------------------------------------------
# STEP 6: 1-CLICK "BEST OF STREAM" COMPILATION STITCHER
# ---------------------------------------------------------------------------

@router.post("/api/jobs/{jid}/stitch-best")
def stitch_best_of_stream(jid: str, body: dict = Body(default={})):
    """Stitch the top N highest-score clips from a job into a single Best-of-Stream compilation clip."""
    _throttle("stitch:" + ctx.uid(), 10, 60)
    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")

    max_n = max(2, min(8, int(body.get("count", 4) or 4)))
    done_clips = [
        c for c in job.get("clips", [])
        if c.get("status") == "done" and not str(c.get("id", "")).startswith("best_")
    ]
    if len(done_clips) < 2:
        raise HTTPException(400, "At least 2 finished clips are required to stitch a Best-of-Stream compilation")

    done_clips.sort(key=lambda c: -float(c.get("score") or 0))
    picked = done_clips[:max_n]
    # Keep chronological order inside compilation
    picked.sort(key=lambda c: float(c.get("start") or 0))

    jdir = Path(job.get("dir", ""))
    segments = []
    total_dur = 0.0
    for clp in picked:
        c_src = jdir / "clips" / f"{clp['id']}.src.mp4"
        s = float(clp.get("start") or 0.0)
        e = float(clp.get("end") or (s + 15.0))
        # Cap each piece to ~18s so the compilation stays punchy (<90s)
        piece_dur = min(18.0, max(4.0, e - s))
        if c_src.is_file():
            segments.append({"path": str(c_src), "start": 0.0, "end": piece_dur, "orig_start": s, "orig_end": s + piece_dur})
        else:
            segments.append({"start": s, "end": s + piece_dur, "orig_start": s, "orig_end": s + piece_dur})
        total_dur += piece_dur

    cid = f"best_{int(time.time()) % 100000}"
    cr = creators.get(job.get("creator") or "") or {}
    base_opts = dict(job.get("options") or {})
    comp_clip = {
        "id": cid,
        "start": float(picked[0].get("start") or 0.0),
        "end": float(picked[0].get("start") or 0.0) + total_dur,
        "dur": round(total_dur, 2),
        "segments": segments,
        "title": f"Top {len(picked)} Best Moments Compilation! 🔥 #Shorts",
        "hook": f"TOP {len(picked)} *BEST MOMENTS*! 🔥",
        "reason": f"Best-of-Stream compilation stitched from {len(picked)} top-scoring clips",
        "source": "compilation",
        "score": max(int(c.get("score") or 80) for c in picked),
        "status": "queued",
        "layout": base_opts.get("layout") or cr.get("layout") or "split_half",
        "style": base_opts.get("style") or cr.get("style") or "bounce",
        "hook_style": base_opts.get("hook_style") or cr.get("hook_style") or "purple_whip",
        "captions": False,
        "facecam": job.get("facecam") or cr.get("facecam"),
        "custom_layout": base_opts.get("custom_layout") or cr.get("custom_layout"),
        "swipe_stop_boost": True,
        "version": 1,
    }
    job.setdefault("clips", []).append(comp_clip)
    jobs.save(job)
    ctx.bump()

    def _run_stitch():
        try:
            jobs.render_one(job, comp_clip, job.get("words") or [])
        except Exception:
            pass

    threading.Thread(target=ctx.bind(_run_stitch), daemon=True).start()
    return {"ok": True, "clip_id": cid, "pieces": len(picked), "duration": round(total_dur, 1)}


# ---------------------------------------------------------------------------
# STEP 7: SMART DISK & BUFFER AUTO-CLEANER
# ---------------------------------------------------------------------------

def _scan_cleanable_buffers(uid: str, min_age_hours: float = 24.0) -> dict:
    u_dir = config.user_dir(uid)
    now = time.time()
    cutoff = now - (min_age_hours * 3600.0)
    files = []
    total_bytes = 0
    for ts_file in u_dir.glob("creators/*/live/*/buffer/*.ts"):
        try:
            st = ts_file.stat()
            if st.st_mtime <= cutoff:
                files.append(ts_file)
                total_bytes += st.st_size
        except OSError:
            continue
    return {"files": files, "count": len(files), "bytes": total_bytes, "mb": round(total_bytes / (1024 * 1024), 2)}


@router.get("/api/storage/cleanable")
def get_cleanable_storage(min_age_hours: float = 24.0):
    """Report how much disk space can be safely freed from old raw .ts stream buffers."""
    info = _scan_cleanable_buffers(ctx.uid(), max(0.0, float(min_age_hours)))
    return {"ok": True, "file_count": info["count"], "cleanable_mb": info["mb"], "min_age_hours": min_age_hours}


@router.post("/api/storage/cleanup")
def run_storage_cleanup(body: dict = Body(default={})):
    """Safely delete old raw .ts live buffer segments while keeping all rendered clips & covers intact."""
    _throttle("cleanup:" + ctx.uid(), 10, 60)
    min_age = max(0.0, float(body.get("min_age_hours", 24.0)))
    info = _scan_cleanable_buffers(ctx.uid(), min_age)
    freed = 0
    deleted = 0
    for f in info["files"]:
        try:
            sz = f.stat().st_size
            f.unlink(missing_ok=True)
            freed += sz
            deleted += 1
        except OSError:
            continue
    return {"ok": True, "deleted_files": deleted, "freed_mb": round(freed / (1024 * 1024), 2)}


# ---------------------------------------------------------------------------
# ONE-CLICK WEBSITE SELF-UPDATER
# ---------------------------------------------------------------------------

@router.post("/api/system/update")
def run_one_click_update():
    """Pull latest ClipNova AI code from GitHub (preserving .env & data/) and install requirements."""
    _throttle("sysupdate:" + ctx.uid(), 5, 60)
    import subprocess
    import sys

    REPO_URL = "https://github.com/ahsanK225/ClipNova-AI.git"
    root = config.ROOT

    # If user downloaded ZIP without .git, initialize git safely so 1-click web update works too
    if not (root / ".git").exists():
        subprocess.run(["git", "init"], cwd=str(root), capture_output=True, text=True, timeout=15)
        subprocess.run(["git", "remote", "add", "origin", REPO_URL], cwd=str(root), capture_output=True, text=True, timeout=15)

    # Safely stash any dirty tracked edits (never touching untracked .env or data/)
    stashed = False
    try:
        st = subprocess.run(["git", "status", "--porcelain"], cwd=str(root), capture_output=True, text=True, timeout=10)
        if any(not ln.startswith("??") for ln in (st.stdout or "").splitlines() if ln.strip()):
            subprocess.run(["git", "stash", "push", "-m", "auto-before-web-update"], cwd=str(root), capture_output=True, timeout=15)
            stashed = True
    except Exception:
        pass

    head_before = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True, timeout=10)
    fetch = subprocess.run(["git", "fetch", "origin", "main"], cwd=str(root), capture_output=True, text=True, timeout=45)
    if fetch.returncode != 0:
        err_txt = ((fetch.stdout or "") + "\n" + (fetch.stderr or "")).strip()
        raise HTTPException(422, f"Git fetch failed: {err_txt[:300]}")

    remote_head = subprocess.run(["git", "rev-parse", "origin/main"], cwd=str(root), capture_output=True, text=True, timeout=10)
    already_up_to_date = (
        head_before.returncode == 0
        and remote_head.returncode == 0
        and head_before.stdout.strip() == remote_head.stdout.strip()
    )

    out_txt = "Already up to date."
    if not already_up_to_date:
        # --mixed first so untracked files (e.g. from a ZIP download) don't block checkout
        subprocess.run(["git", "reset", "--mixed", "origin/main"], cwd=str(root), capture_output=True, text=True, timeout=30)
        reset = subprocess.run(["git", "checkout", "-B", "main", "origin/main"], cwd=str(root), capture_output=True, text=True, timeout=45)
        if reset.returncode == 0:
            reset = subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=str(root), capture_output=True, text=True, timeout=45)
        out_txt = ((reset.stdout or "") + "\n" + (reset.stderr or "")).strip()
        if reset.returncode != 0:
            raise HTTPException(422, f"Git update failed: {out_txt[:300]}")

    req_file = root / "requirements.txt"
    if not already_up_to_date and req_file.is_file():
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_file), "--quiet"], cwd=str(root), capture_output=True, timeout=120)

    return {
        "ok": True,
        "updated": not already_up_to_date,
        "stashed": stashed,
        "output": out_txt[:500],
        "message": "Already on the latest version!" if already_up_to_date else "Update downloaded! Close and restart ClipNova AI to apply new features.",
    }
