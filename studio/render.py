"""Turns a time range into a vertical clip: 9:16 layout, bouncy word captions, hook title, cover."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config, roman
from .media import NO_WINDOW, run

W, H = config.OUT_W, config.OUT_H

# ASS colours are &HBBGGRR. `size` is the ASS font size (line height); _Font turns it into real pixels.
STYLES = {
    "bounce": {"label": "Bounce", "font": "Poppins ExtraBold", "size": 132, "base": "FFFFFF", "active": "00F0FF",
               "strong": "FFFFFF", "outline": 7, "pop": 112, "upper": True, "per": 3, "anim": "bounce"},
    "hormozi": {"label": "Hormozi (Cyan Pop)", "font": "Poppins ExtraBold", "size": 134, "base": "FFFFFF", "active": "00FFFF",
                "strong": "00FFFF", "outline": 8, "pop": 122, "upper": True, "per": 2, "anim": "bounce"},
    "mrbeast": {"label": "MrBeast (Yellow/Orange)", "font": "Anton", "size": 144, "base": "FFFF00", "active": "FF6600",
                "strong": "FF6600", "outline": 8, "pop": 124, "upper": True, "per": 2, "anim": "bounce"},
    "karaoke": {"label": "Karaoke (Color Wipe)", "font": "Poppins ExtraBold", "size": 128, "base": "FFFFFF", "active": "00FF66",
                "strong": "00FF66", "outline": 7, "pop": 100, "upper": True, "per": 3, "anim": "karaoke"},
    "hype": {"label": "Hype", "font": "Anton", "size": 152, "base": "FFFFFF", "active": "3C3CFF",
             "strong": "00D7FF", "outline": 7, "pop": 114, "upper": True, "per": 2, "anim": "bounce"},
    "clean": {"label": "Clean", "font": "Poppins ExtraBold", "size": 100, "base": "FFFFFF", "active": "6BD7FF",
              "strong": "FFFFFF", "outline": 5, "pop": 106, "upper": False, "per": 4, "anim": "bounce"},
}
HOOK_STYLES = {
    "viral_yellow": {
        "label": "Viral Floating (Yellow Punch)", "font": "Archivo Black", "size": 94, "ink": "FFFFFF",
        "highlight": "00E5FF", "no_box": True, "outline": 7, "shadow": 4, "max_w": 960,
    },
    "viral_cyan": {
        "label": "Viral Floating (Cyan Punch)", "font": "Archivo Black", "size": 94, "ink": "FFFFFF",
        "highlight": "00F0FF", "no_box": True, "outline": 7, "shadow": 4, "max_w": 960,
    },
    "neon": {
        "label": "Neon Dark", "font": "Anton", "size": 108, "ink": "FFFFFF", "box": "141210",
        "border": "00F0FF", "pad_x": 42, "pad_y": 24, "radius": 28, "max_w": 920,
    },
    "yellow": {
        "label": "Viral Yellow", "font": "Anton", "size": 108, "ink": "0A0A0A", "box": "00E5FF",
        "border": "0A0A0A", "pad_x": 42, "pad_y": 24, "radius": 28, "max_w": 920,
    },
    "pill": {
        "label": "3D White Pill", "font": "Poppins ExtraBold", "size": 94, "ink": "12100E", "box": "FFFFFF",
        "border": "1C1A18", "pad_x": 42, "pad_y": 24, "radius": 32, "max_w": 920,
    },
    "purple_whip": {
        "label": "Purple Whip (Glow)", "font": "Anton", "size": 108, "ink": "FFFFFF", "box": "2A0845",
        "border": "FF007F", "pad_x": 42, "pad_y": 24, "radius": 28, "max_w": 920,
    },
    "cyber_red": {
        "label": "Cyber Red", "font": "Anton", "size": 108, "ink": "FFFFFF", "box": "180A0A",
        "border": "FF003C", "pad_x": 42, "pad_y": 24, "radius": 28, "max_w": 920,
    },
    "gold_luxury": {
        "label": "Gold Luxury", "font": "Anton", "size": 108, "ink": "FFDF00", "box": "0D0D0D",
        "border": "FFDF00", "pad_x": 42, "pad_y": 24, "radius": 28, "max_w": 920,
    },
}
HOOK = HOOK_STYLES["neon"]
FONT_FILES = {"Poppins ExtraBold": "Poppins-ExtraBold.ttf", "Anton": "Anton-Regular.ttf", "Archivo Black": "ArchivoBlack-Regular.ttf"}
CAP_MAX_W = 960   # captions never run wider than this, whatever is said


class _Font:
    """Measures text exactly as the renderer will draw it, so every word can be placed by hand: the highlighted
    word can grow without pushing its neighbours, and the heading box fits its text."""
    _cache: dict = {}

    def __init__(self, name):
        import struct
        path = Path(__file__).resolve().parent / "fonts" / FONT_FILES.get(name, FONT_FILES["Poppins ExtraBold"])
        d = path.read_bytes()
        tables = {}
        for i in range(struct.unpack(">H", d[4:6])[0]):
            tag, _, off, _ = struct.unpack(">4sIII", d[12 + 16 * i: 28 + 16 * i])
            tables[tag] = off
        self.upm = struct.unpack(">H", d[tables[b"head"] + 18: tables[b"head"] + 20])[0]
        o = tables[b"OS/2"]
        self.asc, self.desc = struct.unpack(">HH", d[o + 74: o + 78])      # what the renderer sizes the font by
        self.cap = struct.unpack(">h", d[o + 88: o + 90])[0] or int(self.upm * 0.7)
        self.path = str(path)
        self._pil = {}

    @classmethod
    def get(cls, name):
        if name not in cls._cache:
            cls._cache[name] = cls(name)
        return cls._cache[name]

    def em(self, size):
        return size * self.upm / (self.asc + self.desc)

    def width(self, text, size):
        """Pixels wide at this ASS size."""
        try:
            from PIL import ImageFont
            if "f" not in self._pil:
                self._pil["f"] = ImageFont.truetype(self.path, 200)
            return self._pil["f"].getlength(text) * self.em(size) / 200
        except Exception:  # noqa: BLE001 - no measuring library: a fair estimate keeps clips rendering
            return len(text) * self.em(size) * 0.62

    def cap_shift(self, size):
        """How far below the anchor the middle of a capital letter sits when text is centred on a point."""
        return ((self.asc - self.desc) / 2 - self.cap / 2) * size / (self.asc + self.desc)


CAPTION_LEAD = 0.00  # Exact acoustic onset: subtitles pop at exact acoustic word onset without premature drift
def install_fonts():
    """Copy the bundled caption fonts next to the data, so captions look the same on every machine and server."""
    src = Path(__file__).resolve().parent / "fonts"
    for f in src.glob("*.ttf"):
        if not (config.FONTS_DIR / f.name).exists():
            shutil.copyfile(f, config.FONTS_DIR / f.name)


LAYOUTS = {
    "split_half": "Classic Split 50/50 (Top Cam, Bottom Game) ⭐",
    "split": "Reaction Split (Floating Cam Top, Full Game Backdrop)",
    "custom": "Custom Visual Layout & Facecam Studio 🎨",
    "gameplay": "Gameplay Focus (Corner PIP Facecam)",
    "crop": "Fullscreen Gameplay (No Cam)",
    "left": "Fill the screen, keep the left side",
    "right": "Fill the screen, keep the right side",
    "fit": "Full frame on black",
    "blur": "Original 16:9 + Blurred Background",
    "zoom": "Zoomed 16:9 + Blurred Background"
}
_FILLS = ("crop", "left", "right", "gameplay", "custom")


def _ts(t):
    t = max(0.0, t)
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def _clean(text):
    return re.sub(r"[\x00-\x1f\x7f]+", " ", re.sub(r"[{}\\]", "", str(text))).strip()


def _key(word):
    return re.sub(r"[^a-z0-9']", "", word.lower())


def _groups(words, per):
    out, cur = [], []
    for w in words:
        if cur and (len(cur) >= per or sum(len(x["w"]) for x in cur) + len(w["w"]) > 16
                    or w["s"] - cur[-1]["e"] > 0.45 or cur[-1]["w"][-1:] in ".?!"):
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def geometry(src_w, src_h, layout):
    """Where the video sits in the 1080x1920 frame, and where hook and captions go."""
    if layout == "split":
        return layout, H, 570, 1450
    if layout in ("split_half", "custom"):
        return layout, H, 220, 1360
    if src_h >= src_w and layout != "crop":
        layout = "crop"  # already vertical or square: nothing to gain from a blurred fill
    if layout not in LAYOUTS:
        layout = "blur"
    if layout in ("blur", "fit"):
        fg_h = min(H, int(round(W * src_h / src_w / 2)) * 2)
    elif layout == "zoom":
        fg_h = 1000
    else:
        fg_h = H
    top = (H - fg_h) // 2
    if layout in _FILLS:
        return layout, fg_h, 300, 1380
    if layout == "split":
        return layout, fg_h, 230, H // 2        # captions sit on the line between the two people
    return layout, fg_h, max(230, top - 190), min(1640, top + fg_h + 180)


_STREAMER_NAMES = {
    "ohnepixel", "ohnpixel", "ishowspeed", "speed", "kai", "kaicenat", "xqc",
    "adin", "adinross", "pokimane", "jynxzi", "tarik", "tenz", "streamer",
    "twitch", "kick", "youtube", "gta", "gta6", "cs2", "csgo"
}

_HOOK_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "this", "that", "these", "those",
    "in", "on", "at", "to", "for", "of", "and", "or", "it", "its", "with", "as",
    "by", "from", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "ready", "gets", "goes", "went", "got", "just", "very", "so", "too", "my",
    "your", "his", "her", "their", "our", "all", "some", "any", "not", "no", "yes",
    "he", "she", "they", "we", "i", "me", "him", "them", "us", "bro", "man", "guy",
    "dude", "what", "why", "how", "when", "where", "who", "there", "here"
}

_HIGH_PUNCH_WORDS = {
    "insane", "crazy", "arrested", "roasts", "roast", "clutch", "banned", "glitch",
    "heist", "heists", "unbelievable", "caught", "secret", "exposed", "richest",
    "poorest", "cheater", "rage", "crying", "dies", "wins", "loses", "mystery",
    "hacked", "rare", "knife", "gold", "dragon", "1of1", "screams", "massive",
    "epic", "shocking", "godly", "legendary", "unreal", "disaster", "billionaire",
    "millionaire", "cursed", "illegal", "impossible", "wild", "worst", "best",
    "biggest", "smug", "genius", "nightmare", "flawless", "cute", "influencers",
    "fails", "failed", "unboxed", "unboxing", "pulled", "clutched", "chokes",
    "choked", "betrayed", "escaped", "cooked", "scammed", "scam"
}


def _wrap_punch_word(token: str) -> str:
    m = re.match(r"^([^\w]*)([\w\-\'\?!]+)(.*)$", token)
    if m:
        prefix, core, suffix = m.groups()
        return f"{prefix}*{core}*{suffix}"
    return f"*{token}*"


def _select_single_punch_word(hook: str, highlight_words: set | None = None) -> str:
    """Selects exactly ONE punch word in the entire hook text to highlight in yellow/accent.
    Ensures streamer names and stopwords are never picked over dramatic action/punch words."""
    if "*" in hook:
        return hook
    tokens = hook.split()
    if not tokens:
        return hook

    def score_token(idx: int, t: str) -> float:
        clean = re.sub(r"[^\w]", "", t).lower()
        if not clean:
            return -999.0
        if clean in _STREAMER_NAMES:
            return -100.0 + len(clean) * 0.1
        if clean in _HOOK_STOPWORDS:
            return -50.0 + len(clean) * 0.1
        score = float(len(clean))
        if clean in _HIGH_PUNCH_WORDS:
            score += 35.0
        if highlight_words and clean in highlight_words:
            score += 25.0
        score += idx * 0.5
        return score

    best_idx = max(range(len(tokens)), key=lambda i: score_token(i, tokens[i]))
    tokens[best_idx] = _wrap_punch_word(tokens[best_idx])
    return " ".join(tokens)


def _format_hook_line_no_box(line: str, ink: str, highlight_col: str, highlight_words: set | None = None) -> str:
    """Formats a hook line with inline ASS color overrides for viral punch words.
    Only words enclosed in asterisks (*word*) are highlighted in highlight_col.
    Lines without asterisks remain cleanly styled in the base ink color."""
    if "*" in line:
        parts = re.split(r"(\*[^*]+\*)", line)
        out = []
        for p in parts:
            if p.startswith("*") and p.endswith("*") and len(p) > 2:
                out.append(f"{{\\c&H{highlight_col}&}}{p[1:-1]}{{\\c&H{ink}&}}")
            else:
                out.append(p)
        return "".join(out)
    return line


def _hook_events(hook, dur, y, style_name="bounce", hook_style=None, max_w=None, font_size=None, x=None, highlight=None, teaser_dur=0.0):
    """The heading: high-CTR modern badge with 3D drop shadow, sleek border, and punchy pop-in entrance."""
    cfg = HOOK_STYLES.get(hook_style or "")
    if not cfg:
        if style_name == "hype":
            cfg = HOOK_STYLES["yellow"]
        elif style_name == "clean":
            cfg = HOOK_STYLES["pill"]
        elif style_name == "mrbeast":
            cfg = HOOK_STYLES["yellow"]
        elif style_name == "purple_whip":
            cfg = HOOK_STYLES["purple_whip"]
        elif style_name == "cyber_red":
            cfg = HOOK_STYLES["cyber_red"]
        else:
            cfg = HOOK_STYLES["neon"]
    f = _Font.get(cfg["font"])
    size = int(font_size) if font_size and int(font_size) >= 20 else cfg["size"]
    banner_max_w = int(max_w) if max_w and int(max_w) >= 200 else cfg.get("max_w", 920)

    # For Viral Floating styles without background box, ensure exactly ONE punch word is highlighted
    if cfg.get("no_box") and "*" not in hook:
        hook = _select_single_punch_word(hook, highlight_words=highlight)

    raw_words = hook.split()
    if not raw_words:
        return []

    words = [w.replace("*", "") for w in raw_words]
    lines_raw = [" ".join(raw_words)]
    lines_clean = [" ".join(words)]
    if f.width(lines_clean[0], size) > banner_max_w and len(raw_words) > 1:
        cut = min(range(1, len(raw_words)), key=lambda i: max(f.width(" ".join(words[:i]), size), f.width(" ".join(words[i:]), size)))
        lines_raw = [" ".join(raw_words[:cut]), " ".join(raw_words[cut:])]
        lines_clean = [" ".join(words[:cut]), " ".join(words[cut:])]
    widest = max(f.width(l, size) for l in lines_clean)
    if widest > banner_max_w:
        size = max(40, int(size * banner_max_w / widest))
        widest = max(f.width(l, size) for l in lines_clean)
    line_h = f.em(size) * 1.16

    if teaser_dur > 0:
        hook_dur = max(teaser_dur + 0.5, 3.8)
    else:
        hook_dur = min(3.8, max(2.5, dur * 0.35))
    span = f"{_ts(0)},{_ts(hook_dur)}"
    ev = []
    center_x = int(x) if x is not None else W // 2

    # Viral Floating styles without background box
    if cfg.get("no_box"):
        outline = cfg.get("outline", 7)
        shadow = cfg.get("shadow", 4)
        hl_col = cfg.get("highlight", "00E5FF")
        for i, raw_line in enumerate(lines_raw):
            cy = y - line_h * (len(lines_raw) - 1) / 2 + i * line_h - f.cap_shift(size)
            formatted = _format_hook_line_no_box(raw_line, cfg["ink"], hl_col, highlight_words=highlight)
            ev.append(f"Dialogue: 4,{span},Hook,,0,0,0,,{{\\an5\\pos({center_x},{cy:.0f})\\fad(0,350)\\fs{size}\\c&H{cfg['ink']}&\\bord{outline}\\3c&H000000&\\shad{shadow}\\4c&H000000&\\fscx88\\fscy88\\t(0,180,\\fscx100\\fscy100)}}{formatted}")
        return ev

    pad_x = cfg.get("pad_x", 42)
    pad_y = cfg.get("pad_y", 24)
    radius = cfg.get("radius", 28)
    bw, bh = widest + 2 * pad_x, line_h * len(lines_clean) + 2 * pad_y
    x0, y0, r = center_x - bw / 2, y - bh / 2, min(radius, bh / 2)
    x1, y1 = x0 + bw, y0 + bh
    n = lambda v: f"{v:.0f}"                                                         # noqa: E731
    box = (f"m {n(x0 + r)} {n(y0)} l {n(x1 - r)} {n(y0)} b {n(x1)} {n(y0)} {n(x1)} {n(y0)} {n(x1)} {n(y0 + r)} "
           f"l {n(x1)} {n(y1 - r)} b {n(x1)} {n(y1)} {n(x1)} {n(y1)} {n(x1 - r)} {n(y1)} "
           f"l {n(x0 + r)} {n(y1)} b {n(x0)} {n(y1)} {n(x0)} {n(y1)} {n(x0)} {n(y1 - r)} "
           f"l {n(x0)} {n(y0 + r)} b {n(x0)} {n(y0)} {n(x0)} {n(y0)} {n(x0 + r)} {n(y0)}")
    # Hook banner is shown at the start of the video for a few seconds to grab attention, with pop-in and smooth fadeout
    # Layer 1: Soft diffused 3D Drop Shadow
    ev.append(f"Dialogue: 1,{span},Hook,,0,0,0,,{{\\an7\\pos(0,12)\\fad(0,350)\\c&H000000&\\alpha&HA0&\\blur16\\fscx88\\fscy88\\t(0,180,\\fscx100\\fscy100)\\p1}}{box}{{\\p0}}")
    # Layer 2: Sleek contrast / neon accent border
    border_col = cfg.get("border")
    if border_col:
        ev.append(f"Dialogue: 2,{span},Hook,,0,0,0,,{{\\an7\\pos(0,0)\\fad(0,350)\\bord5\\3c&H{border_col}&\\c&H{cfg['box']}&\\fscx88\\fscy88\\t(0,180,\\fscx100\\fscy100)\\p1}}{box}{{\\p0}}")
    # Layer 3: Solid box
    ev.append(f"Dialogue: 3,{span},Hook,,0,0,0,,{{\\an7\\pos(0,0)\\fad(0,350)\\c&H{cfg['box']}&\\fscx88\\fscy88\\t(0,180,\\fscx100\\fscy100)\\p1}}{box}{{\\p0}}")
    # Layer 4: Punchy text
    for i, line in enumerate(lines_clean):
        cy = y - line_h * (len(lines_clean) - 1) / 2 + i * line_h - f.cap_shift(size)
        ev.append(f"Dialogue: 4,{span},Hook,,0,0,0,,{{\\an5\\pos({center_x},{cy:.0f})\\fad(0,350)\\fs{size}\\c&H{cfg['ink']}&\\fscx88\\fscy88\\t(0,180,\\fscx100\\fscy100)}}{line}")
    return ev


def _outro_events(dur: float, outro_text: str = "", y: int = 1500) -> list:
    """Animated 3D Outro Support Badge ('NEW CHANNEL • LIKE & SUBSCRIBE!') in the last 3.2 seconds."""
    if not outro_text or not str(outro_text).strip():
        outro_text = "NEW CHANNEL • LIKE & SUBSCRIBE!"
    # Strip unsupported emoji characters that fail in libass DirectWrite shaper, keeping symbols and words
    clean_text = re.sub(r"[^\w\s•!?,.'\":\-\$&#/]", "", str(outro_text)).strip()
    if not clean_text:
        clean_text = "NEW CHANNEL • LIKE & SUBSCRIBE!"
    outro_dur = 3.2
    start_t = max(0.5, dur - outro_dur)
    span = f"{_ts(start_t)},{_ts(dur)}"
    font_name = "Anton"
    f_obj = _Font.get(font_name)
    size = 76
    pad_x, pad_y, radius = 48, 22, 32
    widest = f_obj.width(clean_text, size)
    line_h = f_obj.em(size) * 1.15
    bw, bh = widest + 2 * pad_x, line_h + 2 * pad_y
    x0, y0 = (W - bw) / 2, y - bh / 2
    x1, y1 = x0 + bw, y0 + bh
    r = min(radius, bh / 2)
    n = lambda v: f"{v:.0f}"

    box = (f"m {n(x0 + r)} {n(y0)} l {n(x1 - r)} {n(y0)} b {n(x1)} {n(y0)} {n(x1)} {n(y0)} {n(x1)} {n(y0 + r)} "
           f"l {n(x1)} {n(y1 - r)} b {n(x1)} {n(y1)} {n(x1)} {n(y1)} {n(x1 - r)} {n(y1)} "
           f"l {n(x0 + r)} {n(y1)} b {n(x0)} {n(y1)} {n(x0)} {n(y1)} {n(x0)} {n(y1 - r)} "
           f"l {n(x0)} {n(y0 + r)} b {n(x0)} {n(y0)} {n(x0)} {n(y0)} {n(x0 + r)} {n(y0)}")

    cy = y - f_obj.cap_shift(size)
    ev = []
    # Layer 1: Diffused drop shadow
    ev.append(f"Dialogue: 1,{span},Outro,,0,0,0,,{{\\an7\\pos(0,14)\\c&H000000&\\alpha&HA0&\\blur16\\fscx85\\fscy85\\t(0,180,\\fscx100\\fscy100)\\fad(0,350)\\p1}}{box}{{\\p0}}")
    # Layer 2: Glowing sleek border (White / YouTube Accent)
    ev.append(f"Dialogue: 2,{span},Outro,,0,0,0,,{{\\an7\\pos(0,0)\\bord5\\3c&HFFFFFF&\\c&H1F20E6&\\fscx85\\fscy85\\t(0,180,\\fscx100\\fscy100)\\fad(0,350)\\p1}}{box}{{\\p0}}")
    # Layer 3: Solid box (YouTube Red &H1F20E6&)
    ev.append(f"Dialogue: 3,{span},Outro,,0,0,0,,{{\\an7\\pos(0,0)\\c&H1F20E6&\\fscx85\\fscy85\\t(0,180,\\fscx100\\fscy100)\\fad(0,350)\\p1}}{box}{{\\p0}}")
    # Layer 4: Bold text
    ev.append(f"Dialogue: 4,{span},Outro,,0,0,0,,{{\\an5\\pos({W // 2},{cy:.0f})\\fs{size}\\c&HFFFFFF&\\fscx85\\fscy85\\t(0,180,\\fscx100\\fscy100)\\fad(0,350)}}{clean_text}")
    return ev


def build_ass(words, start, end, hook, style_name, highlight, hook_y, cap_y, hook_style=None, outro_cta=True, outro_text=None, hook_w=None, hook_font_size=None, hook_x=None, teaser_dur=0.0) -> str:
    st = STYLES.get(style_name, STYLES["bounce"])
    cfg = HOOK_STYLES.get(hook_style or "")
    if not cfg:
        if style_name == "hype":
            cfg = HOOK_STYLES["yellow"]
        elif style_name == "clean":
            cfg = HOOK_STYLES["pill"]
        elif style_name == "mrbeast":
            cfg = HOOK_STYLES["yellow"]
        elif style_name == "purple_whip":
            cfg = HOOK_STYLES["purple_whip"]
        elif style_name == "cyber_red":
            cfg = HOOK_STYLES["cyber_red"]
        else:
            cfg = HOOK_STYLES["neon"]
    strong = {_key(h) for h in highlight if _key(h)}
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{st['font']},{st['size']},&H00{st['base']},&H00{st['base']},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,{st['outline']},0,5,0,0,0,1
Style: Hook,{cfg['font']},{cfg['size']},&H00{cfg['ink']},&H00{cfg['ink']},&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Outro,Anton,80,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dur = (end - start) + teaser_dur
    hook_show_dur = max(teaser_dur + 1.5, min(dur, 4.5)) if teaser_dur > 0 else dur
    ev = _hook_events(_clean(hook), dur, hook_y, style_name, hook_style, max_w=hook_w, font_size=hook_font_size, x=hook_x, highlight=strong, teaser_dur=teaser_dur)
    if outro_cta and dur >= 5.0:
        ev.extend(_outro_events(dur, outro_text, y=1680))
    f = _Font.get(st["font"])

    # Robust Timeline Normalization:
    # Convert every word timestamp directly onto the clip's local timeline (0.0 <= s <= dur).
    # When teaser_dur > 0, word timestamps are shifted by teaser_dur so captions match main video.
    inside = []
    if words:
        valid_words = [w for w in words if w.get("w")]
        min_s = min((float(w.get("s", 0.0)) for w in valid_words), default=0.0)
        is_absolute = bool(start > 2.0 and min_s >= start - 3.0)
        for w in valid_words:
            cw = _clean(w.get("w", ""))
            if not cw:
                continue
            ws = float(w.get("s", 0.0)) - (start if is_absolute else 0.0) - CAPTION_LEAD + teaser_dur
            we = float(w.get("e", ws + 0.3)) - (start if is_absolute else 0.0) - CAPTION_LEAD + teaser_dur
            if we > teaser_dur and ws < dur + 0.1:
                inside.append(dict(w, w=cw, s=max(teaser_dur, ws), e=min(dur, max(ws + 0.05, we))))

    inside = sorted(inside, key=lambda w: w["s"])
    for i, w in enumerate(inside[:-1]):
        w["e"] = max(w["s"], min(w["e"], inside[i + 1]["s"]))
    groups = _groups(inside, st["per"])
    for gi, g in enumerate(groups):
        g_start = max(0.0, g[0]["s"])
        g_end = min(dur, min(g[-1]["e"] + 0.25, groups[gi + 1][0]["s"] if gi + 1 < len(groups) else dur))
        if g_end - g_start < 0.02:
            continue
        texts = []
        for x in g:
            t = re.sub(r"[.,;:]+$", "", x["w"])
            texts.append(t.upper() if st["upper"] else t)
        if not all(roman.drawable(t) for t in texts):
            line = " ".join(texts)
            fs = max(44, min(int(st["size"] * 0.7), int(1500 / max(1, len(line)) * 1.6)))
            ev.append(f"Dialogue: 1,{_ts(g_start)},{_ts(g_end)},Cap,,60,60,0,,{{\\an5\\pos({W // 2},{cap_y:.0f})\\q0\\fs{fs}}}{line}")
            continue
        size = st["size"]
        gap = f.width("n n", size) - 2 * f.width("n", size) + (2 * st["outline"] + 6) * size / st["size"]
        total = sum(f.width(t, size) for t in texts) + gap * (len(texts) - 1)
        if total > CAP_MAX_W:
            size = max(36, int(size * CAP_MAX_W / total))
            gap = f.width("n n", size) - 2 * f.width("n", size) + (2 * st["outline"] + 6) * size / st["size"]
            total = sum(f.width(t, size) for t in texts) + gap * (len(texts) - 1)
        cy = cap_y - f.cap_shift(size)
        x = (W - total) / 2
        p = st["pop"]
        for i, (w, t) in enumerate(zip(g, texts)):
            wd = f.width(t, size)
            p = max(104, min(st["pop"], 100 + int(2200 / max(wd, 1))))
            pos = f"\\an5\\pos({x + wd / 2:.0f},{cy:.0f})\\fs{size}"
            x += wd + gap
            a = max(g_start, w["s"])
            b = min(g_end, g[i + 1]["s"] if i + 1 < len(g) else g_end)
            base = st["strong"] if _key(w["w"]) in strong else st["base"]
            anim_type = st.get("anim", "bounce")
            if a - g_start >= 0.02:
                ev.append(f"Dialogue: 1,{_ts(g_start)},{_ts(a)},Cap,,0,0,0,,{{{pos}\\c&H{base}&}}{t}")
            if b - a >= 0.02:
                if anim_type == "karaoke":
                    dur_cs = max(10, int((b - a) * 100))
                    ev.append(f"Dialogue: 2,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{{{pos}\\c&H{st['active']}&\\kf{dur_cs}}}{t}")
                else:
                    ev.append(f"Dialogue: 2,{_ts(a)},{_ts(b)},Cap,,0,0,0,,{{{pos}\\c&H{st['active']}&\\fscx92\\fscy92"
                              f"\\t(0,60,\\fscx{p}\\fscy{p})\\t(60,160,\\fscx{p - 4}\\fscy{p - 4})}}{t}")
            if g_end - b >= 0.02:
                ev.append(f"Dialogue: 1,{_ts(b)},{_ts(g_end)},Cap,,0,0,0,,{{{pos}\\c&H{base}&\\fscx{p - 4}\\fscy{p - 4}"
                          f"\\t(0,80,\\fscx100\\fscy100)}}{t}")
    return head + "\n".join(ev) + "\n"


PIP_W = 380            # how wide the facecam is in the 1080-wide frame
PIP_MARGIN = 26


def _filter(layout, fg_h, facecam=None, facecam_pos="top-right", facecam_delay=0.0, facecam_offset_y=0, game_offset_x=0, zoom=1.0, custom_layout=None, vin="0:v"):
    vin_prefix = f"[{vin}]setpts=PTS-STARTPTS,fps={config.OUT_FPS}"
    if abs(facecam_delay) >= 0.005:
        if facecam_delay < 0:
            fc_delay_filter = f",trim=start={abs(facecam_delay):.3f},setpts=PTS-STARTPTS"
        else:
            fc_delay_filter = f",tpad=start_duration={facecam_delay:.3f}:start_mode=clone,setpts=PTS-STARTPTS"
    else:
        fc_delay_filter = ""

    if layout == "custom" and isinstance(custom_layout, dict):
        cl_mode = str(custom_layout.get("mode") or "split").lower()
        fc_box = custom_layout.get("facecam") or facecam or [0, 0, 480, 360]
        gm_box = custom_layout.get("gameplay") or [0, 0, 1920, 1080]
        try:
            fx, fy, fw, fh = (max(0, int(v)) for v in fc_box[:4])
        except Exception:
            fx, fy, fw, fh = 0, 0, 480, 360
        try:
            gx, gy, gw, gh = (max(0, int(v)) for v in gm_box[:4])
        except Exception:
            gx, gy, gw, gh = 0, 0, 1920, 1080
        fw, fh = max(20, fw), max(20, fh)
        gw, gh = max(20, gw), max(20, gh)

        if cl_mode == "pip":
            pip_size = int(custom_layout.get("pip_size") or PIP_W)
            pip_h = max(2, int(round(pip_size * fh / fw)))
            pos = (custom_layout.get("pip_pos") or facecam_pos or "top-right").lower().strip()
            if pos in ("bottom-left", "bottom_left"):
                px, py = PIP_MARGIN, H - pip_h - 240
            elif pos in ("bottom-right", "bottom_right", "bottom"):
                px, py = W - pip_size - PIP_MARGIN, H - pip_h - 240
            elif pos in ("top-left", "top_left"):
                px, py = PIP_MARGIN, PIP_MARGIN
            else:
                px, py = W - pip_size - PIP_MARGIN, PIP_MARGIN
            return (f"{vin_prefix},split=2[base][fc];"
                    f"[base]crop={gw}:{gh}:{gx}:{gy},"
                    f"scale={W}:{H}:flags=lanczos+accurate_rnd:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},unsharp=5:5:0.5:5:5:0.0,setsar=1[b];"
                    f"[fc]crop={fw}:{fh}:{fx}:{fy}{fc_delay_filter},"
                    f"scale={pip_size}:{pip_h}:flags=lanczos+accurate_rnd,setsar=1[p];"
                    f"[b][p]overlay={px}:{py}[v0];")

        elif cl_mode == "crop":
            return (f"{vin_prefix},crop={gw}:{gh}:{gx}:{gy},"
                    f"scale={W}:{H}:flags=lanczos+accurate_rnd:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},unsharp=5:5:0.5:5:5:0.0,setsar=1[v0];")

        else:
            ratio = float(custom_layout.get("split_ratio") or 0.35)
            ratio = max(0.20, min(0.80, ratio))
            cam_h = int(round(H * ratio / 2)) * 2
            game_h = H - cam_h
            has_div = custom_layout.get("divider", True)
            div_filter = (f",drawbox=x=0:y={cam_h-3}:w={W}:h=6:color=0x141210:t=fill,"
                          f"drawbox=x=0:y={cam_h-1}:w={W}:h=2:color=0x00F0FF@0.9:t=fill" if has_div else "")
            return (f"{vin_prefix},split=2[game][cam];"
                    f"[cam]crop={fw}:{fh}:{fx}:{fy}{fc_delay_filter},"
                    f"scale={W}:{cam_h}:flags=lanczos+accurate_rnd:force_original_aspect_ratio=increase,"
                    f"crop={W}:{cam_h}:(in_w-out_w)/2:0,unsharp=5:5:0.4:5:5:0.0,setsar=1[f];"
                    f"[game]crop={gw}:{gh}:{gx}:{gy},"
                    f"scale={W}:{game_h}:flags=lanczos+accurate_rnd:force_original_aspect_ratio=increase,"
                    f"crop={W}:{game_h}:(in_w-out_w)/2:0,unsharp=5:5:0.5:5:5:0.0,setsar=1[g];"
                    f"[f][g]vstack=inputs=2{div_filter}[v0];")

    if layout == "split" and facecam and len(facecam) == 4 and int(facecam[2]) > 8:
        # Gamer Reaction Split (Top 1/3 Facecam Edge-to-Edge, Bottom 2/3 Game with Subtitle-Safe Framing):
        # Top 1/3 (1080x640): Streamer facecam fills edge-to-edge horizontally at y=0.
        # Streamer's face is prominent, centered & higher up; bottom ~28% of webcam box (chest/sweater/sub bar) is trimmed.
        # Bottom 2/3 (1080x1280): Huge game area with subtitle-safe framing.
        # Streamer's in-game webcam overlay on the left/right is cleanly cropped out while keeping dialogue subtitles 100% visible.
        # Broadcast divider: 6px dark bar + 2px glowing cyan line at y=637.
        fx, fy, fw, fh = (int(v) for v in facecam)
        cam_h = 640
        game_h = 1280
        fh_clean = max(10, int(fh * 0.72))
        fy_clean = max(0, fy - int(fh * 0.04) + facecam_offset_y)
        if fx < 280 and (fx + fw) <= 550:
            gx = max(0, max(fx + fw + 8, 265) + game_offset_x)
            game_crop = f"crop=min(in_w-{gx}\,(in_h*1.15)):in_h:{gx}:0"
        elif fx > 650:
            gw = max(100, fx - 8 + game_offset_x)
            game_crop = f"crop=min({gw}\,(in_h*1.15)):in_h:0:0"
        else:
            game_crop = "crop=min(in_w\,(in_h*1.15)):in_h:(in_w-min(in_w\,(in_h*1.15)))/2:0"
        return (f"{vin_prefix},split=2[game][cam];"
                f"[cam]crop={fw}:{fh_clean}:{fx}:{fy_clean}{fc_delay_filter},"
                f"scale={W}:{cam_h}:flags=lanczos+accurate_rnd:force_original_aspect_ratio=increase,"
                f"crop={W}:{cam_h}:(in_w-out_w)/2:0,unsharp=5:5:0.4:5:5:0.0,setsar=1[f];"
                f"[game]{game_crop},"
                f"scale={W}:{game_h}:flags=lanczos+accurate_rnd,unsharp=5:5:0.5:5:5:0.0,setsar=1[g];"
                f"[f][g]vstack=inputs=2,"
                f"drawbox=x=0:y={cam_h-3}:w={W}:h=6:color=0x141210:t=fill,"
                f"drawbox=x=0:y={cam_h-1}:w={W}:h=2:color=0x00F0FF@0.9:t=fill[v0];")

    if layout == "split_half" and facecam and len(facecam) == 4 and int(facecam[2]) > 8:
        # Classic 50/50 Split (1080x960 each):
        # Top half (1080x960): Streamer facecam fills edge-to-edge.
        # Bottom half (1080x960): Center gameplay with subtitle-safe framing & zero in-game cam leak.
        # Broadcast divider: 6px dark bar + 2px glowing cyan line (color=0x00F0FF@0.9).
        fx, fy, fw, fh = (int(v) for v in facecam)
        fh_clean = max(10, int(fh * 0.72))
        fy_clean = max(0, fy - int(fh * 0.04) + facecam_offset_y)
        if fx < 280 and (fx + fw) <= 550:
            gx = max(0, max(fx + fw + 8, 265) + game_offset_x)
            game_crop = f"crop=min(in_w-{gx}\,(in_h*1.125)):in_h:{gx}:0"
        elif fx > 650:
            gw = max(100, fx - 8 + game_offset_x)
            game_crop = f"crop=min({gw}\,(in_h*1.125)):in_h:0:0"
        else:
            game_crop = "crop=min(in_w\,(in_h*1.125)):in_h:(in_w-min(in_w\,(in_h*1.125)))/2:0"
        return (f"{vin_prefix},split=2[base][fc];"
                f"[fc]crop={fw}:{fh_clean}:{fx}:{fy_clean}{fc_delay_filter},"
                f"scale={W}:960:flags=lanczos+accurate_rnd:force_original_aspect_ratio=increase,"
                f"crop={W}:960:(in_w-out_w)/2:0,unsharp=5:5:0.4:5:5:0.0,setsar=1[f];"
                f"[base]{game_crop},"
                f"scale={W}:960:flags=lanczos+accurate_rnd,unsharp=5:5:0.5:5:5:0.0,setsar=1[g];"
                f"[f][g]vstack=inputs=2,drawbox=x=0:y=957:w={W}:h=6:color=0x141210:t=fill,drawbox=x=0:y=959:w={W}:h=2:color=0x00F0FF@0.9:t=fill[v0];")

    if layout == "gameplay" and facecam and len(facecam) == 4 and int(facecam[2]) > 8:
        # The game fills the screen with lanczos scaling and clarity enhancement,
        # and the webcam sits in the chosen corner of it with sub-frame sync calibration.
        fx, fy, fw, fh = (int(v) for v in facecam)
        pip_h = max(2, int(round(PIP_W * fh / fw)))

        # Determine corner position:
        pos = (facecam_pos or "top-right").lower().strip()
        if pos in ("bottom-left", "bottom_left"):
            pip_x = PIP_MARGIN
            pip_y = H - pip_h - 240
        elif pos in ("bottom-right", "bottom_right", "bottom"):
            pip_x = W - PIP_W - PIP_MARGIN
            pip_y = H - pip_h - 240
        elif pos in ("top-left", "top_left"):
            pip_x = PIP_MARGIN
            pip_y = PIP_MARGIN
        else:  # "top-right", "top", default
            pip_x = W - PIP_W - PIP_MARGIN
            pip_y = PIP_MARGIN

        return (f"{vin_prefix},split=2[base][fc];"
                f"[base]scale={W}:{H}:flags=lanczos+accurate_rnd:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},unsharp=5:5:0.5:5:5:0.0,setsar=1[b];"
                f"[fc]crop={fw}:{fh}:{fx}:{fy}{fc_delay_filter},scale={PIP_W}:{pip_h}:flags=lanczos+accurate_rnd,"
                f"setsar=1[p];"
                f"[b][p]overlay={pip_x}:{pip_y}[v0];")

    fill = f"{vin_prefix},scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    if layout == "crop" or (layout in ("gameplay", "split", "split_half") and not facecam):
        return f"{fill},unsharp=5:5:0.5:5:5:0.0,setsar=1[v0];"
    if layout == "left":
        return fill + ":0:0,setsar=1[v0];"
    if layout == "right":
        return fill + ":in_w-out_w:0,setsar=1[v0];"
    if layout == "fit":
        return f"{vin_prefix},scale={W}:{fg_h},pad={W}:{H}:0:(oh-ih)/2:black,setsar=1[v0];"

    return (f"{vin_prefix},split=2[a][b];"
            f"[a]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=6:2,"
            f"scale={W}:{H},eq=brightness=-0.14:saturation=1.15[bg];"
            f"[b]scale={W}:{fg_h}:force_original_aspect_ratio=increase,crop={W}:{fg_h}[fg];"
            f"[bg][fg]overlay=0:{(H-fg_h)//2},setsar=1[v0];")


def _hook_y(layout, hook_y, facecam=None, facecam_pos="top-right"):
    """Where the heading goes."""
    if layout == "split":
        return 690
    if layout in ("split_half", "custom"):
        return 1010
    if layout == "gameplay" and facecam and len(facecam) == 4 and facecam[2] > 8:
        pos = (facecam_pos or "top-right").lower().strip()
        if pos.startswith("bottom"):
            return 280  # Top of screen is wide open
        return PIP_MARGIN + int(round(PIP_W * facecam[3] / facecam[2])) + 32
    return hook_y


_qsv_ok = None
RENDER_SECONDS = 600      # one clip's video encode; far beyond normal, so a frozen encoder is stopped, not waited on


def render_clip(src: Path, out_dir: Path, name: str, clip: dict, words: list, src_w: int, src_h: int) -> dict:
    """Writes <name>.mp4, <name>.jpg and <name>.ass into out_dir. Returns file names."""
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = clip["start"], clip["end"]
    layout, fg_h, hook_y, cap_y = geometry(src_w, src_h, clip.get("layout", "blur"))
    face = clip.get("facecam")
    if layout in ("gameplay", "split", "split_half") and not (face and len(face) == 4):
        layout = "crop"     # no webcam found: the game fills the screen, which is still the right shape
    facecam_pos = clip.get("facecam_pos", "top-right")
    facecam_delay = float(clip.get("facecam_delay") or 0.0)
    audio_delay = float(clip.get("audio_delay") or 0.0)
    facecam_offset_y = int(clip.get("facecam_offset_y") or 0)
    game_offset_x = int(clip.get("game_offset_x") or 0)
    zoom = float(clip.get("zoom") or 1.0)
    custom_layout = clip.get("custom_layout")
    if isinstance(custom_layout, dict) and custom_layout.get("hook_y"):
        try:
            hook_y = int(custom_layout["hook_y"])
        except Exception:
            pass
    if clip.get("hook_y"):
        try:
            hook_y = int(clip["hook_y"])
        except Exception:
            pass
    else:
        hook_y = _hook_y(layout, hook_y, face, facecam_pos)

    hook_style = clip.get("hook_style") or (custom_layout.get("hook_style") if isinstance(custom_layout, dict) else None)
    hook_w = clip.get("hook_w") or (custom_layout.get("hook_w") if isinstance(custom_layout, dict) else None)
    hook_fs = clip.get("hook_font_size") or (custom_layout.get("hook_font_size") if isinstance(custom_layout, dict) else None)
    hook_x = clip.get("hook_x") or (custom_layout.get("hook_x") if isinstance(custom_layout, dict) else None)

    teaser_enabled = bool(clip.get("teaser_enabled"))
    main_dur = max(0.1, end - start)
    teaser_dur = 0.0
    teaser_start = None
    if teaser_enabled:
        teaser_dur = min(float(clip.get("teaser_dur") or 4.0), main_dur * 0.45)
        teaser_dur = max(1.5, round(teaser_dur, 2))
        if clip.get("teaser_start") is not None:
            try:
                teaser_start = max(start, min(float(clip["teaser_start"]), end - 1.0))
            except (ValueError, TypeError):
                teaser_start = max(start, end - teaser_dur)
        else:
            teaser_start = max(start, end - teaser_dur)

    ass = build_ass(words if clip.get("captions", True) else [], start, end, clip.get("hook", ""), clip.get("style", "bounce"),
                    clip.get("highlight_words", []), hook_y, cap_y, hook_style,
                    outro_cta=clip.get("outro_cta", True), outro_text=clip.get("outro_text"),
                    hook_w=hook_w, hook_font_size=hook_fs, hook_x=hook_x, teaser_dur=teaser_dur)
    # The clip is made in a short work folder and moved into place afterwards. The caption step of ffmpeg cannot
    # open files whose full path is longer than 260 characters on Windows, which a data folder deep inside other
    # folders easily reaches. Inside the work folder every name is short and relative (a drive colon would also
    # break the filter syntax).
    work = Path(tempfile.mkdtemp(prefix="pk"))
    try:
        meta = {"title": clip.get("title") or "", "description": clip.get("description") or "", "comment": clip.get("description") or ""}
        custom_layout = clip.get("custom_layout")
        return _render_in(work, src, out_dir, name, start, end, layout, fg_h, ass, face=face,
                          facecam_pos=facecam_pos, facecam_delay=facecam_delay, audio_delay=audio_delay, meta=meta,
                          facecam_offset_y=facecam_offset_y, game_offset_x=game_offset_x, zoom=zoom,
                          custom_layout=custom_layout, teaser_enabled=teaser_enabled, teaser_dur=teaser_dur,
                          teaser_start=teaser_start)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _render_in(work: Path, src: Path, out_dir: Path, name: str, start, end, layout, fg_h, ass: str, face=None,
               facecam_pos="top-right", facecam_delay=0.0, audio_delay=0.0, meta=None,
               facecam_offset_y=0, game_offset_x=0, zoom=1.0, custom_layout=None,
               teaser_enabled=False, teaser_dur=0.0, teaser_start=None) -> dict:
    global _qsv_ok
    (work / f"{name}.ass").write_text(ass, encoding="utf-8")
    (work / "f").mkdir()
    for f in config.FONTS_DIR.glob("*.ttf"):
        shutil.copyfile(f, work / "f" / f.name)
    dur = max(0.1, end - start)

    # Audio filters: reset audio PTS to 0.000s first, then resample to lock clock to video
    af_filters = ["asetpts=PTS-STARTPTS", "aresample=async=1000:min_hard_comp=0.010:first_pts=0"]
    if abs(audio_delay) >= 0.005:
        if audio_delay > 0:
            ms = int(round(audio_delay * 1000))
            af_filters.append(f"adelay={ms}|{ms}")
        else:
            af_filters.append(f"atrim=start={abs(audio_delay):.3f}")
            af_filters.append("asetpts=PTS-STARTPTS")
    af_filters.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    af_chain = ",".join(af_filters)

    if teaser_enabled and teaser_dur > 0:
        t_dur = min(float(teaser_dur), dur * 0.45)
        t_start = float(teaser_start if teaser_start is not None else (end - t_dur))
        seek_args = [
            "-ss", f"{t_start:.3f}", "-i", str(Path(src).resolve()), "-t", f"{t_dur:.3f}",
            "-ss", f"{start:.3f}", "-i", str(Path(src).resolve()), "-t", f"{dur:.3f}",
        ]
        concat_fc = f"[0:v]setpts=PTS-STARTPTS,fps={config.OUT_FPS}[tv];[0:a:0]asetpts=PTS-STARTPTS[ta];[1:v]setpts=PTS-STARTPTS,fps={config.OUT_FPS}[mv];[1:a:0]asetpts=PTS-STARTPTS[ma];[tv][ta][mv][ma]concat=n=2:v=1:a=1[v_raw][a_raw];"
        fc = concat_fc + _filter(layout, fg_h, face, facecam_pos=facecam_pos, facecam_delay=facecam_delay,
                     facecam_offset_y=facecam_offset_y, game_offset_x=game_offset_x, zoom=zoom,
                     custom_layout=custom_layout, vin="v_raw") + f"[v0]ass={name}.ass:fontsdir=f[v];[a_raw]{af_chain}[a]"
        base = ["ffmpeg", "-y", "-v", "error"] + seek_args + [
                "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
                "-avoid_negative_ts", "make_zero",
                "-fps_mode", "cfr",
                "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    else:
        seek_args = ["-ss", f"{start:.3f}", "-i", str(Path(src).resolve()), "-t", f"{dur:.3f}"]
        fc = _filter(layout, fg_h, face, facecam_pos=facecam_pos, facecam_delay=facecam_delay,
                     facecam_offset_y=facecam_offset_y, game_offset_x=game_offset_x, zoom=zoom,
                     custom_layout=custom_layout) + f"[v0]ass={name}.ass:fontsdir=f[v]"
        base = ["ffmpeg", "-y", "-v", "error"] + seek_args + [
                "-filter_complex", fc, "-map", "[v]", "-map", "0:a:0",
                "-af", af_chain,
                "-avoid_negative_ts", "make_zero",
                "-fps_mode", "cfr",
                "-c:a", "aac", "-b:a", "160k", "-ar", "48000"]
    for k, v in (meta or {}).items():
        if v:
            base += ["-metadata", f"{k}={v}"]
    base += ["-shortest", "-movflags", "+faststart", "-pix_fmt"]
    encoders = []
    # Ultra-clear 1080p60 broadcast profile: CRF 15, 16M average bitrate, 24M peak burst, Rec.709 color fidelity
    encoders.append(("x264", [
        "yuv420p", "-c:v", "libx264", "-crf", "15", "-preset", "medium",
        "-b:v", "16M", "-maxrate", "24M", "-bufsize", "32M",
        "-profile:v", "high", "-level", "4.2",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv"
    ]))
    if _qsv_ok is not False:
        encoders.append(("qsv", [
            "nv12", "-c:v", "h264_qsv", "-global_quality", "18", "-preset", "medium",
            "-b:v", "16M", "-maxrate", "24M"
        ]))
    err = None
    for label, enc in encoders:
        p = subprocess.run(base + enc + [f"{name}.mp4"], cwd=work, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=NO_WINDOW, timeout=RENDER_SECONDS)
        if p.returncode == 0:
            if label == "qsv":
                _qsv_ok = True
            break
        err = p.stderr[-1200:]
        if label == "qsv":
            _qsv_ok = False
    else:
        raise RuntimeError(f"Render failed: {err}")
    cover_t = min(1.2, (t_dur / 2) if (teaser_enabled and teaser_dur > 0) else ((end - start) / 2))
    run(["ffmpeg", "-y", "-v", "error", "-i", f"{name}.mp4", "-ss", f"{cover_t:.2f}", "-frames:v", "1",
         "-q:v", "3", f"{name}.jpg"], cwd=work)
    for ext in ("mp4", "jpg", "ass"):
        shutil.move(str(work / f"{name}.{ext}"), str(out_dir / f"{name}.{ext}"))
    return {"file": f"{name}.mp4", "cover": f"{name}.jpg", "layout": layout}
