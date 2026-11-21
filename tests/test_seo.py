"""Tests for YouTube Shorts SEO integration in PeakCut AI engine, jobs, and metadata."""
import os
import sys
import tempfile
import numpy as np

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-seo-")
os.environ["DATABASE_URL"] = ""
sys.path.insert(0, ".")

from studio import brain, db, games, jobs  # noqa: E402

db.init()
fails = []


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra and not ok else ""))
    ok or fails.append(name)


# 1. Test _tidy with AI provided SEO metadata
raw_clip_1 = {
    "start": 10.0,
    "end": 25.0,
    "score": 85,
    "category": "clutch",
    "hook": "1 VS 3 CLUTCH",
    "title": "Insane 1v3 Police Chase",
    "description": "Streamer escapes 5 star wanted level in GTA 6.",
    "hashtags": ["gta6", "gaming", "clutch"],
    "seo_title": "HE ACTUALLY ESCAPED 5 STARS?! #Shorts",
    "seo_tags": ["gta 6 gameplay", "police chase", "insane escape", "gta vi"],
    "pinned_comment": "Could you survive a 5-star chase in GTA 6? Let me know below! 👇",
    "highlight_words": ["run", "police", "crazy"],
    "reason": "Intense clutch moment.",
}

tidied_1 = brain._tidy(raw_clip_1, 10.0, 25.0, game="gta6")
check("seo_title is preserved and includes #Shorts", "#Shorts" in tidied_1["seo_title"])
check("seo_tags includes custom tags and game tags", any("gta 6" in t.lower() or "gta" in t.lower() for t in tidied_1["seo_tags"]))
check("pinned_comment is populated", len(tidied_1["pinned_comment"]) > 10)
check("hashtags are present", len(tidied_1["hashtags"]) >= 3)

# 2. Test _tidy fallback when AI did not return SEO fields
raw_clip_2 = {
    "start": 5.0,
    "end": 20.0,
    "score": 75,
    "category": "fail",
    "hook": "HE CRASHED",
    "title": "Worst Bike Crash Ever",
    "description": "Streamer hits a tree and flies off.",
    "hashtags": ["fail", "gaming"],
    "highlight_words": ["nooo", "tree"],
    "reason": "Hilarious bike crash.",
}

tidied_2 = brain._tidy(raw_clip_2, 5.0, 20.0, game="gta6")
check("fallback seo_title generates and appends #Shorts", "#Shorts" in tidied_2["seo_title"])
check("fallback seo_tags automatically built from game and tags", len(tidied_2["seo_tags"]) >= 3)
check("fallback pinned_comment provides engagement question for fail category", "expect that to happen" in tidied_2["pinned_comment"] or "thoughts" in tidied_2["pinned_comment"])

# 2b. Test explicit fallback_seo generator function
fb = brain.fallback_seo("Playing GTA 6 Early Access", "IShowSpeed", "gta6", category="funny")
check("fallback_seo returns valid title", "IShowSpeed" in fb["title"] or "GTA 6" in fb["title"])
check("fallback_seo returns seo_title with #Shorts", "#Shorts" in fb["seo_title"])
check("fallback_seo returns rich seo_tags", len(fb["seo_tags"]) >= 5 and "shorts" in fb["seo_tags"])
check("fallback_seo returns category-tailored pinned_comment", len(fb["pinned_comment"]) > 10)

# 3. Test fallback_by_loudness has SEO fields
loud_picks = brain.fallback_by_loudness(db=np.array([0, 1, 2, 5, 8, 2], dtype=float), words=[{"w": "hi", "s": 0, "e": 1}], n=1, max_len=30, duration=60)
if loud_picks:
    check("loudness pick has seo_title", "seo_title" in loud_picks[0] and "#Shorts" in loud_picks[0]["seo_title"])
    check("loudness pick has seo_tags", len(loud_picks[0].get("seo_tags", [])) > 0)
    check("loudness pick has pinned_comment", len(loud_picks[0].get("pinned_comment", "")) > 0)
else:
    check("loudness pick exists", False, "No loud picks returned")

# 4. Test jobs.request_render persists SEO changes
fake_clip = {
    "id": "clip001",
    "start": 10.0,
    "end": 25.0,
    "score": 80,
    "status": "done",
    "title": "Test Title",
    "hook": "TEST",
    "description": "Desc",
    "hashtags": ["test"],
    "seo_title": "Test Title #Shorts",
    "seo_tags": ["test tag", "gta"],
    "pinned_comment": "Old comment",
    "src_offset": 0.0,
    "src_end": 100.0,
}
fake_job = {
    "id": "job001",
    "title": "Test Stream",
    "creator": "c1",
    "status": "ready",
    "clips": [fake_clip],
    "duration": 100.0,
    "dir": tempfile.mkdtemp(prefix="pc-jdir-"),
}

jobs._jobs["job001"] = fake_job
jobs.save = lambda j: None  # mock save
jobs.request_render("job001", "clip001", {
    "seo_title": "NEW VIRAL TITLE #Shorts",
    "seo_tags": "tag one, tag two, gta 6 shorts",
    "pinned_comment": "New engagement question! 👇",
    "start": 10.0,
    "end": 25.0,
})

check("request_render updated seo_title", fake_clip["seo_title"] == "NEW VIRAL TITLE #Shorts")
check("request_render parsed comma-separated seo_tags", fake_clip["seo_tags"] == ["tag one", "tag two", "gta 6 shorts"])
check("request_render updated pinned_comment", fake_clip["pinned_comment"] == "New engagement question! 👇")

if fails:
    print(f"\n{len(fails)} checks failed.")
    sys.exit(1)
print("\nALL PASSED")
