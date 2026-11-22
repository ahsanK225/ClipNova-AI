import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from studio.render import _hook_events, _select_single_punch_word, HOOK_STYLES


class TestHookSingleYellowHighlight(unittest.TestCase):
    def test_single_yellow_highlight_per_banner(self):
        cases = [
            "OHNEPIXEL READY FOR HEISTS 🥷💀",
            "OHNPIXEL ROASTS THE MAP 😭",
            "OHNEPIXEL GETS ARRESTED?! 😱",
            "GTA 6 influencers are insane 😳",
            "OHNEPIXEL FINDS A CUTE DOG?! 🐶"
        ]
        for c in cases:
            evs = _hook_events(c, 10.0, 300, hook_style="viral_yellow")
            total_yellow = sum(ev.count(r"\c&H00E5FF&") for ev in evs)
            self.assertEqual(total_yellow, 1, f"Expected exactly 1 yellow word in banner for '{c}', got {total_yellow}")

    def test_streamer_name_never_highlighted_over_action(self):
        hook = "OHNEPIXEL READY FOR HEISTS"
        punched = _select_single_punch_word(hook)
        self.assertNotIn("*OHNEPIXEL*", punched)
        self.assertIn("*HEISTS*", punched)

        hook2 = "OHNPIXEL ROASTS THE MAP"
        punched2 = _select_single_punch_word(hook2)
        self.assertNotIn("*OHNPIXEL*", punched2)
        self.assertIn("*ROASTS*", punched2)

    def test_user_explicit_asterisks_preserved(self):
        hook = "OHNEPIXEL FINDS A *DOG*?!"
        evs = _hook_events(hook, 10.0, 300, hook_style="viral_yellow")
        total_yellow = sum(ev.count(r"\c&H00E5FF&") for ev in evs)
        self.assertEqual(total_yellow, 1)
        full_text = " ".join(evs)
        self.assertIn(r"{\c&H00E5FF&}DOG{\c&HFFFFFF&}", full_text)


if __name__ == "__main__":
    unittest.main()
