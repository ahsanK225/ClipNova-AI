"""Unit and API tests for PeakCut YouTube Intelligence (`studio/yt_intel.py` + `growth_routes`)."""
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import yt_intel  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else ""


def check(cond: bool, msg: str):
    if not cond:
        print(f"FAIL: {msg}")
        sys.exit(1)
    print(f"PASS: {msg}")


# 1. Hook scoring & 21 formula classification
strong_hook = yt_intel.score_hook("DO NOT BUY THAT *CAR* IN GTA 6! 💀", mode="shorts")
weak_hook = yt_intel.score_hook("wait till the end guys basically", mode="shorts")
check(strong_hook["verdict"] > weak_hook["verdict"], "Strong warning hook outscores generic cliche filler hook")
check(strong_hook["formula"] == "The Warning", f"Hook formula classified as The Warning (got {strong_hook['formula']})")
check(len(yt_intel.HOOK_FORMULAS) == 21, "All 21 YouTube hook formulas loaded")

ranked = yt_intel.rank_hooks(["wait till the end", "HE LOST *EVERYTHING* IN 5 SECONDS?! 😭", "HE LOST EVERYTHING IN 5 SECONDS?! 😭"])
check(len(ranked) == 2, "rank_hooks deduplicates ignoring asterisks")
check("LOST" in ranked[0]["hook"], "rank_hooks places strongest stakes/clock hook first")

# 2. Title + Hook pairing linter
dup_lint = yt_intel.lint_title_pairing("Speed Crashed Purple Bugatti #Shorts", thumb="SPEED CRASHED *PURPLE* BUGATTI")
clean_lint = yt_intel.lint_title_pairing("How Did He Survive That Police Chase?! 😱 #Shorts", thumb="SPEED CRASHED *PURPLE* BUGATTI")
check(any(i["code"] == "duplicate" for i in dup_lint["issues"]), "Flags title duplicating cover/hook words")
check(clean_lint["ctr_score"] > dup_lint["ctr_score"], "Complementary title scores higher than duplicate title")
check("..." in clean_lint["mobile_preview"] or len(clean_lint["title"]) <= 40, "Mobile preview generated")

# 3. Dead-air, filler & repeat EDL detection
words = [
    {"w": "So", "s": 0.0, "e": 0.2}, {"w": "I", "s": 0.25, "e": 0.4}, {"w": "went", "s": 0.45, "e": 0.7},
    {"w": "um", "s": 0.8, "e": 1.0},  # filler separated by short gap -> force cue break via >0.7 gap:
]
cues = [
    (0.0, 1.2, "He robbed the bank"),
    (1.3, 1.7, "um"),
    (1.8, 3.0, "He robbed the bank yesterday"),  # restart of "he robbed the bank" after filler
    (4.6, 5.8, "Police came immediately"),         # 1.6s dead air gap before this
]
edl = yt_intel.analyze_transcript_edl(cues, floor=0.45)
kinds = {c["kind"] for c in edl["cuts"]}
check({"FILLER", "REPEAT", "DEAD"}.issubset(kinds), f"EDL detects FILLER, REPEAT, and DEAD (got {kinds})")
check(edl["removed_sec"] > 1.5, "EDL computes removable dead/retake seconds")

# 4. Validated YouTube chapters
comp = yt_intel.build_compilation_chapters([
    {"title": "Moment One #Shorts", "dur": 14.0},
    {"title": "Moment Two #Shorts", "dur": 12.0},
    {"title": "Moment Three #Shorts", "dur": 15.0},
])
check(comp["valid"] is True and comp["chapters"][0]["label"] == "0:00", "Compilation chapters validated (0:00 start, 3+ >=10s)")

# 5. Audience retention CSV + transcript cliff pairing
csv_sample = "Position (%),Absolute retention (%)\n0,100\n5,88\n10,60\n20,56\n35,34\n50,31\n75,28\n100,24\n"
ret = yt_intel.analyze_retention_csv(csv_sample, cues=cues, duration_sec=60.0)
check(ret["hook_leak_pct"] >= 35.0 and ret["hook_verdict"] in ("leaking", "severe"), "Retention analyzer flags heavy hook leak")
check(len(ret["cliffs"]) >= 1 and ret["cliffs"][0]["lost_pct"] >= 20.0, "Retention analyzer locates steepest drop cliff")

# 6. Channel-median viral outliers
rows = [
    {"channel": "SmallCh", "title": "Normal ep 1", "views": 1000},
    {"channel": "SmallCh", "title": "Normal ep 2", "views": 1100},
    {"channel": "SmallCh", "title": "Normal ep 3", "views": 900},
    {"channel": "SmallCh", "title": "Why Everybody Stopped Playing GTA", "views": 5500},
]
out_res = yt_intel.find_channel_outliers(rows, min_multiple=2.0)
check(len(out_res["outliers"]) == 1 and out_res["outliers"][0]["multiple"] >= 5.0, "Outlier finder scores channel-median multiple")

# 7. Live server growth_routes & /api/yt/lint API integration check (if BASE passed)
if BASE:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    # Sign up / auth via test server open signup if needed, or test /api/yt/lint auth gate + signed-in flow
    signup_req = urllib.request.Request(
        BASE + "/api/auth/signup",
        data=json.dumps({"email": "ytintel@example.com", "password": "Password123!", "name": "YT Tester"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        opener.open(signup_req, timeout=5)
    except urllib.error.HTTPError:
        pass

    # In test_permissions mode email verification may be required; verify /api/yt/lint route is mounted (not 404!)
    req = urllib.request.Request(
        BASE + "/api/yt/lint",
        data=json.dumps({"hook": "DO NOT DRIVE THAT CAR! 💀", "title": "Speed Broke GTA 6 Physics #Shorts"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = opener.open(req, timeout=5)
        payload = json.loads(resp.read().decode())
        check(payload.get("ok") is True and payload["hook"]["verdict"] > 0 and payload["title"]["ctr_score"] > 0, "/api/yt/lint endpoint responds cleanly")
    except urllib.error.HTTPError as e:
        # 401 confirms router IS mounted and protected by session auth (never 404!)
        check(e.code in (401, 403), f"/api/yt/lint mounted behind auth (got HTTP {e.code}, expected non-404)")

    ret_req = urllib.request.Request(
        BASE + "/api/analytics/retention",
        data=json.dumps({"csv_text": csv_sample}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        resp = opener.open(ret_req, timeout=5)
        payload = json.loads(resp.read().decode())
        check(payload.get("ok") is True and "cliffs" in payload, "/api/analytics/retention endpoint responds cleanly")
    except urllib.error.HTTPError as e:
        check(e.code in (401, 403), f"/api/analytics/retention mounted behind auth (got HTTP {e.code}, expected non-404)")

print("yt_intel test suite finished cleanly.")
