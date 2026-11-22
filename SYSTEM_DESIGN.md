# SYSTEM_DESIGN.md — PeakCut System Architecture & Gaming Workflow

## 1. System Goals and Scope
PeakCut is an autonomous, open-source pipeline designed to process gaming livestreams (Twitch, YouTube, Kick) and long videos into viral, captioned 9:16 vertical clips. The system operates locally without subscriptions or watermarks, using on-device speech models (`sherpa-onnx`) or user-configured AI APIs (Gemini, OpenAI, Claude, Ollama).

---

## 2. Architecture Overview
```mermaid
flowchart TD
    Input["YouTube / Twitch Live Stream Link"] --> Ingest["Rolling Buffer (ffmpeg 6s segments)"]
    Ingest --> Audio["Audio Track Extractor"]
    
    Audio --> Energy["Loudness Tracker & Spike Monitor (Shor / Volume +60%)"]
    Audio --> ASR["sherpa-onnx Offline Speech-to-Text (every ~7s)"]
    
    Energy & ASR --> Judges{"Two AI Judges Pipeline"}
    Judges -->|Judge 1: Spoken Words| J1["Transcript Judge (Mazaq / Jokes / Fails / Punchlines)"]
    Judges -->|Judge 2: Reaction Waveform| J2["Signal Judge (Screaming / Laughter / Volume Spikes)"]
    
    J1 & J2 --> Match{"Agreement Gate"}
    Match -->|Both Agree OR Score >= 90| Clipper["Auto-Clip Generation"]
    
    Clipper --> Layout["9:16 Vertical Video + Facecam Corner Extraction / Split Screen"]
    Clipper --> Captions["Bouncy Animated Subtitles (Sample-Accurate, 0ms latency)"]
    Clipper --> SEO["YouTube Shorts SEO (Title with #Shorts, Tags, Pinned Comment)"]
    
    SEO --> Out["Live Dashboard Display & 1-Click Posting"]
```

---

## 3. Live Stream Auto-Detection Intelligence (Shor & Mazaq)
1. **Shor Detection (Loudness & Energy Spikes)**:
   - PeakCut tracks moving audio amplitude (`db`) over 3-minute rolling windows.
   - Any sudden 60%+ volume surge (`loudness +X%`: streamer screaming, shouting, intense laughter, explosions) triggers an immediate snapshot.
   - The Reaction Signal Judge verifies the intensity score (0–100).
2. **Mazaq Detection (Jokes, Roasts, Banter & Fails)**:
   - Words Judge scans continuous timestamped transcript chunks for humor, punchlines, comedic timing, trolling, fails, and streamer laughing.
   - Explicitly trained to recognize Roman Urdu and Hindi gaming slang (*"bhai ye kya tha"*, *"mazaq ho raha hai"*, *"hasi nahi ruk rahi"*, *"arre yaar"*).
3. **YouTube Live Channel URL Normalization & Authentication Pipeline**:
   - `normalize(url)` automatically strips channel tab suffixes (`/streams`, `/videos`, `/featured`, `/live`, `/community`) and canonicalizes them to `https://www.youtube.com/@handle/live`.
   - `resolve(url)` invokes `normalize(url)` on all stream ingestion requests to ensure `yt-dlp` queries active broadcast manifests rather than channel video tab listings.
   - Dual-tier cookie ingestion loads fresh Netscape cookies (`PeakCut/data/cookies.txt`) with automatic Netscape format conversion from browser JSON exports.

### 3.1 Golden Retention Timeline Calibration (12s Pre-Roll Hook & 28s Post-Roll Reaction)
- **Problem Solved**:
  - Previously, pre-roll was set to 18–20s, causing the trigger word or punchline to occur too late in the clip (at 18s+), leading to viewer drop-off within the first 5 seconds.
  - Furthermore, clips were often restricted to 26 seconds, cutting off the streamer's reaction, laughter, chat banter, and continuous gameplay abruptly.
- **Golden Retention Architecture**:
  1. **Pre-roll Window (10–14s, Target: 12.0s)**:
     - When a trigger word or viral moment occurs at timestamp $T$, the clip begins at $\max(0.0, T - 12.0)$.
     - In the resulting 9:16 vertical clip, the trigger word / climax occurs at exactly second 12 (strictly within the golden 10–15s hook window).
     - Viewers receive 10–12 seconds of buildup/context, hear/see the viral event, and stay hooked.
  2. **Post-roll Reaction (25–30s, Target: 28.0s)**:
     - The clip continues until $T + 28.0$, capturing 28 seconds of reaction, laughter, screaming, chat spam, and continuing gameplay action.
     - The video never ends prematurely or abruptly cuts off after the punchline.
  3. **Total Target Duration**:
     - Standard clip duration: $12.0s + 28.0s = 40.0s$ (sweet spot: 38–43s).
     - Overlapping triggers within 15 seconds merge dynamically with smooth reaction extension, capped at 60.0s maximum.
  4. **Multi-Source Alignment**:
     - Applied across OhnePixel Continuous Discovery (`studio/live.py`), Custom Creator Phrases (`studio/live.py`), AI Judge Candidate Alignment (`studio/live.py` `_ai_check`), Prompt Rules (`studio/brain.py`), and Category Profiles (`studio/ohnepixel.py`).

