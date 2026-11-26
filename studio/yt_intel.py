"""YouTube Intelligence & Growth Toolkit for PeakCut / ClipNova AI.

Pure-Python (zero external dependency) adaptations inspired by youtube-agent-skill (MIT):
1. 21 Hook Formulas + Shorts/Standard Hook Scorer (`score_hook`, `rank_hooks`, `HOOK_FORMULAS`)
2. Title + Hook/Thumbnail Pairing Linter (`lint_title_pairing`)
3. Audience Retention CSV Leak Analyzer (`analyze_retention_csv`)
4. Transcript Dead-Air, Filler & Retake EDL Detector (`analyze_transcript_edl`)
5. Validated YouTube Chapters Generator (`generate_chapters`, `build_compilation_chapters`)
6. Channel-Median Viral Outlier Classifier (`find_channel_outliers`)
"""
from __future__ import annotations

import csv
import io
import json
import re
import statistics
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# 1. 21 PROVEN HOOK FORMULAS + GAMING/SHORTS REACTION PATTERNS
# ---------------------------------------------------------------------------

HOOK_FORMULAS: list[dict[str, Any]] = [
    {
        "id": "the-statistic",
        "name": "The Statistic",
        "shape": "A number the viewer did not know, stated flat, then the consequence.",
        "match": [r"\b\d+(?:\.\d+)?\s?%", r"\b\d+\s+(?:out of|in)\s+\d+\b", r"\b\d{2,}(?:,\d{3})+\b"],
    },
    {
        "id": "someone-elses-result",
        "name": "Someone Else's Result",
        "shape": "A named person's outcome, then the mechanism.",
        "match": [r"\bthis\s+(?:channel|guy|creator|streamer|account|player)\b", r"\bwent from\b.*\bto\b", r"\bin\s+(?:a|one|two|three|\d+)\s+(?:second|minute|week|month|year)s?\b"],
    },
    {
        "id": "the-mistake",
        "name": "The Mistake",
        "shape": "Name the error the viewer or player is making right now.",
        "match": [r"\byou(?:'re| are)\s+(?:probably\s+|still\s+)?(?:doing|making)\b", r"\bthe\s+(?:mistake|reason)\s+(?:everyone|most people|nobody)\b", r"\bworst\s+\w+\b"],
    },
    {
        "id": "contrarian-flip",
        "name": "Contrarian Flip",
        "shape": "State the accepted expectation, then flip it.",
        "match": [r"\beveryone\s+(?:says|thinks|tells you)\b", r"\bis\s+(?:actually\s+)?wrong\b", r"\bnobody\s+(?:tells|talks about|expected)\b"],
    },
    {
        "id": "the-reveal",
        "name": "The Reveal",
        "shape": "Promise a specific thing will be shown, then show it.",
        "match": [r"\bi(?:'m| am)\s+going\s+to\s+show\s+you\b", r"\bhere(?:'s| is)\s+(?:the|exactly|what)\b", r"\bon\s+screen\b"],
    },
    {
        "id": "the-superlative",
        "name": "The Superlative",
        "shape": "The single best/worst/fastest/craziest in a category.",
        "match": [r"\bthe\s+(?:best|worst|fastest|easiest|only|funniest|craziest|most)\b", r"\bnumber\s+one\b"],
    },
    {
        "id": "the-clock",
        "name": "The Clock",
        "shape": "Bound the payoff in seconds or minutes.",
        "match": [r"\bin\s+(?:the\s+next\s+)?\d+\s+(?:seconds|secs|minutes|mins|hours)\b", r"\bby\s+the\s+end\b", r"\bunder\s+\d+\b"],
    },
    {
        "id": "i-tried-it",
        "name": "I Tried It",
        "shape": "First-person experiment or challenge with a real stake.",
        "match": [r"\bi\s+(?:tried|spent|tested|let|gave|survived)\b", r"\bfor\s+\d+\s+(?:days|weeks|months|hours)\b", r"\bso\s+you\s+don'?t\s+have\s+to\b"],
    },
    {
        "id": "the-question",
        "name": "The Question",
        "shape": "Open an irresistible curiosity loop with a question.",
        "match": [r"^(?:why|how|what|when|should|can|did|would|could|is|are|do(?!\s+not\b)|does)\b.*\?", r"\?\s*[^\w\s]*$"],
    },
    {
        "id": "the-before-after",
        "name": "Before and After",
        "shape": "Two states, one cut between them.",
        "match": [r"\bbefore\b.*\bafter\b", r"\bthis\s+was\b.*\bthis\s+is\b", r"\bused\s+to\b"],
    },
    {
        "id": "the-teardown",
        "name": "The Teardown",
        "shape": "Break down how something happened or worked.",
        "match": [r"\b(?:broke|break|breaking)\s+(?:it\s+)?down\b", r"\bteardown\b", r"\banalys(?:ed|is|e)\b", r"\bi\s+pulled\b"],
    },
    {
        "id": "the-stack",
        "name": "The Stack",
        "shape": "Two elements colliding into one wild outcome.",
        "match": [r"\b\w+\s+(?:plus|\+|vs)\s+\w+\b", r"\bcombine\b", r"\btogether\b"],
    },
    {
        "id": "the-warning",
        "name": "The Warning",
        "shape": "A cost or disaster the subject/viewer is about to hit.",
        "match": [r"\bdo\s+not\b", r"\bdon'?t\s+(?:upload|post|publish|start|trust|look|blink|do)\b", r"\bbefore\s+you\b", r"\bstop\b"],
    },
    {
        "id": "the-list",
        "name": "The List",
        "shape": "A counted set with the number up front.",
        "match": [r"^\d+\s+\w+", r"\b(?:here\s+are|these\s+are|top)\s+\d+\b"],
    },
    {
        "id": "the-receipt",
        "name": "The Receipt",
        "shape": "Show the proof/moment first, explain second.",
        "match": [r"\bthis\s+is\s+(?:the|my|what)\b", r"\bscreenshot\b", r"\bproof\b", r"\bcaught\b"],
    },
    {
        "id": "the-insider",
        "name": "The Insider",
        "shape": "Hidden detail or system behavior nobody noticed.",
        "match": [r"\b(?:nobody|almost\s+nobody|most\s+people)\s+(?:knows?|opens?|uses?|noticed?)\b", r"\bhidden\b", r"\bsecret\b"],
    },
    {
        "id": "the-impossible",
        "name": "The Impossible Claim",
        "shape": "State an unbelievable feat or disaster.",
        "match": [r"\bwithout\b", r"\bnever\b", r"\bin\s+one\b", r"\bzero\b", r"\bno\s+way\b", r"\bimpossible\b"],
    },
    {
        "id": "the-comparison",
        "name": "The Comparison",
        "shape": "Two options or sides, one clear winner.",
        "match": [r"\bvs\.?\b", r"\bversus\b", r"\bwhich\s+(?:one\s+)?(?:is|wins)\b", r"\bsame\b.*\bways\b"],
    },
    {
        "id": "the-origin",
        "name": "The Origin",
        "shape": "Where the chaos or result actually started.",
        "match": [r"\bevery\s+(?:video|post|clip)\b.*\bstarts\b", r"\bit\s+all\s+(?:starts|started)\b", r"\bthe\s+(?:real\s+)?reason\b"],
    },
    {
        "id": "the-deadline",
        "name": "The Deadline",
        "shape": "Something changing right now or immediately.",
        "match": [r"\b(?:this|next)\s+(?:week|month|year)\b", r"\bis\s+changing\b", r"\bno\s+longer\b", r"\buntil\b"],
    },
    {
        "id": "the-direct-address",
        "name": "The Direct Address",
        "shape": "Name the exact viewer or player in the first six words.",
        "match": [r"^if\s+you\b", r"\bfor\s+(?:anyone|everyone|people|gamers)\s+who\b", r"\byou\s+specifically\b", r"\brate\s+the\b"],
    },
]

