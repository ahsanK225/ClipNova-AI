# PROJECT_STRUCTURE.md — ClipNova AI Live Stream & Video Clipper

## 1. Project Overview
This workspace hosts **ClipNova AI (`ahsanK225/ClipNova-AI`)**, an open-source, local-first AI video and live stream clipping suite. ClipNova AI connects to YouTube, Twitch, and Kick live streams (or video files), performs game-aware highlight detection (specifically recognizing GTA VI, GTA V, and 23+ major titles), crops footage to 9:16 vertical layout (with intelligent facecam corner extraction and split-screen layouts), generates word-by-word synchronized captions with zero latency, and prepares clips for immediate posting.

It includes:
- **Direct YouTube Live Ingestion**: Paste any live stream link directly or monitor creator channels.
- **Automated Shor & Mazaq Intelligence**: Detects sudden loudness (screaming, shouting, laughter) and comedic jokes/fails across English and Roman Urdu.
- **Dual-Engine Video Editing Suite & Full OpenCut Integration**: Full OpenCut web video editor integration (`https://github.com/opencut-app/opencut` / `https://opencut.app` / `https://new.opencut.app`) allowing creators to edit clips with full CapCut-style transitions, VFX, stickers, text overlays, and multi-track timeline tools in a new browser tab with automatic Windows Explorer file-highlight bridge (`explorer.exe /select,"<filepath>"`). Also provides native CapCut Desktop Bridge (`studio/capcut/export.py`) exporting complete project drafts (`draft_info.json`). The Clip Detail Modal (`#clipdlg`) is completely cleaned up (Teaser and Layout accordions removed to Video Studio), dedicated exclusively to Title, Description, Viral Hook, YouTube Shorts SEO, and 1-Click Publishing, with a real-time Live Hook Banner Video Overlay (`#dlg_hook_live_overlay`) and instant `< 5ms` persistence via `💾 Save SEO & Title (Instant - No Re-render)`.
- **Native YouTube Shorts SEO Optimization Engine**: High-CTR titles with `#Shorts`, targeted YouTube Studio tags, pinned comments, and automatic YouTube Data API custom cover thumbnail upload (`POST /upload/youtube/v3/thumbnails/set`).
- **Unified Collapsible Stream Folders & Real Video Preview Fallback**: 1-click folder accordion collapsing stream clip grids into single compact, cyber-dark cards with inline clip badges; smart video preview discovering real clip frames (`clip001.jpg`) instead of blank link icons; modern visual AI decision feed with real-time badges (`⚡ HIGH PRIORITY`, `✂️ CLIPPED`, `🔍 LISTENING`, `⏭️ EVALUATED`).
- **Sticky Clip Editor Preview**: Pinned 9:16 phone video preview that stays locked in viewport while editing options and SEO on the right side.
- **Single Yellow Punch Focus**: Canary Yellow (`\c&H00E5FF&`) highlight limited to exactly 1 punch action keyword per viral hook banner, with streamer names strictly demoted.
- **Golden Retention Timeline Calibration**: 12s pre-roll hook window (trigger occurs in first 10-15s before viewers swipe) + 28s post-roll reaction (continuous reaction, laughter, chat banter, and gameplay without abrupt cutoffs), totaling ~40-42s natural clip length.
- **Rock-Solid Hardware & Audio/Video Sync**: Millisecond PTS normalization, acoustic onset caption alignment (`CAPTION_LEAD = 0.00`), independent webcam/lip delay calibration, and corner placement.

---

