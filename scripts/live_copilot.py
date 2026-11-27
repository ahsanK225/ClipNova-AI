"""CLI bridge for Antigravity Live Co-Pilot to watch active PeakCut streams and inject 30-35s Shorts + SEO.

Usage:
  python scripts/live_copilot.py watch [--creator theburntpeanut] [--window 240] [--frames 5]
  python scripts/live_copilot.py start --creator theburntpeanut [--channel https://www.twitch.tv/...]
  python scripts/live_copilot.py clip --jid <jid> --start 120.5 --end 150.5 --hook "..." --title "..." ...
  python scripts/live_copilot.py seo --jid <jid> --cid clip001 --hook "..." --title "..." ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("PEAKCUT_URL", "http://127.0.0.1:8765").rstrip("/")
HEADERS = {"Origin": BASE, "Content-Type": "application/json"}


def _req(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=HEADERS if data else {"Origin": BASE})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"HTTP {e.code} on {path}: {msg}")


def main():
    ap = argparse.ArgumentParser(description="PeakCut Antigravity Live Co-Pilot Bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_watch = sub.add_parser("watch", help="Fetch live transcript, spikes, frames & recent clips")
    p_watch.add_argument("--creator", default="")
    p_watch.add_argument("--jid", default="")
    p_watch.add_argument("--window", type=float, default=240.0)
    p_watch.add_argument("--frames", type=int, default=5)
    p_watch.add_argument("--json", action="store_true")

    p_start = sub.add_parser("start", help="Start live recording for a creator")
    p_start.add_argument("--creator", required=True)
    p_start.add_argument("--channel", default="")

    p_clip = sub.add_parser("clip", help="Queue an exact 20-35s Co-Pilot clip with custom SEO")
    p_clip.add_argument("--jid", required=True)
    p_clip.add_argument("--start", type=float, required=True)
    p_clip.add_argument("--end", type=float, required=True)
    p_clip.add_argument("--hook", default="")
    p_clip.add_argument("--title", default="")
    p_clip.add_argument("--description", default="")
    p_clip.add_argument("--tags", default="")
    p_clip.add_argument("--hashtags", default="")
    p_clip.add_argument("--comment", default="")
    p_clip.add_argument("--category", default="funny")
    p_clip.add_argument("--score", type=int, default=90)
    p_clip.add_argument("--reason", default="")
    p_clip.add_argument("--force", action="store_true")

    p_seo = sub.add_parser("seo", help="Upgrade SEO metadata on an existing clip")
    p_seo.add_argument("--jid", required=True)
    p_seo.add_argument("--cid", required=True)
    p_seo.add_argument("--hook", default="")
    p_seo.add_argument("--title", default="")
    p_seo.add_argument("--description", default="")
    p_seo.add_argument("--tags", default="")
    p_seo.add_argument("--hashtags", default="")
    p_seo.add_argument("--comment", default="")

    args = ap.parse_args()
    if args.cmd == "watch":
        qs = urllib.parse.urlencode({
            "creator": args.creator,
            "jid": args.jid,
            "window": args.window,
            "frames": args.frames,
        })
        res = _req("GET", f"/api/live/copilot?{qs}")
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return
        sessions = res.get("sessions") or []
        if not sessions:
            print("No active live recordings running right now.")
            return
        for s in sessions:
            print(f"=== JID: {s['jid']} | Creator: {s['creator']} | Game: {s['game']} | Elapsed: {s['elapsed']}s | Buffer: {s['buffer_start']}..{s['buffer_end']}s ===")
            print(f"Title: {s['title']}")
            if s["loudness_spikes"]:
                print("Loudness Spikes:", ", ".join(f"{x['t']}s(z={x['z']})" for x in s["loudness_spikes"]))
            if s["chat_spikes"]:
                print("Chat Spikes:", ", ".join(f"{x['t']}s({x['msgs']}msgs)" for x in s["chat_spikes"]))
            if s["frames"]:
                print("Frames:")
                for f in s["frames"]:
                    print(f"  [{f['t']}s] {f['path']}")
            if s["clips"]:
                print("Recent Clips:")
                for c in s["clips"][-8:]:
                    print(f"  {c['id']} [{c['start']}..{c['end']}s ({c['dur']}s)] {c['status']} | {c.get('hook') or ''} | {c.get('title') or ''}")
            print("Transcript:")
            for line in s["transcript"][-30:]:
                print(" ", line)
        return

    if args.cmd == "start":
        body = {"channel": args.channel} if args.channel else {}
        res = _req("POST", f"/api/creators/{urllib.parse.quote(args.creator)}/live", body)
        print(json.dumps({"ok": True, "jid": res.get("id"), "status": res.get("status"), "title": res.get("title")}, ensure_ascii=False))
        return

    if args.cmd == "clip":
        payload = {
            "start": args.start,
            "end": args.end,
            "category": args.category,
            "score": args.score,
            "force": bool(args.force),
        }
        if args.hook:
            payload["hook"] = args.hook
        if args.title:
            payload["title"] = args.title
            payload["seo_title"] = args.title
        if args.description:
            payload["description"] = args.description
        if args.tags:
            payload["seo_tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
        if args.hashtags:
            payload["hashtags"] = [t.lstrip("#").strip() for t in args.hashtags.split(",") if t.strip()]
        if args.comment:
            payload["pinned_comment"] = args.comment
        if args.reason:
            payload["reason"] = args.reason
        res = _req("POST", f"/api/live/{urllib.parse.quote(args.jid)}/clip", payload)
        print(json.dumps(res, ensure_ascii=False))
        return

    if args.cmd == "seo":
        payload = {}
        if args.hook:
            payload["hook"] = args.hook
        if args.title:
            payload["title"] = args.title
            payload["seo_title"] = args.title
        if args.description:
            payload["description"] = args.description
        if args.tags:
            payload["seo_tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
        if args.hashtags:
            payload["hashtags"] = [t.lstrip("#").strip() for t in args.hashtags.split(",") if t.strip()]
        if args.comment:
            payload["pinned_comment"] = args.comment
        if not payload:
            raise SystemExit("Nothing to update. Provide --hook / --title / --description / --tags / --comment.")
        _req("PUT", f"/api/jobs/{urllib.parse.quote(args.jid)}/clips/{urllib.parse.quote(args.cid)}/text", payload)
        print(json.dumps({"ok": True, "jid": args.jid, "cid": args.cid, "updated": list(payload.keys())}))


if __name__ == "__main__":
    main()
