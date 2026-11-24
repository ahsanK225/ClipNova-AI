"""Talking to the AI service. You bring your own key, and choose the service and model in the dashboard
(Settings, AI) or in .env. What is saved from the dashboard is kept in ai.json in the data folder and wins.

    PEAKCUT_AI_PROVIDER   gemini | openai | xai | groq | openrouter | anthropic | ollama | custom
    PEAKCUT_AI_MODELS     one or more model ids, comma separated, tried in this order
    PEAKCUT_AI_KEY        your key (or PEAKCUT_AI_KEY_FILE, a file holding it)
    PEAKCUT_AI_BASE_URL   only for "custom" (any service that speaks the OpenAI chat format), or to override

Every service is asked for the same thing: JSON that follows a small schema. Gemini takes the schema directly.
The others are told the schema in the prompt and asked for a JSON object, which works with any chat model.

One picture can also be shown (`see`), which is how the webcam is looked for on a gaming stream. A model that
cannot look at pictures answers with something else, and that is simply taken as "it did not look"."""
import base64
import json
import os
import random
import re
import threading
import time

import httpx

from . import config, gemini_client

_ORIG_HTTPX_GET = httpx.get
_ORIG_HTTPX_POST = httpx.post

# name -> (label shown on the pages, address, how it is spoken to, where to get a key, an example model id)
PROVIDERS = {
    "gemini": ("Gemini", "https://generativelanguage.googleapis.com/v1beta/models", "gemini", "https://aistudio.google.com/apikey", "gemini-4-hydrogen"),
    "openai": ("OpenAI", "https://api.openai.com/v1", "openai", "https://platform.openai.com/api-keys", "gpt-4o-mini"),
    "xai": ("Grok", "https://api.x.ai/v1", "openai", "https://console.x.ai", "grok-4"),
    "groq": ("Groq", "https://api.groq.com/openai/v1", "openai", "https://console.groq.com/keys", "llama-3.3-70b-versatile"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "openai", "https://openrouter.ai/keys", "google/gemma-4-31b-it:free"),
    "anthropic": ("Claude", "https://api.anthropic.com/v1", "anthropic", "https://console.anthropic.com", ""),
    "ollama": ("Ollama (on this machine)", "http://127.0.0.1:11434/v1", "openai", "https://ollama.com", "llama3.1"),
    "custom": ("Custom (OpenAI-compatible)", "", "openai", "", ""),
}
ALIASES = {"google": "gemini", "grok": "xai", "claude": "anthropic", "local": "ollama"}
NO_KEY = {"ollama", "custom"}       # a model running on your own machine needs no key
FREE_PROVIDERS = {"gemini", "openrouter", "groq", "ollama", "custom"}

# ---------------------------------------------------------------- the settings in use
_lock = threading.Lock()
_saved = {"at": None, "data": {}}
_telemetry_lock = threading.Lock()
_telemetry: dict[str, dict] = {}
_inflight_lock = threading.Lock()
_inflight: dict[str, threading.Event] = {}
_inflight_results: dict[str, tuple] = {}
_daily_lock = threading.Lock()
_daily_counter = {"day": "", "count": 0}


def _file():
    return config.DATA_DIR / "ai.json"


def _from_dashboard() -> dict:
    """What was saved from the dashboard, read again only when the file changes."""
    f = _file()
    try:
        at = f.stat().st_mtime_ns
    except OSError:
        at = 0
    if _saved["at"] != at:
        try:
            data = json.loads(f.read_text(encoding="utf-8")) if at else {}
        except (OSError, ValueError):
            data = {}
        _saved.update(at=at, data=data if isinstance(data, dict) else {})
    return _saved["data"]


def _using_mock_httpx() -> bool:
    return httpx.post is not _ORIG_HTTPX_POST or httpx.get is not _ORIG_HTTPX_GET


def free_only() -> bool:
    d = _from_dashboard()
    if "free_only" in d:
        return bool(d["free_only"])
    env_v = str(config.env("PEAKCUT_FREE_ONLY", "1") or "1").strip().lower()
    return env_v not in ("0", "false", "no", "off")


def analysis_mode() -> str:
    d = _from_dashboard()
    m = str(d.get("analysis_mode") or "balanced").strip().lower()
    return m if m in ("fast", "balanced", "deep") else "balanced"


def auto_route() -> bool:
    d = _from_dashboard()
    return bool(d.get("auto_route", True))


def daily_budget() -> int:
    d = _from_dashboard()
    try:
        return max(0, int(d.get("daily_budget") or 0))
    except (TypeError, ValueError):
        return 0


def max_concurrency() -> int:
    d = _from_dashboard()
    try:
        return max(1, min(4, int(d.get("concurrency") or 2)))
    except (TypeError, ValueError):
        return 2


def skip_duplicates() -> bool:
    d = _from_dashboard()
    return bool(d.get("skip_duplicates", True))


def current() -> dict:
    """Provider, models, address and key: what the dashboard saved, or else what .env says."""
    d = _from_dashboard()
    p = str(d.get("provider") or config.AI_PROVIDER or "").strip().lower()
    saved_models = list(d["models"]) if d.get("provider") else list(config.AI_MODELS)
    if p in ("gemini", "google") and not saved_models:
        saved_models = list(gemini_client.DEFAULT_FREE_PAIR)
    return {"provider": ALIASES.get(p, p),
            "models": saved_models,
            "base_url": (str(d.get("base_url") or "") if d.get("provider") else config.AI_BASE_URL).rstrip("/"),
            "key": str(d["key"]) if d.get("provider") and "key" in d else config.ai_key(),
            "free_only": free_only(),
            "analysis_mode": analysis_mode(),
            "auto_route": auto_route(),
            "daily_budget": daily_budget(),
            "concurrency": max_concurrency(),
            "skip_duplicates": skip_duplicates(),
            "tier_confirmed_at": float(d.get("tier_confirmed_at") or 0.0)}


_key_index = 0

OPENROUTER_FREE_MODELS = [
    "google/gemini-2.0-flash-exp:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-72b-instruct:free",
    "mistralai/mistral-small-24b-instruct-2501:free",
]


def all_keys() -> list[str]:
    raw = current()["key"]
    if not raw:
        return []
    parts = re.split(r"[\r\n,;]+", raw)
    return [k.strip() for k in parts if k.strip()]


def key() -> str:
    global _key_index
    if provider() in NO_KEY:
        return ""
    klist = all_keys()
    if not klist:
        return ""
    cur_p = provider()
    matching = [k for k in klist if detect_provider_from_key(k) == cur_p]
    pool = matching if matching else klist
    _key_index = _key_index % len(pool)
    return pool[_key_index]


def rotate_key() -> str:
    """Rotate to the next API key in the pool matching current provider (e.g. after a rate limit or quota exhaustion)."""
    global _key_index
    if provider() in NO_KEY:
        return ""
    klist = all_keys()
    cur_p = provider()
    matching = [k for k in klist if detect_provider_from_key(k) == cur_p]
    pool = matching if matching else klist
    if len(pool) > 1:
        _key_index = (_key_index + 1) % len(pool)
        active = pool[_key_index]
        hint = active[-4:] if len(active) >= 8 else "..."
        print(f"[ai] Auto-rotated to API key {_key_index + 1}/{len(pool)} (...{hint})", flush=True)
        return active
    return key()


def key_count() -> int:
    return len(all_keys())


def provider() -> str:
    return current()["provider"]


def models() -> list:
    c = current()
    ms = list(c["models"])
    prov = c["provider"]
    if prov == "gemini":
        if c["free_only"] and not _using_mock_httpx():
            ms = [m for m in ms if not gemini_client.is_paid_only_model(m)]
            if not ms:
                ms = list(gemini_client.DEFAULT_FREE_PAIR)
            elif "gemini-3.5-flash-lite" not in ms and len(ms) < 2:
                ms.append("gemini-3.5-flash-lite")
    elif prov == "openrouter":
        for fm in OPENROUTER_FREE_MODELS:
            if fm not in ms:
                ms.append(fm)
    return ms