_FILLER_WORDS = {
    "basically", "actually", "literally", "just", "really", "very", "so", "kind", "sort", "like",
    "guys", "hey", "welcome", "today", "video", "subscribe", "channel", "moment", "clip",
}
_VAGUE_WORDS = {
    "amazing", "incredible", "insane", "crazy", "huge", "massive", "game", "changer", "secret",
    "powerful", "ultimate", "best", "revolutionary", "mind", "blowing", "unbelievable", "epic",
    "perfect", "complete", "everything",
}
_GENERIC_BANNERS = ("wait till the end", "wait for it", "watch till the end", "bro was not ready")

_CONCRETE_RE = re.compile(r"\b(\d[\d,.]*\s?(%|k|m|x|s|h)?|\$\d|\d+\s?(second|minute|hour|day|week|month|year)s?)\b", re.I)
_YOU_RE = re.compile(r"\b(you|your|you're|youre|yourself|chat|bro)\b", re.I)
_STAKE_RE = re.compile(
    r"\b(lose|lost|wasting|waste|quit|fail|broke|cost|risk|before|stop|never|die|dying|dead|"
    r"stole|robbed|ruined|regrets?|destroyed|crashed|busted|wasted|survived?|trapped|exploded)\b",
    re.I,
)
_CURIOSITY_RE = re.compile(r"\b(why|how|what|which|until|before|but|nobody|almost|except|reason|actually|wait|way)\b", re.I)
_TITLE_STOP = {
    "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "is", "are", "with", "your",
    "you", "my", "i", "this", "that", "it", "how", "what", "why", "did", "shorts", "gta",
}


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9'%$.]+", (text or "").lower())


