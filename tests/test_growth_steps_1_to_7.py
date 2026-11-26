import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from studio import auth, creators, ctx, db, jobs, render, server


class TestGrowthSteps1To7(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.uid = "u_local"
        cls.tok = auth.start_session(cls.uid)
        ctx.set_uid(cls.uid)
        jobs.load_user(cls.uid)
        cls.client = TestClient(server.app, base_url="http://127.0.0.1:8765")
        cls.cookies = {"s": cls.tok}
        cls.headers = {"Host": "127.0.0.1:8765"}

    def test_01_calendar_channel_filter(self):
        cid = "ohnepixel"
        if not creators.get(cid):
            self.skipTest("No creator ohnepixel")
        r_all = self.client.get(f"/api/creators/{cid}/calendar?account_id=all", cookies=self.cookies, headers=self.headers)
        self.assertEqual(r_all.status_code, 200)
        self.assertEqual(r_all.json().get("selected_account_id"), "all")
        accs = r_all.json().get("available_accounts", [])
        if accs:
            aid = accs[0]["id"]
            r_one = self.client.get(f"/api/creators/{cid}/calendar?account_id={aid}", cookies=self.cookies, headers=self.headers)
            self.assertEqual(r_one.status_code, 200)
            self.assertEqual(r_one.json().get("selected_account_id"), aid)

    def test_02_swipe_stop_boost_and_creator_default(self):
        self.assertTrue(creators.DEFAULTS.get("swipe_stop_boost"))
        vfx = render._vfx_ffmpeg_chain([{"type": "zoom_punch", "time": 0.0}])
        self.assertIn("between(t,0.00,0.40)", vfx)

    def test_03_vod_transcript_and_manual_clips_validation(self):
        c_jobs = jobs.list_jobs()
        if not c_jobs:
            self.skipTest("No jobs")
        jid = c_jobs[0]["id"]
        r_tr = self.client.get(f"/api/jobs/{jid}/transcript", cookies=self.cookies, headers=self.headers)
        self.assertEqual(r_tr.status_code, 200)
        self.assertTrue(r_tr.json().get("ok"))

        r_bad = self.client.post(
            f"/api/jobs/{jid}/manual-clips",
            json={"ranges": [{"start": 1.0, "end": 2.0}]},
            cookies=self.cookies,
            headers=self.headers,
        )
        self.assertIn(r_bad.status_code, (400, 404))

    def test_04_title_ctr_scorer(self):
        c_jobs = [j for j in jobs.list_jobs() if j.get("clips")]
        if not c_jobs:
            self.skipTest("No jobs with clips")
        jid = c_jobs[0]["id"]
        cid = c_jobs[0]["clips"][0]["id"]
        r = self.client.post(
            f"/api/jobs/{jid}/clips/{cid}/title-score",
            json={"title": "Insane GTA 6 Police Chase! #Shorts"},
            cookies=self.cookies,
            headers=self.headers,
        )
        self.assertEqual(r.status_code, 200)
        cands = r.json().get("candidates", [])
        self.assertTrue(len(cands) >= 1)
        self.assertGreaterEqual(cands[0]["ctr_score"], 70)

    def test_05_winner_insights(self):
        cid = "ohnepixel"
        if not creators.get(cid):
            self.skipTest("No creator ohnepixel")
        r = self.client.get(f"/api/creators/{cid}/winner-insights", cookies=self.cookies, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        ins = r.json().get("insights", {})
        self.assertIn("sweet_spot_dur_sec", ins)
        self.assertIn("recommendation", ins)

    def test_06_stitch_validation(self):
        c_jobs = jobs.list_jobs()
        if not c_jobs:
            self.skipTest("No jobs")
        jid = c_jobs[0]["id"]
        with patch("studio.jobs.render_one", return_value={"file": "best.mp4", "dur": 20.0}):
            r = self.client.post(f"/api/jobs/{jid}/stitch-best", json={"count": 3}, cookies=self.cookies, headers=self.headers)
            self.assertIn(r.status_code, (200, 400))

    def test_07_storage_cleanable_and_cleanup(self):
        r1 = self.client.get("/api/storage/cleanable?min_age_hours=99999", cookies=self.cookies, headers=self.headers)
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.json().get("file_count"), 0)
        r2 = self.client.post("/api/storage/cleanup", json={"min_age_hours": 99999}, cookies=self.cookies, headers=self.headers)
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json().get("deleted_files"), 0)

    def test_08_one_click_system_update(self):
        import types
        fake_ok = types.SimpleNamespace(returncode=0, stdout="Already up to date.\n", stderr="")
        with patch("subprocess.run", return_value=fake_ok):
            r = self.client.post("/api/system/update", json={}, cookies=self.cookies, headers=self.headers)
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.json().get("ok"))
            self.assertFalse(r.json().get("updated"))

    def test_09_manual_only_and_manual_clip(self):
        from studio import jobs as sj
        opts = sj.clean_options({"manual_only": True, "layout": "split_half"})
        self.assertTrue(opts.get("manual_only"))
        job = sj.create({"type": "file", "path": "", "name": "test_vod.mp4"}, opts, enqueue=False)
        try:
            d = sj.job_dir(job["id"])
            src = d / "source.mp4"
            src.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            job["source_path"] = str(src)
            job["duration"] = 120.0
            sj.save(job)
            with patch.object(sj._q, "put") as mock_put:
                r = self.client.post(f"/api/jobs/{job['id']}/manual_clip",
                                     json={"start": 10.0, "end": 35.0, "hook": "INSANE CLUTCH"},
                                     cookies=self.cookies, headers=self.headers)
                self.assertEqual(r.status_code, 200)
                data = r.json()
                self.assertTrue(data.get("ok"))
                self.assertTrue(data.get("clip_id", "").startswith("manual_"))
                mock_put.assert_called_once()
        finally:
            sj.delete(job["id"])

    def test_10_home_link_auto_creates_creator(self):
        from studio import server as ss, creators as sc
        fake_seen = {"uploader": "AutoTestStreamer99", "channel_url": "https://www.youtube.com/@AutoTestStreamer99"}
        cid = ss._resolve_or_create_creator(None, fake_seen, "https://www.youtube.com/watch?v=abc123")
        self.assertIsNotNone(cid)
        try:
            cr = sc.get(cid)
            self.assertEqual(cr["name"], "AutoTestStreamer99")
            # Second call with same uploader reuses existing creator
            cid2 = ss._resolve_or_create_creator(None, fake_seen, "https://www.youtube.com/watch?v=xyz789")
            self.assertEqual(cid2, cid)
        finally:
            if hasattr(sc, "remove"):
                sc.remove(cid)
            elif hasattr(sc, "delete"):
                sc.delete(cid)


if __name__ == "__main__":
    unittest.main()
