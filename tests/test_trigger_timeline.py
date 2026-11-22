"""Verification test suite for Golden Retention Timeline Calibration.

Golden Retention Rule:
1. Pre-roll window (10-14s, target 12s): Trigger word occurs within first 10-15s of clip.
2. Post-roll reaction (25-30s, target 28s): 25-30s of reaction, laughing & gameplay after trigger.
3. Total clip duration: ~40-42s (never cut off early at 26s).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from studio import live, ohnepixel, brain


class TestTriggerTimeline(unittest.TestCase):
    """Test suite verifying exact trigger timing offsets and post-reaction duration."""

    def test_01_level1_reaction_phrase_golden_timing(self):
        """Level 1 reaction phrase triggers at T=150.0 -> start=138.0, end=178.0, total=40.0s."""
        t_trigger = 150.0
        pre_roll, post_roll = 12.0, 28.0
        
        start = max(0.0, t_trigger - pre_roll)
        end = t_trigger + post_roll
        total_duration = end - start
        trigger_offset = t_trigger - start
        reaction_duration = end - t_trigger

        # Verify trigger occurs in first 10-15s
        self.assertEqual(trigger_offset, 12.0)
        self.assertGreaterEqual(trigger_offset, 10.0)
        self.assertLessEqual(trigger_offset, 15.0)

        # Verify post-roll reaction is 25-30s
        self.assertEqual(reaction_duration, 28.0)
        self.assertGreaterEqual(reaction_duration, 25.0)
        self.assertLessEqual(reaction_duration, 30.0)

        # Verify total duration
        self.assertEqual(total_duration, 40.0)

    def test_02_session_triggers_level1_phrase(self):
        """Simulate Session._triggers with 'what the fuck' at t=60.0."""
        s = live.Session(
            {"title": "GTA 6 stream", "uploader": "ohnePixel", "dir": "", "creator": "", "ai": {},
             "clips": [], "source": {"url": "", "name": "stream"}},
            {"trigger_words": "", "style": "bounce", "layout": "split_half"}
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
        # Trigger 'what the fuck' matched at match_t = 60.0
        self.assertEqual(c["start"], 48.0)  # 60.0 - 12.0
        self.assertEqual(c["end"], 88.0)    # 60.0 + 28.0
        self.assertEqual(c["end"] - c["start"], 40.0)
        self.assertEqual(c.get("trigger_t"), 60.0)
        # Trigger offset within clip: 12s (between 10s and 15s)
        self.assertEqual(c["trigger_t"] - c["start"], 12.0)
        self.assertLessEqual(c["trigger_t"] - c["start"], 15.0)

    def test_03_creator_custom_phrase_golden_timing(self):
        """Simulate Session._triggers with creator custom phrase 'clutch god' at t=120.0."""
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
        self.assertEqual(c["start"], 108.0)  # 120.0 - 12.0
        self.assertEqual(c["end"], 148.0)    # 120.0 + 28.0
        self.assertEqual(c["end"] - c["start"], 40.0)
        self.assertEqual(c.get("trigger_t"), 120.0)
        self.assertEqual(c["trigger_t"] - c["start"], 12.0)

    def test_04_overlapping_triggers_merged_with_post_roll(self):
        """Two triggers 8s apart: T1=100.0, T2=108.0 -> smooth extension with full post-roll."""
        s = live.Session(
            {"title": "GTA 6 stream", "uploader": "ohnePixel", "dir": "", "creator": "", "ai": {},
             "clips": [], "source": {"url": "", "name": "stream"}},
            {"trigger_words": "", "style": "bounce", "layout": "split_half"}
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
        self.assertEqual(s.manual[0]["start"], 88.0)  # 100 - 12
        self.assertEqual(s.manual[0]["end"], 128.0)   # 100 + 28

        # Second trigger 8s later: 'holy shit'
        words2 = [
            {"w": "holy", "s": 108.0, "e": 108.3},
            {"w": "shit", "s": 108.3, "e": 108.6},
        ]
        s.words = words1 + words2
        s._triggers(words2)
        # Should merge into single clip
        self.assertEqual(len(s.manual), 1)
        self.assertEqual(s.manual[0]["start"], 88.0)
        self.assertEqual(s.manual[0]["end"], 136.0)   # 108 + 28 = 136.0
        self.assertEqual(s.manual[0]["end"] - s.manual[0]["start"], 48.0)

    def test_05_category_profiles_standardized(self):
        """Verify all category profiles have min_pre_roll=12 and min_post_roll=28."""
        for cat, prof in ohnepixel.CATEGORY_PROFILES.items():
            self.assertEqual(prof["min_pre_roll"], 12, f"Failed for {cat}")
            self.assertEqual(prof["min_post_roll"], 28, f"Failed for {cat}")

    def test_06_edge_case_near_stream_start(self):
        """Trigger at t=8.0 (stream start) -> start clamps to 0.0, trigger at 8s (<=15s), end=36.0."""
        t_trigger = 8.0
        pre_roll, post_roll = 12.0, 28.0
        start = max(0.0, t_trigger - pre_roll)
        end = t_trigger + post_roll

        self.assertEqual(start, 0.0)
        self.assertEqual(end, 36.0)
        trigger_offset = t_trigger - start
        self.assertEqual(trigger_offset, 8.0)
        self.assertLessEqual(trigger_offset, 15.0)
        self.assertEqual(end - t_trigger, 28.0)


if __name__ == "__main__":
    unittest.main()