def classify_hook_formula(text: str) -> tuple[str, int]:
    """Classify a hook or title against the 21 YouTube hook formulas."""
    clean = re.sub(r"[*#]", " ", text or "").strip()
    best_name, best_hits = "Unclassified", 0
    for f in HOOK_FORMULAS:
        hits = sum(1 for pat in f["match"] if re.search(pat, clean, re.I))
        if hits > best_hits:
            best_name, best_hits = f["name"], hits
    return best_name, best_hits


def score_hook(text: str, mode: str = "shorts") -> dict[str, Any]:
    """Score a YouTube hook/banner on 5 properties (0-100 each) + weakest-link verdict.

    mode='shorts': calibrated for 2-10 word visual hook banners & Shorts openers.
    mode='standard': calibrated for 9-24 word spoken talking-head hooks.
    """
    raw = (text or "").strip()
    clean = re.sub(r"\*", "", raw).strip()
    # Strip trailing emojis cleanly for word counting
    ascii_ish = re.sub(r"[^\w\s'%$.?!,-]", "", clean).strip()
    toks = _words(ascii_ish)
    n_words = len(toks)
    if n_words == 0:
        return {
            "hook": raw,
            "verdict": 0,
            "band": "WEAK",
            "formula": "Unclassified",
            "formula_hits": 0,
            "properties": {"SPECIFICITY": 0, "ADDRESS": 0, "STAKES": 0, "CURIOSITY": 0, "BREVITY": 0},
            "weakest": "SPECIFICITY",
            "fix": "Describe the specific action, person, or outcome in 3-8 punchy words.",
        }

    nums = len(_CONCRETE_RE.findall(ascii_ish))
    vague_n = sum(1 for w in toks if w in _VAGUE_WORDS)
    filler_n = sum(1 for w in toks if w in _FILLER_WORDS)
    proper_n = sum(1 for w in ascii_ish.split()[1:] if w[:1].isupper() and len(w) > 1)
    is_generic_cliche = any(g in ascii_ish.lower() for g in _GENERIC_BANNERS)

    # 1. SPECIFICITY
    spec = 38 + nums * 20 + min(24, proper_n * 8) - vague_n * (6 if mode == "shorts" else 14) - filler_n * 6
    if is_generic_cliche:
        spec -= 28
    spec = max(5, min(100, spec))

    # 2. ADDRESS (direct hook to viewer/subject)
    you_n = len(_YOU_RE.findall(ascii_ish))
    first6 = " ".join(ascii_ish.split()[:6])
    addr_base = 46 if mode == "shorts" else 26
    addr = addr_base + you_n * 18 + (24 if _YOU_RE.search(first6) else 0) + (14 if mode == "shorts" and proper_n else 0)
    addr = max(10, min(100, addr))

    # 3. STAKES (cost, consequence, risk, disaster, victory)
    stake_n = len(_STAKE_RE.findall(ascii_ish))
    stk = 28 + stake_n * 26 + (12 if nums else 0) + (10 if "!" in clean else 0)
    stk = max(10, min(100, stk))

    # 4. CURIOSITY (open loop, question, contrast)
    cur_n = len(_CURIOSITY_RE.findall(ascii_ish))
    q_bonus = 20 if "?" in clean else 0
    closed_pen = -18 if re.search(r"\b(because|so that|which means)\b", ascii_ish, re.I) else 0
    cur = 28 + cur_n * 17 + q_bonus + closed_pen
    cur = max(10, min(100, cur))

    # 5. BREVITY
    if mode == "shorts":
        if 3 <= n_words <= 8:
            brev = 100
        elif n_words < 3:
            brev = max(45, 100 - (3 - n_words) * 20)
        elif n_words <= 14:
            brev = max(55, 100 - (n_words - 8) * 6)
        else:
            brev = max(15, 100 - (n_words - 8) * 7)
    else:
        if 9 <= n_words <= 24:
            brev = 100
        elif n_words < 9:
            brev = max(30, 100 - (9 - n_words) * 11)
        else:
            brev = max(10, 100 - (n_words - 24) * 7)

    props = {
        "SPECIFICITY": spec,
        "ADDRESS": addr,
        "STAKES": stk,
        "CURIOSITY": cur,
        "BREVITY": brev,
    }
    vals = list(props.values())
    verdict = round(0.6 * (sum(vals) / len(vals)) + 0.4 * min(vals))
    if is_generic_cliche:
        verdict = min(verdict, 48)
    band = "STRONG" if verdict >= 72 else ("WORKABLE" if verdict >= 55 else "WEAK")
    formula, hits = classify_hook_formula(clean)
    weakest = min(props, key=props.get)
    fixes = {
        "SPECIFICITY": "Swap generic words for the exact car, NPC, number, or action on screen.",
        "ADDRESS": "Name the streamer/viewer or open with 'you'/'chat' in the first 5 words.",
        "STAKES": "Show what went wrong or what is at risk (lost, crashed, robbed, 5s left).",
        "CURIOSITY": "Open a gap with 'why/how/what' or cut the part that gives away the ending.",
        "BREVITY": "Keep Shorts banners punchy at 3-8 words (or 9-24 words for spoken intros).",
    }
    return {
        "hook": raw,
        "verdict": verdict,
        "band": band,
        "formula": formula,
        "formula_hits": hits,
        "properties": props,
        "weakest": weakest,
        "fix": fixes[weakest],
    }