## 2. Technology Stack & Framework Versions
- **Host Runtime**: Python 3.11.17 (Isolated via `uv` in `PeakCut\.venv`)
- **Backend / Web API**: FastAPI 0.162.5 + Uvicorn 0.54.0 (Port 8765)
- **Database**: SQLite (local single-user) / PostgreSQL (server mode)
- **Speech Recognition & Captions**: `sherpa-onnx` 2.0.1 (Offline local on-device speech-to-text) + `soundfile` + automated Roman Urdu transliteration via `studio/roman.py` (transcribe.py automatically romanizes Hindi/Urdu speech into clean Roman Urdu).
- **Named Custom Presets & Photoshop Mask Studio**: Persistent custom presets store (`custom_presets` on creators) with `GET/POST/DELETE /api/creators/{cid}/presets`. Photoshop-style semi-transparent dark vignette mask (`clsDrawMask`), 8 interactive anchor handles (`nw`, `n`, `ne`, `e`, `se`, `s`, `sw`, `w`) with 9:16 ratio locking, zero-distortion preview (`drawCover`), and direct 1-click clip re-rendering (`POST /api/jobs/{jid}/clips/{cid}/render`).
- **Video & Media**: FFmpeg (9.0.2 Gyan build), `yt-dlp` (2026.10.21), Pillow 11.3.0. Live buffer segments are concatted directly into `.src.mp4` with `-movflags +faststart -avoid_negative_ts make_zero` for sample-accurate 0ms seeking. Interactive Visual Custom Layout Studio with draggable Facecam & Gameplay bounding boxes, customizable Split Screen ratio (20%-80%), Picture-in-Picture, Single Gameplay Crop, and glowing broadcast divider bar.
- **Live Stream Engine**: `studio/live.py` (6s rolling buffer, real-time waveform spike monitor, dual AI judges, zero-delay 0.0s lip-sync default, automatic `/streams`, `/videos`, `/featured` YouTube channel URL normalization to `/live`)
- **YouTube Shorts SEO Engine & 1-Click ChatGPT Bridge**: Integrated in `studio/brain.py`, `studio/server.py`, `studio/jobs.py`, `studio/posting.py`, and `web/index.html` (Multimodal 6-frame video grounding via `jobs.get_clip_frames_payload` and `ai.see_json` generating physical on-screen gameplay hooks and titles, dedicated AI SEO section, multi-title clickable suggestion pills under Post Text and Shorts Title with `✨ AI Title Ideas` button, creator-adaptive personas for Speed/Kai, OhnePixel CS2, and GTA 6 Lore, plus 1-Click ChatGPT prompt generator and auto-fill importer).
- **Multi-Key Pool & Failover**: `studio/ai.py` (intelligent key prefix auto-routing for Gemini, OpenRouter, Groq, xAI, per-provider key isolation preventing cross-service rejection, auto-rotation on quota exhaustion, auto-clearing error banners).
- **Global Header & Navigation**: `web/index.html` (Flexbox non-colliding layout with `.titles`, static `#utabs`, `#global_ai_bar` model selector, and responsive sub-row wrapping under 980px).
- **Layout Framing Engine**: `studio/render.py` (elevated 0.70 facecam framing, dynamic game crop eliminating streamer webcam from gameplay while preserving 100% of GTA 6 center subtitles, glowing broadcast dividers)
- **Frontend / Dashboard**: Lightweight zero-login web interface served by FastAPI (`PeakCut/web`)

---