### 3.2 Unified Sleek Folded Stream Cards & Video Thumbnail Pipeline
- **Problem Solved**:
  - Previously, folded stream jobs rendered a secondary, redundant dashed bar below the stream header (`📁 X clips folded... Open Folder 📂`), creating visual clutter and double rows per project.
  - Jobs without a static downloaded cover thumbnail displayed a blank dark 16:9 box with an uninformative chain-link icon (`🔗`).
- **Solution & Architecture**:
  1. **Unified Single-Row Folder Card**:
     - Collapsing a stream removes all secondary containers. The stream header itself transforms into a sleek, compact, self-contained card (`.job.is-collapsed .job-head`) with `border-radius: 12px`, subtle cyan border highlight, and hover elevation.
     - Inline badge: `📁 <N> Clips` pill next to title, with a dedicated `📁 Open Folder ▶` action button.
     - Entire card header is click-interactive to toggle between folded and expanded states.
  2. **Smart Video Preview Discovery**:
     - Frontend checks `j.thumb`, then falls back to `j.clips[0].id` (`/media/{jid}/clip001.jpg`), displaying the actual facecam/gameplay frame with the duration tag.
     - Backend `/media/{jid}/thumb.jpg` route automatically returns the first available clip thumbnail if the stream cover was not downloaded directly.
     - Zero-clip placeholder is upgraded from a link icon to a modern cyber-dark stream badge (`🔴 LIVE STREAM` or `🎬 VIDEO`).

---

## 4. Hardware & Audio/Video Sync Architecture
1. **Natural Broadcast Lip-Sync Alignment (0.0s Default)**:
   - Live stream clips now default to `0.0s` audio delay (removing previous legacy forced `0.25s` delay).
   - Audio waveform bursts and streamer lip movement match at exact 0.00s broadcast alignment.
   - Interactive `audio_delay` (-500ms to +500ms) and `facecam_delay` (-500ms to +500ms) selects provide fine-grained control across the Clip Editor, Creator Setup, and Job Composer.
2. **Elevated Split Layout Framing & Subtitle-Safe Game Crop**:
   - **Top Facecam**: Scaled with elevated crop (`fh_clean = max(10, int(fh * 0.70))`), centering the streamer's head and eyes while cleanly cropping out excess sweater, chest, and subscriber goal bars.
   - **Bottom Gameplay**: Dynamic horizontal crop starts past streamer webcam (`gx = max(fx + fw + 2, 260)`), completely eliminating streamer in-game webcam overlay from the game area while preserving 100% of GTA 6 center dialogue subtitles.
3. **Native Zero-Drift MP4 Clip Slicing**:
   - In live streaming, buffer chunks are recorded into MPEG-TS pieces for stream crash resilience.
   - When a clip is created from buffer chunks, `studio/live.py` concats the chunks directly into `.src.mp4` with:
     `ffmpeg -y -v error -fflags +genpts -f concat -safe 0 -i lst -c copy -movflags +faststart -avoid_negative_ts make_zero src.mp4`
   - Unlike raw `.ts` (where audio and video packets have asynchronous start offsets of 20ms-500ms and no central index), MP4 constructs exact ISO BMFF sample tables (`stts`, `ctts`, `stsc`), locking video frame 0 to audio sample 0 with 0.000s start time.
   - When `studio/render.py` seeks into `.src.mp4` (`-ss ... -i ... -avoid_negative_ts make_zero`), seeking is sample-locked with 0ms drift.
2. **Input PTS Normalization & Accurate Input Seeking**:
   - `seek_args = ["-ss", f"{start:.3f}", "-i", str(Path(src).resolve()), "-t", f"{dur:.3f}"]`: Input seeking decodes directly from target timestamp.
   - `[0:v]setpts=PTS-STARTPTS,fps=30[vin]` is placed at the entrance of the video filter graph before stream splitting or layout overlays.
   - Eliminates initial frame jitter (0–66ms) and ensures libass subtitle filters receive frames starting at exact local time 0.000s.
3. **Audio Filter Chain Normalization**:
   - Audio timestamps are reset immediately: `asetpts=PTS-STARTPTS,aresample=async=1000:min_hard_comp=0.010:first_pts=0`.
   - Prevents `loudnorm` or `aresample` from buffering or inserting spurious silence at stream starts.
   - Audio delay calibration via `adelay` (for delays) or `atrim` (for advances) locks acoustic voice timing.