def rank_hooks(hooks: Iterable[str], mode: str = "shorts") -> list[dict[str, Any]]:
    """Score and rank hooks descending by verdict while removing case-insensitive duplicates."""
    seen: set[str] = set()
    scored: list[dict[str, Any]] = []
    for h in hooks:
        s = str(h or "").strip()
        if not s:
            continue
        k = re.sub(r"\*", "", s).lower()
        if k in seen:
            continue
        seen.add(k)
        scored.append(score_hook(s, mode=mode))
    scored.sort(key=lambda r: -r["verdict"])
    return scored


# ---------------------------------------------------------------------------
# 2. TITLE + THUMBNAIL/COVER LINTER
# ---------------------------------------------------------------------------

def lint_title_pairing(title: str, thumb: str | None = None, is_shorts: bool = True) -> dict[str, Any]:
    """Lint a YouTube title paired with its on-screen hook/thumbnail text.

    Checks desktop search truncation (60 chars), mobile feed cut (40 chars),
    all-caps spam (>2 caps words), vague vs concrete wording, front-loading,
    and title <-> thumbnail/hook duplication.
    """
    t = (title or "").strip()
    n = len(t)
    t_no_shorts = re.sub(r"#shorts\b", "", t, flags=re.I).strip()
    issues: list[dict[str, str]] = []
    good: list[str] = []

    if n == 0:
        return {
            "title": "",
            "chars": 0,
            "score": 0,
            "ctr_score": 0,
            "band": "WEAK",
            "mobile_preview": "",
            "desktop_truncated": False,
            "duplicate_words": [],
            "formula": "Unclassified",
            "issues": [{"code": "empty", "message": "Title is empty"}],
            "good": [],
            "reason": "Empty title",
        }

    if n > 100:
        issues.append({"code": "length", "message": f"{n} chars — exceeds YouTube's 100-char hard limit"})
    elif n > 65:
        issues.append({"code": "length", "message": f"{n} chars — desktop search cuts near 60 chars"})
    else:
        good.append(f"{n} chars (fits desktop 60-char search cut)")

    mobile_preview = t if n <= 40 else (t[:40].rsplit(" ", 1)[0] + "...")
    if n > 42:
        issues.append({"code": "mobile", "message": f'Mobile feed cuts near "{mobile_preview}" — put subject early'})
    else:
        good.append("Survives 40-char mobile cut")

    if is_shorts:
        if "#shorts" in t.lower():
            good.append("Has #Shorts tag")
        else:
            issues.append({"code": "no-shorts", "message": "Missing #Shorts tag"})

    # Ignore #SHORTS when counting screaming uppercase words
    caps = [w for w in re.sub(r"#shorts\b", "", t, flags=re.I).split() if len(w) > 2 and re.sub(r"[^A-Za-z]", "", w).isupper()]
    if len(caps) > 2:
        issues.append({"code": "shouting", "message": f"{len(caps)} ALL-CAPS words — keep max 2 so it doesn't look spammy"})
    elif caps:
        good.append(f"{len(caps)} emphasis caps word")

    toks = re.findall(r"[a-z0-9']+", t_no_shorts.lower())
    vague_hits = sorted({w for w in toks if w in _VAGUE_WORDS})
    # For Shorts gaming titles, one hype word is fine if paired with concrete subject; >1 vague without specifics hurts
    if len(vague_hits) > 1 or (vague_hits and not re.search(r"\d", t_no_shorts) and len(caps) == 0 and not "?" in t):
        issues.append({"code": "vague", "message": f"Generic hype ({', '.join(vague_hits[:3])}) — name the exact event/item"})

    nums = re.findall(r"\d[\d,.]*%?", t_no_shorts)
    if nums:
        good.append(f"Concrete number ({', '.join(nums[:2])})")

    if "?" in t_no_shorts or "!" in t_no_shorts:
        good.append("Emotional hook punctuation")

    front = [w for w in toks[:3] if w not in _TITLE_STOP]
    if not front:
        issues.append({"code": "front-load", "message": "First 3 words are filler — move the subject forward"})

    duplicate_words: list[str] = []
    if thumb and str(thumb).strip():
        thumb_clean = re.sub(r"[*#]", " ", str(thumb)).strip()
        tw = set(re.findall(r"[a-z0-9']{3,}", t_no_shorts.lower())) - _TITLE_STOP
        hw = set(re.findall(r"[a-z0-9']{3,}", thumb_clean.lower())) - _TITLE_STOP
        duplicate_words = sorted(tw & hw)
        # Flag real overlap when 2+ meaningful words overlap or >50% of thumbnail is duplicated verbatim
        if len(duplicate_words) >= 2 or (hw and len(duplicate_words) / len(hw) >= 0.6):
            issues.append({
                "code": "duplicate",
                "message": f"Title repeats cover/hook words ({', '.join(duplicate_words[:4])}) — use different angle",
            })
        elif tw and hw:
            good.append("Title & cover hook complement each other")
        thumb_words = re.findall(r"[a-z0-9']+", thumb_clean.lower())
        if len(thumb_words) > 7:
            issues.append({"code": "thumb-length", "message": f"{len(thumb_words)} words on cover hook — keep under 6 words"})

    # Compute score balanced for Shorts CTR & pairing hygiene
    score = 70 + min(24, 6 * len(good)) - 11 * len(issues)
    # Severe penalty for hard length/empty/heavy duplication
    if any(i["code"] == "duplicate" for i in issues):
        score -= 4
    score = max(25, min(98, score))
    band = "STRONG" if score >= 78 else ("WORKABLE" if score >= 60 else "WEAK")
    formula, _ = classify_hook_formula(t_no_shorts)
    reason_parts = good[:2] + [i["message"] for i in issues[:2]]

    return {
        "title": t,
        "chars": n,
        "score": score,
        "ctr_score": score,
        "band": band,
        "mobile_preview": mobile_preview,
        "desktop_truncated": n > 60,
        "duplicate_words": duplicate_words,
        "formula": formula,
        "issues": issues,
        "good": good,
        "reason": " · ".join(reason_parts) or "Clean descriptive title",
    }


