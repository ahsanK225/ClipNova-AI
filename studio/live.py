"""Live sessions: record a stream into a rolling buffer, transcribe as it goes, let the AI pick clips."""
import collections
import json
import re
import socket
import ssl
import subprocess
import threading
import time
from pathlib import Path

import numpy as np

from . import ai, alerts, auth, brain, chat_feeds, config, creators, ctx, facecam, games, hashtags, jobs, load, media, safe, transcribe, usage, ohnepixel

# ":username!user@host PRIVMSG #channel :the message"
_NICK = re.compile(r"(?m)^:([A-Za-z0-9_]{2,25})!")

SESSIONS: dict = {}
SEG_SEC = 6           # length of each buffer piece
STALL_SEC = 90        # sound arriving but no picture for this long: start the recorder again
PAD = 8               # seconds kept either side of a clip so it can be re-trimmed later
CHECK_EVERY = 180     # look at the stream every 3 minutes...
QUIET_MAX = 600       # ...but only ask the AI when something happened, or at most every 10 minutes when calm
WINDOW = 240          # seconds of transcript shown to the AI per check
CHAT_KEEP = 600       # seconds of chat names kept: only the last few minutes are ever read
SR = 16000


class NotLive(Exception):
    pass


def _trim_names(users: dict, second: int, kept: int) -> int:
    """Drop the chat names older than CHAT_KEEP, and say when this was last done.

    Only the last few minutes are ever read, and a stream that runs for eight hours would otherwise hold
    a name for every second of it. Called under the session's lock, from the chat reader thread."""
    if second - kept < 60:
        return kept              # walking the whole dict on every message would cost more than it saves
    for t in [t for t in users if t < second - CHAT_KEEP]:
        del users[t]
    return second


def media_safe(e) -> str:
    from . import safe
    return safe.friendly(e, 300)


def normalize(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url
    m = re.match(r"^(https?://(?:www\.)?youtube\.com/(?:@[^/?#]+|channel/[^/?#]+|c/[^/?#]+))(?:/(?:streams|videos|featured|live|community))?/?(?:[?#].*)?$", url)
    return m.group(1) + "/live" if m else url


class _Quiet:
    def debug(self, m): pass
    def info(self, m): pass
    def warning(self, m): pass
    def error(self, m): pass


def resolve(url: str, quality: int = 720) -> dict:
    """Ask yt-dlp for the stream's playable address. Raises NotLive if the channel is offline."""
    url = normalize(url)
    import shutil
    import yt_dlp
    node = shutil.which("node") or ("C:\\Program Files\\nodejs\\node.exe" if Path("C:\\Program Files\\nodejs\\node.exe").is_file() else None)
    q = int(quality or 720)
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "logger": _Quiet(),
            "format": f"b[height<={q}]/bv*[height<={q}]+ba/b", **media.cookie_opts()}
    if node:
        opts["js_runtimes"] = {"node": {"path": str(node)}}
    c = media._cookie_file()
    if c:
        opts["cookiefile"] = str(c)
    if media.is_youtube(url) and media.youtube_paused():
        raise NotLive(media.YT_BLOCKED)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:  # noqa: BLE001
        if media.note_refusal(url, e):
            raise NotLive(media.YT_BLOCKED) from e
        raise NotLive(str(e)[-200:]) from e
    if not info or not info.get("is_live"):
        raise NotLive("This channel is not live right now.")
    fmts = info.get("requested_formats") or [info]
    title = info.get("title") or ""
    if "(live)" in title and info.get("description"):  # Twitch puts the real stream title here
        title = str(info["description"]).splitlines()[0][:120]
    urls = [f["url"] for f in fmts if isinstance(f, dict) and f.get("url")]
    if not urls:
        raise NotLive("Could not open the live stream.")
    return {"urls": urls, "title": title,
            "uploader": info.get("uploader") or info.get("channel") or ""}


def active():
    return [s for s in SESSIONS.values() if not s.finished and not s.user_stopped]


def active_mine():
    u = ctx.uid()
    return [s for s in active() if s.job["user"] == u]


def active_for(cid):
    return next((s for s in active_mine() if s.job["creator"] == cid), None)


def mine(jid):
    """The signed-in user's recording with this id, or None."""
    s = SESSIONS.get(jid)
    return s if s and s.job["user"] == ctx.uid() else None


