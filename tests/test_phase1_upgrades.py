"""Phase 1 upgrade regression tests: atomic backup/recovery, GPU AMF fallback, ASR reuse cache, route dedup, yt_tags."""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-phase1-")
os.environ["DATABASE_URL"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from studio import accounts, auth, ctx, db, jobs, posting, render, safe, server  # noqa: E402

db.init()
fails = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra and not ok else ""))
    if not ok:
        fails.append(name)


try:
    # 1. Atomic write + .bak recovery
    tmp_dir = Path(os.environ["PEAKCUT_DATA"]) / "atomic_test"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_dir / "sample.json"
    safe.atomic_write_text(target, json.dumps({"v": 1, "ok": True}), backup=True)
    safe.atomic_write_text(target, json.dumps({"v": 2, "ok": True}), backup=True)
    check("atomic write creates sibling .bak of last known-good version",
          (tmp_dir / "sample.json.bak").is_file()
          and (safe.load_json_with_backup(tmp_dir / "sample.json.bak", default={}) or {}).get("v") == 1)

    target.write_bytes(b"\x00\x00corrupted{bad")
    recovered = safe.load_json_with_backup(target, default={})
    check("load_json_with_backup recovers valid .bak when primary has null bytes",
          isinstance(recovered, dict) and recovered.get("v") == 1)

    # Corrupt primary must NOT overwrite good .bak
    safe.atomic_write_text(target, json.dumps({"v": 3}), backup=True)
    check("corrupt primary did not overwrite valid .bak on next atomic save",
          (safe.load_json_with_backup(tmp_dir / "sample.json.bak", default={}) or {}).get("v") == 1)

    # 2. jobs.save + _load_file .bak auto-recovery
    u, _ = auth._create("p1@example.com", "P1", password_hash="x")
    with ctx.as_user(u.id):
        job = jobs.create({"type": "url", "url": "https://example.com/p1", "name": "p1"}, {}, enqueue=False)
        jfile = Path(job["dir"]) / "job.json"
        jbak = Path(job["dir"]) / "job.json.bak"
        check("jobs.save creates job.json.bak", jbak.is_file())
        jfile.write_text("{truncated-invalid-json", encoding="utf-8")
        jobs._jobs.pop(job["id"], None)
        jobs._by_user.get(u.id, {}).pop(job["id"], None)
        jobs._load_file(jfile, u.id)
        reloaded = jobs.get(job["id"])
        check("jobs._load_file recovers job cleanly from job.json.bak",
              isinstance(reloaded, dict) and reloaded.get("id") == job["id"])

        # 3. _aligned_words live ASR cache + jobs.public sanitization
        dummy_clip = {
            "id": "clip99", "start": 10.0, "end": 20.0, "title": "t",
            "_aligned_words": [{"w": "hello", "s": 10.5, "e": 11.0}, {"w": "world", "s": 11.1, "e": 11.6}],
        }
        job["clips"].append(dummy_clip)
        pub = jobs.public(job)
        check("jobs.public strips internal _aligned_words key",
              "_aligned_words" not in pub["clips"][-1])

        malformed_pub = jobs.public({"id": "legacy_no_source", "title": "Recovered Job", "status": "done"})
        check("jobs.public handles legacy recovered job missing source/clips without KeyError",
              malformed_pub["source"]["name"] == "Recovered Job" and malformed_pub["clips"] == [])

        fake_src = tmp_dir / "dummy.src.mp4"
        fake_src.write_bytes(b"fakevideo")
        with patch("studio.transcribe.transcribe", side_effect=AssertionError("double transcribe should not run")), \
             patch("studio.media.run", side_effect=AssertionError("redundant wav ffmpeg extract should not run")), \
             patch("studio.brain.english_captions", side_effect=lambda words, *a, **k: words):
            words_out = jobs._caption_words(job, dummy_clip, [], 10.0, src=fake_src, local_start=0.0, local_end=10.0)
        check("jobs._caption_words reuses _aligned_words without re-running Whisper/ffmpeg",
              [w["w"] for w in words_out] == ["hello", "world"] and "_aligned_words" not in dummy_clip)

    # 4. Encoder detection & AMF -> CPU fallback + PEAKCUT_CPU_ENCODE override
    avail = render._supported_encoders()
    check("libx264 detected in supported ffmpeg encoders", "libx264" in avail)

    orig_amf = render._amf_ok
    try:
        render._amf_ok = None
        seen_encoders = []

        class _Proc:
            def __init__(self, rc, err=""):
                self.returncode = rc
                self.stderr = err
                self.stdout = ""

        def fake_subproc(cmd, **kw):
            enc_idx = cmd.index("-c:v") + 1
            enc_name = cmd[enc_idx]
            seen_encoders.append(enc_name)
            if enc_name != "libx264":
                return _Proc(1, "simulated hw init failure")
            return _Proc(0, "")

        with patch.dict(os.environ, {"PEAKCUT_CPU_ENCODE": "0"}, clear=False), \
             patch("studio.render._supported_encoders", return_value={"h264_amf", "libx264"}), \
             patch("studio.render.subprocess.run", side_effect=fake_subproc):
            used = render._encode_with_fallback(["ffmpeg", "-y", "-i", "in.mp4", "-pix_fmt"], "out.mp4")
        check("encoder tries h264_amf first and falls back cleanly to libx264",
              seen_encoders == ["h264_amf", "libx264"] and used == "x264" and render._amf_ok is False)

        seen_encoders.clear()
        with patch.dict(os.environ, {"PEAKCUT_CPU_ENCODE": "1"}, clear=False), \
             patch("studio.render._supported_encoders", return_value={"h264_amf", "libx264"}), \
             patch("studio.render.subprocess.run", side_effect=fake_subproc):
            render._amf_ok = None
            used_cpu = render._encode_with_fallback(["ffmpeg", "-y", "-i", "in.mp4", "-pix_fmt"], "out.mp4")
        check("PEAKCUT_CPU_ENCODE=1 forces CPU libx264 directly",
              seen_encoders == ["libx264"] and used_cpu == "x264")
    finally:
        render._amf_ok = orig_amf

    # 5. Duplicate review_clip route removed
    review_routes = [
        r for r in server.app.routes
        if getattr(r, "path", "") == "/api/jobs/{jid}/clips/{cid}/review"
        and "POST" in getattr(r, "methods", set())
    ]
    check("exactly one POST /api/jobs/{jid}/clips/{cid}/review route registered",
          len(review_routes) == 1, f"found {len(review_routes)}")

    # 6. posting._post non-YouTube branch initializes yt_tags safely
    clip_mp4 = tmp_dir / "clip01.mp4"
    clip_mp4.write_bytes(b"mp4bytes")
    fake_job = {
        "id": "job1", "dir": str(tmp_dir), "user": u.id, "title": "Stream", "creator": "ohnepixel",
        "clips": [{
            "id": "clip01", "file": "clip01.mp4", "status": "done", "title": "IG Clip",
            "description": "Cool", "hashtags": ["#gaming", "#shorts"], "seo_tags": ["gta6"],
            "pinned_comment": "Wait for the end!",
        }],
    }
    ig_post = {
        "id": "post_ig_1", "user": u.id, "creator": "ohnepixel", "account": "acc_ig",
        "job": "job1", "clip": "clip01", "kind": "video", "status": "scheduled", "due_at": 0, "now": True, "tries": 0,
    }
    comm_post = {
        "id": "post_comm_1", "user": u.id, "creator": "ohnepixel", "account": "acc_yt",
        "job": "job1", "clip": "clip01", "kind": "community", "status": "scheduled", "due_at": 9999999999,
    }
    (tmp_dir / "clips").mkdir(exist_ok=True)
    shutil.copyfile(clip_mp4, tmp_dir / "clips" / "clip01.mp4")
    orig_posts = list(posting._posts)
    try:
        posting._posts[:] = [ig_post, comm_post]
        with ctx.as_user(u.id), \
             patch("studio.accounts.get", return_value={"id": "acc_ig", "platform": "instagram", "name": "IG"}), \
             patch("studio.accounts.instagram_upload", return_value=("ig_123", "https://instagram.com/reel/ig_123")), \
             patch("studio.jobs.get", return_value=fake_job), \
             patch("studio.creators.get", return_value={"id": "ohnepixel", "privacy": "public", "post_cleanup": "keep"}), \
             patch("studio.creators.log"), \
             patch("studio.posting._save"):
            posting._post(ig_post)
        check("posting._post non-YouTube with paired community post avoids yt_tags UnboundLocalError",
              ig_post["status"] == "posted" and ("gta6" in (comm_post.get("formatted_text") or "") or "#gaming" in (comm_post.get("formatted_text") or "")))
    finally:
        posting._posts[:] = orig_posts

finally:
    db.engine.dispose()
    shutil.rmtree(os.environ["PEAKCUT_DATA"], ignore_errors=True)

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
