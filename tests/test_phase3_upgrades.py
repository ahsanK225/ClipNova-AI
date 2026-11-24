"""Phase 3 upgrade tests: YouTube/Kick chat feeds, real Community Post UX, silence trim, delta sync, modular routes & JS."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ["PEAKCUT_DATA"] = tempfile.mkdtemp(prefix="pc-phase3-")
os.environ["DATABASE_URL"] = ""
os.environ["PEAKCUT_ACCOUNTS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from studio import accounts, auth, chat_feeds, creators, ctx, db, jobs, live, posting, server  # noqa: E402

db.init()
fails = []


def check(name: str, ok: bool, extra: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{extra}]" if extra and not ok else ""))
    if not ok:
        fails.append(name)


try:
    # 1. Multi-Platform Chat Feeds (Twitch, YouTube, Kick + Cloudflare graceful stop)
    check("detect_platform recognizes Twitch channel URL",
          chat_feeds.detect_platform("https://www.twitch.tv/ohnepixel") == ("twitch", "ohnepixel"))
    check("detect_platform recognizes YouTube URL",
          chat_feeds.detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ")[0] == "youtube")
    check("detect_platform recognizes Kick channel URL",
          chat_feeds.detect_platform("https://kick.com/xqc") == ("kick", "xqc"))
    check("extract_youtube_video_id parses watch/live/short URLs",
          chat_feeds.extract_youtube_video_id("https://www.youtube.com/live/AbCdEfGh123") == "AbCdEfGh123"
          and chat_feeds.extract_youtube_video_id("https://youtu.be/XyZ_1234567") == "XyZ_1234567")

    parsed_msgs, nxt_cont, wait_s = chat_feeds._yt_parse_actions({
        "continuationContents": {
            "liveChatContinuation": {
                "actions": [{
                    "addChatItemAction": {
                        "item": {
                            "liveChatTextMessageRenderer": {
                                "id": "m1",
                                "authorName": {"simpleText": "AliGamer"},
                                "message": {"runs": [{"text": "NO WAY "}, {"emoji": {"shortcuts": ["💀"]}}]},
                            }
                        }
                    }
                }],
                "continuations": [{"timedContinuationData": {"continuation": "tok_next_123", "timeoutMs": 3500}}],
            }
        }
    })
    check("_yt_parse_actions parses author, message runs, continuation & wait timeout",
          parsed_msgs == [("m1", "AliGamer", "NO WAY 💀")] and nxt_cont == "tok_next_123" and wait_s == 3.5)

    sess = live.Session(
        {"id": "lv_p3", "title": "Kick Test", "uploader": "Tester", "dir": os.environ["PEAKCUT_DATA"], "creator": "",
         "ai": {}, "clips": [], "source": {"url": "https://kick.com/tester", "name": "Kick"}},
        {"trigger_words": "clip that", "style": "bounce", "layout": "split_half"},
    )
    sess.samples = 16000 * 25
    sess._record_chat_msg("viewer1", "clip this!")
    check("live.Session._record_chat_msg updates counters and recent_chat_msgs",
          sess.chat_total == 1 and sess.chat[25] == 1 and len(sess.recent_chat_msgs) == 1)

    class _FakeResp:
        def __init__(self, code, text=""):
            self.status_code = code
            self.text = text

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def get(self, *a, **kw):
            return _FakeResp(403, "Just a moment... Cloudflare")

    with patch("studio.chat_feeds.httpx.Client", _FakeClient):
        chat_feeds.run_kick_chat(sess, "tester")
    check("run_kick_chat stops gracefully on Cloudflare 403 without crashing",
          not sess.chat_on and "unavailable" in sess.chat_note.lower())

    # 2. Real Community Post UX (honest needs_manual_post instead of fake posted)
    with patch("studio.accounts._yt_token", return_value="fake_tok"), \
         patch("studio.accounts.httpx.post", return_value=_FakeResp(403, "Forbidden")):
        comm_res = accounts.youtube_post_community({"id": "yt_123", "channel_id": "UC123"}, "Watch now!")
    check("youtube_post_community returns ok=False & needs_manual=True on non-200",
          comm_res.get("ok") is False and comm_res.get("needs_manual") is True and "UC123/community" in comm_res.get("url", ""))

    u, _ = auth._create("p3@example.com", "P3", password_hash="x")
    with ctx.as_user(u.id):
        job = jobs.create({"type": "url", "url": "https://example.com/p3", "name": "p3"}, {}, enqueue=False)
        job["clips"].append({"id": "c1", "start": 0.0, "end": 30.0, "status": "done", "title": "Test Clip", "description": "Fun"})
        jobs.save(job)
        cpost = {
            "id": "comm_p1", "user": u.id, "creator": "", "account": "acc_yt",
            "account_name": "TestYT", "job": job["id"], "clip": "c1", "kind": "community", "status": "scheduled", "tries": 0,
        }
        orig_posts = list(posting._posts)
        try:
            posting._posts[:] = [cpost]
            with patch("studio.accounts.get", return_value={"id": "acc_yt", "platform": "youtube", "name": "TestYT", "channel_id": "UC123"}), \
                 patch("studio.accounts.youtube_post_community", return_value={"ok": False, "needs_manual": True, "remote_id": "", "url": "https://youtube.com/c/UC123/community"}), \
                 patch("studio.creators.log"), patch("studio.posting._save"):
                posting._post_community(cpost)
            check("posting._post_community marks needs_manual_post instead of fake posted",
                  cpost["status"] == "needs_manual_post" and job["clips"][0].get("community_ready") is True and job["clips"][0].get("community_posted") is False)
        finally:
            posting._posts[:] = orig_posts

        # 3. Dead-air silence trim
        words_sparse = [{"w": "hello", "s": 14.0, "e": 14.5}, {"w": "world", "s": 15.0, "e": 16.0}]
        ts, te = jobs.trim_dead_air(words_sparse, 10.0, 25.0, lead_pad=0.8, tail_pad=1.2, min_len=3.0)
        check("trim_dead_air trims >2s leading & >2.5s trailing silence cleanly",
              ts == 13.2 and te == 17.2)

        # Short clip preserves min_len
        ts2, te2 = jobs.trim_dead_air(words_sparse, 10.0, 25.0, min_len=15.0)
        check("trim_dead_air respects min_len lower bound", (ts2, te2) == (10.0, 25.0))

        # Creator/job option support
        c_clean = creators._clean({"trim_silence": True})
        j_clean = jobs.clean_options({"trim_silence": True})
        check("creators._clean and jobs.clean_options preserve trim_silence bool",
              c_clean.get("trim_silence") is True and j_clean.get("trim_silence") is True)

        # 4. Delta Sync + job._rev + legacy sync compatibility
        job2 = jobs.create({"type": "url", "url": "https://example.com/p3_b", "name": "p3b"}, {}, enqueue=False)
        rev1 = int(job.get("_rev") or 0)
        rev2 = int(job2.get("_rev") or 0)
        known_str = f"{job['id']}:{rev1},{job2['id']}:{rev2},deleted_id:1"
        delta_same = server.sync(v="", delta=1, known=known_str)
        check("/api/sync?delta=1 omits unchanged jobs and reports deleted IDs",
              delta_same.get("delta") is True and len(delta_same["jobs"]) == 0
              and set(delta_same["unchanged"]) == {job["id"], job2["id"]}
              and delta_same["deleted"] == ["deleted_id"])

        jobs.save(job)  # bumps job._rev
        delta_one = server.sync(v="", delta=1, known=known_str)
        check("/api/sync?delta=1 sends only updated job when its rev bumps",
              len(delta_one["jobs"]) == 1 and delta_one["jobs"][0]["id"] == job["id"]
              and delta_one["unchanged"] == [job2["id"]])

    # 5. Modular routes & JS asset serving + Node.js JS check
    def _all_paths(routes):
        out = set()
        for r in routes:
            if getattr(r, "path", ""):
                out.add(r.path)
            sub = getattr(getattr(r, "original_router", None), "routes", None)
            if sub:
                out |= _all_paths(sub)
        return out

    route_paths = _all_paths(server.app.routes)
    for p in ("/api/calendar/slots", "/api/creators/{cid}/calendar", "/api/creators/{cid}/analytics/velocity", "/api/jobs/{jid}/clips/{cid}/community"):
        check(f"modular route registered in server.app: {p}", p in route_paths)

    client = TestClient(server.app)
    check("HTTP GET /api/calendar/slots routes cleanly via modular calendar_routes",
          client.get("/api/calendar/slots").status_code in (200, 401))
    r_js = client.get("/assets/clipnova_hero.js")
    check("/assets/clipnova_hero.js served HTTP 200 cleanly", r_js.status_code == 200 and "initClipNovaHeroAnimation" in r_js.text)

    hero_path = Path(__file__).resolve().parent.parent / "web" / "clipnova_hero.js"
    node_chk = subprocess.run(["node", "--check", str(hero_path)], capture_output=True, text=True)
    check("clipnova_hero.js valid JS syntax via Node.js", node_chk.returncode == 0)

    html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
    check("web/index.html loads /assets/clipnova_hero.js & handles needs_manual_post + delta sync",
          "/assets/clipnova_hero.js" in html and "needs_manual_post" in html and "delta=1&known=" in html)

finally:
    db.engine.dispose()
    shutil.rmtree(os.environ["PEAKCUT_DATA"], ignore_errors=True)

print("ALL PASSED" if not fails else f"{len(fails)} failed")
sys.exit(1 if fails else 0)
