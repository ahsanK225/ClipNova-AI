"""Unit tests for YouTube video deletion, post cancellation, and view count synchronization."""
import secrets
import unittest
from unittest.mock import patch, MagicMock
from studio import ctx, accounts, posting, analytics, server
from fastapi.testclient import TestClient


class TestPostDeleteAndViews(unittest.TestCase):
    def setUp(self):
        self.uid = "u_local"
        ctx.set_uid(self.uid)
        self.client = TestClient(server.app, base_url="http://127.0.0.1:8765")
        self.test_ids = []

    def tearDown(self):
        with posting._lock:
            posting._posts = [p for p in posting._posts if p.get("id") not in self.test_ids]
            posting._save()

    def test_01_youtube_delete_account_helper(self):
        """Test accounts.youtube_delete successfully calls Google API."""
        acc = {"id": "yt_test", "platform": "youtube", "access_token": "mock_token", "expires": 9999999999}
        with patch("httpx.delete") as mock_delete:
            mock_delete.return_value = MagicMock(status_code=204)
            res = accounts.youtube_delete(acc, "mock_video_123")
            self.assertTrue(res)
            mock_delete.assert_called_once()
            args, kwargs = mock_delete.call_args
            self.assertEqual(kwargs["params"]["id"], "mock_video_123")
            self.assertIn("Bearer mock_token", kwargs["headers"]["Authorization"])

    def test_02_delete_post_cancels_and_deletes_remote(self):
        """Test delete_post cancels post and deletes remote video."""
        pid = "test_del_" + secrets.token_hex(4)
        cid = "test_comm_" + secrets.token_hex(4)
        self.test_ids.extend([pid, cid])

        test_post = {
            "id": pid,
            "user": self.uid,
            "creator": "ohnepixel",
            "platform": "youtube",
            "account": "yt_test",
            "status": "posted",
            "remote_id": "yt_vid_del_123",
            "title": "Test Deletion Video",
            "due_at": 9999999999,
            "is_scheduled": True
        }
        test_comm = {
            "id": cid,
            "user": self.uid,
            "creator": "ohnepixel",
            "platform": "youtube",
            "account": "yt_test",
            "status": "scheduled",
            "video_post_id": pid,
            "kind": "community",
            "title": "Community Post for Test Deletion",
            "due_at": 9999999999 + 1800
        }
        with posting._lock:
            posting._posts.append(test_post)
            posting._posts.append(test_comm)

        with patch("studio.posting.accounts.youtube_delete") as mock_yt_del:
            mock_yt_del.return_value = True
            res = posting.delete_post(pid, delete_remote=True)
            self.assertTrue(res["ok"])
            self.assertTrue(res["deleted_youtube"])
            self.assertEqual(res["video_id"], "yt_vid_del_123")
            mock_yt_del.assert_called_once()

        self.assertEqual(test_post["status"], "cancelled")
        self.assertEqual(test_comm["status"], "cancelled")

    def test_03_cancel_delegates_to_delete_for_posted(self):
        """Verify calling cancel on an already posted/cloud-scheduled post does not raise ValueError."""
        pid = "test_cancel_" + secrets.token_hex(4)
        self.test_ids.append(pid)

        test_post = {
            "id": pid,
            "user": self.uid,
            "creator": "ohnepixel",
            "platform": "youtube",
            "account": "yt_test",
            "status": "posted",
            "remote_id": "yt_vid_cloud_456",
            "title": "Cloud Scheduled Short",
            "due_at": 9999999999,
            "is_scheduled": True
        }
        with posting._lock:
            posting._posts.append(test_post)

        with patch("studio.posting.accounts.youtube_delete") as mock_yt_del:
            mock_yt_del.return_value = True
            res = posting.cancel(pid)
            self.assertTrue(res["ok"])
            self.assertEqual(test_post["status"], "cancelled")

    def test_04_calendar_filters_cancelled_posts(self):
        """Verify GET /api/creators/{cid}/calendar never returns cancelled posts in scheduled list."""
        pid = "test_sched_canc_" + secrets.token_hex(4)
        self.test_ids.append(pid)

        test_post = {
            "id": pid,
            "user": self.uid,
            "creator": "ohnepixel",
            "platform": "youtube",
            "account": "yt_test",
            "status": "cancelled",
            "remote_id": "yt_vid_canc_789",
            "title": "Cancelled Video",
            "due_at": 9999999999,
            "is_scheduled": True
        }
        with posting._lock:
            posting._posts.append(test_post)

        from studio import auth, db
        db.init()
        tok = auth.start_session("u_local")
        res = self.client.get("/api/creators/ohnepixel/calendar", cookies={"s": tok})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        sched_ids = [p["id"] for p in data.get("scheduled", [])]
        self.assertNotIn(pid, sched_ids)


if __name__ == "__main__":
    unittest.main()