class Session:
    def __init__(self, job, settings):
        self.job, self.settings = job, settings
        self.quality = int(self.settings.get("quality") or self.job.get("options", {}).get("quality") or 720)
        self.dir = Path(job["dir"])
        self.buf = self.dir / "buffer"
        self.buf.mkdir(exist_ok=True)
        (self.dir / "clips").mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.stop_flag = threading.Event()
        self.ended = False            # recording has stopped (stream over, stopped, or failed)
        self.finished = False         # everything is wrapped up
        self.end_note = "Stream ended"
        self.user_stopped = False     # Stop pressed: wrap up at once, no last AI check
        self.proc = None
        self.pending = bytearray()    # audio received but not yet transcribed
        self.audio_downsampled = []   # 2000Hz downsampled audio float32 history for waveform synchronization
        self.clock_fix = 0.0          # how far the video-piece clock is behind the audio clock, last measured
        self.pending_base = 0         # sample index where `pending` starts
        self.samples = 0              # total audio samples received
        self.db = []                  # loudness per second
        self.words = []
        self.t_done = 0.0             # transcript is complete up to this second
        self.segments = []            # (path, start, end) on the session clock
        self.seg_clock = 0.0
        self.part_base = {}           # part -> the stream second that part's own list starts at
        self.csv_seen = {}
        self.listed = set()           # every piece ffmpeg's own list has named (the rest are unfinished)
        self.swept = 0.0              # when the buffer was last searched for unfinished pieces
        self.part = 0
        self.chat = collections.Counter()   # second -> messages
        self.chat_users = {}                 # second -> the people who talked, when it can be told
        self.chat_kept = 0                   # the second this was last pruned at
        self.chat_total = 0
        self.chat_on = False
        self.chat_note = ""
        self.recent_chat_msgs = collections.deque(maxlen=60)  # live buffer of incoming chat messages
        self.channel = None
        self.last_check = 0.0
        self.words_at_check = 0
        self.checks = 0
        self.rejected = 0
        self.verdicts = []
        self.last_trigger = -999.0
        self.started_at = time.time()
        self.skipped = 0
        self.last_ai = 0.0
        self.tokens = 0
        self.manual = []
        self.n = 0
        self.spike = None             # a jump in loudness or chat waiting for its transcript
        self.said = None              # someone said "clip": that moment, waiting for its transcript
        self.last_said = -999.0
        self.last_spike = -999.0      # when the last jump was sent to the AI (stream seconds)
        self.base = {}                # running averages the jumps are measured against, shown on the card
        self.spikes = 0
        self.stalled = 0              # times the picture stopped while the sound went on, and the recorder restarted
        self.game = ""                # which game this stream is, when it can be told
        self.facecam_box = None       # where the webcam is, found once the first clip is made
        self.facecam_checked = False  # the look is made once, even when it finds nothing
        self.ai_busy = 0.0            # when the AI check now running was started, 0 when none is

    def active_detection_mode(self) -> str:
        """Returns the active clipping detection mode: Mode A (AI Intelligent Scoring) or Mode B (Keyword Fallback)."""
        return "MODE A (AI INTELLIGENT SCORING)" if ai.ready() else "MODE B (KEYWORD FALLBACK)"

    def _ask_ai(self, window=None, why=None):
        """Ask the AI on its own thread, so a slow answer never stops the recording.

        While the AI thinks, the speech keeps being written and a "clip that" still works. One check
        runs at a time; if the running one is stuck far past its own timeout, a new one is let through.
        """
        now = time.time()
        if self.ai_busy and now - self.ai_busy < config.LIVE_AI_TIMEOUT + 60:
            return

        def work():
            try:
                self._ai_check(window, why)
            except Exception as e:  # noqa: BLE001
                self.job["ai"]["last_error"] = str(e)[-200:]
            finally:
                self.ai_busy = 0.0
        self.ai_busy = now
        threading.Thread(target=ctx.bind(work), daemon=True, name="ai_check").start()

    def _find_facecam(self, src):
        """Where the webcam is in the stream, once. Only a sure answer is used.

        One frame goes to the AI as well, and whatever it says is measured again on the
        picture. A stream where the webcam is a square picture along the right edge, or
        one where there is no webcam at all and the game has panels of its own, is told
        apart from a real camera by what moves: a person sits still, the game does not."""
        try:
            box = facecam.detect(src, ask=brain.look_for_facecam)
        except Exception:  # noqa: BLE001 - a missing facecam is not a failure
            return None
        if not box:
            return None
        self.job["facecam"] = [box["x"], box["y"], box["w"], box["h"]]
        return self.job["facecam"]

    # ---------------------------------------------------------------- the game this stream is
    def _game(self):
        """The game, from what the creator set or from what the stream's title says.

        The stream title is the best place to look: on launch night it says the game."""
        if self.game:
            return self.game
        found = games.detect(self.settings.get("game"), self.job.get("title"), self.job.get("uploader"),
                             self.job.get("source", {}).get("name"))
        self.game = found[0] or ""
        if self.game:
            try:
                self.job["game"] = self.game
            except Exception:  # noqa: BLE001
                pass
        return self.game

    # ---------------------------------------------------------------- recording
    def start(self):
        SESSIONS[self.job["id"]] = self
        threading.Thread(target=ctx.bind(self._ingest), daemon=True).start()
        threading.Thread(target=ctx.bind(self._analyze), daemon=True).start()
        url = (self.job.get("source") or {}).get("url") or self.job.get("url") or ""
        plat, target = chat_feeds.detect_platform(url)
        if plat:
            self.channel = target
            threading.Thread(target=ctx.bind(chat_feeds.run_chat_loop), args=(self,), daemon=True).start()

    def stop(self, note="Stopped by you"):
        """Instant for the user: the card and the creator show as stopped straight away. Clips already being made
        still finish in the background, but nothing new is transcribed or sent to the AI."""
        self.end_note = note
        self.user_stopped = True
        self.stop_flag.set()
        with self.lock:
            self.job.update(status="done", stage=note)
            proc = self.proc
        jobs.save(self.job)
        if proc and proc.poll() is None:
            proc.terminate()

    def _ingest(self):
        """Record the stream. However this ends, even when ffmpeg cannot start at all, the session is marked as
        ended, so it stops showing as recording and gives its place to the next one."""
        try:
            self._ingest_loop()
        except Exception as e:  # noqa: BLE001
            self.job["error"] = f"Recording stopped: {media_safe(e)}"
        finally:
            self.ended = True

    def _ingest_loop(self):
        fails = 0
        url = self.job["source"]["url"]
        while not self.stop_flag.is_set():
            try:
                try:
                    info = resolve(url, quality=self.quality)
                except TypeError:
                    info = resolve(url)
            except Exception as e:
                fails += 1
                max_fails = 3 if self.samples == 0 else 10
                if fails >= max_fails:
                    if self.samples == 0:
                        self.job["error"] = f"Could not start recording: {media_safe(e)}"
                    break
                self.stop_flag.wait(5 if fails < 3 else 10)
                continue
            if self.stop_flag.is_set():     # stop() came while the stream address was being looked up
                break
            if not self.job.get("uploader"):
                self.job.update(title=info["title"], uploader=info["uploader"])
            self.part += 1
            with self.lock:
                self.seg_clock = max(self.seg_clock, self.samples / SR)
            p = f"p{self.part:02d}"
            cmd = ["ffmpeg", "-v", "error"]
            for u in info["urls"]:
                cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
                        "-rw_timeout", "15000000", "-i", u]
            a_in = "1:a:0" if len(info["urls"]) > 1 else "0:a:0"
            cmd += ["-map", "0:v:0", "-map", a_in, "-c", "copy", "-f", "segment", "-segment_time", str(SEG_SEC),
                    "-reset_timestamps", "1", "-segment_format", "mpegts", "-segment_list", f"{p}.csv",
                    "-segment_list_type", "csv", f"{p}_%05d.ts",
                    "-map", a_in, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "pipe:1"]
            with open(self.dir / "ffmpeg.log", "ab") as errlog:
                proc = subprocess.Popen(cmd, cwd=self.buf, stdout=subprocess.PIPE, stderr=errlog,
                                        creationflags=media.NO_WINDOW)
                with self.lock:               # same lock stop() takes, so stop() always sees this process
                    self.proc = proc
                    stopped = self.stop_flag.is_set()
                if stopped:
                    proc.terminate()
                got = 0
                while True:
                    if self.stop_flag.is_set():
                        if proc.poll() is None:
                            proc.terminate()
                        break
                    data = proc.stdout.read(SR * 2)  # one second of 16-bit mono
                    if not data:
                        break
                    data = data[: len(data) // 2 * 2]
                    got += len(data)
                    x = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                    level = float(20 * np.log10(np.sqrt((x ** 2).mean() + 1e-10))) if len(x) else -100.0
                    with self.lock:
                        self.pending += data
                        self.samples += len(data) // 2
                        self.db.append(level)
                        if len(x):
                            self.audio_downsampled.extend(x[::8].tolist())
                            if len(self.audio_downsampled) > 15 * 60 * 2000:
                                self.audio_downsampled = self.audio_downsampled[-15 * 60 * 2000:]
                    if self.samples / SR - self.seg_clock > STALL_SEC:
                        # The sound is still arriving but no picture has been written for a while: Twitch
                        # does this around an ad break or a stream hiccup, and ffmpeg can stay stuck on it
                        # for the rest of the stream, leaving a recording with sound and no video. Start
                        # again from the live edge; the break in the picture shows up as a gap in the buffer.
                        self.stalled += 1
                        proc.terminate()
                        break
                proc.stdout.close()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            fails = 0 if got > SR * 2 * 10 else fails + 1
            max_fails = 3 if self.samples == 0 else 10
            if fails >= max_fails:
                break
            self.stop_flag.wait(3)

    def _scan_segments(self):
        """Pick up buffer pieces ffmpeg has finished writing."""
        with self.lock:
            for i in range(1, self.part + 1):
                f = self.buf / f"p{i:02d}.csv"
                if not f.exists():
                    continue
                rows = [r.split(",") for r in f.read_text(encoding="utf-8", errors="ignore").splitlines() if r.count(",") >= 2]
                fresh = rows[self.csv_seen.get(i, 0):]
                if fresh and i not in self.part_base:
                    # Where this part's own list starts: a list that carries on from where the last one
                    # stopped needs no shift, one that begins again at zero is shifted to the stream clock.
                    first = fresh[0]
                    try:
                        self.part_base[i] = 0.0 if float(first[1]) >= self.seg_clock - 5 else self.seg_clock
                    except (IndexError, ValueError):
                        self.part_base[i] = 0.0
                base = self.part_base.get(i, 0.0)
                for name, a, b in (r[:3] for r in fresh):
                    try:
                        start, end = base + float(a), base + float(b)
                    except ValueError:
                        continue
                    if end <= start:
                        continue
                    # The list ffmpeg writes says where in the stream each piece sits. Adding the lengths
                    # up instead loses the whole of every piece that went missing (a Twitch stream drops
                    # some), so the buffer slowly fell behind the clock clips ask for, until a moment still
                    # in the buffer looked long gone.
                    self.segments.append((self.buf / name, start, end))
                    self.seg_clock = max(self.seg_clock, end)
                self.listed.update(r[0] for r in rows if len(r) > 2)
                self.csv_seen[i] = len(rows)
            keep_from = self.seg_clock - self.settings["buffer_min"] * 60
            while self.segments and self.segments[0][2] < keep_from:
                self.segments.pop(0)[0].unlink(missing_ok=True)
            if time.time() - self.swept > 60:
                # A recording that is stopped in the middle of a piece leaves that piece behind with no line
                # in ffmpeg's list: no clip is ever cut from it, and it would sit in the buffer for ever. Every
                # restart of the recorder used to leave one behind: about forty megabytes each time.
                self.swept = time.time()
                now = time.time()
                for p in self.buf.glob("p*.ts"):
                    try:
                        if p.name not in self.listed and now - p.stat().st_mtime > 60:
                            p.unlink(missing_ok=True)
                    except OSError:          # already gone: a finished recording clears the buffer
                        pass

    # ---------------------------------------------------------------- chat (Twitch, YouTube, Kick)
    def _record_chat_msg(self, user: str, msg: str) -> None:
        """Record an incoming chat message and increment per-second viewer velocity."""
        with self.lock:
            second = int(self.samples / SR)
            self.chat[second] += 1
            self.chat_total += 1
            who = str(user or "").strip()
            if who:
                self.chat_users.setdefault(second, set()).add(who.lower())
                self.chat_kept = _trim_names(self.chat_users, second, self.chat_kept)
                clean_msg = str(msg or "").strip()
                if clean_msg:
                    self.recent_chat_msgs.append({
                        "user": who[:40],
                        "msg": clean_msg[:140],
                        "t": time.time(),
                    })

    def _chat(self, channel):
        chat_feeds.run_twitch_chat(self, channel)

    def _chat_spike(self, s, e):
        """True if chat was at least 3x busier than usual during (and just after) these seconds.

        The crowd is counted as people, not messages: ten people saying "GG" is a reaction, one
        person saying "GG" ten times is a bot."""
        elapsed = self.samples / SR
        if not self.chat_total or elapsed < 60:
            return False
        avg = self.chat_total / elapsed
        a, b = int(s), int(e) + 6
        rate = sum(self.chat.get(t, 0) for t in range(a, b + 1)) / (b - a + 1)
        if rate <= max(3 * avg, 1.0):
            return False
        people = self.chat_people()
        if not people:
            return True
        p_avg = sum(len(v) for v in people.values()) / max(1, len(people))
        p_rate = sum(len(people.get(t, ())) for t in range(a, b + 1)) / (b - a + 1)
        return p_rate >= max(2.0, 1.5 * p_avg)

    def chat_people(self):
        """Second -> how many different people were talking, where that is known.

        A copy is taken under the lock: the chat reader thread adds to it as it goes."""
        with self.lock:
            return {t: set(names) for t, names in self.chat_users.items()}

    # ---------------------------------------------------------------- analysis
    def _transcribe_step(self):
        with self.lock:
            n = len(self.pending) // 2
            hurry = self.ended or bool(self.manual)
            if n < (SR if hurry else SR * 7):   # about every 7 s, so "what was just said" really is live
                return False
            audio = np.frombuffer(bytes(self.pending[: n * 2]), dtype=np.int16)
            base = self.pending_base
        cut = n
        if not hurry or n > SR * 24:
            # cut at the quietest moment between 4 and 6.5 s, so no word is split; the rest waits for the next pass
            _, cut = next(transcribe._chunks(audio, 4.0, 6.5))
        words = transcribe.transcribe(audio[:cut], lang=self.job.get("lang") or "en")
        off = base / SR
        for w in words:
            w["s"], w["e"] = round(w["s"] + off, 2), round(w["e"] + off, 2)
        with self.lock:
            del self.pending[: cut * 2]
            self.pending_base += cut
            self.words += words
            self.t_done = self.pending_base / SR
        self._triggers(words)
        safe.atomic_write_text(self.dir / "words.json", json.dumps(self.words), backup=True)
        return True

    AUTO_BEFORE, AUTO_AFTER, AUTO_GAP = 30, 20, 60   # seconds of stream sent around a jump; least time between jumps
    JUMP = 0.6                                        # 60% louder or busier than the last three minutes

    def _watch_spikes(self):
        """Always on. Keep a running average of loudness and chat over the last three minutes (leaving out the
        last few seconds), and mark a moment when the last five seconds jump a set percentage above it. Nothing is
        sent yet: the AI gets that moment once its transcript is ready, with the half minute before it."""
        with self.lock:
            n = len(self.db)
            if n < 60:
                self.base = {"warming": True}
                return
            db = np.array(self.db[max(0, n - 190):], dtype=np.float32)
            people = self.chat_people()
            if people:
                chat = [len(people.get(t, ())) for t in range(max(0, n - 190), n)]
            else:
                chat = [self.chat.get(t, 0) for t in range(max(0, n - 190), n)] if (self.chat_on or self.chat_total) else None
        amp = 10 ** (db / 20)                       # loudness as plain level, so a percentage means something
        base, cur = float(amp[:-10].mean()), float(amp[-5:].mean())
        loud_jump = cur / max(base, 1e-6) - 1
        pct = self.JUMP
        why = []
        if loud_jump >= pct:
            why.append(f"loudness +{round(loud_jump * 100)}%")
        chat_base = chat_now = None
        if chat is not None:
            chat_base = sum(chat[:-10]) / max(1, len(chat) - 10)
            chat_now = sum(chat[-8:]) / 8          # chat is bursty, so look at a slightly longer stretch
            if chat_now >= max(1.5, chat_base * (1 + pct)):
                why.append(f"chat +{round((chat_now / max(chat_base, 0.01) - 1) * 100)}%")
        self.base = {"loud_db": round(20 * np.log10(max(base, 1e-6)), 1), "loud_now": round(loud_jump * 100),
                     "chat": round(chat_base, 2) if chat_base is not None else None,
                     "chat_now": round(chat_now, 2) if chat_now is not None else None, "pct": round(pct * 100)}
        if why and not self.spike and n - self.last_spike >= self.AUTO_GAP:
            self.spike = {"t": float(n - 3), "why": ", ".join(why)}
            self.last_spike = n
            self.spikes += 1

    def _ai_check(self, window=None, why=None):
        """Judge 1 reads only the words. If it finds a moment, judge 2 reads only the loudness and chat activity
        for the same stretch, without seeing the words. A clip is made when both say yes (or as set in Setup)."""
        st = self.settings
        every = int(st.get("ai_every_min", 3)) or 3
        if window:                    # just the stretch around a jump, or around someone saying "clip"
            ws, now = max(0.0, window[0]), window[1]
        else:
            now = self.t_done
            ws = max(0.0, now - max(every, 3) * 60 - 90)  # each check overlaps the last by 90 s, so nothing falls between
        self.last_check = self.t_done
        win = [w for w in self.words if ws <= w["s"] <= now]
        recent = [c for c in self.job["clips"] if c.get("score", 0) > 0 and time.time() - c.get("made_at", 0) < 3600]
        last_clip = max((c.get("made_at", 0) for c in self.job["clips"]), default=self.started_at)
        must = st["must_clip_min"] > 0 and time.time() - last_clip >= st["must_clip_min"] * 60
        verdict = {"t": round(now), "wall_t": time.time(), "transcript": None, "reaction": None, "trigger": why, "model": ai.last_active_model()}
        if len(win) < 8:
            # Allow quiet visual moments to qualify via sampled stream frames when AI is available
            q_frames = []
            if ai.ready():
                raw_fb = self._extract_window_frames(ws, now, count=4)
                if raw_fb:
                    step = max(1.0, (now - ws) / max(1, len(raw_fb)))
                    q_frames = [(round(ws + (i + 0.5) * step, 2), b) for i, b in enumerate(raw_fb)]
            if q_frames:
                qcands, _qmod, qtok = brain._find_quiet_visual_candidates(
                    q_frames, win, now, st["min_len"], st["max_len"], self.job["title"], self.job["uploader"], self._game()
                )
                self.tokens += qtok
                for qc in qcands[:1]:
                    is_dup = any(max(0.0, min(qc["end"], k["end"]) - max(qc["start"], k["start"])) >= 6.0 for k in self.job["clips"])
                    if not is_dup and qc.get("score", 0) >= max(65, st["min_score"] - 10):
                        qc.update(source="ai_auto", clip_type="ai_auto", priority="HIGH PRIORITY",
                                  detection_mode="MODE A (QUIET VISUAL)", analysis_mode="frames_and_transcript")
                        self._add_clip(qc)
                        self.checks += 1
                        return self._verdict(verdict, f"Quiet visual highlight: {qc.get('reason', '')[:70]}")
            self.skipped += 1
            return self._verdict(verdict, "Skipped: nobody talking")
        hourly_cap = st.get("live_per_hour", 25)
        if hourly_cap > 0 and len(recent) >= hourly_cap and not must and not why:
            self.skipped += 1
            return self._verdict(verdict, f"Hourly target reached ({len(recent)}/{hourly_cap} clips)")
        usage.set_context(self.job["creator"], self.job["title"] or "Live stream")
        title, up = self.job["title"], self.job["uploader"]
        try:
            cands, tok = brain.judge_transcript(win, ws, now, title, up, st["min_len"], st["max_len"], self.job["clips"],
                                                n=1 if every <= 2 else 2, must=must, game=self._game(),
                                                timeout=config.LIVE_AI_TIMEOUT)  # Auto (0) asks for one
        except Exception as e:  # noqa: BLE001
            self.job["ai"]["last_error"] = str(e)[-200:]
            return self._verdict(verdict, "AI error: " + str(e)[-80:])
        self.checks += 1
        self.tokens += tok
        keep = [c for c in cands if c["score"] >= (40 if must else st["min_score"])]
        verdict["transcript"] = max((c["score"] for c in cands), default=0)
        if not keep:
            return self._verdict(verdict, "Words judge: nothing clip-worthy")
        z = brain.loud_zscore(np.array(self.db, dtype=np.float32))
        lo, hi = int(ws), int(now) + 1
        people = self.chat_people()
        if people:
            chat = [len(people.get(t, ())) for t in range(lo, hi)]
            unit = "people"
        else:
            chat = [self.chat.get(t, 0) for t in range(lo, hi)] if (self.chat_on or self.chat_total) else None
            unit = "messages"
        try:
            sig, tok2 = brain.judge_signals(z[lo:hi], chat, lo, now, unit=unit, timeout=config.LIVE_AI_TIMEOUT)
            self.checks += 1
            self.tokens += tok2
        except Exception as e:  # noqa: BLE001
            sig = []
            self.job["ai"]["last_error"] = str(e)[-200:]
        added = 0
        for c in keep:
            frame_bytes = self._extract_window_frames(c["start"], c["end"], count=3) or None

            c_text = " ".join(w["w"] for w in win if c["start"] <= w["s"] <= c["end"])
            c_lo, c_hi = max(0, int(c["start"])), min(len(z), int(c["end"]) + 1)
            mm = brain.judge_multimodal_moment(
                c_text or win,
                z_scores=z[c_lo:c_hi],
                frame_bytes=frame_bytes,
                title=title,
                uploader=up,
                game=self._game(),
                chat=chat,
                timeout=config.LIVE_AI_TIMEOUT,
            )

            verdict["mm_score"] = mm.get("score")
            verdict["breakdown"] = mm.get("breakdown", "")
            # Strict quality check:
            if mm["priority"] == "SKIP" and not must:
                self.rejected += 1
                self._verdict(verdict, f"Multimodal judge: {mm['reason']}")
                continue

            match = [m for m in sig if m["end"] >= c["start"] - 10 and m["start"] <= c["end"] + 10 and m["score"] >= 50]
            rs = max((m["score"] for m in match), default=0)
            verdict["reaction"] = rs
            both = bool(match)
            is_funny = c.get("category") in ("funny", "fail") and c.get("score", 0) >= max(75, st["min_score"] - 5)
            ok = both or is_funny or (st["decide_mode"] == "either" and c["score"] >= st["min_score"]) or (must and added == 0) or (mm["priority"] == "HIGH PRIORITY")
            if not ok:
                self.rejected += 1
                self._verdict(verdict, "Reaction judge said no, not clipped")
                continue

            # Only skip if this candidate directly duplicates / overlaps an already created clip (> 8s or > 35%)
            is_dup = any(
                max(0.0, min(c["end"], k["end"]) - max(c["start"], k["start"])) >= min(8.0, 0.35 * (c["end"] - c["start"]))
                for k in self.job["clips"]
            )
            if is_dup:
                self._verdict(verdict, "Duplicate: overlaps previous clip")
                continue

            too_close = any(abs(c["start"] - k["start"]) < st.get("min_gap_min", 0) * 60 for k in self.job["clips"])
            ai_caught = both or is_funny or (mm["priority"] == "HIGH PRIORITY") or (c.get("score", 0) >= st["min_score"])

            # If AI caught a verified moment (both judges agreed or high score), ALWAYS clip it even if close to last clip!
            if too_close and not ai_caught:
                self._verdict(verdict, "Too close to the last clip")
                continue

            why = mm["reason"]
            if too_close and ai_caught:
                why += " (viral highlight)"
            c["source"] = "ai_auto"
            c["clip_type"] = "ai_auto"
            c["score"] = mm["score"]
            c["priority"] = mm["priority"]
            c["breakdown"] = mm["breakdown"]
            c["detection_mode"] = mm["mode"]
            c["signals"] = mm.get("signals")
            c["judges"] = {
                "mode": mm["mode"],
                "score": mm["score"],
                "priority": mm["priority"],
                "breakdown": mm["breakdown"],
                "why": why,
                "words": c.get("score", 0),
                "reaction": rs or None,
                "model": ai.last_active_model(),
            }
            c["reason"] = f"{c['reason']} [{mm['mode']}: {mm['breakdown']}]"
            # Golden Retention Alignment (Trigger in first 10-15s, 25-30s reaction afterwards, total ~40-42s)
            c_words = [w for w in win if c["start"] - 5.0 <= w["s"] <= c["end"] + 15.0]
            c_class = ohnepixel.classify_transcript(c_words, game=self._game()) if c_words else {}
            trigger_t = None
            if c_class.get("level1_matches"):
                m_pat = ohnepixel.normalize_text(c_class["level1_matches"][0]).split()
                w_norm = [self._normalize_trigger_text(w.get("w", "")) for w in c_words]
                for idx in range(len(w_norm) - len(m_pat) + 1):
                    if w_norm[idx:idx + len(m_pat)] == m_pat:
                        trigger_t = c_words[idx]["s"]
                        break

            if trigger_t is None and match:
                # Use reaction loudness peak from judge 2 (sig)
                trigger_t = float(match[0].get("start", c["start"] + 12.0))

            max_short = min(max(35.0, float(st.get("max_len") or 40.0)), 45.0)
            if trigger_t is not None:
                # Golden timeline: trigger at ~11s into clip, followed by 25-28s post-roll reaction (~36-40s Short)
                pre_r = 11.0
                post_r = max(20.0, min(28.0, max_short - pre_r))
                c["start"] = max(ws, round(trigger_t - pre_r, 2))
                c["end"] = min(now, round(trigger_t + post_r, 2))
                c["trigger_t"] = trigger_t
            else:
                # Expand short snippets cleanly into 32-40s Shorts window with reaction aftermath
                c_dur = c["end"] - c["start"]
                if c_dur < 32.0:
                    expand = min(min(40.0, max_short) - c_dur, 18.0)
                    c["start"] = max(ws, round(c["start"] - expand * 0.3, 2))
                    c["end"] = min(now, round(c["end"] + expand * 0.7, 2))
            if c["end"] - c["start"] > max_short:
                c["start"] = round(max(ws, c["end"] - max_short), 2)
            self._add_clip(c)
            self._verdict(verdict, f"Clipped ({mm['priority']}): " + why[:40])
            added += 1
            must = False
            if added >= (1 if every <= 2 else 2):
                break

    def _extract_window_frames(self, start_t: float, end_t: float, count: int = 3) -> list[bytes]:
        """Grab sequential JPEG frames from src_mp4 or live .ts buffer segments across [start_t, end_t]."""
        try:
            src_file = getattr(self, "src_mp4", None)
            if src_file and Path(src_file).is_file():
                frames = jobs.extract_clip_frames_bytes(Path(src_file), start_t, end_t, n_frames=count)
                if frames:
                    return frames
        except Exception:
            pass
        with self.lock:
            segs = [(p, s, e) for p, s, e in self.segments if e >= start_t - 1.0 and s <= end_t + 1.0]
        if not segs:
            return []
        dur = max(1.0, float(end_t) - float(start_t))
        ratios = [0.22, 0.55, 0.85] if count == 3 else [(i + 1) / (count + 1) for i in range(max(1, count))]
        out = []
        for r in ratios:
            t = float(start_t) + dur * r
            seg = next((x for x in segs if x[1] <= t <= x[2]), None) or min(segs, key=lambda x: abs(((x[1] + x[2]) / 2.0) - t))
            if seg[0].is_file():
                b = jobs._extract_frame_bytes(seg[0], max(0.0, t - seg[1]))
                if b:
                    out.append(b)
        return out

    def _verdict(self, v, result):
        d = dict(v, result=result)
        if "wall_t" not in d:
            d["wall_t"] = time.time()
        self.verdicts.append(d)
        del self.verdicts[:-30]

    @staticmethod
    def _normalize_trigger_text(text: str) -> str:
        """Normalizes speech transcript and creator trigger phrases for rock-solid Roman Urdu & English matching."""
        t = (text or "").lower()
        t = re.sub(r"[’‘´`]", "'", t)
        t = re.sub(r"\byeh\b", "ye", t)
        t = re.sub(r"\bis ko\b", "isko", t)
        t = re.sub(r"\bus ko\b", "usko", t)
        t = re.sub(r"\bkr\b", "kar", t)
        t = re.sub(r"\bkro\b", "karo", t)
        t = re.sub(r"\bkardo\b", "karo", t)
        t = re.sub(r"\bkarde\b", "karo", t)
        t = re.sub(r"\bkar do\b", "karo", t)
        t = re.sub(r"\bkar de\b", "karo", t)
        t = re.sub(r"\bkrlo\b", "karo", t)
        t = re.sub(r"\bkr do\b", "karo", t)
        t = re.sub(r"[^\w\s']", " ", t)
        return re.sub(r"\s+", " ", t).strip()

    CLIP_WORDS = re.compile(r"\b(clip(\s+(it|that|this|karo))?|(ye|yeh)\s+clip(\s+karo)?)\b", re.I)
    SAID_BEFORE, SAID_AFTER, SAID_GAP = 60, 15, 30

    def _triggers(self, new_words):
        """Built in: when someone says "clip" ("clip it", "clip that"), the AI looks at that moment as soon as its
        transcript is ready; people say it right after something worth clipping. Then the creator's own trigger
        phrases from Setup, which clip straight away with no AI check."""
        if not new_words:
            return

        # STRICT PURE-AI BYPASS: If creator has empty trigger_words, bypass ALL keyword/phrase triggers!
        has_triggers = bool(str(self.settings.get("trigger_words", "")).strip())
        if not has_triggers:
            return

        # Use a rolling window of recent words to eliminate chunk boundary splits
        window_words = self.words[-50:] if len(self.words) >= 50 else list(self.words)
        if not window_words:
            return

        earliest_new = new_words[0]["s"]

        # 1. Built-in "clip" trigger detection across rolling window
        if not self.said and (window_words[-1]["s"] - self.last_said > self.SAID_GAP):
            norm_tokens = [self._normalize_trigger_text(w.get("w", "")) for w in window_words]
            for i, w in enumerate(window_words):
                if w["s"] < earliest_new - 5.0:
                    continue
                # Check 1-word, 2-word, 3-word combinations starting at i
                for n_tok in (1, 2, 3):
                    if i + n_tok <= len(norm_tokens):
                        phrase_cand = " ".join(norm_tokens[i:i + n_tok])
                        if self.CLIP_WORDS.search(phrase_cand):
                            if w["s"] - self.last_said > self.SAID_GAP and not self.said:
                                self.said = {"t": w["s"], "why": f'Someone said "{phrase_cand}"'}
                                self.last_said = w["s"]
                                break
                if self.said:
                    break

        # 2. Intelligent Reaction Phrase Discovery (ohnePixel + creators using default MASTER_TRIGGER_WORDS pack)
        creator_val = str(self.job.get("creator") or "").lower()
        uploader_val = str(self.job.get("uploader") or "").lower()
        channel_val = str(getattr(self, "channel", "") or "").lower()
        is_ohnepixel = "ohnepixel" in creator_val or "ohnepixel" in uploader_val or "ohnepixel" in channel_val
        is_master_pack = str(self.settings.get("trigger_words", "")).strip() == creators.MASTER_TRIGGER_WORDS.strip()

        # Golden Retention Timeline: trigger occurs within first 10-15s (target 12s), followed by 25-30s reaction
        pre_roll, post_roll = 12.0, 28.0

        if is_ohnepixel or is_master_pack:
            g = self._game()
            c_class = ohnepixel.classify_transcript(window_words, game=g)

            # Level 1 strong reaction phrase detection (Continuous Moment Discovery)
            if c_class.get("tier") == 1 and c_class.get("level1_matches"):
                matched_p = c_class["level1_matches"][0]
                match_t = window_words[-1]["s"]
                norm_pat = ohnepixel.normalize_text(matched_p).split()
                plen = len(norm_pat)
                words_n = [self._normalize_trigger_text(w.get("w", "")) for w in window_words]
                for idx in range(len(words_n) - plen + 1):
                    if words_n[idx:idx + plen] == norm_pat:
                        match_t = window_words[idx]["s"]
                        break

                if match_t >= earliest_new - 8.0:
                    max_short = min(max(35.0, float(self.settings.get("max_len") or 40.0)), 45.0)
                    # Merge overlapping triggers within 15 seconds while keeping YouTube Short length (<= 40-45s)
                    if match_t - self.last_trigger <= 15.0 and self.manual:
                        self.manual[-1]["end"] = max(self.manual[-1]["end"], match_t + post_roll)
                        if self.manual[-1]["end"] - self.manual[-1]["start"] > max_short:
                            self.manual[-1]["start"] = max(0.0, self.manual[-1]["end"] - max_short)
                        self.last_trigger = match_t
                    elif match_t - self.last_trigger > 15.0:
                        self.last_trigger = match_t
                        s = max(0.0, match_t - pre_roll)
                        e = match_t + post_roll
                        self.manual.append({
                            "start": s, "end": e,
                            "why": f'"{matched_p}"',
                            "tier": 1,
                            "trigger_type": "reaction_phrase",
                            "source": "trigger",
                            "trigger_word": matched_p,
                            "trigger_t": match_t,
                        })
                    return

        # 3. Creator's custom trigger phrases
        raw_phrases = [p.strip() for p in self.settings.get("trigger_words", "").split(",") if p.strip()]
        if not raw_phrases:
            return

        norm_phrases = []
        for rp in raw_phrases:
            np_text = self._normalize_trigger_text(rp)
            parts = np_text.split()
            if not parts:
                continue
            # Single common words should NEVER trigger auto-clips directly without multimodal validation
            if len(parts) == 1 and (parts[0] in ohnepixel.COMMON_WORDS or len(parts[0]) < 4):
                continue
            if len(np_text) >= 3:
                norm_phrases.append((rp, np_text, parts))

        if not norm_phrases:
            return

        words_norm = [self._normalize_trigger_text(w.get("w", "")) for w in window_words]
        words_no_apos = [w.replace("'", "") for w in words_norm]

        for orig_p, np_text, parts in norm_phrases:
            parts_no_apos = [p.replace("'", "") for p in parts]
            plen = len(parts)
            for i in range(len(words_norm) - plen + 1):
                window = words_norm[i:i + plen]
                window_no_apos = words_no_apos[i:i + plen]
                if window == parts or window_no_apos == parts_no_apos:
                    t = window_words[i]["s"]
                    if t >= earliest_new - 6.0:
                        # Candidate merging if within 15s while keeping YouTube Short length (<= 40-45s)
                        max_short = min(max(35.0, float(self.settings.get("max_len") or 40.0)), 45.0)
                        if t - self.last_trigger <= 15.0 and self.manual:
                            self.manual[-1]["end"] = max(self.manual[-1]["end"], t + post_roll)
                            if self.manual[-1]["end"] - self.manual[-1]["start"] > max_short:
                                self.manual[-1]["start"] = max(0.0, self.manual[-1]["end"] - max_short)
                            self.last_trigger = t
                        elif t - self.last_trigger > 20.0:
                            self.last_trigger = t
                            self.manual.append({
                                "start": max(0.0, t - pre_roll),
                                "end": t + post_roll,
                                "why": f'"{orig_p}"',
                                "tier": 2,
                                "trigger_type": "custom_phrase",
                                "source": "trigger",
                                "trigger_word": orig_p,
                                "trigger_t": t,
                            })

    def _manual_step(self):
        ready = []
        for m in self.manual:
            is_btn = m.get("source") == "manual" or (m.get("trigger_type") in (None, "manual") and m.get("why") in (None, "Hand", "Hand clip"))
            vid_ready = m["end"] <= (self.seg_clock or (self.samples / SR))
            if self.ended or (vid_ready if is_btn else m["end"] <= self.t_done):
                ready.append(m)
        for req in ready:
            text = " ".join(w["w"] for w in self.words if req["start"] <= w["s"] <= req["end"])
            usage.set_context(self.job["creator"], self.job["title"] or "Live stream")

            # Extract sequential video frames for true multimodal evaluation
            fbytes = self._extract_window_frames(req["start"], req["end"], count=3) or None

            # Audio z-score slice & chat
            lo = max(0, int(req["start"]))
            hi = min(len(self.db), int(req["end"]) + 1)
            z = brain.loud_zscore(np.array(self.db, dtype=np.float32)) if len(self.db) > 10 else []
            z_slice = z[lo:hi] if len(z) >= hi else []
            chat_slice = [self.chat.get(t, 0) for t in range(lo, hi)] if (self.chat_on or self.chat_total) else None

            # Run multimodal intelligent scoring (Mode A or Mode B fallback)
            mm = brain.judge_multimodal_moment(
                text,
                z_scores=z_slice,
                frame_bytes=fbytes,
                title=self.job["title"],
                uploader=self.job["uploader"],
                game=self._game(),
                chat=chat_slice,
                timeout=config.LIVE_AI_TIMEOUT,
            )

            # False-positive guardrail:
            # If not an explicit UI button click ("Clip last 30s") and priority is SKIP:
            is_button = req.get("source") == "manual" or (req.get("trigger_type") in (None, "manual") and req.get("why") in (None, "Hand", "Hand clip"))
            if not is_button and mm["priority"] == "SKIP":
                self.manual.remove(req)
                verdict = {"t": round(req["end"]), "wall_t": time.time(), "transcript": mm["score"], "reaction": None,
                           "trigger": req.get("why"), "model": ai.last_active_model()}
                self._verdict(verdict, f"Skipped: {mm['reason']}")
                continue

            try:
                if fbytes:
                    c = brain.describe_multimodal(fbytes, text=text, title=self.job["title"], uploader=self.job["uploader"],
                                                  game=self._game(), timeout=config.LIVE_AI_TIMEOUT)
                else:
                    c = brain.describe(text, self.job["title"], self.job["uploader"], game=self._game(),
                                       timeout=config.LIVE_AI_TIMEOUT)
            except Exception as e:  # noqa: BLE001
                self.job["ai"]["last_error"] = str(e)[-200:]
                c = {"score": mm["score"], "category": "other", "hook": "", "title": self.job["title"],
                     "description": "", "hashtags": [], "highlight_words": []}

            self.manual.remove(req)
            c_start = round(req["start"], 2)
            c_end = round(min(req["end"], self.samples / SR), 2)
            if not is_button:
                max_short = min(max(35.0, float(self.settings.get("max_len") or 40.0)), 45.0)
                if c_end - c_start > max_short:
                    c_start = round(max(0.0, c_end - max_short), 2)
            c.update(
                start=c_start,
                end=c_end,
                score=mm.get("score", 70),
                priority=mm.get("priority", "HIGH PRIORITY"),
                breakdown=mm.get("breakdown") or {},
                detection_mode=mm.get("mode", "MODE B (KEYWORD FALLBACK)"),
                signals=mm.get("signals"),
            )
            c["judges"] = {
                "mode": mm.get("mode", "MODE B (KEYWORD FALLBACK)"),
                "score": mm.get("score", 70),
                "priority": mm.get("priority", "HIGH PRIORITY"),
                "breakdown": mm.get("breakdown") or {},
                "why": mm.get("reason", ""),
                "model": ai.last_active_model(),
            }
            if is_button:
                c["source"] = "manual"
                c["clip_type"] = "manual"
                c["trigger_label"] = "Hand clip"
                c["reason"] = f"Manually clipped by you ({mm['reason']})"
            elif req.get("source") == "trigger" or req.get("trigger_type") in ("reaction_phrase", "custom_phrase"):
                c["source"] = "trigger"
                c["clip_type"] = "trigger"
                trig_w = req.get("trigger_word") or (req.get("why") or "").replace('"', '').strip()
                c["trigger_word"] = trig_w
                c["trigger_label"] = req.get("why") or f'"{trig_w}"'
                c["trigger_phrase"] = trig_w
                c["reason"] = f'Triggered by "{trig_w}" — {mm["reason"]}'
            elif req.get("why"):
                c["trigger_label"] = req["why"]
                c["reason"] = f"{req['why']} — {mm['reason']}"
            else:
                c["source"] = "manual"
                c["reason"] = mm["reason"]

            if "trigger_t" in req:
                c["trigger_t"] = req["trigger_t"]

            self._add_clip(c)

    def _add_clip(self, c):
        self.n += 1
        gname = games.name_of(self._game()) or "GTA 6"
        gname_tag = "".join(ch for ch in gname if ch.isalnum())
        streamer = self.job.get("uploader") or "Streamer"
        if not c.get("title") or not str(c.get("title")).strip():
            c["title"] = f"🔴 {streamer} {gname} Insane Moment! 😂"[:70]
        if not c.get("hook") or not str(c.get("hook")).strip():
            c["hook"] = "WAIT FOR IT"
        if not c.get("description") or not str(c.get("description")).strip():
            c["description"] = f"Unbelievable {gname} moment with {streamer}! Watch till the end. #Shorts #{gname_tag}"
        if not c.get("seo_title") or not str(c.get("seo_title")).strip():
            c["seo_title"] = f"{c['title']} #Shorts"[:100].strip()
        if not c.get("seo_tags") or not len(c.get("seo_tags", [])):
            c["seo_tags"] = [t for t in games.tags_of(self._game())] + [gname.lower(), f"{gname.lower()} gameplay", streamer.lower(), "shorts", "gaming", "viral", "funny moments"]
        if not c.get("pinned_comment") or not str(c.get("pinned_comment")).strip():
            c["pinned_comment"] = f"What stood out most in this {gname} moment?"
        c.setdefault("payoff_at", round(float(c.get("start", 0.0)) + max(1.0, float(c.get("end", 30.0)) - float(c.get("start", 0.0))) * 0.65, 2))
        c.setdefault("analysis_mode", "frames_and_transcript" if c.get("detection_mode", "").startswith("MODE A") else "transcript_only")
        c.setdefault("community_text", brain.build_community_post(
            c.get("seo_title") or c.get("title") or "",
            c.get("description") or "",
            c.get("pinned_comment") or "",
            c.get("hashtags") or [],
        ))
        facecam_delay = float(self.settings.get("facecam_delay") or self.job.get("options", {}).get("facecam_delay") or 0.0)
        audio_delay = float(self.settings.get("audio_delay") if self.settings.get("audio_delay") is not None else (self.job.get("options", {}).get("audio_delay") if self.job.get("options", {}).get("audio_delay") is not None else 0.0))
        facecam_pos = self.settings.get("facecam_pos") or self.job.get("options", {}).get("facecam_pos") or "top-right"
        hook_style = self.settings.get("hook_style") or self.job.get("options", {}).get("hook_style") or "neon"
        outro_cta = self.settings.get("outro_cta", self.job.get("options", {}).get("outro_cta", True))
        outro_text = self.settings.get("outro_text") or self.job.get("options", {}).get("outro_text")
        streamer_only = bool(self.settings.get("streamer_only_captions", self.job.get("options", {}).get("streamer_only_captions", False)))
        # Respect creator setting first, then fallback to job options
        caps = self.settings.get("captions")
        if caps is None:
            caps = self.job.get("options", {}).get("captions", True)
        cl_opt = self.settings.get("custom_layout") or self.job.get("options", {}).get("custom_layout")
        c.update(id=f"clip{self.n:03d}",
                 style=self.settings.get("style", self.job.get("options", {}).get("style", "bounce")),
                 layout=self.settings.get("layout", self.job.get("options", {}).get("layout", "split")),
                 captions=bool(caps),
                 status="queued", version=0, made_at=time.time(),
                 facecam_pos=facecam_pos, facecam_delay=facecam_delay, audio_delay=audio_delay,
                 hook_style=hook_style, outro_cta=outro_cta, outro_text=outro_text,
                 streamer_only_captions=streamer_only)
        if cl_opt:
            c["custom_layout"] = cl_opt
        if self.settings.get("active_preset"):
            c["active_preset"] = self.settings["active_preset"]
        if self.job.get("options", {}).get("hook_text"):      # the person's own big text, in place of the AI's
            c["hook"] = self.job["options"]["hook_text"]
        if self.job.get("options", {}).get("description_text"):
            c["description"], c["fixed_description"] = self.job["options"]["description_text"], True
        else:
            hashtags.apply(c, self.words, self.job.get("title", ""), self.job.get("uploader", ""), self._game())
        with self.lock:
            self.job["clips"].append(c)
        jobs.save(self.job)
        jobs.submit_live(lambda: self._render(c))

    def _render(self, clip):
        """Runs on the render worker: copy the needed buffer pieces, then make the clip."""
        # The picture comes a few seconds behind the sound, and after a hiccup on the stream it can be a
        # minute behind. Wait for it while it is still being written: a clip is never cut down to a stub.
        began, moved_at = time.time(), time.time()
        with self.lock:
            seen = self.seg_clock
        while time.time() - began < 150:
            self._scan_segments()
            if self.ended or (self.segments and self.segments[-1][2] >= clip["end"] + 1):
                break
            with self.lock:
                clock = self.seg_clock
            if clock > seen + 0.5:
                moved_at, seen = time.time(), clock       # the picture is still arriving: it will get there
            elif time.time() - moved_at > 20:
                break               # the picture has stopped arriving: waiting will not help
            time.sleep(1)
        with self.lock:
            segs = [s for s in self.segments if s[2] > clip["start"] - PAD and s[1] < clip["end"] + PAD and s[0].exists()]
        if not segs or segs[-1][2] < clip["start"]:
            clip.update(status="error", error="That part of the stream is no longer in the buffer.")
            jobs.save(self.job)
            return
        if any(b[1] > a[2] + 2 for a, b in zip(segs, segs[1:])):
            # Pieces are missing in the middle: the clip would come out short, with its captions early.
            clip.update(status="error", error="That part of the stream was not recorded: the recording dropped out there.")
            jobs.save(self.job)
            return
        if clip["start"] < segs[0][1]:
            clip["start"] = segs[0][1]
        if clip["end"] > segs[-1][2]:
            clip["end"] = segs[-1][2]
        if "width" not in self.job:
            meta = media.probe(segs[0][0])
            self.job.update(width=meta["width"], height=meta["height"])
        lst = self.dir / "clips" / f"{clip['id']}.txt"
        lst.write_text("".join(f"file '{s[0].as_posix()}'\n" for s in segs), encoding="utf-8")
        src = self.dir / "clips" / f"{clip['id']}.src.mp4"
        try:
            # Remux directly to MP4 with exact sample tables and zero packet clock drift
            media.run(["ffmpeg", "-y", "-v", "error", "-fflags", "+genpts", "-f", "concat", "-safe", "0", "-i", str(lst),
                       "-c", "copy", "-movflags", "+faststart", "-avoid_negative_ts", "make_zero", str(src)])
        except Exception:
            # Fallback to .ts if direct mp4 copy is not supported by source codec
            src_ts = self.dir / "clips" / f"{clip['id']}.src.ts"
            try:
                media.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                           "-c", "copy", str(src_ts)])
                src = src_ts
            except Exception as e:  # noqa: BLE001
                clip.update(status="error", error=media_safe(e))
                jobs.save(self.job)
                return
        finally:
            lst.unlink(missing_ok=True)
        # Detect and skip commercial breaks or static slates (e.g. Twitch "Commercial break in progress"):
        dur = segs[-1][2] - segs[0][1]
        try:
            statics = quality.static_ranges(src, bucket=1.5)
            if statics and quality.static_overlap(0, dur, statics) > (dur * 0.40):
                clip.update(status="error", error="Skipped: this moment was during a commercial break or static screen.")
                jobs.save(self.job)
                return
        except Exception:
            pass

        # Layouts that use webcam: gameplay, split, split_half
        if clip.get("layout") in ("gameplay", "split", "split_half"):
            if not self.facecam_box:
                self.facecam_box = self._find_facecam(src)
            if self.facecam_box:
                clip["facecam"] = self.facecam_box
        heard_src = []
        offset = self._align(src, segs[0][1] + self.clock_fix, dur, heard_out=heard_src)
        self.clock_fix = offset - segs[0][1]  # the two clocks drift ~4 s an hour; start the next clip from here
        src_offset, src_end = round(offset, 2), round(offset + dur, 2)
        span = _clip_span(clip, src_offset, src_end)
        if span is None:
            # The end of the moment is not in the recorded picture: the picture can stop for a while on a
            # stream hiccup, and everything said meanwhile sits on the sound clock only. Cutting what is
            # there would make a clip that stops before its payoff, so this one is not made at all.
            src.unlink(missing_ok=True)
            clip.update(status="error", error="That part of the stream was not recorded: the picture stopped "
                                              "before the end of it.")
            jobs.save(self.job)
            return
        clip.update(src=str(src), src_offset=src_offset, src_end=src_end)
        clip["start"], clip["end"] = span
        if heard_src:
            a_s, b_s = clip["start"] - 0.5, clip["end"] + 0.5
            aligned_slice = [
                dict(w, s=round(w["s"] + src_offset, 2), e=round(w["e"] + src_offset, 2))
                for w in heard_src
                if a_s <= (w["s"] + src_offset) <= b_s
            ]
            if aligned_slice:
                clip["_aligned_words"] = aligned_slice
        jobs.render_one(self.job, clip, list(self.words))

    def _align(self, src, guess, dur, heard_out=None):
        """Where `src` really starts on the transcript clock. The video pieces and the audio feed keep separate
        clocks that drift apart, so transcribe the clip's own audio and line its words up with the live words.
        Local speech model only: no AI calls."""
        key = lambda w: _plain(w).replace("'", "")
        clip_pcm = None
        wav = src.with_suffix(".wav")
        try:
            try:
                media.extract_audio(src, wav)
                clip_pcm = media.load_audio(wav)
            finally:
                wav.unlink(missing_ok=True)
            heard = transcribe.transcribe(clip_pcm, lang=self.job.get("lang") or "en")
            if heard_out is not None and heard:
                heard_out[:] = heard
            with self.lock:
                near = [w for w in self.words if guess - 15 <= w["s"] <= guess + dur + 15]
            diffs = []
            for h in heard:
                k = key(h["w"])
                if len(k) < 3:
                    continue
                m = [w["s"] for w in near if key(w["w"]) == k and abs(w["s"] - (guess + h["s"])) < 8]
                if m:
                    diffs.append(min(m, key=lambda s: abs(s - (guess + h["s"]))) - h["s"])
            if len(diffs) >= 4 or (len(diffs) >= 2 and (max(diffs) - min(diffs)) < 0.5):
                return float(np.median(diffs))
        except Exception:  # noqa: BLE001 - fall back to waveform correlation
            pass

        # Sub-frame audio waveform cross-correlation fallback:
        # If words were not matched (e.g. non-English speech, laughter, background game noise, or silence),
        # cross-correlate clip audio with the live stream audio buffer for millisecond-exact alignment.
        if clip_pcm is not None and len(clip_pcm) >= 16000:
            try:
                ds_rate = 8
                target_ds = 2000
                clip_ds = np.array(clip_pcm[:16000 * 5:ds_rate], dtype=np.float32)
                with self.lock:
                    total_ds = len(self.audio_downsampled)
                    cur_samples = self.samples
                    ds_copy = list(self.audio_downsampled)
                if total_ds > target_ds * 10 and len(clip_ds) >= target_ds * 2:
                    stream_elapsed = cur_samples / SR
                    ds_start_sec = max(0.0, stream_elapsed - (total_ds / target_ds))
                    win_start_sec = max(ds_start_sec, guess - 10.0)
                    win_end_sec = min(stream_elapsed, guess + 10.0 + len(clip_ds) / target_ds)
                    idx_start = int((win_start_sec - ds_start_sec) * target_ds)
                    idx_end = int((win_end_sec - ds_start_sec) * target_ds)
                    buf_slice = np.array(ds_copy[idx_start:idx_end], dtype=np.float32)
                    if len(buf_slice) > len(clip_ds):
                        corr = np.correlate(buf_slice, clip_ds, mode="valid")
                        best_local_idx = int(np.argmax(corr))
                        best_offset_sec = win_start_sec + (best_local_idx / target_ds)
                        return float(round(best_offset_sec, 3))
            except Exception:
                pass

        return guess

    def clip_last(self, seconds):
        end = self.samples / SR
        if self.seg_clock and self.seg_clock < end:
            end = self.seg_clock        # the picture has not caught up with the sound: clip what was recorded
        if end < 5:
            raise ValueError("Nothing has been recorded yet.")
        self.manual.append({
            "start": max(0.0, end - seconds),
            "end": end,
        })
        self._verdict({"t": round(end), "wall_t": time.time(), "transcript": round(seconds),
                       "reaction": None, "trigger": "Hand clip", "model": ai.last_active_model()},
                      f"✂️ Manual clip queued: cutting last {round(seconds)}s now…")

    def _publish(self):
        elapsed = self.samples / SR
        lines = brain.make_lines([w for w in self.words if w["s"] >= self.t_done - 45])[-5:]
        with self.lock:
            sec = int(elapsed)
            self.job.update(
                duration=elapsed,
                live={"elapsed": round(elapsed), "buffer_sec": round(self.segments[-1][2] - self.segments[0][1]) if self.segments else 0,
                      "lines": [l["text"] for l in lines], "level": [round(x) for x in self.db[-60:]],
                      "chat": [self.chat.get(t, 0) for t in range(max(0, sec - 60), sec)] if self.chat_on or self.chat_total else None,
                      "recent_chat": list(self.recent_chat_msgs),
                      "channel": getattr(self, "channel", None),
                      "checks": self.checks, "skipped": self.skipped, "tokens": self.tokens, "words": len(self.words),
                      "rejected": self.rejected, "verdicts": list(reversed(self.verdicts)),
                      "every_min": int(self.settings.get("ai_every_min", 3)) or 3,
                      "auto": None,
                      "started_at": self.started_at,
                      "detection_mode": self.active_detection_mode(),
                      "model": ai.last_active_model(),
                      "pending_clips": len(self.manual)})
        jobs.save(self.job)

    def _analyze(self):
        cid = self.job["creator"]
        started = False
        while True:
            busy = False
            try:
                if not self.user_stopped and not self.ended:      # a recording cannot run for ever
                    if time.time() - self.started_at > config.MAX_LIVE_HOURS * 3600:
                        self.stop(f"Stopped after {config.MAX_LIVE_HOURS:g} hours, the longest one recording can run")
                self._scan_segments()
                busy = self._transcribe_step()
                if not started and self.samples:
                    started = True
                    self.job.update(status="live", stage="Recording")
                    creators.log(cid, f"Recording started: {self.job['title']}")
                self._manual_step()
                # Three ways the AI is asked: on the creator's schedule (every N minutes), and always, when the
                # stream suddenly gets louder or chat busier, or when someone says "clip".
                every = int(self.settings.get("ai_every_min", 3)) or 3
                self._watch_spikes()
                sp, said = self.spike, self.said
                if self.user_stopped:
                    pass
                elif said and (self.t_done >= said["t"] + self.SAID_AFTER or (self.ended and not busy)):
                    self.said = None
                    self._ask_ai((said["t"] - self.SAID_BEFORE, said["t"] + self.SAID_AFTER), said["why"])
                elif sp and (self.t_done >= sp["t"] + self.AUTO_AFTER or (self.ended and not busy)):
                    self.spike = None
                    self._ask_ai((sp["t"] - self.AUTO_BEFORE, sp["t"] + self.AUTO_AFTER), "Jump: " + sp["why"])
                elif self.t_done - self.last_check >= every * 60 or (self.ended and not busy and self.t_done > self.last_check):
                    self._ask_ai()
                self._publish()
            except Exception as e:  # noqa: BLE001
                self.job["ai"]["last_error"] = str(e)[-200:]
            # Leaving here must not happen while an AI check is still running: it may still be adding a
            # clip, and cleanup() deletes the buffer that clip is cut from. That is true after a stop as
            # well as at the end of a stream, so both wait for it. Stopping is still instant on the page:
            # stop() has already written the status.
            if ((self.user_stopped and not self.manual and not self.ai_busy)
                    or (self.ended and not busy and not self.ai_busy
                        and len(self.pending) < SR * 2 and not self.manual)):
                break
            if not busy:
                time.sleep(2)
        failed = bool(self.job.get("error")) and not started
        self.job.update(status="error" if failed else "done", stage="Could not record" if failed else self.end_note)
        jobs.save(self.job)
        creators.log(cid, f"Recording finished ({self.end_note.lower()}): {len(self.job['clips'])} clips, "
                          f"{round(self.samples / SR / 60)} min" if not failed else f"Recording failed: {self.job['error']}")

        if failed:
            alerts.notify(f"recording failed for {self.job['source']['name']}: {self.job['error']}")
        else:
            alerts.notify(f"recording finished for {self.job['source']['name']}: {len(self.job['clips'])} clips, "
                          f"{round(self.samples / SR / 60)} min.")

        def cleanup():  # runs after any queued renders, then frees the buffer
            for f in self.buf.glob("*"):
                f.unlink(missing_ok=True)
            self.finished = True
            SESSIONS.pop(self.job["id"], None)

        jobs.submit_live(cleanup)