## 3. Repository and Directory Tree
```
F:\Games\GTA 6 CLIPPING\
├── PeakCut\                                # Primary Target Repository (ahsanK225)
│   ├── deploy\                             # Docker & Cloud deployment files
│   ├── studio\                             # Core Python processing & API engine
│   │   ├── accounts.py                     # Social OAuth connections, multi-client token refresh & YouTube API upload
│   │   ├── admin.py                        # Admin & diagnostics routes
│   │   ├── ai.py                           # Gemini multimodal vision (see_json), multi-key pool rotation, per-key live health testing & OpenRouter free models
│   │   ├── analytics.py                    # Autonomous hourly views delta tracker (Option A), 24h rolling velocity profile & hybrid algorithm priming engine
│   │   ├── asr.py                          # Speech recognition & word-level timing (sherpa-onnx)
│   │   ├── audio.py                        # Audio engine: background music, viral meme sounds library, path security & safe uploads
│   │   ├── brain.py                        # Universal grounding (anti-hallucination), multimodal scene analysis, dual AI judges & SEO
│   │   ├── calendar.py                     # Dynamic publishing calendar engine (analytics-primed peaks or USA 6PM/12AM/6AM PKT; max 3/day; auto next-day roll; +30m Community Post pairing)
│   │   ├── config.py                       # App configuration & environment parsing
│   │   ├── creators.py                     # Creator workspace profiles, trigger words & settings
│   │   ├── db.py                           # SQLite / SQLAlchemy persistence
│   │   ├── facecam.py                      # Webcam overlay detection (AI vision & pixel gradient edge tracking)
│   │   ├── fetch_model.py                  # Multi-language speech model fetcher & retry engine
│   │   ├── games.py                        # GTA VI & gaming stream detection engine
│   │   ├── hashtags.py                     # Non-AI fast hashtags engine (derives 3-5 tags without burning tokens)
│   │   ├── jobs.py                         # Video processing queue, facecam resolution, multimodal SEO & Windows retry save
│   │   ├── live.py                         # Live stream buffer, 720p lock, loudness spikes, Pure AI Mode bypass on empty triggers, and creator-scoped triggers
│   │   ├── load.py                         # System load, memory, and queue worker throttle
│   │   ├── capcut\                         # Native CapCut Desktop Draft project generator (pyJianYingDraft & template)
│   │   │   ├── export.py                   # Multi-track CapCut draft exporter (video, hook title, subtitle tracks)
│   │   │   ├── pyJianYingDraft\            # Pure Python CapCut desktop draft AST builder & track manager
│   │   │   └── template\                   # Base CapCut project template (draft_info.json, draft_meta_info.json)
│   │   ├── media.py                        # Long-video stream inspector, format resolver & Netscape cookie manager
│   │   ├── ohnepixel.py                    # OhnePixel intelligent detection database, tiered phrases without casual fillers, German/English slang, false-positive protection & Mode B fallback
│   │   ├── posting.py                      # YouTube Shorts cloud scheduling, IG, TikTok & channel exclusivity
│   │   ├── render.py                       # FFmpeg 9:16 vertical render, split layouts, Bouncy/Hormozi/MrBeast subtitles, Hook styles (Purple Whip, etc.)
│   │   ├── server.py                       # FastAPI application & HTTP routes (CapCut export endpoints, multi-key pool, presets)
│   │   ├── storage.py                      # Local file, clip & recording management
│   │   └── video.py                        # FFmpeg rendering, 9:16 layout & caption burn
│   ├── tests\                              # Test suite (31 comprehensive suites)
│   │   ├── run.py                          # Master test runner (690+ automated checks)
│   │   ├── test_ohnepixel_engine.py        # OhnePixel intelligent detection & false-positive suite (12 scenarios)
│   │   ├── test_hashtags.py                # Hashtags generation tests
│   │   ├── test_jobsave.py                 # Windows file locking resilience tests
│   │   ├── test_longvideo.py               # 24-hour video memory efficiency tests
│   │   ├── test_speech.py                  # Multi-language speech model tests
│   │   ├── test_upload_parts.py            # Large chunked upload validation
│   │   ├── test_seo.py                     # YouTube Shorts SEO validation test suite
│   │   ├── test_sync.py                    # Audio/video latency, PTS normalization, and layout tests
│   │   └── test_usa_publishing_calendar.py # USA-focused automatic publishing calendar & community post test suite
│   ├── web\                                # Static frontend web dashboard
│   │   ├── brand\                          # Brand assets & layout visual previews (540x960 crisp JPGs)
│   │   │   ├── layout-split_half.jpg       # Classic Split 50/50 ⭐ (Top Cam 1080x960, Bottom Game 1080x960)
│   │   │   ├── layout-split.jpg            # Reaction Split (Top 1/3 Cam 1080x640, Bottom 2/3 Game 1080x1280)
│   │   │   ├── layout-gameplay.jpg         # Full 9:16 Game + Top-Right Corner PIP Facecam
│   │   │   ├── layout-gameplay_tl.jpg      # Top-Left Corner PIP Facecam
│   │   │   ├── layout-gameplay_bl.jpg      # Bottom-Left Corner PIP Facecam
│   │   │   ├── layout-gameplay_br.jpg      # Bottom-Right Corner PIP Facecam
│   │   │   ├── layout-crop.jpg             # Fullscreen Gameplay Center Crop (No Cam)
│   │   │   ├── layout-left.jpg             # Fill Screen, Keep Left (Minimap / HUD Focus)
│   │   │   ├── layout-right.jpg            # Fill Screen, Keep Right (Killfeed / Score Focus)
│   │   │   ├── layout-fit.jpg              # Full Frame on Black (16:9 Letterbox)
│   │   │   ├── layout-blur.jpg             # Original 16:9 + Ambient Blurred Video Background
│   │   │   └── layout-zoom.jpg             # Zoomed 16:9 + Ambient Blurred Video Background
│   │   ├── audio\                          # Curated background tracks & viral meme sounds (.mp3)
│   │   └── index.html                      # UI dashboard with visual layout previews, multi-key pool & live player
│   ├── tests/                              # Automated test suites
│   │   ├── test_stream_chat_and_scroll.py  # Unit tests for stream card live chat elevation, compact stats & scroll auto-stick/preservation
│   │   ├── test_ai_verdicts_clean_ui.py    # Unit tests for clean single-line AI decisions, removal of what was just said & compact height
│   │   ├── test_bgm_and_meme_sounds.py     # Unit tests for viral background music, meme sounds & zero-latency sync preview
│   │   ├── test_origins_chat_teaser.py     # Unit tests for clip origin badges, Twitch chat streaming & teaser cold open
│   │   ├── test_trigger_timeline.py        # Unit tests for 12s pre-roll hook and 28s post-roll reaction
│   │   ├── test_hook_single_yellow.py      # Unit tests for single punch keyword in hook banner
│   │   └── test_capcut_and_styles.py       # Unit tests for CapCut export and bouncy caption styles
│   ├── GAMING.md                           # Specification for gaming & GTA 6 workflows
│   ├── requirements.txt                    # Pinned Python package dependencies
│   └── .venv\                              # Python 3.11 isolated runtime environment
├── run_peakcut.bat                         # One-click desktop launcher for PeakCut
├── MEMORY.md                               # Permanent Master Agent Operational Memory & Knowledge Vault
├── CHANGELOG.md                            # Auditable project change log
├── GEMINI_SYSTEM_PROMPT.md                 # Master Engineering Prompt
├── PROJECT_STRUCTURE.md                    # Detailed map of the project architecture
├── SYSTEM_DESIGN.md                        # Authoritative technical design specification
└── TASKS.md                                # Persistent task checklist
```

