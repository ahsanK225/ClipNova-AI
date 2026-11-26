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
                     patch("studio.posting.media.probe", side_effect=RuntimeError("skip 2k")), \
                     patch("studio.posting.accounts.youtube_upload", side_effect=fake_upload), \
                     patch("studio.posting.accounts.youtube_set_thumbnail", return_value=False), \
                     patch("studio.posting.accounts.youtube_post_comment"), \
                     patch("studio.posting._save"), \
                     patch("studio.posting._mirror"):
                    posting._post(fake_post)

                self.assertNotIn("Strippers", captured["title"])
                self.assertIn("club scene", captured["title"])
                self.assertEqual(captured["desc"].lower().count("#shorts"), 1)
        finally:
            posting._posts[:] = orig_posts


if __name__ == "__main__":
    unittest.main()
