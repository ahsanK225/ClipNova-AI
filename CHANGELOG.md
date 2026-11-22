# Changelog
All notable project changes are documented here.

## [2026-11-22] — Master Upgrade: OhnePixel Intelligent Livestream Clipping Engine

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
