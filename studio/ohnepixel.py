"""OhnePixel Intelligent Livestream Detection & Keyword Database.

Supports:
- English, German, and community slang.
- Tiered phrase prioritization (Level 1: High Priority Reaction, Level 2: Community/Game-specific, Level 3: Common words).
- False positive protection (common words like "bro", "no", "wait", "what" NEVER trigger alone).
- Laughter, voice emotion and non-verbal reaction markers.
- Game and category adaptation (CS2, GTA 6, Fortnite, Just Chatting, Story Games).
- Keyword-only fallback scoring (Mode B) and AI multimodal signal integration (Mode A).
"""

from __future__ import annotations

import re
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# PHASE 2: OHNEPIXEL KEYWORD AND REACTION DATABASE
# ---------------------------------------------------------------------------

# LEVEL 1: High-Priority Strong Reaction Phrases (Strong clip candidate indicators)
STRONG_REACTION_PHRASES: tuple[str, ...] = (
    "what the fuck",
    "what the fuck is that",
    "what is happening",
    "what just happened",
    "what did i just see",
    "no fucking way",
    "no way",
    "no shot",
    "no fucking shot",
    "are you serious",
    "holy shit",
    "holy fuck",
    "oh my god",
    "oh my fucking god",
    "bro what",
    "what the hell",
    "what the actual fuck",
    "huh",
    "wait wait wait",
    "hold on",
    "you're kidding",
    "you are kidding",
    "this is not real",
    "this is insane",
    "that's crazy",
    "thats crazy",
    "that's disgusting",
    "thats disgusting",
    "i'm done",
    "im done",
    "i'm actually done",
    "im actually done",
    "i can't believe it",
    "i cant believe it",
    "unbelievable",
    "what a joke",
    "why bro",
    "come on bro",
    "no no no",
    "please no",
    "let's fucking go",
    "lets fucking go",
    "let's go",
    "lets go",
    "we got it",
    "we hit it",
    "that's huge",
    "thats huge",
    "did you see that",
    "look at this",
    "look at that",
    "i'm speechless",
    "im speechless",
    "that's a crime",
    "thats a crime",
    "you've got to be kidding me",
    "you got to be kidding me",
    # German strong reactions
    "was ist das",
    "was ist passiert",
    "das gibt es nicht",
    "das gibt's nicht",
    "ach du scheisse",
    "ach du heimat",
    "leckt mich",
    "alter was",
    "oh mein gott",
    "nicht dein ernst",
    "bist du dumm",
)

# LEVEL 2: OhnePixel Community Expressions & Slang (Creator-specific contextual signals)
# These MUST NOT automatically create clips alone; they require reaction or event context.
COMMUNITY_EXPRESSIONS: tuple[str, ...] = (
    "ma drilla",
    "my drilla",
    "drillas",
    "drilla",
    "rejuicer",
    "ohneschnitzel",
    "bazalright",
    "naur",
    "vas",
    "vas?!",
    "huss",
    "tsak",
    "nein",
    "auuug",
    "auuuug",
    "fish dish",
    "gold gold gold",
    "come on g",
    "boys and girls",
    "i'm not gonna lie",
    "im not gonna lie",
    "not gonna lie",
    "we're so back",
    "were so back",
    "what are we doing",
    "listen to me",
    "hearts in the chat",
    "thank you daddy",
    "one more case",
    "last case",
    "juicer",
    "habibi",
    "schatz",
)

# CS2 and Skin-Related Keywords (Game-specific clues, not automatic clip commands)
CS2_SKIN_KEYWORDS: tuple[str, ...] = (
    "blue gem",
    "red gem",
    "gold",
    "gold unbox",
    "knife",
    "karambit",
    "butterfly knife",
    "dragon lore",
    "doppler",
    "fade",
    "case hardened",
    "661",
    "titan holo",
    "nip paper",
    "rare pattern",
    "perfect pattern",
    "1 of 1",
    "one of one",
    "rare skin",
    "insane float",
    "low float",
    "high tier skin",
    "case opening",
    "trade up",
    "overpay",
    "expensive inventory",
    "what is this worth",
    "is that a blue gem",
    "we got a gold",
    "stat trak",
    "factory new",
    "minimal wear",
    "souvenir",
    "howl",
    "m9 bayonet",
)

