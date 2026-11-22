"""Test suite for Creator trigger_words persistence and empty/short trigger words support.
Verifies that deleting or clearing trigger_words persists cleanly and doesn't get overwritten
by MASTER_TRIGGER_WORDS, and verifies live.py keyword trigger bypass when trigger_words is empty.
"""
import json
import shutil
import unittest
from studio import creators, ctx, live


class TestCreatorTriggerWords(unittest.TestCase):
    def setUp(self):
        self.uid = "u_local"
        ctx.set_uid(self.uid)
        self.created_cids = []

    def tearDown(self):
        for cid in self.created_cids:
            try:
                shutil.rmtree(creators.root(cid), ignore_errors=True)
            except Exception:
                pass
        creators.forget(self.uid)

    def test_01_fix_and_clean_logic(self):
        """Verify _fix and _clean directly for empty string, short string, and missing key."""
        # 1. Missing key or None gets MASTER_TRIGGER_WORDS
        fixed_missing = creators._fix({})
        self.assertEqual(fixed_missing["trigger_words"], creators.MASTER_TRIGGER_WORDS)

        fixed_none = creators._fix({"trigger_words": None})
        self.assertEqual(fixed_none["trigger_words"], creators.MASTER_TRIGGER_WORDS)

        # 2. Empty string is PRESERVED (not overwritten by MASTER_TRIGGER_WORDS)
        cleaned_empty = creators._clean({"trigger_words": ""})
        self.assertEqual(cleaned_empty["trigger_words"], "")
        fixed_empty = creators._fix({"trigger_words": ""})
        self.assertEqual(fixed_empty["trigger_words"], "")

        # 3. Short phrase (< 30 characters) is PRESERVED (not overwritten)
        short_phrase = "clip that, insane"
        self.assertLess(len(short_phrase), 30)
        fixed_short = creators._fix({"trigger_words": short_phrase})
        self.assertEqual(fixed_short["trigger_words"], short_phrase)

    def test_02_default_trigger_words_assigned_on_creation(self):
        """New creator created without trigger_words receives MASTER_TRIGGER_WORDS."""
        c = creators.create({"name": "Default Test Streamer"})
        self.created_cids.append(c["id"])
        self.assertIn("trigger_words", c)
        self.assertGreaterEqual(len(c["trigger_words"]), 50)
        self.assertIn("clip that", c["trigger_words"])
        self.assertEqual(c["trigger_words"], creators.MASTER_TRIGGER_WORDS)

    def test_03_empty_trigger_words_persists_on_update_and_reload(self):
        """User deleting all trigger words (saving empty string) persists cleanly across cache and disk."""
        c = creators.create({"name": "Empty Trigger Streamer"})
        cid = c["id"]
        self.created_cids.append(cid)

        # Update with empty trigger_words (user cleared the box in setup)
        updated = creators.update(cid, {"trigger_words": ""})
        self.assertEqual(updated["trigger_words"], "")

        # Verify get() returns empty string
        fetched = creators.get(cid)
        self.assertEqual(fetched["trigger_words"], "")

        # Verify raw JSON on disk actually contains empty string
        disk_json = json.loads((creators.root(cid) / "creator.json").read_text(encoding="utf-8"))
        self.assertEqual(disk_json.get("trigger_words"), "")

        # Clear in-memory cache to force re-reading from disk through _mine() and _fix()
        creators.forget(self.uid)
        reloaded = creators.get(cid)
        self.assertEqual(reloaded["trigger_words"], "", "Empty trigger words must not be resurrected by _fix()")

    def test_04_short_custom_trigger_words_persists(self):
        """Short custom trigger words (< 30 characters) must NOT be overwritten by MASTER_TRIGGER_WORDS."""
        c = creators.create({"name": "Short Trigger Streamer"})
        cid = c["id"]
        self.created_cids.append(cid)

        short_phrase = "clip that, clutch"
        self.assertLess(len(short_phrase), 30)

        updated = creators.update(cid, {"trigger_words": short_phrase})
        self.assertEqual(updated["trigger_words"], short_phrase)

        creators.forget(self.uid)
        reloaded = creators.get(cid)
        self.assertEqual(reloaded["trigger_words"], short_phrase, "Short custom trigger words must be preserved")

    def test_05_live_session_bypasses_triggers_when_empty(self):
        """When trigger_words is empty, both built-in and custom keyword triggers must be bypassed."""
        # 1. Session with empty trigger_words
        s_empty = live.Session(
            {"title": "GTA 6 Pure AI Stream", "uploader": "ohnePixel", "dir": "", "creator": "", "ai": {},
             "clips": [], "source": {"url": "", "name": "stream"}},
            {"trigger_words": "", "style": "bounce", "layout": "split_half"}
        )
        s_empty.last_said = -999.0
        s_empty.last_trigger = -999.0

        sample_words = [
            {"w": "driving", "s": 10.0, "e": 10.5},
            {"w": "clip", "s": 11.0, "e": 11.3},
            {"w": "that", "s": 11.3, "e": 11.6},
            {"w": "fast", "s": 12.0, "e": 12.5},
        ]
        s_empty.words = list(sample_words)

        s_empty._triggers(sample_words)
        self.assertIsNone(s_empty.said, "Built-in 'clip that' must not trigger when trigger_words is empty")
        self.assertEqual(len(s_empty.manual), 0, "No keyword trigger clips should be generated when trigger_words is empty")

        # 2. Session with active trigger_words
        s_active = live.Session(
            {"title": "GTA 6 Active Trigger Stream", "uploader": "ohnePixel", "dir": "", "creator": "", "ai": {},
             "clips": [], "source": {"url": "", "name": "stream"}},
            {"trigger_words": "clip that", "style": "bounce", "layout": "split_half"}
        )
        s_active.last_said = -999.0
        s_active.last_trigger = -999.0
        s_active.words = list(sample_words)

        s_active._triggers(sample_words)
        self.assertTrue(s_active.said is not None or len(s_active.manual) > 0,
                        "Trigger words should trigger when configured")


if __name__ == "__main__":
    unittest.main()
