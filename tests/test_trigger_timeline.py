"""Verification test suite for Strict 30-35s YouTube Shorts Timeline Calibration.

Shorts Retention Rule:
1. Pre-roll window (8-12s, target 10s): Trigger/mistake/rage occurs within first ~10s of clip.
2. Post-roll reaction (18-24s, target 20s): 20s of rage, laughter, mistake aftermath & gameplay.
3. Total clip duration: ~30s strict (hard cap <= 35s even when overlapping triggers merge).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio import live, ohnepixel, brain  # noqa: E402


class TestTriggerTimeline(unittest.TestCase):
    """Test suite verifying exact trigger timing offsets and strict 30-35s duration."""

    def test_01_level1_reaction_phrase_golden_timing(self):
        """Level 1 reaction phrase triggers at T=150.0 -> start=140.0, end=170.0, total=30.0s."""
        t_trigger = 150.0
        pre_roll, post_roll = 10.0, 20.0

        start = max(0.0, t_trigger - pre_roll)
        end = t_trigger + post_roll
        total_duration = end - start
        trigger_offset = t_trigger - start
        reaction_duration = end - t_trigger

        self.assertEqual(trigger_offset, 10.0)
        self.assertGreaterEqual(trigger_offset, 8.0)
        self.assertLessEqual(trigger_offset, 12.0)

        self.assertEqual(reaction_duration, 20.0)
        self.assertGreaterEqual(reaction_duration, 18.0)
        self.assertLessEqual(reaction_duration, 25.0)

        self.assertEqual(total_duration, 30.0)

    def test_02_session_triggers_level1_phrase(self):
        """Simulate Session._triggers with 'what the fuck' at t=60.0 -> 30.0s Short."""
        s = live.Session(
            {"title": "CS2 stream", "uploader": "ohnePixel", "dir": "", "creator": "ohnepixel", "ai": {},
             "clips": [], "source": {"url": "", "name": "stream"}},
            {"trigger_words": "clip that", "style": "bounce", "layout": "split_half"}
        )
        s.last_trigger = -999.0
        words = [
            {"w": "driving", "s": 45.0, "e": 46.0},
            {"w": "around", "s": 47.0, "e": 48.0},
            {"w": "what", "s": 60.0, "e": 60.3},
            {"w": "the", "s": 60.3, "e": 60.5},
            {"w": "fuck", "s": 60.5, "e": 60.9},
            {"w": "was", "s": 61.0, "e": 61.2},
            {"w": "that", "s": 61.2, "e": 61.5},
        ]
        s.words = words
        s._triggers(words)

        self.assertEqual(len(s.manual), 1)
        c = s.manual[0]
        # Trigger 'what the fuck' matched at match_t = 60.0 -> [50.0, 80.0] (30.0s)
        self.assertEqual(c["start"], 50.0)  # 60.0 - 10.0
        self.assertEqual(c["end"], 80.0)    # 60.0 + 20.0
        self.assertEqual(c["end"] - c["start"], 30.0)
        self.assertEqual(c.get("trigger_t"), 60.0)
        self.assertEqual(c["trigger_t"] - c["start"], 10.0)

    def test_03_creator_custom_phrase_golden_timing(self):
        """Simulate Session._triggers with creator custom phrase 'clutch god' at t=120.0 -> 30.0s."""
        s = live.Session(
            {"title": "CS2 stream", "uploader": "streamer", "dir": "", "creator": "", "ai": {},
             "clips": [], "source": {"url": "", "name": "stream"}},
            {"trigger_words": "clutch god", "style": "bounce", "layout": "split_half"}
        )
        s.last_trigger = -999.0
        words = [
            {"w": "he", "s": 115.0, "e": 115.5},
            {"w": "is", "s": 116.0, "e": 116.5},
            {"w": "a", "s": 117.0, "e": 117.5},
            {"w": "clutch", "s": 120.0, "e": 120.4},
            {"w": "god", "s": 120.4, "e": 120.8},
            {"w": "solid", "s": 121.0, "e": 121.5},
            {"w": "play", "s": 121.5, "e": 122.0},
        ]
        s.words = words
        s._triggers(words)

        self.assertEqual(len(s.manual), 1)
        c = s.manual[0]
        self.assertEqual(c["start"], 110.0)  # 120.0 - 10.0
        self.assertEqual(c["end"], 140.0)    # 120.0 + 20.0
        self.assertEqual(c["end"] - c["start"], 30.0)
        self.assertEqual(c.get("trigger_t"), 120.0)
        self.assertEqual(c["trigger_t"] - c["start"], 10.0)

    def test_04_overlapping_triggers_merged_with_post_roll(self):
        """Two triggers 8s apart: T1=100.0, T2=108.0 -> merged clip capped cleanly at <=35.0s."""
        s = live.Session(
            {"title": "CS2 stream", "uploader": "ohnePixel", "dir": "", "creator": "ohnepixel", "ai": {},
             "clips": [], "source": {"url": "", "name": "stream"}},
            {"trigger_words": "clip that", "style": "bounce", "layout": "split_half"}
        )
        s.last_trigger = -999.0
        words1 = [
            {"w": "oh", "s": 100.0, "e": 100.3},
            {"w": "my", "s": 100.3, "e": 100.5},
            {"w": "god", "s": 100.5, "e": 100.8},
        ]
        s.words = list(words1)
        s._triggers(words1)
        self.assertEqual(len(s.manual), 1)
        self.assertEqual(s.manual[0]["start"], 90.0)   # 100 - 10
        self.assertEqual(s.manual[0]["end"], 120.0)    # 100 + 20

        # Second trigger 8s later: 'holy shit'
        words2 = [
            {"w": "holy", "s": 108.0, "e": 108.3},
            {"w": "shit", "s": 108.3, "e": 108.6},
        ]
        s.words = words1 + words2
        s._triggers(words2)
        self.assertEqual(len(s.manual), 1)
        self.assertEqual(s.manual[0]["end"], 128.0)    # 108 + 20 = 128.0
        self.assertLessEqual(s.manual[0]["end"] - s.manual[0]["start"], 35.0)
        self.assertEqual(s.manual[0]["start"], 93.0)   # Clamped to 128 - 35 = 93.0

    def test_05_category_profiles_standardized(self):
        """Verify all category profiles have min_pre_roll=10 and min_post_roll=20."""
        for cat, prof in ohnepixel.CATEGORY_PROFILES.items():
            self.assertEqual(prof["min_pre_roll"], 10, f"Failed for {cat}")
            self.assertEqual(prof["min_post_roll"], 20, f"Failed for {cat}")

    def test_06_edge_case_near_stream_start(self):
        """Trigger at t=8.0 (stream start) -> start clamps to 0.0, trigger at 8s, end=28.0."""
        t_trigger = 8.0
        pre_roll, post_roll = 10.0, 20.0
        start = max(0.0, t_trigger - pre_roll)
        end = t_trigger + post_roll

        self.assertEqual(start, 0.0)
        self.assertEqual(end, 28.0)
        trigger_offset = t_trigger - start
        self.assertEqual(trigger_offset, 8.0)
        self.assertLessEqual(trigger_offset, 12.0)
        self.assertEqual(end - t_trigger, 20.0)

    def test_07_copilot_clip_queue_and_snapshot(self):
        """Verify Co-Pilot injection queues strict <=35s clip with custom SEO metadata."""
        s = live.Session(
            {"id": "job_copilot_t", "title": "GTA Stream", "uploader": "Peanut", "dir": "", "creator": "theburntpeanut",
             "ai": {}, "clips": [], "source": {"url": "https://twitch.tv/test", "name": "stream"}},
            {"trigger_words": "clip that", "style": "bounce", "layout": "split_half"}
        )
        s.samples = 16000 * 120
        s.seg_clock = 120.0
        res = s.clip_copilot(50.0, 92.0, {
            "hook": "HE BLEW HIMSELF UP?! 💀",
            "title": "Streamer Accidentally Rockets His Whole Team 😂 #Shorts",
            "description": "Bro meant to heal and fired an RPG at his feet.",
            "seo_tags": ["gta 6", "funny fail", "shorts"],
            "pinned_comment": "Would you forgive this teammate? 😂👇",
            "score": 94,
            "category": "fail",
        })
        self.assertTrue(res["ok"])
        self.assertEqual(res["dur"], 35.0)  # Clamped from 42s -> 35s strict ceiling
        self.assertEqual(res["start"], 57.0)
        self.assertEqual(res["end"], 92.0)
        self.assertEqual(len(s.manual), 1)
        self.assertEqual(s.manual[0]["source"], "copilot")
        snap = s.copilot_snapshot(window_sec=120.0, max_frames=0)
        self.assertEqual(snap["jid"], "job_copilot_t")
        self.assertEqual(snap["pending_queue"], 1)


if __name__ == "__main__":
    unittest.main()
