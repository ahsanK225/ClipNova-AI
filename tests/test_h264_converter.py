import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
import json
import subprocess
from fastapi.testclient import TestClient
from studio import auth, ctx, db, server


class TestH264Converter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init()
        cls.uid = "u_local"
        ctx.set_uid(cls.uid)
        cls.tok = auth.start_session(cls.uid)
        cls.client = TestClient(server.app, base_url="http://127.0.0.1:8765")
        cls.auth_headers = {
            "Origin": "http://127.0.0.1:8765",
            "Host": "127.0.0.1:8765",
        }
        cls.cookies = {"s": cls.tok}

    def test_convert_file_endpoint_validation(self):
        resp = self.client.post("/api/tools/convert-file-h264", json={"filepath": ""}, headers=self.auth_headers, cookies=self.cookies)
        self.assertEqual(resp.status_code, 400)

        resp2 = self.client.post("/api/tools/convert-file-h264", json={"filepath": "non_existent_file_123.mp4"}, headers=self.auth_headers, cookies=self.cookies)
        self.assertEqual(resp2.status_code, 400)

    def test_convert_real_video_to_h264(self):
        test_src = Path("test_hevc_sim.mp4")
        conv_out = Path("test_hevc_sim_opencut_h264.mp4")
        try:
            cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=0.5",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(test_src.resolve())
            ]
            subprocess.run(cmd, check=True)
            self.assertTrue(test_src.exists())

            resp = self.client.post("/api/tools/convert-file-h264", json={"filepath": str(test_src.resolve())}, headers=self.auth_headers, cookies=self.cookies)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("ok"))
            self.assertTrue(conv_out.exists())
            self.assertIn("H.264 MP4", data.get("message", ""))
        finally:
            if test_src.exists():
                test_src.unlink()
            if conv_out.exists():
                conv_out.unlink()

    def test_frontend_has_converter_button(self):
        html_path = Path(__file__).resolve().parent.parent / "web" / "index.html"
        html = html_path.read_text(encoding="utf-8")
        self.assertIn("convertAnyFileToH264", html)
        self.assertIn("convert-h264", html)
        self.assertIn("Fix HEVC Error", html)


if __name__ == "__main__":
    unittest.main()
