"""Official Google Gen AI SDK (`google-genai`) integration, free-tier model policy,
and multimodal media inference for PeakCut / ClipNova AI.

Respects Google's project-level rate limits:
- Never hardcodes or logs API keys.
- Verifies model capabilities from official specs & live models.list() discovery.
- Enforces Free Mode Only by blocking paid-only Gemini models and paid providers when enabled.
- Explicitly reports when project billing/tier status cannot be auto-verified via API.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Any

from . import config, safe

try:
    from google import genai
    from google.genai import types as genai_types
    SDK_AVAILABLE = True
except Exception:  # pragma: no cover - fallback handled gracefully
    genai = None
    genai_types = None
    SDK_AVAILABLE = False

# Verified from official Google Gemini API docs (https://ai.google.dev/gemini-api/docs/models & /pricing)
# Nov 2026 catalog: Gemini 4 Hydrogen is GA and available on Free Tier ($0) with Text/Image/Video/Audio/PDF.
OFFICIAL_GEMINI_MODELS: dict[str, dict[str, Any]] = {
    "gemini-4-hydrogen": {
        "name": "Gemini 4 Hydrogen",
        "free_tier": True,
        "paid_only": False,
        "pricing": "Free Tier ($0) · Paid $1.50/$7.50 per 1M",
        "modalities": ["text", "image", "video", "audio", "pdf"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Primary (Multimodal Reasoning, Ranking & Final-Cut SEO)",
        "context": "1,048,576 tokens",
        "rate_note": "Project-based RPM/RPD (check Google AI Studio)",
        "desc": "Primary free-tier model: watches video + listens to audio, deep moment reasoning & grounded SEO.",
    },
    "gemini-3.5-flash-lite": {
        "name": "Gemini 3.5 Flash-Lite",
        "free_tier": True,
        "paid_only": False,
        "pricing": "Free Tier ($0) · Paid $0.30/$2.50 per 1M",
        "modalities": ["text", "image", "video", "audio", "pdf"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Verified Free Fallback / Fast Candidate Discovery",
        "context": "1,048,576 tokens",
        "rate_note": "Free Tier Standard & Batch eligible",
        "desc": "Verified free-tier fallback: high throughput multimodal & JSON output.",
    },
    "gemini-3.8-flash": {
        "name": "Gemini 3.8 Flash",
        "free_tier": True,
        "paid_only": False,
        "pricing": "Free Tier ($0) · Paid $0.75/$3.75 per 1M",
        "modalities": ["text", "image", "video", "audio", "pdf"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Secondary Free Multimodal Flash",
        "context": "1,048,576 tokens",
        "rate_note": "Project-based RPM/RPD",
        "desc": "Free-tier multimodal Flash model with agentic video understanding.",
    },
    "gemini-3.6-flash": {
        "name": "Gemini 3.6 Flash",
        "free_tier": True,
        "paid_only": False,
        "pricing": "Free Tier ($0) · Paid $0.75/$3.75 per 1M",
        "modalities": ["text", "image", "video", "audio", "pdf"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Legacy Free Multimodal Flash",
        "context": "1,048,576 tokens",
        "rate_note": "Project-based RPM/RPD",
        "desc": "Previous-generation Flash model with free tier.",
    },
    "gemini-3.1-flash-lite": {
        "name": "Gemini 3.1 Flash-Lite",
        "free_tier": True,
        "paid_only": False,
        "pricing": "Free Tier ($0)",
        "modalities": ["text", "image", "video", "audio", "pdf"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Lightweight Free Backup",
        "context": "1,048,576 tokens",
        "rate_note": "Project-based RPM/RPD",
        "desc": "Lightweight Flash-Lite model with multimodal support.",
    },
    "gemini-flash-lite-latest": {
        "name": "Gemini Flash-Lite Latest",
        "free_tier": True,
        "paid_only": False,
        "pricing": "Free Tier ($0)",
        "modalities": ["text", "image", "video", "audio", "pdf"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Rolling Free Flash-Lite Alias",
        "context": "1,048,576 tokens",
        "rate_note": "Project-based RPM/RPD",
        "desc": "Latest production Flash-Lite release.",
    },
    "gemini-3-flash-preview": {
        "name": "Gemini 3 Flash Preview",
        "free_tier": True,
        "paid_only": False,
        "pricing": "Free Tier ($0)",
        "modalities": ["text", "image", "video", "audio"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Preview Flash Backup",
        "context": "1,048,576 tokens",
        "rate_note": "Preview rate limits",
        "desc": "Gemini 3 Flash preview model.",
    },
    # Explicitly Paid-Only models (blocked when Free Mode Only is enabled)
    "gemini-4-carbon": {
        "name": "Gemini 4 Carbon",
        "free_tier": False,
        "paid_only": True,
        "pricing": "Paid Tier ONLY (No Free Tier)",
        "modalities": ["text", "image", "video", "audio", "pdf"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Blocked in Free Mode Only",
        "context": "1,048,576 tokens",
        "desc": "Frontier paid-only reasoning model; excluded when Free Mode Only is active.",
    },
    "gemini-4-argon": {
        "name": "Gemini 4 Argon",
        "free_tier": False,
        "paid_only": True,
        "pricing": "Paid Tier ONLY (No Free Tier)",
        "modalities": ["text", "image", "video", "audio", "pdf"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Blocked in Free Mode Only",
        "context": "1,048,576 tokens",
        "desc": "Paid-only reasoning model; excluded when Free Mode Only is active.",
    },
    "gemini-4-neon": {
        "name": "Gemini 4 Neon",
        "free_tier": False,
        "paid_only": True,
        "pricing": "Paid Tier ONLY ($3.00/$15.00 per 1M)",
        "modalities": ["text", "image", "video", "audio", "pdf"],
        "video": True,
        "audio": True,
        "vision": True,
        "structured_json": True,
        "role": "Blocked in Free Mode Only",
        "context": "1,048,576 tokens",
        "desc": "Paid-only flagship model; excluded when Free Mode Only is active.",
    },
}

PAID_MODEL_PREFIXES = (
    "gemini-4-carbon",
    "gemini-4-argon",
    "gemini-4-neon",
    "gemini-3.1-pro",
    "gemini-3-pro",
    "gemini-2.5-pro",
    "gemini-omni",
    "gpt-4",
    "o1",
    "o3",
    "o4",
    "claude-",
    "grok-",
)

DEFAULT_FREE_PAIR = ["gemini-4-hydrogen", "gemini-3.5-flash-lite"]

_cache_lock = threading.Lock()


def _cache_dir() -> Path:
    d = config.DATA_DIR / "cache" / "ai"
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_paid_only_model(model_id: str) -> bool:
    mid = (model_id or "").strip().lower().removeprefix("models/")
    if not mid:
        return False
    if mid in OFFICIAL_GEMINI_MODELS:
        return bool(OFFICIAL_GEMINI_MODELS[mid].get("paid_only"))
    if mid.endswith(":free"):
        return False
    return any(mid.startswith(pref) for pref in PAID_MODEL_PREFIXES)


def is_known_free_gemini(model_id: str) -> bool:
    mid = (model_id or "").strip().lower().removeprefix("models/")
    if mid in OFFICIAL_GEMINI_MODELS:
        return bool(OFFICIAL_GEMINI_MODELS[mid].get("free_tier"))
    return ("flash" in mid or "gemma-4" in mid or "gemma-3" in mid) and not is_paid_only_model(mid)


def model_metadata(model_id: str) -> dict[str, Any]:
    mid = (model_id or "").strip().removeprefix("models/")
    meta = OFFICIAL_GEMINI_MODELS.get(mid)
    if meta:
        return {"id": mid, **meta}
    paid = is_paid_only_model(mid)
    return {
        "id": mid,
        "name": mid,
        "free_tier": not paid and ("gemini" in mid or "gemma" in mid),
        "paid_only": paid,
        "pricing": "Paid Tier ONLY" if paid else "Check AI Studio pricing table",
        "modalities": ["text", "image", "video", "audio"] if "gemini" in mid else ["text"],
        "video": "gemini" in mid and "tts" not in mid and "image" not in mid,
        "audio": "gemini" in mid and "image" not in mid,
        "vision": "gemini" in mid or "vision" in mid,
        "structured_json": True,
        "role": "Discovered Model",
        "context": "Up to 1M tokens" if "gemini" in mid else "Model-specific",
        "desc": "Discovered via Gemini API models catalog.",
    }


def tier_verification_info(confirmed_at: float | None = None) -> dict[str, Any]:
    """Google Gemini API key endpoints do NOT return billing plan headers.
    Honest status that tells the owner exactly what to verify in Google AI Studio."""
    confirmed = bool(confirmed_at and float(confirmed_at) > 0)
    return {
        "auto_verifiable": False,
        "verified": confirmed,
        "confirmed_at": float(confirmed_at or 0.0),
        "status": "user_confirmed_free" if confirmed else "unverified_manual_check_required",
        "summary": (
            "Manual AI Studio billing check confirmed by owner (Free Mode Only active)."
            if confirmed else
            "Gemini API does not expose project billing status automatically. Confirm your project is on Free Tier before heavy runs."
        ),
        "check_url": "https://aistudio.google.com/apikey",
        "steps": [
            "Open Google AI Studio (https://aistudio.google.com/apikey) and locate the Project owning your key.",
            "Check Usage & Billing / Plan column for that project: ensure Plan shows 'Free of charge' and NO Google Cloud Billing account is linked.",
            "Remember Free Tier prompts/media may be used by Google to improve products — do not upload confidential footage unless upgraded.",
        ],
    }


def make_client(api_key: str):
    if not SDK_AVAILABLE or not api_key:
        return None
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})


def discover_models(api_key: str, free_only: bool = True) -> list[dict[str, Any]]:
    """Dynamically query Google AI Studio /v1beta/models via the official google-genai SDK."""
    client = make_client(api_key)
    if client is None:
        raise RuntimeError("google-genai SDK unavailable or missing API key.")
    discovered: list[dict[str, Any]] = []
    for m in client.models.list(config={"page_size": 200}):
        raw_name = str(getattr(m, "name", "") or "")
        mid = raw_name.split("/")[-1]
        if not mid:
            continue
        actions = list(getattr(m, "supported_actions", None) or getattr(m, "supported_generation_methods", None) or [])
        if actions and "generateContent" not in actions:
            continue
        low = mid.lower()
        if low == "aqa" or any(t in low for t in ("-tts", "-image", "imagen-", "veo-", "lyria-", "embedding", "computer-use", "robotics", "decision", "antigravity-", "deep-research-", "gemini-2.5-", "gemini-2.0-", "gemini-1.5-")):
            continue
        meta = model_metadata(mid)
        if free_only and meta.get("paid_only"):
            continue
        in_lim = getattr(m, "input_token_limit", None)
        out_lim = getattr(m, "output_token_limit", None)
        discovered.append({
            **meta,
            "input_limit": int(in_lim) if in_lim else None,
            "output_limit": int(out_lim) if out_lim else None,
            "accessible": True,
        })
    # Sort preferred Free-Tier models first (gemini-4-hydrogen -> gemini-3.5-flash-lite -> gemini-3.8-flash -> rest)
    order = {"gemini-4-hydrogen": 0, "gemini-3.5-flash-lite": 1, "gemini-3.8-flash": 2, "gemini-3.6-flash": 3}
    discovered.sort(key=lambda item: (order.get(item["id"], 50), item["id"]))
    return discovered


def _json_schema_clean(s: Any) -> Any:
    if isinstance(s, dict):
        return {k: (v.upper() if k == "type" and isinstance(v, str) and v.lower() in ("object", "array", "string", "integer", "number", "boolean") else _json_schema_clean(v))
                for k, v in s.items()}
    if isinstance(s, list):
        return [_json_schema_clean(x) for x in s]
    return s


def _extract_json_text(raw: str) -> Any:
    txt = (raw or "").strip()
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.I).strip()
    try:
        out = json.loads(txt)
    except ValueError:
        m = re.search(r"[\[{].*[\]}]", txt, re.S)
        if not m:
            raise ValueError(f"Gemini did not return valid JSON: {txt[:120]}")
        out = json.loads(m.group(0))
    if isinstance(out, dict) and "items" in out and len(out) == 1:
        return out["items"]
    return out


def cache_key(task: str, model: str, prompt: str, media_bytes: list[tuple[str, bytes]] | None = None) -> str:
    h = hashlib.sha256()
    h.update(task.encode("utf-8", "ignore"))
    h.update(b"\0")
    h.update(model.encode("utf-8", "ignore"))
    h.update(b"\0")
    h.update(prompt.encode("utf-8", "ignore"))
    for mime, blob in (media_bytes or []):
        h.update(mime.encode("utf-8", "ignore"))
        h.update(str(len(blob)).encode())
        h.update(hashlib.sha256(blob).digest())
    return h.hexdigest()


def get_cached(ckey: str, max_age: int = 86400) -> Any | None:
    f = _cache_dir() / f"{ckey}.json"
    if not f.is_file():
        return None
    data = safe.load_json_with_backup(f)
    if not isinstance(data, dict):
        return None
    if max_age > 0 and time.time() - float(data.get("ts") or 0) > max_age:
        return None
    return data.get("value")


def put_cached(ckey: str, value: Any, meta: dict | None = None):
    f = _cache_dir() / f"{ckey}.json"
    payload = {"ts": time.time(), "value": value, "meta": meta or {}}
    with _cache_lock:
        safe.atomic_write_text(f, json.dumps(payload), backup=False)


def clear_cache() -> int:
    d = _cache_dir()
    removed = 0
    for f in d.glob("*.json*"):
        try:
            f.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def generate_content_json(
    api_key: str,
    model: str,
    prompt: str,
    schema: dict | None = None,
    media_parts: list[tuple[str, bytes]] | None = None,
    timeout: float = 45.0,
    temperature: float = 0.25,
) -> tuple[Any, int, int]:
    """Execute a real Gemini API call using google-genai SDK (`models.generate_content`),
    supporting text + native inline video/audio/image parts and JSON schema responses.
    For media larger than 18 MB, uploads via client.files.upload and cleans up after use.
    """
    client = make_client(api_key)
    if client is None:
        raise RuntimeError("google-genai SDK not initialized.")

    parts: list[Any] = []
    uploaded_names: list[str] = []
    tmp_files: list[Path] = []
    try:
        for idx, (mime, blob) in enumerate(media_parts or []):
            if not blob:
                continue
            if len(blob) <= 18 * 1024 * 1024:
                parts.append(genai_types.Part.from_bytes(data=blob, mime_type=mime))
            else:
                ext = ".mp4" if "mp4" in mime else (".mp3" if "mp3" in mime or "mpeg" in mime else ".bin")
                tf = config.TMP_DIR / f"gapi_{os.getpid()}_{int(time.time()*1000)}_{idx}{ext}"
                tf.write_bytes(blob)
                tmp_files.append(tf)
                uf = client.files.upload(file=str(tf), config={"mime_type": mime})
                while getattr(uf, "state", None) and getattr(uf.state, "name", "") == "PROCESSING":
                    time.sleep(2)
                    uf = client.files.get(name=uf.name)
                uploaded_names.append(uf.name)
                parts.append(uf)
        parts.append(prompt)

        cfg_kwargs: dict[str, Any] = {"temperature": temperature, "response_mime_type": "application/json"}
        if schema:
            cfg_kwargs["response_schema"] = _json_schema_clean(schema)
        cfg = genai_types.GenerateContentConfig(**cfg_kwargs)
        resp = client.models.generate_content(model=model.removeprefix("models/"), contents=parts, config=cfg)
        raw_text = getattr(resp, "text", None)
        if not raw_text and getattr(resp, "candidates", None):
            chunks = []
            for cand in resp.candidates:
                content = getattr(cand, "content", None)
                for p in getattr(content, "parts", None) or []:
                    if getattr(p, "text", None):
                        chunks.append(p.text)
            raw_text = "".join(chunks)
        parsed = _extract_json_text(raw_text or "")
        um = getattr(resp, "usage_metadata", None)
        sent = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
        total = int(getattr(um, "total_token_count", 0) or 0) if um else 0
        cand_tok = int(getattr(um, "candidates_token_count", 0) or 0) if um else 0
        wrote = max(cand_tok, max(0, total - sent))
        return parsed, sent, wrote
    finally:
        for tf in tmp_files:
            try:
                tf.unlink(missing_ok=True)
            except OSError:
                pass
        for name in uploaded_names:
            try:
                client.files.delete(name=name)
            except Exception:
                pass


def generate_text(
    api_key: str,
    model: str,
    prompt: str,
    media_parts: list[tuple[str, bytes]] | None = None,
    timeout: float = 35.0,
) -> tuple[str, int, int]:
    client = make_client(api_key)
    if client is None:
        raise RuntimeError("google-genai SDK not initialized.")
    parts: list[Any] = []
    for mime, blob in (media_parts or []):
        if blob and len(blob) <= 18 * 1024 * 1024:
            parts.append(genai_types.Part.from_bytes(data=blob, mime_type=mime))
    parts.append(prompt)
    resp = client.models.generate_content(model=model.removeprefix("models/"), contents=parts)
    text = getattr(resp, "text", None) or ""
    um = getattr(resp, "usage_metadata", None)
    sent = int(getattr(um, "prompt_token_count", 0) or 0) if um else 0
    total = int(getattr(um, "total_token_count", 0) or 0) if um else 0
    return text, sent, max(0, total - sent)


def jitter_delay(attempt: int, base: float = 2.0, cap: float = 45.0, retry_after: float | None = None) -> float:
    if retry_after is not None and retry_after > 0:
        return min(cap, float(retry_after) + random.uniform(0.2, 1.0))
    return min(cap, base * (2 ** attempt) + random.uniform(0.3, 1.8))
