# 🎬⚡ ClipNova AI — Autonomous Live Stream & Video Clipper

<p align="center">
  <img src="web/brand/app-icon.png" width="160" height="160" style="border-radius: 36px; box-shadow: 0 12px 36px rgba(0, 240, 255, 0.35);" alt="ClipNova AI Logo" /><br>
  <b>ClipNova AI</b><br>
  <i>Turn long videos and live streams into viral, captioned vertical 9:16 clips automatically.</i>
</p>

<p align="center">
  <a href="https://github.com/ahsanK225"><img src="https://img.shields.io/badge/Author-ahsanK225-6366F1?style=for-the-badge&logo=github" alt="Author ahsanK225"></a>
  <a href="https://www.instagram.com/itz_ahsan.iqbal/?__pwa=1"><img src="https://img.shields.io/badge/Instagram-itz__ahsan.iqbal-E4405F?style=for-the-badge&logo=instagram" alt="Instagram"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-00F0FF?style=for-the-badge" alt="License MIT"></a>
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi" alt="FastAPI">
</p>

---

**ClipNova AI** is an autonomous AI-powered video clipping and stream highlight engine. It turns long YouTube videos, Twitch streams, Kick broadcasts, or raw video uploads into high-retention, captioned 9:16 vertical clips ready for TikTok, YouTube Shorts, and Instagram Reels. 

Run it 100% on your own computer or deploy on a cloud server with your own AI keys.

---

## 🚀 Key Features

- **Autonomous Live Stream Clipping**: Monitor live streams (YouTube, Twitch, Kick) in real-time. Detects peak moments using live audio energy, chat velocity, and rolling speech-to-text transcription.
- **Visual Custom Layout & Facecam Studio**:
  - Interactive split screen (Facecam top / Gameplay bottom).
  - Custom drag-and-drop bounding boxes with real-time 9:16 phone canvas preview.
  - PiP (Picture-in-Picture), Zoom, Dynamic Blur Fill, and Fullscreen crop modes.
- **Creator Custom Presets**: Save custom bounding box ratios (e.g. `gg`, `gg2`) per creator and re-render existing clips with a single click.
- **High-Retention Animated Captions**: Word-by-word synchronized subtitles in 6 trending styles (Bounce, Hormozi Cyan Pop, MrBeast Orange/Yellow, Karaoke Wipe, Hype, Clean).
- **100% Private Offline Transcription**: Transcribes audio locally using NVIDIA's Parakeet (English) and FastConformer (Arabic) via `sherpa-onnx`. Audio never leaves your computer.
- **AI Viral SEO Engine**: Automatically generates engaging hook titles, viral descriptions with emojis, and trending hashtags.
- **One-Click Multi-Platform Auto-Posting**: Connect YouTube, Instagram, and TikTok to queue or publish clips directly.
- **Multi-Model AI Support**: Works with Google Gemini, OpenAI, Grok (xAI), Groq, OpenRouter, Anthropic Claude, or local offline LLMs via Ollama.

---

## 🛠️ Quick Start

### 1. Requirements
- Python 3.10+
- `ffmpeg` installed on your system:
  - **Windows**: `winget install Gyan.FFmpeg`
  - **macOS**: `brew install ffmpeg`
  - **Linux**: `sudo apt install ffmpeg`

### 2. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/ahsanK225/ClipNova-AI.git

# Enter repository directory
cd ClipNova-AI

# Create virtual environment and activate
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Start ClipNova AI

```bash
python -m studio.server
```

Open your browser at **`http://127.0.0.1:8765`**.

> On first launch, the local speech transcription model (~480 MB) downloads automatically once.

---

## ⚙️ AI Configuration

ClipNova AI requires an LLM with structured JSON output for clip evaluation and copy generation.

Configure it easily in **Settings → AI** inside the dashboard, or create a `.env` file in the root folder:

```ini
PEAKCUT_AI_PROVIDER=gemini
PEAKCUT_AI_MODELS=gemini-2.5-flash
PEAKCUT_AI_KEY=your-api-key-here
```

### Supported AI Providers:
| Provider | Setting Value | Where to Get Key |
|---|---|---|
| **Google Gemini** | `gemini` | [Google AI Studio](https://aistudio.google.com/apikey) |
| **OpenAI** | `openai` | [OpenAI Platform](https://platform.openai.com/api-keys) |
| **Grok (xAI)** | `xai` | [xAI Console](https://console.x.ai) |
| **Groq** | `groq` | [Groq Cloud](https://console.groq.com/keys) |
| **OpenRouter** | `openrouter` | [OpenRouter AI](https://openrouter.ai/keys) |
| **Claude** | `anthropic` | [Anthropic Console](https://console.anthropic.com) |
| **Ollama** (Local) | `ollama` | [Ollama](https://ollama.com) (No key needed) |

---

## 🏗️ Architecture

| Layer | Technologies & Purpose |
|---|---|
| **Backend** | Python, FastAPI, SQLite / PostgreSQL, Asyncio workers |
| **Media Engine** | FFmpeg, yt-dlp, Sherpa-ONNX (NVIDIA Parakeet & FastConformer) |
| **Frontend** | Responsive Vanilla JS, HTML5 Canvas 9:16 layout studio, Neon CSS Design System |
| **AI Integration** | `studio/ai.py` unified provider client (Gemini, OpenAI, Groq, Ollama) |
| **Deployment** | Docker, Docker Compose, Caddy Reverse Proxy with Automatic HTTPS |

---

## 🔒 Privacy & Security

- **Local Execution**: By default, ClipNova AI runs strictly on `127.0.0.1` and does not accept remote traffic.
- **Audio Privacy**: Audio transcripts are processed locally on your machine.
- **Zero Token Leakage**: API keys and secrets are saved strictly in the local data directory and `.env`, never exposed in web responses or git.

---

## 📜 License & Credits

- Released under the [MIT License](LICENSE).
- Developed & Maintained by **[ahsanK225](https://github.com/ahsanK225)**.
- Follow on Instagram: **[@itz_ahsan.iqbal](https://www.instagram.com/itz_ahsan.iqbal/?__pwa=1)**.