def _clip_span(clip, src_offset, src_end):
    """The part of a clip the recorded picture really holds, or None when the end of it was never recorded.

    The clip's own times are on the transcript clock; the source file starts at `src_offset` and covers up to
    `src_end`. A second of give is allowed at the edges, because the picture stops between two frames."""
    if clip["end"] > src_end + 1:
        return None
    return max(clip["start"], src_offset), min(clip["end"], src_end)


def _pieces_on_disk(s):
    """Every piece still on disk, put back at its real time in the stream. Used after a restart, when the
    running clock is gone and only ffmpeg's own lists are left to go by."""
    s.part = len(list(s.buf.glob("p*.csv")))
    s.seg_clock = 0.0
    s.csv_seen = {}
    with s.lock:
        for i in range(1, s.part + 1):
            f = s.buf / f"p{i:02d}.csv"
            if not f.exists():
                continue
            rows = [r.split(",") for r in f.read_text(encoding="utf-8", errors="ignore").splitlines() if r.count(",") >= 2]
            base = 0.0                  # the first part's list starts at the start of the recording
            if i > 1 and rows:
                try:
                    if float(rows[0][1]) < s.seg_clock - 5:
                        base = s.seg_clock       # this part's list begins again at zero
                except ValueError:
                    pass
            for name, a, b in (r[:3] for r in rows):
                try:
                    start, end = base + float(a), base + float(b)
                except ValueError:
                    continue
                if end <= start:
                    continue
                s.segments.append((s.buf / name, start, end))
                s.listed.add(name)
                s.seg_clock = max(s.seg_clock, end)
            s.csv_seen[i] = len(rows)