# GTA 6 and Action Game Keywords
GTA6_KEYWORDS: tuple[str, ...] = (
    "npc",
    "npc moment",
    "cop chase",
    "police",
    "wanted level",
    "car crash",
    "physics",
    "ragdoll",
    "heist",
    "mission failed",
    "wasted",
    "busted",
    "rockstar",
    "vice city",
    "jason",
    "lucia",
    "glitch",
    "flying car",
    "clutch getaway",
)

# LEVEL 3: Common Words (False-positive protection: NEVER clip solely on these!)
COMMON_WORDS: tuple[str, ...] = (
    "bro",
    "bruh",
    "no",
    "okay",
    "ok",
    "wait",
    "what",
    "gold",
    "knife",
    "wow",
    "yeah",
    "man",
    "dude",
    "yo",
    "guys",
    "yes",
    "nice",
    "good",
    "bad",
    "oh",
    "ah",
)

# Textual laughter representations in transcripts
LAUGHTER_PATTERNS: tuple[str, ...] = (
    "hahaha",
    "hahahaha",
    "hehehe",
    "ahahah",
    "[laughter]",
    "[laughs]",
    "*laughs*",
    "*laughing*",
    "crying laughing",
    "im wheezing",
    "i'm wheezing",
    "wheezing",
    "cant breathe",
    "can't breathe",
)

# Category adaptation profiles
CATEGORY_PROFILES: dict[str, dict[str, Any]] = {
    "cs2": {
        "name": "Counter-Strike 2",
        "keywords": CS2_SKIN_KEYWORDS,
        "clutch_terms": ("clutch", "1v3", "1v4", "1v5", "ace", "defuse", "headshot", "ninja defuse"),
        "visual_hints": ("case opening", "unboxed", "rare skin banner", "kill feed", "round victory"),
        "min_pre_roll": 15,
        "min_post_roll": 25,
    },
    "gta 6": {
        "name": "Grand Theft Auto VI",
        "keywords": GTA6_KEYWORDS,
        "clutch_terms": ("escape", "chase", "mission pass", "crazy physics", "stunt"),
        "visual_hints": ("police sirens", "car crash", "npc interaction", "cutscene", "wanted stars"),
        "min_pre_roll": 18,
        "min_post_roll": 22,
    },
    "just chatting": {
        "name": "Just Chatting",
        "keywords": COMMUNITY_EXPRESSIONS,
        "clutch_terms": ("storytime", "debate", "reaction", "drama", "unhinged take"),
        "visual_hints": ("streamer face full screen", "discord call", "reddit reaction", "video watch"),
        "min_pre_roll": 20,
        "min_post_roll": 30,
    },
    "story games": {
        "name": "Story & Single Player Games",
        "keywords": ("cutscene", "plot twist", "boss fight", "ending", "jumpscare", "died"),
        "clutch_terms": ("boss defeated", "scary", "emotional", "climax"),
        "visual_hints": ("cinematic cutscene", "boss health bar", "game over screen"),
        "min_pre_roll": 20,
        "min_post_roll": 25,
    },
}


# ---------------------------------------------------------------------------
# NORMALIZATION & MATCHING HELPERS
# ---------------------------------------------------------------------------

