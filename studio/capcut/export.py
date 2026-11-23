"""Exports a PeakCut clip into a native CapCut Desktop Project (draft_info.json, draft_meta_info.json).

When exported, the clip opens directly inside CapCut Desktop on Windows with timeline tracks:
- Video Track (Rendered 9:16 vertical video)
- Caption / Subtitle Text Track (Word-level subtitle segments)
- Hook Title Text Track (Pop-in heading banner)
Allows users to apply CapCut's native filters, transitions, AI effects, stickers, and sound effects!
"""

import os
import sys
import json
import time
import shutil
import re
from pathlib import Path

# Add studio/capcut to sys.path so pyJianYingDraft imports its local modules
_CAPCUT_DIR = Path(__file__).resolve().parent
if str(_CAPCUT_DIR) not in sys.path:
    sys.path.insert(0, str(_CAPCUT_DIR))

try:
    import pyJianYingDraft as draft
except Exception as e:
    draft = None
    _import_err = str(e)


def get_capcut_drafts_dir() -> Path:
    """Finds the local CapCut Desktop drafts folder on Windows, or falls back to local data folder."""
    local_app = os.environ.get("LOCALAPPDATA", "")
    if local_app:
        candidate = Path(local_app) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        if candidate.exists():
            return candidate
    # Fallback to PeakCut data/capcut_drafts
    fallback = Path(__file__).resolve().parent.parent.parent / "data" / "capcut_drafts"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", str(text or "")).strip()
    return re.sub(r"[-\s]+", "_", s)[:32] or "clip"


def export_clip_to_capcut(job: dict, clip: dict, mp4_path: str = "") -> dict:
    """Exports the given clip into a native CapCut desktop draft folder.

    Returns dict with { ok, draft_path, draft_name, message }.
    """
    if draft is None:
        return {"ok": False, "error": f"CapCut draft engine not available: {_import_err}"}

    cid = clip.get("id") or "clip"
    title = clip.get("title") or clip.get("hook") or f"Clip {cid}"
    slug = _slug(title)
    dur = float(clip.get("dur") or clip.get("duration") or 30.0)
    dur_us = int(dur * 1_000_000)

    drafts_root = get_capcut_drafts_dir()
    draft_name = f"PeakCut_{cid}_{slug}"
    draft_dir = drafts_root / draft_name

    # If folder already exists, clear it for fresh export
    if draft_dir.exists():
        shutil.rmtree(draft_dir, ignore_errors=True)

    template_dir = _CAPCUT_DIR / "template"
    if not template_dir.exists():
        return {"ok": False, "error": f"CapCut template directory missing at {template_dir}"}

    shutil.copytree(template_dir, draft_dir)

    # Initialize 1080x1920 vertical canvas
    sf = draft.Script_file(1080, 1920)

    # 1. Main Video Track
    if mp4_path and os.path.exists(mp4_path):
        try:
            sf.add_track(draft.Track_type.video, "PeakCut Video")
            vmat = draft.Video_material("video", path=str(Path(mp4_path).resolve()), duration=dur_us, width=1080, height=1920)
            vseg = draft.Video_segment(vmat, draft.Timerange(0, dur_us))
            sf.add_segment(vseg, "PeakCut Video")
        except Exception as e:
            # Non-fatal: if video material registration has any issue, draft still creates
            pass

    # 2. Hook Title Track
    hook = clip.get("hook") or title
    if hook:
        try:
            sf.add_track(draft.Track_type.text, "Hook Title")
            hook_dur_us = min(dur_us, 3_500_000)
            hook_seg = draft.Text_segment(
                text=str(hook).upper(),
                timerange=draft.Timerange(0, hook_dur_us),
            )
            sf.add_segment(hook_seg, "Hook Title")
        except Exception:
            pass

    # 3. Caption Subtitles Track
    words = clip.get("words", [])
    if words and clip.get("captions", True):
        try:
            sf.add_track(draft.Track_type.text, "Captions")
            # Group into short phrases for natural subtitle chunks
            step = 3
            start_offset = float(clip.get("start", 0.0))
            is_absolute = bool(start_offset > 2.0 and words and float(words[0].get("s", 0.0)) >= start_offset - 2.0)
            
            for i in range(0, len(words), step):
                chunk = words[i:i + step]
                chunk_text = " ".join(re.sub(r"[^\w\s.,!?-]", "", w.get("w", "")).strip() for w in chunk).strip()
                if not chunk_text:
                    continue
                w_start = float(chunk[0].get("s", 0.0)) - (start_offset if is_absolute else 0.0)
                w_end = float(chunk[-1].get("e", w_start + 1.0)) - (start_offset if is_absolute else 0.0)
                w_start = max(0.0, w_start)
                w_end = min(dur, max(w_start + 0.3, w_end))
                
                s_us = int(w_start * 1_000_000)
                d_us = max(200_000, int((w_end - w_start) * 1_000_000))
                
                txt_seg = draft.Text_segment(
                    text=chunk_text.upper(),
                    timerange=draft.Timerange(s_us, d_us)
                )
                sf.add_segment(txt_seg, "Captions")
        except Exception:
            pass

    # Dump draft content (both draft_info.json and draft_content.json for CapCut 9.x+ compatibility)
    sf.dump(str(draft_dir / "draft_info.json"))
    try:
        sf.dump(str(draft_dir / "draft_content.json"))
    except Exception:
        shutil.copyfile(str(draft_dir / "draft_info.json"), str(draft_dir / "draft_content.json"))

    now_us = int(time.time() * 1_000_000)

    # Attach cover image if available
    cover_file = ""
    cover_candidates = [
        Path(mp4_path).with_suffix(".jpg") if mp4_path else None,
        Path(job.get("dir", "")) / "clips" / f"{cid}.jpg",
        Path(job.get("dir", "")) / f"{cid}.jpg",
    ]
    for cc in cover_candidates:
        if cc and cc.exists():
            try:
                shutil.copyfile(str(cc.resolve()), str(draft_dir / "draft_cover.jpg"))
                cover_file = str(draft_dir / "draft_cover.jpg")
                break
            except Exception:
                pass

    # Update metadata
    meta_path = draft_dir / "draft_meta_info.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            meta["draft_name"] = draft_name
            meta["tm_duration"] = dur_us
            meta["tm_draft_create"] = now_us
            meta["tm_draft_modified"] = now_us
            meta["draft_fold_path"] = str(draft_dir)
            meta["draft_root_path"] = str(drafts_root)
            if cover_file:
                meta["draft_cover"] = cover_file.replace("/", "\\")
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # Register in CapCut's root_meta_info.json so it immediately appears on CapCut's Home Projects screen
    registered = register_in_root_meta(drafts_root, draft_dir, draft_name, dur_us, now_us, cover_file)

    return {
        "ok": True,
        "draft_path": str(draft_dir),
        "draft_name": draft_name,
        "message": f"Successfully exported to CapCut Desktop project: {draft_name}",
        "in_capcut_folder": drafts_root.name == "com.lveditor.draft",
        "registered_in_home": registered,
    }


