import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from studio import render


class TestHookBannerSync(unittest.TestCase):
    def test_fonts_dir_defined_and_exists(self):
        self.assertTrue(hasattr(render, "FONTS_DIR"), "render module must have FONTS_DIR defined")
        raw_fonts_dir = Path(render.__file__).resolve().parent / "fonts"
        self.assertTrue(raw_fonts_dir.is_dir(), f"Fonts dir {raw_fonts_dir} must exist")
        # Ensure Anton and Poppins exist
        self.assertTrue((raw_fonts_dir / "Anton-Regular.ttf").exists())
        self.assertTrue((raw_fonts_dir / "Poppins-ExtraBold.ttf").exists())
        self.assertTrue((raw_fonts_dir / "ArchivoBlack-Regular.ttf").exists())

    def test_fonts_dir_escaped_colons(self):
        # On Windows, drive letters like F: must be escaped as F\: in filter strings
        if ":" in str(Path(render.__file__).resolve()):
            self.assertIn("\\:", render.FONTS_DIR, "Drive colon in FONTS_DIR must be escaped with backslash")

    def test_hook_events_generation(self):
        hook_text = "LOST ALL HIS MONEY IN GTA 6 😭"
        events = render._hook_events(hook_text, 15.0, 320, hook_style="viral_yellow")
        self.assertTrue(len(events) > 0, "Hook events must not be empty")
        # Ensure event contains dialogue line
        self.assertTrue(any("Dialogue:" in ev for ev in events))

    def test_html_contains_hook_upgrades(self):
        html_path = Path(__file__).resolve().parent.parent / "web" / "index.html"
        html = html_path.read_text(encoding="utf-8")
        self.assertIn(".hook-pill-btn.active-hook", html)
        self.assertIn("Apply Hook &amp; Re-make Video", html)
        self.assertIn("updateDlgLiveHookOverlay", html)
        self.assertIn("replayDlgHookAnimation", html)


if __name__ == "__main__":
    unittest.main()