_APOSTROPHES = re.compile(r"[’‘´`]")
_PUNCTUATION = re.compile(r"[^\w\s']")
_WHITESPACE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize text for consistent phonetic, dialect and typo matching."""
    if not text:
        return ""
    t = text.lower().strip()
    t = _APOSTROPHES.sub("'", t)
    # German Umlaut normalization for transcripts
    t = t.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    # Phonetic community speech variants
    t = re.sub(r"\bnaur+\b", "naur", t)
    t = re.sub(r"\bwa+t+\b", "what", t)
    t = re.sub(r"\bbroo+\b", "bro", t)
    t = re.sub(r"\bmaa+\s+drilla\b", "ma drilla", t)
    t = re.sub(r"\bmy\s+drilla\b", "ma drilla", t)
    t = _PUNCTUATION.sub(" ", t)
    return _WHITESPACE.sub(" ", t).strip()


def extract_matched_phrases(text: str, phrase_list: Iterable[str]) -> list[str]:
    """Find which phrases from phrase_list appear in normalized text."""
    norm = normalize_text(text)
    if not norm:
        return []
    matches = []
    # Word boundary search for precision
    for phrase in phrase_list:
        p_norm = normalize_text(phrase)
        if not p_norm:
            continue
        pattern = r"\b" + re.escape(p_norm) + r"\b"
        if re.search(pattern, norm):
            matches.append(phrase)
    return matches


# ---------------------------------------------------------------------------
# CLASSIFICATION & SCORING
# ---------------------------------------------------------------------------

def classify_transcript(
    words_or_text: list[dict] | str,
    game: str | None = None,
) -> dict[str, Any]:
    """
    Classifies transcript text for OhnePixel livestream clipping.

    Returns:
    - score: Keyword relevance score (0 - 100)
    - tier: 1 (High Priority), 2 (Community/Game), 3 (Common words), or None
    - matches: list of all matched phrases
    - level1_matches: list of Level 1 phrases matched
    - level2_matches: list of Level 2 expressions matched
    - level3_matches: list of Level 3 common words matched
    - laughter_detected: bool
    - requires_evidence: bool (True if Level 2/3 and needs visual/audio evidence to clip)
    - skip_reason: str or None (if should be skipped)
    """
    if isinstance(words_or_text, list):
        full_text = " ".join(w.get("w", "") for w in words_or_text if isinstance(w, dict))
    else:
        full_text = str(words_or_text or "")

    norm = normalize_text(full_text)
    tokens = norm.split()
    total_words = len(tokens)

    if total_words == 0:
        return {
            "score": 0,
            "tier": None,
            "matches": [],
            "level1_matches": [],
            "level2_matches": [],
            "level3_matches": [],
            "laughter_detected": False,
            "requires_evidence": True,
            "skip_reason": "Empty transcript",
            "eligible": False,
        }

    # 1. Match Level 1 Phrases (Strong Reactions)
    level1 = extract_matched_phrases(norm, STRONG_REACTION_PHRASES)

    # 2. Match Level 2 Expressions (Community & Game-Specific)
    level2 = extract_matched_phrases(norm, COMMUNITY_EXPRESSIONS)
    game_key = (game or "").lower().strip()
    if "cs" in game_key:
        level2.extend(extract_matched_phrases(norm, CS2_SKIN_KEYWORDS))
    elif "gta" in game_key:
        level2.extend(extract_matched_phrases(norm, GTA6_KEYWORDS))

    # Deduplicate matches
    level2 = list(dict.fromkeys(level2))

    # 3. Match Level 3 Common Words
    level3 = [w for w in COMMON_WORDS if re.search(r"\b" + re.escape(w) + r"\b", norm)]

    # 4. Check Laughter Patterns in Text
    laughter = any(pat in norm for pat in LAUGHTER_PATTERNS) or bool(re.search(r"\b(ha){3,}\b", norm))

    # Check for repeated phrases like "GOLD GOLD GOLD" or "WAIT WAIT WAIT" or "NO NO NO"
    has_repetition = bool(
        re.search(r"\b(gold\s+){2,}gold\b", norm)
        or re.search(r"\b(wait\s+){2,}wait\b", norm)
        or re.search(r"\b(no\s+){2,}no\b", norm)
        or re.search(r"\b(why\s+){2,}why\b", norm)
        or re.search(r"\b(what\s+){2,}what\b", norm)
    )

    # Check for single common word isolation:
    # If transcript ONLY contains common words without reaction or repetition, strictly skip!
    is_only_common = False
    if not level1 and not level2 and not laughter and not has_repetition:
        meaningful_words = [t for t in tokens if t not in COMMON_WORDS and len(t) > 2]
        if len(meaningful_words) <= 1:
            is_only_common = True

    # Compute Keyword Relevance Score (Signal 1: 0 - 100)
    kw_score = 0
    tier = None

    if level1:
        tier = 1
        # Base for Level 1 is 80-95
        kw_score = 85 + min(15, len(level1) * 5)
    elif level2 or has_repetition or laughter:
        tier = 2
        # Base for Level 2 / community is 60-75
        kw_score = 65 + (10 if has_repetition else 0) + (10 if laughter else 0) + min(10, len(level2) * 5)
    elif level3 and not is_only_common:
        tier = 3
        # Common words with other conversational tokens: 30-45
        kw_score = 35 + min(15, len(tokens))
    else:
        # Mundane / normal speech
        kw_score = max(5, min(25, total_words * 2))

    kw_score = min(100, max(0, kw_score))

    # Determine eligibility and evidence requirements
    # Example E: Casual "BRO" -> SKIP
    if is_only_common:
        return {
            "score": min(kw_score, 20),
            "tier": 3,
            "matches": level3,
            "level1_matches": [],
            "level2_matches": [],
            "level3_matches": level3,
            "laughter_detected": False,
            "requires_evidence": True,
            "skip_reason": "Casual common word without event or excitement",
            "eligible": False,
        }

    # Level 1 phrases are strong candidates, but Phase 3 requires visual/reaction validation
    # Level 2 expressions MUST NOT automatically create clips without event/reaction context.
    requires_evidence = tier in (2, 3)

    return {
        "score": kw_score,
        "tier": tier,
        "matches": level1 + level2 + (level3 if not level1 and not level2 else []),
        "level1_matches": level1,
        "level2_matches": level2,
        "level3_matches": level3,
        "laughter_detected": laughter,
        "has_repetition": has_repetition,
        "requires_evidence": requires_evidence,
        "skip_reason": None,
        "eligible": True,
    }


# ---------------------------------------------------------------------------
# PHASE 4: KEYWORD-ONLY FALLBACK (MODE B)
# ---------------------------------------------------------------------------

def evaluate_keyword_fallback(
    words_or_text: list[dict] | str,
    audio_zscore: float = 0.0,
    chat_velocity: float = 0.0,
    game: str | None = None,
) -> dict[str, Any]:
    """
    Evaluates moments when multimodal AI is unavailable (Mode B).
    Uses tiered phrase prioritization with false-positive protection.

    Rules:
    - Level 1: Strong reaction phrases create candidates (score >= 75)
    - Level 2: Community/Game expressions create candidates ONLY if audio_zscore > 1.2 or chat_velocity > 1.5 or repetition
    - Level 3: Common words alone are NEVER clipped (score < 50)
    """
    cls = classify_transcript(words_or_text, game=game)
    if not cls["eligible"]:
        return {
            "mode": "MODE B (KEYWORD FALLBACK)",
            "clipped": False,
            "score": cls["score"],
            "tier": cls["tier"],
            "priority": "SKIP",
            "reason": cls["skip_reason"] or "Mundane moment",
            "matches": cls["matches"],
        }

    tier = cls["tier"]
    score = cls["score"]
    reason = ""

    if tier == 1:
        # Strong Level 1 phrase
        score = max(score, 80)
        if audio_zscore > 1.0 or chat_velocity > 1.5:
            score = min(100, score + 10)
        reason = f"High-priority reaction phrase matched: {', '.join(cls['level1_matches'][:2])}"
    elif tier == 2:
        # Community expressions require audio boost or repetition
        has_signal = audio_zscore >= 1.2 or chat_velocity >= 1.5 or cls.get("has_repetition") or cls.get("laughter_detected")
        if not has_signal:
            return {
                "mode": "MODE B (KEYWORD FALLBACK)",
                "clipped": False,
                "score": min(score, 55),
                "tier": tier,
                "priority": "SKIP",
                "reason": "Community expression without reaction spike or chat excitement",
                "matches": cls["matches"],
            }
        score = max(70, min(90, score + int(audio_zscore * 8)))
        reason = f"Community phrase with reaction spike: {', '.join(cls['level2_matches'][:2])}"
    else:
        # Tier 3 common words without AI cannot be safely clipped
        return {
            "mode": "MODE B (KEYWORD FALLBACK)",
            "clipped": False,
            "score": min(score, 45),
            "tier": tier,
            "priority": "SKIP",
            "reason": "Common words require AI multimodal verification",
            "matches": cls["matches"],
        }

    priority = "HIGH PRIORITY" if score >= 75 else ("REVIEW QUEUE" if score >= 60 else "SKIP")
    return {
        "mode": "MODE B (KEYWORD FALLBACK)",
        "clipped": score >= 60,
        "score": score,
        "tier": tier,
        "priority": priority,
        "reason": reason,
        "matches": cls["matches"],
    }
