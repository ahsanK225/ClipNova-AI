"""Unit tests for ClipNova AI: Web Video Studio (In-Browser CapCut-Style Multi-Track Editor).
Tests timeline project retrieval, filters, VFX presets, export with auto-calendar scheduling,
and frontend HTML Studio view integration.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, ".")

os.environ.update(
    PEAKCUT_DATA=os.path.join(os.getcwd(), ".test_data_studio"),
    DATABASE_URL="",
    PEAKCUT_ACCOUNTS="0"
)

from fastapi.testclient import TestClient
from studio import auth, ctx, db, jobs, server, render, accounts, posting


class TestVideoStudio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.uid = "u_local"
        ctx.set_uid(cls.uid)
        cls.client = TestClient(server.app, base_url="http://127.0.0.1:8765")
        cls.tok = auth.start_session(cls.uid)
        cls.headers = {"Origin": "http://127.0.0.1:8765", "Host": "127.0.0.1:8765"}
        cls.cookies = {"s": cls.tok}

    def setUp(self):
        with ctx.as_user(self.uid):
            # Create a test job and done clip with words
            self.job = jobs.create({"name": "gta6_heist_test.mp4", "size": 1024 * 1024}, {}, enqueue=False)
            self.jid = self.job["id"]
            
            # Populate a sample clip with word-level subtitles
            words = [
                {"w": "LOOK", "s": 0.5, "e": 1.2},
                {"w": "AT", "s": 1.2, "e": 1.5},
                {"w": "THIS", "s": 1.5, "e": 2.1},
                {"w": "INSANE", "s": 2.1, "e": 3.0},
                {"w": "GTA6", "s": 3.0, "e": 3.8},
                {"w": "CHASE", "s": 3.8, "e": 4.5}
            ]
            clip_data = {
                "id": "c1_test",
                "start": 0.0,
                "end": 15.0,
                "dur": 15.0,
                "hook": "LOOK AT THIS INSANE GTA6 CHASE",
                "title": "OhnePixel Hits A $7K Jackpot in GTA 6!",
                "description": "Insane moment clipped live #Shorts #GTA6",
                "status": "done",
                "file": "c1_test.mp4",
                "cover": "c1_test.jpg",
                "version": 1,
                "words": words,
                "layout": "split",
                "facecam_pos": "top-right",
                "bgm_track": "phonk_drift",
                "bgm_volume": 0.25,
                "bgm_offset": 5.0,
                "video_filter": "vibrant",
                "speed": 1.0
            }
            
            # Insert clip into job
            self.job["clips"] = [clip_data]
            self.job["status"] = "done"
            jobs.save(self.job)

    def test_get_studio_project(self):
        """GET /api/jobs/{jid}/clips/{cid}/studio-project returns full multi-track project contract."""
        with ctx.as_user(self.uid):
            res = self.client.get(
                f"/api/jobs/{self.jid}/clips/c1_test/studio-project",
                headers=self.headers,
                cookies=self.cookies
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("ok"))
            self.assertEqual(data["clip_id"], "c1_test")
            self.assertEqual(data["duration"], 15.0)
            self.assertEqual(data["aspect_ratio"], "9:16")
            
            # Tracks
            tracks = data.get("tracks", {})
            self.assertIn("subtitles", tracks)
            self.assertEqual(len(tracks["subtitles"]), 6)
            self.assertEqual(tracks["subtitles"][0]["text"], "LOOK")
            
            self.assertIn("video", tracks)
            self.assertEqual(tracks["video"]["filter"], "vibrant")
            self.assertEqual(tracks["video"]["speed"], 1.0)
            
            self.assertIn("audio", tracks)
            self.assertEqual(tracks["audio"]["track"], "phonk_drift")
            self.assertEqual(tracks["audio"]["volume"], 0.25)
            self.assertEqual(tracks["audio"]["offset"], 5.0)
            
            # Presets & Filters
            filters = data.get("available_filters", [])
            filter_ids = [f["id"] for f in filters]
            self.assertIn("normal", filter_ids)
            self.assertIn("vibrant", filter_ids)
            self.assertIn("cinematic", filter_ids)
            self.assertIn("moody", filter_ids)
            self.assertIn("cyberpunk", filter_ids)
            self.assertIn("bw", filter_ids)
            
            vfx = data.get("available_vfx", [])
            vfx_ids = [v["id"] for v in vfx]
            self.assertIn("flash", vfx_ids)
            self.assertIn("shake", vfx_ids)
            self.assertIn("glitch", vfx_ids)
            self.assertIn("zoom_punch", vfx_ids)

    def test_post_studio_export_modifications(self):
        """POST /api/jobs/{jid}/clips/{cid}/studio-export saves filter, audio trim, word edits and re-renders."""
        payload = {
            "title": "Updated Studio Cut Title",
            "video_filter": "cyberpunk",
            "speed": 1.25,
            "bgm_track": "hype_trap",
            "bgm_volume": 0.40,
            "bgm_offset": 12.5,
            "words": [
                {"w": "INSANE", "s": 0.0, "e": 1.0},
                {"w": "SPEED", "s": 1.0, "e": 2.0}
            ]
        }
        with ctx.as_user(self.uid):
            res = self.client.post(
                f"/api/jobs/{self.jid}/clips/c1_test/studio-export",
                json=payload,
                headers=self.headers,
                cookies=self.cookies
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("ok"))
            self.assertIn("Studio export triggered", data.get("message", ""))
            
            # Verify job clip has updated properties
            updated_job = jobs.get(self.jid)
            clip = updated_job["clips"][0]
            self.assertEqual(clip["video_filter"], "cyberpunk")
            self.assertEqual(clip["speed"], 1.25)
            self.assertEqual(clip["bgm_track"], "hype_trap")
            self.assertEqual(clip["bgm_volume"], 0.40)
            self.assertEqual(clip["bgm_offset"], 12.5)

    @patch("studio.posting.enqueue")
    def test_post_studio_export_schedule_to_calendar(self, mock_enqueue):
        """POST /api/jobs/{jid}/clips/{cid}/studio-export with schedule_now=True calls posting.enqueue."""
        mock_enqueue.return_value = [{"id": "post_studio_1", "status": "scheduled", "slot": "04:30 PM"}]
        payload = {
            "title": "Scheduled Studio Cut",
            "video_filter": "cinematic",
            "schedule_now": True,
            "accounts": ["yt_acc_1"]
        }
        with ctx.as_user(self.uid):
            res = self.client.post(
                f"/api/jobs/{self.jid}/clips/c1_test/studio-export",
                json=payload,
                headers=self.headers,
                cookies=self.cookies
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("ok"))
            self.assertIsNotNone(data.get("scheduled"))
            mock_enqueue.assert_called_once()

    def test_ffmpeg_video_filters_mapping(self):
        """Ensure render.py VIDEO_FILTERS mapping exists and contains required filter graphs."""
        self.assertTrue(hasattr(render, "VIDEO_FILTERS"))
        vf = render.VIDEO_FILTERS
        self.assertIn("vibrant", vf)
        self.assertIn("cinematic", vf)
        self.assertIn("moody", vf)
        self.assertIn("cyberpunk", vf)
        self.assertIn("bw", vf)
        self.assertIn("saturation=1.3", vf["vibrant"])
        self.assertIn("hue=h=15", vf["cyberpunk"])

    def test_frontend_web_studio_ui_markup(self):
        """Ensure web/index.html includes all Studio tabs, buttons, styles and functions."""
        html_content = Path("web/index.html").read_text(encoding="utf-8")
        
        # Check tab navigation
        self.assertIn('["studio", "Video Studio", "film", 0]', html_content)
        
        # Check buttons
        self.assertIn('data-act="open_web_studio"', html_content)
        self.assertIn('Open in Web Studio', html_content)
        
        # Check functions
        self.assertIn('function drawVideoStudioTab()', html_content)
        self.assertIn('function renderStudioWorkspace()', html_content)
        self.assertIn('function saveStudioExport(', html_content)
        self.assertIn('function studioExportCapcutDesktop()', html_content)
        self.assertIn('function studioSetSubPos(', html_content)
        self.assertIn('CapCut Desktop Bridge', html_content)
        self.assertIn('OpenCut Web Studio', html_content)
        
        # Check styles
        self.assertIn('studio-track-row', html_content)
        self.assertIn('studio-word-block', html_content)
        self.assertIn('@keyframes studioShake', html_content)
        self.assertIn('@keyframes studioGlitch', html_content)
        self.assertIn('@keyframes studioZoomPunch', html_content)


if __name__ == "__main__":
    unittest.main()