4. **Calibrated Subtitle Acoustic Onset, Outro Separation & Strict Toggle Compliance**:
   - `CAPTION_LEAD = 0.08`: Captions illuminate in sync with natural vocalization when enabled.
   - When `"captions": false` is configured in creator setup or clip options, subtitle generation is strictly bypassed:
     - `_caption_words()` returns empty `[]` without running transcription cleanup.
     - `build_ass()` generates zero `Dialogue: 1... Cap` subtitle events, burning only the hook banner and clean video.
     - Active live streams synchronize `s.job["options"]` immediately upon creator settings update.
   - Subtitle area in `split` and `split_half` layout is centered at `cap_y = 1360` / `1520` in the game section.
   - Outro CTA badge is placed in the bottom safe zone at `y = 1680` (320px vertical clearance from captions), completely eliminating visual overlap in the final 3.2 seconds.
5. **Zero-Touch Automatic Synchronization & Proportional Gamer Split Layout**:
   - Eliminates confusing manual delay dropdowns from UI (Clip Editor, Creator Settings, and Composer).
   - Audio and video clocks are synchronized automatically at container and filter levels with 0ms offset.
   - **Split Layout (1/3 Top, 2/3 Bottom)**:
     - Top Facecam (1080x640): Fills edge-to-edge horizontally at y=0. Streamer is fully visible with natural proportions and zero voids.
     - Bottom Gameplay (1080x1280): Massive game area with subtitle-safe zoom-out framing (`crop=min(in_w\,1040):in_h:(in_w-min(in_w\,1040))/2:0`). In-game dialogue subtitles fit screen boundaries without edge clipping, while keeping streamer borders/overlays cleanly cropped out.
     - Broadcast divider: 6px dark bar + 2px glowing cyan line (`color=0x00F0FF@0.9`). Hook banner positioned at y=690.

