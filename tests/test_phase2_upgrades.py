"""Phase 2 upgrade tests: Word Editor API/persistence, Multi-frame Live Extraction, Creator Packs, Full-Cam Check, UI Filters."""
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-phase2-")
os.environ["DATABASE_URL"] = ""
os.environ["PEAKCUT_ACCOUNTS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from studio import auth, brain, ctx, db, facecam, jobs, live, ohnepixel, render, server  # noqa: E402

db.init()
fails = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra and not ok else ""))
    if not ok:
        fails.append(name)


try:
    # 1. Word Editor Backend & HTTP Endpoints
    u, _ = auth._create("p2@example.com", "P2", password_hash="x")
    with ctx.as_user(u.id):
        job = jobs.create({"type": "url", "url": "https://example.com/p2", "name": "p2"}, {}, enqueue=False)
        jdir = Path(job["dir"])
        (jdir / "words.json").write_text(json.dumps([
            {"w": "own", "s": 10.2, "e": 10.5},
            {"w": "pixel", "s": 10.5, "e": 10.9},
            {"w": "went", "s": 11.0, "e": 11.4},
            {"w": "crazy", "s": 11.4, "e": 11.9},
        ]), encoding="utf-8")
        clip = {"id": "clip01", "start": 10.0, "end": 15.0, "status": "done", "style": "bounce", "layout": "crop"}
        job["clips"].append(clip)
        jobs.save(job)

        client = TestClient(server.app)
        tok = auth._sign({"u": u.id, "exp": 9999999999}, server.SECRET) if hasattr(auth, "_sign") else None
        # Sign cookie via server helper / login or set session token directly
        sid = auth._new_session(u.id) if hasattr(auth, "_new_session") else None
        # Call FastAPI handler directly under ctx AND via TestClient with signed cookie
        got = jobs.get_clip_words(job, clip)
        check("get_clip_words reads transcript slice for unedited clip",
              [w["w"] for w in got["words"]] == ["own", "pixel", "went", "crazy"] and got["source"] == "transcript")

        edited_in = [
            {"w": "ohnePixel", "s": 10.2, "e": 10.9},
            {"w": "", "s": 10.9, "e": 11.0},  # cleared filler should be dropped
            {"w": "went", "s": 11.0, "e": 11.4},
            {"w": "CRAZY!", "s": 11.4, "e": 11.9},
        ]
        saved = jobs.save_clip_words(job, clip, edited_in)
        check("save_clip_words strips empty words & saves edited list",
              [w["w"] for w in saved] == ["ohnePixel", "went", "CRAZY!"])

        got_after = jobs.get_clip_words(job, clip)
        check("get_clip_words prefers edited words over raw transcript",
              [w["w"] for w in got_after["words"]] == ["ohnePixel", "went", "CRAZY!"] and got_after["source"] == "edited")

        # Ensure _caption_words uses saved edited words without calling Whisper or AI rewrite
        with patch("studio.transcribe.transcribe", side_effect=AssertionError("should not transcribe edited words")), \
             patch("studio.brain.english_captions", side_effect=AssertionError("should not overwrite edited words")):
            cap_words = jobs._caption_words(job, clip, [], 0.0)
        check("_caption_words preserves user-edited words without calling AI/Whisper",
              [w["w"] for w in cap_words] == ["ohnePixel", "went", "CRAZY!"])

        # Verify FastAPI route handlers directly
        put_res = server.save_clip_words(job["id"], "clip01", {"words": [{"w": "Bro", "s": 10.2, "e": 10.6}]})
        get_res = server.get_clip_words(job["id"], "clip01")
        check("server GET/PUT clip words handlers persist updates cleanly",
              put_res.get("ok") and put_res.get("count") == 1 and [w["w"] for w in get_res["words"]] == ["Bro"])

    # 2. Multi-frame Extraction from Live .ts Segments + Multimodal Prompt + Canary Yellow + Roman Urdu Pack
    seg_dir = Path(os.environ["PEAKCUT_DATA"]) / "live_segs"
    seg_dir.mkdir(parents=True, exist_ok=True)
    seg0 = seg_dir / "seg000.ts"
    seg1 = seg_dir / "seg001.ts"
    seg0.write_bytes(b"ts0")
    seg1.write_bytes(b"ts1")
    sess = live.Session(
        {"id": "lv1", "title": "GTA 6 Live", "uploader": "DesiGamer", "dir": str(seg_dir), "creator": "desi",
         "ai": {}, "clips": [], "source": {"url": "", "name": "stream"}},
        {"trigger_words": "clip that", "style": "bounce", "layout": "split_half"},
    )
    sess.segments = [(seg0, 100.0, 110.0), (seg1, 110.0, 120.0)]
    seen_calls = []

    def fake_extract(path, t):
        seen_calls.append((Path(path).name, round(float(t), 2)))
        return b"JPEGDATA"

    with patch("studio.jobs._extract_frame_bytes", side_effect=fake_extract):
        frames = sess._extract_window_frames(100.0, 120.0, count=3)
    check("live.Session._extract_window_frames extracts 3 multi-segment frames when src_mp4 missing",
          len(frames) == 3 and seen_calls[0][0] == "seg000.ts" and seen_calls[-1][0] == "seg001.ts")

    # Canary Yellow punch word selection helper in brain
    punched = brain._apply_yellow_punch("SPEED CAUGHT AN NPC IN GTA 6")
    check("brain._apply_yellow_punch wraps single punch word in asterisks",
          punched.count("*") == 2 and "*SPEED*" not in punched)

    # Roman Urdu strong reaction phrase in ohnepixel.classify_transcript
    ru_cls = ohnepixel.classify_transcript("bhai kya hua ye police piche par gayi", game="gta 6")
    check("ohnepixel.classify_transcript detects Roman Urdu tier-1 hype phrase",
          ru_cls["tier"] == 1 and "bhai kya hua" in ru_cls["level1_matches"])

    # Multimodal judge sends multi-frame notice when list[bytes] passed
    seen_prompts = []
    with patch("studio.ai.ready", return_value=True), \
         patch("studio.ai.see_json", side_effect=lambda p, imgs, **kw: (seen_prompts.append((p, len(imgs))) or {"event_detected": True, "event_type": "glitch", "visual_score": 88, "description": "car flew", "is_entertaining": True, "reason": "wild crash"}, 10, 10)):
        mm = brain.judge_multimodal_moment(
            [{"w": "bhai", "s": 1.0, "e": 1.3}, {"w": "kya", "s": 1.3, "e": 1.6}, {"w": "hua", "s": 1.6, "e": 2.0}],
            z_scores=np.array([2.5, 3.1], dtype=np.float32),
            frame_bytes=[b"f1", b"f2", b"f3"],
            title="GTA 6 Chaos",
            uploader="Speed",
            game="GTA 6",
        )
    check("judge_multimodal_moment forwards multi-frame list & scores VIS",
          bool(seen_prompts) and seen_prompts[0][1] == 3 and "3 sequential video frames" in seen_prompts[0][0]
          and mm["signals"]["visual"]["score"] == 88 and mm["priority"] == "HIGH PRIORITY")

    # 3. Dynamic Full-Cam vs Corner-Cam Detection
    check("facecam.is_fullscreen_cam returns True when facecam box covers >=45% of frame",
          facecam.is_fullscreen_cam(seg0, 0.0, 10.0, [0, 0, 1600, 900], 1920, 1080))
    check("facecam.is_fullscreen_cam returns False when face box missing",
          not facecam.is_fullscreen_cam(seg0, 0.0, 10.0, None, 1920, 1080))

    # Flat uniform empty corner + noisy center -> True; noisy bordered corner -> False
    rng = np.random.default_rng(7)
    full_cam_frames = np.full((3, 90, 160), 40, dtype=np.uint8)
    full_cam_frames[:, 15:75, 45:115] = rng.integers(30, 220, size=(3, 60, 70), dtype=np.uint8)
    full_cam_frames[:, 2:24, 125:158] = 42  # flat wall behind top-right corner
    corner_mp4 = Path(os.environ["PEAKCUT_DATA"]) / "corner_test.mp4"
    corner_mp4.write_bytes(b"mp4")
    with patch("studio.facecam._clip_frames", return_value=full_cam_frames):
        check("facecam.is_fullscreen_cam detects empty wall corner + active center as fullscreen cam",
              facecam.is_fullscreen_cam(corner_mp4, 0.0, 10.0, [1500, 20, 390, 260], 1920, 1080))

    bordered_cam_frames = full_cam_frames.copy()
    bordered_cam_frames[:, 2:24, 125:158] = rng.integers(10, 240, size=(3, 22, 33), dtype=np.uint8)
    with patch("studio.facecam._clip_frames", return_value=bordered_cam_frames):
        check("facecam.is_fullscreen_cam preserves active corner webcam with overlay detail",
              not facecam.is_fullscreen_cam(corner_mp4, 0.0, 10.0, [1500, 20, 390, 260], 1920, 1080))

    # 4. UI HTML verification for Search/Filter Toolbar & Word Editor Modal
    html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
    for token in ("clip_filter_bar", "clip_search_q", "clip_filter_status", "clip_filter_sort",
                  "clipMatchesFilter", "sortClipsForView", "dlg_caption_words_box",
                  "loadClipWordsEditor", "save_clip_words", "save_and_remake_words"):
        check(f"web/index.html contains {token}", token in html)

finally:
    db.engine.dispose()
    shutil.rmtree(os.environ["PEAKCUT_DATA"], ignore_errors=True)

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