def recover(job):
    """After a restart: finish the clips of an interrupted recording from the stream pieces still on disk."""
    c = creators.get(job["creator"]) or dict(creators.DEFAULTS)
    s = Session(job, c)
    s.ended, s.end_note = True, "Recording stopped when the studio closed"
    _pieces_on_disk(s)
    try:
        s.words = json.loads((s.dir / "words.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        s.words = []
    s.n = len(job["clips"])
    todo = [k for k in job["clips"] if k.get("status") == "queued"]
    for k in todo:
        jobs.submit_live(lambda k=k: s._render(k))

    def cleanup():
        for f in s.buf.glob("*"):
            f.unlink(missing_ok=True)
        job.pop("recover", None)
        jobs.save(job)
        creators.log(job["creator"], f"Finished {len(todo)} clip(s) from a recording interrupted by a restart")

    jobs.submit_live(cleanup)


def _plain(word: str) -> str:
    """A word reduced to its letters and digits, in any alphabet (no Arabic vowel marks), for matching words up."""
    return re.sub(r"[^\w']|_", "", transcribe.ARABIC_MARKS.sub("", word.lower()))


def start_session(creator: dict, url=None) -> dict:
    url = normalize(url or creator.get("channel") or "")
    if not re.match(r"^https?://[^/]+\.[^/]+/", url + "/"):
        raise ValueError("Add this creator's channel link first.")
    if active_for(creator["id"]):
        raise ValueError("This creator is already being recorded.")
    if not media.site_allowed(url):
        raise ValueError("Channel links must be from YouTube, Twitch or Kick.")
    if media.is_youtube(url) and media.youtube_paused():
        raise ValueError(media.YT_BLOCKED.replace("download videos", "record YouTube streams")
                         .replace("Upload the video file instead, or use a Twitch or Kick link. YouTube links",
                                  "Twitch and Kick streams still work. YouTube"))
    if len(active_mine()) >= config.MAX_LIVE_PER_USER:
        raise ValueError(f"You're already recording {len(active_mine())} streams, the most this server allows at once. Stop one first.")
    if len(active()) >= config.MAX_LIVE_TOTAL or (active() and load.busy()):
        raise ValueError("PeakCut is recording as many streams as it can right now. Try again in a little while.")
    from . import fetch_model, tools
    if tools.missing():
        raise ValueError(tools.HELP)
    lang = creator.get("lang") if fetch_model.known(creator.get("lang")) else fetch_model.DEFAULT
    if lang != fetch_model.DEFAULT and not transcribe.REMOTE and not fetch_model.ready(lang):
        raise ValueError(f"This creator speaks {fetch_model.label(lang)}, and its speech model isn't on this computer "
                         "yet. Add it in Settings → Speech models (an admin can do this), then start recording again.")
    job_opts = {k: creator[k] for k in ("style", "layout", "captions", "streamer_only_captions", "quality", "audio_delay", "facecam_delay",
                                         "facecam_pos", "hook_style", "outro_cta", "outro_text", "custom_layout") if k in creator}
    job = jobs.create({"type": "live", "url": url, "name": f"{creator['name']} live"}, job_opts, enqueue=False,
                      creator=creator["id"], kind="live")
    job.update(status="live", stage="Connecting to the stream", lang=lang)
    jobs.save(job)
    Session(job, creator).start()
    return job


def _watch_user(uid):
    """Start recording any of this user's auto-record creators who have gone live."""
    from . import profiles
    with ctx.as_user(uid):
        try:
            todo = [c for c in creators.all_creators() if c["auto_watch"] and c["channel"]]
            if not todo:
                return
        except Exception:  # noqa: BLE001
            return
        for c in todo:
            _watch_one(c)


def check_now(cid):
    """Auto-record was just turned on: look now, on a thread, instead of waiting for the next round."""
    uid = ctx.uid()

    def run():
        from . import profiles
        with ctx.as_user(uid):
            c = creators.get(cid)
            if not c or not c["auto_watch"] or not c["channel"]:
                return
            for url in c.get("channels", {}).values():
                profiles._live.pop(url.rstrip("/").lower(), None)     # a fresh answer, not one from two minutes ago
            _watch_one(c)
            profiles.refresh(cid, force=True)
    threading.Thread(target=run, daemon=True).start()


def _watch_one(c):
    """Start recording this auto-record creator if they are live on any of their channels."""
    from . import profiles
    try:
        if active_for(c["id"]) or len(active_mine()) >= config.MAX_LIVE_PER_USER or len(active()) >= config.MAX_LIVE_TOTAL or (active() and load.busy()):
            return
        # the chosen channel first, then their other platforms
        urls = [c["channel"]] + [u for u in c.get("channels", {}).values() if u != c["channel"]]
        for url in urls:
            # one shared "are they live?" answer per channel, however many people follow it
            if not profiles.live_shared(profiles.platform_of(url), url).get("live"):
                continue
            if media.is_youtube(url):
                # check YouTube will hand over the stream before making a recording that could only fail
                if media.youtube_paused():
                    continue
                try:
                    resolve(normalize(url))
                except NotLive:
                    continue
            start_session(c, url)
            where = creators.platform_key(url).title()
            creators.log(c["id"], f"Went live on {where}: recording started automatically")
            alerts.notify(f"{c['name']} went live on {where}, recording started.")
            break
    except NotLive:
        pass
    except Exception as e:  # noqa: BLE001
        creators.log(c["id"], f"Auto-record check failed: {str(e)[-150:]}")


def watch_loop():
    """Every two minutes, start recording any creator set to auto-record who has gone live. Covers every user,
    several at a time, so the round stays short however many accounts there are."""
    from concurrent.futures import ThreadPoolExecutor
    time.sleep(20)
    pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="watch")
    while True:
        t0 = time.time()
        try:
            list(pool.map(_watch_user, auth.user_ids()))
        except Exception:  # noqa: BLE001
            pass
        time.sleep(max(15, 120 - (time.time() - t0)))


def _resume_recordings(paused):
    """Recordings that were running when the server stopped: start recording the same channel again, if the
    stream is still on. Tried for a few minutes, since the server may come back a little before the network."""
    time.sleep(10)
    for _ in range(6):
        left = []
        for uid, cid, url in paused:
            with ctx.as_user(uid):
                try:
                    c = creators.get(cid)
                    if not c or active_for(cid):
                        continue
                    resolve(normalize(url))      # raises NotLive if the stream has ended: no empty recording is made
                    start_session(c, url)
                    creators.log(cid, "Recording picked up again after a server update")
                except NotLive:
                    continue                  # the stream ended while the server was away
                except Exception:  # noqa: BLE001 - try again shortly
                    left.append((uid, cid, url))
        if not left:
            return
        paused = left
        time.sleep(30)


def start():
    paused = []
    for j in jobs.all_jobs():
        if j.get("recover"):
            with ctx.as_user(j["user"]):
                recover(j)
        if j.get("was_live") and j.get("creator"):
            paused.append((j["user"], j["creator"], j["source"]["url"]))
            j.pop("was_live", None)
            jobs.save(j)
    if paused:
        threading.Thread(target=_resume_recordings, args=(paused,), daemon=True).start()
    threading.Thread(target=watch_loop, daemon=True).start()