---

## 4. How to Use YouTube Live Clipping
1. Open PeakCut via [run_peakcut.bat](file:///F:/Games/GTA%206%20CLIPPING/run_peakcut.bat) or browse to `http://127.0.0.1:8765`.
2. **Direct Method**: Paste any active YouTube Live link (`https://www.youtube.com/watch?v=...` or `https://youtube.com/live/...`) directly in the top input box and click **Start live clipping** (or "Make clips").
3. **Creator Method**: Click **New Creator** on the left menu, enter the YouTube channel URL, and click **Record live stream**.
4. PeakCut starts monitoring the live stream in real time. It uses dual AI judges to continuously listen for **Shor** (volume jumps +60%, screaming, laughing) and **Mazaq** (funny jokes, punchlines, fails).
5. Detected clips appear immediately in 9:16 vertical format with word-by-word subtitles, facecam cropping, and ready-to-copy YouTube Shorts SEO!

---

## 5. Video Rendering & Audio/Video Sync Architecture
- **`studio/render.py`**:
  - Normalizes frame PTS via `[0:v]setpts=PTS-STARTPTS,fps=30` at the very entrance of the video filter graph to eliminate initial frame drops and timestamp jitter.
  - Normalizes audio PTS via `asetpts=PTS-STARTPTS,aresample=async=1000:min_hard_comp=0.010:first_pts=0`.
  - Background Music & Meme Sounds Mixing: Infinite loop (`-stream_loop -1`) or trimmed seek (`-ss <bgm_offset>`) combined with `asetpts=PTS-STARTPTS` and `amix=inputs=2:duration=first:dropout_transition=2`.
  - CapCut Desktop Draft Export (`studio/capcut/export.py`): Generates full native CapCut desktop projects in `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\` with tracks for video, audio, captions, and PIP.
  - Calibrated subtitle lead: `CAPTION_LEAD = 0.00` for exact acoustic word onset.
  - Multi-layout support: `blur`, `zoom`, `crop`, `gameplay` (corner PIP with `top-right`, `top-left`, `bottom-left`, `bottom-right`), and `split` (1080x960 facecam top + 1080x960 gameplay bottom).
  - 3D Hook banner & 3D Outro Support Badge ('NEW CHANNEL • LIKE & SUBSCRIBE!') burned in the last 3.2 seconds.
- **`studio/jobs.py`**:
  - VOD Deduplication: Checks `prior_spans` of previous jobs on the same source URL so re-submitting links automatically discovers the next fresh highlights instead of duplicating old moments.
  - Direct slice Whisper transcription with local timestamp alignment.
  - Configurable `audio_delay`, `facecam_delay`, and `facecam_pos`.
- **`studio/facecam.py`**:
  - Scale normalization for Gemini per-mille coordinate systems (`scale = 1000.0 if any(v > 100)`).
  - Semantic bounding box protection for green-screen/cutout streamers without over-constraining borders.
- **`studio/posting.py` & `studio/accounts.py`**:
  - `force=True` on manual "Post now" to dispatch immediate live publishing.
  - Native YouTube Cloud Scheduling on "Add to queue": uploads directly to YouTube's servers with native RFC3339 `publishAt` timestamp scheduled 1 hour apart (`post_gap_min = 60`). The PC does not need to stay on; YouTube Studio handles autonomous release.
  - Generates direct Short URL and "📌 Studio" link badges on clip cards.
- **`studio/render.py`**:
  - Automatically slices off the bottom 12% of detected streamer webcam boxes (`fh_clean = max(10, int(fh * 0.88))`) to eliminate cut-off subscriber counters and overlay bars while maintaining facecam clarity.

---

## 6. Multi-API Key Pool & Interactive Management Architecture
- **`studio/ai.py`**:
  - Maintains a pooled list of API keys in `data/users/u_local/ai.json` with 8000-character capacity.
  - Exposes `all_keys()`, `rotate_key()`, `add_key(new_key)`, and `remove_key(index)`.
  - Dynamic status tracking: active key is assigned `🟢 Live / Active`, while standby keys are marked `⚪ Standby (Auto-rotates)`.
  - Automatic quota failover: whenever an API call encounters HTTP 429, ResourceExhausted, or token exhaustion, `_retry_on_quota` auto-rotates to the next standby key seamlessly.
- **`studio/server.py`**:
  - `POST /api/ai/keys`: Appends a new API key to the active pool (with duplicate prevention).
  - `DELETE /api/ai/keys/{idx}`: Removes a key by index.
  - `GET /api/ai`: Returns `keys_list` with masked strings and live status badges for UI display.
- **`web/index.html`**:
  - Interactive **🔑 API Keys Pool Card**: Replaces plain textarea with a clear list showing Key #, masked key, live/standby status pill, individual `🗑️ Remove` buttons, and an input box with `[➕ Add Key]`.

---

## 7. Automatic USA-Focused Publishing Calendar, Clip Picker & UI Accordion Architecture
- **`studio/calendar.py`**:
  - Core USA publishing schedule calculator: 6:00 PM, 12:00 AM, 6:00 AM PKT slots.
  - Accounts for USA Daylight Saving Time (DST) dynamically via `zoneinfo.ZoneInfo("America/New_York")` and `ZoneInfo("America/Los_Angeles")`.
  - Enforces strict 3-video daily ceiling and auto-advances subsequent ready clips to future days.
- **`studio/server.py`**:
  - `GET /api/creators/{cid}/calendar`: Returns active calendar data, daily quota usage, and upcoming slots with scheduled clips.
  - `GET /api/creators/{cid}/ready-clips`: Lists all finished/rendered clips ready for scheduling with cover thumbnails, duration, and AI score.
  - `POST /api/calendar/schedule-clip`: Schedules a specific clip directly to a targeted calendar slot timestamp, pairing a Community Post (+30m).
- **`web/index.html`**:
  - `#cal_picker_dlg`: Interactive modal popup for slot selection with ready clip cards and 1-click `⚡ Schedule to this Slot` action.
  - Collapsible `<details class="card">` accordions for `Viral Hook Banner`, `Viral Climax Teaser`, `Background Music`, and `Layout Studio` in `#clipdlg`.
  - Squeezed `.meters` grid (`minmax(130px, 170px) minmax(130px, 170px) minmax(360px, 1fr)`) allowing full readability of `Latest AI Decisions`.
  - Route & Subtab persistence across F5 refresh using `fromPath` calendar regex and `localStorage`.


### 18. Web Video Studio (In-Browser CapCut-Style Multi-Track Editor)
- **Frontend Timeline & Editor**: `web/index.html` (`drawVideoStudioTab()`, `renderStudioWorkspace()`, `saveStudioExport()`)
  - 9:16 vertical player viewport with real-time CSS color grading filters and transport controls.
  - Subtitle word-level highlight overlay and double-click in-place typo editing.
  - 5-tab tool drawer: Filters (Normal, Vibrant, Cinematic, Moody, Cyberpunk, B&W), VFX (Flash, Shake, Glitch, Zoom Punch), Audio & BGM mix, Subtitles, Layout.
  - Interactive multi-track timeline with Time Ruler, draggable Red/Cyan Playhead Needle, Subtitles word blocks track, Video cut track, Facecam track, Audio waveform track, and VFX track.
- **Backend Project & Export Endpoints**: `studio/server.py`
  - `GET /api/jobs/{jid}/clips/{cid}/studio-project`: Returns full timeline project contract.
  - `POST /api/jobs/{jid}/clips/{cid}/studio-export`: Triggers FFmpeg re-render and optional 1-click scheduling into YouTube Publishing Calendar at USA Peak Velocity slot.
- **FFmpeg Color Grading Engine**: `studio/render.py` (`VIDEO_FILTERS`)
  - Injects `eq` and `hue` filtergraphs directly into the video filter pipeline.

### 19. CapCut Desktop Native Bridge & OpenCut Web Studio
- **CapCut Desktop Generator**: `studio/capcut/export.py`
  - Generates `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\<draft_name>\draft_info.json`
  - Maps Video Track, Subtitle Captions Track, and Hook Title Track for native CapCut desktop editing.
- **UI Launchers**: `web/index.html` (`#clipdlg`, `drawVideoStudioTab()`)
  - `🌐 Open in OpenCut Web Studio` for browser-based multi-track timeline editing.
  - `🚀 Open in CapCut Desktop` for official PC CapCut app editing with native transitions and AI effects.
