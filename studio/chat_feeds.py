"""Multi-platform live chat feeds for PeakCut live sessions (Twitch IRC, YouTube Live Chat, Kick)."""
from __future__ import annotations

import collections
import json
import re
import socket
import ssl
import time
from urllib.parse import parse_qs, urlparse

import httpx

_NICK = re.compile(r"(?m)^:([A-Za-z0-9_]{2,25})!")
_YT_VID = re.compile(r"(?:[?&]v=|/live/|youtu\.be/)([A-Za-z0-9_-]{11})")
_YT_KEY = re.compile(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"')
_YT_CONT = re.compile(r'"continuation"\s*:\s*"([^"]{15,})"')
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def detect_platform(url: str) -> tuple[str, str]:
    """Identify streaming platform and channel/video target from a stream URL."""
    u = str(url or "").strip()
    if not u:
        return "", ""
    m_tw = re.match(r"^https?://(?:www\.)?twitch\.tv/([A-Za-z0-9_]+)", u, re.I)
    if m_tw:
        return "twitch", m_tw.group(1).lower()
    m_kk = re.match(r"^https?://(?:www\.)?kick\.com/([A-Za-z0-9_-]+)", u, re.I)
    if m_kk:
        return "kick", m_kk.group(1).lower()
    host = (urlparse(u if "://" in u else "https://" + u).hostname or "").lower()
    if "youtube" in host or host == "youtu.be":
        return "youtube", u
    return "", ""


def extract_youtube_video_id(url: str) -> str:
    """Extract 11-char YouTube video id from watch, live, or short share URLs."""
    m = _YT_VID.search(str(url or ""))
    if m:
        return m.group(1)
    q = parse_qs(urlparse(str(url or "")).query)
    vid = (q.get("v") or [""])[0]
    return vid if len(vid) == 11 else ""


def run_twitch_chat(session, channel: str) -> None:
    """Connect anonymously to Twitch IRC and stream PRIVMSG chat lines into session."""
    chan = str(channel or "").strip().lower()
    if not chan:
        return
    while not session.stop_flag.is_set() and not session.ended:
        try:
            raw = socket.create_connection(("irc.chat.twitch.tv", 6697), timeout=20)
            s = ssl.create_default_context().wrap_socket(raw, server_hostname="irc.chat.twitch.tv")
            s.sendall(f"NICK justinfan{int(time.time()) % 90000 + 10000}\r\nJOIN #{chan}\r\n".encode())
            s.settimeout(30)
            rest = b""
            session.chat_on = True
            while not session.stop_flag.is_set() and not session.ended:
                try:
                    data = s.recv(8192)
                except socket.timeout:
                    continue
                if not data:
                    break
                *lines, rest = (rest + data).split(b"\r\n")
                for line in lines:
                    if line.startswith(b"PING"):
                        s.sendall(b"PONG :tmi.twitch.tv\r\n")
                    elif b" PRIVMSG #" in line:
                        line_str = line.decode("utf-8", "replace")
                        who = _NICK.findall(line_str)
                        if who:
                            parts = line_str.split(f" PRIVMSG #{chan} :", 1)
                            msg = parts[1].strip() if len(parts) > 1 else ""
                            session._record_chat_msg(who[0], msg)
            s.close()
        except Exception:  # noqa: BLE001
            pass
        session.chat_on = False
        session.stop_flag.wait(5)


def _yt_parse_actions(data: dict) -> tuple[list[tuple[str, str, str]], str, float]:
    """Parse (id, author, text) entries, next continuation token, and wait seconds from YouTube chat JSON."""
    cont_obj = (data.get("continuationContents") or {}).get("liveChatContinuation") or {}
    msgs = []
    for act in cont_obj.get("actions") or []:
        item = (act.get("addChatItemAction") or {}).get("item") or {}
        ren = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer") or {}
        if not ren:
            continue
        mid = str(ren.get("id") or "")
        author = str((ren.get("authorName") or {}).get("simpleText") or "Viewer").strip()
        runs = (ren.get("message") or {}).get("runs") or []
        text = "".join(str(r.get("text") or ((r.get("emoji") or {}).get("shortcuts") or [""])[0]) for r in runs).strip()
        if author and text:
            msgs.append((mid, author, text))
    nxt_cont = ""
    wait_sec = 3.0
    for c in cont_obj.get("continuations") or []:
        for k in ("invalidationContinuationData", "timedContinuationData"):
            if isinstance(c.get(k), dict):
                nxt_cont = c[k].get("continuation") or nxt_cont
                ms = float(c[k].get("timeoutMs") or 3000)
                wait_sec = max(2.0, min(8.0, ms / 1000.0))
                break
        if nxt_cont:
            break
    return msgs, nxt_cont, wait_sec


def run_youtube_chat(session, url: str) -> None:
    """Poll YouTube Live Chat continuation feed publicly with bounded deduplication and clean shutdown."""
    seen_ids: collections.deque[str] = collections.deque(maxlen=600)
    seen_set: set[str] = set()
    headers = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}

    while not session.stop_flag.is_set() and not session.ended:
        try:
            vid = extract_youtube_video_id(url)
            with httpx.Client(headers=headers, timeout=15, follow_redirects=True) as cli:
                if not vid:
                    r_page = cli.get(url)
                    if r_page.status_code == 200:
                        m_can = re.search(r'watch\?v=([A-Za-z0-9_-]{11})', r_page.text)
                        if m_can:
                            vid = m_can.group(1)
                if not vid:
                    session.stop_flag.wait(15)
                    continue
                r_chat = cli.get(f"https://www.youtube.com/live_chat?is_popout=1&v={vid}")
                if r_chat.status_code != 200:
                    session.stop_flag.wait(15)
                    continue
                m_key = _YT_KEY.search(r_chat.text)
                m_cont = _YT_CONT.search(r_chat.text)
                if not (m_key and m_cont):
                    session.stop_flag.wait(20)
                    continue
                api_key, cont = m_key.group(1), m_cont.group(1)
                session.chat_on = True
                while cont and not session.stop_flag.is_set() and not session.ended:
                    payload = {
                        "context": {"client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00"}},
                        "continuation": cont,
                    }
                    r_api = cli.post(f"https://www.youtube.com/youtubei/v1/live_chat/get_live_chat?key={api_key}", json=payload)
                    if r_api.status_code != 200:
                        break
                    msgs, cont, wait_sec = _yt_parse_actions(r_api.json())
                    for mid, author, text in msgs:
                        dedup_key = mid or f"{author}:{text[:40]}"
                        if dedup_key in seen_set:
                            continue
                        if len(seen_ids) == seen_ids.maxlen:
                            old = seen_ids.popleft()
                            seen_set.discard(old)
                        seen_ids.append(dedup_key)
                        seen_set.add(dedup_key)
                        session._record_chat_msg(author, text)
                    session.stop_flag.wait(wait_sec)
        except Exception:  # noqa: BLE001
            pass
        session.chat_on = False
        session.stop_flag.wait(8)


