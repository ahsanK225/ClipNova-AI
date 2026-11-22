"""Unit tests for PeakCut / ClipNova AI:
Background Music & Meme Sounds System (Live In-Browser Preview & FFmpeg Mix Rendering)
"""
import io
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, ".")

os.environ.update(
    PEAKCUT_DATA=os.path.join(os.getcwd(), ".test_data_bgm"),
    DATABASE_URL="",
    PEAKCUT_ACCOUNTS="0"
)

from studio import audio, auth, ctx, db, jobs, render, server


class TestBgmAndMemeSounds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()

    def test_list_and_get_tracks(self):
        """Audio module returns 11 built-in tracks and resolves safe paths."""
        tracks = audio.list_tracks()
        self.assertGreaterEqual(len(tracks), 11)
        ids = [t["id"] for t in tracks]
        self.assertIn("none", ids)
        self.assertIn("phonk_drift", ids)
        self.assertIn("vine_boom", ids)
        self.assertIn("funny_sneaky", ids)
        self.assertIn("dramatic_suspense", ids)

        # Path resolution
        p = audio.get_track_path("phonk_drift")
        self.assertIsNotNone(p)
        self.assertTrue(p.is_file())
        self.assertEqual(p.suffix, ".mp3")

        # None track returns None
        self.assertIsNone(audio.get_track_path("none"))

        # Path traversal security check
        self.assertIsNone(audio.get_track_path("../../etc/passwd"))
        self.assertIsNone(audio.get_track_path("..\\..\\windows\\system32"))

    def test_save_upload_audio(self):
        """Custom audio upload validates format, size, and returns track metadata."""
        fake_wav = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
        track = audio.save_upload("My Crazy Meme.wav", fake_wav)
        self.assertTrue(track["id"].startswith("custom_"))
        self.assertEqual(track["category"], "custom")
        self.assertIn("My Crazy Meme", track["title"])

        # Resolving uploaded track
        p = audio.get_track_path(track["id"])
        self.assertIsNotNone(p)
        self.assertTrue(p.is_file())

        # Bad format rejection
        with self.assertRaises(ValueError):
            audio.save_upload("malicious.exe", b"fake")

    def test_request_render_preserves_bgm_options(self):
        """jobs.request_render stores bgm_track and bgm_volume on clip."""
        uid = auth.local_user().id
        clip = {
            "id": "clip_bgm_test", "start": 0.0, "end": 10.0,
            "status": "done", "hook": "FAST CAR", "title": "Speed Drives",
            "score": 90, "version": 1
        }
        with ctx.as_user(uid):
            job = jobs.create({"type": "file", "name": "BGM Test Job"}, {}, enqueue=False)
            job.update(status="done", clips=[clip])
            jobs.save(job)

            jobs.request_render(job["id"], "clip_bgm_test", {
                "bgm_track": "phonk_drift",
                "bgm_volume": 0.25
            })
            j_reload = jobs.get(job["id"])
            c_reload = next(x for x in j_reload["clips"] if x["id"] == "clip_bgm_test")
            self.assertEqual(c_reload["bgm_track"], "phonk_drift")
            self.assertEqual(c_reload["bgm_volume"], 0.25)

    def test_server_audio_endpoints(self):
        """Server endpoints /api/audio/tracks and /api/audio/track/{id} work cleanly."""
        res = server.audio_tracks()
        self.assertTrue(res.get("ok"))
        self.assertGreaterEqual(len(res["tracks"]), 11)

        file_resp = server.audio_track_file("phonk_drift")
        self.assertEqual(file_resp.media_type, "audio/mpeg")

    def test_frontend_has_bgm_card_and_controls(self):
        """web/index.html includes BGM controls, volume slider, and filter tabs."""
        html = Path("web/index.html").read_text(encoding="utf-8")
        self.assertIn("Background Music &amp; Meme Sounds", html)
        self.assertIn('id="dlg_bgm_vol"', html)
        self.assertIn('id="dlg_bgm_cards"', html)
        self.assertIn("loadBgmTracks", html)
        self.assertIn("selectBgmTrack", html)
        self.assertIn("updateBgmVolume", html)
        self.assertIn("toggleBgmSyncPreview", html)

    def test_render_with_bgm_mixing(self):
        """_render_in mixes background audio into output MP4 cleanly."""
        import subprocess, tempfile
        work = Path(tempfile.mkdtemp(prefix="pk_bgm_test_"))
        out_dir = Path(tempfile.mkdtemp(prefix="pk_bgm_out_"))
        try:
            # Create a 2s dummy video
            dummy_src = work / "src.mp4"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "testsrc=duration=2:size=1080x1920:rate=30",
                "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
                "-c:v", "libx264", "-c:a", "aac", str(dummy_src)
            ], check=True)

            res = render._render_in(
                work=work,
                src=dummy_src,
                out_dir=out_dir,
                name="clip_test_mixed",
                start=0.0,
                end=2.0,
                layout="gameplay",
                fg_h=1920,
                ass="[Script Info]\nScriptType: v4.00+\n[V4+ Styles]\nFormat: Name\nStyle: Default\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n",
                bgm_track="phonk_drift",
                bgm_volume=0.20
            )
            out_mp4 = out_dir / "clip_test_mixed.mp4"
            self.assertTrue(out_mp4.is_file(), f"Output file missing: {out_mp4}")
            self.assertGreater(out_mp4.stat().st_size, 5000)
        finally:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
            shutil.rmtree(out_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
