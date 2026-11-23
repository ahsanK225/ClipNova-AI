"""
Tests to verify no duplicate hook banner is shown when the video is already rendered with the hook.
Checks backend metadata persistence and frontend display logic.
"""
import unittest
from pathlib import Path
import re


class TestHookOverlayNoDuplicate(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent
        self.index_html = (self.root / "web" / "index.html").read_text(encoding="utf-8")
        self.jobs_py = (self.root / "studio" / "jobs.py").read_text(encoding="utf-8")

    def test_jobs_py_saves_rendered_hook_metadata(self):
        """jobs.py must record rendered_hook and rendered_hook_style when clip rendering finishes."""
        self.assertIn('rendered_hook=local.get("hook", "")', self.jobs_py)
        self.assertIn('rendered_hook_style=clip.get("hook_style", "")', self.jobs_py)

    def test_index_html_has_calc_hook_top_pos(self):
        """index.html must have calcDlgHookTopPos helper with split_half mapped to 52.5%."""
        self.assertIn("window.calcDlgHookTopPos", self.index_html)
        self.assertIn('"52.5%"', self.index_html)
        self.assertIn('"36%"', self.index_html)
        self.assertIn('"16%"', self.index_html)

    def test_index_html_hides_overlay_when_hook_is_already_burned(self):
        """index.html must hide overlay when clip is done and current hook matches rendered hook."""
        self.assertIn("isAlreadyBurnedInVideo", self.index_html)
        self.assertIn("overlay.style.display = \"none\"", self.index_html)
        self.assertIn("overlay.dataset.previewActive = \"false\"", self.index_html)

    def test_index_html_overlay_starts_hidden(self):
        """Initial #dlg_hook_live_overlay HTML must have display:none."""
        self.assertIn('id="dlg_hook_live_overlay"', self.index_html)
        self.assertIn('display:none', self.index_html)


    def test_index_html_has_generate_ai_viral_hooks(self):
        """index.html must have window.generateAiViralHooks and invoke it on btn_ai_hooks click."""
        self.assertIn("window.generateAiViralHooks", self.index_html)
        self.assertIn("generateAiViralHooks(this)", self.index_html)
        self.assertIn("active-hook", self.index_html)

    def test_server_hooks_endpoint_applies_top_hook(self):
        """studio/server.py must generate 6 hooks and apply the top hook to clip['hook']."""
        server_py = (self.root / "studio" / "server.py").read_text(encoding="utf-8")
        self.assertIn('count=6', server_py)
        self.assertIn('clip["hook"] = hooks[0]', server_py)


if __name__ == "__main__":
    unittest.main()