def _is_cf_blocked(resp: httpx.Response) -> bool:
    if resp.status_code in (403, 429):
        body = (resp.text or "")[:1500].lower()
        return "cf-" in body or "cloudflare" in body or "just a moment" in body or "challenge" in body or resp.status_code == 403
    return False


def run_kick_chat(session, slug: str) -> None:
    """Poll public Kick channel messages if accessible; cleanly stop without bypassing Cloudflare anti-bot checks."""
    chan = str(slug or "").strip().lower()
    if not chan:
        return
    seen_ids: collections.deque[str] = collections.deque(maxlen=600)
    seen_set: set[str] = set()
    headers = {"User-Agent": _UA, "Accept": "application/json"}

    try:
        with httpx.Client(headers=headers, timeout=12, follow_redirects=True) as cli:
            while not session.stop_flag.is_set() and not session.ended:
                r_ch = cli.get(f"https://kick.com/api/v2/channels/{chan}/messages")
                if _is_cf_blocked(r_ch):
                    session.chat_note = "Kick chat unavailable (anti-bot protected)"
                    session.chat_on = False
                    return
                if r_ch.status_code == 200:
                    try:
                        payload = r_ch.json()
                    except (ValueError, TypeError):
                        payload = {}
                    raw_msgs = payload.get("data", {}).get("messages") if isinstance(payload.get("data"), dict) else payload.get("messages")
                    if isinstance(raw_msgs, list):
                        session.chat_on = True
                        for item in raw_msgs[-30:]:
                            if not isinstance(item, dict):
                                continue
                            mid = str(item.get("id") or "")
                            sender = item.get("sender") if isinstance(item.get("sender"), dict) else {}
                            user = str(sender.get("username") or item.get("username") or "Viewer").strip()
                            msg = str(item.get("content") or item.get("message") or "").strip()
                            dedup_key = mid or f"{user}:{msg[:40]}"
                            if msg and dedup_key not in seen_set:
                                if len(seen_ids) == seen_ids.maxlen:
                                    seen_set.discard(seen_ids.popleft())
                                seen_ids.append(dedup_key)
                                seen_set.add(dedup_key)
                                session._record_chat_msg(user, msg)
                session.stop_flag.wait(4)
    except Exception:  # noqa: BLE001
        pass
    session.chat_on = False


def run_chat_loop(session) -> None:
    """Dispatch live chat monitoring for Twitch, YouTube, or Kick stream URLs."""
    url = ((session.job.get("source") or {}).get("url") or session.job.get("url") or "").strip()
    plat, target = detect_platform(url)
    if plat == "twitch":
        session.channel = target
        run_twitch_chat(session, target)
    elif plat == "youtube":
        session.channel = target
        run_youtube_chat(session, target)
    elif plat == "kick":
        session.channel = target
        run_kick_chat(session, target)
