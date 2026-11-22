"""Test suite for multi-title SEO suggestions, pill rendering, and AI title ideas endpoint.
"""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, ".")

os.environ.update(
    PEAKCUT_DATA=os.path.join(os.getcwd(), ".test_data_seo"),
    DATABASE_URL="",
    PEAKCUT_ACCOUNTS="0"
)

from studio import auth, brain, ctx, db, jobs, server


class TestSeoTitleSuggestions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()

    def test_generate_viral_titles_fallback(self):
        """When AI is unavailable or mocked, generate_viral_titles produces 4 high-CTR titles ending with #Shorts."""
        titles = brain.generate_viral_titles(
            text="what is that car chat look at this purple car",
            title="ohnePixel Reacts to GTA 6",
            uploader="ohnePixel",
            game="GTA 6",
            count=4
        )
        self.assertEqual(len(titles), 4)
        for t in titles:
            self.assertTrue("#Shorts" in t or "#shorts" in t, f"Title missing #Shorts: {t}")
            self.assertGreater(len(t), 10)

    def test_tidy_preserves_and_generates_four_titles(self):
        """_tidy returns 'titles' (4 items) and 'hooks' (up to 5 items)."""
        raw_clip = {
            "start": 0, "end": 15, "score": 85,
            "category": "funny", "title": "Insane GTA 6 Drift",
            "hook": "LOOK AT THAT CAR",
            "description": "Crazy drift on stream",
            "hashtags": ["gta6", "gaming"], "reason": "funny"
        }
        tidied = brain._tidy(raw_clip, 0, 15, game="GTA 6")
        self.assertIn("titles", tidied)
        self.assertIn("hooks", tidied)
        self.assertEqual(len(tidied["titles"]), 4)
        for t in tidied["titles"]:
            self.assertTrue("#Shorts" in t or "#shorts" in t)
        self.assertGreaterEqual(len(tidied["hooks"]), 3)

    def test_post_text_returns_titles(self):
        """brain.post_text returns 'titles' array along with title, description, and hashtags."""
        good = {
            "start": 0, "end": 0, "score": 80,
            "hook": "UNBELIEVABLE MOMENT", "title": "The Craziest Shot Ever",
            "description": "Watch till the end to see this insane play!",
            "hashtags": ["gaming", "viral"], "reason": "highlight"
        }
        with patch.object(brain, "ask_ai", return_value=([good], "gemini-3.5-flash-lite", 10)):
            res = brain.post_text("look at this insane play he hit the shot across the map", game="GTA 6")
            self.assertIn("title", res)
            self.assertIn("titles", res)
            self.assertIn("description", res)
            self.assertIn("hashtags", res)
            self.assertEqual(len(res["titles"]), 4)

    def test_titles_endpoint(self):
        """GET / POST /api/jobs/{jid}/clips/{cid}/titles generates and returns 4 titles and persists to clip."""
        uid = auth.local_user().id
        clip = {
            "id": "clip_title_test", "start": 0.0, "end": 10.0,
            "status": "done", "hook": "INSANE DRIFT", "title": "Speed Drives Purple Whip",
            "description": "Speed driving in GTA 6", "hashtags": ["gta6"],
            "score": 90, "version": 1, "file": "clip_title_test.mp4"
        }
        with ctx.as_user(uid):
            job = jobs.create({"type": "file", "name": "Title Test Job"}, {}, enqueue=False)
            job.update(status="done", title="IShowSpeed Plays GTA 6", uploader="IShowSpeed", game="GTA 6", clips=[clip])
            jobs.save(job)

            with patch.object(brain, "generate_viral_titles", return_value=[
                "Speed Loses It Driving Purple Whip in GTA 6! 💀 #Shorts",
                "What Did Speed Just Find in GTA 6?! 😱 #Shorts",
                "Would You Have Survived This in GTA 6?! 😂 #Shorts",
                "Speed's Funniest GTA 6 Moment Ever! 🔥 #Shorts"
            ]):
                res = server.clip_generate_titles(job["id"], "clip_title_test")
                self.assertTrue(res.get("ok"))
                self.assertEqual(len(res["titles"]), 4)
                # Verify clip updated
                j_reload = jobs.get(job["id"])
                c_reload = [x for x in j_reload["clips"] if x["id"] == "clip_title_test"][0]
                self.assertEqual(c_reload["titles"], res["titles"])

    def test_frontend_has_title_and_seo_pills(self):
        """web/index.html includes #dlg_title_pills, #dlg_seo_title_pills, btn_ai_titles, and handlers."""
        html_path = Path("web/index.html")
        self.assertTrue(html_path.is_file())
        html = html_path.read_text(encoding="utf-8")
        self.assertIn('id="dlg_title_pills"', html)
        self.assertIn('id="dlg_seo_title_pills"', html)
        self.assertIn('data-act="ai_generate_titles"', html)
        self.assertIn('data-act="pick_title"', html)
        self.assertIn('title-pill-btn', html)
        self.assertIn('seo-title-pill-btn', html)


if __name__ == "__main__":
    unittest.main()
