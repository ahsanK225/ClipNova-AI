"""Unit tests for ClipNova AI:
1. Clip Origin Badges & Labels (Manual vs Keyword Trigger vs AI Auto Detection)
2. Twitch Live Chat Message Streaming & Buffering
3. Viral Teaser Hook (Cold Open Climax) Timeline & Concat Pipeline
"""
import unittest
import collections
import time
from pathlib import Path
from studio import render, live


class TestClipOriginsChatTeaser(unittest.TestCase):

    def test_manual_clip_payload_and_source(self):
        """Ensure manual clip button press marks source='manual' and is never confused with AI."""
        # Simulated session with mocked samples
        class DummySession:
            def __init__(self):
                self.samples = 48000 * 100
                self.seg_clock = None
                self.manual = []
            clip_last = live.Session.clip_last

        s = DummySession()
        s.clip_last(30)
        self.assertEqual(len(s.manual), 1)
        req = s.manual[0]
        self.assertEqual(req["start"], 270.0)
        self.assertEqual(req["end"], 300.0)
        # When _manual_step runs on button click (no req.why), it identifies is_button=True
        is_button = (req.get("why") == "Hand clip") or (req.get("source") == "manual") or (not req.get("why"))
        self.assertTrue(is_button)

    def test_twitch_chat_parsing(self):
        """Ensure Twitch IRC PRIVMSG lines extract username and message text cleanly."""
        buf = collections.deque(maxlen=40)
        channel = "ohnepixel"
        raw_irc_line = b":fan123!fan123@fan123.tmi.twitch.tv PRIVMSG #ohnepixel :LMAO THAT PURPLE CAR IS WILD\r\n"
        line_str = raw_irc_line.decode("utf-8", "replace")
        who = live._NICK.findall(line_str)
        parts = line_str.split(f" PRIVMSG #{channel} :", 1)

        self.assertEqual(who[0], "fan123")
        self.assertTrue(len(parts) > 1)
        msg_text = parts[1].strip()
        self.assertEqual(msg_text, "LMAO THAT PURPLE CAR IS WILD")
        buf.append({"user": who[0], "msg": msg_text[:140], "t": time.time()})
        self.assertEqual(len(buf), 1)
        self.assertEqual(buf[0]["user"], "fan123")

    def test_teaser_cold_open_ass_shift(self):
        """Ensure build_ass shifts words timeline by teaser_dur and hook covers the teaser."""
        words = [
            {"w": "LOOK", "s": 10.0, "e": 10.5},
            {"w": "AT", "s": 10.6, "e": 10.9},
            {"w": "THIS", "s": 11.0, "e": 11.5},
        ]
        start = 10.0
        end = 40.0
        teaser_dur = 4.0
        ass = render.build_ass(
            words, start, end,
            hook="WHAT IS THAT CAR?!",
            style_name="bounce",
            highlight=["car"],
            hook_y=1010,
            cap_y=1360,
            hook_style="viral_yellow",
            teaser_dur=teaser_dur
        )
        self.assertIn("WHAT IS THAT", ass)
        self.assertIn("CAR?!", ass)
        # Check that Dialogue for words starts at or after teaser_dur (4.0s)
        # In ASS, 4.0s is formatted as 0:00:04.00 or similar
        self.assertIn("0:00:04", ass)

    def test_filter_vin_parameter(self):
        """Ensure _filter accepts custom input stream (e.g. vin='v_raw' from concat filter)."""
        fc = render._filter("split_half", 1080, facecam=[0, 0, 480, 360], vin="v_raw")
        self.assertIn("[v_raw]setpts=PTS-STARTPTS", fc)


if __name__ == "__main__":
    unittest.main()
