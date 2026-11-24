"""PeakCut web server. Run with:  python -m studio.server

Public pages:  /  /login  /signup          The app:  /app  (signed-in users only)
Everything under /api, /media and /oauth needs a session, except /api/auth/* and /api/public."""
import contextlib
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import sqlalchemy as sa
import uvicorn
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

from . import admin as admins
from . import account, load
from . import (accounts, ai, alerts, analytics, auth, brain, calendar, config, creators, ctx, db, jobs, live, media, posting,
               profiles, render, safe, transcribe, usage)

from . import tools as _tools  # noqa: E402


def _quiet(fn):
    try:
        fn()
    except Exception as e:  # noqa: BLE001 - said again, in plain words, when a video needs it
        print(f"  {e}", flush=True)


app = FastAPI(title="PeakCut", docs_url=None, redoc_url=None, openapi_url=None)
WEB = config.ROOT / "web"
OPEN = ("/api/auth/", "/pub/", "/api/public", "/auth/google/", "/auth/verify", "/brand/", "/assets/", "/api/audio/", "/healthz", "/favicon.ico", "/robots.txt", "/sitemap.xml")
PAGES = {"/": "landing.html", "/login": "auth.html", "/signup": "auth.html", "/reset": "reset.html",
         "/privacy": "legal.html", "/terms": "legal.html", "/acceptable-use": "legal.html"}
VIDEO_TYPES = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".ts", ".flv", ".avi"}
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; "
       "frame-src https://player.twitch.tv https://www.youtube-nocookie.com https://www.youtube.com https://player.kick.com; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com")


BOOT = f"{int(time.time()) % 100000:x}"     # part of every sync token, so pages reload their data after a restart


@app.on_event("startup")
async def _more_threads():
    import anyio.to_thread
    anyio.to_thread.current_default_thread_limiter().total_tokens = int(config.env("PEAKCUT_REQUEST_THREADS", "64"))


@app.on_event("startup")
def _startup():
    db.init()
    for f in (config.TMP_DIR / "uploads").glob("*"):      # uploads cut short by a restart
        try:
            f.unlink()
        except OSError:
            pass
    render.install_fonts()
    if _tools.missing():
        print("\n  " + _tools.HELP + "\n", flush=True)
    if not transcribe.REMOTE and config.env("PEAKCUT_FETCH_MODEL", "1") != "0":     # the speech model: fetched now, in the background, if it was never downloaded
        from . import fetch_model
        threading.Thread(target=lambda: _quiet(fetch_model.ensure), daemon=True).start()
    jobs.start()
    live.start()
    posting.start()
    from . import updates
    updates.start()                  # looks for a newer PeakCut every minute, in the background


# ================================================================ the gate: who is asking, and are they allowed
class Gate:
    """Runs before every request: finds the signed-in user, blocks what needs sign-in, blocks cross-site form
    posts, caps upload size and adds security headers."""

    def __init__(self, app):
        self.inner = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        req = Request(scope)
        path, method = scope["path"], scope["method"]

        async def deny(status, msg, redirect=None):
            no_keep = {"Cache-Control": "private, no-store"}      # never kept by a browser or CDN
            resp = RedirectResponse(redirect, 303, headers=no_keep) if redirect else JSONResponse({"detail": msg}, status, headers=no_keep)
            await resp(scope, receive, send)

        if method not in ("GET", "HEAD", "OPTIONS"):
            if not _from_here(req):
                return await deny(403, "Cross-site requests are not allowed.")
            # Only the upload may be big. Everything else is a small form, and is cut off at 256 KB whatever its
            # headers claim, so nobody can fill the server's memory by posting junk (signed in or not).
            piece = method == "PUT" and path.startswith("/api/upload/")
            cap = ((min(config.MAX_UPLOAD_MB, config.UPLOAD_PART_MB) if piece else config.MAX_UPLOAD_MB) + 8) * 1024 * 1024 \
                if path == "/api/upload" or piece else 256 * 1024
            try:
                if int(req.headers.get("content-length") or 0) > cap:
                    return await deny(413, f"That file is too big. The limit is {config.MAX_UPLOAD_MB} MB." if path == "/api/upload" else "That request is too large.")
            except ValueError:
                return await deny(400, "Bad request.")
            seen, inner_receive = 0, receive

            async def receive():
                nonlocal seen
                m = await inner_receive()
                if m["type"] == "http.request":
                    seen += len(m.get("body", b""))
                    if seen > cap:
                        raise HTTPException(413, "That request is too large.")
                return m

        is_open = path in PAGES or any(path.startswith(p) for p in OPEN)
        admin_area = path == "/admin" or path.startswith(("/admin/", "/api/admin/"))
        if config.ACCOUNTS:
            cookie = req.cookies.get(auth.COOKIE, "")
            user = auth._sess.get(auth._h(cookie)) if cookie and not admin_area else None      # remembered: no database, no thread hop
            user = user[1] if user and time.time() - user[0] < auth.SESS_FOR else (
                await run_in_threadpool(auth.user_for, cookie, admin_area) if cookie else None)
        else:
            # No sign-in: whoever opens the page is the owner. Because nothing else stands in the way, the page
            # must have been asked for by its real address (a number, "localhost", or the address in settings),
            # so another website cannot reach it through a made-up name that points at this machine.
            if not _own_address(req.headers.get("host", "")):
                return await deny(403, "Open PeakCut by its own address.")
            if path == "/" or path == "/reset" or path.startswith("/auth/"):
                return await deny(303, "", redirect="/app")
            if path.startswith("/api/auth/") and path != "/api/auth/me":
                return await deny(404, "Not Found")
            user = auth._local or await run_in_threadpool(auth.local_user)
        if admin_area:
            # The admin area does not exist for anyone else: same "not found" whether signed out or a normal user.
            if not user or not user.is_admin:
                return await deny(404, "Not Found")
            if method not in ("GET", "HEAD"):
                # changes must come from our own pages: the browser has to say so, and it has to match
                if not _from_here(req, must_say=True):
                    return await deny(403, "Cross-site requests are not allowed.")
        if not user and not is_open:
            if path == "/app" or path.startswith("/app/"):
                return await deny(401, "", redirect="/login")
            return await deny(401, "Please sign in.")
        if user and path in ("/login", "/signup"):
            return await deny(303, "", redirect="/app")
        scope.setdefault("state", {})["user"] = user
        if user and path in ("/api/upload", "/api/upload/start") and method == "POST":
            # decided before a single byte of the file is accepted: verified, has a free slot, has disk space
            def allowed():
                with ctx.as_user(user.id):
                    _need_verified(); _job_slots(); _quota()                     # noqa: E702
            try:
                await run_in_threadpool(allowed)
            except HTTPException as e:
                return await deny(e.status_code, e.detail)
        if user and path.startswith("/api/") and not auth.seen_recently(user.id):
            await run_in_threadpool(auth.touch, user.id)

        unchanged = False

        async def send_with_headers(message):
            nonlocal unchanged
            if unchanged:                       # the browser's copy is current: send no body at all
                if message["type"] == "http.response.body" and not message.get("more_body"):
                    await send({"type": "http.response.body", "body": b""})
                return
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                if method == "GET" and message.get("status") == 200:
                    tag = next((v.decode("latin-1") for k, v in h if k.lower() == b"etag"), "")
                    have = req.headers.get("if-none-match", "")
                    if tag and have and tag.removeprefix("W/") in [x.strip().removeprefix("W/") for x in have.split(",")]:
                        unchanged = True
                        message["status"] = 304
                        h[:] = [(k, v) for k, v in h if k.lower() not in (b"content-length", b"content-type", b"content-encoding")]
                h += [(b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                      (b"referrer-policy", b"strict-origin-when-cross-origin"), (b"content-security-policy", CSP.encode()),
                      (b"permissions-policy", b"camera=(), microphone=(), geolocation=()")]
                if config.HTTPS:
                    h.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
                if path.startswith("/api/"):
                    h.append((b"cache-control", b"no-store"))
                elif message.get("status", 200) >= 300 and not any(k.lower() == b"cache-control" for k, _ in h):
                    # redirects and errors are never kept by a CDN: a "not found" for a clip that is still being
                    # made, or a sign-in redirect, must not be shown to anyone later
                    h.append((b"cache-control", b"private, no-store"))
                if path.startswith(("/app", "/admin", "/api/", "/auth/", "/reset", "/media/")):
                    h.append((b"x-robots-tag", b"noindex, nofollow"))
            await send(message)

        token = ctx._uid.set(user.id if user else None)
        try:
            if user and path == "/api/sync" and method == "GET":
                # By far the most common request. When nothing of this user's changed it is answered right here:
                # no worker thread, no database, no disk. Anything else falls through to the normal route.
                quick = _sync_unchanged(req.query_params.get("v", ""))
                if quick is not None:
                    return await JSONResponse(quick)(scope, receive, send_with_headers)
            await self.inner(scope, receive, send_with_headers)
        finally:
            ctx._uid.reset(token)


app.add_middleware(Gate)


class Compress:
    """gzip for text responses. Videos and images are already compressed and need byte ranges, so they pass through."""
    def __init__(self, app):
        from starlette.middleware.gzip import GZipMiddleware
        self.plain, self.gzip = app, GZipMiddleware(app, minimum_size=800, compresslevel=6)

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "") if scope["type"] == "http" else ""
        media = path.startswith(("/media/", "/api/upload")) or path.endswith((".mp4", ".jpg", ".png", ".webp", ".ico"))
        await (self.plain if scope["type"] != "http" or media else self.gzip)(scope, receive, send)


app.add_middleware(Compress)


# Cloudflare's published address ranges (cloudflare.com/ips). PEAKCUT_CDN_RANGES replaces them if they ever change.
_CDN_RANGES = None


def _from_cdn(addr: str) -> bool:
    global _CDN_RANGES
    import ipaddress
    if _CDN_RANGES is None:
        ranges = config.env("PEAKCUT_CDN_RANGES") or (
            "173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22 141.101.64.0/18 108.162.192.0/18 "
            "190.93.240.0/20 188.114.96.0/20 197.234.240.0/22 198.41.128.0/17 162.158.0.0/15 104.16.0.0/13 "
            "104.24.0.0/14 172.64.0.0/13 131.0.72.0/22 2400:cb00::/32 2606:4700::/32 2803:f800::/32 2405:b500::/32 "
            "2405:8100::/32 2a06:98c0::/29 2c0f:f248::/32")
        _CDN_RANGES = [ipaddress.ip_network(r) for r in ranges.replace(",", " ").split()]
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in n for n in _CDN_RANGES)


# Private and local addresses: the only places a reverse proxy in front of PeakCut can sit.
_PROXY_CIDRS = ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "169.254.0.0/16",
                "::1/128", "fc00::/7", "fe80::/10")
_PROXY_RANGES = [ipaddress.ip_network(r) for r in _PROXY_CIDRS]


def _trust_proxy() -> bool:
    return (config.env("PEAKCUT_TRUST_PROXY") or "").strip().lower() not in ("", "0", "false", "no")


def _valid_ip(text: str) -> str:
    """The address as text if it really is an IP address, otherwise ""."""
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return ""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return str(ip)


def _from_proxy(addr: str) -> bool:
    clean = _valid_ip(addr)
    if not clean:
        return False
    ip = ipaddress.ip_address(clean)
    return any(ip in n for n in _PROXY_RANGES)


def _ip(request: Request) -> str:
    """The visitor's address, used for rate limits. The connection's own address, or the one the proxy in front
    reports (PEAKCUT_TRUST_PROXY). If that connection comes from the CDN, the CDN's header names the real visitor
    (PEAKCUT_CLIENT_IP_HEADER). The header is believed only when the CDN really sent the request, so nobody can
    pick their own address by sending it themselves.

    The proxy adds the address it saw at the END of X-Forwarded-For. Everything before that was written by the
    visitor, so only the last entry is believed, and only when the connection came from a proxy on a private address."""
    direct = request.client.host if request.client else ""
    peer = direct
    fwd = ",".join(request.headers.getlist("x-forwarded-for"))
    if _trust_proxy() and fwd and _from_proxy(direct):
        peer = _valid_ip(fwd.rsplit(",", 1)[-1].strip()) or direct
    named = config.env("PEAKCUT_CLIENT_IP_HEADER")
    if named and request.headers.get(named) and _from_cdn(peer):
        return _valid_ip(request.headers[named].split(",")[0].strip()[:64]) or peer
    return peer


def _from_here(req, must_say=False) -> bool:
    """Did this change come from PeakCut's own page, and not from another website?

    The browser's own answer is trusted first: it marks every request "same-origin" or not, and a web page cannot
    fake that mark. Comparing the page's address with the address the request arrived at is only the fallback,
    because that comparison goes wrong when something in between rewrites either of them (a proxy, an antivirus
    web shield, a browser extension), which made every save fail with "Cross-site requests are not allowed"."""
    if (req.headers.get("sec-fetch-site") or "").lower() == "same-origin":
        return True
    origin = (req.headers.get("origin") or "").rstrip("/").lower()
    if not origin:
        return not must_say
    return urlparse(origin).netloc == (req.headers.get("host") or "").lower() or origin == config.PUBLIC_URL.lower()


def _own_address(host: str) -> bool:
    """Is this the address PeakCut is really reached by? A number (127.0.0.1, 192.168.1.20), "localhost", or the
    host in PEAKCUT_PUBLIC_URL."""
    import ipaddress
    name = host.strip().lower()
    name = name[1:name.index("]")] if name.startswith("[") and "]" in name else name.rsplit(":", 1)[0] if ":" in name else name
    if name in ("localhost", urlparse(config.PUBLIC_URL).hostname or "") or name.endswith(".localhost"):
        return True
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        return False


def _me(request: Request):
    return request.state.user


def _admin(request: Request):
    """The signed-in admin, read from the database for this very request. Anyone else gets "not found"."""
    u = getattr(request.state, "user", None)
    if not u or not u.is_admin or u.disabled:
        raise HTTPException(404)
    return u


def _need_verified():
    if not auth.is_verified(ctx.uid()):
        raise HTTPException(403, "Confirm your email first. We sent you a link when you signed up; you can send a new one from the banner at the top.")


# ================================================================ pages
def _page(name, shared=False):
    """A page. The browser keeps its copy and asks each time whether it has changed; when it has not, the answer
    is a few bytes ("not modified") instead of the whole page again. Signed-in pages are never kept by anything
    in between (a proxy or CDN), only by the person's own browser."""
    return FileResponse(WEB / name, headers={"Cache-Control": ("public" if shared else "private") + ", no-cache"})


_LANDING: dict = {}