# ---------------------------------------------------------------------------
# 3. TRANSCRIPT PARSING, DEAD-AIR/RETAKE EDL & VALIDATED YOUTUBE CHAPTERS
# ---------------------------------------------------------------------------

_FILLER_ONLY_RE = re.compile(
    r"^[\s,.-]*((um+|uh+|er+|ah+|so|okay|ok|right|yeah|like|anyway|basically|"
    r"actually|you know|i mean|let me see|hold on)[\s,.-]*)+$",
    re.I,
)
_CHAPTER_STOP = set(
    "the a an of for to in on and or is are was were be been with this that it as at by from "
    "you your i my we our they them he she but so if then than there here what which who how "
    "when where why not no yes do does did just really very like about into over out up down "
    "can could will would should have has had get got make made go going went one two".split()
)


def _parse_ts(s: str) -> float:
    s = s.strip().replace(",", ".")
    p = s.split(":")
    if len(p) == 3:
        return int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])
    return int(p[0]) * 60 + float(p[1])


def words_to_cues(words: list[dict[str, Any]], max_gap: float = 0.65, max_words: int = 12) -> list[tuple[float, float, str]]:
    """Group PeakCut word-level timestamps [{w, s, e}] into spoken cues."""
    cues: list[tuple[float, float, str]] = []
    buf: list[str] = []
    c_start = 0.0
    c_end = 0.0
    for item in words or []:
        wt = str(item.get("w") or item.get("word") or "").strip()
        if not wt:
            continue
        ws = float(item.get("s") or item.get("start") or 0.0)
        we = float(item.get("e") or item.get("end") or (ws + 0.25))
        if not buf:
            c_start = ws
        elif (ws - c_end) > max_gap or len(buf) >= max_words:
            cues.append((round(c_start, 3), round(c_end, 3), " ".join(buf)))
            buf = []
            c_start = ws
        buf.append(wt)
        c_end = max(we, ws + 0.05)
    if buf:
        cues.append((round(c_start, 3), round(c_end, 3), " ".join(buf)))
    return cues