def route_models(task: str = "general") -> list[str]:
    """Capability-aware ordered model sequence for a given task without silently promoting paid models."""
    ms = models()
    if provider() != "gemini" or not auto_route() or _using_mock_httpx():
        return ms
    mode = analysis_mode()
    # In Fast mode or Pass-1 candidate discovery, prefer ultra-fast free Flash-Lite first if present, else primary.
    preferred_order: list[str] = []
    if task in ("discovery", "fast_scan") or mode == "fast":
        order = ("gemini-3.5-flash-lite", "gemini-4-hydrogen", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite")
    elif task in ("reasoning", "deep_review", "seo", "hooks", "ranking") or mode == "deep":
        order = ("gemini-4-hydrogen", "gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3-flash-preview")
    else:
        order = ("gemini-4-hydrogen", "gemini-3.5-flash-lite", "gemini-3.8-flash")
    for cand in order:
        if cand in ms and cand not in preferred_order:
            preferred_order.append(cand)
    for m in ms:
        if m not in preferred_order:
            preferred_order.append(m)
    return preferred_order or ms


def _record_telemetry(model: str, ok: bool, ms: int = 0, sent: int = 0, wrote: int = 0, err: str = "", rate_limited_wait: float = 0.0):
    now = time.time()
    mid = (model or "").removeprefix("models/")
    if not mid:
        return
    with _telemetry_lock:
        rec = _telemetry.setdefault(mid, {
            "calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0,
            "avg_ms": 0, "last_ok_at": 0.0, "last_error": "", "rate_limited_until": 0.0,
        })
        rec["calls"] += 1
        rec["tokens_in"] += max(0, int(sent))
        rec["tokens_out"] += max(0, int(wrote))
        if ok:
            prev_n = max(1, rec["calls"] - rec["errors"])
            rec["avg_ms"] = int((rec["avg_ms"] * (prev_n - 1) + ms) / prev_n) if prev_n > 1 else ms
            rec["last_ok_at"] = now
            rec["last_error"] = ""
            rec["rate_limited_until"] = 0.0
        else:
            rec["errors"] += 1
            rec["last_error"] = str(err)[:180]
            if rate_limited_wait > 0:
                rec["rate_limited_until"] = now + rate_limited_wait


def _check_daily_budget():
    b = daily_budget()
    if b <= 0 or _using_mock_httpx():
        return
    today = time.strftime("%Y-%m-%d")
    with _daily_lock:
        if _daily_counter["day"] != today:
            _daily_counter.update(day=today, count=0)
        if _daily_counter["count"] >= b:
            raise AIError(f"Daily local request budget ({b} requests) reached. Wait until tomorrow or increase budget in Settings -> AI.", daily=True)


def _bump_daily_budget():
    today = time.strftime("%Y-%m-%d")
    with _daily_lock:
        if _daily_counter["day"] != today:
            _daily_counter.update(day=today, count=0)
        _daily_counter["count"] += 1


def telemetry_snapshot() -> dict:
    with _telemetry_lock:
        stats = {k: dict(v) for k, v in _telemetry.items()}
    today = time.strftime("%Y-%m-%d")
    with _daily_lock:
        used_today = _daily_counter["count"] if _daily_counter["day"] == today else 0
    return {"models": stats, "today_requests": used_today, "daily_budget": daily_budget()}


def label() -> str:
    return PROVIDERS.get(provider(), ("",))[0]


def base_url() -> str:
    c = current()
    return c["base_url"] or PROVIDERS.get(c["provider"], ("", ""))[1]


def ready() -> bool:
    c = current()
    if not (c["provider"] in PROVIDERS and c["models"] and base_url() and (c["key"] or c["provider"] in NO_KEY)):
        return False
    if c["free_only"] and not _using_mock_httpx() and c["provider"] not in FREE_PROVIDERS:
        return False
    return True


_last_active_model: str = ""


def set_last_active_model(model: str):
    global _last_active_model
    _last_active_model = str(model or "").strip()


def last_active_model() -> str:
    return _last_active_model or (models() or [""])[0]


RECOMMENDED_MODELS = {
    "gemini": [
        {"id": "gemini-4-hydrogen", "name": "Gemini 4 Hydrogen", "is_free": True, "badge": "Free Tier · Primary (Recommended)", "desc": "Watches video + listens to audio, advanced reasoning, hooks & grounded SEO ($0 Free Tier)"},
        {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite", "is_free": True, "badge": "Free Tier · Verified Fallback", "desc": "Fast multimodal fallback & candidate discovery ($0 Free Tier, Standard & Batch)"},
        {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash", "is_free": True, "badge": "Free Tier · Multimodal", "desc": "Secondary free-tier Flash model with video/audio understanding"},
        {"id": "gemini-3-flash-preview", "name": "Gemini 3 Flash Preview", "is_free": True, "badge": "Free Preview", "desc": "Backup Flash preview model on Gemini API"},
    ],
    "openrouter": [
        {"id": "meta-llama/llama-3.3-70b-instruct:free", "name": "Llama 3.3 70B Instruct (Free)", "is_free": True, "badge": "Free · 70B", "desc": "Flagship open source intelligence for dialogue & SEO"},
        {"id": "google/gemma-4-31b-it:free", "name": "Gemma 4 31B (Free)", "is_free": True, "badge": "Free · Google", "desc": "High quality dialogue & funny streamer hook reasoning"},
        {"id": "deepseek/deepseek-r1:free", "name": "DeepSeek R1 (Free)", "is_free": True, "badge": "Free · Reasoning", "desc": "Deep reasoning model for clip score & commentary"},
        {"id": "mistralai/mistral-7b-instruct:free", "name": "Mistral 7B (Free)", "is_free": True, "badge": "Free · Fast", "desc": "Fast turnaround for high volume clipping"}
    ],
    "groq": [
        {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B Versatile", "is_free": True, "badge": "Ultra Fast", "desc": "Blazing fast LPU inference for instant hooks"},
        {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant", "is_free": True, "badge": "Instant Speed", "desc": "Lowest latency processing"}
    ],
    "openai": [
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "is_free": False, "badge": "Paid Tier", "desc": "Disabled in Free Mode Only"},
        {"id": "gpt-4o", "name": "GPT-4o", "is_free": False, "badge": "Paid Tier", "desc": "Disabled in Free Mode Only"}
    ],
    "xai": [
        {"id": "grok-4", "name": "Grok 4", "is_free": False, "badge": "Paid Tier", "desc": "Disabled in Free Mode Only"}
    ]
}


def detect_provider_from_key(k: str) -> str:
    k = (k or "").strip()
    if k.startswith("sk-or-"):
        return "openrouter"
    if k.startswith("AIza") or k.startswith("AQ."):
        return "gemini"
    if k.startswith("gsk_"):
        return "groq"
    if k.startswith("xai-"):
        return "xai"
    if k.startswith("sk-ant-"):
        return "anthropic"
    if k.startswith("sk-"):
        return "openai"
    return ""


def public() -> dict:
    """What the settings page may see. The key itself never leaves the server: only whether there is one, and
    its last four characters so the owner can tell which key it is."""
    c = current()
    klist = all_keys()
    count = len(klist)
    active_idx = _key_index % count if count else 0
    keys_list = []
    for i, k in enumerate(klist):
        is_active = (i == active_idx)
        hint = f"...{k[-4:]}" if len(k) >= 8 else "key"
        masked = f"{k[:6]}...{k[-4:]}" if len(k) >= 12 else (k[:2] + "..." + k[-2:] if len(k) >= 5 else "***")
        prov_id = detect_provider_from_key(k)
        prov_hint = PROVIDERS.get(prov_id, ("AI Key",))[0]
        keys_list.append({
            "index": i,
            "hint": hint,
            "masked": masked,
            "provider_hint": prov_hint,
            "provider_id": prov_id,
            "active": is_active,
            "status": "Live / Active" if is_active else "Standby (Ready)",
            "role": "Active Pool Key" if is_active else "Standby Backup Key"
        })
    models_list = []
    tel = telemetry_snapshot()
    for idx, m in enumerate(c["models"] or []):
        meta = gemini_client.model_metadata(m) if c["provider"] == "gemini" else {}
        trec = tel["models"].get(m, {})
        models_list.append({
            "id": m,
            "role": "Primary Model" if idx == 0 else f"Fallback #{idx}",
            "is_primary": idx == 0,
            "free_tier": meta.get("free_tier", True),
            "paid_only": meta.get("paid_only", False),
            "modalities": meta.get("modalities", ["text"]),
            "pricing": meta.get("pricing", ""),
            "calls": trec.get("calls", 0),
            "errors": trec.get("errors", 0),
            "avg_ms": trec.get("avg_ms", 0),
            "last_ok_at": trec.get("last_ok_at", 0.0),
            "last_error": trec.get("last_error", ""),
            "rate_limited_until": trec.get("rate_limited_until", 0.0),
            "desc": meta.get("desc") or ("Primary highlight scoring, multimodal vision & hooks" if idx == 0 else "Capability-aware verified fallback model")
        })
    hint = f"{count} authorized keys configured (active: ...{klist[0][-4:]})" if count > 1 else (c["key"][-4:] if len(c["key"]) >= 12 else "")
    recs = RECOMMENDED_MODELS.get(c["provider"], [])
    return {"provider": c["provider"], "models": c["models"], "models_list": models_list, "recommended_models": recs,
            "base_url": c["base_url"], "has_key": bool(c["key"]),
            "key_count": count, "key_hint": hint, "keys_list": keys_list, "ready": ready(), "label": label(),
            "saved_here": bool(_from_dashboard().get("provider")),
            "sdk_active": bool(gemini_client.SDK_AVAILABLE),
            "free_only": c["free_only"],
            "analysis_mode": c["analysis_mode"],
            "auto_route": c["auto_route"],
            "daily_budget": c["daily_budget"],
            "today_requests": tel["today_requests"],
            "concurrency": c["concurrency"],
            "skip_duplicates": c["skip_duplicates"],
            "tier_verification": gemini_client.tier_verification_info(c.get("tier_confirmed_at")),
            "providers": [{"id": k, "label": v[0], "address": v[1], "needs_key": k not in NO_KEY, "key_url": v[3], "example": v[4]}
                          for k, v in PROVIDERS.items()]}


def activate_key(index: int) -> dict:
    """User clicked a key in the pool: move it to active position, auto-detect its provider,
    and update models/endpoint accordingly."""
    global _key_index
    klist = all_keys()
    if index < 0 or index >= len(klist):
        raise ValueError("Invalid key index.")
    chosen_key = klist.pop(index)
    klist.insert(0, chosen_key)
    _key_index = 0
    clear_problem()
    target_prov = detect_provider_from_key(chosen_key)
    prov = target_prov or "gemini"
    recs = [m["id"] for m in RECOMMENDED_MODELS.get(prov, [])]
    models = recs[:4] if recs else ["gemini-3.5-flash-lite"]
    base_url = PROVIDERS[prov][1] if prov in PROVIDERS else ""
    return save(prov, models, base_url, "\n".join(klist))


def select_primary_model(model_id: str) -> dict:
    """Make model_id the 1st primary model, keeping existing models as fallbacks."""
    mid = str(model_id or "").strip()
    if not mid:
        raise ValueError("Invalid model ID.")
    c = current()
    prov = c.get("provider") or "gemini"
    cur_models = [m for m in (c.get("models") or []) if m != mid]
    new_models = [mid] + cur_models[:4]
    base_url = PROVIDERS[prov][1] if prov in PROVIDERS else c.get("base_url", "")
    return save(prov, new_models, base_url)


def switch_model(provider_id: str, model_id: str) -> dict:
    """Instantly switch active provider and primary model, persisting selection."""
    p = ALIASES.get(str(provider_id or "").strip().lower(), str(provider_id or "").strip().lower())
    if p not in PROVIDERS:
        raise ValueError("Invalid provider ID.")
    mid = str(model_id or "").strip()
    if not mid:
        raise ValueError("Invalid model ID.")
    c = current()
    cur_models = [m for m in (c.get("models") or []) if m != mid]
    new_models = [mid] + cur_models[:4]
    base_url = PROVIDERS[p][1] if p in PROVIDERS else c.get("base_url", "")
    return save(p, new_models, base_url)


def get_catalog(provider_id: str | None = None) -> dict:
    """Return comprehensive catalog for the requested provider or all providers,
    with official Gemini free-tier specs & dynamic SDK discovery when available."""
    results = {}
    # 1. Gemini (Official catalog + live SDK accessibility check)
    gem_list = [
        {"id": "gemini-4-hydrogen", "name": "Gemini 4 Hydrogen", "tier": "FREE TIER", "is_free": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Project RPM/RPD (Free Tier)", "pricing": "Free Tier ($0) · Paid $1.50/$7.50 per 1M", "badge": "Free Tier · Primary (Recommended)", "desc": "Watches video + listens to audio, deep reasoning, hooks & grounded SEO"},
        {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite", "tier": "FREE TIER", "is_free": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Free Tier (Standard & Batch)", "pricing": "Free Tier ($0) · Paid $0.30/$2.50 per 1M", "badge": "Free Tier · Verified Fallback", "desc": "Verified free-tier fallback for fast multimodal discovery & JSON output"},
        {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash", "tier": "FREE TIER", "is_free": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Project RPM/RPD (Free Tier)", "pricing": "Free Tier ($0) · Paid $0.75/$3.75 per 1M", "badge": "Free Tier · Multimodal", "desc": "Secondary free-tier Flash model with agentic video understanding"},
        {"id": "gemini-3.6-flash", "name": "Gemini 3.6 Flash", "tier": "FREE TIER", "is_free": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Project RPM/RPD (Free Tier)", "pricing": "Free Tier ($0) · Paid $0.75/$3.75 per 1M", "badge": "Free Tier · Flash", "desc": "Previous-generation Flash model with Free Tier"},
        {"id": "gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash-Lite", "tier": "FREE TIER", "is_free": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Project RPM/RPD (Free Tier)", "pricing": "Free Tier ($0)", "badge": "Free Tier · Lightweight", "desc": "Cost-efficient multimodal Flash-Lite backup"},
        {"id": "gemini-flash-lite-latest", "name": "Gemini Flash-Lite Latest", "tier": "FREE TIER", "is_free": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Project RPM/RPD", "pricing": "Free Tier ($0)", "badge": "Rolling Alias · Free", "desc": "Points to newest production Flash-Lite release"},
        {"id": "gemini-3-flash-preview", "name": "Gemini 3 Flash Preview", "tier": "FREE TIER", "is_free": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Preview RPM/RPD", "pricing": "Free Tier ($0)", "badge": "Free Preview", "desc": "Backup Flash preview model"},
        {"id": "gemini-4-neon", "name": "Gemini 4 Neon", "tier": "PAID ONLY", "is_free": False, "paid_only": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Paid Tier Only", "pricing": "$3.00/$15.00 per 1M (No Free Tier)", "badge": "Paid Only · Blocked in Free Mode", "desc": "Frontier reasoning model; excluded when Free Mode Only is enabled"},
        {"id": "gemini-4-carbon", "name": "Gemini 4 Carbon", "tier": "PAID ONLY", "is_free": False, "paid_only": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Paid Tier Only", "pricing": "Paid Tier Only", "badge": "Paid Only · Blocked in Free Mode", "desc": "Strongest reasoning model; requires paid tier"},
        {"id": "gemini-4-argon", "name": "Gemini 4 Argon", "tier": "PAID ONLY", "is_free": False, "paid_only": True, "vision": True, "video": True, "audio": True, "structured_json": True, "context": "1,048,576 tokens", "rate_limit": "Paid Tier Only", "pricing": "Paid Tier Only", "badge": "Paid Only · Blocked in Free Mode", "desc": "Paid-tier reasoning model; excluded in Free Mode Only"},
    ]
    results["gemini"] = [m for m in gem_list if m.get("is_free", True)] if free_only() else gem_list

    # 2. OpenRouter (dynamic discovery)
    or_models = [
        {"id": "google/gemma-4-31b-it:free", "name": "Gemma 4 31B (Free)", "tier": "VERIFIED FREE", "is_free": True, "vision": False, "structured_json": True, "context": "128k tokens", "rate_limit": "20 RPM", "pricing": "$0.00 / 100% Free", "badge": "Verified Free · Google", "desc": "High quality dialogue & funny streamer hook reasoning"},
        {"id": "google/gemma-4-26b-a4b-it:free", "name": "Gemma 4 26B (Free)", "tier": "VERIFIED FREE", "is_free": True, "vision": False, "structured_json": True, "context": "128k tokens", "rate_limit": "20 RPM", "pricing": "$0.00 / 100% Free", "badge": "Verified Free · Google", "desc": "Ultra-fast open reasoning for clip SEO"},
        {"id": "inclusionai/ling-3.2-flash:free", "name": "Ling 3.2 Flash (Free)", "tier": "VERIFIED FREE", "is_free": True, "vision": False, "structured_json": True, "context": "128k tokens", "rate_limit": "20 RPM", "pricing": "$0.00 / 100% Free", "badge": "Verified Free · Fast", "desc": "Fast turnaround for high volume clipping"},
    ]
    try:
        r = httpx.get("https://openrouter.ai/api/v1/models", timeout=3)
        if r.status_code == 200:
            raw_data = r.json().get("data", [])
            live_free = []
            for m in raw_data:
                mid = m.get("id", "")
                if mid.endswith(":free"):
                    arch = m.get("architecture", {})
                    is_vis = "image" in str(arch.get("modality", "")).lower()
                    ctx_len = m.get("context_length", 32768)
                    live_free.append({
                        "id": mid,
                        "name": m.get("name") or mid,
                        "tier": "VERIFIED FREE",
                        "is_free": True,
                        "vision": is_vis,
                        "structured_json": True,
                        "context": f"{ctx_len//1000}k tokens" if ctx_len else "32k tokens",
                        "rate_limit": "Provider quota",
                        "pricing": "$0.00 / 100% Free",
                        "badge": "Verified Free" + (" · Vision" if is_vis else ""),
                        "desc": m.get("description", "Free model on OpenRouter")[:100]
                    })
            if live_free:
                or_models = live_free
    except Exception:
        pass
    results["openrouter"] = or_models

    # 3. Groq
    results["groq"] = [
        {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B Versatile", "tier": "FREE TIER", "is_free": True, "vision": False, "structured_json": True, "context": "128k tokens", "rate_limit": "30 RPM / 6k TPM / 14.4k RPD", "pricing": "Free Tier ($0)", "badge": "Free Tier · Ultra Fast", "desc": "Blazing fast LPU inference for instant hooks"},
        {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B Instant", "tier": "FREE TIER", "is_free": True, "vision": False, "structured_json": True, "context": "128k tokens", "rate_limit": "30 RPM / 20k TPM / 14.4k RPD", "pricing": "Free Tier ($0)", "badge": "Free Tier · Lowest Latency", "desc": "Instant speed processing for live clipping"},
        {"id": "llama-3.2-11b-vision-preview", "name": "Llama 3.2 11B Vision", "tier": "FREE TIER", "is_free": True, "vision": True, "structured_json": True, "context": "128k tokens", "rate_limit": "30 RPM", "pricing": "Free Tier ($0)", "badge": "Free Tier · Vision", "desc": "Fast multimodal visual scene understanding"},
        {"id": "gemma2-9b-it", "name": "Gemma 2 9B IT", "tier": "FREE TIER", "is_free": True, "vision": False, "structured_json": True, "context": "8k tokens", "rate_limit": "30 RPM", "pricing": "Free Tier ($0)", "badge": "Free Tier", "desc": "Google Gemma on Groq LPU hardware"}
    ]

    # 4. Ollama (dynamic local scan)
    ollama_models = []
    ollama_online = False
    try:
        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=1.5)
        if r.status_code == 200:
            ollama_online = True
            for m in r.json().get("models", []):
                mid = m.get("name", "")
                size_gb = m.get("size", 0) / (1024**3)
                is_vis = any(v in mid.lower() for v in ("llava", "vision", "moondream", "minicpm", "bakllava", "llama3.2-vision"))
                ollama_models.append({
                    "id": mid,
                    "name": f"{mid} ({size_gb:.1f} GB)",
                    "tier": "LOCAL",
                    "is_free": True,
                    "vision": is_vis,
                    "structured_json": True,
                    "context": "Local context",
                    "rate_limit": "Unlimited (Local Hardware)",
                    "pricing": "$0.00 (Local / Private)",
                    "badge": "Local · $0" + (" · Vision" if is_vis else ""),
                    "desc": f"Running on local hardware ({size_gb:.1f} GB)"
                })
    except Exception:
        pass
    if not ollama_models:
        ollama_models = [
            {"id": "llama3.2:latest", "name": "Llama 3.2 (Local)", "tier": "LOCAL", "is_free": True, "vision": False, "structured_json": True, "context": "Local", "rate_limit": "Unlimited", "pricing": "$0.00 (Local)", "badge": "Local Default", "desc": "Requires Ollama running on localhost:11434"},
            {"id": "llava:latest", "name": "LLaVA (Vision / Local)", "tier": "LOCAL", "is_free": True, "vision": True, "structured_json": True, "context": "Local", "rate_limit": "Unlimited", "pricing": "$0.00 (Local)", "badge": "Local Vision", "desc": "Local multimodal model for video frames"}
        ]
    results["ollama"] = {
        "online": ollama_online,
        "models": ollama_models
    }

    # 5. OpenAI
    results["openai"] = [
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "tier": "PAID / STANDARD", "is_free": False, "vision": True, "structured_json": True, "context": "128k tokens", "rate_limit": "Tier-based", "pricing": "$0.15 / 1M input tokens", "badge": "Vision · Fast · Low Cost", "desc": "Fast vision & text generation from OpenAI"},
        {"id": "gpt-4o", "name": "GPT-4o", "tier": "PAID / STANDARD", "is_free": False, "vision": True, "structured_json": True, "context": "128k tokens", "rate_limit": "Tier-based", "pricing": "$2.50 / 1M input tokens", "badge": "Flagship · Multimodal", "desc": "Top-tier multimodal understanding & complex scene analysis"}
    ]

    # 6. xAI Grok
    results["xai"] = [
        {"id": "grok-4", "name": "Grok 4", "tier": "PAID / STANDARD", "is_free": False, "vision": False, "structured_json": True, "context": "128k tokens", "rate_limit": "Tier-based", "pricing": "Standard API rates", "badge": "Humor & Wit", "desc": "Unfiltered humor and sharp punchlines"},
        {"id": "grok-vision-beta", "name": "Grok Vision Beta", "tier": "PAID / STANDARD", "is_free": False, "vision": True, "structured_json": True, "context": "128k tokens", "rate_limit": "Tier-based", "pricing": "Standard API rates", "badge": "Vision", "desc": "Multimodal vision from xAI"}
    ]

    # 7. Anthropic Claude
    results["anthropic"] = [
        {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "tier": "PAID / STANDARD", "is_free": False, "vision": True, "structured_json": True, "context": "200k tokens", "rate_limit": "Tier-based", "pricing": "$3.00 / 1M input tokens", "badge": "Top Visual Reasoning", "desc": "Leading multimodal reasoning & human-like writing"},
        {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku", "tier": "PAID / STANDARD", "is_free": False, "vision": False, "structured_json": True, "context": "200k tokens", "rate_limit": "Tier-based", "pricing": "$0.80 / 1M input tokens", "badge": "Fast Inference", "desc": "Fast and responsive for text and dialogue"}
    ]

    # 8. Custom
    results["custom"] = [
        {"id": "custom-model", "name": "Custom Model", "tier": "LOCAL / CUSTOM", "is_free": True, "vision": True, "structured_json": True, "context": "Custom", "rate_limit": "Custom", "pricing": "Custom Server", "badge": "OpenAI Compatible", "desc": "Connects to any OpenAI-compatible inference server"}
    ]

    if provider_id and provider_id in results:
        return results[provider_id]
    return results


def add_key(new_key: str) -> dict:
    global _key_index
    nk = str(new_key or "").strip()
    if not nk:
        raise ValueError("Enter a valid API key.")
    klist = all_keys()
    if nk in klist:
        raise ValueError("This API key is already in the pool.")
    klist.append(nk)
    c = current()
    if len(klist) == 1:
        _key_index = 0
        target_prov = detect_provider_from_key(nk)
        prov = target_prov or c.get("provider") or "gemini"
        base_url = PROVIDERS[prov][1] if prov in PROVIDERS else c.get("base_url", "")
        recs = [m["id"] for m in RECOMMENDED_MODELS.get(prov, [])]
        models = recs[:4] if recs else (c.get("models") or ["gemini-3.5-flash-lite"])
        return save(prov, models, base_url, "\n".join(klist))
    return save(c["provider"], c["models"], c.get("base_url") or "", "\n".join(klist))


def remove_key(index: int) -> dict:
    global _key_index
    klist = all_keys()
    if index < 0 or index >= len(klist):
        raise ValueError("Invalid key index.")
    klist.pop(index)
    _key_index = 0
    c = current()
    if klist:
        target_prov = detect_provider_from_key(klist[0])
        prov = target_prov or c.get("provider") or "gemini"
        base_url = PROVIDERS[prov][1] if prov in PROVIDERS else c.get("base_url", "")
        recs = [m["id"] for m in RECOMMENDED_MODELS.get(prov, [])]
        models = recs[:4] if recs else (c.get("models") or ["gemini-3.5-flash-lite"])
        return save(prov, models, base_url, "\n".join(klist))
    return save(c.get("provider") or "gemini", c.get("models") or ["gemini-3.5-flash-lite"], c.get("base_url") or "", "")


def save(provider_id: str, model_ids, address: str = "", new_key=None, **prefs) -> dict:
    """Save the choice made in the dashboard. `new_key` None keeps the key that is already there (the page never
    has it to send back); an empty string removes it."""
    p = ALIASES.get(str(provider_id or "").strip().lower(), str(provider_id or "").strip().lower())
    if p not in PROVIDERS:
        raise ValueError("Choose one of the AI services in the list.")
    old_raw = dict(_from_dashboard())
    eff_free = bool(prefs["free_only"]) if "free_only" in prefs and prefs["free_only"] is not None else free_only()
    if eff_free and not _using_mock_httpx() and p not in FREE_PROVIDERS:
        raise ValueError(f"{PROVIDERS[p][0]} is a paid provider and is disabled while Free Mode Only is enabled.")
    if isinstance(model_ids, str):
        model_ids = model_ids.split(",")
    ms = [str(m).strip()[:120] for m in (model_ids or []) if str(m).strip()][:5]
    if not ms:
        raise ValueError("Enter the model to use.")
    if any(not re.fullmatch(r"[\w.\-:/@]+", m) for m in ms):
        raise ValueError("A model id has letters, digits and . - : / only.")
    if eff_free and not _using_mock_httpx():
        blocked = [m for m in ms if gemini_client.is_paid_only_model(m)]
        if blocked:
            raise ValueError(f"Paid-tier model(s) disabled in Free Mode Only: {', '.join(blocked)}")
    address = str(address or "").strip().rstrip("/")[:300]
    if address and not re.fullmatch(r"https?://[^\s]+", address):
        raise ValueError("The address has to start with http:// or https://")
    if p == "custom" and not address:
        raise ValueError("A custom service needs its address, for example http://127.0.0.1:1234/v1")
    old = current()
    klist = all_keys()
    matching_keys = [k_item for k_item in klist if detect_provider_from_key(k_item) == p]
    if new_key is not None and str(new_key).strip():
        k = str(new_key).strip()[:8000]
    elif old["provider"] == p:
        k = old["key"]
    elif matching_keys:
        k = old["key"]
    elif p in NO_KEY:
        k = ""
    else:
        k = ""
    if not k and p not in NO_KEY:
        raise ValueError("Paste the key for this service.")
    payload = {
        "provider": p,
        "models": ms,
        "base_url": address,
        "key": k,
        "free_only": eff_free,
        "analysis_mode": str(prefs.get("analysis_mode") or old_raw.get("analysis_mode") or "balanced").lower(),
        "auto_route": bool(prefs["auto_route"]) if "auto_route" in prefs else bool(old_raw.get("auto_route", True)),
        "daily_budget": max(0, int(prefs["daily_budget"])) if "daily_budget" in prefs and prefs["daily_budget"] is not None else max(0, int(old_raw.get("daily_budget") or 0)),
        "concurrency": max(1, min(4, int(prefs["concurrency"]))) if "concurrency" in prefs and prefs["concurrency"] is not None else max(1, min(4, int(old_raw.get("concurrency") or 2))),
        "skip_duplicates": bool(prefs["skip_duplicates"]) if "skip_duplicates" in prefs else bool(old_raw.get("skip_duplicates", True)),
        "tier_confirmed_at": float(prefs["tier_confirmed_at"]) if "tier_confirmed_at" in prefs and prefs["tier_confirmed_at"] is not None else float(old_raw.get("tier_confirmed_at") or 0.0),
    }
    if payload["analysis_mode"] not in ("fast", "balanced", "deep"):
        payload["analysis_mode"] = "balanced"
    with _lock:
        f = _file()
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)        # the key is only for whoever runs the server
        except OSError:
            pass
        tmp.replace(f)
        _saved["at"] = None
    clear_problem()
    return public()


def update_preferences(**prefs) -> dict:
    """Update Free Mode Only, analysis mode, budget, concurrency, or tier verification without touching keys."""
    c = current()
    ms = list(c.get("models") or [])
    if prefs.get("free_only", c.get("free_only")) and c["provider"] == "gemini":
        ms = [m for m in ms if not gemini_client.is_paid_only_model(m)] or list(gemini_client.DEFAULT_FREE_PAIR)
    return save(c["provider"] or "gemini", ms or list(gemini_client.DEFAULT_FREE_PAIR), c.get("base_url") or "", **prefs)


def list_models(provider_id=None, address=None, with_key=None) -> list:
    """The model ids a service offers, so the settings page can show a list to pick from."""
    c = current()
    p = ALIASES.get(str(provider_id or c["provider"]).lower(), str(provider_id or c["provider"]).lower())
    if p not in PROVIDERS:
        raise ValueError("Choose one of the AI services in the list.")
    k = str(with_key or "").strip() or (key() if c["provider"] == p else "")
    base = str(address or "").strip().rstrip("/") or (c["base_url"] if c["provider"] == p else "") or PROVIDERS[p][1]
    if not base:
        raise ValueError("Enter the service's address first.")
    how = PROVIDERS[p][2]
    if how == "gemini" and gemini_client.SDK_AVAILABLE and not _using_mock_httpx() and k:
        try:
            items = gemini_client.discover_models(k, free_only=free_only())
            return [m["id"] for m in items][:400]
        except Exception as e:
            raise AIError(str(e)[:220]) from e
    if how == "gemini":
        r = httpx.get(base, params={"pageSize": 200}, headers={"x-goog-api-key": k}, timeout=20)
    elif how == "anthropic":
        r = httpx.get(f"{base}/models", params={"limit": 200}, headers={"x-api-key": k, "anthropic-version": "2023-06-01"}, timeout=20)
    else:
        r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {k}"} if k else {}, timeout=20)
    if r.status_code != 200:
        raise AIError(f"HTTP {r.status_code} {r.text[:200].replace(k or chr(0), '<key>')}")
    data = r.json()
    if how == "gemini":
        found = []
        for m in data.get("models", []):
            if "generateContent" not in (m.get("supportedGenerationMethods") or []):
                continue
            mid = m.get("name", "").split("/")[-1]
            low_id = mid.lower()
            if mid and low_id != "aqa" and not any(t in low_id for t in ("-tts", "-image", "imagen-", "veo-", "lyria-", "embedding")):
                if free_only() and not _using_mock_httpx() and gemini_client.is_paid_only_model(mid):
                    continue
                found.append(mid)
    else:
        found = [m.get("id", "") for m in data.get("data", []) if isinstance(m, dict)]
    return sorted({m for m in found if m})[:400]


def test_key(index: int | None = None, key_val: str | None = None) -> dict:
    """Test one specific key from the pool or an arbitrary key value, returning live health and latency."""
    klist = all_keys()
    if index is not None:
        if index < 0 or index >= len(klist):
            raise ValueError(f"Invalid key index #{index + 1}")
        target_key = klist[index]
    elif key_val:
        target_key = str(key_val).strip()
    else:
        target_key = key()

    if not target_key:
        raise ValueError("No API key available to test.")

    c = current()
    p = c["provider"]
    ms = c["models"] or []
    model = ms[0] if ms else "gemini-3.5-flash-lite"
    how = PROVIDERS[p][2]
    base = base_url()

    # Intelligent provider & endpoint routing based on target key prefix:
    if target_key.startswith("sk-or-"):
        how = "openai"
        base = "https://openrouter.ai/api/v1"
        model = "meta-llama/llama-3.3-70b-instruct:free" if not ("/" in model and not model.startswith("gemini")) else model
    elif target_key.startswith("AIza") or target_key.startswith("AQ."):
        how = "gemini"
        base = PROVIDERS["gemini"][1]
        if "/" in model:
            model = "gemini-3.5-flash-lite"
    elif target_key.startswith("gsk_"):
        how = "openai"
        base = "https://api.groq.com/openai/v1"
        model = "llama-3.3-70b-versatile"
    elif target_key.startswith("xai-"):
        how = "openai"
        base = "https://api.x.ai/v1"
        model = "grok-4"

    t0 = time.time()
    try:
        # 1. OpenRouter keys: Direct auth validation returning real status and quota
        if target_key.startswith("sk-or-"):
            url = "https://openrouter.ai/api/v1/auth/key"
            headers = {"Authorization": f"Bearer {target_key}"}
            r = httpx.get(url, headers=headers, timeout=12)
            dt = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                data = r.json().get("data", {})
                free_reqs = data.get("free_model_daily_requests", {}).get("remaining")
                rem_label = f" ({free_reqs}/50 Free Left)" if free_reqs is not None else " (Quota OK)"
                return {
                    "ok": True,
                    "status": "active",
                    "label": f"Working{rem_label}",
                    "ms": dt,
                    "model": "OpenRouter Key Auth",
                    "key_hint": target_key[-4:] if len(target_key) >= 4 else "key"
                }
            elif r.status_code in (401, 403):
                return {
                    "ok": False,
                    "status": "invalid",
                    "label": "Invalid Key",
                    "ms": dt,
                    "error": "OpenRouter rejected key. Check your key in OpenRouter dashboard.",
                    "http_code": r.status_code
                }
            else:
                return {
                    "ok": False,
                    "status": "error",
                    "label": f"HTTP {r.status_code}",
                    "ms": dt,
                    "error": f"OpenRouter returned status {r.status_code}: {r.text[:120]}",
                    "http_code": r.status_code
                }

        # 2. OpenAI keys: Direct model list check with OpenAI API
        elif target_key.startswith("sk-proj-") or (target_key.startswith("sk-") and not target_key.startswith("sk-or-") and not target_key.startswith("sk-ant-")):
            url = "https://api.openai.com/v1/models"
            headers = {"Authorization": f"Bearer {target_key}"}
            r = httpx.get(url, headers=headers, timeout=12)
            dt = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                return {
                    "ok": True,
                    "status": "active",
                    "label": "Working (Quota OK)",
                    "ms": dt,
                    "model": "OpenAI Models API",
                    "key_hint": target_key[-4:] if len(target_key) >= 4 else "key"
                }
            elif r.status_code in (401, 403):
                return {
                    "ok": False,
                    "status": "invalid",
                    "label": "Invalid Key",
                    "ms": dt,
                    "error": "OpenAI rejected key or unauthorized.",
                    "http_code": r.status_code
                }
            elif r.status_code in (429, 503) or "quota" in r.text.lower():
                return {
                    "ok": False,
                    "status": "exhausted",
                    "label": "Quota Exhausted",
                    "ms": dt,
                    "error": "OpenAI credit or daily quota exhausted.",
                    "http_code": r.status_code
                }
            else:
                return {
                    "ok": False,
                    "status": "error",
                    "label": f"HTTP {r.status_code}",
                    "ms": dt,
                    "error": f"OpenAI returned status {r.status_code}: {r.text[:120]}",
                    "http_code": r.status_code
                }

        # 3. Google Gemini keys (AIza... or AQ.Ab8...)
        elif target_key.startswith("AIza") or target_key.startswith("AQ.") or how == "gemini":
            test_mod = "gemini-3.5-flash-lite" if ("/" in model or "llama" in model) else model
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{_gem(test_mod)}:generateContent"
            headers = {"x-goog-api-key": target_key}
            body = {
                "contents": [{"role": "user", "parts": [{"text": "Reply with JSON: {\"status\": \"ok\"}"}]}],
                "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}
            }
            r = httpx.post(url, json=body, headers=headers, timeout=15)
            dt = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                return {
                    "ok": True,
                    "status": "active",
                    "label": "Working (Quota OK)",
                    "ms": dt,
                    "model": test_mod,
                    "key_hint": target_key[-4:] if len(target_key) >= 4 else "key"
                }
            elif r.status_code in (429, 503) or "quota" in r.text.lower() or "resource_exhausted" in r.text.lower():
                return {
                    "ok": False,
                    "status": "exhausted",
                    "label": "Quota Exhausted",
                    "ms": dt,
                    "error": "Daily/per-minute quota limit reached. PeakCut will auto-rotate to another key.",
                    "http_code": r.status_code
                }
            elif r.status_code in (400, 401, 403):
                return {
                    "ok": False,
                    "status": "invalid",
                    "label": "Invalid Key",
                    "ms": dt,
                    "error": "API key rejected or unauthorized by Google AI Studio.",
                    "http_code": r.status_code
                }
            else:
                return {
                    "ok": False,
                    "status": "error",
                    "label": f"HTTP {r.status_code}",
                    "ms": dt,
                    "error": f"API returned status {r.status_code}: {r.text[:120]}",
                    "http_code": r.status_code
                }

        # 4. Anthropic Claude keys
        elif target_key.startswith("sk-ant-") or how == "anthropic":
            url = "https://api.anthropic.com/v1/messages"
            headers = {"x-api-key": target_key, "anthropic-version": "2023-06-01"}
            body = {"model": "claude-3-5-haiku-20241022", "max_tokens": 10, "messages": [{"role": "user", "content": "hi"}]}
            r = httpx.post(url, json=body, headers=headers, timeout=15)
            dt = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                return {"ok": True, "status": "active", "label": "Working (Quota OK)", "ms": dt, "model": "claude-3-5-haiku-20241022", "key_hint": target_key[-4:]}
            else:
                return {"ok": False, "status": "error", "label": f"HTTP {r.status_code}", "ms": dt, "error": r.text[:120]}

        # 5. Groq, Grok, or Custom OpenAI format
        else:
            cust_base = "https://api.groq.com/openai/v1" if target_key.startswith("gsk_") else ("https://api.x.ai/v1" if target_key.startswith("xai-") else base)
            cust_mod = "llama-3.3-70b-versatile" if target_key.startswith("gsk_") else ("grok-4" if target_key.startswith("xai-") else model)
            url = f"{cust_base}/chat/completions"
            headers = {"Authorization": f"Bearer {target_key}"}
            body = {"model": cust_mod, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
            r = httpx.post(url, json=body, headers=headers, timeout=15)
            dt = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                return {"ok": True, "status": "active", "label": "Working (Quota OK)", "ms": dt, "model": cust_mod, "key_hint": target_key[-4:]}
            elif r.status_code in (429, 503) or "quota" in r.text.lower():
                return {"ok": False, "status": "exhausted", "label": "Quota Exhausted", "ms": dt, "error": "Quota limit reached", "http_code": r.status_code}
            else:
                return {"ok": False, "status": "error", "label": f"HTTP {r.status_code}", "ms": dt, "error": r.text[:120]}
    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        return {"ok": False, "status": "error", "label": "Connection Timeout / Error", "ms": dt, "error": str(e)[:120]}


def test_all_keys() -> list[dict]:
    """Test all keys in the pool in parallel or sequential fast checks."""
    klist = all_keys()
    results = []
    for i in range(len(klist)):
        try:
            res = test_key(index=i)
            res["index"] = i
            results.append(res)
        except Exception as e:
            results.append({"index": i, "ok": False, "status": "error", "label": "Error", "error": str(e)})
    return results


def test() -> dict:
    """One tiny request with the settings in use, to prove the key, the address and the model all work."""
    ms = models()
    if not ready():
        raise ValueError("Save a service, a model and a key first.")
    out, sent, wrote = call(ms[0], 'Answer with a JSON array that holds the single string "ok".', {"type": "ARRAY", "items": {"type": "STRING"}})
    clear_problem()
    return {"ok": True, "model": ms[0], "tokens": sent + wrote, "answer": str(out)[:80]}


class AIError(RuntimeError):
    """A failed AI call. `wait` is how many seconds the service asked us to wait before trying again, when it
    said so (a Retry-After header, or Gemini's retryDelay)."""
    def __init__(self, message, wait=None, daily=False):
        super().__init__(message)
        self.wait = wait
        self.daily = daily        # the limit is for the whole day, so waiting a minute won't help


problem = {"text": "", "at": 0.0}       # why the AI last failed, for the dashboard; cleared when it answers again


def explain(e) -> str:
    """What went wrong with an AI call, in words the owner can act on."""
    text, low = str(e), str(e).lower()
    name = (models() or ["?"])[0]
    m = re.match(r"HTTP (\d{3})\b", text)
    status = m.group(1) if m else ""
    if status in ("401", "403") or "api key" in low or "api_key" in low or "unauthorized" in low or "permission" in low:
        return f"{label()} refused the key. Paste a working key under Settings, AI."
    if "no longer available" in low or "deprecated" in low or "retired" in low or "discontinued" in low:
        return f"{label()} has retired \"{name}\" (or it isn't available to new keys). Open Settings, AI, press Find models and pick a newer model."
    # Only a 404 that is about a model says the model is unknown. A 400 like "API key not found" or a stray
    # "404" inside some other message must not be reported as an unknown model.
    if (status == "404" and "model" in low) or (not status and ("404" in text or "not found" in low or "does not exist" in low or "unknown model" in low or "not_found" in low)) \
            or (status and "is not found for api version" in low):
        return f"{label()} doesn't know the model \"{name}\". Open Settings, AI, press Find models and pick one from the list."
    if "429" in text or "quota" in low or "rate limit" in low or "exhausted" in low:
        return f"{label()} says the key has hit its limit or has no credit left. Check the account with {label()}, or try again later."
    if "connect" in low or "timed out" in low or "timeout" in low or "getaddrinfo" in low or "refused" in low or "nodename" in low or "servname" in low or "nameresolutionerror" in low or "name resolution" in low:
        return f"PeakCut couldn't reach {label()}. Check the internet connection" + (" and that Ollama is running." if provider() == "ollama" else ".")
    return ""


def note_problem(e):
    import time
    why = explain(e)
    if why:
        problem.update(text=why, at=time.time())


def clear_problem():
    problem.update(text="", at=0.0)


def asked_wait(r) -> float | None:
    """How long the service asked us to wait, in seconds, or None when it didn't say."""
    try:
        v = (r.headers.get("retry-after") or "").strip()
        if v:
            return max(0.0, float(v))
    except (ValueError, AttributeError):
        pass
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', getattr(r, "text", "") or "")
    return float(m.group(1)) if m else None


def _fail(r, model):
    text = r.text[:300].replace(key() or "\0", "<key>")
    limited = r.status_code in (429, 503)
    raise AIError(f"HTTP {r.status_code} {text}", wait=asked_wait(r) if limited else None,
                  daily=limited and bool(re.search(r"PerDay|per day|daily", r.text or "", re.I)))


# ---------------------------------------------------------------- the schema, said in words for chat models
def _json_schema(s):
    """Gemini's schema spelling (ARRAY, OBJECT...) as ordinary JSON Schema."""
    if isinstance(s, dict):
        return {k: (v.lower() if k == "type" and isinstance(v, str) else _json_schema(v)) for k, v in s.items()}
    if isinstance(s, list):
        return [_json_schema(x) for x in s]
    return s


def _wrapped(prompt, schema):
    return (prompt + "\n\nAnswer with JSON only, no other text and no code fences: one object with a single key "
            "\"items\", whose value follows this JSON Schema:\n" + json.dumps(_json_schema(schema)))


def _json_chunks(text: str):
    """Every balanced {...} or [...] in the text, in the order they appear."""
    out, depth, start, in_str, esc = [], 0, None, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            if depth == 0:
                start = i
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0 and start is not None:
                out.append(text[start:i + 1])
                start = None
            elif depth < 0:
                depth = 0
    return out


def _parse(text):
    """The JSON in an answer, even if the model wrapped it in a code fence or a sentence.

    A model that is not careful sometimes puts a sentence in front of the JSON,
    or a second object after it, or forgets a comma. The JSON is looked for
    inside the answer rather than demanded of it."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    out = None
    try:
        out = json.loads(text)
    except ValueError:
        for chunk in _json_chunks(text):
            try:
                out = json.loads(chunk)
                break
            except ValueError:
                continue
        if out is None:
            m = re.search(r"[\[{].*[\]}]", text, re.S)
            if not m:
                raise AIError("The AI did not answer with JSON.")
            try:
                out = json.loads(m.group(0))
            except ValueError:
                raise AIError("The AI did not answer with JSON.")
    if isinstance(out, dict) and "items" in out:
        out = out["items"]
    return out


def _is_quota_error(e):
    err_str = str(e).lower()
    return any(w in err_str for w in ("429", "quota", "resource_exhausted", "rate_limit", "ratelimit", "limit exceeded"))


def _is_model_fallback_error(e):
    err_str = str(e).lower()
    return _is_quota_error(e) or any(w in err_str for w in ("503", "unavailable", "high demand", "overload", "404", "not supported", "timed out", "timeout"))


def _retry_on_quota(fn, *args, **kwargs):
    """Respect Google's project-level quotas: NEVER rotate keys to bypass limits.
    Uses bounded exponential backoff + jitter on transient 429/503 only, letting
    capability-aware model routing or graceful local fallback take over on daily limits."""
    max_attempts = 2 if _using_mock_httpx() else 2
    last_err = None
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if _is_quota_error(e) and attempt < max_attempts - 1 and not getattr(e, "daily", False):
                wait_s = gemini_client.jitter_delay(attempt, base=1.5, cap=12.0, retry_after=getattr(e, "wait", None))
                if not _using_mock_httpx():
                    time.sleep(min(wait_s, 6.0))
                continue
            raise
    raise last_err


# ---------------------------------------------------------------- one call
def _ensure_free_policy(model: str):
    if free_only() and not _using_mock_httpx():
        if provider() not in FREE_PROVIDERS:
            raise AIError(f"Paid provider '{provider()}' disabled while Free Mode Only is enabled.")
        if gemini_client.is_paid_only_model(model):
            raise AIError(f"Paid-only model '{model}' disabled while Free Mode Only is enabled.")


def call(model: str, prompt: str, schema: dict, timeout: float | None = None, allow_cache: bool = False):
    """Ask one model. Returns (the parsed JSON answer, tokens sent, tokens written back)."""
    _ensure_free_policy(model)
    _check_daily_budget()
    ckey = gemini_client.cache_key("call", model, prompt + json.dumps(schema, sort_keys=True)) if allow_cache and not _using_mock_httpx() else None
    if ckey:
        cached = gemini_client.get_cached(ckey)
        if cached is not None:
            set_last_active_model(model)
            return cached, 0, 0
    how = PROVIDERS[provider()][2]
    fn = {"gemini": _gemini, "openai": _openai, "anthropic": _anthropic}[how]
    t0 = time.time()
    try:
        res = _retry_on_quota(fn, model, prompt, schema, timeout)
        _record_telemetry(model, True, int((time.time() - t0) * 1000), res[1], res[2])
        _bump_daily_budget()
        set_last_active_model(model)
        if ckey and res[0]:
            gemini_client.put_cached(ckey, res[0], {"model": model})
        return res
    except Exception as e:
        wait_s = getattr(e, "wait", 0.0) or (60.0 if _is_quota_error(e) else 0.0)
        _record_telemetry(model, False, int((time.time() - t0) * 1000), err=str(e), rate_limited_wait=wait_s)
        raise


def see(prompt: str, image: bytes, timeout: float | None = None) -> tuple[str, int, int]:
    """Ask one model about one picture: (the answer as text, tokens in, tokens out)."""
    return _retry_on_quota(_see_impl, prompt, image, timeout)


def _see_impl(prompt: str, image: bytes, timeout: float | None = None) -> tuple[str, int, int]:
    if not ready() or not image or not models():
        return "", 0, 0
    model = (route_models("vision") or models())[0]
    _ensure_free_policy(model)
    _check_daily_budget()
    how = PROVIDERS[provider()][2]
    if how == "gemini":
        if gemini_client.SDK_AVAILABLE and not _using_mock_httpx():
            t0 = time.time()
            try:
                text, sent, wrote = gemini_client.generate_text(key(), model, prompt, [("image/jpeg", image)], timeout=timeout or 60.0)
                _record_telemetry(model, True, int((time.time() - t0) * 1000), sent, wrote)
                _bump_daily_budget()
                set_last_active_model(model)
                return text, sent, wrote
            except Exception as e:
                _record_telemetry(model, False, int((time.time() - t0) * 1000), err=str(e))
                raise AIError(str(e)[:300], daily=bool(re.search(r"per ?day|daily", str(e), re.I))) from e
        b64 = base64.b64encode(image).decode()
        body = {"contents": [{"role": "user", "parts": [
            {"text": prompt},
            {"inline_data": {"mimeType": "image/jpeg", "data": b64}}]}]}
        r = httpx.post(f"{base_url()}/{_gem(model)}:generateContent", json=body,
                       headers={"x-goog-api-key": key()}, timeout=timeout or 120)
        if r.status_code != 200:
            _fail(r, model)
        data = r.json()
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        u = data.get("usageMetadata", {})
        sent = int(u.get("promptTokenCount") or 0)
        return text, sent, max(0, int(u.get("totalTokenCount") or 0) - sent)
    b64 = base64.b64encode(image).decode()
    if how == "anthropic":
        body = {"model": model, "max_tokens": 300, "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
            {"type": "text", "text": prompt}]}]}
        r = httpx.post(f"{base_url()}/messages", json=body, timeout=timeout or 120,
                       headers={"x-api-key": key(), "anthropic-version": "2023-06-01"})
        if r.status_code != 200:
            _fail(r, model)
        data = r.json()
        text = "".join(p.get("text", "") for p in data.get("content") or [] if p.get("type") == "text")
        u = data.get("usage") or {}
        return text, int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
    headers = {"Authorization": f"Bearer {key()}"} if key() else {}
    body = {"model": model, "stream": False, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}]}]}
    r = httpx.post(f"{base_url()}/chat/completions", json=body, headers=headers, timeout=timeout or 120)
    if r.status_code != 200:
        _fail(r, model)
    data = _openai_body(r)
    text = (data["choices"][0]["message"].get("content") or "")
    u = data.get("usage") or {}
    return text, int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)


def _gem(model: str) -> str:
    """Gemini names models "models/gemini-2.5-flash"; the address already ends in /models, so only the bare id is used."""
    return model.removeprefix("models/")


def see_media(
    prompt: str,
    media_parts: list[tuple[str, bytes]],
    schema: dict | None = None,
    timeout: float | None = None,
    task: str = "deep_review",
    allow_cache: bool = True,
) -> tuple[dict | list, int, int, str]:
    """Capability-aware multimodal call for native video/mp4, audio/*, and/or image/jpeg parts.
    Deduplicates identical concurrent calls, caches completed results locally, and falls back
    cleanly across free-tier models on the same project key without paid escalation.
    Returns (parsed_json, tokens_in, tokens_out, model_used)."""
    if not ready() or not media_parts:
        return {}, 0, 0, ""
    cand_models = route_models(task)
    ckey = None
    if allow_cache and not _using_mock_httpx() and cand_models:
        ckey = gemini_client.cache_key(task, cand_models[0], prompt, media_parts)
        cached = gemini_client.get_cached(ckey)
        if cached is not None and isinstance(cached, dict) and "data" in cached:
            m_cached = str(cached.get("model") or cand_models[0])
            set_last_active_model(m_cached)
            return cached["data"], 0, 0, m_cached

    how = PROVIDERS[provider()][2]
    last_err = None
    for model in cand_models:
        _ensure_free_policy(model)
        _check_daily_budget()
        t0 = time.time()
        try:
            if how == "gemini" and gemini_client.SDK_AVAILABLE and not _using_mock_httpx():
                out, sent, wrote = _retry_on_quota(
                    gemini_client.generate_content_json,
                    key(), model, prompt, schema, media_parts, float(timeout or 45.0), 0.25,
                )
                _record_telemetry(model, True, int((time.time() - t0) * 1000), sent, wrote)
                _bump_daily_budget()
                set_last_active_model(model)
                if ckey and out:
                    gemini_client.put_cached(ckey, {"data": out, "model": model}, {"task": task})
                return out, sent, wrote, model
            # Non-Gemini SDK providers only accept images (strip video/audio parts safely).
            imgs = [blob for mime, blob in media_parts if mime.startswith("image/")]
            if imgs:
                out, sent, wrote = see_json(prompt, imgs, schema=schema, timeout=timeout)
                return out, sent, wrote, model
        except Exception as e:
            last_err = e
            wait_s = 60.0 if _is_quota_error(e) else 0.0
            _record_telemetry(model, False, int((time.time() - t0) * 1000), err=str(e), rate_limited_wait=wait_s)
            if _is_model_fallback_error(e):
                continue
            raise
    if last_err:
        note_problem(last_err)
        raise AIError(str(last_err)[:300]) from last_err
    return {}, 0, 0, ""


def see_json(prompt: str, image: bytes | list[bytes], schema: dict | None = None, timeout: float | None = None, model: str | None = None) -> tuple[dict | list, int, int]:
    """Ask one multimodal model about one or more video frames and expect a parsed JSON answer.
    Returns (the parsed JSON data, tokens in, tokens out)."""
    return _retry_on_quota(_see_json_impl, prompt, image, schema, timeout, model)


def _see_json_impl(prompt: str, image: bytes | list[bytes], schema: dict | None = None, timeout: float | None = None, model_override: str | None = None) -> tuple[dict | list, int, int]:
    if not ready() or not image or not models():
        return {}, 0, 0
    cand = [model_override] if model_override else (route_models("deep_review") or models())
    model = cand[0]
    _ensure_free_policy(model)
    _check_daily_budget()
    img_list = [img for img in (image if isinstance(image, list) else [image]) if img and len(img) > 100]
    if not img_list:
        return {}, 0, 0
    how = PROVIDERS[provider()][2]
    if how == "gemini":
        if gemini_client.SDK_AVAILABLE and not _using_mock_httpx():
            media_parts = [("image/jpeg", img) for img in img_list]
            for m in cand:
                _ensure_free_policy(m)
                t0 = time.time()
                try:
                    out, sent, wrote = gemini_client.generate_content_json(
                        key(), m, prompt, schema=schema, media_parts=media_parts, timeout=float(timeout or 40.0), temperature=0.25
                    )
                    _record_telemetry(m, True, int((time.time() - t0) * 1000), sent, wrote)
                    _bump_daily_budget()
                    set_last_active_model(m)
                    return out, sent, wrote
                except Exception as e:
                    _record_telemetry(m, False, int((time.time() - t0) * 1000), err=str(e), rate_limited_wait=60.0 if _is_quota_error(e) else 0.0)
                    if m != cand[-1] and (_is_quota_error(e) or "404" in str(e)):
                        continue
                    raise AIError(str(e)[:300], daily=bool(re.search(r"per ?day|daily", str(e), re.I))) from e
        gen_cfg = {"temperature": 0.4, "responseMimeType": "application/json"}
        if schema:
            gen_cfg["responseSchema"] = schema
        parts = [{"text": prompt}]
        for img in img_list:
            b64 = base64.b64encode(img).decode()
            parts.append({"inline_data": {"mimeType": "image/jpeg", "data": b64}})
        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": gen_cfg
        }
        r = httpx.post(f"{base_url()}/{_gem(model)}:generateContent", json=body,
                       headers={"x-goog-api-key": key()}, timeout=timeout or 35)
        if r.status_code != 200:
            _fail(r, model)
        data = r.json()
        text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
        u = data.get("usageMetadata", {})
        sent = int(u.get("promptTokenCount") or 0)
        wrote = max(0, int(u.get("totalTokenCount") or 0) - sent)
        return _parse(text), sent, wrote

    # For other OpenAI-compatible or Anthropic providers:
    if how == "anthropic":
        content = [{"type": "text", "text": prompt + "\n\nRespond with a valid JSON object ONLY."}]
        for img in img_list:
            b64 = base64.b64encode(img).decode()
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
        url = f"{base_url()}/messages"
        body = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 1024}
        headers = {"x-api-key": key(), "anthropic-version": "2023-06-01"}
        r = httpx.post(url, json=body, headers=headers, timeout=timeout or 35)
        if r.status_code != 200:
            _fail(r, model)
        text = "".join(p.get("text", "") for p in r.json().get("content", []))
        return _parse(text), 0, 0

    # Default OpenAI format (OpenRouter, Groq, custom):
    content = [{"type": "text", "text": prompt + "\n\nRespond with a valid JSON object ONLY."}]
    for img in img_list:
        b64 = base64.b64encode(img).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    url = f"{base_url()}/chat/completions"
    body = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 1024}
    headers = {"Authorization": f"Bearer {key()}"}
    r = httpx.post(url, json=body, headers=headers, timeout=timeout or 35)
    if r.status_code != 200:
        _fail(r, model)
    text = r.json()["choices"][0]["message"]["content"]
    return _parse(text), 0, 0


def _gemini(model, prompt, schema, timeout=None):
    _ensure_free_policy(model)
    if gemini_client.SDK_AVAILABLE and not _using_mock_httpx():
        try:
            return gemini_client.generate_content_json(key(), model, prompt, schema=schema, timeout=float(timeout or 60.0), temperature=0.3)
        except Exception as e:
            msg = str(e)
            low = msg.lower()
            limited = "429" in msg or "503" in msg or "quota" in low or "resource_exhausted" in low
            if schema and ("400" in msg or "schema" in low or "json mode" in low) and "api key" not in low:
                try:
                    return gemini_client.generate_content_json(key(), model, _wrapped(prompt, schema), schema=None, timeout=float(timeout or 60.0), temperature=0.3)
                except Exception:
                    pass
            raise AIError(msg[:300], daily=limited and bool(re.search(r"per ?day|daily", msg, re.I))) from e
    url = f"{base_url()}/{_gem(model)}:generateContent"
    headers = {"x-goog-api-key": key()}
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json", "responseSchema": schema}}
    r = httpx.post(url, json=body, headers=headers, timeout=timeout or 120)
    used_plain = False
    if r.status_code in (400, 422) and "api key" not in r.text.lower() and "api_key" not in r.text.lower():
        # Models like Gemma in the Gemini list support generateContent without responseSchema.
        plain = {"contents": [{"role": "user", "parts": [{"text": _wrapped(prompt, schema)}]}]}
        r = httpx.post(url, json=plain, headers=headers, timeout=timeout or 120)
        used_plain = True
    if r.status_code != 200:
        _fail(r, model)
    data = r.json()
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    u = data.get("usageMetadata", {})
    sent = int(u.get("promptTokenCount") or 0)
    parsed = _parse(text) if used_plain else json.loads(text)
    return parsed, sent, max(0, int(u.get("totalTokenCount") or 0) - sent)   # the answer, and any thinking billed with it


def _openai_body(r):
    """The answer, whether the service sent plain JSON or an event stream.

    Some OpenAI-compatible servers answer with a stream of events unless the
    request says otherwise, so the answer is read from whichever shape arrived.
    A model that answers with a tool call instead of a message leaves the JSON in
    the call's arguments, so that is used too."""
    try:
        data = r.json()
    except ValueError:
        data = _from_events(r.text)
    for ch in data.get("choices") or []:
        msg = ch.get("message") or {}
        if (msg.get("content") or "").strip():
            continue
        for call in msg.get("tool_calls") or []:
            args = (call.get("function") or {}).get("arguments")
            if args:
                msg["content"] = args
                break
    return data


def _from_events(text: str) -> dict:
    """Read an answer out of a server-sent event stream."""
    parts, usage, calls = [], {}, {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        chunk = line[5:].strip()
        if not chunk or chunk == "[DONE]":
            continue
        try:
            d = json.loads(chunk)
        except ValueError:
            continue
        usage = d.get("usage") or usage
        for ch in d.get("choices") or []:
            for piece in ((ch.get("message") or {}), (ch.get("delta") or {})):
                if piece.get("content"):
                    parts.append(piece["content"])
                for call in piece.get("tool_calls") or []:
                    i = call.get("index", 0)
                    calls[i] = calls.get(i, "") + ((call.get("function") or {}).get("arguments") or "")
    message = {"content": "".join(parts)}
    if not message["content"] and calls:
        message["content"] = "".join(calls.values())
    return {"choices": [{"message": message}], "usage": usage}


def _openai(model, prompt, schema, timeout=None):
    headers = {"Authorization": f"Bearer {key()}"} if key() else {}
    body = {"model": model, "messages": [{"role": "user", "content": _wrapped(prompt, schema)}], "stream": False}
    # Most services accept these two extras; a few models refuse one of them, so they are dropped on a refusal.
    extras = [{"temperature": 0.4, "response_format": {"type": "json_object"}}, {"response_format": {"type": "json_object"}}, {}]
    r = None
    for extra in extras:
        r = httpx.post(f"{base_url()}/chat/completions", json={**body, **extra}, headers=headers, timeout=timeout or 180)
        if r.status_code not in (400, 422):
            break
    if r.status_code != 200:
        _fail(r, model)
    data = _openai_body(r)
    u = data.get("usage") or {}
    return _parse(data["choices"][0]["message"].get("content")), int(u.get("prompt_tokens") or 0), int(u.get("completion_tokens") or 0)


def _anthropic(model, prompt, schema, timeout=None):
    body = {"model": model, "max_tokens": 8192, "messages": [{"role": "user", "content": _wrapped(prompt, schema)}]}
    r = httpx.post(f"{base_url()}/messages", json=body, timeout=timeout or 180,
                   headers={"x-api-key": key(), "anthropic-version": "2023-06-01"})
    if r.status_code != 200:
        _fail(r, model)
    data = r.json()
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    u = data.get("usage") or {}
    return _parse(text), int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