@app.get("/")
def landing():
    f = WEB / "landing.html"
    m = f.stat().st_mtime
    if _LANDING.get("m") != m:
        html = f.read_text(encoding="utf-8").replace("{{SITE}}", config.PUBLIC_URL)
        _LANDING.update(m=m, html=html, etag='"' + hashlib.md5(html.encode()).hexdigest() + '"')
    # fresh for five minutes; after that a CDN or browser may show its copy while it quietly fetches the new one
    return HTMLResponse(_LANDING["html"], headers={"Cache-Control": "public, max-age=300, stale-while-revalidate=86400",
                                                   "ETag": _LANDING["etag"]})


@app.get("/robots.txt")
def robots():
    return Response("User-agent: *\nAllow: /\nDisallow: /app\nDisallow: /api/\nDisallow: /auth/\nDisallow: /reset\nDisallow: /media/\n"
                    f"\nSitemap: {config.PUBLIC_URL}/sitemap.xml\n", media_type="text/plain",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sitemap.xml")
def sitemap():
    day = time.strftime("%Y-%m-%d")
    pages = [("/", "1.0", "weekly"), ("/signup", "0.8", "monthly"), ("/login", "0.4", "monthly"), ("/terms", "0.3", "yearly"),
             ("/privacy", "0.3", "yearly"), ("/acceptable-use", "0.2", "yearly")]
    body = "".join(f"<url><loc>{config.PUBLIC_URL}{u}</loc><lastmod>{day}</lastmod><changefreq>{c}</changefreq>"
                   f"<priority>{p}</priority></url>" for u, p, c in pages)
    return Response('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                    + body + "</urlset>", media_type="application/xml", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/login")
@app.get("/signup")
def auth_page():
    return _page("auth.html", shared=True)


@app.get("/reset")
def reset_page():
    return _page("reset.html", shared=True)


LEGAL = {
    "privacy": ("Privacy Policy", "How PeakCut collects, uses and protects your data, including Google user data, cookies and your privacy rights."),
    "terms": ("Terms of Service", "The terms for using PeakCut, the AI clipping tool for streams and videos: accounts, availability and liability."),
    "acceptable-use": ("Acceptable Use Policy", "What you may and may not do with PeakCut, the AI stream clipping tool."),
}


@app.get("/privacy")
@app.get("/terms")
@app.get("/acceptable-use")
def legal_page(request: Request):
    """Public, so Google's app review (and anyone) can read them. Business name, law and contact come from settings."""
    import html as _h
    page = request.url.path.strip("/")
    title, desc = LEGAL[page]
    contact = config.CONTACT_EMAIL
    who = (f'<a href="mailto:{_h.escape(contact)}">{_h.escape(contact)}</a>' if contact
           else "the contact details on our website")
    name = _h.escape(config.LEGAL_NAME or "PeakCut")
    law = (f"the laws of {_h.escape(config.LEGAL_COUNTRY)}" if config.LEGAL_COUNTRY
           else "the laws of the country where PeakCut's operator is established")
    out = (_LEGAL_HTML or (WEB / "legal.html").read_text(encoding="utf-8"))
    for k, v in {"{{CONTACT}}": who, "{{PAGE}}": page, "{{PAGE_PATH}}": page, "{{SITE}}": _h.escape(config.PUBLIC_URL),
                 "{{NAME}}": name, "{{LAW}}": law, "{{TITLE}}": title, "{{DESC}}": desc}.items():
        out = out.replace(k, v)
    return HTMLResponse(out, headers={"Cache-Control": "public, max-age=3600"})


_LEGAL_HTML = ""


@app.get("/app")
@app.get("/app/{rest:path}")
def app_page(rest: str = ""):
    """Every app address (/app/videos, /app/creators/<id>/setup ...) is the same page; it shows the right view."""
    return _page("index.html")


@app.get("/admin")
@app.get("/admin/{rest:path}")
def admin_page(request: Request, rest: str = ""):
    _admin(request)
    return _page("admin.html")


@app.get("/healthz")
def healthz():
    with db.engine.connect() as c:
        c.execute(sa.text("select 1"))
    return {"ok": True}


@app.get("/brand/{name}")
def brand(name: str):
    if not re.fullmatch(r"[\w\-]+\.(svg|png|ico|webp|jpg|mp4)", name) or not (WEB / "brand" / name).is_file():
        raise HTTPException(404)
    return FileResponse(WEB / "brand" / name, headers={"Cache-Control": "public, max-age=604800, stale-while-revalidate=86400"})


@app.get("/assets/{name}")
def asset(name: str):
    if not re.fullmatch(r"[\w\-]+\.js", name) or not (WEB / name).is_file():
        raise HTTPException(404)
    return FileResponse(WEB / name, media_type="text/javascript", headers={"Cache-Control": "public, max-age=86400, stale-while-revalidate=604800"})


@app.get("/favicon.ico")
def favicon():
    return RedirectResponse("/brand/favicon.svg", 308)


# ================================================================ sign up, sign in, sign out
@app.get("/api/public")
def public_config():
    from . import mailer
    return {"google": auth.google_ready(), "mail": mailer.ready(), "verify_email": config.VERIFY_EMAIL}


def _signed_in(request: Request, user, first: bool, redirect=None):
    token = auth.start_session(user.id, _ip(request), request.headers.get("user-agent", ""))
    resp = RedirectResponse(redirect, 303) if redirect else JSONResponse({"user": auth.public(user)})
    resp.set_cookie(**auth.cookie_args(token))
    return resp


@app.post("/api/auth/signup")
def signup(request: Request, body: dict = Body(...)):
    try:
        auth.throttle("signup:" + _ip(request), 8, 3600)
        user, first = auth.signup(str(body.get("email", "")), str(body.get("password", "")), str(body.get("name", "")))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    if not auth.is_verified(user.id):
        auth.send_verify(user)
    return _signed_in(request, user, first)


@app.post("/api/auth/resend-verification")
def resend_verification(request: Request):
    u = _me(request)
    if not u:
        raise HTTPException(401, "Please sign in.")
    if auth.is_verified(u.id):
        return {"verified": True}
    try:
        auth.throttle("verify:" + u.id, 3, 900)
    except auth.AuthError:
        raise HTTPException(429, "We've sent a few already. Check your spam folder, or try again in 15 minutes.")
    from . import mailer
    return {"sent": auth.send_verify(u), "mail_ready": mailer.ready()}


@app.get("/auth/verify")
def verify_email(request: Request, t: str = ""):
    try:
        auth.verify_link(t)
    except auth.AuthError as e:
        return RedirectResponse("/app?verify_error=" + quote(str(e)), status_code=303)
    return RedirectResponse("/app?verified=1", status_code=303)


@app.post("/api/auth/forgot")
def forgot_password(request: Request, body: dict = Body(...)):
    email = str(body.get("email", "")).strip().lower()
    try:
        auth.throttle("forgot-ip:" + _ip(request), 10, 3600)
        auth.throttle("forgot:" + email, 3, 3600)
    except auth.AuthError as e:
        raise HTTPException(429, str(e))
    auth.forgot(email)
    return {"ok": True}   # the same answer whether or not the account exists


@app.post("/api/auth/reset")
def reset_password(request: Request, body: dict = Body(...)):
    try:
        auth.throttle("reset-ip:" + _ip(request), 20, 3600)
        user = auth.reset_password(str(body.get("token", "")), str(body.get("password", "")))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    return _signed_in(request, user, False)


@app.post("/api/auth/login")
def login(request: Request, body: dict = Body(...)):
    email = str(body.get("email", ""))
    try:
        auth.throttle("login-ip:" + _ip(request), 30, 600)
        auth.throttle(f"login:{email.strip().lower()[:254]}:{_ip(request)}", 8, 600)
        auth.throttle("login:" + email.strip().lower()[:254], 60, 600)
        user = auth.login(email, str(body.get("password", "")))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    return _signed_in(request, user, False)


@app.post("/api/auth/logout")
def logout(request: Request):
    auth.end_session(request.cookies.get(auth.COOKIE, ""))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
def me(request: Request):
    return {"user": auth.public(_me(request)) if _me(request) else None}


@app.post("/api/auth/password")
def change_password(request: Request, body: dict = Body(...)):
    if not _me(request):
        raise HTTPException(401, "Please sign in.")
    try:
        auth.throttle("pw:" + _me(request).id, 6, 600)
        auth.change_password(_me(request).id, str(body.get("current", "")), str(body.get("new", "")),
                             keep_token=request.cookies.get(auth.COOKIE, ""))
    except auth.AuthError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/auth/google/start")
def google_start(next: str = "/app"):
    if not auth.google_ready():
        raise HTTPException(404)
    url, state = auth.google_url(next)
    resp = RedirectResponse(url)
    # the sign-in can only be finished by the browser that started it
    resp.set_cookie("g_state", state, max_age=900, httponly=True, samesite="lax", secure=config.HTTPS, path="/auth/google")
    return resp


@app.get("/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error or not code or not state or not hmac.compare_digest(request.cookies.get("g_state", ""), state):
        return RedirectResponse("/login?error=google", 303)
    try:
        auth.throttle("google:" + _ip(request), 30, 600)
        user, first, nxt = auth.google_finish(code, state)
    except auth.AuthError:
        return RedirectResponse("/login?error=google", 303)
    return _signed_in(request, user, first, redirect=nxt)


# ================================================================ app status
@app.get("/api/status")
def status(request: Request):
    from . import notices
    from . import updates
    me_ = _me(request)
    return {"user": auth.public(me_), "update": updates.latest() if me_.is_admin else None, "accounts": config.ACCOUNTS, "disk_full": load.disk_full(), "no_ffmpeg": bool(_tools.missing()), "links": {"repo": config.REPO_URL, "follow": config.FOLLOW_URL}, "ai": usage.brief(), "unread": notices.unread(),
            "tour": not accounts.settings()["tour_done"],
            "youtube": accounts.youtube_ready(), "connect": {p: accounts.can_connect(p) for p in accounts.PLATFORM_NAMES}, "max_upload_mb": config.MAX_UPLOAD_MB, "upload_part_mb": config.UPLOAD_PART_MB, "max_batch": config.MAX_ACTIVE_JOBS_PER_USER,
            "styles": {k: v["label"] for k, v in render.STYLES.items()}, "hook_styles": {k: v["label"] for k, v in render.HOOK_STYLES.items()}, "layouts": render.LAYOUTS, "speech": _speech_brief()}


def _speech_brief() -> dict:
    """Which spoken languages can be transcribed here: for the language choice when adding a video."""
    from . import fetch_model
    return {k: {"label": m[0], "size_mb": m[3], "state": fetch_model.status(k)} for k, m in fetch_model.MODELS.items()}


# ================================================================ videos
def _job_or_404(jid: str):
    job = jobs.get(jid) if re.fullmatch(r"[\w\-]{8,60}", jid) else None
    if not job:
        raise HTTPException(404, "No such video")
    return job


def _job_slots():
    from . import tools
    if tools.missing():
        raise HTTPException(503, tools.HELP)
    if jobs.busy_count() >= config.MAX_ACTIVE_JOBS_PER_USER:
        raise HTTPException(429, f"You already have {config.MAX_ACTIVE_JOBS_PER_USER} videos in progress. Wait for one to finish.")


_create_lock = threading.Lock()      # "do I have a free slot?" and "take it" happen together, so bursts cannot slip past the limit
_lookups = threading.BoundedSemaphore(8)   # link and channel previews running at once, whole server
_disk: dict = {}


def _quota():
    """Each account has a fixed amount of disk space. Measured at most once a minute."""
    if load.disk_full():
        from . import storage
        raise HTTPException(507, storage.full_message())
    uid = ctx.uid()
    got = _disk.get(uid)
    if not got or time.time() - got[0] > 60:
        total = 0
        for root, _dirs, files in os.walk(config.user_dir(uid)):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        got = _disk[uid] = (time.time(), total)
    if got[1] > config.MAX_USER_GB * 1e9:
        raise HTTPException(507, "Your storage is full. Delete some older videos to make room.")


def _throttle(key, limit, window, msg="Too many requests at once. Wait a moment."):
    try:
        auth.throttle(key, limit, window)
    except auth.AuthError:
        raise HTTPException(429, msg)


def _lookup(fn, *a):
    """Run a preview lookup, unless the server is already doing as many as it should."""
    if not _lookups.acquire(blocking=False):
        raise HTTPException(429, "Lots of people are looking things up right now. Try again in a few seconds.")
    try:
        return fn(*a)
    finally:
        _lookups.release()


def _creator_rows():
    out = []
    for c in creators.all_creators():
        if profiles.needs_refresh(c):
            profiles.refresh(c["id"])
        s = live.active_for(c["id"])
        out.append({**c, "live_job": s.job["id"] if s else None, "log": creators.read_log(c["id"], 30)})
    return out


def _sync_token() -> str:
    return f"{BOOT}.{ctx.version()}.{jobs.queue_epoch() if jobs.busy_count() else 0}"


def _sync_unchanged(v: str):
    """{"v": token} if the page is up to date and this user's creators are already in memory, else None."""
    mine = creators._mem.get(ctx.uid())
    if mine is None or not v or v != _sync_token():
        return None
    for c in list(mine.values()):                      # still keep live status fresh while the page is open
        if profiles.needs_refresh(c):
            profiles.refresh(c["id"])
    return {"v": v}


@app.get("/api/sync")
def sync(v: str = ""):
    """What the page asks every couple of seconds. It sends the token it got last time; when nothing of this
    user's has changed, the answer is just that token: no files read, nothing built."""
    token = _sync_token()
    if v == token:
        return _sync_unchanged(v) or {"v": token}
    from . import notices
    return {"v": token, "jobs": [jobs.public(j) for j in jobs.list_jobs()], "creators": _creator_rows(),
            "accounts": accounts.list_accounts(), "ai": usage.brief(), "unread": notices.unread()}


@app.get("/api/jobs")
def list_jobs():
    return [jobs.public(j) for j in jobs.list_jobs()]


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    return jobs.public(_job_or_404(jid))


@app.get("/api/preview")
def link_preview(request: Request, url: str = ""):
    url = url.strip()[:500]
    if not media.site_allowed(url):
        raise HTTPException(400, "Paste a full link to a YouTube, Twitch or Kick video.")
    try:
        auth.throttle(f"preview:{_me(request).id}", 12, 60)
    except auth.AuthError:
        raise HTTPException(429, "Too many links at once. Wait a moment.")
    try:
        return _lookup(media.preview, url)
    except media.YouTubeBlocked as e:
        raise HTTPException(503, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Couldn't open that video. Check the link is public and complete.")


@app.post("/api/jobs")
def create_from_link(body: dict = Body(...)):
    _need_verified()
    _quota()
    _throttle("newjob:" + ctx.uid(), 30, 600)
    url = str(body.get("url", "")).strip()[:500]
    if not media.site_allowed(url):
        raise HTTPException(400, "Paste a full link to a YouTube, Twitch or Kick video.")
    try:
        media.check_youtube(url)          # YouTube is refusing us right now: say so, rather than queue a job that fails
    except media.YouTubeBlocked as e:
        raise HTTPException(503, str(e))
    creator = str(body.get("creator") or "") or None
    if creator and not creators.get(creator):
        raise HTTPException(404, "No such creator")
    seen = media._PREVIEWS.get(url)  # already looked up while the user was typing: show it straight away
    if not seen:
        try:
            seen = media.preview(url)
        except Exception:
            seen = None
    if seen and seen.get("is_live"):
        c = creators.get(creator) if creator else None
        if not c:
            up_name = (seen.get("uploader") or "").strip() or "Live Streamer"
            c = next((cr for cr in creators.all_creators() if cr.get("name", "").strip().lower() == up_name.lower()), None)
            if not c:
                c = creators.create({"name": up_name, "channel": url})
        try:
            return jobs.public(live.start_session(c, url))
        except ValueError as e:
            raise HTTPException(400, str(e))
    try:
        with _create_lock:
            _job_slots()
            job = jobs.create({"type": "url", "url": url, "name": url}, body.get("options") or {}, creator=creator)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e) if isinstance(e, ValueError) else "Those options aren't valid.")
    if seen:
        job.update(title=seen["title"], uploader=seen["uploader"], duration=seen["duration"])
        if media.save_thumb(jobs.job_dir(job["id"]), url=url):
            job["thumb"] = True
        jobs.save(job)
    return jobs.public(job)


@app.post("/api/upload")
def create_from_file(file: UploadFile = File(...), options: str = Form("{}"), creator: str = Form("")):
    _need_verified()
    _job_slots()
    name = re.sub(r"[^\w.\- ]", "_", Path(file.filename or "video.mp4").name)[:120]
    ext = Path(name).suffix.lower()
    if ext not in VIDEO_TYPES:
        raise HTTPException(400, "Upload a video file (mp4, mov, mkv or webm).")
    if creator and not creators.get(creator):
        raise HTTPException(404, "No such creator")
    try:
        opts = json.loads(options)
        opts = opts if isinstance(opts, dict) else {}
    except ValueError:
        opts = {}
    updir = config.TMP_DIR / "uploads"
    updir.mkdir(exist_ok=True)
    tmp = updir / f"{os.urandom(8).hex()}{ext}"
    limit, size = config.MAX_UPLOAD_MB * 1024 * 1024, 0
    try:
        with tmp.open("wb") as f:
            while chunk := file.file.read(4 * 1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"That file is too big. The limit is {config.MAX_UPLOAD_MB} MB.")
                f.write(chunk)
        try:
            with _create_lock:
                _job_slots()
                job = jobs.create({"type": "file", "path": str(tmp), "name": name}, opts, enqueue=False, creator=creator or None)
        except (ValueError, TypeError):
            raise HTTPException(400, "Those options aren't valid.")
        _disk.pop(ctx.uid(), None)
        dest = jobs.job_dir(job["id"]) / ("source" + ext)
        shutil.move(str(tmp), dest)
    finally:
        tmp.unlink(missing_ok=True)
    job["source"]["path"] = str(dest)
    jobs.enqueue(job)
    return jobs.public(job)


# ---------------------------------------------------------------- big files, sent in pieces
# The page cuts a large file into pieces, sends each one, and asks for them to be joined. Each piece is small enough
# for anything standing in front of the app. Nothing is trusted from the page: the sizes are fixed when the upload
# starts, every piece must be exactly its size, and only the account that started an upload can add to it.
_UP_ID = re.compile(r"[0-9a-f]{24}")
_up_lock = threading.Lock()


def _up_root() -> Path:
    d = config.TMP_DIR / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


UP_IDLE_SEC = 15 * 60     # an upload of your own that hasn't moved for this long was left behind (tab closed, page reloaded)


def _up_active(d: Path) -> float:
    """When this upload last moved: its folder, or any piece in it (a piece being sent grows as it arrives)."""
    newest = d.stat().st_mtime
    for f in d.iterdir():
        try:
            newest = max(newest, f.stat().st_mtime)
        except OSError:
            pass
    return newest


def _up_sweep():
    """Forget uploads that were started and never finished: anyone's after six hours, and the asker's own once
    they have stood still for UP_IDLE_SEC. An upload cut short by closing the tab or reloading the page never
    says it stopped, and it must not keep counting against the limit of uploads at once."""
    me = ctx.uid()
    for d in _up_root().glob("up-*"):
        try:
            if not d.is_dir():
                continue
            idle = time.time() - _up_active(d)
            if idle > 6 * 3600:
                shutil.rmtree(d, ignore_errors=True)
            elif idle > UP_IDLE_SEC and json.loads((d / "meta.json").read_text(encoding="utf-8")).get("user") == me:
                shutil.rmtree(d, ignore_errors=True)
        except (OSError, ValueError):
            pass


def _up_get(upid: str) -> dict:
    """The upload, only if it belongs to whoever is asking."""
    if not _UP_ID.fullmatch(upid or ""):
        raise HTTPException(404, "No such upload")
    try:
        meta = json.loads((_up_root() / f"up-{upid}" / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(404, "This upload has expired. Start it again.")
    if meta.get("user") != ctx.uid():
        raise HTTPException(404, "No such upload")
    return meta


@app.post("/api/upload/start")
def upload_start(body: dict = Body(...)):
    _need_verified()
    _job_slots()
    _quota()
    _throttle("upstart:" + ctx.uid(), 30, 600)
    name = re.sub(r"[^\w.\- ]", "_", Path(str(body.get("name") or "video.mp4")).name)[:120]
    ext = Path(name).suffix.lower()
    if ext not in VIDEO_TYPES:
        raise HTTPException(400, "Upload a video file (mp4, mov, mkv or webm).")
    size = body.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise HTTPException(400, "Bad file size.")
    if size > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"That file is too big. The limit is {config.MAX_UPLOAD_MB} MB.")
    if _disk.get(ctx.uid(), (0, 0))[1] + size > config.MAX_USER_GB * 1e9:
        raise HTTPException(507, "There isn't room for this file in your storage. Delete some older videos to make room.")
    creator = str(body.get("creator") or "")
    if creator and not creators.get(creator):
        raise HTTPException(404, "No such creator")
    opts = body.get("options") if isinstance(body.get("options"), dict) else {}
    try:
        jobs.clean_options(opts)                 # refused now rather than after the whole file has been sent
    except (ValueError, TypeError):
        raise HTTPException(400, "Those options aren't valid.")
    _up_sweep()
    mine = 0
    for d in _up_root().glob("up-*"):
        try:
            mine += json.loads((d / "meta.json").read_text(encoding="utf-8")).get("user") == ctx.uid()
        except (OSError, ValueError):
            pass
    if mine >= config.MAX_ACTIVE_JOBS_PER_USER:
        raise HTTPException(429, f"You already have {mine} uploads in progress. Let one finish first.")
    part = config.UPLOAD_PART_MB * 1024 * 1024
    upid = os.urandom(12).hex()
    d = _up_root() / f"up-{upid}"
    d.mkdir()
    meta = {"user": ctx.uid(), "name": name, "ext": ext, "size": size, "part": part, "parts": -(-size // part),
            "options": opts, "creator": creator, "t": time.time()}
    (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return {"id": upid, "part": part, "parts": meta["parts"]}


@app.put("/api/upload/{upid}/{n}")
async def upload_part(request: Request, upid: str, n: int):
    meta = await run_in_threadpool(_up_get, upid)
    if not 0 <= n < meta["parts"]:
        raise HTTPException(400, "No such piece.")
    want = meta["part"] if n < meta["parts"] - 1 else meta["size"] - meta["part"] * (meta["parts"] - 1)
    d = _up_root() / f"up-{upid}"
    tmp = d / f"{n:05d}.{os.urandom(4).hex()}.tmp"
    got = 0
    try:
        with tmp.open("wb") as f:
            async for chunk in request.stream():
                got += len(chunk)
                if got > want:
                    raise HTTPException(400, "That piece is the wrong size.")
                await run_in_threadpool(f.write, chunk)
        if got != want:
            raise HTTPException(400, "That piece is the wrong size.")
        tmp.replace(d / f"{n:05d}.part")           # sending a piece again simply replaces it
    finally:
        tmp.unlink(missing_ok=True)
    return {"ok": True, "n": n}


@app.post("/api/upload/{upid}/finish")
def upload_finish(upid: str):
    meta = _up_get(upid)
    _need_verified()
    d = _up_root() / f"up-{upid}"
    with _up_lock:                                    # two "finish" calls for one upload make one video, not two
        if not (d / "meta.json").is_file():
            raise HTTPException(404, "This upload has expired. Start it again.")
        parts = [d / f"{i:05d}.part" for i in range(meta["parts"])]
        missing = [i for i, p in enumerate(parts) if not p.is_file()]
        if missing:
            raise HTTPException(409, f"Piece {missing[0] + 1} of {meta['parts']} has not arrived yet.")
        if sum(p.stat().st_size for p in parts) != meta["size"]:
            raise HTTPException(400, "The pieces do not add up to the file.")
        try:
            with _create_lock:
                _job_slots()
                job = jobs.create({"type": "file", "path": "", "name": meta["name"]}, meta["options"], enqueue=False,
                                  creator=meta["creator"] or None)
        except (ValueError, TypeError):
            raise HTTPException(400, "Those options aren't valid.")
        dest = jobs.job_dir(job["id"]) / ("source" + meta["ext"])
        try:
            with dest.open("wb") as out:
                for p in parts:
                    with p.open("rb") as src:
                        shutil.copyfileobj(src, out, 4 * 1024 * 1024)
        except OSError:
            jobs.delete(job["id"])
            raise HTTPException(507, "There wasn't room to save this file. Delete some older videos and try again.")
        shutil.rmtree(d, ignore_errors=True)
    _disk.pop(ctx.uid(), None)
    job["source"]["path"] = str(dest)
    jobs.enqueue(job)
    return jobs.public(job)


@app.delete("/api/upload/{upid}")
def upload_cancel(upid: str):
    _up_get(upid)
    shutil.rmtree(_up_root() / f"up-{upid}", ignore_errors=True)
    return {"ok": True}


@app.post("/api/jobs/{jid}/clips/{cid}/render")
def rerender(jid: str, cid: str, body: dict = Body(...)):
    job = _job_or_404(jid)
    clip = next((c for c in job["clips"] if c["id"] == cid), None)
    if not clip:
        raise HTTPException(404, "No such clip")
    if job["status"] in ("queued", "running") or clip.get("status") in ("queued", "rendering"):
        raise HTTPException(409, "This clip is still being made. Try again when it has finished.")
    _throttle("render:" + ctx.uid(), 20, 600, "That's a lot of re-makes in a short time. Wait a few minutes.")
    try:
        jobs.request_render(jid, cid, body)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return jobs.public(job)


@app.post("/api/jobs/{jid}/clips/{cid}/review")
def review_clip(jid: str, cid: str, body: dict = Body(...)):
    """Set review feedback rating for a clip (great, good, bad, missed, duplicate, false_reaction)."""
    job = _job_or_404(jid)
    clip = next((c for c in job["clips"] if c["id"] == cid), None)
    if not clip:
        raise HTTPException(404, "No such clip")
    rating = str(body.get("rating", "")).strip().lower()
    valid_ratings = {"great", "good", "bad", "missed", "duplicate", "false_reaction"}
    if rating not in valid_ratings:
        raise HTTPException(400, f"Invalid rating. Must be one of: {', '.join(sorted(valid_ratings))}")
    clip["feedback"] = rating
    clip["feedback_at"] = time.time()
    jobs.save(job)
    return {"ok": True, "feedback": rating}



@app.post("/api/jobs/{jid}/apply-preset")
def apply_preset_to_job(jid: str, body: dict = Body(...)):
    """Apply a custom preset or layout to all clips in a job, and optionally re-render all."""
    import copy
    job = _job_or_404(jid)
    pname = str(body.get("preset_name") or body.get("name") or "").strip()
    custom_layout = body.get("custom_layout")
    rerender_all = bool(body.get("rerender_all", True))

    cr = {}
    if job.get("creator"):
        try:
            cr = creators.get(job["creator"]) or {}
        except Exception:
            cr = {}

    if not custom_layout and pname:
        custom_layout = cr.get("custom_presets", {}).get(pname)

    if not custom_layout and cr.get("custom_layout"):
        custom_layout = cr.get("custom_layout")

    if not custom_layout:
        raise HTTPException(400, "No custom layout or preset provided")

    custom_layout = {**custom_layout, "enabled": True}

    # Update job options
    job.setdefault("options", {})
    job["options"]["custom_layout"] = copy.deepcopy(custom_layout)
    job["options"]["layout"] = "custom"
    if pname:
        job["options"]["active_preset"] = pname
    if custom_layout.get("hook_style"):
        job["options"]["hook_style"] = custom_layout["hook_style"]
    if custom_layout.get("facecam"):
        job["facecam"] = custom_layout["facecam"]

    count = 0
    for clip in job.get("clips", []):
        clip_changes = {
            "layout": "custom",
            "custom_layout": copy.deepcopy(custom_layout),
            "active_preset": pname
        }
        if custom_layout.get("hook_style"):
            clip_changes["hook_style"] = custom_layout["hook_style"]
        if custom_layout.get("caption_style"):
            clip_changes["style"] = custom_layout["caption_style"]
        if custom_layout.get("hook_y") is not None:
            clip_changes["hook_y"] = custom_layout["hook_y"]
        if custom_layout.get("hook_w") is not None:
            clip_changes["hook_w"] = custom_layout["hook_w"]
        if custom_layout.get("facecam"):
            clip_changes["facecam"] = custom_layout["facecam"]

        if rerender_all:
            try:
                jobs.request_render(jid, clip["id"], clip_changes)
                count += 1
            except Exception:
                clip.update(clip_changes)
        else:
            clip.update(clip_changes)
            count += 1

    jobs.save(job)
    return {"ok": True, "updated_clips": count, "preset_name": pname, "rerender_all": rerender_all}


def _clip_or_404(jid: str, cid: str):
    job = _job_or_404(jid)
    clip = next((c for c in job["clips"] if c["id"] == cid), None)
    if not clip:
        raise HTTPException(404, "No such clip")
    return job, clip


@app.put("/api/jobs/{jid}/clips/{cid}/text")
def clip_text(jid: str, cid: str, body: dict = Body(...)):
    """Save a clip's title, description and hashtags. The video is not made again."""
    job, clip = _clip_or_404(jid, cid)
    _throttle("cliptext:" + ctx.uid(), 120, 600)
    try:
        jobs.save_post_text(job, clip, body)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return jobs.public(job)


@app.get("/api/jobs/{jid}/clips/{cid}/words")
def get_clip_words(jid: str, cid: str):
    """Return editable timestamped caption words for one clip."""
    job, clip = _clip_or_404(jid, cid)
    return jobs.get_clip_words(job, clip)


@app.put("/api/jobs/{jid}/clips/{cid}/words")
def save_clip_words(jid: str, cid: str, body: dict = Body(...)):
    """Save user-edited caption words on a clip so the next render burns those exact words."""
    job, clip = _clip_or_404(jid, cid)
    _throttle("clipwords:" + ctx.uid(), 120, 600)
    words_in = body.get("words") if isinstance(body, dict) else None
    if not isinstance(words_in, list):
        raise HTTPException(400, "Body must include a 'words' list.")
    saved = jobs.save_clip_words(job, clip, words_in)
    return {"ok": True, "count": len(saved), "words": saved}


@app.post("/api/jobs/{jid}/clips/{cid}/write")
def clip_write(jid: str, cid: str):
    """Ask the AI for a new visually-grounded title, description and hashtags for one clip."""
    job, clip = _clip_or_404(jid, cid)
    _throttle("clipwrite:" + ctx.uid(), 20, 600, "That's a lot of rewrites in a short time. Wait a few minutes.")
    usage.set_context(job.get("creator"), job.get("title") or "")
    try:
        text = jobs.spoken_in(job, clip)
        title = job.get("title") or clip.get("title") or ""
        uploader = job.get("uploader") or job.get("creator") or ""
        game = job.get("game") or None
        frames = jobs.get_clip_frames_payload(job, clip, n_frames=6)
        meta = None
        if frames and ai.ready():
            try:
                meta = brain.describe_multimodal(frames, text=text, title=title, uploader=uploader, game=game)
            except Exception as e:
                print(f"[clip_write] Multimodal describe notice: {e}", flush=True)
        if meta and meta.get("title"):
            res = {
                "title": meta["title"],
                "titles": meta.get("titles", []),
                "description": meta["description"],
                "hashtags": meta.get("hashtags", []),
                "seo_title": meta.get("seo_title", meta["title"]),
                "seo_tags": meta.get("seo_tags", []),
                "pinned_comment": meta.get("pinned_comment", ""),
                "hook": meta.get("hook"),
                "hooks": meta.get("hooks", [])
            }
        else:
            res = brain.post_text(text, title, uploader, game=game)
        if isinstance(res, dict):
            if res.get("titles"):
                clip["titles"] = res["titles"]
            if res.get("hooks"):
                clip["hooks"] = res["hooks"]
            if res.get("hook"):
                clip["hook"] = res["hook"]
            jobs.save(job)
        return res
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@app.get("/api/jobs/{jid}/clips/{cid}/titles")
@app.post("/api/jobs/{jid}/clips/{cid}/titles")
def clip_generate_titles(jid: str, cid: str):
    """Generate 4 viral, high-CTR YouTube Shorts title suggestions using AI vision and video frames."""
    job, clip = _clip_or_404(jid, cid)
    _throttle("cliptitles:" + ctx.uid(), 30, 600, "Please wait a moment before generating more titles.")
    usage.set_context(job.get("creator"), job.get("title") or "")
    try:
        text = jobs.spoken_in(job, clip)
        title = job.get("title") or clip.get("title") or ""
        uploader = job.get("uploader") or job.get("creator") or ""
        game = job.get("game") or None
        frames = jobs.get_clip_frames_payload(job, clip, n_frames=6)
        titles = brain.generate_viral_titles(text, title, uploader, game=game, count=4, image=frames)
        clip["titles"] = titles
        if titles and not clip.get("title"):
            clip["title"] = titles[0]
        jobs.save(job)
        return {"ok": True, "titles": titles, "title": clip.get("title")}
    except Exception as e:
        raise HTTPException(500, f"Failed to generate viral titles: {e}")


@app.get("/api/jobs/{jid}/clips/{cid}/hooks")
@app.post("/api/jobs/{jid}/clips/{cid}/hooks")
def clip_generate_hooks(jid: str, cid: str):
    """Generate 6 viral hook banner variations for this clip using AI vision and video frames."""
    job, clip = _clip_or_404(jid, cid)
    _throttle("cliphooks:" + ctx.uid(), 30, 600, "Please wait a moment before generating more hooks.")
    usage.set_context(job.get("creator"), job.get("title") or "")
    try:
        text = jobs.spoken_in(job, clip)
        title = job.get("title") or clip.get("title") or ""
        uploader = job.get("uploader") or job.get("creator") or ""
        game = job.get("game") or None
        frames = jobs.get_clip_frames_payload(job, clip, n_frames=6)
        hooks = brain.generate_viral_hooks(text, title, uploader, game=game, count=6, image=frames)
        clip["hooks"] = hooks
        if hooks:
            clip["hook"] = hooks[0]
        jobs.save(job)
        return {"ok": True, "hooks": hooks, "hook": clip.get("hook")}
    except Exception as e:
        raise HTTPException(500, f"Failed to generate viral hooks: {e}")


@app.post("/api/jobs/{jid}/clips/{cid}/open-folder")
def open_clip_folder(jid: str, cid: str):
    """Open folder in Windows Explorer and highlight the exact clip MP4 file for 1-click ChatGPT upload."""
    job, clip = _clip_or_404(jid, cid)
    d = Path(job["dir"])
    candidates = []
    clip_file = clip.get("file")
    if clip_file:
        candidates.append(d / "clips" / clip_file)
        candidates.append(d / clip_file)
    if clip.get("src"):
        candidates.append(Path(clip["src"]))
    candidates.extend([
        d / "clips" / f"{cid}.mp4",
        d / "clips" / f"{cid}_vertical.mp4",
        d / f"{cid}.mp4",
        d / "clips" / f"{cid}.jpg",
        d / "clips",
        d
    ])
    target = next((p for p in candidates if p.exists()), d)
    target_str = str(target.resolve())
    try:
        if os.name == "nt":
            if target.is_file():
                try:
                    subprocess.Popen(f'explorer.exe /select,"{target_str}"')
                except Exception:
                    os.startfile(str(target.parent.resolve()))
            else:
                os.startfile(target_str)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", target_str] if target.is_file() else ["open", target_str])
        else:
            subprocess.Popen(["xdg-open", str(target.parent if target.is_file() else target)])
        return {"ok": True, "path": target_str, "filename": target.name}
    except Exception as e:
        raise HTTPException(500, f"Could not open folder: {e}")


@app.post("/api/jobs/{jid}/clips/{cid}/convert-h264")
def convert_clip_to_h264(jid: str, cid: str):
    """Ensure clip video is encoded in standard H.264 MP4 for 100% smooth browser and editor playback."""
    job, clip = _clip_or_404(jid, cid)
    d = Path(job["dir"])
    candidates = [
        d / "clips" / f"{cid}.mp4",
        d / "clips" / f"{cid}_vertical.mp4",
        d / f"{cid}.mp4",
    ]
    target = next((p for p in candidates if p.exists()), None)
    if not target:
        raise HTTPException(404, "Clip video file not found")
        
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name", "-of", "json", str(target)]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        info = json.loads(res.stdout) if res.returncode == 0 else {}
        codec = info.get("streams", [{}])[0].get("codec_name", "").lower()
    except Exception:
        codec = "unknown"
        
    if codec == "h264" and target.suffix.lower() == ".mp4":
        if os.name == "nt":
            try:
                subprocess.Popen(f'explorer.exe /select,"{str(target.resolve())}"')
            except Exception:
                pass
        return {
            "ok": True,
            "status": "already_h264",
            "codec": codec,
            "path": str(target.resolve()),
            "filename": target.name,
            "message": "Clip is already encoded in standard H.264! 100% browser and editor ready."
        }
        
    out_file = target.parent / f"{target.stem}_h264.mp4"
    conv_cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(target.resolve()),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_file.resolve())
    ]
    res_conv = subprocess.run(conv_cmd, capture_output=True, text=True, timeout=180)
    if res_conv.returncode != 0:
        raise HTTPException(500, f"FFmpeg conversion failed: {res_conv.stderr}")
        
    if os.name == "nt" and out_file.exists():
        try:
            subprocess.Popen(f'explorer.exe /select,"{str(out_file.resolve())}"')
        except Exception:
            pass
            
    return {
        "ok": True,
        "status": "converted",
        "codec": "h264",
        "path": str(out_file.resolve()),
        "filename": out_file.name,
        "message": "Successfully converted to H.264 MP4! File highlighted in Explorer."
    }


@app.post("/api/tools/convert-file-h264")
def convert_any_file_h264(body: dict = Body(...)):
    """Convert any external video file (HEVC, H.265, MOV, MKV, etc.) into web-safe H.264 MP4."""
    filepath = str(body.get("filepath", "")).strip().strip('"').strip("'")
    if not filepath:
        raise HTTPException(400, "Please provide a valid video filepath")
    p = Path(filepath)
    if not p.exists() or not p.is_file():
        raise HTTPException(400, f"File does not exist: {filepath}")
        
    out_file = p.parent / f"{p.stem}_converted_h264.mp4"
    conv_cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(p.resolve()),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_file.resolve())
    ]
    res = subprocess.run(conv_cmd, capture_output=True, text=True, timeout=300)
    if res.returncode != 0:
        raise HTTPException(500, f"Conversion failed: {res.stderr}")
        
    if os.name == "nt" and out_file.exists():
        try:
            subprocess.Popen(f'explorer.exe /select,"{str(out_file.resolve())}"')
        except Exception:
            pass
            
    return {
        "ok": True,
        "converted_path": str(out_file.resolve()),
        "filename": out_file.name,
        "message": f"Successfully converted '{p.name}' to H.264 MP4!"
    }


@app.post("/api/jobs/{jid}/clips/{cid}/export-capcut")
def export_to_capcut(jid: str, cid: str):
    """Export the clip into a native CapCut desktop project folder with tracks for video, hook, and captions."""
    job, clip = _clip_or_404(jid, cid)
    from studio.capcut import export_clip_to_capcut
    d = Path(job["dir"])
    candidates = [
        d / "clips" / f"{cid}.mp4",
        d / "clips" / f"{cid}_vertical.mp4",
        d / f"{cid}.mp4",
        d / "clips" / f"{cid}.src.mp4",
    ]
    mp4_path = next((str(p.resolve()) for p in candidates if p.exists()), "")
    res = export_clip_to_capcut(job, clip, mp4_path=mp4_path)
    if not res.get("ok"):
        raise HTTPException(500, res.get("error", "Failed to export CapCut draft"))
    try:
        from studio.capcut import find_and_launch_capcut
        res["launched"] = find_and_launch_capcut()
    except Exception:
        res["launched"] = False
    return res


@app.post("/api/jobs/{jid}/clips/{cid}/open-capcut-folder")
def open_capcut_folder(jid: str, cid: str):
    """Open the exported CapCut draft folder in Windows Explorer."""
    from studio.capcut import get_capcut_drafts_dir, _slug, export_clip_to_capcut
    job, clip = _clip_or_404(jid, cid)
    title = clip.get("title") or clip.get("hook") or f"Clip {cid}"
    slug = _slug(title)
    draft_name = f"PeakCut_{cid}_{slug}"
    draft_dir = get_capcut_drafts_dir() / draft_name
    if not draft_dir.exists():
        d = Path(job["dir"])
        candidates = [d / "clips" / f"{cid}.mp4", d / f"{cid}.mp4", d / "clips" / f"{cid}.src.mp4"]
        mp4_path = next((str(p.resolve()) for p in candidates if p.exists()), "")
        export_clip_to_capcut(job, clip, mp4_path=mp4_path)
    if draft_dir.exists():
        try:
            if os.name == "nt":
                os.startfile(str(draft_dir.resolve()))
        except Exception:
            pass
    return {"ok": True, "draft_path": str(draft_dir)}


@app.get("/api/jobs/{jid}/clips/{cid}/studio-project")
def get_studio_project(jid: str, cid: str):
    """Retrieve full timeline tracks (video, facecam, subtitles, bgm, filters, and VFX) for Web Video Studio."""
    job, clip = _clip_or_404(jid, cid)
    from studio import audio
    
    clip_file = clip.get("file") or f"{cid}.mp4"
    rel_path = f"/media/{jid}/{clip_file}"
    
    words = clip.get("words", [])
    subtitles = []
    start_offset = float(clip.get("start", 0.0))
    is_absolute = bool(start_offset > 2.0 and words and float(words[0].get("s", 0.0)) >= start_offset - 2.0)
    
    for idx, w in enumerate(words):
        w_start = round(float(w.get("s", 0.0)) - (start_offset if is_absolute else 0.0), 3)
        w_end = round(float(w.get("e", w_start + 0.4)) - (start_offset if is_absolute else 0.0), 3)
        subtitles.append({
            "id": idx + 1,
            "text": str(w.get("w", "")),
            "start": max(0.0, w_start),
            "end": max(0.1, w_end)
        })
        
    dur = float(clip.get("dur") or (clip.get("end", 30.0) - clip.get("start", 0.0)))
    
    filters = [
        {"id": "normal", "name": "Normal (Standard)", "css": "none"},
        {"id": "vibrant", "name": "🔥 Vibrant Viral", "css": "saturate(1.3) contrast(1.1)", "ffmpeg": "eq=saturation=1.3:contrast=1.1"},
        {"id": "cinematic", "name": "🎬 Cinematic Film", "css": "contrast(1.15) brightness(0.95) sepia(0.1)", "ffmpeg": "eq=contrast=1.15:brightness=-0.03"},
        {"id": "moody", "name": "🌑 Moody Dark", "css": "contrast(1.2) brightness(0.9)", "ffmpeg": "eq=contrast=1.2:brightness=-0.08"},
        {"id": "cyberpunk", "name": "⚡ Cyberpunk", "css": "hue-rotate(15deg) saturate(1.35)", "ffmpeg": "hue=h=15:s=1.35"},
        {"id": "bw", "name": "🎞️ Classic B&W", "css": "grayscale(1) contrast(1.2)", "ffmpeg": "eq=saturation=0:contrast=1.2"}
    ]
    
    vfx_presets = [
        {"id": "flash", "name": "💥 Flash White Climax", "desc": "Bright white flash impact on drop/reveal"},
        {"id": "shake", "name": "⚡ Screen Shake", "desc": "Rapid 12px camera rumble on punchline"},
        {"id": "glitch", "name": "📺 Glitch RGB", "desc": "Chromatic aberration & horizontal noise shift"},
        {"id": "zoom_punch", "name": "🎯 Zoom Punch", "desc": "Instant 1.25x zoom-in punch on face/reaction"}
    ]
    
    stickers = [
        {"id": "fire", "emoji": "🔥", "label": "FIRE"},
        {"id": "skull", "emoji": "💀", "label": "DEAD"},
        {"id": "laugh", "emoji": "😂", "label": "LOL"},
        {"id": "siren", "emoji": "🚨", "label": "POLICE/GTA"},
        {"id": "trophy", "emoji": "🏆", "label": "WIN/JACKPOT"},
        {"id": "clown", "emoji": "🤡", "label": "CLOWN/L"}
    ]

    return {
        "ok": True,
        "job_id": jid,
        "clip_id": cid,
        "title": clip.get("title") or clip.get("hook") or f"Clip {cid}",
        "hook": clip.get("hook") or "",
        "video_url": rel_path,
        "duration": max(1.0, round(dur, 2)),
        "aspect_ratio": "9:16",
        "tracks": {
            "subtitles": subtitles,
            "facecam": {
                "enabled": bool(clip.get("layout") in ("split", "gameplay", "custom") or clip.get("face")),
                "pos": clip.get("facecam_pos", "top-right"),
                "layout": clip.get("layout", "split")
            },
            "audio": {
                "track": clip.get("bgm_track") or "none",
                "volume": clip.get("bgm_volume", 0.18),
                "offset": clip.get("bgm_offset", 0.0)
            },
            "video": {
                "filter": clip.get("video_filter") or "normal",
                "speed": clip.get("speed", 1.0)
            }
        },
        "available_sounds": audio.list_tracks(),
        "available_filters": filters,
        "available_vfx": vfx_presets,
        "available_stickers": stickers
    }


@app.post("/api/jobs/{jid}/clips/{cid}/studio-export")
def studio_export_clip(jid: str, cid: str, body: dict = Body(default={})):
    """Export modified timeline project from Web Video Studio: triggers re-render and optionally schedules to YouTube."""
    job, clip = _clip_or_404(jid, cid)
    
    changes = {}
    for fld in ("hook", "title", "description", "layout", "facecam_pos", "bgm_track", "bgm_volume", "bgm_offset", "video_filter", "speed", "style"):
        if fld in body:
            changes[fld] = body[fld]
    if "words" in body and isinstance(body["words"], list):
        changes["words"] = body["words"]
    
    # Request re-render
    jobs.request_render(jid, cid, changes)
    
    # Optional auto-schedule into Publishing Calendar
    sched_info = None
    if body.get("schedule_now"):
        from studio import posting, accounts
        accs = body.get("accounts")
        if not accs:
            user_accs = accounts.list_for(ctx.uid() or "u_local")
            accs = [a["id"] for a in user_accs if a.get("type") == "youtube"]
        if accs:
            try:
                sched_res = posting.enqueue(job, clip, accs, target_ts=body.get("target_ts"))
                sched_info = sched_res
            except Exception as e:
                sched_info = {"error": str(e)}

    updated_job = jobs.get(jid)
    updated_clip = next((c for c in updated_job.get("clips", []) if c["id"] == cid), clip)
    return {
        "ok": True,
        "clip": updated_clip,
        "scheduled": sched_info,
        "message": "Studio export triggered! Clip is re-rendering with your cuts, VFX & audio mix."
    }


@app.post("/api/jobs/{jid}/clips/{cid}/ai_seo")
def generate_clip_ai_seo(jid: str, cid: str, body: dict = Body(default={})):
    job, clip = _clip_or_404(jid, cid)
    model = body.get("model")
    tone = body.get("tone")
    d = Path(job["dir"])
    frame_payload = jobs.get_clip_frames_payload(job, clip, n_frames=6)

    words_file = d / "words.json"
    words = []
    if words_file.is_file():
        try:
            words = json.loads(words_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not words:
        words = job.get("words", [])
    clip_text = " ".join(w.get("w", "") for w in words if clip["start"] <= w.get("s", 0) <= clip["end"])

    streamer_name = job.get("creator") or job.get("uploader") or ""
    if not streamer_name or str(streamer_name).lower() in ("streamer", "none", ""):
        t = job.get("title", "")
        for known in ("ishowspeed", "speed", "ohnepixel", "kai cenat", "jynxzi", "sketch", "xqc", "adin ross", "gameranx"):
            if known in t.lower():
                streamer_name = "IShowSpeed" if known in ("ishowspeed", "speed") else known.title()
                break

    meta = None
    try:
        meta = brain.describe_multimodal(frame_payload, text=clip_text, title=job.get("title", ""),
                                         uploader=streamer_name, game=job.get("game"), model=model, tone=tone)
    except Exception as e:
        print(f"[ai_seo] Multimodal scan failed ({e}), falling back to text brain.describe", flush=True)
    if not meta or not meta.get("hook"):
        try:
            meta = brain.describe(clip_text or job.get("title", ""), title=job.get("title", ""),
                                  uploader=streamer_name, game=job.get("game"))
        except Exception:
            pass
    if not meta or not meta.get("hook"):
        raise HTTPException(500, "Could not generate AI SEO for this clip. Check your AI API key in Settings.")
    titles = meta.get("titles") or []
    if not titles or len(titles) < 3:
        try:
            titles = brain.generate_viral_titles(clip_text or job.get("title", ""),
                                                 title=job.get("title", ""),
                                                 uploader=streamer_name,
                                                 game=job.get("game"),
                                                 count=4)
        except Exception:
            titles = [meta["title"]]
    meta["titles"] = titles
    clip.update({
        "hook": meta["hook"],
        "hooks": meta.get("hooks", []),
        "title": meta["title"],
        "titles": meta.get("titles", []),
        "description": meta["description"],
        "hashtags": meta.get("hashtags", []),
        "seo_title": meta.get("seo_title", meta["title"]),
        "seo_tags": meta.get("seo_tags", []),
        "pinned_comment": meta.get("pinned_comment", ""),
    })
    jobs.save(job)
    clip_json = d / "clips" / f"{cid}.json"
    if clip_json.is_file():
        try:
            pj = json.loads(clip_json.read_text(encoding="utf-8"))
            pj.update({
                "hook": meta["hook"],
                "hooks": meta.get("hooks", []),
                "title": meta["title"],
                "titles": meta.get("titles", []),
                "description": meta["description"],
                "hashtags": meta.get("hashtags", []),
                "seo_title": meta.get("seo_title", meta["title"]),
                "seo_tags": meta.get("seo_tags", []),
                "pinned_comment": meta.get("pinned_comment", ""),
            })
            clip_json.write_text(json.dumps(pj, indent=1), encoding="utf-8")
        except Exception:
            pass
    return {"ok": True, "clip": clip, "hook": clip["hook"], "hooks": clip.get("hooks", []),
            "title": clip["title"], "titles": clip.get("titles", []),
            "description": clip["description"],
            "hashtags": clip.get("hashtags", []),
            "seo_title": clip["seo_title"], "seo_tags": clip["seo_tags"], "pinned_comment": clip["pinned_comment"]}


@app.delete("/api/jobs/{jid}")
def delete_job(jid: str):
    job = _job_or_404(jid)
    if job["status"] in ("queued", "running", "live") or jid in live.SESSIONS:
        raise HTTPException(409, "This is still being worked on. Stop it or wait for it to finish first.")
    jobs.delete(jid)
    return {"ok": True}


def _pairs(v, limit=300) -> list:
    """[[video id, clip id], ...] from the page, checked."""
    out = []
    for x in (v if isinstance(v, list) else [])[:limit]:
        if isinstance(x, (list, tuple)) and len(x) == 2 and all(isinstance(y, str) and re.fullmatch(r"[\w\-]{1,60}", y) for y in x):
            out.append((x[0], x[1]))
    return out


@app.delete("/api/jobs/{jid}/clips/{cid}")
def delete_clip(jid: str, cid: str):
    _job_or_404(jid)
    try:
        if not account.delete_clip(jid, cid):
            raise HTTPException(404, "No such clip")
    except account.Busy as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/bulk/delete")
def bulk_delete(body: dict = Body(...)):
    _throttle("bulkdel:" + ctx.uid(), 30, 600)
    vids = [x for x in (body.get("videos") if isinstance(body.get("videos"), list) else [])[:300]
            if isinstance(x, str) and re.fullmatch(r"[\w\-]{8,60}", x)]
    return account.delete_many(vids, _pairs(body.get("clips")))


@app.get("/api/clips.zip")
def clips_zip(ids: str = ""):
    """Many clips as one download. `ids` is video.clip pairs separated by commas."""
    _throttle("zip:" + ctx.uid(), 12, 600, "Give it a moment: you just downloaded several groups of clips.")
    pairs = _pairs([p.split(".", 1) for p in ids.split(",") if "." in p][:300])
    try:
        f = account.zip_clips(pairs)
    except ValueError as e:
        raise HTTPException(400, str(e))
    from starlette.background import BackgroundTask
    return FileResponse(f, filename=f"peakcut-clips-{len(pairs)}.zip", media_type="application/zip",
                        headers={"Cache-Control": "private, no-store"}, background=BackgroundTask(lambda: f.unlink(missing_ok=True)))


@app.delete("/api/creators/{cid}")
def delete_creator(cid: str):
    _throttle("cdel:" + ctx.uid(), 30, 600)
    try:
        r = account.delete_creator(cid)
    except account.Busy as e:
        raise HTTPException(409, str(e))
    if not r.get("ok"):
        raise HTTPException(404, "No such creator")
    return r


@app.post("/api/account/delete")
def delete_my_account(request: Request, body: dict = Body(...)):
    """Deletes the signed-in account and everything in it. The page asks for the email to be typed, so it cannot
    happen by a stray click or a request the person did not mean to make."""
    me_ = _me(request)
    if str(body.get("confirm") or "").strip().lower() != me_.email.lower():
        raise HTTPException(400, "Type your email address exactly to confirm.")
    try:
        account.delete_account(me_.id)
    except account.Busy as e:
        raise HTTPException(409, str(e))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.cookie_args("x")["key"], path="/")
    return resp


@app.get("/media/{jid}/{name}")
def media_file(jid: str, name: str, download: int = 0):
    if not re.fullmatch(r"[\w\-\.]+\.(mp4|jpg)", name) or ".." in name:
        raise HTTPException(404)
    job = _job_or_404(jid)
    f = Path(job["dir"]) / "clips" / name
    if not f.is_file():
        if name == "thumb.jpg":
            # Smart thumbnail fallback: if thumb.jpg does not exist, serve first available clip thumbnail
            clips_dir = Path(job["dir"]) / "clips"
            if clips_dir.is_dir():
                first_clip_jpg = next((p for p in sorted(clips_dir.glob("clip*.jpg")) if p.is_file()), None)
                if first_clip_jpg:
                    return FileResponse(first_clip_jpg, headers={"Cache-Control": "private, max-age=300"})
        raise HTTPException(404)
    save_as = name
    if download and name.endswith(".mp4"):
        # a clip is saved under its title, not "clip01.mp4", the same as when several are downloaded as a zip
        clip = next((c for c in job.get("clips", []) if Path(str(c.get("file") or "")).name == name), None)
        if clip:
            save_as = account.clip_title_name(clip, Path(name).stem) + ".mp4"
    return FileResponse(f, filename=save_as if download else None, headers={"Cache-Control": "private, max-age=300"})


# ================================================================ Background Music & Meme Sounds
@app.get("/api/audio/tracks")
def audio_tracks():
    from . import audio
    return {"ok": True, "tracks": audio.list_tracks()}


@app.api_route("/api/audio/track/{track_id}", methods=["GET", "HEAD"])
def audio_track_file(track_id: str):
    from . import audio
    p = audio.get_track_path(track_id)
    if not p or not p.is_file():
        raise HTTPException(404, "Audio track not found.")
    ext = p.suffix.lower()
    media_type = "audio/mpeg" if ext == ".mp3" else ("audio/wav" if ext == ".wav" else "audio/mp4")
    return FileResponse(p, media_type=media_type, headers={"Cache-Control": "public, max-age=604800, stale-while-revalidate=86400"})


@app.post("/api/audio/upload")
async def audio_upload(file: UploadFile = File(...)):
    from . import audio
    if not file.filename:
        raise HTTPException(400, "No file provided.")
    content = await file.read()
    try:
        track = audio.save_upload(file.filename, content)
        return {"ok": True, "track": track}
    except ValueError as err:
        raise HTTPException(400, str(err))


# ================================================================ creators and live recording
def _channel_ok(body: dict):
    links = [str(body.get("channel") or "").strip()]
    chs = body.get("channels")
    if chs is not None and not isinstance(chs, dict):
        raise HTTPException(400, "Bad channel list.")
    for plat, url in (chs or {}).items():
        url = str(url or "").strip()
        if url and creators.platform_key(url) != plat:
            raise HTTPException(400, f"That link isn't a {plat.title()} channel.")
        links.append(url)
    for ch in links:
        if ch and not media.site_allowed(live.normalize(ch)):
            raise HTTPException(400, "Channel links must be from YouTube, Twitch or Kick.")


@app.get("/api/admin/email-preview")
def email_preview(request: Request, kind: str = "verify"):
    """What account emails look like, for admins."""
    from . import mailer
    _admin(request)
    if kind == "reset":
        page = mailer.preview("Reset your password", "Someone asked to reset the password for this PeakCut account. If that was you, choose a new one below.",
                              "Choose a new password", config.PUBLIC_URL + "/reset?t=example",
                              "The link works for one hour. If you didn't ask for this, ignore this email and your password stays the same.")
    else:
        page = mailer.preview()
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


@app.post("/api/admin/test-email")
def test_email(request: Request):
    """Send the confirm-email template to the admin, to check the email service works."""
    from . import mailer
    me_ = _admin(request)
    if not mailer.ready():
        raise HTTPException(400, "No email service is set up yet. Add the PEAKCUT_SMTP settings to .env first.")
    mailer.send(me_.email, "PeakCut test email", "Your emails are working",
                "This is a test from your PeakCut server. Account emails like this one will now reach people.",
                "Open PeakCut", config.PUBLIC_URL + "/app", "You can ignore this message.")
    return {"sent_to": me_.email}


@app.post("/api/feedback")
def send_feedback(request: Request, body: dict = Body(...)):
    from . import feedback
    u = _me(request)
    try:
        auth.throttle("feedback:" + u.id, 10, 3600)
        return feedback.submit(u.id, str(body.get("kind", "")), str(body.get("message", "")),
                               str(body.get("page", "")), str(body.get("context", "")))
    except auth.AuthError:
        raise HTTPException(429, "You've sent a lot of messages in the last hour. Try again a bit later.")
    except feedback.Refused as e:
        raise HTTPException(400, str(e))


@app.get("/api/admin/feedback")
def admin_feedback(request: Request, status: str = ""):
    from . import feedback
    _admin(request)
    return feedback.listing(status)


@app.post("/api/admin/feedback/{fid}")
def admin_feedback_status(request: Request, fid: int, body: dict = Body(...)):
    from . import feedback
    _admin(request)
    try:
        feedback.set_status(fid, str(body.get("status", "")))
    except feedback.Refused as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.get("/api/notifications")
def notifications_list():
    from . import notices
    return notices.mine()


@app.post("/api/notifications/read")
def notifications_read():
    from . import notices
    notices.read_all()
    return {"ok": True}


@app.get("/api/me/photo")
def my_photo(request: Request):
    u = _me(request)
    got = auth.photo(u.id) if u else None
    if not got:
        raise HTTPException(404)
    return FileResponse(got[0], media_type=got[1], headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/channel-preview")
def channel_preview(request: Request, url: str = ""):
    url = url.strip()[:300]
    if not url or not media.site_allowed(live.normalize(url)):
        raise HTTPException(400, "Paste a YouTube, Twitch or Kick channel link.")
    try:
        auth.throttle(f"chanprev:{_me(request).id}", 12, 60)
    except auth.AuthError:
        raise HTTPException(429, "Too many lookups at once. Wait a moment.")
    try:
        return _lookup(profiles.preview, url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Couldn't open that channel. Check the link.")


@app.get("/api/creators/{cid}/avatar")
def creator_avatar(cid: str, p: str = ""):
    c = creators.get(cid)
    if not c:
        raise HTTPException(404)
    key = p if p in creators.PLATFORMS else creators.platform_key(c["channel"])
    prof = (c.get("profiles") or {}).get(key) or {}
    f = creators.root(cid) / f"avatar-{key}.img"
    if not f.is_file() or prof.get("pic") not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(404)
    return FileResponse(f, media_type=prof["pic"], headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/creators")
def list_creators():
    return _creator_rows()


@app.post("/api/creators")
def new_creator(body: dict = Body(...)):
    _channel_ok(body)
    if len(creators.all_creators()) >= config.MAX_CREATORS:
        raise HTTPException(400, f"This server allows {config.MAX_CREATORS} creators per account.")
    try:
        c = creators.create(body)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if c.get("channels"):
        profiles.refresh(c["id"], force=True)
    return c


@app.put("/api/creators/{cid}")
def edit_creator(cid: str, body: dict = Body(...)):
    _throttle("cedit:" + ctx.uid(), 60, 600)
    _channel_ok(body)
    try:
        c = creators.update(cid, body)
    except KeyError:
        raise HTTPException(404, "No such creator")
    except ValueError as e:
        raise HTTPException(400, str(e))
    s = live.active_for(cid)
    if s:
        s.settings = c  # new settings apply to the running recording straight away
        s.game = None   # clear cached game detection so new setting takes effect
        if "captions" in c:
            s.job.setdefault("options", {})["captions"] = c["captions"]
        if "layout" in c:
            s.job.setdefault("options", {})["layout"] = c["layout"]
        if "style" in c:
            s.job.setdefault("options", {})["style"] = c["style"]
        if "quality" in c:
            s.job.setdefault("options", {})["quality"] = c["quality"]
        jobs.save(s.job)
    if "channels" in body or "channel" in body:
        profiles.refresh(cid, force=True)
    if body.get("auto_watch") and c.get("auto_watch") and not s:
        live.check_now(cid)    # if they are live right now, recording starts within seconds
    return c


@app.get("/api/creators/{cid}/frame")
def get_creator_frame(cid: str, request: Request, t: float = 2.0, cb: str = ""):
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")

    # Sanitize t: JS Date.now() sends millisecond epoch (>3600.0). Clamp to safe offset.
    if t > 3600.0 or t < 0.0:
        t = 2.0

    # 1. Check if recording session is active right now
    s = live.active_for(cid)
    if s:
        segs = sorted(s.buf.glob("*.ts"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not segs:
            segs = sorted(s.buf.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        for seg in segs[:3]:
            b = jobs._extract_frame_bytes(seg, 0.5)
            if not b:
                b = jobs._extract_frame_bytes(seg, 0.0)
            if b:
                return Response(content=b, media_type="image/jpeg",
                                headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    # 2. Check for recent clips or videos in creator workspace
    c_root = creators.root(cid)
    recent_vids = sorted(c_root.glob("live/*/clips/*.src.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    recent_vids += sorted(c_root.glob("videos/*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    recent_vids += sorted(c_root.glob("live/*/clips/*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    for vid in recent_vids[:5]:
        b = jobs._extract_frame_bytes(vid, t)
        if not b and abs(t - 1.0) > 0.1:
            b = jobs._extract_frame_bytes(vid, 1.0)
        if not b:
            b = jobs._extract_frame_bytes(vid, 0.2)
        if b:
            return Response(content=b, media_type="image/jpeg",
                            headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    # 3. Check for Twitch preview thumbnail if twitch channel is configured
    tw_channel = c.get("channels", {}).get("twitch") or (c.get("channel") if "twitch" in (c.get("channel") or "") else "")
    if not tw_channel and cid.lower() in ("ohnepixel", "ishowspeed", "kaicenat"):
        tw_channel = cid.lower()
    if tw_channel:
        import urllib.request
        username = tw_channel.rstrip("/").split("/")[-1].lower()
        tw_thumb_url = f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{username}-1920x1080.jpg?cb={int(time.time())}"
        try:
            req = urllib.request.Request(tw_thumb_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 5000:
                        return Response(content=data, media_type="image/jpeg",
                                        headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        except Exception:
            pass

    # 4. Check for any clip cover in workspace
    for cover in sorted(c_root.glob("live/*/clips/*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True):
        if cover.is_file() and cover.stat().st_size > 1000:
            return FileResponse(cover, media_type="image/jpeg", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    # 5. Check global video clips in user folder as realistic fallback
    try:
        user_root = c_root.parent.parent
        all_vids = sorted(user_root.glob("creators/*/live/*/clips/*.src.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if all_vids:
            b = jobs._extract_frame_bytes(all_vids[0], 2.0) or jobs._extract_frame_bytes(all_vids[0], 0.5)
            if b:
                return Response(content=b, media_type="image/jpeg", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    except Exception:
        pass

    # 6. Clean 1920x1080 visual studio grid fallback
    from PIL import Image, ImageDraw
    import io
    img = Image.new("RGB", (1920, 1080), (18, 20, 26))
    d = ImageDraw.Draw(img)
    for x in range(0, 1920, 160):
        d.line([(x, 0), (x, 1080)], fill=(28, 32, 42), width=1)
    for y in range(0, 1080, 120):
        d.line([(0, y), (1920, y)], fill=(28, 32, 42), width=1)
    d.rectangle([(20, 20), (520, 395)], outline=(0, 240, 255), width=3)
    d.text((40, 40), f"{c.get('name', 'Streamer')} Webcam Area", fill=(0, 240, 255))
    d.rectangle([(480, 0), (1920, 1080)], outline=(255, 140, 0), width=2)
    d.text((520, 40), "Gameplay & Action Area", fill=(255, 140, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return Response(content=buf.getvalue(), media_type="image/jpeg")


@app.get("/api/jobs/{jid}/frame")
def get_job_frame(jid: str, cid: str = None, t: float = 2.0, cb: str = ""):
    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")

    # Sanitize t: JS Date.now() sends millisecond epoch (>3600.0). Clamp to safe offset.
    if t > 3600.0 or t < 0.0:
        t = 2.0

    jdir = Path(job.get("dir", ""))
    # If a specific clip id is passed, prioritize extracting directly from that clip's source!
    if cid:
        c_src = jdir / "clips" / f"{cid}.src.mp4"
        if c_src.is_file():
            b = jobs._extract_frame_bytes(c_src, min(2.0, t)) or jobs._extract_frame_bytes(c_src, 0.5)
            if b:
                return Response(content=b, media_type="image/jpeg",
                                headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
        c_cover = jdir / "clips" / f"{cid}.jpg"
        if c_cover.is_file() and c_cover.stat().st_size > 1000:
            return FileResponse(c_cover, media_type="image/jpeg",
                                headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

    src = Path(job.get("source_path") or job.get("src") or "")
    if not src.is_file():
        jdir = Path(job.get("dir", ""))
        segs = sorted((jdir / "buffer").glob("*.ts"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not segs:
            segs = sorted((jdir / "buffer").glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if segs:
            src = segs[0]
        else:
            recent_vids = sorted((jdir / "clips").glob("*.src.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if recent_vids:
                src = recent_vids[0]
    if src.is_file():
        b = jobs._extract_frame_bytes(src, max(0.0, t))
        if not b and abs(t - 1.0) > 0.1:
            b = jobs._extract_frame_bytes(src, 1.0)
        if not b:
            b = jobs._extract_frame_bytes(src, 0.2)
        if b:
            return Response(content=b, media_type="image/jpeg",
                            headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    jdir = Path(job.get("dir", ""))
    for c in sorted((jdir / "clips").glob("*.jpg")):
        if c.is_file() and c.stat().st_size > 1000:
            return FileResponse(c, media_type="image/jpeg")
    raise HTTPException(404, "No frames available")


@app.post("/api/creators/{cid}/custom-layout")
def save_creator_custom_layout(cid: str, body: dict = Body(...)):
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    custom_layout = body.get("custom_layout") if "custom_layout" in body else body
    cl = {
        "enabled": bool(custom_layout.get("enabled", True)),
        "mode": str(custom_layout.get("mode", "split")).lower(),
        "split_ratio": max(0.15, min(0.85, float(custom_layout.get("split_ratio", 0.35)))),
        "pip_pos": str(custom_layout.get("pip_pos", "top-right")).lower(),
        "pip_size": max(100, min(800, int(custom_layout.get("pip_size", 380)))),
        "divider": bool(custom_layout.get("divider", True)),
    }
    try:
        cl["facecam"] = [max(0, int(v)) for v in custom_layout.get("facecam", [0, 0, 480, 360])[:4]]
    except Exception:
        cl["facecam"] = [0, 0, 480, 360]
    try:
        cl["gameplay"] = [max(0, int(v)) for v in custom_layout.get("gameplay", [0, 0, 1920, 1080])[:4]]
    except Exception:
        cl["gameplay"] = [0, 0, 1920, 1080]

    update_data = {
        "custom_layout": cl
    }
    if body.get("set_default") is True:
        update_data["layout"] = "custom"
    if cl.get("facecam"):
        update_data["facecam_pos"] = cl.get("pip_pos", "top-right")
    updated = creators.update(cid, update_data)
    s = live.active_for(cid)
    if s:
        s.settings["custom_layout"] = cl
        s.job.setdefault("options", {})["custom_layout"] = cl
        if body.get("set_default") is True:
            s.job.setdefault("options", {})["layout"] = "custom"
        jobs.save(s.job)
    return {"ok": True, "custom_layout": cl, "creator": updated}


@app.get("/api/creators/{cid}/presets")
def get_creator_presets(cid: str):
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    return {"presets": c.get("custom_presets") or {}}


@app.post("/api/creators/{cid}/presets")
def save_creator_preset(cid: str, body: dict = Body(...)):
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    pname = str(body.get("name") or "").strip()[:50]
    if not pname:
        raise HTTPException(400, "Preset name is required")
    pdata = body.get("preset") or body
    p_obj = {
        "name": pname,
        "mode": str(pdata.get("mode", "split")).lower(),
        "split_ratio": max(0.15, min(0.85, float(pdata.get("split_ratio", 0.35)))),
        "pip_pos": str(pdata.get("pip_pos", "top-right")).lower(),
        "pip_size": max(100, min(800, int(pdata.get("pip_size", 380)))),
        "divider": bool(pdata.get("divider", True))
    }
    try:
        p_obj["facecam"] = [max(0, int(x)) for x in pdata.get("facecam", [0, 0, 480, 360])[:4]]
    except Exception:
        p_obj["facecam"] = [0, 0, 480, 360]
    try:
        p_obj["gameplay"] = [max(0, int(x)) for x in pdata.get("gameplay", [0, 0, 1920, 1080])[:4]]
    except Exception:
        p_obj["gameplay"] = [0, 0, 1920, 1080]

    presets = dict(c.get("custom_presets") or {})
    presets[pname] = p_obj
    update_data = {
        "custom_presets": presets,
        "active_preset": pname,
        "layout": "custom",
        "custom_layout": {**p_obj, "enabled": True}
    }
    updated = creators.update(cid, update_data)
    return {"ok": True, "name": pname, "presets": presets, "active_preset": pname, "creator": updated}


@app.post("/api/creators/{cid}/presets/{name}/activate")
def activate_creator_preset(cid: str, name: str):
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    presets = dict(c.get("custom_presets") or {})
    if name not in presets:
        raise HTTPException(404, f"Preset '{name}' not found")
    p_obj = presets[name]
    update_data = {
        "active_preset": name,
        "layout": "custom",
        "custom_layout": {**p_obj, "enabled": True}
    }
    updated = creators.update(cid, update_data)
    return {"ok": True, "presets": presets, "active_preset": name, "creator": updated}


@app.delete("/api/creators/{cid}/presets/{name}")
def delete_creator_preset(cid: str, name: str):
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    presets = dict(c.get("custom_presets") or {})
    update_data = {}
    if name in presets:
        del presets[name]
        update_data["custom_presets"] = presets
        if c.get("active_preset") == name:
            update_data["active_preset"] = next(iter(presets.keys())) if presets else ""
            if update_data["active_preset"]:
                p_next = presets[update_data["active_preset"]]
                update_data["custom_layout"] = {**p_next, "enabled": True}
        creators.update(cid, update_data)
    return {"ok": True, "presets": presets, "active_preset": update_data.get("active_preset", c.get("active_preset"))}


@app.post("/api/creators/{cid}/live")
def go_live(cid: str, body: dict = Body(default={})):
    _need_verified()
    try:
        c = creators.get(cid)
    except ValueError:
        c = None
    if not c:
        raise HTTPException(404, "No such creator")
    # The stream requested, else the primary channel chosen in creator settings, else any live channel
    on_air = [p["channel"] for k, p in (c.get("profiles") or {}).items() if p.get("live") and c.get("channels", {}).get(k) == p.get("channel")]
    asked = str((body or {}).get("channel") or "").strip()
    if asked and (asked in c.get("channels", {}).values() or asked == c.get("channel")):
        url = asked
    elif c.get("channel"):
        url = c["channel"]
    elif on_air:
        url = on_air[0]
    else:
        url = next(iter(c.get("channels", {}).values()), "")
    try:
        return jobs.public(live.start_session(c, url))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/live/{jid}/stop")
def stop_live(jid: str):
    s = live.mine(jid)
    if not s:
        raise HTTPException(404, "This recording has already ended")
    s.stop()
    return {"ok": True}


@app.post("/api/live/{jid}/clip")
def clip_now(jid: str, body: dict = Body(...)):
    s = live.mine(jid)
    if not s or s.ended:
        raise HTTPException(404, "This recording has already ended")
    _throttle("clipnow:" + ctx.uid(), 6, 60, "Give it a moment: your last clips are still being made.")
    if len(s.manual) >= 3:
        raise HTTPException(429, "Give it a moment: your last clips are still being made.")
    try:
        s.clip_last(max(5, min(180, float(body.get("seconds", 30)))))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ================================================================ AI usage
@app.get("/api/usage")
def ai_usage():
    return usage.summary({c["id"]: c["name"] for c in creators.all_creators()})


# ---------------------------------------------------------------- the AI key and model, set from the dashboard
# Only the owner (or an admin, when accounts are on) reaches these. The key is never sent back to the page.
def _ai_error(e) -> str:
    return safe.friendly(e, 300).replace(ai.key() or "\0", "<key>")


@app.post("/api/ai/clear-problem")
def ai_clear_problem(request: Request):
    ai.clear_problem()
    usage.forget_all()
    ctx.bump()
    return {"ok": True}


@app.get("/api/ai")
def ai_get(request: Request):
    _admin(request)
    return ai.public()


@app.put("/api/ai")
def ai_put(request: Request, body: dict = Body(...)):
    _admin(request)
    k = body.get("key")
    try:
        out = ai.save(body.get("provider"), body.get("models"), body.get("base_url") or "",
                      None if k is None or (isinstance(k, str) and not k.strip() and not body.get("remove_key")) else str(k))
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    usage.forget_all()
    ctx.bump()
    return out


@app.post("/api/ai/keys")
def ai_add_key(request: Request, body: dict = Body(...)):
    _admin(request)
    k = body.get("key")
    if not k:
        raise HTTPException(400, "API key cannot be empty.")
    try:
        out = ai.add_key(k)
    except ValueError as e:
        raise HTTPException(400, str(e))
    usage.forget_all()
    ctx.bump()
    return out


@app.delete("/api/ai/keys/{idx}")
def ai_remove_key(request: Request, idx: int):
    _admin(request)
    try:
        out = ai.remove_key(idx)
    except ValueError as e:
        raise HTTPException(400, str(e))
    usage.forget_all()
    ctx.bump()
    return out


@app.get("/api/ai/catalog")
def ai_catalog(request: Request, provider: str | None = None):
    return ai.get_catalog(provider_id=provider)


@app.post("/api/ai/switch")
def ai_switch(request: Request, body: dict = Body(default={})):
    _admin(request)
    prov = body.get("provider")
    model = body.get("model")
    if not prov or not model:
        raise HTTPException(400, "Provider and Model required.")
    try:
        out = ai.switch_model(prov, model)
        test_res = {}
        try:
            test_res = ai.test_key()
        except Exception as e:
            test_res = {"ok": False, "error": str(e)}
        out["test"] = test_res
        ctx.bump()
        return out
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, str(e))


@app.post("/api/ai/keys/{idx}/activate")
def ai_activate_key(request: Request, idx: int):
    _admin(request)
    try:
        out = ai.activate_key(idx)
    except ValueError as e:
        raise HTTPException(400, str(e))
    ctx.bump()
    return out


@app.post("/api/ai/models/select")
def ai_select_model(request: Request, body: dict = Body(default={})):
    _admin(request)
    model = body.get("model")
    if not model:
        raise HTTPException(400, "Model ID required.")
    try:
        out = ai.select_primary_model(model)
    except ValueError as e:
        raise HTTPException(400, str(e))
    ctx.bump()
    return out


@app.post("/api/ai/keys/{idx}/test")
def ai_test_key(request: Request, idx: int):
    _admin(request)
    _throttle("aitest:" + ctx.uid(), 40, 600)
    try:
        return ai.test_key(index=idx)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(502, str(e))


@app.post("/api/ai/keys/test-all")
def ai_test_all_keys(request: Request):
    _admin(request)
    _throttle("aitest_all:" + ctx.uid(), 20, 600)
    try:
        return {"results": ai.test_all_keys()}
    except Exception as e:
        raise HTTPException(502, str(e))


@app.post("/api/ai/models")
def ai_models(request: Request, body: dict = Body(default={})):
    _admin(request)
    _throttle("aimodels:" + ctx.uid(), 30, 600)
    try:
        return {"models": ai.list_models(body.get("provider"), body.get("base_url"), body.get("key"))}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        reason = ai.explain(e)
        raise HTTPException(502, f"The service did not give its list of models. {reason}" if reason else
                            "The service did not give its list of models. Check the key, or type the model yourself. " + _ai_error(e)[:160])


@app.post("/api/ai/test")
def ai_test(request: Request):
    _admin(request)
    _throttle("aitest:" + ctx.uid(), 20, 600)
    try:
        return ai.test()
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, ai.explain(e) or "The AI did not answer: " + _ai_error(e))


# ---------------------------------------------------------------- speech models, one per spoken language
# Only the owner (or an admin, when accounts are on) can download or delete them: they are shared by everyone here.
def _speech_lang(lang: str) -> str:
    from . import fetch_model
    if not fetch_model.known(lang):
        raise HTTPException(400, "PeakCut has no speech model for that language.")
    return lang


@app.get("/api/speech")
def speech_list(request: Request):
    _admin(request)
    from . import fetch_model
    return {"models": [{"lang": k, "label": m[0], "size_mb": m[3], "credit": m[4], "state": fetch_model.status(k),
                        "percent": fetch_model.state[k]["percent"], "error": fetch_model.state[k]["error"],
                        "default": k == fetch_model.DEFAULT} for k, m in fetch_model.MODELS.items()]}


@app.post("/api/speech/{lang}")
def speech_download(request: Request, lang: str):
    _admin(request)
    from . import fetch_model
    fetch_model.start(_speech_lang(lang))
    ctx.bump()
    return speech_list(request)


@app.delete("/api/speech/{lang}")
def speech_remove(request: Request, lang: str):
    _admin(request)
    from . import fetch_model
    try:
        fetch_model.remove(_speech_lang(lang))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    ctx.bump()
    return speech_list(request)


# ================================================================ posting, accounts, settings
@app.get("/api/overview")
def overview():
    return posting.overview()


@app.get("/api/settings")
def get_settings():
    return accounts.public_settings()


@app.put("/api/settings")
def put_settings(body: dict = Body(...)):
    try:
        accounts.save_settings(body)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e))
    return accounts.public_settings()


@app.get("/api/accounts")
def list_accounts():
    return accounts.list_accounts()


@app.delete("/api/accounts/{aid}")
def remove_account(aid: str):
    accounts.remove(aid)
    return {"ok": True}


# ---------------------------------------------------------------- connecting YouTube, Instagram and TikTok
# Connect sends the browser to the platform's own sign-in page; the platform sends it back here, and the person lands
# on Settings, Connected apps, with the account added (or a message saying what went wrong).
def _back(**q):
    from urllib.parse import urlencode as _ue
    return RedirectResponse("/app/settings/apps?" + _ue(q), 303)


@app.get("/oauth/{platform}/start")
def connect_start(platform: str):
    if platform not in accounts.PLATFORM_NAMES:
        raise HTTPException(404)
    try:
        return RedirectResponse(accounts.connect_url(platform), 303)
    except ValueError as e:
        return _back(connect_error=str(e))


@app.get("/oauth/{platform}/callback")
def connect_callback(platform: str, code: str = "", state: str = "", error: str = "", error_description: str = "",
                     error_reason: str = ""):
    if platform not in accounts.PLATFORM_NAMES:
        raise HTTPException(404)
    name = accounts.PLATFORM_NAMES[platform]
    if error or not code:
        why = "you cancelled" if error in ("access_denied",) or error_reason == "user_denied" else (error_description or error or "no sign-in code came back")
        return _back(connect_error=f"{name} was not connected: {why[:160]}.")
    try:
        _throttle("connect:" + ctx.uid(), 30, 600)
        acc = accounts.connect_finish(platform, code, state)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        return _back(connect_error=f"{name} was not connected: {safe.friendly(e, 240)}")
    return _back(connected=platform, name=acc["name"])


@app.get("/pub/{token}.mp4")
def public_clip(token: str):
    """A clip for a platform to fetch while posting it: one clip, one hour, signed (see accounts.clip_link)."""
    got = accounts.read_clip_link(token)
    if not got:
        raise HTTPException(404)
    uid, job_id, name = got
    with ctx.as_user(uid):
        job = jobs.get(job_id) if re.fullmatch(r"[\w\-]{8,60}", job_id) else None
        f = Path(job["dir"]) / "clips" / name if job else None
    if not f or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, media_type="video/mp4", headers={"Cache-Control": "private, no-store"})


# ---------------------------------------------------------------- where PeakCut keeps everything (Settings, Storage)
def _on_this_computer(request: Request) -> bool:
    """Is the person sitting at the computer PeakCut runs on? Only then can a folder window be opened for them."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost") and not config.env("PEAKCUT_TRUST_PROXY")


@app.get("/api/storage")
def storage_get(request: Request):
    from . import storage
    _admin(request)
    return storage.info(_on_this_computer(request))


@app.post("/api/storage/open")
def storage_open(request: Request):
    from . import storage
    _admin(request)
    if not _on_this_computer(request):
        raise HTTPException(400, "The folder can only be opened on the computer PeakCut runs on.")
    try:
        storage.open_folder()
    except OSError as e:
        raise HTTPException(500, "Couldn't open the folder: " + safe.friendly(e, 200))
    return {"ok": True}


@app.post("/api/storage/pick")
def storage_pick(request: Request):
    from . import storage
    _admin(request)
    if not _on_this_computer(request):
        raise HTTPException(400, "Type the folder's path instead: a folder window can only be shown on the computer PeakCut runs on.")
    return {"path": storage.pick_folder()}


@app.put("/api/storage")
def storage_put(request: Request, body: dict = Body(...)):
    from . import storage
    _admin(request)
    try:
        if body.get("cancel"):
            storage.cancel_change()
            return storage.info(_on_this_computer(request))
        storage.change(str(body.get("path") or ""), bool(body.get("move", True)))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return storage.info(_on_this_computer(request))


@app.get("/api/apps")
def apps_get(request: Request):
    _admin(request)
    return accounts.apps_public()


@app.put("/api/apps")
def apps_put(request: Request, body: dict = Body(...)):
    _admin(request)
    try:
        return accounts.save_app(str(body.get("platform", "")), body.get("client_id"), body.get("client_secret"))
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- YouTube cookies, for servers YouTube refuses
# A secret like a password: it is saved to a file only this server reads, and never sent back to the page.
@app.get("/api/youtube-cookies")
def yt_cookies_get(request: Request):
    _admin(request)
    f = config.YT_COOKIES
    return {"saved": f.is_file(), "updated": int(f.stat().st_mtime) if f.is_file() else 0}


@app.put("/api/youtube-cookies")
def yt_cookies_put(request: Request, body: dict = Body(...)):
    _admin(request)
    f, text = config.YT_COOKIES, str(body.get("text") or "")
    if body.get("remove"):
        f.unlink(missing_ok=True)
    else:
        rows = [l.split("\t") for l in text.splitlines() if l.strip() and not l.startswith("# ")]
        if len(text) > 1_000_000 or not any(len(r) == 7 and "youtube.com" in r[0] for r in rows):
            raise HTTPException(400, "That doesn't look like a cookies.txt file with YouTube cookies in it. Export it "
                                     "from a browser signed in to YouTube, with an extension such as \"Get cookies.txt LOCALLY\".")
        text = text if text.startswith("# Netscape") else "# Netscape HTTP Cookie File\n" + text
        f.write_text(text, encoding="utf-8")
        with contextlib.suppress(OSError):
            f.chmod(0o600)
    media._yt_refused_until = 0.0        # try YouTube again straight away
    return yt_cookies_get(request)


@app.post("/api/posts")
def add_posts(body: dict = Body(...)):
    job = jobs.get(str(body.get("job")))
    clip = next((c for c in job["clips"] if c["id"] == body.get("clip")), None) if job else None
    if not clip or clip.get("status") != "done":
        raise HTTPException(404, "That clip is not ready")
    accounts_list = [str(a) for a in body.get("accounts", [])][:20]
    if not accounts_list:
        raise HTTPException(400, "Tick at least one account first.")
    now = bool(body.get("now"))
    made = posting.enqueue(job, clip, accounts_list, now=now, force=now)
    if not made:
        made = posting.enqueue(job, clip, accounts_list, now=now, force=True)
    if not made:
        raise HTTPException(400, "Nothing was queued. Pick at least one account.")
    return {"queued": len(made)}


@app.post("/api/posts/{pid}/{action}")
def post_action(pid: str, action: str):
    try:
        handler = {
            "cancel": posting.cancel,
            "retry": posting.retry,
            "delete": lambda p_id: posting.delete_post(p_id, delete_remote=True),
        }.get(action)
        if not handler:
            raise KeyError(action)
        res = handler(pid)
        return {"ok": True, "result": res}
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/posts/{pid}")
def delete_post_endpoint(pid: str):
    try:
        res = posting.delete_post(pid, delete_remote=True)
        return {"ok": True, "result": res}
    except KeyError:
        raise HTTPException(404, "Post not found")
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/jobs/{jid}/clips/{cid}/unschedule")
def unschedule_clip(jid: str, cid: str):
    _job_or_404(jid)
    cancelled = posting.cancel_clip(jid, cid)
    return {"ok": True, "cancelled": cancelled}


@app.post("/api/bulk/unschedule")
def bulk_unschedule(body: dict = Body(...)):
    _throttle("bulkunsched:" + ctx.uid(), 30, 600)
    clips = body.get("clips", [])
    total_cancelled = 0
    for item in clips:
        if isinstance(item, str) and item.startswith("c:"):
            parts = item.split(":")
            if len(parts) >= 3:
                total_cancelled += posting.cancel_clip(parts[1], parts[2])
        elif isinstance(item, dict):
            jid = item.get("job")
            cid = item.get("clip")
            if jid and cid:
                total_cancelled += posting.cancel_clip(jid, cid)
    return {"ok": True, "cancelled": total_cancelled}


@app.get("/api/calendar/slots")
def get_calendar_slots(account_id: str = None, count: int = 6):
    """Returns the upcoming available publishing slots according to the USA-focused calendar."""
    _throttle("calslots:" + ctx.uid(), 60, 60)
    slots = calendar.assign_slots_to_videos(account_id, posting._mine(), count=min(max(count, 1), 30))
    return {
        "slots": slots,
        "max_per_day": calendar.MAX_VIDEOS_PER_DAY,
        "min_gap_hours": 6,
        "tz_pkt": "UTC+5 (Pakistan Standard Time)",
        "tz_us_east": "US Eastern Time",
        "tz_us_west": "US Pacific Time"
    }


@app.get("/api/creators/{cid}/calendar")
def get_creator_calendar(cid: str):
    """Returns the full publishing calendar schedule, slots, and queued videos for a specific creator."""
    _throttle("creatorcal:" + ctx.uid(), 60, 60)
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")

    now_ts = time.time()
    all_mine = posting._mine()
    c_posts = [p for p in all_mine if p.get("creator") == cid]

    # Collect scheduled posts: open in local queue OR future scheduled on platform
    scheduled_posts = []
    seen_post_ids = set()
    for p in c_posts:
        if p.get("status") in ("cancelled", "deleted"):
            continue
        sched_t = float(p.get("scheduled_at") or p.get("due_at") or (p.get("calendar_slot", {}).get("video_ts") if isinstance(p.get("calendar_slot"), dict) else 0) or 0)
        is_future = sched_t > now_ts + 60
        if p.get("status") in posting.OPEN or is_future or p.get("is_scheduled"):
            scheduled_posts.append(p)
            seen_post_ids.add(p.get("id"))

    # Also harvest any future scheduled posts stored on clips directly
    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())
    all_jobs = {j["id"]: j for j in jobs.list_jobs() if j.get("creator") == cid}
    for j in all_jobs.values():
        for clip in j.get("clips", []):
            for pid, pdata in (clip.get("posts") or {}).items():
                if pid not in seen_post_ids and isinstance(pdata, dict):
                    if pdata.get("status") in ("cancelled", "deleted"):
                        continue
                    sched_t = float(pdata.get("scheduled_at") or pdata.get("due_at") or (pdata.get("calendar_slot", {}).get("video_ts") if isinstance(pdata.get("calendar_slot"), dict) else 0) or 0)
                    if pdata.get("status") in posting.OPEN or sched_t > now_ts + 60 or pdata.get("is_scheduled"):
                        post_copy = dict(pdata)
                        post_copy["id"] = pid
                        post_copy["job"] = j["id"]
                        post_copy["clip"] = clip.get("id")
                        post_copy["creator"] = cid
                        post_copy["cover"] = clip.get("cover") or f"{clip['id']}.jpg"
                        post_copy["file"] = clip.get("file") or ""
                        post_copy["hook"] = clip.get("hook") or ""
                        post_copy["title"] = clip.get("title") or clip.get("hook") or post_copy.get("title") or "Short"
                        post_copy["reason"] = clip.get("reason") or ""
                        post_copy["clip_status"] = clip.get("status") or "done"
                        scheduled_posts.append(post_copy)
                        seen_post_ids.add(pid)

    scheduled_posts.sort(key=lambda p: float(p.get("scheduled_at") or p.get("due_at") or (p.get("calendar_slot", {}).get("video_ts") if isinstance(p.get("calendar_slot"), dict) else 0) or 0))

    recent_posted = [p for p in c_posts if p.get("status") == "posted" and p.get("id") not in seen_post_ids]
    recent_posted.sort(key=lambda p: -float(p.get("posted_at") or p.get("due_at") or 0))
    recent_posted = recent_posted[:10]

    for p in scheduled_posts + recent_posted:
        j = all_jobs.get(p.get("job"))
        if j:
            clip = next((k for k in j.get("clips", []) if k.get("id") == p.get("clip")), None)
            if clip:
                p["cover"] = clip.get("cover") or f"{clip['id']}.jpg"
                p["file"] = clip.get("file") or ""
                p["hook"] = clip.get("hook") or ""
                p["reason"] = clip.get("reason") or ""
                p["clip_status"] = clip.get("status") or "done"

    primary_acc = c["accounts"][0] if c.get("accounts") else None
    upcoming_slots = calendar.assign_slots_to_videos(primary_acc, scheduled_posts + all_mine, count=9, creator_id=cid)
    analytics_profile = analytics.get_analytics_profile(cid)

    return {
        "creator": {"id": c["id"], "name": c["name"], "accounts": c.get("accounts", [])},
        "scheduled": scheduled_posts,
        "recent_posted": recent_posted,
        "upcoming_slots": upcoming_slots,
        "max_per_day": calendar.MAX_VIDEOS_PER_DAY,
        "preferred_times_pkt": analytics_profile.get("primed_slots_pkt") or ["06:00 PM", "12:00 AM", "06:00 AM"],
        "min_gap_hours": analytics_profile.get("min_gap_hours", 5.0),
        "analytics": analytics_profile
    }


@app.get("/api/creators/{cid}/analytics/velocity")
def get_creator_velocity(cid: str):
    """Returns 24-hour hourly view velocity profile, detected audience peaks, and priming parameters."""
    _throttle("creatorvelocity:" + ctx.uid(), 60, 60)
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    return analytics.get_analytics_profile(cid)


@app.post("/api/creators/{cid}/analytics/sync")
def sync_creator_analytics(cid: str):
    """Polls YouTube Data API v3 for latest video view snapshots and computes delta velocity."""
    _throttle("creatoranalyticsync:" + ctx.uid(), 30, 60)
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    try:
        profile = analytics.sync_youtube_stats(cid)
        return {"ok": True, "profile": profile}
    except Exception as e:
        raise HTTPException(500, f"Sync error: {e}")


@app.post("/api/creators/{cid}/analytics/settings")
def update_creator_analytics_settings(cid: str, payload: dict = Body(...)):
    """Updates analytics scheduling mode, priming offset, min gap, or manual peak hours."""
    _throttle("creatoranalyticsettings:" + ctx.uid(), 60, 60)
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")
    profile = analytics.save_analytics_settings(cid, payload)
    return {"ok": True, "profile": profile}


@app.get("/api/creators/{cid}/ready-clips")
def get_creator_ready_clips(cid: str):
    """Returns all rendered/completed clips for a creator ready for calendar scheduling."""
    c = creators.get(cid)
    if not c:
        raise HTTPException(404, "Creator not found")

    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())
    all_jobs = [j for j in jobs.list_jobs() if j.get("creator") == cid]
    ready_clips = []
    now_ts = time.time()

    for j in all_jobs:
        for clip in j.get("clips", []):
            if clip.get("status") == "done":
                sched_info = None
                for pid, pdata in (clip.get("posts") or {}).items():
                    if isinstance(pdata, dict):
                        st = float(pdata.get("scheduled_at") or pdata.get("due_at") or (pdata.get("calendar_slot", {}).get("video_ts") if isinstance(pdata.get("calendar_slot"), dict) else 0) or 0)
                        if st > now_ts + 60 or pdata.get("status") in posting.OPEN:
                            sched_info = {
                                "scheduled_at": st,
                                "slot": pdata.get("calendar_slot"),
                                "account_name": pdata.get("account_name"),
                            }
                            break

                ready_clips.append({
                    "id": clip["id"],
                    "job_id": j["id"],
                    "title": clip.get("title") or clip.get("hook") or "Clip",
                    "hook": clip.get("hook") or "",
                    "duration": round(clip.get("end", 0) - clip.get("start", 0), 1),
                    "score": clip.get("score", 70),
                    "cover": clip.get("cover") or f"{clip['id']}.jpg",
                    "file": clip.get("file") or "",
                    "scheduled": sched_info,
                    "created": j.get("created", 0),
                })

    ready_clips.sort(key=lambda x: -x["created"])
    return {"clips": ready_clips}


@app.post("/api/calendar/schedule-clip")
def schedule_clip_to_slot(payload: dict = Body(...)):
    """Schedules a specific clip directly to a specific USA publishing calendar slot."""
    cid = payload.get("creator") or payload.get("creator_id")
    jid = payload.get("job_id")
    clip_id = payload.get("clip_id")
    slot_ts = float(payload.get("slot_ts") or 0)

    if not (cid and jid and clip_id and slot_ts):
        raise HTTPException(400, "creator, job_id, clip_id, and slot_ts are required")

    if not jobs.list_jobs():
        jobs.load_user(ctx.uid())

    job = jobs.get(jid)
    if not job:
        raise HTTPException(404, "Job not found")
    clip = next((k for k in job.get("clips", []) if k.get("id") == clip_id), None)
    if not clip:
        raise HTTPException(404, "Clip not found")

    c = creators.get(cid)
    acc_id = None
    if c and c.get("accounts"):
        acc_id = c["accounts"][0]
    else:
        user_accs = accounts.list_accounts()
        yt_accs = [a for a in user_accs if a.get("platform") == "youtube"]
        acc_id = (yt_accs[0]["id"] if yt_accs else (user_accs[0]["id"] if user_accs else None))

    if not acc_id:
        raise HTTPException(400, "No connected social account found. Please connect your YouTube account in the Accounts tab first.")

    made = posting.enqueue(job, clip, [acc_id], target_ts=slot_ts, force=True)
    slot_info = calendar.format_slot_info(slot_ts, creator_id=cid)
    return {
        "ok": True,
        "slot": slot_info,
        "title": clip.get("title") or clip.get("hook") or "Short",
        "posts_created": len(made)
    }


@app.get("/api/jobs/{jid}/clips/{cid}/community")
def get_clip_community_post(jid: str, cid: str):
    """Returns the pre-formatted community post text, Short URL, and schedule information."""
    job = _job_or_404(jid)
    clip = next((c for c in job["clips"] if c["id"] == cid), None)
    if not clip:
        raise HTTPException(404, "Clip not found")

    vpost = next((p for p in posting._mine() if p.get("job") == jid and p.get("clip") == cid and p.get("kind") != "community"), None)
    short_url = (vpost.get("url") or "") if vpost else ""
    if not short_url and vpost and vpost.get("remote_id"):
        short_url = f"https://www.youtube.com/shorts/{vpost['remote_id']}"
    if not short_url and clip.get("posts"):
        for pdata in clip["posts"].values():
            if pdata.get("url") and "youtu" in pdata.get("url", ""):
                short_url = pdata["url"]
                break

    title = clip.get("seo_title") or clip.get("title") or clip.get("hook") or "Clip"
    desc = clip.get("description") or ""
    comment = str(clip.get("pinned_comment") or "").strip()
    tags = list(clip.get("seo_tags") or []) + list(clip.get("hashtags") or [])

    comm_text = calendar.build_community_post_text(title, desc, short_url, comment, tags)

    return {
        "title": title,
        "text": comm_text,
        "short_url": short_url,
        "video_post": vpost,
        "community_scheduled_at": clip.get("community_scheduled_at")
    }


@app.post("/api/jobs/{jid}/clips/{cid}/dismiss-cleanup")
def dismiss_cleanup(jid: str, cid: str):
    job = _job_or_404(jid)
    clip = next((c for c in job["clips"] if c["id"] == cid), None)
    if not clip:
        raise HTTPException(404, "No such clip")
    if "cleanup_prompt" in clip:
        del clip["cleanup_prompt"]
        jobs.save(job)
        ctx.bump()
    return {"ok": True}


@app.post("/api/alerts/test")
def test_alert():
    if not alerts.configured():
        raise HTTPException(400, "Save a Discord webhook or Telegram details first.")
    auth_problem = None
    try:
        auth.throttle("alert:" + ctx.uid(), 10, 600)
    except auth.AuthError as e:
        auth_problem = str(e)
    if auth_problem:
        raise HTTPException(429, auth_problem)
    problems = alerts.send("PeakCut: test message. Alerts are working.")
    if problems:
        raise HTTPException(400, "; ".join(problems))
    return {"ok": True}


# ================================================================ admin (only accounts marked as admin in the database)
# The gate above already answers "not found" to everyone else; each route checks again so neither can be forgotten.
def _uid_ok(uid: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]{6,40}", uid):
        raise HTTPException(404)
    return uid


@app.get("/api/admin/overview")
def admin_overview(request: Request):
    _admin(request)
    return admins.overview()


@app.get("/api/admin/users/{uid}")
def admin_user(request: Request, uid: str):
    _admin(request)
    try:
        return admins.user_detail(_uid_ok(uid))
    except admins.Refused as e:
        raise HTTPException(e.status, str(e))


@app.post("/api/admin/users/{uid}/disabled")
def admin_disable(request: Request, uid: str, body: dict = Body(...)):
    me_ = _admin(request)
    try:
        return admins.set_disabled(me_, _uid_ok(uid), body.get("disabled"))
    except admins.Refused as e:
        raise HTTPException(e.status, str(e))


@app.post("/api/admin/users/{uid}/delete")
def admin_delete_user(request: Request, uid: str, body: dict = Body(...)):
    me_ = _admin(request)
    target = auth.get_user(_uid_ok(uid))
    if not target:
        raise HTTPException(404, "No such account")
    if target.id == me_.id:
        raise HTTPException(400, "You can't delete your own account from here.")
    if str(body.get("confirm") or "").strip().lower() != target.email.lower():
        raise HTTPException(400, "Type the account's email address exactly to confirm.")
    try:
        account.delete_account(target.id)
    except account.Busy as e:
        raise HTTPException(409, str(e))
    with db.engine.begin() as c:
        admins._log(c, me_.id, "delete", target.id, "account deleted")
    return {"ok": True}


def main():
    print(f"\n  PeakCut is running:  {config.PUBLIC_URL}\n")
    if not config.ACCOUNTS and (config.HTTPS or config.HOST not in ("127.0.0.1", "localhost", "::1")):
        print("  Sign-in is off, so anyone who can reach this address can use PeakCut and its AI key.\n"
              "  On a server other people can reach, set PEAKCUT_ACCOUNTS=1 in .env.\n", flush=True)
    if config.env("PEAKCUT_AUTO_RELOAD") == "1":
        # restart by itself whenever the server code changes (pages in web/ never need a restart)
        uvicorn.run("studio.server:app", host=config.HOST, port=config.PORT, log_level="warning", backlog=4096, reload=True,
                    reload_dirs=[str(config.ROOT / "studio")], reload_includes=["*.py"],
                    proxy_headers=_trust_proxy(), forwarded_allow_ips=list(_PROXY_CIDRS))
        return
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="warning", backlog=4096,
                proxy_headers=_trust_proxy(), forwarded_allow_ips=list(_PROXY_CIDRS))


if __name__ == "__main__":
    main()
