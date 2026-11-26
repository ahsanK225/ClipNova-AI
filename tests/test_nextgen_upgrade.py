"""NextGen Upgrade tests: Google GenAI SDK policy, free-tier enforcement, two-pass clipping, dedupe, final-cut Shorts package & UI consolidation."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-nextgen-")
os.environ["DATABASE_URL"] = ""
os.environ["PEAKCUT_ACCOUNTS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from studio import ai, auth, brain, ctx, db, gemini_client, jobs, media, server  # noqa: E402

db.init()
fails = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra and not ok else ""))
    if not ok:
        fails.append(name)


try:
    # 1. Google GenAI SDK defaults, free-tier enforcement, manual tier verification & 429 behavior
    check("gemini_client DEFAULT_FREE_PAIR prioritizes gemini-4-hydrogen & gemini-3.5-flash-lite",
          gemini_client.DEFAULT_FREE_PAIR == ["gemini-4-hydrogen", "gemini-3.5-flash-lite"])
    check("is_known_free_gemini & is_paid_only_model classify gemini-4-hydrogen (free) and gemini-4-carbon (paid)",
          gemini_client.is_known_free_gemini("gemini-4-hydrogen") is True
          and gemini_client.is_known_free_gemini("gemini-3.5-flash-lite") is True
          and gemini_client.is_paid_only_model("gemini-4-hydrogen") is False
          and gemini_client.is_paid_only_model("gemini-4-carbon") is True
          and gemini_client.is_paid_only_model("gemini-2.5-pro") is True)

    tier_unverified = gemini_client.tier_verification_info(None)
    check("tier_verification_info reports unverified by default (never auto-assumes free)",
          tier_unverified["status"] == "unverified_manual_check_required"
          and len(tier_unverified["steps"]) >= 3
          and "aistudio.google.com" in tier_unverified["check_url"])

    tier_confirmed = gemini_client.tier_verification_info(1760000000.0)
    check("tier_verification_info reflects user_confirmed_free after manual check",
          tier_confirmed["status"] == "user_confirmed_free" and tier_confirmed["verified"] is True)

    # Configure isolated keys and verify free_only enforcement + no silent 429 key-rotation bypass
    with patch.object(ai, "test_key", return_value=None):
        paid_rejected = False
        try:
            ai.save("gemini", ["gemini-4-hydrogen", "gemini-4-carbon"], "", "AIzaFakeKeyOne1111111111", free_only=True)
        except ValueError:
            paid_rejected = True
        ai.save("gemini", ["gemini-4-hydrogen", "gemini-3.5-flash-lite"], "", "AIzaFakeKeyOne1111111111", free_only=True)
        ai.add_key("AIzaFakeKeyTwo2222222222")
        ai.activate_key(0)
        ai.update_preferences(free_only=True, auto_route=True, analysis_mode="balanced")
    cur_cfg = ai.current()
    check("ai.save rejects paid model gemini-4-carbon in Free Mode Only and saves verified free pair",
          paid_rejected
          and cur_cfg["models"][:2] == ["gemini-4-hydrogen", "gemini-3.5-flash-lite"]
          and all(not gemini_client.is_paid_only_model(m) for m in cur_cfg["models"]),
          f"paid_rejected={paid_rejected} models={cur_cfg['models']} free_only={cur_cfg['free_only']}")

    routed_scan = ai.route_models("discovery")
    routed_review = ai.route_models("reasoning")
    check("ai.route_models assigns Flash-Lite to discovery and Hydrogen to reasoning",
          routed_scan[0] == "gemini-3.5-flash-lite"
          and routed_review[0] == "gemini-4-hydrogen",
          f"scan={routed_scan} review={routed_review}")

    with patch.object(ai, "test_key", return_value=None):
        ai.switch_model("gemini", "gemini-3.8-flash")
    routed_gen_38 = ai.route_models("general")
    check("switch_model('gemini', 'gemini-3.8-flash') syncs general route & last_active_model",
          routed_gen_38[0] == "gemini-3.8-flash" and ai.last_active_model() == "gemini-3.8-flash",
          f"general={routed_gen_38} active={ai.last_active_model()}")
    with patch.object(ai, "test_key", return_value=None):
        ai.save("gemini", ["gemini-4-hydrogen", "gemini-3.5-flash-lite"], "", "AIzaFakeKeyOne1111111111", free_only=True)

    # Verify cache avoids duplicate network calls + 429 does NOT bypass quota via key rotation
    gemini_client.clear_cache()
    sdk_calls = []
    schema_dummy = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

    def _fake_sdk_once(*a, **kw):
        sdk_calls.append(a)
        return {"ok": True}, 90, 30

    with patch.object(gemini_client, "generate_content_json", side_effect=_fake_sdk_once):
        r1 = ai.call("gemini-4-hydrogen", "test prompt stable", schema_dummy, allow_cache=True)
        r2 = ai.call("gemini-4-hydrogen", "test prompt stable", schema_dummy, allow_cache=True)
    check("ai.call disk cache prevents duplicate AI request on identical prompt",
          len(sdk_calls) == 1 and r1[0] == {"ok": True} and r2[0] == {"ok": True} and r2[1] == 0,
          f"calls={len(sdk_calls)} r1={r1} r2={r2}")

    def _always_429(*a, **kw):
        raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")

    start_key_idx = ai._key_index
    with patch.object(gemini_client, "generate_content_json", side_effect=_always_429):
        with patch("studio.ai.time.sleep", return_value=None):
            try:
                ai.call("gemini-4-hydrogen", "say hi uncached 429", schema_dummy, allow_cache=False)
                quota_raised = False
            except Exception:
                quota_raised = True
    check("429 quota exhaustion fails honestly without rotating active_key_idx to bypass limits",
          quota_raised and ai._key_index == start_key_idx,
          f"raised={quota_raised} idx={start_key_idx}->{ai._key_index}")

    # 2. Canonical YouTube URL normalization & Duplicate/Retry rules
    canon_ids = {
        media.canonical_source_id(url="https://www.youtube.com/watch?v=tx_0pcjW8SE&t=12s"),
        media.canonical_source_id(url="https://youtu.be/tx_0pcjW8SE?si=abc123"),
        media.canonical_source_id(url="https://www.youtube.com/shorts/tx_0pcjW8SE"),
        media.canonical_source_id(url="https://www.youtube.com/live/tx_0pcjW8SE?feature=share"),
    }
    check("canonical_source_id unifies watch, youtu.be, shorts & live into yt:tx_0pcjW8SE",
          canon_ids == {"yt:tx_0pcjW8SE"}, f"canon={canon_ids}")

    # 3. Two-Pass Clipping: Quiet visual candidates, "clip that" backtrack & Pass 2 verification
    with patch.object(ai, "see_media", return_value=([{"frame_index": 0, "timestamp": 65.0, "interesting": True, "score": 86, "category": "funny", "what_happened": "Silent shock stare", "reason": "Silent facecam reaction works cleanly."}], 120, 40, "gemini-4-hydrogen")):
        quiet_cands, q_mod, _ = brain._find_quiet_visual_candidates(
            keyframes=[(65.0, b"jpg1"), (150.0, b"jpg2")],
            words=[],
            duration=240.0,
            min_len=20,
            max_len=45,
            title="Quiet Stream",
            uploader="Streamer",
            game="GTA 6",
        )
    check("Quiet footage with 0 transcript words qualifies via sampled keyframes",
          len(quiet_cands) == 1 and quiet_cands[0]["payoff_at"] == 65.0 and q_mod == "gemini-4-hydrogen",
          f"quiet_cands={quiet_cands}")

    bt_windows = brain._find_trigger_backtrack_windows(
        words=[{"s": 90.0, "e": 90.5, "w": "bro"}, {"s": 90.6, "e": 91.0, "w": "clip"}, {"s": 91.1, "e": 91.5, "w": "that"}],
        duration=180.0,
        min_len=20,
        max_len=45,
    )
    check("'clip that' trigger backtracks early (~15-30s prior) to include setup",
          len(bt_windows) == 1 and bt_windows[0]["start"] <= 70.0 and bt_windows[0]["end"] >= 93.0,
          f"bt_windows={bt_windows}")

    def _fake_pass2(cand, mparts, w_a, w_b, w_fmt, title, uploader, game, min_len, max_len, weights=None):
        if cand["start"] < 50.0:
            return {"_rejected": True, "reason": "Routine lobby wait."}, "gemini-4-hydrogen", 150, "multimodal_video_audio"
        return {
            **cand,
            "start": cand["start"],
            "end": cand["start"] + 28.0,
            "payoff_at": cand["start"] + 22.0,
            "score": 88,
            "reason": "Silent shock stare as the explosion launches his car.",
            "analysis_mode": "multimodal_video_audio",
        }, "gemini-4-hydrogen", 220, "multimodal_video_audio"

    import numpy as np
    fake_db = np.zeros(180)
    words_pass = [
        {"s": 12.0, "e": 12.5, "w": "yo"}, {"s": 15.0, "e": 15.5, "w": "look"}, {"s": 18.0, "e": 18.4, "w": "chat"},
        {"s": 112.0, "e": 112.4, "w": "uh"}, {"s": 115.0, "e": 115.5, "w": "bro"}, {"s": 118.0, "e": 118.5, "w": "what"},
    ]
    with patch.object(brain, "ask_ai", return_value=([
        {"start": 10.0, "end": 40.0, "score": 78, "hook": "WAIT WHAT", "reason": "Intro bit"},
        {"start": 110.0, "end": 145.0, "score": 84, "hook": "SILENT STARE", "reason": "Facecam reaction"},
    ], "gemini-3.5-flash-lite", 100)):
        with patch.object(brain, "_review_candidate_pass2", side_effect=_fake_pass2):
            picks, diag = brain.find_clips(
                words=words_pass,
                db=fake_db,
                duration=180.0,
                max_clips=5,
                min_len=15,
                max_len=45,
                review_media=lambda a, b: [("video/mp4", b"fake-mp4-bytes")],
            )
    check("Pass 2 quality filter returns fewer strong clips & saves payoff_at + multimodal_video_audio label",
          len(picks) == 1 and abs(picks[0]["payoff_at"] - 132.0) < 5.0 and picks[0]["analysis_mode"] == "multimodal_video_audio",
          f"picks={picks} diag={diag}")

    with patch.object(brain, "ask_ai", return_value=([{"start": 10.0, "end": 35.0, "score": 82, "hook": "WHAT?!", "reason": "Funny callout"}], "gemini-4-hydrogen", 80)):
        t_picks, t_diag = brain.find_clips(
            words=[{"s": 11.0, "e": 11.4, "w": "oh"}, {"s": 14.0, "e": 14.4, "w": "no"}, {"s": 17.0, "e": 17.4, "w": "bro"}],
            db=fake_db,
            duration=90.0,
            max_clips=3,
            min_len=15,
            max_len=45,
            review_media=None,
        )
    check("Transcript-only fallback labels clips as analysis_mode='transcript_only'",
          len(t_picks) == 1 and t_picks[0]["analysis_mode"] == "transcript_only" and t_diag["analysis_mode"] == "transcript_only",
          f"t_picks={t_picks} t_diag={t_diag}")

    # 4. End-to-End Job API: Canonical duplicate tracking, retry error clip, trim seo_stale & final-cut package
    u, _ = auth._create("nextgen@example.com", "NG", password_hash="x")
    with ctx.as_user(u.id):
        job_a = jobs.create({"type": "url", "url": "https://youtu.be/tx_0pcjW8SE?si=test"}, {}, enqueue=False)
        job_a["status"] = "done"
        job_a["uploader"] = "IShowSpeed"
        job_a["game"] = "GTA 6"
        job_a["clips"] = [
            {"id": "c_ok", "start": 10.0, "end": 38.0, "payoff_at": 31.0, "status": "done", "hook": "HE FELL OFF?!", "title": "Original Done Clip #Shorts", "seo_title": "Original Done Clip #Shorts", "description": "Original desc", "hashtags": ["Shorts", "GTA6"], "seo_tags": ["gta 6", "ishowspeed"], "pinned_comment": "Did you see that?", "version": 1},
            {"id": "c_err", "start": 60.0, "end": 88.0, "status": "error", "error": "FFmpeg interrupted", "version": 1},
        ]
        jobs.save(job_a)

        check("jobs.create stores canonical_source_id='yt:tx_0pcjW8SE'",
              job_a.get("canonical_source_id") == "yt:tx_0pcjW8SE")

        # Trim clip -> seo_stale becomes True
        with patch.object(jobs._q, "put", lambda *a, **kw: None):
            jobs.request_render(job_a["id"], "c_ok", {"start": 12.0, "end": 41.0, "title": "Original Done Clip #Shorts"})
        trimmed = [x for x in jobs.get(job_a["id"])["clips"] if x["id"] == "c_ok"][0]
        check("Trimming clip boundary marks seo_stale=True",
              trimmed.get("seo_stale") is True and float(trimmed.get("start")) == 12.0,
              f"trimmed={trimmed}")

        # Save manual edits to pinned_comment -> tracked in edited_fields
        jobs.save_post_text(jobs.get(job_a["id"]), trimmed, {"pinned_comment": "My hand-written question?"})
        saved_c = [x for x in jobs.get(job_a["id"])["clips"] if x["id"] == "c_ok"][0]
        check("save_post_text records manual edited_fields",
              "pinned_comment" in (saved_c.get("edited_fields") or []),
              f"saved_c={saved_c}")

        # Generate final cut package while preserving manually edited field
        fake_pkg = {
            "hook": "HE STOLE THE HELICOPTER?!",
            "hooks": ["HE STOLE THE HELICOPTER?!", "WAIT FOR THE CRASH"],
            "title": "Speed Actually Took Off In GTA 6! #Shorts",
            "titles": ["Speed Actually Took Off In GTA 6! #Shorts", "He Escaped 5 Stars?! #Shorts"],
            "description": "Speed jumps straight onto the skids before it lifts off in GTA 6.",
            "hashtags": ["Shorts", "GTA6", "GTA6", "IShowSpeed"],
            "seo_tags": ["gta 6", "ishowspeed", "gta 6 shorts"],
            "pinned_comment": "AI comment should not overwrite manual edit",
            "community_post": "Full chopper escape Short is live: [SHORT_URL]",
        }
        with patch.object(brain, "generate_final_cut_package", return_value=fake_pkg):
            res_pkg = server.generate_clip_ai_seo(job_a["id"], "c_ok", {})
        reloaded_ok = [x for x in jobs.get(job_a["id"])["clips"] if x["id"] == "c_ok"][0]
        check("Final-cut /package clears seo_stale, dedupes hashtags, sets [SHORT_URL] & preserves edited pinned_comment",
              res_pkg.get("ok") is True
              and reloaded_ok.get("seo_stale") is False
              and len(reloaded_ok.get("hashtags", [])) == 3
              and "[SHORT_URL]" in reloaded_ok.get("community_text", "")
              and reloaded_ok.get("pinned_comment") == "My hand-written question?",
              f"res={res_pkg} clip={reloaded_ok}")

        # Retry failed clip via /resume
        with patch.object(jobs._q, "put", lambda *a, **kw: None):
            res_resume = server.resume_job(job_a["id"], {})
        reloaded_err = [x for x in jobs.get(job_a["id"])["clips"] if x["id"] == "c_err"][0]
        check("POST /api/jobs/{jid}/resume re-queues failed clips cleanly",
              res_resume.get("ok") is True and reloaded_err["status"] == "queued",
              f"res={res_resume} err_clip={reloaded_err}")

    # 5. Frontend UI consolidation & Light/Dark theme + Node JS syntax check
    html_path = Path("web/index.html")
    html = html_path.read_text(encoding="utf-8")
    check("web/index.html has ONE YouTube Shorts panel and removed duplicate seo_title pills",
          'id="dlg_youtube_shorts_panel"' in html
          and html.count('data-f="title"') == 1
          and 'data-f="seo_title"' not in html
          and 'id="dlg_seo_title_pills"' not in html
          and 'data-field="hashtags"' in html
          and 'data-field="description"' in html
          and 'data-act="copy"' in html
          and 'data-act="ai_save_prefs"' in html
          and 'data-act="ai_confirm_free_tier"' in html
          and '<meta name="color-scheme" content="light dark">' in html
          and 'id="themeToggleBtn"' in html)

    scripts = re.findall(r"<script[^>]*>([\s\S]*?)</script>", html)
    big_js = max(scripts, key=len)
    js_tmp = Path(os.environ["PEAKCUT_DATA"]) / "check_ui.js"
    js_tmp.write_text(big_js, encoding="utf-8")
    node_res = subprocess.run(["node", "--check", str(js_tmp)], capture_output=True, text=True)
    check("Frontend main <script> passes node --check with zero syntax errors",
          node_res.returncode == 0, node_res.stderr[:200])

    # 6. Render custom layout frame mode (No Facecam & custom mobile height 30-100%)
    from studio import render as render_mod
    fg_blur = render_mod._filter("custom", 1080, custom_layout={"mode": "frame", "mobile_height": 68, "bg_style": "blur", "gameplay": [360, 0, 1200, 1080], "no_facecam": True})
    fg_full = render_mod._filter("custom", 1080, custom_layout={"mode": "frame", "mobile_height": 100, "gameplay": [656, 0, 608, 1080], "no_facecam": True})
    fg_nocam_split = render_mod._filter("custom", 1080, custom_layout={"mode": "split", "no_facecam": True, "gameplay": [480, 0, 1440, 1080]})
    check("Custom Studio 'frame' mode supports custom mobile height + blur & 100% full + no_facecam fallback",
          "boxblur=" in fg_blur and "overlay=0:" in fg_blur
          and "crop=1080:1920" in fg_full and "overlay=" not in fg_full
          and "vstack" not in fg_nocam_split and "crop=1080:1920" in fg_nocam_split)

    # 7. Streamer-Only Captions word filtering & safe fallback
    from studio import facecam as facecam_mod
    sample_words = [
        {"w": "Bro", "s": 1.0, "e": 1.3},
        {"w": "look!", "s": 1.4, "e": 1.7},
        {"w": "NPC", "s": 4.2, "e": 4.6},
        {"w": "line", "s": 4.7, "e": 5.1},
        {"w": "crazy!", "s": 8.2, "e": 8.6},
    ]
    kept = render_mod.filter_streamer_words(sample_words, [(0.8, 2.0), (8.0, 9.0)])
    kept_none = render_mod.filter_streamer_words(sample_words, None)
    check("Streamer-Only Captions keeps streamer words, drops NPC dialogue & falls back safely",
          [w["w"] for w in kept] == ["Bro", "look!", "crazy!"]
          and len(kept_none) == len(sample_words)
          and facecam_mod.detect_speech_windows("missing.mp4", 0.0, 5.0, None, 1920, 1080) is None
          and 'data-k="streamer_only_captions"' in html
          and 'data-f="streamer_only_captions"' in html)

    # 8. CapCut-style Multi-segment Cut, Trim & Merge timeline support
    check("CapCut-style Multi-Segment Cut & Merge Studio UI + job segments validation present",
          'studioSplitSegmentAtPlayhead' in html
          and 'studioStartTrimDrag' in html
          and 'studioStartSegDrag' in html
          and 'studioStartRulerScrub' in html
          and 'studioTrimSelectedToPlayhead' in html
          and 'studioAddClipToTimeline' in html
          and 'studioSetZoom' in html
          and 'id="studio_timeline_scroll"' in html
          and 'id="studio_media_bin"' in html)

    # 9. CapCut-style VFX & Meme SFX Soundboard + FFmpeg mixing
    vfx_fc = render_mod._vfx_ffmpeg_chain([{"type": "flash", "time": 2.0}, {"type": "wasted_bw", "time": 5.0}])
    check("CapCut-style VFX & Meme SFX Soundboard + FFmpeg cues work end-to-end",
          "between(t,2.00,2.22)" in vfx_fc
          and "hue=s=0:enable='between(t,5.00,6.40)'" in vfx_fc
          and 'id="studio_track_vfx"' in html
          and 'id="studio_vfx_grid"' in html
          and 'id="studio_meme_sfx_grid"' in html
          and 'studioAddSfxCue' in html
          and 'studioStartCueDrag' in html
          and 'studioDeleteSelected' in html
          and 'studioUploadCustomSfx' in html)

    # 10. Manual 'Clip last 30s / 60s' processes button clicks without blocking on t_done
    live_src = (Path(__file__).resolve().parent.parent / "studio" / "live.py").read_text(encoding="utf-8")
    check("Manual clip_last queues verdict and _manual_step processes button clicks without waiting for t_done",
          "Manual clip queued" in live_src
          and "vid_ready if is_btn else m[\"end\"] <= self.t_done" in live_src
          and 'Clipping ${d.s}s' in html)

    # 11. Calendar routes deduplicates scheduled_posts + all_mine so 2/3 days still show S3
    cal_routes_src = (Path(__file__).resolve().parent.parent / "studio" / "routes" / "calendar_routes.py").read_text(encoding="utf-8")
    check("calendar_routes deduplicates scheduled_posts + all_mine before assign_slots_to_videos",
          "dedup_posts" in cal_routes_src and ("count=21" in cal_routes_src or "count=24" in cal_routes_src))

finally:
    shutil.rmtree(os.environ["PEAKCUT_DATA"], ignore_errors=True)

sys.exit(1 if fails else 0)