def register_in_root_meta(drafts_root: Path, draft_dir: Path, draft_name: str, dur_us: int, now_us: int, cover_path: str = "") -> bool:
    """Registers the project into CapCut's root_meta_info.json so CapCut displays it on the homepage."""
    root_meta_file = drafts_root / "root_meta_info.json"
    if not root_meta_file.exists():
        return False
    try:
        import uuid
        with open(root_meta_file, "r", encoding="utf-8") as f:
            root_data = json.load(f)
        store = root_data.get("all_draft_store", [])
        
        # Remove any existing draft with the same name or folder path to prevent duplicates
        norm_dir = str(draft_dir).replace("\\", "/")
        store = [d for d in store if d.get("draft_name") != draft_name and d.get("draft_fold_path") != norm_dir]
        
        draft_id = str(uuid.uuid4()).upper()
        entry = {
            "cloud_draft_cover": False,
            "cloud_draft_sync": False,
            "draft_cloud_last_action_download": False,
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cover": str(cover_path).replace("/", "\\") if cover_path else "",
            "draft_fold_path": norm_dir,
            "draft_id": draft_id,
            "draft_is_ai_shorts": False,
            "draft_is_cloud_temp_draft": False,
            "draft_is_infinite_canvas_draft": False,
            "draft_is_invisible": False,
            "draft_is_pippit_draft": False,
            "draft_is_web_article_video": False,
            "draft_json_file": str(draft_dir / "draft_content.json").replace("/", "\\"),
            "draft_name": draft_name,
            "draft_new_version": "",
            "draft_root_path": str(drafts_root).replace("/", "\\"),
            "draft_timeline_materials_size": 0,
            "draft_type": "",
            "draft_web_article_video_enter_from": "",
            "pippit_avatar_url": "",
            "pippit_extra_info": "",
            "pippit_id": "",
            "pippit_user_name": "",
            "streaming_edit_draft_ready": True,
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_entry_id": -1,
            "tm_draft_cloud_modified": 0,
            "tm_draft_cloud_parent_entry_id": -1,
            "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1,
            "tm_draft_create": now_us,
            "tm_draft_modified": now_us,
            "tm_draft_removed": 0,
            "tm_duration": dur_us
        }
        # Prepend to the top of the list so it is shown as the first project in CapCut
        store.insert(0, entry)
        root_data["all_draft_store"] = store
        with open(root_meta_file, "w", encoding="utf-8") as f:
            json.dump(root_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Warning: Failed to update root_meta_info.json: {e}")
        return False


def find_and_launch_capcut() -> bool:
    """Finds CapCut.exe on Windows and launches it so CapCut Desktop opens on screen."""
    import subprocess
    local_app = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", "")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
    
    candidates = [
        Path(local_app) / "CapCut" / "Apps" / "CapCut.exe",
        Path(program_files) / "CapCut" / "CapCut.exe",
        Path(program_files_x86) / "CapCut" / "CapCut.exe",
        Path(local_app) / "Programs" / "CapCut" / "CapCut.exe",
    ]
    if local_app and (Path(local_app) / "CapCut" / "Apps").exists():
        for f in (Path(local_app) / "CapCut" / "Apps").glob("**/CapCut.exe"):
            candidates.append(f)
            
    exe = next((p for p in candidates if p.exists()), None)
    if exe:
        try:
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            subprocess.Popen([str(exe.resolve())], creationflags=flags)
            return True
        except Exception as e:
            print("Failed to launch CapCut:", e)
    return False
