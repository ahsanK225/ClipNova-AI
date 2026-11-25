"""
Tests for clean AI Decisions & Moment Activity UI layout.
Verifies:
1. Redundant model badge is removed from individual list rows and meter header (displayed cleanly in stats bar).
2. Sleek compact single-line row layout with 12-hour AM/PM format, status badge, headline, and full tooltip.
3. "What was just said" raw transcript clutter is removed.
4. JavaScript in web/index.html is syntactically valid.
"""
import unittest
import os
import re
import subprocess

PEAKCUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(PEAKCUT_DIR, "web", "index.html")

class TestAIVerdictsCleanUI(unittest.TestCase):
    def setUp(self):
        with open(INDEX_HTML, "r", encoding="utf-8") as f:
            self.html = f.read()

    def test_no_redundant_model_pill_in_rows(self):
        """Ensure v.model pill was deleted from individual activity rows."""
        row_template_match = re.search(r'id="live_ai_verdicts_list"[\s\S]*?function jobHtml', self.html)
        self.assertIsNotNone(row_template_match, "live_ai_verdicts_list container must exist")
        row_template = row_template_match.group(0)
        
        self.assertNotIn('${esc(v.model', row_template)
        self.assertNotIn('gemini-3.5-flash-lite</span>', row_template)

    def test_active_model_in_stats_bar_and_clean_header(self):
        """Active AI model is cleanly shown in the stats bar, while meter header stays single-line and uncrowded."""
        self.assertIn('Active AI Model', self.html)
        self.assertIn('<span>🧠</span> Latest AI Decisions</h4>', self.html)
        self.assertIn('LIVE MONITOR', self.html)

    def test_compact_single_line_card_layout(self):
        """Verify readable 2-line broadcast monitor layout with status pill, AM/PM time, and 142px max-height."""
        self.assertIn('max-height:142px', self.html)
        row_template_match = re.search(r'id="live_ai_verdicts_list"[\s\S]*?function jobHtml', self.html)
        row_template = row_template_match.group(0)
        
        self.assertIn('time12', row_template)
        self.assertIn('badgeText', row_template)
        self.assertIn('⚡ LATEST', row_template)
        self.assertIn('${icon} <b style="color:var(--heading)">${esc(headline)}</b>', row_template)

    def test_no_what_was_just_said(self):
        """Ensure raw transcript 'What was just said' meter is removed."""
        self.assertNotIn('<h4>What was just said</h4>', self.html)

    def test_javascript_syntax_valid(self):
        """Validate that all JavaScript inside <script> tags passes compilation."""
        script_matches = re.findall(r'<script[\s\S]*?>([\s\S]*?)</script>', self.html, flags=re.IGNORECASE)
        self.assertTrue(len(script_matches) > 0, "Should have scripts in index.html")
        
        check_script_path = os.path.join(PEAKCUT_DIR, "scratch_check_syntax.js")
        try:
            with open(check_script_path, "w", encoding="utf-8") as f:
                f.write("""
const fs = require('fs');
const html = fs.readFileSync('web/index.html', 'utf-8');
const scriptMatches = [...html.matchAll(/<script[\\s\\S]*?>([\\s\\S]*?)<\\/script>/gi)];
for (let i = 0; i < scriptMatches.length; i++) {
  const code = scriptMatches[i][1];
  if (!code.trim()) continue;
  new Function(code);
}
console.log('ALL_SCRIPTS_SYNTAX_VALID');
""")
            res = subprocess.run(["node", check_script_path], cwd=PEAKCUT_DIR, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Node.js syntax error: {res.stderr}")
            self.assertIn("ALL_SCRIPTS_SYNTAX_VALID", res.stdout)
        finally:
            if os.path.exists(check_script_path):
                os.remove(check_script_path)

if __name__ == "__main__":
    unittest.main()

