"""Unit tests for USA-Focused Automatic Publishing Calendar & Community Post Scheduling."""
import unittest
import time
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo

from studio import calendar, posting

PKT = ZoneInfo("Asia/Karachi")
US_EAST = ZoneInfo("America/New_York")
US_WEST = ZoneInfo("America/Los_Angeles")


class TestUSAPublishingCalendar(unittest.TestCase):

    def test_cycle_slots_generation(self):
        """Rule 3 & 4: Slots are 18:00 PKT (Slot 1), 00:00 PKT (Slot 2), 06:00 PKT (Slot 3)."""
        base_d = date(2026, 11, 23)
        slots = calendar.get_slots_for_cycle(base_d)
        self.assertEqual(len(slots), 3)

        dt1 = datetime.fromtimestamp(slots[0], tz=PKT)
        dt2 = datetime.fromtimestamp(slots[1], tz=PKT)
        dt3 = datetime.fromtimestamp(slots[2], tz=PKT)

        self.assertEqual((dt1.hour, dt1.minute), (18, 0)) # 6:00 PM PKT
        self.assertEqual((dt2.hour, dt2.minute), (0, 0))  # 12:00 AM PKT
        self.assertEqual((dt3.hour, dt3.minute), (6, 0))  # 6:00 AM PKT

    def test_minimum_gap_between_slots(self):
        """Rule 5: Minimum gap between video slots is at least 5-6 hours."""
        base_d = date(2026, 11, 23)
        slots = calendar.get_slots_for_cycle(base_d)

        # Gap between slot 1 (18:00) and slot 2 (00:00 next day) = 6 hours
        gap_1_2 = slots[1] - slots[0]
        self.assertEqual(gap_1_2, 6 * 3600)

        # Gap between slot 2 (00:00) and slot 3 (06:00) = 6 hours
        gap_2_3 = slots[2] - slots[1]
        self.assertEqual(gap_2_3, 6 * 3600)

        # Gap between slot 3 (06:00) and next day's slot 1 (18:00) = 12 hours
        next_slots = calendar.get_slots_for_cycle(date(2026, 11, 24))
        gap_3_next1 = next_slots[0] - slots[2]
        self.assertEqual(gap_3_next1, 12 * 3600)

    def test_eight_videos_calendar_scenario(self):
        """Rule 7: Test exact 8-video multi-day auto-roll scenario.
        Day 1: Video 1 (6:00 PM), Video 2 (12:00 AM), Video 3 (6:00 AM)
        Day 2: Video 4 (6:00 PM), Video 5 (12:00 AM), Video 6 (6:00 AM)
        Day 3: Video 7 (6:00 PM), Video 8 (12:00 AM)
        """
        # Starting at 12:00 PM PKT on Nov 23
        start_ts = datetime(2026, 11, 23, 12, 0, tzinfo=PKT).timestamp()
        assigned = calendar.assign_slots_to_videos("acc1", [], count=8, from_ts=start_ts)

        self.assertEqual(len(assigned), 8)

        expected_times = [
            ("2026-11-23 06:00 PM PKT", "2026-11-23 06:30 PM PKT"),
            ("2026-11-24 12:00 AM PKT", "2026-11-24 12:30 AM PKT"),
            ("2026-11-24 06:00 AM PKT", "2026-11-24 06:30 AM PKT"),
            ("2026-11-24 06:00 PM PKT", "2026-11-24 06:30 PM PKT"),
            ("2026-11-25 12:00 AM PKT", "2026-11-25 12:30 AM PKT"),
            ("2026-11-25 06:00 AM PKT", "2026-11-25 06:30 AM PKT"),
            ("2026-11-25 06:00 PM PKT", "2026-11-25 06:30 PM PKT"),
            ("2026-11-26 12:00 AM PKT", "2026-11-26 12:30 AM PKT"),
        ]

        for i, (exp_vid, exp_comm) in enumerate(expected_times):
            self.assertEqual(assigned[i]["video_pkt_str"], exp_vid, f"Video {i+1} time mismatch")
            self.assertEqual(assigned[i]["community_pkt_str"], exp_comm, f"Video {i+1} community time mismatch")

    def test_strict_daily_limit_and_community_exclusion(self):
        """Rule 1: Maximum 3 videos per day. Community posts do NOT count toward the limit."""
        start_ts = datetime(2026, 11, 23, 12, 0, tzinfo=PKT).timestamp()

        # Simulate existing posts for day cycle 1: 3 videos + 3 community posts
        existing = [
            {"account": "acc1", "status": "scheduled", "kind": "video", "scheduled_at": start_ts + 6 * 3600},
            {"account": "acc1", "status": "scheduled", "kind": "community", "scheduled_at": start_ts + 6.5 * 3600},
            {"account": "acc1", "status": "scheduled", "kind": "video", "scheduled_at": start_ts + 12 * 3600},
            {"account": "acc1", "status": "scheduled", "kind": "community", "scheduled_at": start_ts + 12.5 * 3600},
            {"account": "acc1", "status": "scheduled", "kind": "video", "scheduled_at": start_ts + 18 * 3600},
            {"account": "acc1", "status": "scheduled", "kind": "community", "scheduled_at": start_ts + 18.5 * 3600},
        ]

        # Scheduling a 4th video must NOT be placed on Day 1; it must roll to Day 2 (Nov 24 6:00 PM PKT)
        next_slot = calendar.find_next_available_slot("acc1", existing, from_ts=start_ts)
        self.assertEqual(next_slot["video_pkt_str"], "2026-11-24 06:00 PM PKT")

    def test_community_post_offset_and_formatting(self):
        """Rule 6: Community post offset is exactly 30 minutes, with formatted Short link."""
        vid_ts = datetime(2026, 11, 23, 18, 0, tzinfo=PKT).timestamp()
        info = calendar.format_slot_info(vid_ts)

        self.assertEqual(info["community_ts"] - info["video_ts"], 1800)
        self.assertEqual(info["video_pkt_str"], "2026-11-23 06:00 PM PKT")
        self.assertEqual(info["community_pkt_str"], "2026-11-23 06:30 PM PKT")

        text = calendar.build_community_post_text(
            title="Insane GTA 6 Stunt!",
            description="Check out this unbelievable moment from today's stream.",
            video_url="https://youtube.com/shorts/sample123",
            pinned_comment="Who else saw this live?",
            hashtags=["GTA6", "Gaming"]
        )

        self.assertIn("🔥 Insane GTA 6 Stunt!", text)
        self.assertIn("▶️ Watch the full Short here:\nhttps://youtube.com/shorts/sample123", text)
        self.assertIn("💬 Community Discussion:\nWho else saw this live?", text)
        self.assertIn("#Shorts #GTA6 #Gaming", text)

    def test_timezone_and_dst_awareness(self):
        """Rule 9: Dynamic timezone awareness for US Eastern / Pacific with DST."""
        # Winter time (EST: UTC-5, PST: UTC-8)
        winter_ts = datetime(2026, 1, 15, 18, 0, tzinfo=PKT).timestamp()
        w_info = calendar.format_slot_info(winter_ts)
        self.assertIn("EST", w_info["video_us_east_str"])
        self.assertEqual(w_info["video_us_east_str"], "08:00 AM EST")
        self.assertEqual(w_info["video_us_west_str"], "05:00 AM PST")

        # Summer time (EDT: UTC-4, PDT: UTC-7)
        summer_ts = datetime(2026, 7, 15, 18, 0, tzinfo=PKT).timestamp()
        s_info = calendar.format_slot_info(summer_ts)
        self.assertIn("EDT", s_info["video_us_east_str"])
        self.assertEqual(s_info["video_us_east_str"], "09:00 AM EDT")
        self.assertEqual(s_info["video_us_west_str"], "06:00 AM PDT")

    def test_creator_calendar_endpoint(self):
        """Verify GET /api/creators/{cid}/calendar endpoint structure and responses."""
        from fastapi.testclient import TestClient
        from studio.server import app
        from studio import auth, db

        db.init()
        client = TestClient(app, base_url="http://127.0.0.1:8765")
        tok = auth.start_session("u_local")
        res = client.get("/api/creators/ishowspeed/calendar", cookies={"s": tok}, headers={"Host": "127.0.0.1:8765"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("creator", data)
        self.assertEqual(data["creator"]["name"], "IShowSpeed")
        self.assertIn("scheduled", data)
        self.assertIn("upcoming_slots", data)
        self.assertEqual(data["max_per_day"], 3)
        self.assertIn(round(float(data["min_gap_hours"])), (5, 6))

    def test_frontend_creator_calendar_markup(self):
        """Verify web/index.html has Publishing Calendar tab and setup calendar card."""
        from pathlib import Path
        html = Path("web/index.html").read_text(encoding="utf-8")
        self.assertIn("Publishing Calendar", html)
        self.assertIn("renderCreatorCalendarCard", html)
        self.assertIn("setup_creator_calendar_card", html)
        self.assertIn("creator_calendar_view", html)
        self.assertIn("copy_post_comm", html)


if __name__ == "__main__":
    unittest.main()

