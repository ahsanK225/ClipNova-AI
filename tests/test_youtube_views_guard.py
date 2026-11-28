"""Tests for YouTube Shorts anti-spam burst guard, safety sanitizer, and #Shorts deduplication."""
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from studio import calendar, ctx, posting


class TestYouTubeViewsGuard(unittest.TestCase):
    def test_sanitize_youtube_shorts_text(self):
        self.assertEqual(
            posting.sanitize_youtube_shorts_text("OhnePixel Bringing Strippers Back To The Hotel 😂 #Shorts"),
            "OhnePixel Bringing club scene Back To The Hotel 😂 #Shorts",
        )
        self.assertEqual(
            posting.sanitize_youtube_shorts_text("GTA 6 Cops & Supercar Escape! 🚗 #Shorts"),
            "GTA 6 Cops & Supercar Escape! 🚗 #Shorts",
        )
        self.assertNotIn("fuck", posting.sanitize_youtube_shorts_text("What the fuck is happening").lower())

    def test_yt_needs_spacing_cooldown_and_daily_cap(self):
        now = 1_800_000_000.0
        # Empty history -> clear to post immediately
        self.assertEqual(posting._yt_needs_spacing("yt_1", [], now), "")

        # Recent upload 10 minutes ago -> triggers 45 min cooldown
        recent = [{"account": "yt_1", "platform": "youtube", "kind": "video", "status": "posted", "posted_at": now - 600}]
        self.assertIn("45 min", posting._yt_needs_spacing("yt_1", recent, now))

        # Upload 2 hours ago, same day -> clear if < 3 today
        older = [{"account": "yt_1", "platform": "youtube", "kind": "video", "status": "posted", "posted_at": now - 7200}]
        self.assertEqual(posting._yt_needs_spacing("yt_1", older, now), "")

        # 3 uploads already posted today -> triggers daily cap
        three_today = [
            {"account": "yt_1", "platform": "youtube", "kind": "video", "status": "posted", "posted_at": now - 3600 * i}
            for i in range(2, 5)
        ]
        self.assertIn("daily safe cap", posting._yt_needs_spacing("yt_1", three_today, now))

    def test_no_duplicate_shorts_hashtag_in_post(self):
        orig_posts = list(posting._posts)
        captured = {}
        try:
            with ctx.as_user("u_local"):
                posting._posts[:] = []
                fake_job = {
                    "id": "job_test_yt",
                    "creator": "ohnepixel",
                    "dir": ".",
                    "clips": [{
                        "id": "clip_1",
                        "status": "done",
                        "file": "clip_1.mp4",
                        "title": "OhnePixel Bringing Strippers To The Hotel #Shorts",
                        "description": "Crazy GTA 6 moment #GTA6 #Shorts",
                        "hashtags": ["GTA6", "Shorts"],
                        "pinned_comment": "What a wild scene!",
                    }],
                }
                fake_post = {
                    "id": "p_test_1",
                    "user": ctx.uid(),
                    "job": "job_test_yt",
                    "clip": "clip_1",
                    "creator": "ohnepixel",
                    "account": "yt_1",
                    "account_name": "TestYT",
                    "platform": "youtube",
                    "status": "posting",
                    "due_at": time.time(),
                    "now": True,
                    "tries": 0,
                    "title": "Test",
                }
                fake_acc = {"id": "yt_1", "platform": "youtube", "name": "TestYT"}

                def fake_upload(acc, path, title, desc, tags, privacy, publish_at=None):
                    captured["title"] = title
                    captured["desc"] = desc
                    return "vid123", "https://www.youtube.com/shorts/vid123"

                with patch("studio.posting.jobs.get", return_value=fake_job), \
                     patch("studio.posting.jobs.save"), \
                     patch("studio.posting.accounts.get", return_value=fake_acc), \
                     patch("studio.posting.creators.get", return_value={"privacy": "public", "post_cleanup": "keep"}), \
                     patch("studio.posting.creators.log"), \
                     patch("studio.posting.media.probe", return_value={"duration": 41.0, "width": 1080, "height": 1920}), \
                     patch("studio.posting.render.scale_to_2k") as mock_2k, \
                     patch("studio.posting.accounts.youtube_upload", side_effect=fake_upload), \
                     patch("studio.posting.accounts.youtube_set_thumbnail") as mock_thumb, \
                     patch("studio.posting.accounts.youtube_post_comment"), \
                     patch("studio.posting._save"), \
                     patch("studio.posting._mirror"):
                    posting._post(fake_post)

                self.assertFalse(mock_2k.called, "Shorts should upload native 1080x1920 without 588MB 2K bloat")
                self.assertFalse(mock_thumb.called, "Shorts <= 61s should not call thumbnails.set API")
                self.assertNotIn("Strippers", captured["title"])
                self.assertIn("club scene", captured["title"])
                self.assertFalse(captured["desc"].startswith("💬 Top Comment:"), "Description should start naturally without automated Top Comment stamp")
                self.assertEqual(captured["desc"].lower().count("#shorts"), 1)
        finally:
            posting._posts[:] = orig_posts

    def test_staggered_upload_spacing(self):
        now = 1_800_000_000.0
        # Empty queue -> uploads right now
        self.assertEqual(posting._next_staggered_upload_ts("yt_1", [], now, now + 36000), now)
        # Another post queued/uploaded at `now` -> next upload staggered +45m later (still before publishAt)
        existing = [{"account": "yt_1", "platform": "youtube", "kind": "video", "status": "scheduled", "due_at": now}]
        t2 = posting._next_staggered_upload_ts("yt_1", existing, now, now + 36000)
        self.assertGreaterEqual(t2 - now, posting.YT_STAGGER_UPLOAD_MIN_GAP_SEC)
        # Third post with t2 in queue -> staggered another +45m
        existing.append({"account": "yt_1", "platform": "youtube", "kind": "video", "status": "scheduled", "due_at": t2})
        t3 = posting._next_staggered_upload_ts("yt_1", existing, now, now + 36000)
        self.assertGreaterEqual(t3 - t2, posting.YT_STAGGER_UPLOAD_MIN_GAP_SEC)

    def test_post_top_comment_and_calendar_ui(self):
        orig_posts = list(posting._posts)
        try:
            with ctx.as_user("u_local"):
                p = {
                    "id": "p_comm_1",
                    "user": ctx.uid(),
                    "job": "j1",
                    "clip": "c1",
                    "creator": "ohnepixel",
                    "account": "yt_1",
                    "platform": "youtube",
                    "status": "posted",
                    "remote_id": "vid_live_1",
                    "pinned_comment": "Rate this escape 1-10!",
                    "comment_posted": False,
                    "comment_pending": True,
                }
                posting._posts[:] = [p]
                fake_acc = {"id": "yt_1", "platform": "youtube", "name": "TestYT"}
                with patch("studio.posting.accounts.get", return_value=fake_acc), \
                     patch("studio.posting.accounts.youtube_post_comment", return_value={"id": "c_yt_1"}) as mock_pc, \
                     patch("studio.posting.creators.log"), \
                     patch("studio.posting._save"), \
                     patch("studio.posting._mirror"):
                    res = posting.post_top_comment("p_comm_1")
                self.assertTrue(res["ok"])
                self.assertEqual(res["comment_id"], "c_yt_1")
                self.assertTrue(p["comment_posted"])
                self.assertFalse(p["comment_pending"])
                self.assertTrue(mock_pc.called)
        finally:
            posting._posts[:] = orig_posts
        html = (Path(__file__).resolve().parent.parent / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-act="post_yt_comment"', html)
        self.assertIn("💬 Post Comment", html)


if __name__ == "__main__":
    unittest.main()