def parse_transcript_cues(raw: str) -> list[tuple[float, float, str]]:
    """Parse SRT, VTT, or Whisper JSON text into [(start, end, text)]."""
    txt = (raw or "").strip()
    if not txt:
        return []
    if txt.startswith("{") or txt.startswith("["):
        try:
            d = json.loads(txt)
            segs = d.get("segments", d if isinstance(d, list) else [])
            out = []
            for s in segs:
                t = (s.get("text") or s.get("w") or "").strip()
                if t:
                    out.append((float(s.get("start", s.get("s", 0.0))), float(s.get("end", s.get("e", 0.0))), t))
            return out
        except Exception:
            pass
    cues: list[list[Any]] = []
    cur: list[Any] | None = None
    for line in txt.splitlines():
        m = re.match(r"\s*(\d[\d:.,]+)\s*-->\s*(\d[\d:.,]+)", line)
        if m:
            cur = [_parse_ts(m.group(1)), _parse_ts(m.group(2)), []]
            cues.append(cur)
        elif cur is not None and line.strip() and not line.strip().isdigit():
            cur[2].append(line.strip())
    return [(a, b, " ".join(parts)) for a, b, parts in cues if parts]


def analyze_transcript_edl(
    cues: list[tuple[float, float, str]],
    floor: float = 0.45,
    span_start: float | None = None,
    span_end: float | None = None,
) -> dict[str, Any]:
    """Detect DEAD air gaps, FILLER-only cues, and REPEAT sentence restarts."""
    filtered = list(cues or [])
    if span_start is not None or span_end is not None:
        lo = float(span_start or 0.0)
        hi = float(span_end if span_end is not None else 1e12)
        filtered = [
            (max(lo, s) - lo, min(hi, e) - lo, t)
            for s, e, t in filtered
            if e >= lo and s <= hi and t.strip()
        ]
    if not filtered:
        return {"duration": 0.0, "cues_count": 0, "cuts": [], "removed_sec": 0.0, "out_sec": 0.0}

    dur = max(e for _, e, _ in filtered)
    if span_start is not None and span_end is not None:
        dur = max(dur, float(span_end) - float(span_start))

    def _norm(t: str) -> list[str]:
        return re.sub(r"[^a-z ]", "", t.lower()).split()

    cuts: list[dict[str, Any]] = []
    for i, (s, e, t) in enumerate(filtered):
        if _FILLER_ONLY_RE.match(t):
            cuts.append({"kind": "FILLER", "start": round(s, 2), "end": round(e, 2), "dur": round(e - s, 2), "why": t.strip()[:48]})
        if i > 0:
            gap = s - filtered[i - 1][1]
            if gap > floor:
                keep = floor / 2.0
                cs = round(filtered[i - 1][1] + keep, 2)
                ce = round(s - keep, 2)
                if ce > cs:
                    cuts.append({"kind": "DEAD", "start": cs, "end": ce, "dur": round(ce - cs, 2), "why": f"{gap:.2f}s pause"})
        if t.strip() and not _FILLER_ONLY_RE.match(t):
            j = i - 1
            while j >= 0 and (_FILLER_ONLY_RE.match(filtered[j][2]) or not filtered[j][2].strip()):
                j -= 1
            if j >= 0:
                w1, w2 = _norm(filtered[j][2]), _norm(t)
                k = min(5, len(w1), len(w2))
                if (k >= 4 and w1[:k] == w2[:k]) or (len(w1) == 3 and len(w2) == 3 and w1 == w2):
                    cs, ce = round(filtered[j][0], 2), round(filtered[j][1], 2)
                    if ce > cs:
                        cuts.append({"kind": "REPEAT", "start": cs, "end": ce, "dur": round(ce - cs, 2), "why": f'restart of "{" ".join(w1[:k])}"'})

    cuts.sort(key=lambda c: c["start"])
    removed = round(sum(c["end"] - c["start"] for c in cuts), 2)
    return {
        "duration": round(dur, 2),
        "cues_count": len(filtered),
        "cuts": cuts,
        "removed_sec": removed,
        "out_sec": round(max(0.0, dur - removed), 2),
    }


def _mmss(sec: float) -> str:
    t = max(0, int(round(sec)))
    h, m, s = t // 3600, (t % 3600) // 60, t % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _topic_keywords(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z']{4,}", (text or "").lower()) if w not in _CHAPTER_STOP}


