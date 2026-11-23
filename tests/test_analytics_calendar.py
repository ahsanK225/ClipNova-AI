import unittest
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient

from studio import analytics, calendar, creators, ctx, jobs, posting, auth, db
from studio.server import app

PKT_TZ = ZoneInfo("Asia/Karachi")

class TestAnalyticsAndCalendarPriming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.tok = auth.start_session("u_local")
        ctx.set_uid("u_local")
        cls.client = TestClient(app, base_url="http://127.0.0.1:8765")
        cls.cid = "ohnepixel"
        if not creators.get(cls.cid):
            creators.create({"name": "ohnePixel", "channel": "https://youtube.com/@ohnePixel"})

    def test_01_detect_peak_hours_with_spacing(self):
        # Construct synthetic 24h velocity with peaks at hour 18 (6 PM), 23 (11 PM), 5 (5 AM)
        velocity = [100] * 24
        velocity[18] = 5000  # Major Peak 1
        velocity[19] = 4800  # Adjacent hour (should be suppressed by min_gap)
        velocity[23] = 4000  # Major Peak 2
        velocity[5] = 3000   # Major Peak 3

        peaks = analytics.detect_peak_hours(velocity, count=3, min_gap_hours=4.5)
        self.assertEqual(len(peaks), 3)
        self.assertIn(18, peaks)
        self.assertIn(23, peaks)
        self.assertIn(5, peaks)
        # Verify 19 is suppressed because it's only 1 hour from 18
        self.assertNotIn(19, peaks)

    def test_02_calculate_primed_slots(self):
        peaks = [18, 23, 5]
        # Priming 1.5 hours before peak:
        # 18:00 - 1.5h = 16:30 -> 04:30 PM
        # 23:00 - 1.5h = 21:30 -> 09:30 PM
        # 05:00 - 1.5h = 03:30 -> 03:30 AM
        primed = analytics.calculate_primed_slot_times(peaks, priming_offset_hours=1.5)
        self.assertEqual(primed, ["04:30 PM", "09:30 PM", "03:30 AM"])

    def test_03_record_views_snapshot_and_delta(self):
        cid = self.cid
        # Initial snapshot
        vstats1 = {"vid_abc": 1000, "vid_xyz": 500}
        prof1 = analytics.record_views_snapshot(cid, "yt_test", vstats1)
        self.assertIsNotNone(prof1)

        # Second snapshot with increased views
        vstats2 = {"vid_abc": 1450, "vid_xyz": 800} # +450 + 300 = +750 delta
        prof2 = analytics.record_views_snapshot(cid, "yt_test", vstats2)
        self.assertGreaterEqual(prof2["total_tracked_views_48h"], 750)
        self.assertEqual(prof2["last_sync_status"], "success")

    def test_04_save_analytics_settings(self):
        cid = self.cid
        # Update settings to custom mode
        res = analytics.save_analytics_settings(cid, {
            "mode": "custom",
            "custom_peaks_pkt": [17, 22, 4],
            "priming_offset_hours": 1.0,
            "min_gap_hours": 4.5
        })
        self.assertEqual(res["mode"], "custom")
        self.assertEqual(res["detected_peaks_pkt"], [17, 22, 4])
        self.assertEqual(res["priming_offset_hours"], 1.0)
        # 17:00 - 1.0h = 16:00 -> 04:00 PM
        self.assertIn("04:00 PM", res["primed_slots_pkt"])

        # Reset to analytics mode
        res_reset = analytics.save_analytics_settings(cid, {
            "mode": "analytics",
            "priming_offset_hours": 1.5
        })
        self.assertEqual(res_reset["mode"], "analytics")

    def test_05_dynamic_calendar_slots_assignment(self):
        cid = self.cid
        slots = calendar.assign_slots_to_videos(
            account_id="yt_test",
            existing_posts=[],
            count=3,
            creator_id=cid
        )
        self.assertEqual(len(slots), 3)
        for s in slots:
            self.assertTrue(s.get("is_analytics_driven"))
            self.assertIn("Primed", s.get("priming_note", ""))
            self.assertEqual(s.get("creator_id"), cid)

    def test_06_server_api_analytics_endpoints(self):
        cid = self.cid
        cookie = {"s": self.tok}
        headers = {"Host": "127.0.0.1:8765"}

        # 1. GET velocity
        r = self.client.get(f"/api/creators/{cid}/analytics/velocity", cookies=cookie, headers=headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("hourly_velocity", data)
        self.assertIn("detected_peaks_pkt", data)
        self.assertIn("primed_slots_pkt", data)

        # 2. POST settings
        r_set = self.client.post(f"/api/creators/{cid}/analytics/settings", json={
            "mode": "analytics",
            "priming_offset_hours": 1.5,
            "min_gap_hours": 5.0
        }, cookies=cookie, headers=headers)
        self.assertEqual(r_set.status_code, 200)
        self.assertEqual(r_set.json()["ok"], True)

        # 3. POST sync
        r_sync = self.client.post(f"/api/creators/{cid}/analytics/sync", json={}, cookies=cookie, headers=headers)
        self.assertEqual(r_sync.status_code, 200)
        self.assertEqual(r_sync.json()["ok"], True)

        # 4. GET creator calendar includes analytics
        r_cal = self.client.get(f"/api/creators/{cid}/calendar", cookies=cookie, headers=headers)
        self.assertEqual(r_cal.status_code, 200)
        cal_data = r_cal.json()
        self.assertIn("analytics", cal_data)
        self.assertTrue(len(cal_data["upcoming_slots"]) > 0)
        first_slot = cal_data["upcoming_slots"][0]
        self.assertTrue(first_slot.get("is_analytics_driven"))


if __name__ == "__main__":
    unittest.main()