## 8. Speech Trigger Recognition Engine ("Always clip the last 30 seconds when someone says")
The live speech trigger engine (`studio/live.py:Session._triggers`) continuously monitors real-time streaming transcripts and queues a 30-second highlight immediately when a trigger phrase is detected, bypassing AI score thresholds:
- **Rolling Window Cross-Chunk Scan**: Scans a rolling window of recent words (`self.words[-50:]`) rather than isolating the incoming 4-6s audio chunk, eliminating phrase-splitting at chunk boundaries.
- **Apostrophe & Unicode Normalization**: Translates curly quotes (`’`, `‘`, `´`, `` ` ``) to ASCII `'` and matches both with-apostrophe and without-apostrophe word tokens (e.g. `that's a clip` == `thats a clip`).
- **Phonetic Roman Urdu Support**: Automatically normalizes Roman Urdu phonetic variations (`yeh` -> `ye`, `is ko` -> `isko`, `kardo`/`karde` -> `karo`).
- **Rapid Re-Triggering Cooldown**: Cooldown calibrated to 25 seconds (reduced from 45s) to allow sequential high-energy moments in fast-paced streams to be captured.

---

## 9. Story-Driven YouTube Shorts SEO Pipeline
Integrated directly in `studio/brain.py` and `studio/posting.py`:
- **Multimodal Video Frame Grounding for Hooks, Titles & Post Text (`jobs.py`, `ai.py`, `brain.py`)**:
  - In addition to spoken audio transcripts, PeakCut extracts 6 high-resolution video frames across the clip timeline (0.15, 0.35, 0.55, 0.70, 0.85, 0.95) via `jobs.get_clip_frames_payload` and submits them to multimodal vision models (`gemini-3.5-flash-lite` via `ai.see_json`).
  - Physical vehicles, objects, crashes, characters, and streamer facial expressions are extracted into structured JSON metadata.
  - Generates ground-truth hooks (`*CAR*`, `*ALLIGATOR*`, `*BOAT*`) and titles that strictly describe what is visually happening on screen, completely eliminating blind transcript cliché templates (e.g. `"GTA 6 flashbacks are wild"`, `"He lost his mind"`).
  - All 3 creative generation endpoints (`/hooks`, `/titles`, `/write`) now leverage this 6-frame vision payload.
- **1-Click AI Video Scan in Clip Editor (`server.py`, `web/index.html`)**:
  - Allows creators to re-scan any clip's visual frame with AI via `POST /api/jobs/{jid}/clips/{cid}/ai_seo`.
  - Instantly populates and refreshes Hook, Title, Description, YouTube search tags, and Pinned comment in the editor dialog.
  - Re-burning the hook is executed seamlessly via "Save and re-make clip".
- **Multi-Title AI Suggestions & Interactive Clickable Pills (`brain.py`, `server.py`, `web/index.html`)**:
  - AI generates 4 distinct, high-CTR YouTube Shorts titles ending with `#Shorts` and fitting emojis via `generate_viral_titles()`.
  - In `#clipdlg`, both `Title (with Viral Hashtags)` and `Shorts Title (High-CTR with #Shorts)` feature `#dlg_title_pills` and `#dlg_seo_title_pills` containers displaying clickable title suggestion pills (`💡 Title #1`, `💡 Title #2`, `💡 Title #3`, `💡 Title #4`).
  - Added dedicated `✨ AI Title Ideas` button (`btn_ai_titles`) calling `/api/jobs/{jid}/clips/{cid}/titles` for on-demand title generation.
  - Clicking any suggested pill updates both title inputs simultaneously and applies a glowing cyan accent border to the active pill across both containers.
- **5-Line Story "Khulasa"**: Contextual story summary of the specific comedic/action moment (actor, unexpected twist, escalation, streamer reaction, community question).
- **High-CTR Title**: Curiosity-gap title capped with `#Shorts`.
- **Top Discussion Pinned Comment**: Provocative prompt posted as top comment to drive algorithm engagement and comments.
- **Channel Direct Publishing**: Authenticated Google OAuth client publishing directly to target channel (`The Paradox Files`).
1. **Layout Strategy**:
   - `blur`: Full frame centered with blurred background fill.
   - `zoom`: Zoomed frame with subtle blurred fill.
   - `crop`: 9:16 center crop filling the canvas.
   - `gameplay`: Full 9:16 vertical gameplay with streamer facecam in corner PIP.
   - `split`: Split Screen layout (Top 1080x960 Facecam reaction + Bottom 1080x960 Gameplay) stacked with `vstack`.
2. **Webcam Corner Positioning (`facecam_pos`)**:
   - `top-right`: Standard upper-right corner (`PIP_MARGIN` padding).
   - `top-left`: Upper-left corner.
   - `bottom-left`: Lower-left corner positioned above the YouTube Shorts / TikTok UI safe zone (`H - pip_h - 240`).
   - `bottom-right`: Lower-right corner.
   - Automatic heading adjustment: When facecam is bottom-positioned, the top is open so hook banner renders at `y = 280`.

---

## 6. VOD Deduplication for Repeated URLs
1. **Problem**: Re-clipping a long video or stream URL repeatedly created duplicate clips of the first audio spike.
2. **Solution (`studio/jobs.py`)**:
   - Before finding candidate clips, `jobs.py` queries existing completed jobs for the same source URL.
   - Collects `prior_spans = [(start, end), ...]`.
   - Filters candidate moments that overlap with any previously clipped span by >= 30%.
   - Seamlessly advances across subsequent blocks (minutes 10, 20, 30...) to produce brand new, non-repeating highlights.

---

## 7. Modern Split Gamer Layout & Non-Destructive Facecam Framing
1. **Vertical Geometry**:
   - Canvas: 1080x1920 (9:16 vertical short format).
   - Top Section (`cam_h = 640px`): Streamer webcam reaction.
   - Bottom Section (`game_h = 1280px`): Gameplay action.
2. **Facecam Auto-Framing**:
   - Edge/corner detected streamer webcam is cropped (`crop={fw}:{fh}:{fx}:{fy}`) from source regardless of corner placement (`top-right`, `top-left`, `bottom-left`, `bottom-right`).
   - Ambient blurred background (`scale=1080:640:force_original_aspect_ratio=increase,boxblur=25:25`) fills the sides.
   - Foreground webcam is scaled proportionally (`force_original_aspect_ratio=decrease`) and centered (`(W-w)/2:({cam_h}-h)/2`).
   - Prevents face/chin cutoff and facial distortion.
3. **Gameplay Fill**:
   - Gameplay scaled with `force_original_aspect_ratio=increase,crop=1080:1280:(in_w-out_w)/2:(in_h-out_h)/2` ensuring zero black void at the bottom.

---

## 8. Schedule Cancellation & Single-Channel Exclusivity
1. **Schedule Cancellation**:
   - `cancel_clip(job_id, clip_id)` cancels all open scheduled posts for a clip.
   - UI provides inline `[✕]` cancellation buttons on scheduled pills, clip details, and bulk actions.
2. **Single-Channel Exclusivity**:
   - In `_post(p)`, upon successful publication to any connected channel/account, all pending posts for other channels on that clip are automatically cancelled to prevent duplicate cross-posting.

---

## 9. Post-Upload Local File Cleanup Workflow
1. **Configurable Policy (`post_cleanup`)**:
   - `"ask"` (default): Prompts user with confirmation dialogue to delete or keep local media files.
   - `"auto"`: Immediately purges `.mp4`, `.jpg`, and `.ass` files upon successful upload.
   - `"keep"`: Retains all local files on disk.

---

## 10. Universal Multilingual Trigger Recognition Engine
1. **Trigger Phrase Persistence**:
   - Master list (`MASTER_TRIGGER_WORDS`) contains exhaustive variants across English, Roman Urdu, and Hindi.
   - Extended validation limit to 5000 characters to prevent tag truncation.
   - Inherited by all new creators and persisted across sessions.

---

## 12. Native YouTube Cloud Scheduling & Overlay Auto-Purge
1. **Native YouTube Cloud Scheduling (`accounts.py`, `posting.py`)**:
   - Transformed "Add to queue" from local waiting to direct, immediate upload to YouTube's cloud servers with native `publishAt` RFC3339 timestamp scheduling.
   - Automatically spaces queued clips at 1-hour intervals (`post_gap_min = 60`): 1st clip at +1h, 2nd clip at +2h, etc.
   - Status is set to `privacyStatus: "private"` and `publishAt: "YYYY-MM-DDTHH:MM:SS.000Z"`.
   - YouTube processes the video immediately in the cloud and automatically flips it to public at the scheduled timestamp, freeing the user from keeping their PC or PeakCut server running.
   - Clip cards display "Scheduled for <time>" badges with direct links to the Short and "📌 Studio" buttons linking to YouTube Studio.
2. **Streamer Overlay & Subscriber Count Bar Auto-Purge (`render.py`)**:
   - Webcam bounding box is cleanly purged of bottom overlays: bottom 12% (`fh_clean = max(10, int(fh * 0.88))`) is trimmed away in `split` and `split_half` layouts.
   - Slices away ugly half-cut live subscriber counts, ticker bars, and broadcaster desk borders while top-anchoring the streamer's face, hair, and shoulders with full visual clarity.

---

## 13. Multi-API Key Pool, OpenRouter Free Fallback & Universal Grounding
1. **Multi-API Key Pool & Auto-Rotation (`studio/ai.py`, `studio/server.py`, `web/index.html`)**:
   - Interactive Pool Management: Users can see all keys listed individually (`Key #1`, `Key #2`, etc.) with masked strings (e.g. `AQ.Ab8...eJ6Q`).
   - Real-Time Status Indicators: Active key shows `🟢 Live / Active`; backup standby keys show `⚪ Standby (Auto-rotates)`.
   - Granular CRUD: Each key has an individual red `🗑️ Remove` button (`DELETE /api/ai/keys/{idx}`), and an `[➕ Add Key]` row (`POST /api/ai/keys`) allows adding keys one by one without overwriting the pool.
   - `_retry_on_quota` wraps API calls: when an active key hits HTTP 429, ResourceExhausted, or token exhaustion, PeakCut rotates automatically to the next working key in the pool without failing the operation.
   - Built-in OpenRouter free models fallback pool (`OPENROUTER_FREE_MODELS`: Gemini 2.0 Flash Exp free, LLaMA 3.3 70B free, Qwen 2.5 72B free, Mistral Small free).
2. **Universal Grounding Anti-Hallucination Constraints (`studio/brain.py`, `studio/jobs.py`)**:
   - Multi-modal vision analysis automatically evaluates physical video frames for newly generated clips.
   - Grounding rules strictly forbid inventing actions, items, vehicles, or interactions that are not physically present on screen (e.g. rooms, elevators, hallways, outdoor).
   - If the speech is ambiguous, negated, or inquiring ("where is X", "there is no X"), the situation is properly identified as searching or confusion, avoiding false action claims.

---

## 14. Upstream Synchronization & Windows Robustness Architecture
1. **Zero-Token Fast Hashtags Engine (`studio/hashtags.py`)**:
   - Generates contextual viral hashtags directly from gaming categories and dialogue without consuming Gemini API tokens or hitting network rate limits.
2. **Windows Atomic File Save Resilience (`studio/jobs.py: _put_in_place`)**:
   - Implements backoff-retry on Windows systems where file indexing services or real-time antivirus scanners temporarily hold file handles during atomic file replacements.
3. **Long Video Stream Processing (`studio/media.py`)**:
   - Minimizes memory usage during stream length probes for day-long and 24-hour video streams.
4. **Proxy Header Security Hardening (`studio/server.py: _PROXY_CIDRS`)**:
   - Enforces CIDR verification on upstream reverse proxies to prevent header spoofing in self-hosted or cloud deployments.

---

## 15. Visual Stream & Clip Layout Preview Architecture
1. **Authentic Rendered Sample Previews (`web/brand/layout-*.jpg`)**:
   - Real 540x960 crisp JPG frames extracted from actual gameplay and live streamer broadcasts with real audio/visual subtitle rendering.
   - Covers all 9 supported layouts and 4 corner webcam positions (12 image variants):
     - `split_half`: Classic 50/50 Split with edge-to-edge facecam and subtitle-safe gameplay.
     - `split`: Reaction Split (1/3 Cam, 2/3 Game).
     - `gameplay`: Full Game with Picture-in-Picture facecam in 4 positions (top-right, top-left, bottom-left, bottom-right).
     - `crop`, `left`, `right`: Direct single-frame framing choices.
     - `fit`, `blur`, `zoom`: 16:9 letterbox and ambient background options.
2. **Interactive Phone-Frame Showcase (`web/index.html: drawCreatorForm`)**:
   - Realistic mobile phone frame with bezel and notch dynamically rendering the selected layout's preview.
   - Dynamic specs breakdown: real-time resolution, in-game subtitle visibility, and format recommendations.
   - Quick-Switch Strip: 1-click layout selector tiles with real image thumbnails and active selection indicators.
3. **Fullscreen Layout Comparison Gallery (`web/index.html: #layout_gallery_dlg`)**:
   - Responsive multi-column modal comparing all 9 layouts with high-resolution phone previews, pros/cons, and 1-click selection dispatch.
4. **Context-Aware Previews in Clip Editor & Composer (`drawClipDlg`, `drawAdd`)**:
   - Real-time preview card in clip editing dialog updating dynamically on layout/webcam position change.
   - Thumbnail tiles in the top Composer options replacing abstract CSS bars.

---

## 16. Global Header Navigation, Provider-Matched Key Routing & 1-Click ChatGPT Bridge
1. **Header Navigation Collision Architecture (`web/index.html`)**:
   - Topbar utilizes flexbox static flow (`display: flex; flex-wrap: nowrap; align-items: center; justify-content: space-between`).
   - Creator navigation tabs (`.utabs`: Clips, Setup, Activity) use `position: static !important; transform: none !important`, preventing collision with `#global_ai_bar`.
   - Responsive breakpoint at 980px wraps navigation tabs onto an independent sub-row on narrower viewports.
2. **Provider-Matched Multi-Key Pool Routing (`studio/ai.py`)**:
   - Dynamic key router matches active provider to key prefixes in the pool (`AQ...` -> Gemini, `sk-or-...` -> OpenRouter, `sk-proj...` -> OpenAI).
   - Eliminates 401/400 errors caused by sending cross-provider keys to incorrect endpoints.
   - Automatic failover cycles within provider-matched keys upon encountering rate limits or quota boundaries.
   - Successful tests and key activations automatically clear cached errors (`clear_problem()`, `usage.forget_all()`).
3. **1-Click ChatGPT Bridge (`web/index.html`, `studio/brain.py`)**:
   - **Open in ChatGPT (`open_chatgpt_bridge`)**: Extracts clip metadata (streamer, game, duration, speech transcript, reaction tone), constructs an engineered prompt requesting high-CTR title, description, tags, and pinned comment, copies to clipboard, and opens `https://chatgpt.com/` in a new tab.
   - **Paste from ChatGPT (`paste_chatgpt_seo`)**: Reads clipboard or prompts user, parses JSON or text responses, and auto-populates all SEO fields in the Clip Editor.
   - **Dedicated AI SEO Settings Tab**: Features persona presets (`creator_adaptive`, `hype_speed`, `cs2_skin`, `gta6_openworld`) and model selection for YouTube Shorts optimization.

---

## 17. Interactive Visual Custom Layout & Facecam Studio (CapCut / Streamladder Style)
1. **Interactive Visual Framing Canvas (`web/index.html: #custom_layout_dlg`)**:
   - Built a specialized visual layout studio modal accessible directly from Creator Setup and Clip Editor.
   - 16:9 stream source container displays the live broadcast frame with dual draggable/resizable bounding boxes:
     - **Facecam Box (Cyan `#00F0FF`)**: Positioned over streamer's webcam with 4 corner resize handles.
     - **Gameplay Box (Orange `#FF8C00`)**: Positioned over game action/subtitles with 4 corner resize handles.
   - Coordinates are normalized to source space `[0..1920, 0..1080]` regardless of display scaling or viewport width.
2. **Real-time 9:16 Smartphone Preview**:
   - HTML5 2D canvas (`#cls_phone_canvas`) updates dynamically on mouse/touch drag events via `ctx.drawImage`.
   - Slices exact pixel regions from the source frame and renders live split-screen or PiP with optional cyan glowing broadcast divider.
3. **Backend Multi-Layout Render Engine (`studio/render.py`)**:
   - `mode == "split"`: User sets custom Split Height Ratio (20% to 70%). FFmpeg filtergraph crops webcam and game boxes, scales with Lanczos accurate rounding and unsharp mask, and stacks vertically with broadcast divider.
   - `mode == "pip"`: User chooses corner (Top-Right, Top-Left, Bottom-Left, Bottom-Right) and PIP size. FFmpeg filtergraph scales game to full 9:16 and overlays facecam.
   - `mode == "crop"`: Crops gameplay box directly to 1080x1920 short.
4. **Live Stream Frame Extraction Engine (`studio/server.py`)**:
   - `GET /api/creators/{cid}/frame`: Automatically grabs live stream frame from active session buffer (`*.ts` / `*.mp4`), recent clips, or live Twitch thumbnail (`https://static-cdn.jtvnw.net/previews-ttv/live_user_{user}-1920x1080.jpg`).
   - Also supports custom screenshot upload directly from local disk.

---

## 18. Automatic Roman Urdu Speech Transcripts Transliteration
1. **Root Cause Resolution**:
   - Speech-to-text models previously output Hindi Devanagari script (`अच्छा...`) or Urdu script when Hindi or Urdu audio was spoken.
2. **Transliteration Layer (`studio/transcribe.py`)**:
   - `transcribe.transcribe` returns `roman.words(words)`, converting Devanagari and Urdu script words into clean, natural Roman Urdu (Latin Hinglish script) at word level, keeping timestamps sample-accurate.
   - Guarantees 100% of captions and live transcripts are displayed and rendered in clean Roman Urdu without requiring an external AI call.

---

## 19. Native CapCut Desktop Draft Export Engine
1. **Direct CapCut Desktop Project Generation (`studio/capcut/export.py`)**:
   - Integrated a lightweight Python AST engine (`studio/capcut/pyJianYingDraft`) and template bundle that writes standard CapCut desktop project structures directly into the user's local CapCut draft directory:
     `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\PeakCut_<clip_id>_<slug>\`
   - Generates `draft_info.json`, `draft_meta_info.json`, and supporting metadata files without requiring CapCut to run during export.
2. **Multi-Track Timeline Architecture**:
   - **Video Track ("PeakCut Video")**: Primary 9:16 vertical video clip segment with exact duration in microseconds.
   - **Hook Title Track ("Hook Title")**: Heading title text segment positioned during the first 3.5 seconds.
   - **Captions Track ("Captions")**: Word-level subtitle segments converted into microsecond-accurate time intervals for immediate editing in CapCut.
3. **Seamless 1-Click Desktop Workflow**:
   - API endpoints: `POST /api/jobs/{jid}/clips/{cid}/export-capcut` and `POST /api/jobs/{jid}/clips/{cid}/open-capcut-folder`.
   - Allows users to open any PeakCut clip in CapCut Desktop and instantly apply CapCut's native video filters, 3D transitions, stickers, sound effects, and animations.

---

## 21. OhnePixel Intelligent Livestream Clipping Engine (Multimodal AI & Tiered Fallback)
1. **Intelligent Detection Without "Clip It"**:
   - Upgraded detection engine to discover genuinely entertaining livestream moments without requiring streamers to command "clip it".
   - Automatically detects peaks across emotional reactions, uncontrollable laughter, unusual conversations, clutch gameplay moments, and skin unboxes.
2. **Automatic Dual Mode Capability Selection**:
   - **Mode A (AI Intelligent Scoring)**:
     - Combined weighted multi-signal scoring:
       - **Signal 1: Keyword Relevance (25%)**: Creator-specific vocabulary, expressions, semantic conversation meaning (`studio/ohnepixel.py`).
       - **Signal 2: Excitement and Reaction Intensity (35%)**: Running audio amplitude z-scores, laughter patterns, shock, voice cracks, and chat message velocity spikes.
       - **Signal 3: Actual Visual & Event Evidence (40%)**: Multimodal AI frame inspection via `ai.see_json` verifying real on-screen gameplay events, clutch plays, vehicle physics glitches, or item unbox reveals.
     - **Dynamic Weight Redistribution**: When video frames are unavailable (audio-only or fast stream capture), redistributes 40% weight to Keyword (40%) and Reaction (60%).
     - **Event-Quality Validation Guardrails**:
       - Casual common words alone ("bro", "no", "wait") -> Strictly SKIP.
       - Reaction phrase spoken calmly without visual/audio evidence -> SKIP.
       - Incredible clutch or rare event without loud shouting -> HIGH PRIORITY based on visual evidence.
       - Uncontrollable laughter or "GOLD GOLD GOLD" + skin evidence -> HIGH PRIORITY.
   - **Mode B (Keyword-Only Fallback)**:
     - Automatically active when multimodal AI is unavailable.
     - Tiered phrase prioritization:
       - **Level 1**: High-priority phrases ("WHAT THE FUCK IS THAT", "NO FUCKING WAY", "HOLY SHIT", "ARE YOU SERIOUS", "LET'S FUCKING GO").
       - **Level 2**: Community slang ("MA DRILLA", "REJUICER", "NAUR", "VAS?!", "NEIN", "GOLD GOLD GOLD") requiring reaction spike or chat velocity > 1.5 to clip.
       - **Level 3**: Common words ("BRO", "NO", "OKAY", "WAIT", "WHAT", "GOLD", "KNIFE", "WOW") never clipped alone.
3. **Continuous Moment Discovery & Smart Clip Boundaries**:
   - Natural narrative boundary structure:
     - Pre-roll: 18s (captures setup / anticipation).
     - Post-roll: 25s (captures reaction / payoff).
     - Total clip length clamped between 20s and 60s.
   - Multi-trigger candidate merging: overlapping triggers within 15 seconds are merged into a single continuous clip instead of fractured fragments.
4. **Review Feedback API & UI Indicators**:
   - Live dashboard cards display prominent Active Detection Mode badge (`⚡ MODE A (AI INTELLIGENT SCORING)` vs `🎯 MODE B (KEYWORD FALLBACK)`).
   - Clip dialog and badges surface score breakdown (`Score: 88 · KW 25% | RX 32% | VIS 31%`).
   - 1-click review feedback rating endpoint (`POST /api/jobs/{jid}/clips/{cid}/review`) supporting `great`, `good`, `bad`, `missed`, `duplicate`, `false_reaction`.

1. **Physics-Based ASS Subtitle Keyframing (`studio/render.py`)**:
   - Extracted physics keyframing algorithms from `Beautiful-Captions` and `ai-video-captions`.
   - Implemented word-by-word pop and wipe animations natively inside ASS subtitle dialogue tags rendered via `libass`:
     - **`hormozi`**: Bold white text with cyan word-level pop (`\t(0,60,\fscx122\fscy122)\t(60,160,\fscx118\fscy118)\c&H00FFFF&`) and thick 8px black outline.
     - **`mrbeast`**: Bright yellow text with punchy orange highlight pop (`\c&H0066FF&`) and 8px outline.
     - **`karaoke`**: Smooth word-by-word color wipe using `\kf` duration tags.
     - **`bounce`**, **`hype`**, and **`clean`**: Maintained existing high-energy presets.
2. **Interactive Hook Banner Customizer (`web/index.html`, `studio/render.py`)**:
   - Added badge themes: `purple_whip` (Purple card `#2A0845` with hot pink neon glowing border `#FF007F`), `cyber_red` (Action red badge), and `gold_luxury` (Gold border with black backdrop).
   - Real-time sliders in Visual Layout Studio for vertical placement (`hook_y`), width (`hook_w`), font size, and badge theme.
   - Real-time 9:16 phone mockup canvas renders the exact Hook Banner pill with drop shadow, border, and title text, alongside live sample bouncy subtitles.

## 8. YouTube Cover Thumbnail Automation, Viewport Sticky Preview & Stream Folder Hierarchy
1. **YouTube Data API Cover Thumbnail Automation (`studio/accounts.py`, `studio/posting.py`)**:
   - Automated `thumbnails.set` integration pushing high-CTR viral cover JPEG (`clip.jpg` containing the hook banner, facecam, and gameplay action) directly to YouTube on publish.
   - Eliminates manual thumbnail setting in YouTube Studio for uploaded Shorts.
2. **Sticky Video Preview & Decoupled Scroll Engine (`web/index.html`)**:
   - Two-column viewport-locked editor modal (`#clipdlg`, `.editor` at `height: calc(100vh - 36px); overflow: hidden;`).
   - Sticky phone stage (`.editor .stage` with `position: sticky; top: 0; overflow: hidden;`) stays centered and pinned in view while user scrolls the settings panel.
3. **Whole-Banner Single Punch Word Focus (`studio/render.py`)**:
   - Banned streamer names and stopwords from receiving viral canary yellow highlight.
   - Evaluates whole banner before line-break splitting, guaranteeing exactly 1 punch word highlighted in yellow across all lines.
4. **Collapsible Stream Project Folders (`web/index.html`)**:
   - 1-click fold/expand toggle for stream cards with localStorage state persistence.
   - Compact folded summary cards (`📁 N clips inside this project`) saving massive vertical scrolling.

---

## 24. Clip Origin Taxonomy, Twitch Live Chat Stream & Viral Teaser Cold Open Architecture
1. **Clip Origin Taxonomy & Distinction**:
   - **`source: "manual"`**: Triggered via user button click ("Clip last 30s", "Clip now", "Hand clip"). Displays prominent pink badge `👆 MANUAL` (independent of multimodal score evaluation).
   - **`source: "trigger"`**: Triggered via reaction phrase or creator custom keyword. Displays amber badge `🎯 "<word>"` (e.g. `🎯 "Oh my god"`, `🎯 "Chat"`).
   - **`source: "ai_auto"`**: Detected automatically by AI without button or trigger phrase. Displays cyan/green badge `🤖 AI AUTO <score>`.
2. **Real-Time Twitch Live Chat Streaming**:
   - Background IRC client connects to `irc.chat.twitch.tv:6697` anonymously.
   - Parses `PRIVMSG` lines into circular buffer `self.recent_chat_msgs` (`user`, `msg`, `t`).
   - Frontend renders live scrolling chat window matching the AI decision feed height (190px) with user colored badges and 1-click Popout Chat window option.
3. **Viral Climax Teaser Cold Open Hook Pipeline**:
   - Allows creators to take the end 3-5 seconds (reaction climax) and prepend it at 0:00 as a teaser hook.
   - Interactive control in `#clipdlg` with duration selector and `🎯 Use Current Video Playhead` button.
   - Single-pass ffmpeg concatenation (`concat=n=2:v=1:a=1`), shifting transcript subtitles by `teaser_dur` and displaying the Hook Banner over the teaser cold open.