def generate_chapters(cues: list[tuple[float, float, str]], target: int = 7) -> dict[str, Any]:
    """Generate YouTube-rule-validated chapters (0:00 start, >=3 chapters, >=10s each) from cues."""
    if len(cues or []) < 6:
        return {"valid": False, "chapters": [], "text": "", "reason": "Too few spoken cues to chapter"}
    dur = cues[-1][1]
    if dur < 30.0:
        return {"valid": False, "chapters": [], "text": "", "reason": "Video under 30s cannot hold 3 valid 10s chapters"}

    cand = []
    for i in range(1, len(cues)):
        gap = cues[i][0] - cues[i - 1][1]
        before = " ".join(c[2] for c in cues[max(0, i - 12):i])
        after = " ".join(c[2] for c in cues[i:i + 12])
        kb, ka = _topic_keywords(before), _topic_keywords(after)
        shift = 1.0 - (len(kb & ka) / len(kb | ka)) if (kb | ka) else 0.0
        cand.append((gap * 1.6 + shift * 3.2, cues[i][0]))
    cand.sort(reverse=True)

    picked = [0.0]
    min_len = 10.0
    for _, t in cand:
        if len(picked) >= max(3, target):
            break
        if all(abs(t - p) >= min_len for p in picked) and (dur - t) >= min_len:
            picked.append(t)
    picked.sort()

    chapters = []
    for n, t in enumerate(picked):
        end = picked[n + 1] if n + 1 < len(picked) else dur
        seg_text = " ".join(c[2] for c in cues if c[0] >= t and c[1] <= end)
        kws = list(_topic_keywords(seg_text))
        kws.sort(key=lambda w: -seg_text.lower().count(w))
        label = " ".join(w.capitalize() for w in kws[:3]) or f"Part {n + 1}"
        chapters.append({
            "start": round(t, 2),
            "label": _mmss(t),
            "title": label,
            "seconds": round(end - t, 2),
        })

    valid = len(chapters) >= 3 and chapters[0]["start"] == 0 and all(c["seconds"] >= min_len for c in chapters)
    block = "\n".join(f"{c['label']} {c['title']}" for c in chapters)
    return {"valid": valid, "chapters": chapters, "text": block}


def build_compilation_chapters(pieces: list[dict[str, Any]]) -> dict[str, Any]:
    """Build exact validated YouTube chapters for a Best-of-Stream stitched compilation."""
    cur = 0.0
    chapters = []
    for idx, p in enumerate(pieces or [], 1):
        dur = max(1.0, float(p.get("dur") or 0.0))
        raw_title = re.sub(r"#shorts\b", "", str(p.get("title") or p.get("hook") or f"Moment {idx}"), flags=re.I)
        raw_title = re.sub(r"[*]", "", raw_title).strip(" -|!")[:55] or f"Moment {idx}"
        chapters.append({
            "start": round(cur, 2),
            "label": _mmss(cur),
            "title": raw_title,
            "seconds": round(dur, 2),
        })
        cur += dur
    valid = len(chapters) >= 3 and chapters[0]["start"] == 0 and all(c["seconds"] >= 10.0 for c in chapters)
    text = "\n".join(f"{c['label']} {c['title']}" for c in chapters)
    return {"valid": valid, "chapters": chapters, "text": text}


# ---------------------------------------------------------------------------
# 4. AUDIENCE RETENTION CSV ANALYZER
# ---------------------------------------------------------------------------

