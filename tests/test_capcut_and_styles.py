"""Tests for CapCut Desktop project export, Bouncy & Hormozi caption styles, and Hook banner styles."""

import os
import sys
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio import render
from studio.capcut import export_clip_to_capcut, get_capcut_drafts_dir


def test_caption_styles():
    words = [
        {"w": "OhnePixel", "s": 0.5, "e": 1.1},
        {"w": "reacts", "s": 1.2, "e": 1.8},
        {"w": "to", "s": 1.9, "e": 2.1},
        {"w": "GTA", "s": 2.2, "e": 2.6},
        {"w": "VI", "s": 2.7, "e": 3.0},
    ]
    styles_to_test = ["bounce", "hormozi", "mrbeast", "karaoke", "hype", "clean"]
    for st in styles_to_test:
        ass = render.build_ass(
            words=words,
            start=0.0,
            end=5.0,
            hook="THAT PURPLE WHIP THOUGH",
            style_name=st,
            highlight=["VI", "GTA"],
            hook_y=1010,
            cap_y=1400,
            hook_style="purple_whip",
        )
        assert "[Script Info]" in ass, f"Failed on style {st}: missing Script Info"
        assert "Style: Cap" in ass, f"Failed on style {st}: missing Cap style"
        assert "Style: Hook" in ass, f"Failed on style {st}: missing Hook style"
        assert "Dialogue: 4" in ass, f"Failed on style {st}: missing Hook dialogue"
        assert "PURPLE WHIP" in ass, f"Failed on style {st}: missing hook text"
        print(f"PASS: caption style '{st}' generated valid ASS")


def test_hook_styles_and_custom_positioning():
    hooks_to_test = ["purple_whip", "cyber_red", "gold_luxury", "neon", "yellow", "pill"]
    for hk in hooks_to_test:
        ass = render.build_ass(
            words=[],
            start=0.0,
            end=4.0,
            hook="INSANE HIGHWAY DRIFT",
            style_name="bounce",
            highlight=[],
            hook_y=650,
            cap_y=1400,
            hook_style=hk,
            hook_w=850,
            hook_font_size=96,
        )
        assert "INSANE HIGHWAY DRIFT" in ass, f"Failed on hook style {hk}"
        assert "\\pos(" in ass, f"Failed on hook style {hk}: missing pos tag"
        print(f"PASS: hook style '{hk}' with custom hook_y/w generated valid ASS")


def test_capcut_desktop_export():
    clip = {
        "id": "clip_unit_test",
        "title": "GTA 6 Highway Drift",
        "dur": 8.5,
        "hook": "THAT PURPLE WHIP THOUGH",
        "captions": True,
        "words": [
            {"w": "Look", "s": 0.5, "e": 0.9},
            {"w": "at", "s": 1.0, "e": 1.2},
            {"w": "that", "s": 1.3, "e": 1.6},
            {"w": "car", "s": 1.7, "e": 2.2},
        ],
    }
    job = {"id": "job_unit_test", "dir": str(ROOT)}
    res = export_clip_to_capcut(job, clip)
    assert res.get("ok") is True, f"CapCut export returned not ok: {res}"
    draft_path = Path(res["draft_path"])
    assert draft_path.exists(), f"Draft folder was not created: {draft_path}"
    assert (draft_path / "draft_info.json").exists(), "Missing draft_info.json"
    assert (draft_path / "draft_meta_info.json").exists(), "Missing draft_meta_info.json"
    print(f"PASS: export_clip_to_capcut created draft at {draft_path}")
    # Clean up test draft
    shutil.rmtree(draft_path, ignore_errors=True)
    print("PASS: cleaned up test draft folder")


if __name__ == "__main__":
    test_caption_styles()
    test_hook_styles_and_custom_positioning()
    test_capcut_desktop_export()
    print("\nALL CAPCUT AND CAPTION/HOOK TESTS PASSED!")
