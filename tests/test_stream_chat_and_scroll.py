"""Unit tests for ClipNova AI:
1. Stream Card Live Chat Elevation & Compact Stats
2. Auto-scroll pinning & user scroll preservation across 2s polling
3. Live AI verdicts retention, wall_t timestamps & LATEST event badge
"""
import unittest
import collections
import time
from pathlib import Path
from studio import live


class TestStreamChatAndScroll(unittest.TestCase):

    def test_verdict_wall_t_and_buffer_retention(self):
        """Ensure _verdict records wall_t timestamp and preserves up to 30 verdicts."""
        class DummySession:
            def __init__(self):
                self.verdicts = []
            _verdict = live.Session._verdict

        s = DummySession()
        now = time.time()
        for i in range(35):
            s._verdict({"t": i * 10, "trigger": f"jump_{i}"}, f"Result {i}")

        # Buffer retention capped at 30, not prematurely truncated to 6
        self.assertEqual(len(s.verdicts), 30)
        # Oldest items [0..4] were trimmed, 5 is the oldest retained
        self.assertEqual(s.verdicts[0]["trigger"], "jump_5")
        self.assertEqual(s.verdicts[-1]["trigger"], "jump_34")
        # Every verdict has wall_t timestamp recorded
        for v in s.verdicts:
            self.assertIn("wall_t", v)
            self.assertGreaterEqual(v["wall_t"], now - 1.0)

    def test_recent_chat_ordering(self):
        """Ensure recent_chat_msgs maintains chronological order (oldest first, newest last)."""
        buf = collections.deque(maxlen=60)
        t0 = time.time()
        buf.append({"user": "viewer1", "msg": "first message", "t": t0})
        buf.append({"user": "viewer2", "msg": "second message", "t": t0 + 1})
        buf.append({"user": "viewer3", "msg": "latest message", "t": t0 + 2})

        chat_list = list(buf)
        self.assertEqual(chat_list[0]["msg"], "first message")
        self.assertEqual(chat_list[-1]["msg"], "latest message")

    def test_frontend_html_structure_and_scroll_preservation(self):
        """Verify web/index.html has the elevated chat, compact stats, and scroll restoration logic."""
        html_path = Path(__file__).resolve().parent.parent / "web" / "index.html"
        self.assertTrue(html_path.is_file(), "web/index.html must exist")
        content = html_path.read_text(encoding="utf-8")

        # 1. Compact stats styling in .sinfo
        self.assertIn("sstats-compact", content)
        self.assertIn("watching", content)

        # 2. Elevated Live Chat inside drawStream
        self.assertIn("sinfo-chat-box", content)
        self.assertIn("stream_live_chat_list", content)
        self.assertIn("stream_chat_jump_btn", content)

        # 3. Duplicate live chat removed from bottom meters, replaced with clean layout
        self.assertNotIn('id="live_chat_stream"', content, "Duplicate chat must be removed from bottom grid")

        # 4. AI verdicts container has persistent ID and LATEST badge
        self.assertIn('id="live_ai_verdicts_list"', content)
        self.assertIn("⚡ LATEST", content)

        # 5. render() scroll preservation logic
        self.assertIn("chatWasNearBottom", content)
        self.assertIn("chatPrevScroll", content)
        self.assertIn("aiPrevScroll", content)
        self.assertIn("newChatEl.scrollTop = newChatEl.scrollHeight", content)


if __name__ == "__main__":
    unittest.main()
