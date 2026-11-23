import json
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from studio import auth, ctx, db, jobs, server


class TestClipCleanSeo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.uid = "u_local"
        ctx.set_uid(cls.uid)
        cls.tok = auth.start_session(cls.uid)
        cls.client = TestClient(server.app, base_url="http://127.0.0.1:8765")
        cls.auth_headers = {
            "Origin": "http://127.0.0.1:8765",
            "Host": "127.0.0.1:8765",
        }
        cls.cookies = {"s": cls.tok}

    def test_save_post_text_persists_seo_and_hook_instantly(self):
        """Verify save_post_text immediately updates SEO fields, hook and style without re-render."""
        job = {
            "id": "job_seo_test",
            "dir": "f:/Games/GTA 6 CLIPPING/PeakCut/data/runs/dummy_job",
            "user": "local",
            "clips": [
                {
                    "id": "c1",
                    "title": "Old Title",
                    "description": "Old Desc",
                    "hook": "Old Hook",
                    "hook_style": "neon",
                    "seo_title": "Old SEO Title",
                    "seo_tags": ["gaming"],
                    "pinned_comment": "Old comment",
                }
            ],
        }
        with patch.object(jobs, "save", return_value=None):
            jobs.save_post_text(
                job,
                job["clips"][0],
                {
                    "title": "New Title #Shorts",
                    "description": "New Desc with Emojis 😂🔥",
                    "seo_title": "New High-CTR Title #Shorts",
                    "seo_tags": ["gta 6", "clutch", "viral"],
                    "pinned_comment": "Drop your thoughts below! 👇",
                    "hook": "WHAT IS THAT TATTOO 💀",
                    "hook_style": "viral_yellow",
                },
            )

        c = job["clips"][0]
        self.assertEqual(c["title"], "New Title #Shorts")
        self.assertEqual(c["description"], "New Desc with Emojis 😂🔥")
        self.assertEqual(c["seo_title"], "New High-CTR Title #Shorts")
        self.assertEqual(c["seo_tags"], ["gta 6", "clutch", "viral"])
        self.assertEqual(c["pinned_comment"], "Drop your thoughts below! 👇")
        self.assertEqual(c["hook"], "WHAT IS THAT TATTOO 💀")
        self.assertEqual(c["hook_style"], "viral_yellow")

    def test_put_clip_text_endpoint(self):
        """Verify PUT /api/jobs/{jid}/clips/{cid}/text persists hook, seo_title, seo_tags and pinned_comment."""
        with ctx.as_user(self.uid):
            job = jobs.create({"name": "test_seo_video.mp4", "size": 1024 * 1024}, {}, enqueue=False)
            jid = job["id"]
            clip_data = {
                "id": "c_seo_test",
                "start": 0.0,
                "end": 15.0,
                "dur": 15.0,
                "title": "Old Title",
                "hook": "Old Hook",
                "status": "done",
                "file": "c_seo_test.mp4",
                "cover": "c_seo_test.jpg",
                "version": 1,
            }
            job["clips"] = [clip_data]
            jobs.save(job)

        try:
            res = self.client.put(
                f"/api/jobs/{jid}/clips/c_seo_test/text",
                json={
                    "title": "Insane GTA 6 Moment 😂 #Shorts",
                    "description": "Watch till the end! #Shorts #Gaming",
                    "seo_title": "Insane GTA 6 Moment #Shorts",
                    "seo_tags": "gta 6, gaming, funny",
                    "pinned_comment": "Would you have survived this? 😂",
                    "hook": "WHAT IS THAT TATTOO 💀",
                    "hook_style": "viral_yellow",
                },
                cookies=self.cookies,
                headers=self.auth_headers,
            )
            self.assertEqual(res.status_code, 200, res.text)
            saved_job = jobs.get(jid)
            clp = saved_job["clips"][0]
            self.assertEqual(clp["hook"], "WHAT IS THAT TATTOO 💀")
            self.assertEqual(clp["hook_style"], "viral_yellow")
            self.assertEqual(clp["seo_title"], "Insane GTA 6 Moment #Shorts")
            self.assertEqual(clp["seo_tags"], ["gta 6", "gaming", "funny"])
            self.assertEqual(clp["pinned_comment"], "Would you have survived this? 😂")
        finally:
            with ctx.as_user(self.uid):
                jobs.delete(jid)

    def test_index_html_clean_modal_and_live_hook_overlay(self):
        """Ensure web/index.html is clean (no teaser card, no layout card in #clipdlg) and has instant SEO & hook overlay."""
        html = Path("f:/Games/GTA 6 CLIPPING/PeakCut/web/index.html").read_text(encoding="utf-8")

        # 1. Cleaned up modal
        self.assertNotIn("Viral Climax Teaser (Cold Open Hook)", html)
        self.assertNotIn("Layout & Framing Studio (Collapsible Accordion)", html)
        self.assertNotIn("Advanced Timing, Sync & Framing (Collapsible)", html)

        # 2. Instant Save SEO button
        self.assertIn('data-act="save_seo_instant"', html)
        self.assertIn("Save SEO &amp; Title (Instant - No Re-render)", html)

        # 3. Live Hook Overlay on #stage
        self.assertIn('id="dlg_hook_live_overlay"', html)
        self.assertIn('id="btn_dlg_replay_hook"', html)
        self.assertIn("renderHookBannerHtml", html)
        self.assertIn("updateDlgLiveHookOverlay", html)
        self.assertIn("replayDlgHookAnimation", html)


if __name__ == "__main__":
    unittest.main()