def analyze_retention_csv(
    csv_text: str,
    cues: list[tuple[float, float, str]] | None = None,
    duration_sec: float | None = None,
) -> dict[str, Any]:
    """Parse YouTube Studio Audience Retention CSV and surface Hook Leak, Cliffs, and Slide."""
    rows: list[tuple[float, float]] = []
    reader = csv.reader(io.StringIO(csv_text or ""))
    for r in reader:
        vals: list[float] = []
        for col in r:
            cleaned = col.strip().replace("%", "").replace(",", "")
            try:
                vals.append(float(cleaned))
            except ValueError:
                continue
        if len(vals) >= 2:
            rows.append((vals[0], vals[1]))

    if len(rows) < 6:
        raise ValueError("Need at least 6 numeric (position, retention%) rows from YouTube Studio retention CSV.")

    xs = [r[0] for r in rows]
    ys = [r[1] for r in rows]
    pct_axis = max(xs) <= 100.5
    dur = float(duration_sec) if (duration_sec and duration_sec > 0) else None
    if not dur and cues:
        dur = max((e for _, e, _ in cues), default=0.0) or None

    def _to_sec(x: float) -> float | None:
        if not pct_axis:
            return x
        return (x / 100.0) * dur if dur else None

    start_val = ys[0] if ys[0] > 0 else 100.0
    cutoff = 30.0 if not pct_axis else ((min(30.0, dur * 0.25) / dur * 100.0) if dur else 10.0)
    hook_end = min((y for x, y in rows if x <= cutoff), default=start_val)
    hook_leak = round(max(0.0, start_val - hook_end), 2)
    hook_verdict = "healthy" if hook_leak < 25 else ("leaking" if hook_leak < 40 else "severe")

    drops = []
    for i in range(1, len(rows)):
        loss = ys[i - 1] - ys[i]
        span = (xs[i] - xs[i - 1]) or 1.0
        drops.append((loss / span, xs[i - 1], xs[i], loss))
    drops.sort(key=lambda d: -d[0])

    cliffs = []
    for _, a1, b1, loss in drops[:5]:
        if loss <= 0.8:
            continue
        at_sec = _to_sec(a1)
        said = ""
        if cues and at_sec is not None:
            near = [q[2] for q in cues if q[0] <= at_sec + 4.0 and q[1] >= at_sec - 4.0]
            said = " ".join(near)[:160]
        cliffs.append({
            "from": round(a1, 2),
            "to": round(b1, 2),
            "lost_pct": round(loss, 2),
            "at_seconds": round(at_sec, 1) if at_sec is not None else None,
            "at_label": _mmss(at_sec) if at_sec is not None else f"{a1:.1f}%",
            "said": said,
        })

    mid = [d[3] for d in drops if d[1] > cutoff]
    slide = round(sum(mid) / len(mid), 3) if mid else 0.0

    recommendations = []
    if hook_leak >= 25:
        recommendations.append(f"Opening leaked {hook_leak}% — tighten the first 2-3s visual/verbal hook before anything else.")
    if cliffs:
        top_c = cliffs[0]
        where = top_c["at_label"]
        recommendations.append(
            f"Steepest viewer drop (-{top_c['lost_pct']}%) at {where}"
            + (f' while saying "{top_c["said"][:70]}"' if top_c["said"] else "")
            + " — trim or punch up pacing there."
        )
    if slide > 0.8 and not cliffs:
        recommendations.append("Steady middle bleed without sharp cliffs — tighten cuts and remove dead air across the middle.")
    if not recommendations:
        recommendations.append("Healthy retention curve! Keep this hook length and pacing format.")

    return {
        "points": len(rows),
        "start_pct": round(start_val, 1),
        "end_pct": round(ys[-1], 1),
        "hook_leak_pct": hook_leak,
        "hook_verdict": hook_verdict,
        "cliffs": cliffs,
        "slide_per_unit": slide,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# 5. CHANNEL-MEDIAN VIRAL OUTLIER FINDER
# ---------------------------------------------------------------------------

def find_channel_outliers(rows: list[dict[str, Any]], min_multiple: float = 2.0, min_videos_per_channel: int = 4) -> dict[str, Any]:
    """Rank videos by multiple over their OWN channel's median views (not raw subscriber size)."""
    by_channel: dict[str, list[dict[str, Any]]] = {}
    for row in rows or []:
        ch = str(row.get("channel") or "unknown").strip()
        by_channel.setdefault(ch, []).append(row)

    outliers = []
    skipped_thin = []
    for ch, items in by_channel.items():
        if len(items) < min_videos_per_channel:
            skipped_thin.append({"channel": ch, "count": len(items)})
            continue
        med = statistics.median(float(it.get("views") or 0) for it in items)
        if med <= 0:
            continue
        for it in items:
            views = int(it.get("views") or 0)
            mult = views / med
            if mult >= min_multiple:
                title = str(it.get("title") or "")
                formula, _ = classify_hook_formula(title)
                outliers.append({
                    "channel": ch,
                    "title": title,
                    "views": views,
                    "channel_median": int(med),
                    "multiple": round(mult, 2),
                    "formula": formula,
                    "url": str(it.get("url") or ""),
                })

    outliers.sort(key=lambda r: -r["multiple"])
    formula_counts: dict[str, int] = {}
    for o in outliers:
        formula_counts[o["formula"]] = formula_counts.get(o["formula"], 0) + 1

    return {
        "total_videos": len(rows or []),
        "channels_analyzed": len(by_channel),
        "outliers": outliers[:30],
        "skipped_thin_channels": skipped_thin,
        "formula_breakdown": dict(sorted(formula_counts.items(), key=lambda kv: -kv[1])),
    }
