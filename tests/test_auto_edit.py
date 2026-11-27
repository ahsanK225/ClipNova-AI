"""Tests for Signature Brand Auto-Editing (`studio/auto_edit.py` + `studio/render.py` motion VFX & watermark)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PEAKCUT_DATA", tempfile.mkdtemp(prefix="pc-brand-"))
os.environ.setdefault("DATABASE_URL", "")
sys.path.insert(0, str(ROOT))

from studio import audio, auto_edit, creators, db, jobs, render  # noqa: E402

db.init()


def check(cond: bool, msg: str):
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"PASS: {msg}")


# 1. Mid-clip pause jump-cut tightening (relative offsets + preserved minimum duration)
words = [
    {"w": "Wait", "s": 10.2, "e": 10.5},
    {"w": "what", "s": 10.6, "e": 10.9},
    {"w": "is", "s": 11.0, "e": 11.2},
    {"w": "that", "s": 11.3, "e": 11.7},
    # 3.0s silent pause inside clip between 11.7 and 14.7
    {"w": "Oh", "s": 14.7, "e": 15.0},
    {"w": "my", "s": 15.1, "e": 15.3},
    {"w": "god", "s": 15.4, "e": 15.8},
    {"w": "run!", "s": 15.9, "e": 16.4},
    # Another 2.6s silence before payoff
    {"w": "No", "s": 19.0, "e": 19.4},
    {"w": "way!", "s": 19.5, "e": 20.1},
    {"w": "Bro", "s": 22.0, "e": 22.4},
    {"w": "survived!", "s": 22.5, "e": 23.2},
]
segs = auto_edit.tighten_clip_segments(words, start=10.0, end=28.0, max_gap=0.85, keep_pad=0.22, min_out_dur=10.0)
check(len(segs) >= 2, f"tighten_clip_segments splits long pauses into jump cuts (got {len(segs)})")
check(segs[0]["start"] == 0.0 and segs[0]["orig_start"] == 10.0, "Segment starts are clip-relative while orig_start stays absolute")
check(sum(s["end"] - s["start"] for s in segs) < 18.0, "Tightened segments remove dead air inside clip")

# 2. Custom-only SFX picking (never picks built-in tracks)
mock_tracks = [
    {"id": "vine_boom", "title": "Vine Boom", "category": "meme", "duration": 2.0},
    {"id": "custom_boom_hit", "title": "Custom Boom Hit", "category": "custom", "duration": 1.1},
    {"id": "custom_long_song", "title": "Full BGM Song", "category": "custom", "duration": 42.0},
]
with patch.object(audio, "list_tracks", return_value=mock_tracks):
    picked_sfx = auto_edit.pick_custom_sfx_tracks(max_count=2)
check(len(picked_sfx) == 1 and picked_sfx[0]["id"] == "custom_boom_hit", "pick_custom_sfx_tracks strictly selects short custom SFX only")

# 3. Brand edit profiles & manual Studio preservation
clip = {"id": "c_test1", "start": 10.0, "end": 28.0, "hook": "DON'T PEEK THAT *DOOR* ⚠️", "style": "bounce"}
cr = {"id": "cr1", "brand_style": "viral_gaming", "auto_tighten": True, "auto_sfx": True, "brand_watermark": "@ParadoxClips"}
with patch.object(audio, "list_tracks", return_value=mock_tracks):
    res_brand = auto_edit.apply_brand_edit(clip, {"options": {}}, cr, None, words)
check(res_brand["applied"] is True and clip.get("video_filter") == "brand_pop", "Viral Gaming profile applies brand_pop filter")
check(any(v["type"] == "zoom_punch" for v in clip.get("vfx_cues", [])), "Viral Gaming profile places real zoom_punch VFX")
check(len(clip.get("sfx_cues", [])) >= 1 and clip["sfx_cues"][0]["track_id"] == "custom_boom_hit", "Places custom SFX on climax beat")
check(clip.get("brand_watermark") == "@ParadoxClips", "Applies creator brand watermark")

# Respect cleared manual Studio VFX
manual_clip = {"id": "c_man", "start": 0.0, "end": 16.0, "vfx_cues": [], "sfx_cues": [], "video_filter": "normal"}
with patch.object(audio, "list_tracks", return_value=mock_tracks):
    auto_edit.apply_brand_edit(manual_clip, {"options": {}}, cr, None, words)
check(manual_clip["vfx_cues"] == [] and manual_clip["sfx_cues"] == [] and manual_clip["video_filter"] == "normal",
      "Preserves explicit Studio manual clearing of VFX/SFX/filter")

# Clean defaults check: never auto-insert bruh/SFX or random mid-clip jump cuts unless opted in
check(creators.DEFAULTS["brand_style"] == "off" and creators.DEFAULTS["auto_tighten"] is False and creators.DEFAULTS["auto_sfx"] is False,
      "creators.DEFAULTS keeps continuous clean clips with zero auto SFX or jump-cuts by default")
check(creators.DEFAULTS["min_len"] == 20 and creators.DEFAULTS["max_len"] == 35 and jobs.DEFAULTS["max_len"] == 35,
      "Default clip window targets strict ~30-35s YouTube Shorts (max_len=35)")
clean_default_clip = {"id": "c_clean", "start": 0.0, "end": 35.0, "hook": "CAR CRASH REACTION 😭", "style": "bounce"}
res_off = auto_edit.apply_brand_edit(clean_default_clip, {"options": {}}, {}, None, words)
check(res_off["applied"] is False and "segments" not in clean_default_clip and "sfx_cues" not in clean_default_clip,
      "apply_brand_edit leaves clean continuous clips untouched when brand_style defaults to off")

# Creator & job option cleaning
cleaned_cr = creators._clean({"name": "Test", "brand_style": "chaos_meme", "auto_tighten": False, "auto_sfx": True, "brand_watermark": "  @MyBrand  "})
check(cleaned_cr["brand_style"] == "chaos_meme" and cleaned_cr["auto_tighten"] is False and cleaned_cr["brand_watermark"] == "@MyBrand",
      "creators._clean validates brand_style, auto_tighten, auto_sfx, and brand_watermark")
cleaned_job = jobs.clean_options({"brand_style": "cinematic", "auto_tighten": True, "auto_sfx": False, "brand_watermark": "@StreamBrand"})
check(cleaned_job["brand_style"] == "cinematic" and cleaned_job["auto_sfx"] is False and cleaned_job["brand_watermark"] == "@StreamBrand",
      "jobs.clean_options preserves valid brand options")

# 4. Real FFmpeg render smoke test with real zoom_punch + shake + brand_pop + brand_watermark + strict segment duration check
motion_expr = render._vfx_motion_chain([{"type": "zoom_punch", "time": 0.2}, {"type": "shake", "time": 1.4}])
check("crop=" in motion_expr and "scale=1080:1920:eval=frame" in motion_expr, "_vfx_motion_chain builds real dynamic crop+scale FFmpeg expression")

tmp_dir = Path(tempfile.mkdtemp(prefix="pc-render-"))
src_vid = tmp_dir / "sample.mp4"
out_dir = tmp_dir / "out"
subprocess.run([
    "ffmpeg", "-y", "-v", "error",
    "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=8",
    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(src_vid),
], check=True)
r_clip = {
    "start": 0.0, "end": 3.5, "layout": "blur", "hook": "WATCH *THIS*! 🔥",
    "style": "bounce", "highlight_words": ["this"], "video_filter": "brand_pop",
    "brand_watermark": "@ParadoxClips",
    "vfx_cues": [{"type": "zoom_punch", "time": 0.15}, {"type": "shake", "time": 1.6}, {"type": "flash", "time": 1.6}],
}
r_out = render.render_clip(src_vid, out_dir, "brand_test", r_clip, [{"w": "Watch", "s": 0.3, "e": 0.7}, {"w": "this!", "s": 0.8, "e": 1.3}], 1280, 720)
rendered_mp4 = out_dir / r_out["file"]
rendered_ass = (out_dir / "brand_test.ass").read_text(encoding="utf-8")
check(rendered_mp4.is_file() and rendered_mp4.stat().st_size > 10_000, "FFmpeg renders branded MP4 with real motion VFX & brand_pop cleanly")
check("@ParadoxClips" in rendered_ass, "Rendered ASS includes brand_watermark signature")

# Verify multi-segment concat obeys -t BEFORE -i (8s source trimmed to two 1.2s segments must stay ~2.4s, never 8s+)
seg_clip = {
    "start": 0.0, "end": 5.0, "layout": "blur", "hook": "SEGMENT TEST", "style": "bounce",
    "segments": [
        {"path": str(src_vid), "start": 0.2, "end": 1.4, "orig_start": 0.2, "orig_end": 1.4, "words": [], "src_w": 1280, "src_h": 720},
        {"path": str(src_vid), "start": 3.0, "end": 4.2, "orig_start": 3.0, "orig_end": 4.2, "words": [], "src_w": 1280, "src_h": 720},
    ],
}
s_out = render.render_clip(src_vid, out_dir, "seg_dur_test", seg_clip, [], 1280, 720)
real_dur = float(subprocess.check_output(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_dir / s_out["file"])]
).decode().strip())
check(1.8 <= real_dur <= 3.0, f"Multi-segment FFmpeg input trimming keeps exact segment sum duration ({real_dur:.2f}s vs 2.4s expected)")

print("auto_edit test suite finished cleanly.")
