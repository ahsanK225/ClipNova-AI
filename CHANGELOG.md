# Changelog
All notable project changes are documented here.

## [2026-11-24] — CapCut Desktop Auto-Registration in root_meta_info.json & Process Auto-Launcher

### Fixed
- **CapCut Desktop Project Visibility (`studio/capcut/export.py`)**:
  - Resolved root cause of exported projects not appearing on CapCut Desktop's home screen.
  - Implemented `register_in_root_meta()` which prepends the exported draft to `all_draft_store` in `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\root_meta_info.json`.
  - Exported drafts now generate both `draft_content.json` (for CapCut 9.x+) and `draft_info.json`, along with `draft_cover.jpg` thumbnail.
  - As a result, CapCut Desktop instantly displays the project at the very top (Project #1) of its Projects screen.
- **CapCut Desktop Process Auto-Launcher (`studio/capcut/export.py`, `studio/server.py`)**:
  - Implemented `find_and_launch_capcut()` which locates `CapCut.exe` (located at `C:\Users\ahsan\AppData\Local\CapCut\Apps\CapCut.exe`) and launches/focuses the CapCut application automatically upon export.

## [2026-11-24] — Built-in 1-Click H.264 Video Converter Pipeline (100% Free OpenCut HEVC Fix)

### Added
- **Built-in H.264 Video Converter Pipeline (`studio/server.py`, `web/index.html`)**:
  - **Clip-Level H.264 Verification (`POST /api/jobs/{jid}/clips/{cid}/convert-h264`)**:
    - Automatically checks the video codec using `ffprobe`.
    - If already H.264 (true for all ClipNova clips), confirms instantly and highlights the MP4 in Windows Explorer.
    - If encoded in HEVC or any foreign codec, executes fast FFmpeg transcode (`-c:v libx264 -preset veryfast -crf 17 -pix_fmt yuv420p -c:a aac -movflags +faststart`) in ~5-10s and highlights the web-safe MP4 in Explorer.
  - **Universal File Converter Endpoint (`POST /api/tools/convert-file-h264`)**:
    - Converts ANY external video file on the user's computer (including raw streams, HEVC, H.265, MKV, MOV) into a standard, 100% free H.264 MP4 without requiring paid CapCut Pro.
  - **Frontend UI & 1-Click Launchers (`web/index.html`)**:
    - Upgraded `window.launchOpenCutNewTab` to auto-ensure H.264 before launching OpenCut Projects.
    - Added `window.convertAnyFileToH264` and prominent `🔄 Convert Video to H.264 (Fix HEVC Error)` action button in the Video Studio OpenCut drawer.
- **Automated Converter Test Suite (`tests/test_h264_converter.py`)**:
  - Tests validation, real FFmpeg video transcode to H.264, and frontend button presence (3/3 tests passed).

## [2026-11-24] — Viral Hook Banner Real-Time Stage Sync, Glowing Active Pills & Render Engine Fontsdir Fix

### Fixed
- **Render Engine `fontsdir` Filter Typo in `studio/render.py`**:
  - Resolved `fontsdir=f` typo on lines 842, 857, and 866 of `studio/render.py` where a broken f-string was passing non-existent folder `f` to FFmpeg.
  - Defined `FONTS_DIR = str((Path(__file__).resolve().parent / "fonts").resolve().as_posix()).replace(":", "\\:")` ensuring Windows drive colons are escaped (`F\:`) in FFmpeg filtergraphs.
  - Replaced all 3 instances with `fontsdir='{FONTS_DIR}'`, allowing ASS subtitles, hook banners, and font files (`Anton`, `Poppins`, `Archivo Black`) to load without font errors.
- **Viral Hook Pill Visual Highlight in `web/index.html`**:
  - Fixed issue where clicking `#2: LOST ALL HIS MONEY IN GTA 6 😭` or other pills did not show high-contrast active state.
  - Added `.hook-pill-btn.active-hook` CSS rule with `border: 2px solid #00F0FF !important; background: rgba(0,240,255,0.22) !important; box-shadow: 0 0 12px rgba(0,240,255,0.5) !important; color: #00F0FF !important; transform: scale(1.03);`.
  - Upgraded `pick_hook` event handler to perform case-insensitive, trimmed comparison and dynamically update all pills to toggle `.active-hook`.
  - Added background auto-persistence (`PUT /api/jobs/{jid}/clips/{cid}/text`) so selected hooks are immediately saved to the database.
- **Real-Time Video Stage Overlay Sync & Pop-In Animation**:
  - In `updateDlgLiveHookOverlay()`, ensured `overlay.style.opacity = "1"` and `overlay.style.transform = "translateX(-50%) scale(1)"` so the hook overlay is never stuck at opacity 0 if the preview video is paused past 3.8s.
  - Whenever a hook is selected or modified, `vid.currentTime` seeks to 0:00 and triggers `hookPopIn` animation on the stage player.
- **Dedicated 1-Click "Apply Hook & Re-make Video (~10s)" Button**:
  - Added a prominent cyan-gradient action button right inside the `Viral Hook Banner` accordion in `#clipdlg`.
  - Creators can preview live on player, then burn the selected hook banner permanently into the MP4 clip file with 1 click without having to scroll or navigate away.

### Added
- **Automated Verification Test Suite (`tests/test_hook_banner_sync.py`)**:
  - Tests `FONTS_DIR` presence, directory validity, font TTF files presence, drive colon escaping, ASS hook events generation, and frontend HTML hook banner classes.

## [2026-11-24] — Multi-Editor Architecture: Direct Built-in Studio Saved-Clip Loader, CapCut Desktop Auto-Project & OpenCut Projects Direct Link

### Added
- **Multi-Editor Architecture for Creator Ease (`web/index.html`, `studio/capcut/export.py`)**:
  - **Saved Clip Direct Loader in Built-in Video Studio (`openWebStudio`)**:
    - Implemented `window.openWebStudio(jid, cid)` in `web/index.html`.
    - Clicking `🎬 Edit in Built-in Studio (Clip Ready)` or the `🎬` icon on any clip card directly sets `window._studioClip = { jid, cid }` and navigates to the Video Studio tab.
    - The saved clip is immediately loaded into the 9:16 vertical player, timeline ruler, filters, VFX, and subtitle editor with zero manual drag-and-drop or project creation required ("wahi jo clip saved he ossi ko show kry").
  - **CapCut Desktop Auto-Project Generation (`export_capcut`)**:
    - Clicking `🚀 Auto-Create CapCut Project` automatically runs `export_clip_to_capcut()`, creating a complete CapCut draft inside `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\PeakCut_<clip_id>\`.
    - The project draft includes: Video track (9:16 vertical video), Subtitle track (word-level animated captions), and Hook track (viral heading banner).
    - Automatically opens the draft folder in Windows Explorer so creators can see the project and launch CapCut to find their clip already placed on the timeline ("khud hi projects ban jane chaye").
  - **OpenCut Projects Direct Link (`launchOpenCutNewTab`)**:
    - Updated `window.launchOpenCutNewTab` to point directly to `https://opencut.app/projects` instead of the marketing landing page `https://opencut.app`.
    - Automatically invokes `/open-folder` to highlight the `.mp4` file in Windows Explorer for seamless drag-and-drop.
  - **Clip Detail Modal (`#clipdlg`) 3 Distinct Quick Studio Buttons**:
    - `🎬 Edit in Built-in Studio (Clip Ready)`: Green/Cyan gradient button loading the saved clip directly into the in-app editor.
    - `🚀 Auto-Create CapCut Project`: Purple/Blue gradient button auto-generating the project draft in CapCut Desktop.
    - `🌐 OpenCut Web (Projects)`: Direct launcher to OpenCut projects dashboard.
  - **Studio Top Action Bar**:
    - Added `🚀 Auto-Create CapCut Project` alongside `🌐 OpenCut Projects` for 1-click external draft generation.

### Tests and Verification
- Executed unit test suite `tests/test_clip_clean_seo.py` and `tests/test_video_studio.py` (8/8 passed).
- Live HTTP verification on `http://127.0.0.1:8765/`:
  - `openWebStudio present`: True
  - `Edit in Built-in Studio button`: True
  - `Auto-Create CapCut Project button`: True
  - `OpenCut Projects link`: True
- Fresh server daemon running on port 8765.

## [2026-11-24] — Full OpenCut Web Editor Integration (New Tab Launch & Drag-and-Drop Bridge)

### Added
- **Full OpenCut Web Application Integration (`web/index.html`, `studio/server.py`)**:
  - Fully integrated OpenCut (`https://github.com/opencut-app/opencut` / `https://opencut.app` / `https://new.opencut.app`) to provide creators with complete CapCut-style web video editing capabilities (transitions, VFX, stickers, text overlays, multi-track timeline) in a new browser tab per user request.
  - Implemented `window.launchOpenCutNewTab(jid, cid)` in `web/index.html`:
    - Opens `https://opencut.app` directly in a fresh browser tab (`_blank`).
    - Automatically invokes backend `/api/jobs/{jid}/clips/{cid}/open-folder` which launches Windows Explorer with the rendered `.mp4` file pre-selected (`explorer.exe /select,"<filepath>"`).
    - Creators can effortlessly drag and drop the highlighted video file straight into OpenCut's web interface for instant editing.
  - **Video Studio OpenCut Drawer Tab**:
    - Replaced generic panels with a dedicated `🌐 OpenCut Web Studio` first tab in the Video Studio drawer.
    - Added prominent 1-click `🌐 Launch OpenCut Editor (New Tab)` button.
    - Added clear 4-step visual workflow card explaining the drag & drop process (1. Open in New Tab, 2. File Highlighted in Explorer, 3. Drag into OpenCut, 4. Export & Queue).
    - Provided direct clip action chips:
      - `📁 Open Clip Folder in Explorer`: highlights the clip `.mp4` on demand.
      - `📥 Direct Download MP4`: downloads the clip directly to local drive.
      - `🔗 Copy Clip Video URL`: copies the full HTTP streaming URL to clipboard for web import.
      - `🚀 Launch Next-Gen OpenCut Link`: launches `https://new.opencut.app` variant.
    - Included optional embedded studio iframe toggle (`toggleEmbedOpenCut`) for creators who prefer editing directly within the ClipNova dashboard.
  - **Top Action Bar & Clip Detail Modal Wiring**:
    - Video Studio top action bar updated with `<span>🌐</span> Open in OpenCut (New Tab)` button.
    - Clip Detail Modal (`#clipdlg`) Quick Studio Launcher row updated to wire `🌐 OpenCut Web Studio` directly to `launchOpenCutNewTab`.

### Tests and Verification
- Executed automated unit tests `tests/test_clip_clean_seo.py` and `tests/test_video_studio.py` (8/8 passed).
- Live HTTP verification on `http://127.0.0.1:8765/`:
  - `launchOpenCutNewTab`: True
  - `opencut.app link`: True
  - `Open in OpenCut button`: True
  - `save_seo_instant`: True
  - `dlg_hook_live_overlay`: True
  - `Viral Climax Teaser absent`: True
  - `Layout & Framing Studio absent`: True
- Verified live server daemon running on port 8765.

## [2026-11-24] — Clip Detail Modal Clean-Up, Live Hook Banner Overlay & Instant 1-Click SEO Persistence

### Added
- **Clip Detail Modal Clean-Up (`web/index.html`)**:
  - Removed `Viral Climax Teaser (Cold Open Hook)` accordion from `#clipdlg` as dedicated editors are now integrated (Item 1).
  - Removed `Layout & Framing Studio` and `Advanced Timing, Sync & Framing` accordions from `#clipdlg` (Item 2), keeping the dialog uncluttered and focused strictly on SEO, Title, Description, Tags, Hook, and YouTube Publishing.
  - Added Quick Studio Launcher row at top of `#clipdlg` (`🌐 OpenCut Web Studio`, `🚀 CapCut Desktop Bridge`, `🎨 Layout & Timing Studio`).
  - Added hidden inputs preserving clip layout, timing, delays, zoom, and framing parameters so that if a full re-render is triggered, parameters are safely retained.
- **Instant 1-Click SEO & Text Persistence without Re-render (`web/index.html`, `studio/jobs.py`, `studio/server.py`)**:
  - Added high-visibility prominent green action button `💾 Save SEO & Title (Instant - No Re-render)` in `#clipdlg` (Item 2).
  - Updated `jobs.save_post_text()` to accept and persist `hook`, `hook_style`, `seo_title`, `seo_tags`, `pinned_comment`, `captions`, `style`, `outro_cta`, `bgm_track`, `bgm_volume`, `bgm_offset` directly into memory and sidecar `{clip['id']}.json`.
  - Updated `postText()` in `web/index.html` to extract and serialize all SEO, title, tags, and hook attributes.
  - Instant < 5ms save with immediate green toast confirmation and zero FFmpeg re-rendering delay.
- **Live Viral Hook Banner Overlay (`web/index.html`, `studio/render.py`, `studio/jobs.py`)**:
  - Fixed Viral Hook Banner functionality (Item 3): added real-time `#dlg_hook_live_overlay` on top of the `#stage` video player.
  - Interactive `@keyframes hookPopIn` entrance with styling for all hook styles (`viral_yellow` with yellow punch word highlight, `viral_cyan`, `neon` dark gaming box, `purple_whip`, `yellow` box, `pill`, `cyber_red`, `gold_luxury`).
  - Added `🎣 Replay Hook` button to restart the video at 0:00 and replay the hook pop-in animation on demand.
  - Live synchronization hides overlay after 3.8s matching the rendered video.
  - Selecting hook pills in `#dlg_hook_pills`, changing hook banner style dropdown, or typing in the hook input immediately updates the video overlay in real-time.
  - Updated `pick_hook` and `pick_title` click handlers to synchronize in-memory clip state (`clp.hook = h`, `clp.title = t`, `clp.seo_title = seoT`).
  - Expanded `hook` length limit in `studio/jobs.py` from 60 to 120 characters and `hook_style` to 40 characters.

### Tests and Verification
- Created automated test suite `tests/test_clip_clean_seo.py` with 3 comprehensive tests (3/3 passed in 0.113s):
  - `test_save_post_text_persists_seo_and_hook_instantly`: verifies `save_post_text` saves title, description, SEO title, search tags, pinned comment, hook, and hook style without re-rendering.
  - `test_put_clip_text_endpoint`: verifies `PUT /api/jobs/{jid}/clips/{cid}/text` persists all fields and returns 200 OK.
  - `test_index_html_clean_modal_and_live_hook_overlay`: verifies teaser and layout cards are removed, `save_seo_instant` button is present, and live hook overlay functions exist.
- Regression suite `tests/test_video_studio.py` (5/5 passed in 0.083s).
- Live server test on `http://127.0.0.1:8765/` verified `HTTP 200 OK`, `save_seo_instant: True`, `dlg_hook_live_overlay: True`, `Viral Climax Teaser: False`, `Layout & Framing Studio: False`.

## [2026-11-24] — Dual-Engine Video Editing Suite: OpenCut Web Studio & CapCut Desktop Bridge

### Added
- **Dual-Engine Video Editing Suite (`web/index.html`, `studio/server.py`, `studio/capcut/export.py`)**:
  - **Clip Detail Modal (`#clipdlg`) Differentiated Launchers**:
    - `🌐 Open in OpenCut Web Studio`: Directly opens the in-browser multi-track editor with live timeline, filters, VFX, and audio drop sync.
    - `🚀 Open in CapCut Desktop`: 1-click export creating a native CapCut desktop draft project (`draft_info.json`) with video, word-level captions, and hook tracks already pre-mapped.
    - `📁 CapCut Project Folder`: Directly opens the local `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` folder in Windows Explorer.
  - **Video Studio CapCut Desktop Bridge Tab**:
    - Added dedicated `🚀 CapCut Desktop Bridge` tab in the studio drawer.
    - Shows detected local CapCut projects directory and provides 1-click export and folder access right from inside the studio workspace.
  - **Live Subtitle Vertical Positioning**:
    - In the Subtitles tab, added vertical position presets (`⬆️ Top`, `🎯 Center`, `⬇️ Bottom (Default)`).
    - Clicking any option instantly repositions the subtitle overlay on the 9:16 vertical video player in real time.

### Tests and Verification
- Unit test suite `tests/test_video_studio.py` (5/5 passed in 0.204s).
- Native CapCut generator test suite `tests/test_capcut_and_styles.py` (15/15 passed).
- Real browser visual verification via subagent `3d5e906e-d734-4748-b052-981d04c3470e` on `http://localhost:8765`:
  - Verified clip detail modal with both `🌐 Open in OpenCut Web Studio` and `🚀 Open in CapCut Desktop` buttons.
  - Verified Video Studio drawer's `🚀 CapCut Desktop Bridge` panel and tested export trigger.
  - Verified subtitle positioning (`🎯 Center`) repositioning overlay to center.
  - Visual evidence artifacts saved: `opencut_and_capcut_bridge_verified.png` and `capcut_desktop_bridge_panel.png`.

## [2026-11-23] — In-Browser Web Video Studio (CapCut / OpenCut Style Multi-Track Editor)

### Added
- **In-Browser Web Video Studio Workspace (`web/index.html`)**:
  - **Dedicated Navigation Tab (`🎬 Video Studio`)**: Added `["studio", "Video Studio", "film", 0]` to creator tabs in `drawShell()`, supporting deep linking via `/app/creators/<cid>/studio`.
  - **Launch Action Points**: Added `🎬 Open in Web Studio` button to clip cards (`clipHtml`) and `#clipdlg` Clip Editor modal.
  - **Clip Selection Grid**: When entering the Studio without an active clip, displays a visual grid of all finished clips for the creator with thumbnails, timecodes, and direct `🎬 Open in Studio` launch buttons.
  - **9:16 Vertical Video Viewport**: Studio workspace with 9:16 aspect ratio player, real-time CSS color grading filters, transport controls (`⏪ -1s`, `▶️ Play/Pause`, `⏩ +1s`), and playback speed selectors (`0.75x`, `1.0x`, `1.25x`, `1.5x`).
  - **Live Dynamic Subtitle Overlay**: Active spoken word dynamically highlighted in real-time in sync with playback.
  - **5-Tab Studio Tool Drawer**:
    1. `🎨 Visual Filters`: Cards for Normal, Vibrant Viral, Cinematic Film, Moody Dark, Cyberpunk, and Classic B&W with instantaneous CSS live preview.
    2. `⚡ Viral VFX Overlays`: Real-time interactive animations for Flash White, Screen Shake, Glitch RGB, and Zoom Punch with `⚡ Test Now` and `➕ Add at Playhead` keyframe placement.
    3. `🎵 Audio & BGM Mix`: Track selection, volume slider, draggable start offset scrubber, and viral quick jumps (`0:00`, `+10s`, `⚡ 0:15 Drop`, `+30s`).
    4. `💬 Subtitles & Captions`: Interactive transcript word blocks with timestamps; clicking any word jumps playhead to that exact word; editable text box allows fixing speech-to-text typos in place.
    5. `🎭 Layout & Facecam`: Layout switcher for Split vertical, Fullscreen gameplay, and Custom presets.
  - **CapCut-Style Multi-Track Timeline (`web/index.html`)**:
    - Interactive Time Ruler with 5-second tick markers and click-to-seek functionality.
    - Draggable Red/Cyan Playhead Needle extending down across all tracks that tracks playback progress accurately.
    - Track 1 (💬 Subtitles): Individual word blocks with start/end positions, active glow on spoken word, and click-to-seek.
    - Track 2 (🎬 Video): Video clip bar with visual split cut slice marks.
    - Track 3 (🎭 Facecam): Facecam PiP placement indicator.
    - Track 4 (🎵 Audio): Background audio track with volume and offset trim badges.
    - Track 5 (⚡ VFX): Visual event pills representing placed VFX moments.
- **Backend Studio Project & Export APIs (`studio/server.py`, `studio/jobs.py`, `studio/render.py`)**:
  - `GET /api/jobs/{jid}/clips/{cid}/studio-project`: Returns full multi-track project contract (word timestamps, filter presets, VFX presets, audio tracks, and stickers).
  - `POST /api/jobs/{jid}/clips/{cid}/studio-export`: Saves cuts, filters, speed, audio trim, word edits, and triggers re-render via `jobs.request_render()`.
  - **1-Click Auto-Queue to YouTube**: `🚀 Save & Queue to YouTube (USA Peak)` renders the video and immediately enqueues it into the USA Publishing Calendar at the optimal peak velocity slot via `posting.enqueue()`.
  - **FFmpeg Filtergraph Color Grading (`studio/render.py`)**: Added `VIDEO_FILTERS` mapping (`vibrant`, `cinematic`, `moody`, `cyberpunk`, `bw`) and chained video filters into FFmpeg output.

### Tests and Verification
- Created comprehensive test suite `tests/test_video_studio.py` (5/5 passed in 0.239s):
  - Verified `GET /api/jobs/{jid}/clips/{cid}/studio-project` returns valid schema, tracks, filters, and VFX.
  - Verified `POST /api/jobs/{jid}/clips/{cid}/studio-export` updates clip metadata and triggers re-render.
  - Verified auto-scheduling with `schedule_now=True` calls `posting.enqueue()`.
  - Verified FFmpeg `VIDEO_FILTERS` dictionary and filter syntax.
  - Verified frontend `web/index.html` markup, tabs, styles, and action buttons.
- Real browser visual verification via subagent `102fb32c-382c-404a-b0ac-b20b6e4ba4ab` on `http://localhost:8765`:
  - Verified 5 top tabs in creator view (`Clips`, `Video Studio`, `Publishing Calendar`, `Setup`, `Activity`).
  - Navigated to `Video Studio` tab, opened OhnePixel clip, verified 9:16 vertical player, vibrant filter application, screen shake test, and multi-track timeline with interactive playhead scrubbing at 15s.
  - Visual evidence artifacts saved: `video_studio_timeline_verified.png` and `video_studio_timeline_fullpage.png`.

## [2026-11-23] — CapCut-Style Audio Start Trim & Video Editor (OpenCut) Architecture

### Added
- **CapCut-Style Sound Trim & Audio Start Offset (`web/index.html`, `studio/render.py`, `studio/jobs.py`)**:
  - **Interactive Range Scrubber (`#dlg_bgm_offset_slider`)**: When any background track or user-uploaded audio is selected in the Clip Editor (`#clipdlg`), an interactive sound trim box (`#dlg_bgm_trim_box`) appears allowing creators to choose the exact section of the audio track that plays during the clip.
  - **Live Audio Sync & Auditioning**:
    - Moving the scrubber immediately updates the audio playhead (`audio.currentTime = (video.currentTime + offset) % duration`).
    - Added instant audition button `🎧 Listen from here` to preview the trimmed sound for 3.5 seconds.
    - Added viral quick jump buttons: `⏮️ 0:00 (Start)`, `+10s`, `⚡ 0:15 (Drop)`, `+30s`.
  - **FFmpeg Seek Mixing (`studio/render.py`)**:
    - Passed `-ss <bgm_offset>` before `-stream_loop -1 -i <bgm_path>`.
    - Applied `asetpts=PTS-STARTPTS` filter to reset audio PTS to 0.0s before mixing with the primary video voice track.
  - **Persistence in Job Data (`studio/jobs.py`)**:
    - Added `clip["bgm_offset"]` validation and storage in `update_clip`.
- **Open-Source Video Editor (OpenCut / OpenReel) Evaluation & Architecture (`SYSTEM_DESIGN.md`)**:
  - Researched and evaluated `OpenCut-app/OpenCut` (React + Rust/WASM) and `Augani/openreel-video` (React + Zustand + WebCodecs) for browser-based multi-track non-linear video editing.
  - Documented complete architecture for bridging ClipNova AI clips with both native CapCut Desktop drafts (`studio/capcut/export.py`) and embedded web timeline editors.

### Tests and Verification
- Unit test suite `tests/test_bgm_and_meme_sounds.py`: 6/6 tests passed in 2.64s.
  - Verified `bgm_offset` persistence in `jobs.request_render`.
  - Verified FFmpeg rendering with audio seek offset creating valid mixed MP4.
  - Verified HTML markup for trim box, slider, and buttons.
- Real browser subagent visual verification on `http://127.0.0.1:8765`:
  - Verified `#dlg_bgm_trim_box` appears when a track is selected and hides when "None" is active.
  - Clicked `⚡ 0:15 (Drop)`, successfully updating slider to 15 and display to `0:15` out of `0:24`.
  - Saved visual evidence artifact `sound_trim_offset_verified.png`.

## [2026-11-23] — YouTube Remote Video Deletion, Post View Counts & Setup Calendar Purge

### Fixed
- **Post Cancellation & Cloud Schedule Exception (`studio/posting.py`, `studio/server.py`)**:
  - Resolved `Cancel failed: Only posts that are still waiting can be cancelled.` error when canceling already uploaded or cloud-scheduled YouTube Shorts.
  - `posting.cancel(pid)` and `posting.delete_post(pid)` now gracefully handle posts with status `"posted"` and `remote_id`, delegating to `accounts.youtube_delete()` to permanently delete the video from YouTube and cancel associated community posts.
  - In `studio/server.py`, `get_creator_calendar()` strictly excludes posts with status `"cancelled"` or `"deleted"` from the scheduled queue.
- **Calendar Removed from Setup Tab (`web/index.html`)**:
  - Completely purged `#setup_creator_calendar_card` and `renderCreatorCalendarCard` from Creator Setup (`#cform`).
  - Creator Setup is now focused strictly on creator settings (stream links, language, trigger words, custom framing presets, and posting configurations) without vertical calendar bloat. The full Publishing Calendar remains housed in its dedicated top tab (`Publishing Calendar`).

### Added
- **YouTube Remote Video Deletion API (`studio/accounts.py`, `studio/posting.py`, `studio/server.py`)**:
  - Implemented `accounts.youtube_delete(acc, video_id)` invoking `DELETE https://www.googleapis.com/youtube/v3/videos?id={video_id}` via YouTube Data API v3.
  - Added backend endpoints `POST /api/posts/{pid}/delete` and `DELETE /api/posts/{pid}`.
  - In `web/index.html`, added interactive `🗑️ Delete from YouTube` button with native confirmation prompt for all uploaded/cloud-scheduled Shorts.
- **Live YouTube View Counts on Calendar & Queue Cards (`web/index.html`, `studio/analytics.py`)**:
  - Both Timeline slot cards and Queued videos tab display real-time YouTube view counts: `👁️ <N> views` and `✓ On YouTube` badges.
  - Upgraded `analytics.sync_youtube_stats(cid)` to auto-detect the creator's connected YouTube channel and query `accounts.youtube_views()` to update `p["views"]` across all uploaded clips.
- **Unit & Integration Test Suite (`tests/test_post_delete_and_views.py`)**:
  - Added 4 automated tests verifying `accounts.youtube_delete`, `posting.delete_post`, `posting.cancel` delegation, and cancelled posts exclusion in `get_creator_calendar()`.

### Tests and Verification
- Executed unit test suite `tests/test_post_delete_and_views.py`: 4/4 tests passed (100%).
- Executed full calendar and trigger test suites (25 tests across 4 suites): 25/25 tests passed in 2.16s.
- Real browser subagent visual verification on `http://127.0.0.1:8765`:
  - Verified Setup tab (`artifacts/setup_tab_clean_no_calendar.png`) is completely clean of calendar cards.
  - Verified Publishing Calendar Queue tab (`artifacts/calendar_views_and_delete_youtube_verified.png`) displays `👁️ 0 views`, `✓ On YouTube`, and `🗑️ Delete from YouTube` button.
  - Verified `🔄 Sync Views` button spins and triggers live sync.

## [2026-11-23] — Creator-Scoped Trigger Words Isolation & Explicit UI Safeguards

### Fixed
- **Restored Default Trigger Words for xQc (`data/users/u_local/creators/xqc/creator.json`)**:
  - Restored full `MASTER_TRIGGER_WORDS` (628 characters) for `xqc` following previous testing runs.
  - Confirmed and verified that all creators (`ishowspeed`, `ducky-reloaded`, `jenkins-clips`, `mrbeast`) retain their full trigger keywords intact, while `ohnepixel` maintains its user-requested Pure AI mode (empty trigger words).

### Added
- **Explicit Creator-Isolated Trigger Words UI (`web/index.html`)**:
  - Replaced ambiguous generic label and buttons with explicit creator-branded controls in `#cform`:
    - Header: `Always clip the last 30 seconds when someone says on <Creator>'s stream:`
    - Pill Badge: `👤 Isolated to <Creator>`
    - Contextual Explanatory Subtext: `🔒 Per-Creator Isolation: Changes here apply strictly to <Creator> and will never affect other creators. Leave empty to disable keyword triggers (pure AI-only scoring).`
    - Action Buttons: `🗑️ Clear for <Creator> (Pure AI)` and `🔄 Restore Defaults for <Creator>`.
    - Live Toasts: Clearly state that actions and clears apply strictly to the active creator and leave all other creators untouched.
- **Creator Isolation Verification Tests (`tests/test_creators_trigger_words.py`)**:
  - Added `test_06_creator_trigger_words_isolation` asserting that creating multiple creators, clearing trigger words for Creator A, or modifying them to custom phrases leaves Creator B completely untouched with its full default `MASTER_TRIGGER_WORDS` intact across in-memory cache, disk persistence, and cache eviction cycles.

### Tests and Verification
- Executed unit test suite `tests/test_creators_trigger_words.py`: 7/7 tests passed cleanly (100% success).
- Real browser subagent visual inspection on `http://127.0.0.1:8765`:
  - Verified `xQc` Setup displays full trigger words with `👤 Isolated to xQc` badge and action buttons.
  - Verified `ohnepixel` Setup displays empty trigger words with `👤 Isolated to ohnepixel` badge and action buttons.
  - Verification screenshots captured: `artifacts/xqc_trigger_words_verified.png` and `artifacts/ohnepixel_trigger_words_isolated.png`.

## [2026-11-23] — Option A Autonomous Hourly Views Velocity Tracker & Hybrid Algorithm Priming Publishing Engine

### Added
- **Autonomous Hourly Views Delta Tracker (Option A) (`studio/analytics.py`, `studio/server.py`)**:
  - Automatically queries YouTube Data API v3 (`videos.list(part="statistics,snippet")`) to record periodic snapshots of view counts across recently uploaded Shorts.
  - Computes hourly view velocity ($\Delta \text{views}_t = \text{views}_t - \text{views}_{t-1}$) attributed to the corresponding PKT 24-hour clock buckets (00:00 to 23:00 PKT).
  - Maintains 7-day rolling hourly velocity distribution and 48-hour views metrics.
- **Hybrid Algorithm Priming Engine (`studio/analytics.py`, `studio/calendar.py`)**:
  - Automatically discovers the channel's top 3 peak audience activity hours using circular non-maximum suppression (enforcing $\ge 4.5-5\text{h}$ spacing and the 3 videos/day ceiling).
  - Offsets publishing time by $1.0 - 2.0\text{h}$ (default 1.5h / 90 minutes) *prior* to peak traffic surge, allowing YouTube Shorts recommendation engine to index, evaluate audio fingerprint, and seed impression buckets before viewer flood arrives.
  - Formats slots with rich metadata: `is_analytics_driven`, `peak_target_pkt`, and glowing badges `⚡ Primed 90m before audience peak`.
- **Interactive 24-Hour Velocity Histogram & Live Switcher UI (`web/index.html`)**:
  - Renders a 24-hour visual bar chart modeled after YouTube Studio 48-hour views analytics, highlighting detected peak hours with glowing cyan/purple gradient bars.
  - Quick-switch buttons: `⚡ Auto (Analytics)`, `🇺🇸 USA Standard`, and live `🔄 Sync Views` button.
  - In Creator Settings (`#cform`), added dedicated card `📅 Dynamic YouTube Scheduling & Velocity Optimization` to configure engine mode, priming lead warmup (1h, 1.5h, 2h), and minimum video spacing (4h, 4.5h, 5h, 6h).
- **Backend API Endpoints (`studio/server.py`)**:
  - `GET /api/creators/{cid}/analytics/velocity`: returns 24-hour velocity curve, active peaks, and priming parameters.
  - `POST /api/creators/{cid}/analytics/sync`: polls YouTube Data API v3 for latest view stats and updates velocity curve.
  - `POST /api/creators/{cid}/analytics/settings`: updates scheduling mode, priming offset, and minimum gap.

### Tests and Verification
- Comprehensive test suite in `tests/test_analytics_calendar.py` passed 6/6 tests covering peak detection with non-maximum suppression, algorithm priming offset calculation, hourly view delta snapshots, settings persistence, dynamic slot assignment, and server API endpoints.
- Regression test suite `tests/test_usa_publishing_calendar.py` passed 8/8 tests.
- Total 14/14 tests passed in 0.157s.
- Background server daemon verified healthy on `http://127.0.0.1:8765`.

## [2026-11-23] — Interactive Calendar Slot Video Picker, Refresh Route Persistence, Squeezed Meters & Collapsible Clip Editor Accordions

### Added
- **Interactive Calendar Slot Video Picker Modal (`#cal_picker_dlg`) (`web/index.html`, `studio/server.py`)**:
  - Clicking `+ Queue Next Video` or clicking any open slot in the USA Publishing Calendar opens an interactive video picker modal window `#cal_picker_dlg`.
  - Lists all ready/rendered clips for the active creator via `GET /api/creators/{cid}/ready-clips` with 9:16 vertical cover thumbnails, duration, AI energy score, and status.
  - Features 1-click `⚡ Schedule to this Slot` button that triggers `POST /api/calendar/schedule-clip`, enqueuing the video upload at that slot timestamp and pairing a Community Post (+30m).
  - Slot card instantly transitions to `🎬 SCHEDULED` displaying thumbnail, title, USA viewing windows, and paired community post.
- **Collapsible Cards in Clip Editor (`#clipdlg`) (`web/index.html`)**:
  - Converted `🎣 Viral Hook Banner`, `🎬 Viral Climax Teaser (Cold Open Hook)`, `🎵 Background Music & Meme Sounds`, and `🎨 Layout & Framing Studio` into native collapsible `<details class="card">` accordions with rotating chevron indicators (`▾`), matching `⚙️ Advanced Timing, Sync & Framing`.
  - Cards can be toggled open or closed with smooth CSS transitions without cluttering the screen.

### Changed
- **Squeezed Sparkline Meters & Expansive AI Decision Space (`web/index.html`)**:
  - Updated live stream bottom `.meters` grid from equal-width `repeat(auto-fit, minmax(280px, 1fr))` to `minmax(130px, 170px) minmax(130px, 170px) minmax(360px, 1fr)`.
  - Squeezes `Loudness` and `Chat / sec` sparklines into compact cards and grants `Latest AI Decisions` the expanded width (`1fr` / 600px+) so event headlines and natural-language explanations are fully readable without truncation.
- **Route & Tab Persistence Across Page Refresh (`web/index.html`)**:
  - Updated route parsing regex in `fromPath` to include `calendar` (`(?:\/(setup|activity|clips|calendar))?`), preventing calendar URLs from falling back to overview.
  - Guarded `go` against premature redirection to `overview` when `S.creators` is not yet loaded.
  - Stored and restored both `view` and `ctab` from URL pathname and `localStorage`, ensuring page refresh (F5) directly restores the creator view and exact subtab.

### Fixed
- **Calendar Scheduled Videos Recognition (`studio/server.py`, `studio/calendar.py`, `studio/posting.py`)**:
  - Fixed scheduled video filtering in `get_creator_calendar` so future YouTube uploaded posts marked `"posted"` or `status in posting.OPEN` with future `scheduled_at`/`due_at` are included in `scheduled_posts`.
  - Added `target_ts` parameter in `posting.enqueue` for direct slot scheduling and `is_scheduled` metadata tracking.

### Tests and Verification
- Unit and regression test suite in `tests/test_usa_publishing_calendar.py`, `tests/test_creators_trigger_words.py`, `tests/test_trigger_timeline.py`, and `tests/test_ai_verdicts_clean_ui.py` passed (25/25 tests OK in 0.64s).
- Full AST validation of JavaScript in `web/index.html` executed with Node.js with zero errors.
- Live HTTP test against `http://127.0.0.1:8765/api/calendar/schedule-clip` returned `200 OK` with 2 posts created.
- Server daemon verified healthy on port 8765.

## [2026-11-23] — Strict Live Pure AI Mode Bypass & Reaction Phrase Scoping

### Fixed
- **Bypassed Unintended Level 1 Reaction Phrase Triggers when Trigger Words Cleared (`studio/live.py`)**:
  - Fixed bug where `Session._triggers()` executed `ohnepixel.classify_transcript()` outside of `has_triggers` check. Even when a user deleted all trigger words (`"trigger_words": ""`), speaking any phrase in `STRONG_REACTION_PHRASES` automatically created a clip with `source: "trigger"`.
  - Added strict guard at the entry of `Session._triggers()`: if `trigger_words` is empty or whitespace, the method returns immediately, completely bypassing all keyword triggers, phrase matchers, and built-in "clip that" commands.
- **Creator-Scoped OhnePixel Level 1 Auto-Triggers (`studio/live.py`)**:
  - Scoped `ohnepixel.classify_transcript()` Level 1 reaction phrases exclusively to OhnePixel channels (`is_ohnepixel`). Streams from other creators (such as xQc, Speed, or custom streamers) no longer falsely trigger on CS2 reaction phrases.
- **Removed Casual Conversational Fillers from Level 1 Strong Reaction Phrases (`studio/ohnepixel.py`)**:
  - Removed `"huh"`, `"come on bro"`, `"why bro"`, `"wait wait wait"`, `"hold on"`, and `"no no no"` from `STRONG_REACTION_PHRASES`. These casual phrases are common in normal dialogue and no longer trigger auto-clips directly without multimodal AI evidence.
- **Shared Timeline Roll Variables (`studio/live.py`)**:
  - Positioned `pre_roll, post_roll = 12.0, 28.0` before creator branch so creator custom trigger phrases have access to timeline variables without `UnboundLocalError`.

### Tests and Verification
- Python test script executed reproducing the exact issue with `"come on bro"` and `"huh"` on xQc with empty `trigger_words` (1 manual item created before fix, 0 manual items created after fix).
- All 32 automated tests in `tests/test_creators_trigger_words.py`, `tests/test_trigger_timeline.py`, `tests/test_ohnepixel_engine.py`, and `tests/test_usa_publishing_calendar.py` passed (100% OK in 1.48s).
- Additional regression tests in `test_live.py`, `test_games.py`, `test_delete.py`, and `test_post_text.py` passed.
- Server daemon restarted on port 8765; health check `http://127.0.0.1:8765/healthz` returned `HTTP 200 {"ok":true}`.

## [2026-11-23] — Cyber-Glass USA Content Calendar, Day Timeline & Micro-Animations

### Added
- **World-Class Cyber-Dark Glassmorphic Calendar Theme (`web/index.html`)**:
  - Replaced rough dashed borders with sleek production SaaS glassmorphic cards (`backdrop-filter: blur(20px)`, subtle inset rim highlight, layered ambient depth shadows).
  - High-contrast Inter-aligned typography with distinct electric cyan (`#00F0FF`), emerald (`#10B981`), and royal purple (`#A855F7`) semantic accents.
- **Micro-Animations & Smooth Interactions (`web/index.html`)**:
  - Added `@keyframes calPulse` creating a realistic pulsing radar wave on the green engine status dot (`● Auto Engine Active · USA Peaks`).
  - Added `@keyframes calFlowArrow` with gentle shimmer and slide motion on pipeline flow arrows.
  - Added `@keyframes calFadeInUp` for smooth fade-in entry when switching views.
  - Added smooth card hover lift and glowing rim light (`transform: translateY(-3px); box-shadow: 0 16px 36px -8px rgba(0,240,255,0.22)`).
- **Structured Day Timeline Grouping (`web/index.html`)**:
  - Slots are now grouped cleanly by day (`⚡ Today`, `🗓️ Tomorrow`, `🗓️ Day 3`) with daily usage counters (e.g. `0/3 slots claimed`).
  - Each slot clearly displays its PKT publishing time, USA target audience window (Morning Drive, Afternoon Peak, Prime Evening in EST/PST), and connected Community Post (+30m).
- **Interactive Multi-View Switcher (`web/index.html`)**:
  - Integrated 3 view modes: `📅 Day Timeline` (default structured calendar), `⚡ USA Slots` (sequential windows list), and `🎬 Queued Videos` (active video cards).
  - Toggles dynamically without full-page reloads.
- **Segmented Daily Capacity Meter (`web/index.html`)**:
  - 3-dot visual indicator in topbar reflecting the strict daily limit (Slots 1, 2, 3) with filled vs open states.
- **Automated Publishing Pipeline Infographic (`web/index.html`)**:
  - Replaced plain empty state with a sleek visual pipeline: `[ ✂️ Clip Video ] ➔ [ 📅 3/Day Limit ] ➔ [ 🇺🇸 USA Peaks ] ➔ [ 📢 Community (+30m) ] ➔ [ 🔄 Auto-Roll ]`.

### Tests and Verification
- Node.js full AST validation: **100% CLEAN** (466,524 characters inline JavaScript).
- Automated tests in `tests/test_usa_publishing_calendar.py` and `tests/test_creators_trigger_words.py`: **13/13 PASSED** in 1.475s.
- Verified visual quality in browser subagent.

## [2026-11-23] — Creator Trigger Keywords Deletion & Pure AI Clipping Support

### Added
- **Pure AI Livestream Clipping Mode**:
  - Creators can now clear the trigger words textarea to test or run pure autonomous multimodal AI clipping without relying on spoken keywords or phrase triggers.
  - When `trigger_words` is empty, both built-in "clip that/karo" detection and custom phrase detection are bypassed in `studio/live.py`, letting multimodal visual inspection, loudness spikes, chat velocity, and Gemini scoring decide highlights.
- **Setup UI Quick Action Buttons (`web/index.html`)**:
  - Added `🗑️ Clear All (AI Only)` button: 1-click clears all trigger words and enables unscheduled testing of pure AI clipping.
  - Added `🔄 Restore Defaults` button: 1-click restores the full 39 master multilingual trigger phrases.
  - Added explanatory hint: "Leave completely empty to disable keyword triggers (pure AI intelligent scoring only)."

### Fixed
- **Trigger Keywords Deletion & Short Phrases Bug (`studio/creators.py`)**:
  - Fixed aggressive validation in `_fix()` where `not tw or len(tw) < 30` forcefully resurrected `MASTER_TRIGGER_WORDS` whenever a user deleted keywords or set a short phrase.
  - User can now save an empty string `""` or short custom trigger phrases (e.g. `"clip that, insane"`), and the value is permanently preserved across in-memory cache, JSON disk files, and page reloads.

### Tests and Verification
- Created automated test suite `tests/test_creators_trigger_words.py`:
  - `test_01_default_trigger_words_assigned_on_creation`: PASSED.
  - `test_02_empty_trigger_words_persists_on_update_and_reload`: PASSED.
  - `test_03_short_custom_trigger_words_persists`: PASSED.
  - `test_04_live_session_bypasses_triggers_when_empty`: PASSED.
- Tested live HTTP API: `PUT /api/creators/ohnepixel` with empty string verified returning `''` and persisting across `GET /api/creators`.
- Verified regression suite `tests/test_trigger_timeline.py` and `tests/test_usa_publishing_calendar.py`: **14/14 PASSED**.
- Node.js full AST verification: **PASS** (455,196 chars inline JavaScript verified clean).

## [2026-11-23] — Creator Content Calendar & Setup Schedule View

### Added
- **Dedicated 'Publishing Calendar' Tab in Creator View (`web/index.html`)**:
  - Added `["calendar", "Publishing Calendar", "calendar", nSched]` in creator navigation bar (`#utabs`) with dynamic badge counter showing total scheduled videos.
  - Clicking the tab loads a full-width immersive content calendar view (`#creator_calendar_view`) rendered via `drawCreatorCalendarTab()`.
- **Persistent Publishing Calendar Card in Creator Setup (`web/index.html`)**:
  - Embedded the USA Content Calendar card directly at the very top of the Creator Setup form (`#cform`) right before "Their stream" settings per user request.
  - Automatically loads and displays the creator's schedule when navigating to Setup.
- **Backend Creator Calendar API (`studio/server.py`)**:
  - Added `GET /api/creators/{cid}/calendar` endpoint returning the creator's active scheduled videos, paired Community Posts (+30m), recent uploads, and the next 9 available USA publishing slots with PKT and US Eastern/Pacific times.
- **Rich Calendar Schedule Card UI (`web/index.html`)**:
  - Day-by-day timeline cards showing:
    - Exact PKT upload time (`06:00 PM`, `12:00 AM`, `06:00 AM PKT`)
    - Exact US time with DST (`08:00 AM EST / 05:00 AM PST`)
    - Video cover thumbnail preview and duration badge
    - Account badge and title
    - Paired Community Post time (+30m offset) with 1-click `📋 Copy` button
    - Action buttons: `[▶ View Clip]` to launch the clip modal, and `[✕ Cancel]` to cancel the scheduled post
    - Visual indicators for next available publishing slots and today's slot usage (e.g. `Today: 1/3 Used (2 Left)`).
  - Added `"calendar"` SVG icon in icon dictionary `I`.

### Tests and Verification
- Executed `tests/test_usa_publishing_calendar.py`: **8/8 PASSED** in 1.224s.
- Verified `GET /api/creators/ishowspeed/calendar` returning HTTP 200 with 5 scheduled posts and 9 upcoming slots.
- Node.js AST parser: `web/index.html syntax 100% clean!`.
- Server running on port 8765 with `/healthz` returning 200 OK.


## [2026-11-23] — Automatic USA-Focused Publishing Calendar & Community Post Scheduling Engine

### Added
- **USA-Focused Automatic Publishing Calendar Engine (`studio/calendar.py`)**:
  - Engineered timezone-aware publishing calendar using Python standard library `zoneinfo` supporting `Asia/Karachi` (PKT, UTC+5), `America/New_York` (US Eastern), and `America/Los_Angeles` (US Pacific).
  - Enforces strict daily video limit: **maximum 3 videos per PKT calendar day cycle**. If 3 videos are already scheduled or slots have passed, subsequent clips automatically roll forward to tomorrow and future days without manual date picking.
  - Implemented preferred USA-optimized publishing slots per PKT calendar day:
    - **Slot 1: 6:00 PM PKT** (08:00 AM US Eastern / 05:00 AM US Pacific)
    - **Slot 2: 12:00 AM PKT midnight** (02:00 PM US Eastern / 11:00 AM US Pacific)
    - **Slot 3: 06:00 AM PKT morning** (08:00 PM US Eastern / 05:00 PM US Pacific)
  - Preferred slot order: `6:00 PM -> 12:00 AM -> 6:00 AM`.
  - Maintained minimum **5–6 hours gap** between consecutive video publications (6h and 12h default spacing).
  - Multi-day auto-roll queue tested and verified across 8 ready videos:
    - Day 1: Video 1 (6:00 PM), Video 2 (12:00 AM), Video 3 (6:00 AM)
    - Day 2: Video 4 (6:00 PM), Video 5 (12:00 AM), Video 6 (6:00 AM)
    - Day 3: Video 7 (6:00 PM), Video 8 (12:00 AM)
  - Timezone and US Daylight Saving Time (DST) dynamically resolved for both summer (EDT) and winter (EST).

- **Paired YouTube Community Post (+30m) Automation (`studio/posting.py`, `studio/accounts.py`)**:
  - For every video scheduled on YouTube, automatically creates and schedules a paired Community Post set for **exactly 30 minutes after the video goes live** (+30m offset).
  - Community Posts do NOT count toward the 3-video daily publishing limit.
  - Generates high-CTR formatted text payload matching video SEO:
    - Viral title with fire emoji (`🔥 [Title]`)
    - Clean description (duplicate `#Shorts` stripped)
    - Direct Short link (`▶️ Watch the full Short here: https://youtube.com/shorts/...`)
    - Discussion prompt (`💬 Community Discussion: [Pinned Comment]`)
    - Viral hashtags
  - Automatically updates paired Community Post with the real Short URL upon YouTube upload completion.
  - Implemented `accounts.youtube_post_community` with InnerTube backstage integration and staging fallback.
  - Updated single-channel exclusivity logic so video uploads do NOT cancel their paired community posts.

- **REST API Endpoints (`studio/server.py`)**:
  - `GET /api/calendar/slots`: Returns upcoming available slots with PKT and US Eastern/Pacific timestamps.
  - `GET /api/jobs/{jid}/clips/{cid}/community`: Returns pre-formatted community post text and Short link for instant access.

- **Frontend Calendar & Community UI (`web/index.html`)**:
  - Post pills in clip cards render distinct purple badges for community posts: `📢 Community · Scheduled for ... (+30m)` with cancel button.
  - Clip cards feature quick-action `📢` button to copy community text and open the channel community tab.
  - Clip editor modal (`#clipdlg`) features informational calendar banner: `📅 USA Auto-Calendar: 6:00 PM · 12:00 AM · 6:00 AM PKT (Max 3/day) · 📢 +30m Auto-Community Post`.
  - Added dedicated `📢 Copy Community Post` button in Clip modal that copies formatted payload and opens channel community tab in browser.

- **Automated Unit Test Suite (`tests/test_usa_publishing_calendar.py`)**:
  - 6 comprehensive tests covering: daily limit enforcement, multi-day 8-video auto-roll scenario, slot order, 5-6h minimum spacing, community post +30m pairing & formatting, and US DST timezone awareness. 100% passed.

### Tests and Verification
- `tests/test_usa_publishing_calendar.py`: 6/6 tests PASSED in 0.001s.
- `tests/test_stream_chat_and_scroll.py`: 3/3 tests PASSED in 0.045s.
- `tests/test_ai_verdicts_clean_ui.py`: 5/5 tests PASSED in 0.028s.
- Node.js AST parser: `web/index.html syntax 100% clean!`.
- Server daemon verified live on port 8765 with `/healthz` returning 200 OK and `/api/calendar/slots` returning 200 OK.


## [2026-11-23] — Stream Card Dead Space Elimination & Popout Chat Removal

### Removed
- **Redundant 'Popout Chat ↗' Button (`web/index.html`)**:
  - Removed Popout Chat button from stream card `.cta` per user feedback (`media_1795386289444_45c636ab.jpg`).
  - Removed duplicate popout button from chat header.

### Changed
- **Compacted Stream Info Panel & Zero Video Void Space (`web/index.html`)**:
  - Restructured `.cta` action buttons into a tight 2-column grid (`display: grid; grid-template-columns: 1fr 1fr; gap: 6px; height: 34px`).
  - Reduced `.sinfo-chat-box` height to `min-height: 115px; max-height: 165px; padding: 6px 8px;`.
  - Aligned `.stream` container with `align-items: start;` and `.player` with `aspect-ratio: 16/9; width: 100%`, perfectly aligning video player and `.sinfo` side-by-side with zero black void below.


## [2026-11-23] — Streamlined Live Meters: Removal of 'What was just said' & Compact AI Decisions Height Alignment

### Removed
- **'What was just said' Raw Transcript Column (`web/index.html`)**:
  - Completely removed the 4th meter column (`What was just said`), eliminating raw Whisper speech fragments ("Okay.", "These Ubers are scanning hard!") that created visual clutter.
  - Liberated ~300px horizontal real estate, expanding remaining meters into a clean, balanced 2-3 column layout.

### Added / Changed
- **Compact Single-Line AI Decisions Row Architecture (`web/index.html`)**:
  - Replaced bulky 2-line cards (55px height) with sleek, high-density single-line rows (`min-height: 24px`, `padding: 4px 8px`).
  - Integrated 12-hour AM/PM time (`⏱️ 3:25 AM`), status badge (`🔍 LISTENING`, `✂️ CLIPPED`, `⚡ HIGH PRIORITY`), `⚡ LATEST` cyan glow pill, bold headline (`💬 Chat Spike Surge (+63%)`), and concise reason snippet into a single horizontal row with full text preserved in hover tooltips.
  - Reduced container downward `max-height` from `190px` to **`86px`**, perfectly matching the ~95px-100px height of adjacent sparkline meters ("Loudness, last minute" and "Chat messages per second") and preventing the meter from stretching downward.
- **Uncluttered Header**:
  - Simplified meter header to a clean single line: `<span>🧠</span> Latest AI Decisions` with `● LIVE MONITOR` pill.
  - Removed duplicate model badge from header (reliably displayed in the stats bar right above as `Active AI Model: gemini-3.5-flash-lite`).
- **Automated Test Suite Expansion (`tests/test_ai_verdicts_clean_ui.py`)**:
  - Added test cases verifying elimination of 'What was just said', compact single-line row formatting, 86px max-height constraint, clean header, and Node.js JavaScript syntax compilation.


## [2026-11-23] — Clean AI Decisions Card Architecture & Elimination of Redundant Model Badges

### Added
- **2-Line High-Contrast Dark Card Design (`web/index.html`)**:
  - Transformed squashed single-line verdict items in `Latest AI Decisions & Moment Activity` into structured 2-line cards with comfortable padding (`padding: 8px 10px`), rounded corners (`border-radius: 8px`), and left accent borders (`border-left: 3px solid`).
  - **Line 1 (Status & Metadata)**: Features 12-hour AM/PM formatted timestamp (`⏱️ 3:12 AM`), distinct status badge (`⚡ HIGH PRIORITY`, `✂️ CLIPPED`, `🔍 LISTENING`, `🔊 LOUDNESS`, `💬 CHAT SPIKE`, `⏭️ SKIPPED`), prominent `⚡ LATEST` cyan glow pill on newest decision, and optional AI numeric score (`Score 70`).
  - **Line 2 (Action Headline & Plain-English Reason)**: Full width second line featuring icon + bold headline (e.g. `🎯 Viral Highlight Clipped:`, `🗣️ Routine Conversation:`) followed by an uncompressed, human-friendly explanation explaining why AI decided to clip or skip.
- **Automated UI Unit Test Suite (`tests/test_ai_verdicts_clean_ui.py`)**:
  - Validates zero duplicate model pills in individual decision rows.
  - Verifies presence of single active model badge in meter header (`🤖 gemini-3.5-flash-lite`).
  - Verifies 2-line card DOM structure, AM/PM formatting, and JavaScript AST syntax validity.

### Changed
- **Eliminated Repetitive Model Badge Clutter (`web/index.html`)**:
  - Removed redundant `gemini-3.5-flash-lite` badge that was repeated on every single row inside `#live_ai_verdicts_list`, freeing 140px width per row.
  - Kept a single authoritative AI model indicator in the card top header (`🤖 gemini-3.5-flash-lite`).

### Tests and Verification
- Executed `tests/test_ai_verdicts_clean_ui.py`: 4/4 passed in 0.060s.
- Node.js full AST validation of `web/index.html`: `ALL_SCRIPTS_SYNTAX_VALID`.
- Server daemon verified running on port 8765 with `/api/status` returning HTTP 200 OK.


## [2026-11-23] — Twitch Live Chat Elevation, Compact Stats Bar & Polling Scroll Auto-Stick/Preservation

### Added
- **Stream Card Live Chat Elevation (`web/index.html`)**:
  - Elevated Twitch Live Chat feed directly into the stream card (`.stream .sinfo`) beside the live video player in the exact prominent panel requested by the user.
  - Displays real-time message stream with purple username badges, live channel badge (`#channel`), and 1-click `Popout ↗` window link.
  - Added floating `More messages below ↓` jump button that appears if the user scrolls up to read earlier chat.
- **Scroll Memory & Auto-Stick Pipeline (`web/index.html`)**:
  - Auto-sticks live chat to the bottom (`scrollTop = scrollHeight`) as new messages arrive in real-time, exactly mirroring real Twitch chat.
  - Added smart scroll detection: if the user scrolls up to read history (`> 45px` from bottom), auto-scroll pauses and preserves the user's exact scroll position across 2-second polling cycles.
  - Added scroll position preservation for `#live_ai_verdicts_list` so user reviewing older decisions is never snapped back to the top by polling.
- **`⚡ LATEST` AI Decision Highlight (`web/index.html`)**:
  - Added distinctive glowing cyan `⚡ LATEST` badge and card styling on the freshest decision in `Latest AI Decisions & Moment Activity`.
- **Extended Verdicts Retention Buffer (`studio/live.py`)**:
  - Extended live session verdicts buffer from 6 to 30 items (`del self.verdicts[:-30]`) and attached precise `wall_t` epoch timestamps.
- **Automated Test Suite (`tests/test_stream_chat_and_scroll.py`)**:
  - Added unit test suite covering verdict retention, `wall_t` timestamps, deque chat message ordering, HTML compact stats, and scroll restoration logic.

### Changed
- **Compact Stream Stats Bar (`web/index.html`)**:
  - Replaced bulky 3-block grid cards (`watching / live for / followers`) with a single-line horizontal badges bar (`.sstats-compact`), liberating vertical screen real estate for the elevated chat feed.
- **Streamlined Bottom Meters Grid (`web/index.html`)**:
  - Removed redundant chat column from the bottom meters grid, leaving a clean 4-meter layout (`Loudness`, `Chat messages per second`, `Latest AI Decisions`, `What was just said`).

### Tests and Verification
- Node.js script AST check on `web/index.html`: `ALL SCRIPTS SYNTAX PERFECT!` (438,453 chars).
- Executed `tests/test_stream_chat_and_scroll.py`: 3/3 passed in 0.011s.
- Executed regression suite `test_origins_chat_teaser.py`, `test_bgm_and_meme_sounds.py`, and `test_seo_title_suggestions.py`: 16/16 passed in 13.293s.
- Server daemon verified healthy on port 8765: `{"ok":true}`.

## [2026-11-23] — Viral Background Music & Meme Sounds Library with Zero-Latency Real-Time In-Browser Sync Preview & FFmpeg Mix Rendering

### Added
- **Viral Background Music & Meme Sounds System (`studio/audio.py`, `web/audio/`, `studio/server.py`)**:
  - Implemented built-in library of 10 viral background music tracks and meme sound effects synthesized mathematically at 44.1kHz stereo MP3s:
    1. `🏎️ Phonk Drift Beat` (Fast 140 BPM 808 cowbell & bass for car drifts, chases, and speed)
    2. `🕵️ Sneaky Snitch` (Playful 120 BPM pizzicato tiptoe bounce for hilarious fails & NPC moments)
    3. `🚨 Dramatic Suspense` (Dark pulsing heartbeat & cinematic tension swell for climax scenes)
    4. `⚡ Hype Trap Anthem` (Aggressive 145 BPM brass stabs & rolling 808s for victory and clutch kills)
    5. `☕ Chill Lo-Fi Breeze` (Warm Rhodes chords & vinyl crackle for relaxing cruises & chat)
    6. `🎻 Sad Violin (L Moment)` (Melancholic minor violin phrase for tragic deaths & busted moments)
    7. `💥 Vine Boom Impact` (Deep sub-bass explosion impact for punchlines & crazy reveals)
    8. `🗿 Bruh Sound Effect` (Classic vocal formant drop for utter disbelief and facepalms)
    9. `🔔 Metal Pipe Falling` (Chaotic reverberant metallic ringing clang on crashes and sudden hits)
    10. `🎺 MLG Airhorn Blast` (3-shot high-energy trumpet fanfare for maximum hype moments)
    11. `🚫 None (Original Audio Only)` (Default clean audio mode)
  - Added REST API endpoints:
    - `GET /api/audio/tracks`: Lists all built-in and user-uploaded custom tracks.
    - `GET /api/audio/track/{track_id}`: High-performance audio streaming with Range request support.
    - `POST /api/audio/upload`: Drag-and-drop / file selector upload for custom `.mp3`, `.wav`, `.m4a`, `.ogg`, `.aac` tracks (< 30MB) into `data/audio/uploads/`.
- **Zero-Latency Real-Time In-Browser Audio Sync Preview (`web/index.html`)**:
  - Solved problem where creators previously had to re-render the whole video just to hear audio changes.
  - In `#clipdlg` Clip Editor:
    - Added sleek obsidian cyber card: **`🎵 Background Music & Meme Sounds`**.
    - **Real-Time Volume Slider**: 0% to 100% volume slider with real-time numeric display (`dlg_bgm_vol`), immediately updating `<audio>` element volume live without waiting.
    - **Live Video Sync Engine**: Video `#stage video` play, pause, seek, and loop events automatically synchronize with `window._bgmAudio` in real-time.
    - **Instant Track Audition**: Every card has a quick `▶️ Test` preview button to listen to any track standalone before selecting.
    - **Category Filter Tabs**: `🔥 All`, `🎵 Beats & Music`, `💥 Meme Sounds`, `📁 My Uploads`.
    - **Sync Toggle**: One-click button to toggle audio sync preview on/off.
- **FFmpeg Mix Rendering Pipeline (`studio/render.py`, `studio/jobs.py`)**:
  - `jobs.request_render` accepts `bgm_track` and `bgm_volume`.
  - `render._render_in` loops the background music with `-stream_loop -1 -i <bgm_path>` and mixes it under the streamer's voice via `amix=inputs=2:duration=first:dropout_transition=2`.
  - Works seamlessly with or without Climax Teasers (`teaser_enabled`).

### Tests and Verification
- Created `tests/test_bgm_and_meme_sounds.py` (6/6 tests passed 100%):
  - Verified built-in tracks listing and path resolution.
  - Verified path traversal protection against `../../` exploits.
  - Verified custom audio upload validation.
  - Verified `request_render` persistence.
  - Verified real FFmpeg execution rendering a 1080x1920 MP4 with background music mix.
- Verified regression suites: `test_seo_title_suggestions.py`, `test_origins_chat_teaser.py`, `test_post_text.py` (10/10 passed).
- Validated JavaScript AST syntax in `web/index.html` with Node.js (Exit code 0).
- Live server daemon running on port 8765 (`curl http://127.0.0.1:8765/api/audio/tracks` returned 200 OK).

## [2026-11-23] — True Video Frame-Grounded AI Viral Hooks, Title Ideas & Vision SEO

### Added
- **Multimodal Video Frame Grounding for Viral Hooks, Titles & Post Text (`studio/jobs.py`, `studio/brain.py`, `studio/server.py`, `web/index.html`)**:
  - Solved issue where AI Viral Hooks (`/hooks`), Title Ideas (`/titles`), and "Write again with AI" (`/write`) were running on blind text transcripts, causing generic hallucinated clichés (e.g. `GTA 6 *flashbacks* are wild 💀`, `Ohnepixel loses his *mind* live 😭`).
  - Added `jobs.get_clip_frames_payload(job, clip, n_frames=6)` in `studio/jobs.py` extracting 6 sequential video frames across the clip timeline (0.15, 0.35, 0.55, 0.70, 0.85, 0.95) directly from clip MP4s, source slices, or cover JPEGs.
  - Upgraded `generate_viral_hooks` and `generate_viral_titles` in `studio/brain.py` to accept `image: bytes | list[bytes] | None`. When video frames are available, prompts run through Gemini Vision (`ai.see_json(prompt, image, schema=...)`).
  - Generated hooks now physically describe on-screen vehicles, crashes, alligators, stunts, and streamer facial expressions with single-word yellow asterisks (`*CAR*`, `*ALLIGATOR*`, `*BOAT*`) and emojis (just like ChatGPT).
  - Integrated `jobs.get_clip_frames_payload` into `clip_generate_hooks`, `clip_generate_titles`, `clip_write`, and `generate_clip_ai_seo` in `studio/server.py`.
  - Updated UI buttons and toast notifications in `web/index.html` to clearly inform the user that AI is visually watching video frames (`📸 Watching video…`).

### Tests and Verification
- Added multimodal tests in `tests/test_seo_title_suggestions.py`:
  - `test_multimodal_frames_payload_and_hooks`: Passed (6/6 passed).
  - Verified `test_post_text.py` and `test_origins_chat_teaser.py` (4/4 passed).
- Verified live Gemini vision execution on 6 Vice City stream frames, generating grounded hooks (`WHAT IS THAT *ALLIGATOR*?! 🐊💀`, `BRO DID NOT SEE THE *BRIDGE* 🌉💥`, `WHAT IS ON THAT *BOAT*?! 🛥️👀`).
- Validated JavaScript AST in `web/index.html` with Node.js (Exit code 0).

## [2026-11-23] — Multi-Title SEO Suggestions & Interactive Title Pill Selection in Clip Editor

### Added
- **Multi-Title AI Suggestions & Interactive Clickable Pills (`studio/brain.py`, `studio/server.py`, `web/index.html`)**:
  - Restored and enhanced creator-favorite feature where AI suggests 3-4 alternative high-CTR YouTube Shorts titles for every clip.
  - In `#clipdlg` Clip Editor:
    - Under **Title (with Viral Hashtags)**: Added `#dlg_title_pills` rendering 3-4 clickable title suggestion pills (`💡 Title #1: ...`, `💡 Title #2: ...`, `💡 Title #3: ...`, `💡 Title #4: ...`).
    - Under **AI SEO - YouTube Shorts SEO**: Added `#dlg_seo_title_pills` rendering 3-4 clickable Shorts title pills directly beneath `Shorts Title (High-CTR with #Shorts)`.
    - Added shiny `✨ AI Title Ideas` button (`btn_ai_titles`) next to Shorts Title to generate 4 fresh title variations on demand.
  - **Synchronized Pill Click Handler (`pick_title`)**:
    - Clicking any title pill instantly populates BOTH the `Title (with Viral Hashtags)` input and the `Shorts Title (High-CTR with #Shorts)` input.
    - Synchronously highlights the clicked title pill across both sections with the active neon cyan accent border and glow (`1px solid var(--accent, #00f0ff)`).
  - **Dynamic AI Generation & Fallback Pipeline (`studio/brain.py`)**:
    - Added `TITLES_SCHEMA` and `generate_viral_titles(text, title, uploader, game, count=4)` generating 4 distinct viral titles ending with `#Shorts` and fitting emojis.
    - Updated `_tidy` to guarantee every clip retains and generates a 4-title array (`titles: [...]`), ensuring pills are never empty even if video dialogue is minimal.
    - Updated `post_text` to return `titles` array alongside `title`, `description`, `hashtags`, `seo_title`, `seo_tags`, and `pinned_comment`.
    - Updated `describe_multimodal` to generate 4 titles.
  - **New REST API Endpoint (`studio/server.py`)**:
    - Added `@app.get("/api/jobs/{jid}/clips/{cid}/titles")` and `@app.post("/api/jobs/{jid}/clips/{cid}/titles")` calling `clip_generate_titles(jid, cid)`.
    - Updated `clip_write` to persist `clip["titles"]` and return it.
    - Updated `generate_clip_ai_seo` to ensure 4 title variations are returned and saved.
  - **Live UI Dynamic Refresh (`web/index.html`)**:
    - `writetext` ("Write again with AI") dynamically populates both `#dlg_title_pills` and `#dlg_seo_title_pills`.
    - `re_ai_seo` ("✨ AI Scan Video & Fix SEO") dynamically populates both `#dlg_title_pills` and `#dlg_seo_title_pills`.
    - `ai_generate_titles` ("✨ AI Title Ideas") fetches 4 fresh titles and immediately updates inputs and pills.

### Tests and Verification
- Created `tests/test_seo_title_suggestions.py` covering:
  - `generate_viral_titles` fallback generation (4 titles ending with #Shorts)
  - `_tidy` 4-title and hook preservation
  - `post_text` returning `titles` array
  - `/api/jobs/{jid}/clips/{cid}/titles` endpoint execution and clip persistence
  - `web/index.html` presence of `#dlg_title_pills`, `#dlg_seo_title_pills`, and event handlers.
  - Result: 5/5 tests passed (0.016s).
- Ran existing project test suite `test_post_text.py` (35 checks passed), `test_origins_chat_teaser.py` (4/4 passed), and `test_seo.py` (17 checks passed).
- Node.js JavaScript syntax check on `web/index.html`: 2/2 script blocks passed with zero syntax errors.
- Live server daemon restarted on port 8765: HTTP 200 OK.

## [2026-11-23] — Explicit Clip Origin Badges, Twitch Live Chat Window & Viral Climax Teaser Cold Open

### Added
- **Explicit Clip Origin Badges & Labels (`studio/live.py`, `web/index.html`)**:
  - Eliminated ambiguity between manual button clips, keyword triggers, and real AI auto detections.
  - **Manual Clips**: UI clicks on "Clip last 30s" / "Clip now" are strictly tagged with `source: 'manual'` and `trigger_type: 'manual'`, rendering as a prominent pink badge: `👆 MANUAL` (even if multimodal AI evaluates the score).
  - **Keyword Trigger Clips**: Trigger phrases and reaction keywords are strictly tagged with `source: 'trigger'`, rendering as vibrant amber badges: `🎯 "Oh my god"`, `🎯 "Chat"`, `🎯 "Meme"` (the creator's preferred style).
  - **Real AI Auto Detection**: Highlights detected automatically by AI are tagged with `source: 'ai_auto'` and rendered as `🤖 AI AUTO 96` / `🤖 AI AUTO 83`.
- **Real-Time Twitch Live Chat Window / Feed (`studio/live.py`, `web/index.html`)**:
  - Backend IRC bot parses incoming `PRIVMSG` stream messages, buffering latest clean user and text messages in `self.recent_chat_msgs`.
  - Added dedicated `💬 Twitch Live Chat` meter component in the live recording dashboard matching the height of the AI decisions feed (190px).
  - Displays real-time message stream with colored user badges, smooth auto-scroll, and a 1-click `Popout ↗` window option.
- **Viral Climax Teaser Cold Open Hook Editor & Concat Pipeline (`studio/render.py`, `studio/jobs.py`, `web/index.html`)**:
  - Implemented creator-requested Viral Teaser Cold Open: takes the funniest 3-5 seconds of reaction/punchline from the end of the video and prepends it at 0:00 as a teaser hook.
  - In `#clipdlg` clip editor: added interactive "🎬 Viral Climax Teaser (Cold Open Hook)" control card with duration selector (3s, 4s, 5s) and `🎯 Use Current Video Playhead` button to grab the exact playhead position from preview.
  - In `studio/render.py`: `build_ass` shifts transcript captions by `teaser_dur` and displays Hook Banner over the teaser cold open; `_render_in` uses ffmpeg filter concat to assemble the teaser and main video in a single 1080p60 pass with seamless audio.
- **12-Hour AM/PM Time Format & Plain Human Headlines (`studio/live.py`, `web/index.html`)**:
  - Saved `wall_t = time.time()` on every AI verdict in `studio/live.py`.
  - Frontend formats timestamps into clean 12-hour AM/PM times (`02:12 PM`, `01:11 PM`, `11:08 AM`).
  - Replaced developer debug jargon with plain creator headlines (Loud Voice / Shout, Chat Spike Surge, Target Pace Reached, Quiet Gameplay, Routine Conversation, Viral Highlight Clipped).

### Tests and Verification
- Created `tests/test_origins_chat_teaser.py` covering:
  - Manual clip payload tagging (`source: manual`, `trigger_type: manual`)
  - Twitch IRC PRIVMSG username and message extraction
  - Teaser cold open ASS subtitle time shift and hook banner display
  - Video filter `vin` parameter for concat filter
  - Result: 4/4 tests passed (0.019s).
- Ran existing project test suites: `test_trigger_timeline.py`, `test_hook_single_yellow.py`, `test_ohnepixel_engine.py`, `test_capcut_and_styles.py`. Result: 21/21 tests passed.
- Node.js JavaScript syntax check on `web/index.html`: `All 2 script blocks 100% valid!`.
- Server restarted on port 8765: HTTP 200 OK.


## [2026-11-23] — Unified Sleek Folded Stream Cards & Real Video Preview Fallback

### Changed & Improved
- **Unified Sleek Folder Rows (`web/index.html`)**:
  - Completely removed the redundant and noisy second dashed box (`📁 X clips folded... Open Folder 📂`) on collapsed projects.
  - The stream row itself is now a single, unified, cyber-dark card with smooth rounded borders (`border-radius: 12px`), subtle cyan border glow, and interactive hover effects.
  - Added an inline `📁 <N> Clips` badge directly next to the stream title and an upgraded `📁 Open Folder ▶` / `📂 Fold ▼` toggle button.
  - Clicking anywhere on the stream header smoothly expands or collapses the clip grid without layout jumping.
- **Authentic Video Thumbnail Fallback (`web/index.html`, `studio/server.py`)**:
  - Resolved the blank/dead chain link icon box on streams without a dedicated cover thumbnail.
  - Frontend and backend now automatically discover the first available clip thumbnail (`clip001.jpg` in `clips/`) and display a crisp, real gameplay/facecam frame with the overlay duration tag.
  - If a job has 0 clips yet, it displays a sleek cyber gaming badge (`🔴 LIVE STREAM` or `🎬 VIDEO`) with glowing neon gradients instead of an empty dark box.

### Tests and Verification
- Node.js AST syntax validation: `JavaScript Syntax: VALID (Code 0)`.
- HTTP endpoint `/media/{jid}/thumb.jpg`: verified 200 OK with JPEG image data.
- Browser subagent visual inspection: verified clean single-row folder layout, absence of dashed box, and real video preview frames. Screenshot captured: `browser_evidence/4c38de25-4432-4b5a-af8e-1feda53dc462/final_step_12.png`.

## [2026-11-22] — Golden Retention Timeline Calibration (12s Pre-Roll Hook & 28s Post-Roll Reaction)

### Added
- **Dedicated Timeline Test Suite (`tests/test_trigger_timeline.py`)**:
  - Comprehensive unit and integration test suite (6/6 tests passing) verifying exact timing offsets:
    - Pre-roll lead-in: 12.0s ($\ge 10.0s$ and $\le 15.0s$)
    - Post-roll reaction: 28.0s ($\ge 25.0s$ and $\le 30.0s$)
    - Total duration: 40.0s
    - Overlapping trigger merging up to 60.0s
    - Category profile standardization across CS2, GTA 6, Just Chatting, and Story Games
    - Boundary clamping at stream inception ($T < 12s$)

### Changed
- **Pre-Roll and Post-Roll Boundary Calibration (`studio/live.py`)**:
  - Replaced legacy `pre_roll = 18.0, post_roll = 25.0` with `pre_roll = 12.0, post_roll = 28.0`.
  - Trigger word or viral event now occurs at second 12 of the clip (within the first 10-15s hook window before viewers swipe).
  - After the trigger word, the clip continues for 28 seconds of reaction, laughter, chat banter, and continuous gameplay (total ~40.0s).
  - Preserved `trigger_t` across manual candidates and clip metadata.
- **AI Check Candidate Alignment (`studio/live.py`)**:
  - Upgraded `_ai_check` candidate refinement with Golden Retention Alignment:
    - Identifies exact match timestamp of Level 1 reaction phrases in candidate transcripts and snaps `start = max(ws, trigger_t - 12.0)` and `end = min(now, trigger_t + 28.0)`.
    - Falls back to audio loudness reaction peak from signal judge (`sig`).
    - Standardizes candidate expansion to 40.0–42.0s with a 70% post-roll reaction bias.
- **AI Scout Prompt Rules (`studio/brain.py`)**:
  - Updated `RULES` with the **Golden Retention Timeline Rule**:
    - Climax/trigger occurs within first 10 to 15 seconds (target 12s).
    - Mandatory 25 to 30 seconds (target 28s) of aftermath footage after the trigger.
    - Total duration 38 to 44 seconds (target ~40-42s).
- **Category Profiles Standardization (`studio/ohnepixel.py`)**:
  - Standardized `min_pre_roll: 12` and `min_post_roll: 28` across CS2, GTA 6, Just Chatting, and Story Games profiles.

### Tests and Verification
- `tests/test_trigger_timeline.py`: 6/6 tests passed.
- `tests/test_ohnepixel_engine.py`: 12/12 tests passed.
- `tests/test_hook_single_yellow.py`: 3/3 tests passed.
- `tests/test_live_times.py`: All 18 timing checks passed.
- `tests/test_live.py`: All 4 live checks passed.
- PeakCut server daemon running cleanly on port 8765.

## [2026-11-22] — Livestream Clipping Engine & UI Suite Overhaul

### Added
- **Automatic YouTube Cover Thumbnail Upload (`studio/accounts.py`, `studio/posting.py`)**:
  - Implemented `youtube_set_thumbnail` using the official YouTube Data API v3 `POST https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}` endpoint.
  - When posting clips to YouTube, PeakCut now automatically pushes the high-CTR viral cover thumbnail (`clip0xx.jpg` with the hook banner, facecam, and gameplay scene). Creators no longer need to manually choose or upload a thumbnail in YouTube Studio.
- **Collapsible Stream Project Folders (`web/index.html`)**:
  - Added an accordion folder toggle (`📁 / 📂`) on all stream and video project cards.
  - Clicking "Fold Clips" collapses the massive vertical cards grid into a clean, compact single-line summary (`📁 7 clips folded in this stream. Click to open folder`), saving massive vertical scroll space.
  - Folding preference is saved into `localStorage` across page refreshes.
- **Upgraded Visual AI Decision Feed (`web/index.html`)**:
  - Overhauled "Latest AI decisions" into a modern, spacious visual activity feed.
  - Added real-time decision badges (`⚡ HIGH PRIORITY`, `✂️ CLIPPED`, `🔍 LISTENING`, `⏭️ EVALUATED`), timestamps (`⏱️ 9:24`), bold trigger reasons, and active AI model tag (`gemini-3.5-flash-lite`).

### Changed & Fixed
- **Single Yellow Punch Keyword per Viral Hook Banner (`studio/render.py`, `tests/test_hook_single_yellow.py`)**:
  - Solved the bug where multi-line hooks had 2 yellow words across lines.
  - Formats at the whole-banner level before line splitting so exactly ONE punch keyword across all lines is highlighted in Canary Yellow (`\c&H00E5FF&`).
  - Streamer names (`ohnepixel`, `speed`, `kai`, etc.) and stopwords are strictly demoted, while action/punch verbs (`heists`, `roasts`, `arrested`, `glitch`) receive priority.
- **Natural Gameplay Clip Duration Matching (~42–45s) (`studio/live.py`)**:
  - Expanded candidate clip boundaries to capture full 42–45s natural gameplay moments (matching continuous discovery 18s pre-roll + 25s post-roll), preventing clips from being cut down to 26s when 45s of action is available.
  - Re-rendered `clip016` from 26.0s to 43.02s, matching `clip016.src.mp4`.
- **Hourly Clip Throttle Removal (`studio/creators.py`, `studio/live.py`)**:
  - Raised default `live_per_hour` from 4 to 25.
  - High-priority moments and phrase triggers now bypass hourly limits completely, eliminating the frustrating "Skipped: 4 clips this hour already" blocker during active gaming streams.
- **Pinned / Sticky Video Preview in Clip Editor (`web/index.html`)**:
  - Updated `#clipdlg`, `.editor`, `.stage`, and `.panel` layout with `position: sticky; overflow-y: auto; height: 100%`.
  - When scrolling through settings, caption styles, sync, SEO, or publishing buttons on the right, the left phone video preview remains securely locked and pinned in the center of the screen without scrolling away.

## [2026-11-22] — Fix: AI Viral Hooks Button 405 Method Not Allowed Bug

### Fixed
- **AI Viral Hooks Button Handler (`web/index.html`, `studio/server.py`)**:
  - **Root Cause**: `ai_generate_hooks` in `web/index.html` was calling `api(path, {}, "POST")` where `api(path, opt)` only takes 2 arguments (`path` and `opt`). Because `opt` was empty `{}` without a method, `fetch()` defaulted to a `GET` request. FastAPI rejected it with `405 Method Not Allowed`, throwing an error and preventing hooks from generating.
  - **Resolution**: Replaced with `await send('/api/jobs/${encodeURIComponent(jid)}/clips/${encodeURIComponent(cid)}/hooks', {})` which properly sends a JSON POST request.
  - **Dual-Method Compatibility & Persistence**: Added `@app.get` alongside `@app.post` for `/api/jobs/{jid}/clips/{cid}/hooks` in `studio/server.py`, and automatically saved generated hooks into `clip["hooks"]` and `jobs.save(job)`.
  - **Frontend UI Refresh**: Clicking `✨ AI Viral Hooks` generates 5 high-CTR headline pills with Canary Yellow punch tags (`*word*`), selects the top hook, and enables 1-click switching between variations.


### Added
- **Dedicated OhnePixel Keyword & Reaction Database (`studio/ohnepixel.py`)**:
  - German + English speech recognition support, community slang, pronunciation and spelling variants (`naur`, `ma drilla`, `vas?!`, `nein`, `auuug`, `rejuicer`, `fish dish`, `gold gold gold`).
  - Tiered classification:
    - Level 1: Strong Reaction Phrases (35+ phrases e.g. "WHAT THE FUCK IS THAT", "NO FUCKING WAY", "HOLY SHIT", "ARE YOU SERIOUS", "LET'S FUCKING GO", "WHAT JUST HAPPENED").
    - Level 2: OhnePixel Community Expressions & CS2 Skin Terms (Contextual signals, require reaction or event context).
    - Level 3: Common Words ("bro", "no", "okay", "wait", "what", "gold", "knife", "wow") with strict false-positive prevention.
  - Laughter and non-verbal reaction detection patterns (`hahaha`, `wheezing`, `crying laughing`, `[laughter]`).
  - Category profiles for Counter-Strike 2, GTA VI, Just Chatting, and Story Games.
- **Intelligent Multimodal AI Scoring (Mode A) in `studio/brain.py`**:
  - `judge_multimodal_moment` combining 3 primary signals:
    - Signal 1: Keyword Relevance (25%) via `ohnepixel.classify_transcript`.
    - Signal 2: Streamer Excitement & Reaction Intensity (35%) via audio loudness z-scores, laughter patterns, and chat velocity.
    - Signal 3: Actual Visual / Gameplay Event Evidence (40%) via candidate frame analysis with multimodal AI (`ai.see_json`).
  - Dynamic weight redistribution when visual frames are absent (Keyword 40%, Reaction 60%).
  - Event-quality validation rules ensuring casual "BRO" or quiet non-events are strictly skipped, while genuine clutches, uncontrollable laughter, and unboxes achieve High Priority.
- **Keyword-Only Fallback Engine (Mode B) in `studio/ohnepixel.py`**:
  - Automatically activated when AI models or keys are unavailable.
  - Tiered evaluation with false-positive guardrails.
- **Continuous Moment Discovery & Smart Clip Boundaries in `studio/live.py`**:
  - Natural event windowing: 18s pre-roll (setup), 25s post-roll (reaction/payoff), 20–60s total clip duration.
  - Multi-trigger candidate merging: overlapping triggers within 15 seconds are consolidated into a single unified clip instead of fragmented clips.
  - Automated video frame extraction via `ffmpeg` from rolling `.src.mp4` buffer for visual verification.
- **Review Feedback API & Frontend Controls (`studio/server.py`, `web/index.html`)**:
  - Endpoint `POST /api/jobs/{jid}/clips/{cid}/review` supporting `great`, `good`, `bad`, `missed`, `duplicate`, `false_reaction`.
  - High-contrast Active Detection Mode badge (`⚡ MODE A (AI INTELLIGENT SCORING)` vs `🎯 MODE B (KEYWORD FALLBACK)`) in live session header.
  - Score breakdown pills (`Score: 88 · KW 25% | RX 32% | VIS 31%`) in clip dialog and badges.
  - 1-click review action buttons in the clip dialog.
- **Comprehensive Unit & Integration Test Suite (`tests/test_ohnepixel_engine.py`)**:
  - Tested all 12 requested scenarios: casual bro skipped, shouting no fucking way high priority, 8s uncontrollable laughter, quiet knife unbox visual detection, wait wait wait with reaction, repeated gold gold gold, just chatting funny conversation, GTA 6 physics glitch, story game jumpscare, chat spam burst, 15s candidate merging, and Mode B fallback. All 12 passed 100%.

### Tests and Verification
- Executed `& '.\\.venv\\Scripts\\python.exe' tests/test_ohnepixel_engine.py` -> 12 tests passed (OK).
- Executed `& '.\\.venv\\Scripts\\python.exe' tests/test_live.py` -> ALL PASSED.
- Executed `& '.\\.venv\\Scripts\\python.exe' tests/test_live_times.py` -> All checks passed.
- Validated JavaScript syntax in `web/index.html` via Node.js AST check -> OK.
- Tested `POST /api/jobs/{jid}/clips/{cid}/review` on live server -> HTTP 200 OK (`{"ok": true, "feedback": "great"}`).


## [2026-11-22] — Official Rebranding to ClipNova AI & Remote Repository Configuration

### Added & Changed
- **Official Rebranding to ClipNova AI (`web/index.html`, `studio/config.py`, `.env`)**:
  - Updated application title, sidebar branding alt tags, and onboarding tour copy to **ClipNova AI**.
  - Configured default repository endpoint to `https://github.com/ahsanK225/ClipNova-AI`.
  - Created standalone launch script `run_clipnova.bat`.
- **Git Remote Configuration (`git remote set-url origin`)**:
  - Set remote origin to `https://github.com/ahsanK225/ClipNova-AI.git` under user's GitHub account (`ahsanK225`).


## [2026-11-22] — OpusClip Modern Cyber-Dark Theme, Preset Studio Edit Mode & Clean Unobstructed Smartphone Mockup

### Added & Improved
- **OpusClip Modern Cyber-Dark AI Studio Theme (`web/index.html`)**:
  - Replaced muddy brown/white palette with deep luxury cyber-dark obsidian (`#090B10`, `#0C0F17`, `#131826`) with electric neon indigo/violet (`#6366F1`, `#8B5CF6`) and cyan (`#00F0FF`) glow accents.
  - Transformed cards and surfaces with glassmorphism, glowing borders, crisp white `#FFFFFF` headings, and smooth hover micro-animations.
  - Sleek modern scrollbars and dark dialog backdrop filters.
- **Direct Preset Editing in Studio & 1-Click Batch Applicator (`web/index.html`)**:
  - Added direct **`[ ✏️ Edit ]`** button on every saved preset chip in Creator Settings: 1-click opens Visual Layout Studio loaded with the preset's exact crop boxes.
  - Added **`[ 🚀 Apply All ]`** button on each preset chip (`applyPresetToAllCreatorClips`): 1-click batch applies preset to all clips in creator's streams and re-renders them.
  - Enhanced `applyPresetToClip`: clicking a preset chip in the Clip Dialog instantly updates DOM, displays stage spinner `Re-making clip with "${name}"…`, passes all fields, and queues re-render without requiring scrolling to "Save and re-make clip".
  - Inside Studio modal, preloads active preset into canvas, shows `✏️ Editing "${name}"`, and displays prominent **`[ 💾 Update "${name}" ]`** overwrite button.
- **Clean Unobstructed Smartphone Mockup (`web/index.html`)**:
  - Completely removed clutter overlay stickers (`▶ Shorts` red pill, fake like/comment icons, and bottom `CapCut / Streamladder Style` badge) that were obscuring the video preview.
  - The phone preview is now 100% clean, showing pristine video framing with an ultra-thin metallic bezel, speaker notch, and dimension tag underneath.

### Tests and Verification
- Node.js AST validator on `web/index.html`: Code 0 (Zero errors, all scripts valid).
- `tests/test_capcut_and_styles.py`: ALL PASSED (12/12 caption and hook styles + CapCut export verified).
- Server alive and responding with HTTP 200 on `http://127.0.0.1:8765/app`.


## [2026-11-22] — Instagram Profile Link, GitHub Repository Redirection, and Branding Refresh

### Added & Changed
- **Instagram Profile Redirection (`studio/config.py`, `web/index.html`, `.env`)**:
  - Pointed default `FOLLOW_URL` to user's profile: `https://www.instagram.com/itz_ahsan.iqbal/?__pwa=1`.
  - Updated `web/index.html` "Follow me" action and feedback modal to open Ahsan Iqbal's Instagram profile directly.
- **GitHub Profile / Repo Redirection (`studio/config.py`, `web/index.html`, `.env`)**:
  - Pointed default `REPO_URL` to user's GitHub: `https://github.com/ahsanK225`.
  - Updated "Star on GitHub" button title and metadata.
- **Clean Repository & Git Ignore Rules (`.gitignore`)**:
  - Added ignore patterns for temporary test videos, audio files, extracted frames, test scripts, and `cookies.txt`.
- **Live Server Restart & Verification**:
  - Restarted PeakCut daemon on port 8765; confirmed `/api/status` returns user's GitHub and Instagram profile URLs.

### Tests and Verification
- `GET http://127.0.0.1:8765/api/status`: Verified `links` returns `{'repo': 'https://github.com/ahsanK225', 'follow': 'https://www.instagram.com/itz_ahsan.iqbal/?__pwa=1'}`.
- `tests/test_capcut_and_styles.py`: ALL PASSED (12/12 caption and hook styles + CapCut export verified).


## [2026-11-22] — CapCut Desktop Export, Bouncy / Hormozi Subtitles, Purple Whip Hook Styling & Visual Studio Controls

### Added
- **CapCut Desktop Project Draft Generator (`studio/capcut/export.py`, `studio/capcut/`)**:
  - Embedded lightweight Python draft engine capable of generating native CapCut Desktop drafts directly in `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\`.
  - Added backend endpoints: `POST /api/jobs/{jid}/clips/{cid}/export-capcut` and `POST /api/jobs/{jid}/clips/{cid}/open-capcut-folder`.
  - Generates multi-track project with Video Track (9:16 vertical clip), Text Track for Hook Banner, and Subtitle Text Track for word-level captions.
  - Added 1-click "🚀 Open in CapCut Desktop" and "📁 CapCut Project Folder" buttons in Clip Dialog.
- **Bouncy Word-Level Pop Captions (`studio/render.py`)**:
  - Extracted and integrated battle-tested physics keyframes from `Beautiful-Captions` and `ai-video-captions`.
  - Added new selectable caption styles:
    - `hormozi`: Bold cyan highlight pop with thick 8px black outline.
    - `mrbeast`: Bright yellow base text with punchy orange highlight pop.
    - `karaoke`: Word-by-word smooth color wipe using `\kf` tags.
  - Retained existing `bounce`, `hype`, and `clean` styles.
- **Hook Banner Styling & Custom Positioning (`studio/render.py`, `web/index.html`)**:
  - Added new hook badge themes matching user reference:
    - `purple_whip`: Dark purple badge with hot pink neon glowing border ("THAT PURPLE WHIP THOUGH").
    - `cyber_red`: Action high-intensity red badge.
    - `gold_luxury`: Gold border with black backdrop.
  - Added parameters `hook_y`, `hook_w`, `hook_font_size`, `hook_x` allowing custom placement anywhere on the 9:16 frame.
- **Interactive Hook Banner & Captions Visual Editor (`web/index.html`)**:
  - Added dedicated editor card in Visual Layout Studio with real-time sliders for vertical height (Y), banner width (W), banner style selector, and caption style selector.
  - Real-time phone canvas preview (`clsDrawPhonePreview`) draws the active Hook Banner pill with drop shadow and border, and renders sample bouncy subtitles directly on the 9:16 phone mockup.
  - Custom hook settings are saved into named presets and applied both globally (Creator Setup) and to individual clips.
- **Comprehensive Verification Suite (`tests/test_capcut_and_styles.py`)**:
  - Validates ASS subtitle generation across all 6 caption styles and all 6 hook styles.
  - Tests CapCut desktop draft creation, track integrity, and directory hygiene.

## [2026-11-21] — Named Custom Presets Store, Photoshop Dark Crop Mask, 8 Anchor Handles & Clip Re-Rendering

### Added
- **Named Custom Presets Store (`studio/creators.py`, `studio/server.py`, `web/index.html`)**:
  - Added `custom_presets` dict storage on creators allowing users to create, name, and permanently store multiple custom presets (e.g. "GTA 6 Daytime Cam", "OhnePixel Top-Left").
  - Added backend endpoints: `GET /api/creators/{cid}/presets`, `POST /api/creators/{cid}/presets`, and `DELETE /api/creators/{cid}/presets/{name}`.
  - Added "My Saved Presets" interactive chips row with 1-click preset apply and deletion in the Studio dialog.
  - Added dedicated "➕ Save as New Named Preset" input box.
- **Photoshop-Style Dark Mask Canvas (`web/index.html`)**:
  - Implemented semi-transparent dark vignette mask (`clsDrawMask`) over the 16:9 canvas with cutouts for active crop area so unused stream portions are shaded dark (`rgba(0,0,0,0.72)` or `0.92` deep blackout).
  - High-contrast visual focus: only the selected box is illuminated, with Photoshop corner crop brackets and 3x3 rule-of-thirds grid guides.
- **8 Interactive Anchor Points / Boundary Handles (`web/index.html`)**:
  - Added 8 handles for both Gameplay and Facecam boxes (`nw`, `n`, `ne`, `e`, `se`, `s`, `sw`, `w`) with appropriate resize cursors, allowing user to drag any individual edge or corner freely.
  - Added 9:16 Slot Ratio Lock toggle (`🔒 9:16 Slot Ratio Locked` vs `🔓 Freeform Points`).
- **Zero-Distortion Preview Engine (`web/index.html`)**:
  - Implemented `drawCover` canvas helper utilizing uniform aspect-ratio scaling with centered clipping, preventing game characters and streamer faces from ever stretching or squashing.
- **Existing Clip Direct Re-Rendering from Studio (`web/index.html`, `studio/jobs.py`, `studio/server.py`)**:
  - When opened from a clip, Studio extracts the exact frame from that clip's source video via `GET /api/jobs/{jid}/frame?cid={cid}`.
  - Clicking "⚡ Apply to This Clip & Re-Render" sends `POST /api/jobs/{jid}/clips/{cid}/render`, queues the clip, and triggers background FFmpeg re-rendering with custom layout.

### Fixed
- **Prevented Forced Custom Layout Overrides**:
  - Fixed `render.py:362` and `jobs.py:580` where saving custom layout previously forced `layout = "custom"` on all creators and existing clips, breaking standard 50/50 splits. Custom layout now only applies when `layout == "custom"` is explicitly set.
  - Restored `ohnepixel` creator layout to default `split_half`.
- **Live Frame Refresh Sanitization**:
  - Clamped seek timestamp `t` to safe seconds if millisecond epoch (`Date.now() > 3600`) was sent, preventing FFmpeg EOF seek failures.
  - Added cache-busting query parameter `cb` and explicit `CLS.img.src = url` triggering `onload`.

### Tests and Verification
- Executed `test_endpoints.py`: All 5 checks passed (Status OK, Frame extraction 86.5KB JPEG OK, Presets GET/POST/DELETE OK).
- Regression test runner `tests/run.py` executed.



## [2026-11-21] — Interactive Visual Custom Layout & Facecam Studio (CapCut/Streamladder Style) & Roman Urdu Speech Transcripts

### Added
- **Interactive Visual Custom Layout & Facecam Studio (`PeakCut/web/index.html`)**:
  - Built full CapCut / Streamladder style interactive visual studio modal dialog (`#custom_layout_dlg`) accessible directly from Creator Setup (`drawCreatorForm`) and Clip Editor (`drawClipDlg`).
  - Interactive 16:9 source stream canvas with draggable, resizable Cyan bounding box for Facecam (webcam) and Orange bounding box for Gameplay with 4-corner handles.
  - Real-time 9:16 vertical smartphone canvas preview updating live on mouse/touch drag via HTML5 2D canvas without reloading.
  - Multi-layout modes: Split Screen (Cam Top, Game Bottom), Picture-in-Picture (Floating Corner Cam), and Fullscreen Gameplay Crop.
  - Customizable Split Height Ratio slider (20% to 70%) and Glowing Cyan broadcast divider toggle.
  - Quick streamer presets: `OhnePixel (Top-Left Cam)`, `Top-Right Cam`, `Speed / Kai (Bottom-Left Cam)`, `Classic 50/50 Split`, and `Corner PIP`.
  - Live stream frame capture button (`📸 Refresh Live Frame`) pulling live snapshot directly from active stream buffer or Twitch thumbnail, plus custom screenshot upload support.
- **Backend Custom Layout Render Engine (`PeakCut/studio/render.py`, `PeakCut/studio/creators.py`, `PeakCut/studio/jobs.py`)**:
  - Added `layout == "custom"` filtergraph in `render._filter`: crops exact `facecam` and `gameplay` coordinates, scales with lanczos accurate rounding, unsharp mask clarity, and applies customizable broadcast divider line.
  - Added `custom_layout` configuration to Creator `DEFAULTS` and `_clean`.
  - Added API endpoints in `studio/server.py`:
    - `GET /api/creators/{cid}/frame`: extracts fresh 16:9 JPEG snapshot from active stream buffer, recent clips, or Twitch thumbnail.
    - `GET /api/jobs/{jid}/frame`: extracts JPEG frame at given timestamp from video or buffer.
    - `POST /api/creators/{cid}/custom-layout`: saves custom layout bounding boxes and mode as default for creator and active recording session.

### Fixed
- **Speech-to-Text & Transcripts Romanization (`PeakCut/studio/transcribe.py`)**:
  - Fixed voice recognition and speech transcription returning Hindi Devanagari script (`अच्छा...`) or Urdu script when Hindi/Urdu speech is spoken.
  - Connected `transcribe.transcribe` to `roman.words(words)`, guaranteeing 100% of speech recognized across live stream and video clips is automatically converted into clean, natural Roman Urdu (`accha, idhar mainne kaha tha...`).

### Tests and Verification
- Created and executed `PeakCut/scratch/test_custom_layout_and_roman.py`: all 16 checks PASSED with 0 errors.
  - Devanagari Hindi conversion to Roman Urdu verified.
  - Urdu script conversion to Roman Urdu verified.
  - Custom layout filtergraph and split height math verified.
  - `GET /api/creators/ohnepixel/frame` verified (HTTP 200, valid JPEG >73KB).
  - `POST /api/creators/ohnepixel/custom-layout` verified (HTTP 200, custom layout saved).
- Full regression suite `PeakCut/tests/run.py` executed across all test suites.

## [2026-11-21] — Header Overlap Elimination, Intelligent Multi-Key Provider Routing, Stale Error Clearing & 1-Click ChatGPT Bridge

### Added
- **1-Click ChatGPT Bridge (`PeakCut/web/index.html`)**:
  - Added `🚀 Open in ChatGPT` in Clip Editor: automatically compiles streamer persona, content category, duration, dialogue, and scene context into an engineered prompt, copies to clipboard, and opens ChatGPT in a new tab.
  - Added `📋 Paste from ChatGPT`: automatically parses pasted text or JSON from ChatGPT and populates High-CTR Title, Description with emojis/hashtags, YouTube Search Tags, and Pinned Comment Hook.
  - Added dedicated **AI SEO & Viral Hooks** section in Settings with creator tone presets (`Auto-Adaptive`, `Speed/Kai Hype`, `OhnePixel CS2 Skins`, `GTA 6 Lore`) and model selector.
- **Provider-Aware Key Pool Auto-Routing (`PeakCut/studio/ai.py`)**:
  - `key()` and `rotate_key()` dynamically inspect the active provider and select matching API keys from the pool (Gemini keys for Google, OpenRouter keys for OpenRouter, OpenAI keys for OpenAI).
  - Multi-key rotation cycles seamlessly within provider-matched keys upon encountering rate limits or quota boundaries.
  - `save()` preserves all existing keys in the pool without wiping keys across provider switches.
- **Dismissible AI Problem Banner & Auto-Clear (`PeakCut/studio/ai.py`, `PeakCut/studio/server.py`, `PeakCut/web/index.html`)**:
  - Added instant dismiss button (`✕ Dismiss`) on warning banners.
  - Successful test executions via `ai.test()` or `POST /api/ai/test` automatically purge cached errors via `clear_problem()` and `usage.forget_all()`.
  - Added `@app.post("/api/ai/clear-problem")` endpoint for manual and programmatic clearing.

### Fixed
- **Top Bar Header Overlap Collision (`PeakCut/web/index.html`)**:
  - Resolved collision where Creator navigation tabs (`#utabs`: Clips, Setup, Activity) overlapped directly over the `#global_ai_bar` model selector on creator pages.
  - Replaced absolute centering with flexbox static flow (`position: static !important; transform: none !important`), `margin-left: auto` for AI pill, and responsive 2-row wrapping on viewports under 980px.
- **Stale "Gemini Refused the Key" Banner**:
  - Fixed root cause where testing an OpenRouter key against Gemini previously lodged an error in `ai.problem` that persisted for 6 hours.
  - Synchronized provider addresses and models when switching providers in Settings (`#ai_provider` auto-populates correct `#ai_base` and `#ai_models`).
  - Added `ai_primary_model_select` change handler for instant persistence.
- **OpenRouter Free Model Catalog**:
  - Updated deprecated OpenRouter models to currently active free models (`google/gemma-4-31b-it:free`, `openrouter/free`).

### Tests and Verification
- Executed full test suite (`PeakCut/tests/run.py`): all 26 test suites PASSED with 0 errors.
- Verified individual test suites: `test_ai.py` (37 checks), `test_local.py` (42 checks), `test_seo.py` (17 checks), `test_post_text.py` (36 checks).
- Tested running daemon server on `http://127.0.0.1:8765`:
  - `GET /api/status`: verified `problem: ""` and `ready: true`.
  - `POST /api/ai/test`: verified HTTP 200 with `gemini-3.5-flash-lite` responding successfully in 17 tokens.
  - `GET /api/ai/catalog`: verified all 8 providers listed and available.


## [2026-11-20] — Audio/Video Lip-Sync Fix, Enhanced Split Framing, Multi-Key Pool Modernization & AI SEO Scan Fix

### Added
- **Interactive Audio & Webcam Delay Calibration Controls (`PeakCut/web/index.html`)**:
  - Added dedicated Voice Sync (`audio_delay`) and Webcam Sync (`facecam_delay`) dropdown selectors with clear millisecond calibration steps (-500ms to +500ms) across:
    - Clip Editor Dialog (`drawClipDlg`)
    - Creator Setup Form (`drawCreatorForm`)
    - Job Composer Form (`drawAdd`)
  - Integrated with `jobOptions()` and `request_render` for instant persistence and live re-renders.
- **Provider Auto-Detection & Key Pool Modernization (`PeakCut/studio/ai.py`, `PeakCut/web/index.html`)**:
  - Automatically detects provider from key prefixes (`AIza` or `AQ.` -> `[Gemini]`, `sk-or-` -> `[OpenRouter]`, `gsk_` -> `[Groq]`, `xai-` -> `[Grok]`, `sk-` -> `[OpenAI]`).
  - Added per-key `[⚡ Test Key]` direct test button and `[⚡ Test All Keys]` batch validator with live latency (ms) and status pill feedback.
  - Multi-endpoint test router in `test_key` routes test queries directly to the correct provider endpoint (Google AI Studio, OpenRouter, Groq, xAI) regardless of which provider is currently selected in the dropdown.
  - Automatically pre-fills recommended models and base URL addresses upon switching providers in the AI service dropdown.
  - Dynamically shows/hides the Address (`#ai_basewrap`) field for `custom`, `ollama`, and `openrouter` services.
  - Added persistent `#ai_test_result_box` below the Save button displaying clear confirmation (`✅ Model responded in Xms`) without disappearing.

### Fixed
- **Root Cause of Audio/Video Lip-Sync Delay in Live Clips (`PeakCut/studio/live.py`, `PeakCut/studio/jobs.py`)**:
  - Discovered and removed hardcoded default `0.25` (250ms) delay forced on all live stream clips (`live.py:738` and `jobs.py:554`).
  - Set default delay to `0.0s`, locking live stream clips to the natural 0.00s broadcast lip-sync alignment where mouth movement and audio waveform bursts match at the exact millisecond.
- **Split Layout Framing Adjustments (`PeakCut/studio/render.py`)**:
  - **Top Facecam**: Shifted camera higher up (`fh_clean = max(10, int(fh * 0.70))`), centering the streamer's head and facial expressions prominently while cropping out excess sweater/chest and overlay elements.
  - **Bottom Gameplay**: Implemented dynamic horizontal cropping (`gx = max(fx + fw + 2, 260)`) starting past the streamer's broadcast webcam box. Completely eliminates the streamer's small webcam overlay from the game view while keeping 100% of GTA 6 center dialogue subtitles and HUD visible.
  - Verified visually on `rendered_split_half_test.jpg` and `rendered_split_gamer_test.jpg`.
- **"✨ AI Scan Video & Fix SEO" Button & Script Syntax (`PeakCut/web/index.html`)**:
  - Fixed duplicate `if (a === "copy") {` check and matching extra closing brace `}` which previously caused script parsing issues.
  - Upgraded `re_ai_seo` click handler to fallback to `D.jid` and `D.cid` so button clicks never fail with undefined job/clip IDs.
  - Verified `/api/jobs/{jid}/clips/{cid}/ai_seo` multimodal frame inspection returning grounded scene hooks and tags.

### Tests and Verification
- Compiled all studio and test python files with `compileall`: 0 errors.
- Executed full test suite (`PeakCut/tests/run.py`): all 31 suites PASSED (690+ assertions).
- Verified `/healthz` and `/api/ai` on live server daemon (port 8765): HTTP 200 OK.
- Tested `POST /api/ai/keys/test-all`: verified Keys #0, #1, #2 active with Quota OK (~764-1100ms latency).

## [2026-11-20] — Visual Layout Preview Suite: Real Stream Previews, Phone Mockup Showcase & Fullscreen Comparison Gallery

### Added
- **True 9:16 Vertical Smartphone Screen Mockups (`PeakCut/web/index.html`)**:
  - Eliminated squashed landscape preview boxes and replaced them with true vertical smartphone frames (`144px x 256px` with 9:16 aspect ratio, speaker notch, Shorts indicator, side like/comment icons, and cyan dimension tag).
  - Shows the complete vertical YouTube Short from top to bottom without edge clipping or squashing.
- **Authentic IShowSpeed GTA 6 Broadcast Previews (`PeakCut/web/brand/layout-*.jpg`)**:
  - Re-rendered all 12 thumbnail variations directly from IShowSpeed's live GTA 6 stream (`output/native_sync.mp4`):
    - Real streamer facecam reaction (`[0, 334, 258, 136]`) with zero void bars.
    - Punchy viral YouTube Shorts captions (`Arial 78pt`, bright yellow with 7px heavy black outline and shadow).
    - Modern neon hook banner (`SPEED FOUND GTA 6 SECRET! 💀`).
    - Glowing cyan broadcast divider line (`#00F0FF`).
- **High-Contrast Professional Typography & Card Styling (`PeakCut/web/index.html`)**:
  - Replaced unreadable dark-brown titles with crisp `#FFFFFF` white headers.
  - Set descriptions to clear, high-contrast `#CBD5E1` light grey.
  - Added vibrant glowing orange pill badges (`#FF9040`).
- **Interactive Category Filter Tabs & Smooth Animations (`PeakCut/web/index.html`)**:
  - Added top filter tabs: `All Formats (9)`, `🔥 Facecam + Game (Best for Streamers)`, `🎮 Pure Gameplay (No Cam)`, `✨ 16:9 Social & Ambient Blur`.
  - Added silky cubic-bezier hover lift (`translateY(-5px)`), phone frame scale-up (`scale(1.03)`), and active orange glow borders.
- **Interactive Phone-Frame Showcase in Creator Setup (`web/index.html`)**:
  - Added a prominent, interactive phone frame mockup directly inside `Creator Setup -> Clips` showing exactly how the chosen layout and webcam position will look on mobile screens.
  - Displays dynamic specs: resolution breakdown, subtitle visibility confirmation, and layout virality recommendation.
  - Added **Quick Switch Strip**: a row of miniature preview cards allowing 1-click layout switching with immediate visual feedback.
- **Fullscreen Layout Comparison Gallery Modal (`web/index.html: #layout_gallery_dlg`)**:
  - Accessible via `[🖼️ Compare All 9 Layouts Fullscreen]`: opens a side-by-side visual comparison gallery of all 9 layouts with high-res thumbnails, pros/cons, best-use streamer scenarios, and 1-click `[Select This Layout]` buttons.
- **Live Layout Preview in Clip Editor (`web/index.html: drawClipDlg`)**:
  - Added live preview card next to the Layout and Webcam Position dropdowns inside the clip editor dialog, allowing creators to see how a clip will be recomposed before re-making it.
- **Visual Thumbnail Tiles in Composer (`web/index.html: drawAdd`)**:
  - Upgraded Composer layout selector buttons to display real rendered preview thumbnails instead of plain abstract CSS bars.

### Fixed
- **FFmpeg Filter Expression Syntax Bug in `studio/render.py` (Line 442)**:
  - Fixed literal `(H-fg_h)/2` in `overlay` filter by evaluating Python integer expression `{(H-fg_h)//2}`, eliminating FFmpeg `Invalid argument` crashes when rendering with `blur` or `zoom` layouts.

## [2026-11-20] — Upstream Synchronization with GitHub (origin/main) & Safe Custom Features Preservation

### Added & Merged from Upstream (`origin/main`)
- **Non-AI Fast Hashtags Engine (`studio/hashtags.py`, `tests/test_hashtags.py`)**:
  - Automatically derives 3 to 5 relevant hashtags directly from title/description/gameplay without requiring AI inference or burning API tokens.
- **Day-Long Video Memory Optimization (`studio/media.py`, `tests/test_longvideo.py`)**:
  - Stream-inspects hours-long VODs and full 24-hour recordings with minimal RAM footprint.
- **Windows Busy/Antivirus File Locking Resilience (`studio/jobs.py: _put_in_place`, `tests/test_jobsave.py`)**:
  - Adds retry mechanism with exponential backoff for atomic saves on Windows when search indexers or antivirus scanners temporarily lock `job.json`.
- **Proxy Security Hardening (`studio/server.py: _PROXY_CIDRS`, `tests/test_hardening.py`)**:
  - Restricts trusted proxy headers to private IP ranges, preventing IP spoofing.
- **MP4 Metadata Tagging (`studio/render.py`)**:
  - Injects native `title` and `description` MP4 container tags into exported videos.
- **Speech Model Timeout & Multi-Language Support (`studio/fetch_model.py`, `studio/transcribe.py`, `tests/test_speech.py`)**:
  - Added Arabic speech model exporter and graceful retry on model download stalls.

### Preserved Custom Features (Zero Overwrite, 100% Retained)
- **Interactive Multi-Key Pool & Auto-Rotation (`studio/ai.py`, `studio/server.py`, `web/index.html`)**:
  - Multi-key pool supporting multiple Gemini and OpenRouter keys with auto-rotation on 429 quota exhaustion.
  - Per-key live testing (`POST /api/ai/keys/{idx}/test`), auto-test on key add, failover sequence cards, and high-contrast status badges.
- **Precise Audio/Video Synchronization (`studio/render.py`, `studio/jobs.py`)**:
  - Sample-accurate decode seeking, PTS clock reset, 0.00ms acoustic caption onset, and CFR lock (`-fps_mode cfr`).
- **Modern Split Layouts & Sub-Bar Purge (`studio/render.py`)**:
  - Modern viral split (1/3 Cam, 2/3 Game) and clean 50/50 split with bottom 12% streamer sub-bar auto-purge.
- **Native YouTube Cloud Scheduling on Queue (`studio/posting.py`, `studio/accounts.py`, `web/index.html`)**:
  - Instant YouTube queue upload with native `publishAt` RFC3339 1-hour scheduling.
- **720p Live Ingestion Lock & Rolling Window Triggers (`studio/live.py`, `studio/creators.py`)**:
  - YouTube live streams locked to 720p to eliminate packet lag, with banned single-word noise filters.
- **Grounded Visual Anti-Hallucination Engine (`studio/brain.py`, `studio/jobs.py`)**:
  - Physical video frame inspection preventing hallucinated titles across all scenes (elevators, rooms, outdoor).

### Tests and Verification
- Executed complete 31-suite test runner via `PeakCut/tests/run.py` against isolated test server:
  - **All 31 test suites passed (690+ total checks passed, 0 failures, 100% success)**.
  - Passed suites: permissions (58), abuse/limits (42), queue under load (33), long video memory (5), deleting (19), Windows job save (5), big text (25), hashtags (19), chunked uploads (25), AI services (37), local dashboard key (42), Roman Urdu captions (28), captions toggle (16), social connections (44), new-version notice (20), default limits (9), caption collision (20), ad breaks (8), answers (11), AI retry (18), game detection (32), facecam detection (32), live recording times (18), fresh installs (22), storage folder (20), security (21), YouTube Shorts SEO (17), robustness logs (11), speech models (42), post text rewrite (36), live stops (4).
- Production PeakCut server daemon running cleanly on port 8765 with live Gemini key pool active.

## [2026-11-20] — Professional Multi-Key Pool Upgrade & Per-Key Live Testing Engine

### Added
- **Selected Models & Failover Sequence Showcase Card (`studio/ai.py`, `web/index.html`)**:
  - Added dedicated card at top of AI settings visually showcasing all configured models in priority order:
    - ⚡ **1st Primary Model** (e.g. `gemini-3.5-flash-lite`): Active inference engine for live clips, facecam detection, and grounded hooks.
    - 🔄 **Fallback #1** (e.g. `gemini-3.1-flash-lite`): Auto-engages if primary hits rate limit or quota freeze.
    - 🔄 **Fallback #2** (e.g. `gemini-flash-lite-latest`): Emergency backup failover.
- **Per-Key Live Testing Engine (`studio/ai.py`, `studio/server.py`, `web/index.html`)**:
  - Implemented `ai.test_key(index)` and `ai.test_all_keys()`: sends an active probe to Google AI Studio / OpenRouter to verify key validity, quota status, and latency (ms).
  - Added backend endpoints `POST /api/ai/keys/{idx}/test` and `POST /api/ai/keys/test-all`.
  - Added `[⚡ Test Key]` button on every single key row with live inline feedback (`✅ Working (4462ms)`, `⚠️ Quota Exhausted`, or `❌ Invalid Key`).
  - Added global `[⚡ Test All Keys]` button in pool header to test all pool keys simultaneously.
  - Implemented **Auto-Test on Key Add**: when pasting a key and clicking `[➕ Add Key]`, PeakCut immediately probes the new key against Gemini and confirms live health with a toast notification.
- **High-Contrast, Crystal-Clear Standby & Active Badges (`web/index.html`)**:
  - Replaced the low-contrast faded grey standby text with vibrant, crystal-clear high-contrast green badges:
    - **Active Key**: `🟢 Live / Active` (High-contrast emerald with glowing dot).
    - **Standby Key**: `🟢 Standby (Ready)` (High-contrast mint/emerald with visible green border and glowing dot).

### Fixed
- Fixed `list_models()` illegal header error when pool contains multiple keys separated by newlines.
- Synchronized `render.CAPTION_LEAD = 0.00` and repaired try-block indentation in `render.py`.
- Verified live key health: Key #1 (`...eJ6Q`) and Key #2 (`...ihtA`) both verified HTTP 200 OK with `gemini-3.5-flash-lite`.

## [2026-11-20] — YouTube Live /streams URL Normalization & Netscape Cookies Ingest

### Added
- **Fresh Netscape Cookies Sync (`PeakCut/data/cookies.txt`, `PeakCut/cookies.txt`, `PeakCut/data/youtube_cookies.txt`)**:
  - Ingested 48 fresh session and rolling timestamp cookies (including `LOGIN_INFO`, `__Secure-1PSIDTS`, `__Secure-3PSIDTS`, `SID`, `SAPISID`) directly from user browser JSON.
  - Resolved `yt-dlp` YouTube bot challenge and successfully verified live stream resolution for IShowSpeed's GTA 6 broadcast.

### Fixed
- **YouTube Live Channel `/streams` URL Normalization Bug (`studio/live.py`)**:
  - Fixed regex in `normalize(url)` to strip tab suffixes (`/streams`, `/videos`, `/featured`, `/live`, `/community`) and normalize them to `/live`.
  - Added automatic `url = normalize(url)` invocation inside `resolve(url)` to guarantee that any channel URL variant passed to `yt-dlp` resolves the live broadcast rather than a channel tab/playlist.
  - Eliminated the infinite `Connecting to the stream` loop when creator channels contain `/streams` in their URL.

### Tests and Verification
- Ran full test suite via `PeakCut/tests/run.py`: All 21 test suites passed (56 permissions, 40 abuse/limits, 32 queue, 26 AI services, 28 Roman Urdu, 32 games, 32 facecam, 17 fresh install, 21 security, 17 SEO checks passed).
- Live stream extraction verified: `live.resolve("https://www.youtube.com/@IShowSpeed/live")` successfully resolved active broadcast title `🔴 GTA 6 FINALE LAST MISSION 90% RIGHT NOW GET IN HERE!` with 2 playable stream tracks.

## [2026-11-20] — Multi-API Key Pool & Auto-Rotation, Universal Scene Grounding, 720p Ingest & AI Scan Fix

### Added
- **Interactive Multi-Key Pool UI & Add/Remove System (`studio/ai.py`, `studio/server.py`, `web/index.html`)**:
  - Replaced the plain multi-line `<textarea>` in Settings -> AI with an interactive **🔑 API Keys Pool Card**:
    - Each key is listed row-by-row with index (`Key #1`, `Key #2`, etc.) and masked string (e.g. `AQ.Ab8...eJ6Q`).
    - Real-time status badges: `🟢 Live / Active` for the key currently bearing the query load; `⚪ Standby (Ready to auto-rotate)` for backup keys.
    - Each key has an individual red `🗑️ Remove` button with instant API deletion.
    - Integrated `[➕ Add Key]` row with dedicated input box allowing users to easily paste and add keys one by one into the pool.
    - Added backend endpoints `POST /api/ai/keys` (with duplicate prevention) and `DELETE /api/ai/keys/{idx}`.
    - Key string storage capacity expanded from 400 to 8000 characters to safely manage 20+ keys.
- **Multi-API Key Pool & Automatic Rate/Quota Rotation (`studio/ai.py`, `web/index.html`)**:
  - Implemented multi-key pooling supporting multiple API keys (comma or newline separated).
  - Added `all_keys()`, `rotate_key()`, and `_retry_on_quota` wrapper: when any active key encounters HTTP 429, ResourceExhausted, or token exhaustion, PeakCut automatically switches to the next available working key in the pool and retries without user intervention.
  - Added native OpenRouter free models fallback pool (`google/gemini-2.0-flash-exp:free`, `meta-llama/llama-3.3-70b-instruct:free`, `qwen/qwen-2.5-72b-instruct:free`, `mistralai/mistral-small-24b-instruct-2501:free`).
  - Upgraded Settings AI interface with comfortable multi-line `<textarea>` for key entry and real-time pool status counter.
- **Universal Scene Grounding & Anti-Hallucination Engine (`studio/brain.py`, `studio/jobs.py`)**:
  - Implemented universal truthfulness constraints across all environments (rooms, hallways, elevators, swimming pools, streets, vehicles).
  - Explicitly banned inventing fake vehicles or actions (such as non-existent bikes or car crashes) when the streamer/character is exploring or confused.
  - Sits on top of Gemini Multimodal Vision: every newly generated clip now inspects physical video frames to anchor the hook, title, and description directly to on-screen reality.
  - Fixed `clip010`: replaced hallucinated "Grand Theft Auto VI Insane Bike Reaction! 🚲🔥" with accurate grounded title "Speed Gets Completely Confused Looking For A Bike! 🚲😭 #Shorts" ("SPEED SEARCHING FOR THE BIKE 🚲").
- **720p Live Stream Resolution Ingestion Lock (`studio/live.py`)**:
  - `resolve(url, quality)` dynamically inherits the creator's `quality` setting (default 720p).
  - Prevents heavy DASH desync by selecting 720p stream formats for much tighter A/V alignment and lower CPU overhead.

### Fixed
- **AI Scan Video & Fix SEO Server 500 & Fetch Error (`studio/server.py`, `web/index.html`)**:
  - Resolved `NameError: name 'brain' is not defined` by adding missing `brain` import to `server.py`.
  - Added robust fallback to transcript analysis if vision analysis is unavailable.
  - Updated frontend `re_ai_seo` handler to accept both `res.clip` and root `res` objects.
  - Verified live endpoint returning HTTP 200 on `clip010`.
- **Post-Upload Success Dialog Button Cut-off (`web/index.html`, `creator.json`)**:
  - Upgraded `.dlg-foot` with `flex-wrap: wrap; gap: 10px; width: 100%` and `flex: 1 1 180px` button distribution.
  - Completely eliminated horizontal overflow where the left button was cut off ("ep on Disk").
  - Set default `post_cleanup: "keep"` for clean, uninterrupted uploads without annoying popups.

### Tests and Verification
- Executed all 21 test suites in `PeakCut/tests/run.py` — **All 21 test suites passed 100%**.
- Verified `ai.all_keys()`, `ai.rotate_key()` and fallback mechanisms.
- Verified live server daemon running on port 8765.

### Documentation
- Updated `CHANGELOG.md`, `TASKS.md`, `PROJECT_STRUCTURE.md`, `SYSTEM_DESIGN.md`.



### Fixed
- **Captions Off Setting Ignored Bug (`studio/live.py`)**:
  - Resolved bug where clips generated during live streams continued to burn in captions even when the creator had disabled "Generate captions" in Setup (`captions: false`).
  - Previously, `live.py: _add_clip` called `c.update(..., captions=self.job["options"].get("captions", True))` which read from stale initial session options instead of the creator's live settings.
  - Fixed `_add_clip` to prioritize `self.settings.get("captions")` over `self.job["options"]`, strictly honoring the creator's toggle.
- **Active Live Session Settings Real-Time Sync (`studio/server.py`)**:
  - In `edit_creator(cid, body)`: When user saves creator settings in UI, active live sessions now instantly sync `s.job["options"]` (`captions`, `layout`, `style`, `quality`) and clear cached game state `s.game = None`, ensuring immediate application without needing to restart the stream.
- **Queue & Clip Runner Strict Fallback (`studio/jobs.py`)**:
  - In `jobs.py: render_one` and queue clip runner: If a clip's `captions` property is missing or undefined, it dynamically checks the creator's profile settings before falling back, preventing unwanted caption generation.
  - In `web/index.html: drawClipDlg`: Clip editor dialog checkbox now checks both clip and parent job options, preventing an unchecked setting from being silently re-enabled on remake.
- **Verified Zero-Captions Render**:
  - Re-rendered `clip005` with `captions: false`: Confirmed via `clip005_nocaptions_frame2.jpg` that animated subtitles (`GUY WYMAN HELPING`) are 100% removed, leaving middle gameplay completely clean.

### Tests and Verification
- Executed all 20 test suites via `tests/run.py`: All 20 suites passed, including `turning captions off and back on (16 checks passed)`.
- Verified server daemon active on port 8765.

### Documentation
- Updated `CHANGELOG.md`, `TASKS.md`, `PROJECT_STRUCTURE.md`, `SYSTEM_DESIGN.md`.


## [2026-11-20] — Edge-to-Edge Compact Facecam (1/3 Top) & Subtitle-Safe In-Game Zoom-Out (2/3 Bottom)

### Added
- **Edge-to-Edge Compact Top Facecam (1080x640) (`studio/render.py`)**:
  - Replaced floating 520px facecam box and blurred background void in `split` layout.
  - Streamer's webcam now anchors directly at `y=0` and fills the full horizontal width (1080px) edge-to-edge.
  - Height optimized to compact 640px (1/3 of vertical screen) so the streamer's face, hair, and shoulders are 100% visible with natural proportions and zero voids.
- **Subtitle-Safe In-Game Zoom-Out Framing (1080x1280) (`studio/render.py`)**:
  - Expanded gameplay canvas to a massive 1280px height (2/3 of vertical screen).
  - Implemented exact subtitle-safe horizontal framing (`crop=min(in_w\,1040):in_h:(in_w-min(in_w\,1040))/2:0`):
    - Completely prevents cutting off the beginning and ending words of GTA 6 in-game dialogue subtitles.
    - Verified on `clip005` dialogue: *"Like you said, it's a cop town. Got Wyman helping out here, he'll text you the details."* — 100% fully visible with comfortable side margins.
    - Accurately excludes streamer overlays, chat, and stream borders from leaking into the game section.
- **Unified Layout Parity Across `split` and `split_half`**:
  - Upgraded both `split` and `split_half` layouts with subtitle-safe zoom-out framing.
  - Positioned broadcast divider (6px dark bar + 2px glowing cyan line `0x00F0FF@0.9`) cleanly between sections.
  - Positioned hook banner at `y=690` in `split` (just below the divider at the top of the gameplay) without obscuring streamer or dialogue.

### Tests and Verification
- Rendered real clip `clip005.mp4` with the new layout and extracted frame at 2.0s (`clip005_new_layout_frame2.jpg`).
- Visually inspected and verified:
  1. Top webcam: 1080px wide edge-to-edge, sitting at top, Speed fully visible.
  2. Bottom gameplay: 1280px tall, in-game dialogue subtitles complete without edge cutoff.
- Executed all 20 test suites via `tests/run.py` — 100% passed (0 errors).
- Restarted PeakCut server daemon on port 8765.

### Documentation
- Updated `CHANGELOG.md`, `TASKS.md`, `PROJECT_STRUCTURE.md`, `SYSTEM_DESIGN.md`.


## [2026-11-20] — Native Zero-Drift MP4 Clip Slicing & Manual Delay Dropdown Removal

### Added
- **Native Zero-Drift MP4 Clip Slicing (`studio/live.py`)**:
  - Live buffer segment concat upgraded from MPEG-TS (`.src.ts`) directly to ISO BMFF MP4 (`.src.mp4`):
    `ffmpeg -y -v error -fflags +genpts -f concat -safe 0 -i lst -c copy -movflags +faststart -avoid_negative_ts make_zero src.mp4`
  - In raw MPEG-TS, packet boundaries for AAC audio frames (~21.3ms) and H.264 video GOPs (~2.0s) have independent presentation timestamps with no unified index, causing ~516ms seeking offset during FFmpeg cut.
  - Concat to `.src.mp4` constructs exact sample index tables (`stts`, `ctts`, `stsc`), locking video frame 0 to audio sample 0 with 0.000s start time.
  - Downstream seeking in `render.py` (`-ss ... -i ... -avoid_negative_ts make_zero`) accesses sample-locked frames directly with 0ms drift.
  - Includes robust fallback to `.ts` if source codec cannot be muxed into MP4.

### Changed
- **Removed Confusing Manual Delay Dropdowns (`web/index.html`)**:
  - Completely removed `Voice / Audio Sync` and `Webcam / Lip Delay` selects from:
    1. Clip Editor Dialog (`#clipdlg`)
    2. Creator Settings Form (`drawCreatorForm`)
    3. Composer Options (`drawAdd` - removed "Sync calibration" box)
  - Removed obsolete `SYNC_OPTIONS` and `syncOpts` helper functions.
  - Standardized default `audio_delay: 0.0` and `facecam_delay: 0.0` across all options and creator profiles (`ducky-reloaded/creator.json`).
  - Clipping is now completely automatic and zero-touch without requiring manual milliseconds adjustments.

### Tests and Verification
- Executed all 20 test suites in `tests/run.py`: All 20 suites passed cleanly (0 errors).
- Tested FFprobe start time comparisons:
  - Raw `.ts` direct seek: Video start time `0.516667s` vs Audio start time `0.000000s` (~516ms drift).
  - Remuxed `.mp4` direct seek: Video start time `0.000000s` vs Audio start time `0.000000s` (0ms drift).
- Verified PeakCut server daemon returns HTTP 200 and serves clean `index.html` without delay dropdowns.

### Documentation
- Updated `CHANGELOG.md`, `TASKS.md`, `PROJECT_STRUCTURE.md`, `SYSTEM_DESIGN.md`.


## [2026-11-20] — Clean Edge-to-Edge 50/50 Split (Zero Blur Bars) & Full In-Game Subtitle Framing

### Added
- **Clean Edge-to-Edge 50/50 Split Layout in `split_half` (`studio/render.py`)**:
  - Top half (1080x960): Streamer facecam fills the entire upper half edge-to-edge without letterbox/blur bars on top or bottom.
  - Bottom half (1080x960): Center gameplay fills the entire lower half edge-to-edge without letterbox/blur bars, perfectly framing in-game dialogue subtitles and action with zero edge cutoff.
  - Divider: Sleek 6px dark broadcast bar with 2px glowing cyan accent line (`color=0x00F0FF@0.9`).
  - Verified on `clip004_v2_clean.jpg`: Speed fills top 1080x960 cleanly, bottom game displays GTA 6 subtitle (`Oh shit! Little homefield advantage, then.`) with zero blur bars.

## [2026-11-20] — In-Game Subtitle Safe Zoom-Out Layout, Trigger Word Flooding Elimination & Live Delay Inheritance

### Added
- **In-Game Subtitle Safe Zoom-Out Layout in `split_half` (`studio/render.py`)**:
  - Upgraded `split_half` bottom half (1080x960): Instead of horizontally cropping 313px on left and right, the 16:9 gameplay is scaled with `decrease` to 1080x608 and centered over an ambient blurred background (`boxblur=25:25`).
  - Guarantees 100% visibility of in-game GTA 6 dialogue subtitles, radar mini-map, health bars, and HUD with zero edge cutoff.
- **Trigger Word Flooding Prevention (`studio/live.py`, `studio/creators.py`)**:
  - Implemented `BANNED_SINGLE_WORD_TRIGGERS` in `studio/live.py`: filters out common everyday words ("bro", "shit", "what", "dead", "perfect", "easy", "kya", "yo") from trigger matching.
  - Cleared dictionary-dump from `MASTER_TRIGGER_WORDS` and creator profiles (`ishowspeed/creator.json`, `ducky-reloaded/creator.json`), retaining only genuine clipping commands ("clip that", "clip it", "clip karo", "ye clip karo").
  - Restores dual AI virality judges (Words Judge & Reaction Judge) so live streams are not flooded with 13 generic "Hand" clips in 8 minutes.
- **Persistent Live Stream Audio Delay Inheritance (`creator.json`, `studio/live.py`)**:
  - Saved `audio_delay: 0.150` (+150ms) into `ishowspeed/creator.json`, ensuring all newly recorded live streams and clips inherit the voice calibration automatically.

## [2026-11-20] — Multimodal Vision Scene Analysis, Visually Grounded Hooks & SEO, and 1-Click AI Video Scan in Clip Editor

### Added
- **Multimodal Video Frame Scene Understanding (`studio/ai.py`, `studio/brain.py`)**:
  - Added `ai.see_json(prompt, image, schema, timeout)` to inspect video frames directly with Gemini multimodal vision (`gemini-3.5-flash-lite`).
  - Added `brain.describe_multimodal(image_bytes, text, title, uploader, game, timeout)`: extracts actual visual details (e.g. pink inflatable flamingo pool float, poolside party, police car, specific reaction) and combines them with spoken transcript.
  - Generates highly contextual, grounded hooks, titles, descriptions, and YouTube search tags that accurately reflect what is physically visible in the clip.
- **Visual Scene SEO Integration in Render Pipeline (`studio/jobs.py`)**:
  - Added `_extract_frame_bytes(src, t)` using fast ffmpeg pipe extraction (~50ms).
  - In `jobs.py: render_one()`, if hook is generic or needs AI SEO, the actual frame is extracted from the video and analyzed via multimodal AI before burning the hook banner onto the video.
- **Live Multimodal Re-Scan API Endpoint (`studio/server.py`)**:
  - Added `POST /api/jobs/{jid}/clips/{cid}/ai_seo`: re-scans the clip's visual frame + spoken words, updates the clip metadata in `job.json`, and returns fresh visual SEO fields.
- **1-Click "✨ AI Scan Video & Fix SEO" Button (`web/index.html`)**:
  - Added gradient action button in Clip Editor (`#clipdlg`) alongside "Copy SEO".
  - On click, it triggers `/api/jobs/{jid}/clips/{cid}/ai_seo` and dynamically updates `Hook`, `Title`, `Description`, `Shorts Title`, `Search Tags`, and `Pinned Comment` live in the dialog.
  - Clicking "Save and re-make clip" applies the new visual hook banner to the video.

### Changed
- **Eliminated Repetitive Cliché Templates (`studio/brain.py`)**:
  - Removed repetitive few-shot attractor examples (such as `"THIS NPC HAS NO CHILL 💀"`) from `RULES` prompt.
  - Added strict negative constraints against generic template hooks (`"NPC HAS NO CHILL"`, `"BRO WAS NOT READY"`, `"FLAMINGO MAN IS UNHINGED"` unless genuinely applicable).
  - Updated `fallback_seo()` to use varied dynamic action patterns rather than static "NO CHILL" fallback.

### Tests and Verification
- Tested multimodal frame extraction and Gemini 3.5 Flash Lite visual scene recognition on `clip017.jpg` and `clip016.jpg`.
- Verified accurate identification of the giant pink flamingo pool float and poolside party scene.
- Verified test suite execution and clean syntax across all modules.



## [2026-11-20] — Extended Delay Range (±1000ms), New Video Sync Inheritance, Twitch Ad Slate Filter, Cookie Sync & Multi-line Box UI

### Added
- **Extended Delay Calibration Range (±1000ms / 1.0s) (`web/index.html`)**:
  - Implemented `SYNC_OPTIONS` and `syncOpts()` helper providing granular delay options from `-1000ms` (-1.0s) to `+1000ms` (+1.0s) in 50ms and 100ms steps.
  - Deployed across Creator Settings (`drawCreatorForm`), Composer Options (`drawAdd`), and Clip Editor Dialog (`drawClipDlg`).
- **Twitch Commercial Break Slate Auto-Detection (`studio/live.py`)**:
  - Integrated `quality.static_ranges(src, bucket=1.5)` in `live.py: _render`.
  - Clips with >40% static screen (such as Twitch's purple "Commercial break in progress" screen) are automatically detected and skipped with a descriptive log.
- **Multi-line Box Layout for Trigger Words & Post Footer (`web/index.html`)**:
  - Replaced single-line `<input>` with expandable `<textarea data-k="trigger_words" rows="4">` box with clean padding, border, and placeholder.
  - Replaced single-line `post_footer` with `<textarea data-k="post_footer" rows="2">`.
- **Automatic Browser Cookies Sync & JSON-to-Netscape Converter (`studio/media.py`)**:
  - Added `_convert_json_cookies()`: automatically watches for exported `cookies.json` in user Downloads or `data/` and converts all 91 cookies (including `LOGIN_INFO`, `SID`, `SAPISID`) into standard Netscape format.
- **CSP YouTube Compatibility (`studio/server.py`)**:
  - Added `https://www.youtube.com` into CSP `frame-src` alongside `https://www.youtube-nocookie.com`.

### Fixed
- **Voice Delay on New Videos & Live Streams (`studio/jobs.py`, `studio/live.py`)**:
  - Root cause resolved: `jobs.py: clean_options` was rejecting negative numbers and dropping delay parameters because they were missing from `DEFAULTS`. Added `audio_delay` and `facecam_delay` to `DEFAULTS`, allowing values between `-2.0s` and `+2.0s`.
  - Updated `jobs.py: create()` to inherit `audio_delay`, `facecam_delay`, `layout`, and `facecam_pos` directly from the creator profile for all newly queued videos and live recordings.
  - Updated `live.py: start_session` to pass creator delay settings into `jobs.create()`.
- **Default Subtitles & Layout for IShowSpeed & Ducky Reloaded**:
  - Updated `creator.json` profiles: set `layout: "split_half"`, `captions: true`, and `facecam_delay: -0.10` so subtitles are generated and split screen is active by default.
- **Direct Slice Transcription Timestamp Drift (`studio/jobs.py`)**:
  - Ensured direct audio slice transcription returns accurate word timings mapped onto the clip timeline, eliminating subtitle drift.

### Tests and Verification
- Executed full test suite (`PeakCut/tests/run.py`): all 20 test suites and over 350 individual checks passed (`ALL PASSED`).
- Tested `live.resolve()` with Netscape `cookies.txt` generated from user `cookies.json`.
- Tested `split_half` video generation, divider line rendering, and delay filter combinations (`trim`, `tpad`, `adelay`, `atrim`).
- Verified fresh PeakCut web server running healthy as a background daemon on port 8765 (`/healthz` returns `{"ok": true}`).



## [2026-11-20] — Classic 50/50 Split Refinement, Outro Subtitle Overlap Elimination, Precise Input-Seek & Delay Calibration Engine

### Added
- **Classic 50/50 Split Layout with Glowing Divider (`studio/render.py`)**:
  - Refined `split_half` layout: Top 960px is centered streamer webcam, bottom 960px is 16:9 gameplay.
  - Added a sleek broadcast divider between the halves (`drawbox=x=0:y=957:w=1080:h=6:color=0x141210:t=fill,drawbox=x=0:y=959:w=1080:h=2:color=0x00F0FF@0.9:t=fill`) with a 2px glowing cyan accent line.
  - Set `split_half` as the default layout across all creators and new jobs.
- **Outro Badge & Subtitle Overlap Elimination (`studio/render.py`)**:
  - Relocated Outro CTA badge from `y=1500` to bottom safe zone `y=1680`.
  - Subtitles in `split_half` are centered at `cap_y=1360`, providing 320px clean separation with zero overlap in the final 3.2 seconds of clips.
- **Clip Editor Dialog Context & Feedback (`studio/jobs.py`, `web/index.html`)**:
  - Fixed background render context: added automatic fallback user token assignment in `render_one` (`ctx._uid.set(job.get("user") or "u_local")`), preventing `RuntimeError: No signed-in user in this context` during editor clip re-renders.
  - Enhanced `#clipdlg` "Save and re-make clip": displays active spinner and status update while rendering, and pops success toast on completion.
  - Expanded sync calibration range (-300ms to +300ms in 25ms steps) across creator forms, clip editor dialog, and composer options.

### Changed
- **Accurate Input Seeking & Frame-Accurate Filter Timestamps (`studio/render.py`)**:
  - Restored `-ss {start}` BEFORE `-i {src}` for video slicing.
  - Combined with `[0:v]setpts=PTS-STARTPTS` and `asetpts=PTS-STARTPTS`, input frames and audio samples decode starting at 0.000s, perfectly matching ASS subtitle timeline `0.0 <= s <= dur`.
  - Updated cover thumbnail extraction to `-i {name}.mp4 -ss {cover_t}` to accurately capture the opening hook banner.

### Fixed
- **Missing Hook Banner & Subtitle Drift**:
  - Fixed issue where output-seeking (`-i` before `-ss`) caused `-filter_complex` to receive pre-cut frames and burn subtitles on discarded frames, shifting the entire subtitle timeline.
- **Clip Editor Dialog Controls Not Applying**:
  - Resolved issue where changes to Hook style, Caption style, Layout, Webcam Position, Voice Sync, and Lip Delay failed to render due to missing context credentials.
- **YouTube Player Embed Blocking**:
  - Updated CSP header to permit `https://www.youtube-nocookie.com` and added a floating "Watch on YouTube ↗" fallback button on stream cards.

### Tests and Verification
- Rendered `clip003` (IShowSpeed) in version 6 with `split_half` layout, `facecam_delay: -0.10`, and captions.
- Extracted and verified visual frames:
  - `speed_v6_f1.5.jpg`: Verified Hook banner ("SPEED ROASTING RANDOM NPCS 😂"), top facecam, glowing cyan divider line, and "HI LADIES" subtitle at `y=1360`.
  - `speed_v6_f44.5.jpg`: Verified Outro badge ("NEW CHANNEL • LIKE & SUBSCRIBE!") cleanly situated at `y=1680` with zero subtitle overlap.
  - Verified PeakCut web server running and healthy on port 8765 (`/healthz` returns `{"ok": true}`).
- Full test suite execution across all modules.



## [2026-11-19] — Multi-Creator Sync Calibration, CFR Audio Lock, Twitch Embed & YouTube Watch URL Fixes

### Added
- **Creator Sync Controls (`web/index.html`)**: Added 'Voice / Audio Sync' and 'Webcam / Lip Delay' dropdown controls in Creator Settings (`drawCreatorForm`) and in the Composer Options pane (`drawAdd`). Settings persist to `creator.json` and automatically apply to all generated clips.
- **Twitch Localhost Redirection (`web/index.html`)**: Automatically redirects from `127.0.0.1` to `localhost:8765` so Twitch's parent domain restrictions are satisfied, allowing the Twitch stream player to play directly inside PeakCut.
- **Instant Live Clip Action (`web/index.html`)**: Added an instant 'Clip last 30s' button and active live listening indicator to the stream card during background recording.

### Changed
- **FFmpeg Frame Sync Mode (`studio/render.py`)**: Switched from `-fps_mode passthrough` to `-fps_mode cfr` to eliminate variable-frame-rate (VFR) timestamp drift and maintain sample-accurate audio/video synchronization across the entire video.
- **Negative PTS Handling (`studio/render.py`)**: Replaced `setpts=PTS+(delay/TB)` for advance camera delays with `trim=start=...,setpts=PTS-STARTPTS` to prevent FFmpeg overlay frame dropping and freezing.

### Fixed
- **YouTube Live Stream Detection (`studio/profiles.py`)**: Fixed `live_now` appending `/live` to specific video watch URLs (`watch?v=...`), which was causing YouTube live streams to falsely show as 'Offline'.
- **YouTube Player IFrame Security (`web/index.html`)**: Added `origin` parameter and `referrerpolicy="no-referrer-when-downgrade"` to prevent Google bot challenge blocks on local embeds.

### Tests and Verification
- Tested `profiles.live_now` on `https://www.youtube.com/watch?v=hwSg39yIBGU` -> verified `live: True` and extracted exact title.
- Re-rendered Ducky Bhai `clip01.mp4` with calibrated sync and verified `ducky_calibrated_f49.jpg` at 49.15s with perfect acoustic-lip lock.
- Executed full PeakCut test suite (`tests/run.py`): All 21 test suites PASSED.


## [2026-11-19] — Schedule Cancellation, Single-Channel Post Exclusivity, Post-Upload Local File Cleanup, Universal Multilingual Triggers & Non-Destructive Split Facecam Framing

### Added
- **Schedule Cancellation System (`studio/posting.py`, `studio/account.py`, `studio/server.py`, `web/index.html`)**:
  - Added `posting.cancel_clip(job_id, clip_id)` to cancel all open scheduled posts for a clip.
  - Added `posting.forget_clip(job_id, clip_id)` to cancel scheduled posts if a clip is deleted from disk.
  - Added API endpoints: `POST /api/jobs/{jid}/clips/{cid}/unschedule` and `POST /api/bulk/unschedule`.
  - Added UI controls: inline `[✕]` cancellation button on scheduled status pills, `[✕] Cancel Schedule` in clip card footers, dialog button, and bulk action bar.
- **Single-Channel Exclusivity & Post-Upload Local File Deletion (`studio/posting.py`, `studio/creators.py`, `web/index.html`)**:
  - Once a video is uploaded to one channel, all pending posts for other channels are automatically cancelled to prevent duplicate cross-posting.
  - Added `post_cleanup` configuration (`"ask"`, `"auto"`, `"keep"`), defaulting to `"ask"`.
  - On `"auto"`, rendered clip media (`.mp4`, `.jpg`, `.ass`) is deleted from disk immediately upon successful upload.
  - On `"ask"`, a user-friendly confirmation prompt is displayed in the UI: *"Bhai yeh video upload ho chuki hai, is video ko delete karoon ya rakhna hai?"* with one-click `Delete from disk` or `Keep file` actions.
- **Universal Multilingual Trigger Words across All Creators (`studio/creators.py`)**:
  - Defined comprehensive `MASTER_TRIGGER_WORDS` covering English, Roman Urdu, and Hindi phrases (`clip that`, `clip it`, `clip karo`, `ye clip karo`, `isko clip karo`, `someone clip that`, `viral moment`, `kya baat hai`, `o bhai maro mujhe`, etc.).
  - Increased character limit in `_clean()` from 300 to 5000 characters to prevent accidental truncation of long trigger lists.
  - Auto-populated across existing creators (`Ducky Reloaded`, `IShowSpeed`, `MrBeast`) and new creator templates.
- **Visual Checkmark Badge & Split Default in Layout Selector (`web/index.html`)**:
  - Added active outline (`border: 2px solid var(--brand)`) and a circular checkmark badge (`✓`) via `.tile-o[aria-pressed=true]::after` for instant visual confirmation of selected layout and caption style.
  - Defaulted composer layout to `"split"` (`c?.layout || "split"`).

### Fixed
- **Streamer Facecam Auto-Framing & Chin Cutoff in Split Layout (`studio/render.py`)**:
  - Diagnosed that `scale={W}:{cam_h}:force_original_aspect_ratio=increase,crop={W}:{cam_h}:(in_w-out_w)/2:0` lopped off the bottom ~35% of the webcam, cutting off the streamer's mouth, chin, and chest.
  - Re-engineered split and split_half filtergraphs:
    - Top zone: Layered with a soft ambient blurred background of the room (`boxblur=25:25`), with the foreground facecam scaled to fit without clipping (`force_original_aspect_ratio=decrease`) and centered (`(W-w)/2:({cam_h}-h)/2`). Streamer's entire face, hair, headphones, chin, and collar remain 100% visible with zero distortion.
    - Bottom zone: Scaled with `force_original_aspect_ratio=increase,crop={W}:{game_h}:(in_w-out_w)/2:(in_h-out_h)/2` ensuring gameplay fills edge-to-edge with zero black void at the bottom.
  - Verified on Ducky Bhai GTA 6 video: re-rendered `clip01.mp4` and verified on `ducky_new_split_f25.jpg`.
- **Acoustic Subtitle Sync & Audio Drift Resilience Offline (`studio/jobs.py`, `studio/render.py`)**:
  - Normalized direct slice transcription timestamps to source timeline (`clip_base = float(clip["start"])`) to eliminate double-subtraction offset.
  - Upgraded `build_ass` in `render.py` to auto-detect both local slice timestamps and source timeline timestamps without dropping words.


## [2026-11-19] — Direct YouTube Publishing to The Paradox Files, Story-Driven SEO Engine & Resilient Live Speech Trigger Engine

### Added
- **Direct YouTube Publishing to "The Paradox Files" (`F:\Games\yt-what if videos`, `PeakCut/data/users/u_local/accounts`)**:
  - Integrated Google OAuth credentials and refreshed tokens from `F:\Games\yt-what if videos\token.json`.
  - Authenticated and verified YouTube channel ownership: `The Paradox Files` (`yt_UCYRTCqsgp0Trd_7XjSbBT6g`).
  - Successfully uploaded viral Short: [https://www.youtube.com/shorts/Usfig_Bpa0g](https://www.youtube.com/shorts/Usfig_Bpa0g) (`Usfig_Bpa0g`).
  - Auto-posted engaging top discussion comment (ID: `UgywL756YaJyAj5OZDh4AaABAg`).
- **Story-Driven SEO & Pinned Comment Engine (`studio/brain.py`)**:
  - Re-engineered `RULES` system prompt in `studio/brain.py` to enforce a 5-line narrative "khulasa" (story breakdown), provocative discussion-starting pinned comment, high-converting channel CTA, and 8+ high-traffic hashtags.
  - Upgraded heuristic `fallback_seo` with GTA 6 mission, police chase, beggar theft, dog AI, and physics scenarios with authentic storytelling and high CTR formatting.

### Fixed
- **Speech Trigger Recognition Engine ("Always clip the last 30 seconds when someone says") (`studio/live.py`)**:
  - **Chunk Boundary Splitting Elimination**: Refactored `_triggers()` to scan a rolling window of the last 50 words (`self.words[-50:]`) rather than isolating the incoming audio chunk (`new_words`). Multi-word phrases like `"someone clip that"` or `"you better clip that"` spanning across audio chunk borders now match seamlessly.
  - **Apostrophe & Unicode Normalization**: Normalized curly quotes (`’`, `‘`, `´`, `` ` ``) to ASCII `'` and supported both with-apostrophe and without-apostrophe comparisons so that speech engine transcripts (`that's`, `that’s`, `thats`) always match user phrases.
  - **Roman Urdu & Hindi Phonetic Flexibility**: Added automated normalization for common variations (`yeh` -> `ye`, `is ko` -> `isko`, `kardo`/`karde` -> `karo`, `kr` -> `kar`).
  - **Dynamic Cooldown Tuning**: Reduced trigger cooldown from 45 seconds to 25 seconds, allowing back-to-back hype moments in live streams to be captured.
  - **Typo Protection**: Filtered out accidental single-character phrases (e.g. `clip v`) to prevent false triggers.
  - Verified with comprehensive automated integration test suite (`scratch/test_live_triggers_integration.py`).

## [2026-11-19] — Modern Viral Split Layout (1/3 Cam, 2/3 Game), 0ms Acoustic Subtitle Sync, Contextual Narrative Hooks & End-to-End 1080p/720p Quality Pipeline

### Fixed
- **Root-Cause Resolution of Low Quality / 360p Download Fallback (`studio/media.py`, `studio/live.py`)**:
  - Diagnosed that `player_client: ["android", ...]` in yt-dlp options caused YouTube's SABR streaming experiment to strip 720p/1080p stream URLs on the Android client, forcing yt-dlp to silently downgrade to format 18 (640x360 @ 421 kbps).
  - Explicitly registered the system's Node.js binary (`C:\Program Files\nodejs\node.exe`) in yt-dlp `js_runtimes` and removed the restricted Android client override.
  - Verified with direct probe: `media.download` now fetches true 1920x1080 @ 60fps streams (3.56 Mbps AVC1 + Opus audio) across all jobs and future clippings.
  - Re-rendered `speed_stolen_perfect_split.mp4` at 5.88 Mbps 1080x1920 with crystal-clear visual fidelity and verified on test frames.

### Added
- **Modern Viral Gamer Split Layout (`layout: "split"`) (`studio/render.py`, `web/index.html`)**:
  - Re-engineered vertical split framing to match viral TikTok/Shorts aesthetics: Top ~1/3 (1080x640) for facecam reaction with headroom, Bottom ~2/3 (1080x1280) for zoomed, expansive gameplay.
  - Added high-quality Lanczos scaling (`flags=lanczos+accurate_rnd`) and unsharp filter (`unsharp=5:5:0.5:5:5:0.0`) to avoid blurriness.
  - Increased video export bitrate to 8 Mbps (`-crf 18 -b:v 8M -maxrate 12M -bufsize 16M`) with 160k AAC audio.
- **End-to-End Video Quality System (1080p vs 720p) (`studio/creators.py`, `studio/jobs.py`, `studio/media.py`, `web/index.html`)**:
  - Added `quality` setting to `DEFAULTS` and `_clean` in `studio/creators.py`, defaulting to 1080p.
  - Creator profile now includes "Default video quality" selector (1080p vs 720p).
  - Main composer bar respects creator's default quality (defaulting to 1080p) and toggles active state properly.
  - `studio/jobs.py` inherits creator's quality setting for all downloads and passes it to `media.download` and `media.download_section`.
  - Added quality support in `request_render` for re-rendering clips in higher quality.
- **Context-Specific Narrative Hooks (`studio/brain.py`)**:
  - Banned repetitive, generic templates ("WAIT TILL THE END", "BRO WAS NOT READY FOR THIS", "BRO REGRETTED THIS").
  - Enforced dynamic narrative formula: `[KEY ACTOR] + [HILARIOUS ACTION/EVENT] + [EMOJI]` (e.g. `BEGGAR STOLE SPEED'S FOOD 😭💀`).
  - Upgraded fallback heuristic to extract narrative events from speech rather than defaulting to static clichés.
- **Short Video Support (< 90s) (`studio/jobs.py`)**:
  - Added automatic fallback for videos under 90s so that short clips or highlights submitted by the user are processed and formatted without being dropped.

### Fixed
- **Subtitle Latency Desync Bug (`studio/jobs.py`)**:
  - Eliminated the `+ off` offset bug in `_caption_words` (`w["s"] + local_start` instead of `w["s"] + off + local_start`), locking subtitles to exact acoustic onset with 0ms latency.
- **YouTube vs Twitch Channel Fallback (`studio/server.py`)**:
  - Locked channel selection to the exact requested platform URL, preventing YouTube tasks from switching to Twitch.
- **YouTube Mobile Client Bypasses (`studio/media.py`, `studio/live.py`)**:
  - Added `player_client: ["android", "ios", "mweb", "web"]` to yt-dlp extractor args to bypass bot checks without needing cookie uploads.
- **Stream Buffer Boundary Clamping (`studio/live.py`)**:
  - Clamped manual clips to available buffer boundaries so they never fail with "That part of the stream is no longer in the buffer".

## [2026-11-19] — Sample-Accurate Timeline Seeking, Audio/Video Keyframe Desync Elimination, Twitch Download Fallback & One-Click Direct Posting

### Fixed
- **Root-Cause Elimination of ~960ms A/V Desync on Live Clips (`studio/render.py`)**:
  - Identified that fast input-seeking (`-ss start -i file.ts`) on MPEG-TS concatenated streams jumped to the nearest preceding transport keyframe (e.g. 12.050s instead of 13.010s), while audio demuxed from 13.010s, creating an artificial 960ms delay where video lagged behind audio.
  - Implemented sample-accurate decode seek for clips (`-i file.ts -ss start -t dur`) and 2-step seek for long files (`-ss pre -i file -ss offset -t dur`).
  - Verified with frame-by-frame MSE and Whisper alignment: MSE dropped from 745.38 to 0.67, aligning frame 0 and audio start down to 0.000ms.
- **Creator Settings Sync Parameter Inheritance (`studio/creators.py`, `studio/live.py`, `studio/jobs.py`)**:
  - Added `facecam_pos`, `facecam_delay`, `audio_delay`, `hook_style`, `outro_cta`, and `outro_text` to `DEFAULTS` and `_clean` in `creators.py` so sync settings are not stripped.
  - Updated `Session._add_clip` in `live.py` and `jobs.render_one` in `jobs.py` to inherit creator delay presets.
- **Twitch HLS Format Selection & Range Download Fallback (`studio/media.py`)**:
  - Updated audio format query to support Twitch `audio_only` streams alongside YouTube `m4a` streams.
  - Added fallback in `download_section` for HLS streams where `download_ranges` is not supported.
- **Uploaded File Deduplication (`studio/jobs.py`)**:
  - Extended `prior_spans` matching to include local file uploads and title matching (e.g. `ohnepixel raw`), preventing duplicate clips when re-processing the same raw video file.
- **One-Click Instant "Post now" (`web/index.html`, `studio/posting.py`, `studio/server.py`)**:
  - Removed confirmation dialog on "Post now" click, posting immediately to selected accounts.
  - Supported `force=True` on backend to prevent false duplicate rejection.

## [2026-11-20] — Live Stream Resilience, Automatic Audio Sync (+250ms), Subtitle-Safe Framing & YouTube Auth Resolution

### Added
- **Native YouTube Cloud Scheduling on Queue (`studio/posting.py`, `studio/accounts.py`, `web/index.html`)**:
  - Transformed "Add to queue" into immediate YouTube cloud upload with native `publishAt` RFC3339 scheduling.
  - Calculates 1-hour spaced slots (60-minute intervals) for queued clips: Clip 1 -> +1h, Clip 2 -> +2h, Clip 3 -> +3h.
  - Directly uploads videos to YouTube's servers as Private with automatic public release timestamps.
  - Users no longer need to keep their computer running or wait locally; YouTube Studio manages and executes the release autonomously.
  - Added direct "📌 Studio" link and scheduled time badges (`Scheduled for Today HH:MM`) on clip cards.
- **Streamer Overlay & Subscriber Count Bar Auto-Purge (`studio/render.py`)**:
  - Automatically trims bottom 12% (`fh_clean = int(fh * 0.88)`) of detected webcam bounding boxes and top-anchors vertical scaling in `split` and `split_half` layouts.
  - Slices away ugly half-cut live subscriber counts (e.g. `62,939,835`), ticker bars, and broadcaster desk borders while preserving natural head and shoulder framing.
- **Live Stream Continuous Ingestion Resilience (`studio/live.py`)**:
  - Configured `-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -rw_timeout 15000000` independently across ALL input URLs (both video and audio DASH/HLS tracks).
  - Implemented resilient retry backoff up to 10 attempts upon network TLS session resets (`-10054`), automatically refreshing yt-dlp stream manifests so the live recording bot runs continuously without dropping.
- **Automated Live Stream Audio-Video Sync Calibration (`studio/live.py`, `studio/jobs.py`, `studio/render.py`)**:
  - Calibrated default live audio delay to `+0.250s` (+250ms), resolving YouTube DASH audio lead where speech played before mouth movement ("awaz pehle aana aur game me baad me bolna").
  - Verified frame-accurate speech onset at `0.275s`, matching exact visual vocalization.
- **YouTube OAuth Status Diagnostics (`studio/accounts.py`, `data/users/u_local/creators/ishowspeed/creator.json`)**:
  - Diagnosed `400 invalid_grant: Token has been expired or revoked` for "The Paradox Files", adding human-friendly status notice to reconnect channel in Settings.
  - Linked active, verified YouTube account `yt_UC7JLjIDUyHOvs4sdjSCxS8w` ("ahsan iqbal") to IShowSpeed creator profile for immediate one-click and automated publishing.

### Changed
- **Streamlined UI Without Manual Sync Dropdowns (`web/index.html`)**:
  - Removed manual "Voice / Audio Sync" and "Webcam / Lip Delay" dropdowns from the Creator Setup dialog, executing synchronization autonomously in the rendering pipeline.
- **Subtitle-Safe Game Framing (`studio/render.py`)**:
  - Adjusted game crop window to `crop=min(in_w\,1040):in_h:(in_w-min(in_w\,1040))/2:0` scaled to `1080x1280`, ensuring in-game dialogue subtitles are fully readable and fit screen boundaries without edge clipping.

### Fixed
- **Strict Caption Generation Suppression (`studio/live.py`, `studio/jobs.py`, `studio/server.py`)**:
  - Real-time synchronization of creator settings into live memory sessions; when captions are disabled in Setup, ASS subtitle rendering is completely suppressed on all subsequent live clips.

### Tests and Verification
- Visual inspection of extracted frame crops: `mouth_0.4s.jpg` vs `mouth_0.8s.jpg` and `sync_test2`.
- Audio onset measurement via numpy audio energy detection confirmed exact acoustic alignment at 0.275s.
- Full PeakCut test suite execution via `tests/run.py`.

## [2026-11-19] — Multi-Corner Facecam, Split Screen, Audio/Video Sync Architecture & VOD Deduplication

### Added
- **Multi-Corner Facecam Placement (`studio/render.py`, `studio/jobs.py`, `web/index.html`)**:
  - Support for `facecam_pos`: `top-right`, `top-left`, `bottom-left`, `bottom-right`.
  - Automatically calculates bottom safe-zone coordinates (`H - pip_h - 240`) so facecams placed at the bottom never obscure or get covered by TikTok/YouTube Shorts UI elements.
  - Dynamically adjusts hook banner position: top remains clear (`y = 280`) when facecam is located at the bottom.
- **Split Screen Layout (`layout: "split"`) (`studio/render.py`, `studio/jobs.py`, `web/index.html`)**:
  - Vertical 1080x1920 canvas split into two equal 1080x960 halves using `vstack`.
  - Top half: Enlarged streamer reaction facecam.
  - Bottom half: Crisp centered gameplay with subtitles burned at `y = 1420`.
- **VOD Deduplication Engine for Repeated Links (`studio/jobs.py`)**:
  - Inspects existing completed jobs for the same source URL.
  - Automatically collects `prior_spans = [(start, end), ...]` and skips previously clipped segments.
  - Advances through the video blocks to find brand new highlights on subsequent submissions instead of re-clipping the first peak.
- **Independent Webcam / Voice Latency Calibration (`web/index.html`, `studio/render.py`)**:
  - Added `facecam_delay` and `audio_delay` controls in the clip edit dialog.
  - Sub-frame webcam layer shift via `[fc]setpts=PTS+({facecam_delay}/TB)` advances or delays mouth movement independently of game audio/video.

### Fixed
- **Audio/Video & Gameplay Sync Discrepancies (`studio/render.py`)**:
  - Placed `[0:v]setpts=PTS-STARTPTS,fps=30` at the very entrance of the video filter graph before stream splitting or layout composition, eliminating initial frame drops and demuxer jitter (0–66ms).
  - Normalized audio filter chain: `asetpts=PTS-STARTPTS,aresample=async=1000:min_hard_comp=0.010:first_pts=0` placed prior to `loudnorm`, ensuring audio clock locks to video from frame 0.
  - Cross-correlation analysis verified exact 0.00ms audio sample offset between source seek and rendered output.
- **Subtitle Desync & Premature Flashing (`studio/render.py`)**:
  - Calibrated `CAPTION_LEAD` from `0.08` to `0.00`. Subtitles now illuminate precisely at the acoustic onset of the word vocalization rather than flashing ahead prematurely.
- **Facecam Coordinate Normalization & Cutout Preservation (`studio/brain.py`, `studio/facecam.py`)**:
  - Scaled Gemini vision per-mille bounding boxes uniformly (`scale = 1000.0 if any(v > 100)`).
  - Prevented double-snap over-constraining in `_seen`: Green-screen and borderless cutout streamers preserve their full semantic width without being clipped to narrow head-only slices.
- **Manual "Post now" 400 Error (`studio/posting.py`, `studio/server.py`)**:
  - Supported `force=True` on manual post actions so already-posted clips can be reposted immediately without duplicate blockage errors.

### Tests and Verification
- `tests/test_sync.py`: Unit tests for PTS normalization, split screen layout, all 4 corner coordinates, and VOD deduplication passed with 100% OK.
- `PeakCut/tests/run.py`: Full master test suite across all 21 testing categories passed completely ("All tests passed.").
- Visual rendered verification:
  - `gameplay_bl_sec2.jpg`: ohnepixel facecam placed at bottom-left corner with 3D Hook & glowing subtitles.
  - `split_screen_sec2.jpg`: Split screen layout with facecam reaction on top and gameplay on bottom.
