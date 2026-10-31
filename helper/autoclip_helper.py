#!/usr/bin/env python3
"""AutoClip Web helper.

Browsers cannot read YouTube data directly, so this small server runs on your PC,
uses yt-dlp to fetch a video's info and captions, and hands them to the web app
over http://127.0.0.1. It only answers web pages you allow with --allow-origin.

    pip install -U "yt-dlp[default,deno]"
    python autoclip_helper.py --app https://USERNAME.github.io/REPO/

With --app the helper also serves the web app itself at http://127.0.0.1:8765/.
Safari needs that: it blocks https pages (GitHub Pages) from calling http://127.0.0.1.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import ssl
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

VERSION = "0.1.0"
DEFAULT_PORT = 8765
DEV_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
}
CACHE_TTL = 20 * 60  # caption URLs from YouTube expire after a few hours
MAX_BODY = 64 * 1024

try:
    import yt_dlp
    from yt_dlp.utils import DownloadError
except ImportError:  # reported in main()
    yt_dlp = None
    DownloadError = Exception


class UserError(Exception):
    """An error whose message can be shown to the user as-is."""


class Config:
    allowed_origins: set[str] = set(DEV_ORIGINS)
    cookies_file: str | None = None
    cookies_from_browser: str | None = None
    app_url: str | None = None


CFG = Config()
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


# ---------------------------------------------------------------- yt-dlp ---

def clean_url(raw: str) -> str:
    """First URL in the input (pasting a link twice is common), or a bare video ID."""
    raw = (raw or "").strip()
    parts = [p.strip() for p in re.split(r"(?=https?://)", raw) if p.strip()]
    url = parts[0] if parts else ""
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        url = f"https://www.youtube.com/watch?v={url}"
    return url


YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


def is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in YOUTUBE_HOSTS)


def ydl_options() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # A pasted playlist link would otherwise resolve every video in it.
        "extract_flat": "in_playlist",
        "color": {"stdout": "never", "stderr": "never"},
    }
    # yt-dlp only enables deno by default; also accept node/bun if that is what is installed.
    runtimes = {name: {} for name in ("deno", "node", "bun") if shutil.which(name)}
    if runtimes:
        opts["js_runtimes"] = runtimes
    if CFG.cookies_file:
        opts["cookiefile"] = CFG.cookies_file
    if CFG.cookies_from_browser:
        opts["cookiesfrombrowser"] = (CFG.cookies_from_browser,)
    return opts


def friendly_error(err: Exception) -> str:
    msg = _ANSI.sub("", str(err)).replace("ERROR: ", "").strip()
    low = msg.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        return ("YouTube meminta verifikasi (deteksi bot). Jalankan helper dengan "
                "--cookies-from-browser firefox atau --cookies cookies.txt.")
    if "private video" in low:
        return "Video ini privat."
    if "members-only" in low or "join this channel" in low:
        return "Video ini khusus member channel."
    if "confirm your age" in low or "age-restricted" in low:
        return "Video dibatasi usia. Jalankan helper dengan --cookies-from-browser agar memakai akun yang sudah login."
    if "unsupported url" in low:
        return "Link tidak dikenali. Tempel link video YouTube."
    if "unavailable" in low or "is not available" in low:
        return "Video tidak tersedia."
    if "getaddrinfo" in low or "timed out" in low or "unable to download" in low:
        return "Gagal menghubungi YouTube. Cek koneksi internet."
    return msg.splitlines()[0][:300] if msg else "Terjadi kesalahan di yt-dlp."


def _json3(formats: list[dict]) -> dict | None:
    return next((f for f in formats or [] if f.get("ext") == "json3" and f.get("url")), None)


def list_tracks(info: dict) -> list[dict]:
    """Manual subtitles plus the original-language automatic captions."""
    orig = (info.get("language") or "").split("-")[0].lower()
    tracks = []
    for lang, fmts in (info.get("subtitles") or {}).items():
        f = _json3(fmts)
        if lang != "live_chat" and f:
            name = f.get("name") or (fmts[0].get("name") if fmts else None) or lang
            tracks.append({"key": f"manual:{lang}", "lang": lang, "kind": "manual", "name": name, "_url": f["url"]})

    auto = info.get("automatic_captions") or {}
    # Auto captions list ~100 machine translations; "-orig" marks the real ASR track.
    keys = [k for k in auto if k.endswith("-orig")]
    if not keys and orig:
        keys = [k for k in auto if k.split("-")[0].lower() == orig][:1]
    if not keys:
        keys = [k for k in ("id", "en") if k in auto]
    for lang in keys:
        f = _json3(auto[lang])
        if f:
            base = lang.removesuffix("-orig")
            name = (f.get("name") or base).replace(" (Original)", "")
            tracks.append({"key": f"auto:{lang}", "lang": base, "kind": "auto", "name": name, "_url": f["url"]})
    return tracks


def pick_track(tracks: list[dict], orig: str | None) -> dict | None:
    """Prefer automatic captions: they carry real per-word timings."""
    base = (orig or "").split("-")[0].lower()
    for pred in (
        lambda t: t["kind"] == "auto",
        lambda t: t["kind"] == "manual" and base and t["lang"].split("-")[0].lower() == base,
        lambda t: True,
    ):
        for t in tracks:
            if pred(t):
                return t
    return None


def parse_json3(raw: bytes) -> tuple[list[list], bool]:
    """Words as [start, end, text] plus whether most timings were estimated."""
    data = json.loads(raw)
    items: list[tuple[float, str]] = []
    estimated = 0
    for ev in data.get("events") or []:
        parts = [s for s in ev.get("segs") or [] if (s.get("utf8") or "").strip()]
        if not parts:
            continue
        t0 = ev.get("tStartMs", 0) / 1000
        dur = ev.get("dDurationMs", 0) / 1000
        timed = any("tOffsetMs" in s for s in parts[1:]) or (
            len(parts) == 1 and len(parts[0]["utf8"].split()) == 1
        )
        if timed:
            starts = [t0 + s.get("tOffsetMs", 0) / 1000 for s in parts]
            texts = [s["utf8"] for s in parts]
            ends = starts[1:] + [t0 + dur if dur else starts[-1] + 0.6]
        else:
            starts, texts, ends = [t0], [" ".join(s["utf8"] for s in parts)], [t0 + (dur or 2.0)]
        for st, tx, en in zip(starts, texts, ends):
            ws = tx.replace("\n", " ").split()
            if len(ws) == 1:
                items.append((st, ws[0]))
            elif ws:
                # Spread a multi-word line over its time span by character count.
                estimated += len(ws)
                total = sum(len(w) + 1 for w in ws)
                span = max(en - st, 0.2 * len(ws))
                acc = 0
                for w in ws:
                    items.append((st + span * acc / total, w))
                    acc += len(w) + 1

    items.sort(key=lambda x: x[0])
    starts_text: list[tuple[float, str]] = []
    prev = -1.0
    for st, w in items:
        if st <= prev:
            st = prev + 0.01
        prev = st
        starts_text.append((st, w))

    words = []
    for i, (st, w) in enumerate(starts_text):
        # Captions only give word starts; estimate how long the word is spoken.
        en = st + min(1.0, max(0.25, 0.07 * len(w) + 0.12))
        if i + 1 < len(starts_text):
            en = min(en, starts_text[i + 1][0])
        en = max(en, st + 0.01)
        words.append([round(st, 3), round(en, 3), w])
    # Auto captions occasionally merge two words; only flag tracks that are mostly line-timed.
    return words, estimated > 0.25 * max(1, len(words))


def load_video(url: str) -> dict:
    with _cache_lock:
        hit = _cache.get(url)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return hit[1]
    try:
        with yt_dlp.YoutubeDL(ydl_options()) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise UserError(friendly_error(e)) from e
    if not info:
        raise UserError("Video tidak ditemukan.")
    if info.get("_type") == "playlist":
        raise UserError("Itu link playlist. Tempel link satu video.")
    if not str(info.get("extractor_key", "")).startswith("Youtube"):
        raise UserError("Saat ini hanya video YouTube yang didukung.")
    if info.get("is_live"):
        raise UserError("Siaran langsung belum didukung. Tunggu sampai siarannya selesai.")
    entry = {
        "video": {
            "id": info.get("id"),
            "title": info.get("title") or "",
            "channel": info.get("channel") or info.get("uploader") or "",
            "duration": info.get("duration") or 0,
            "thumbnail": info.get("thumbnail") or "",
            "url": info.get("webpage_url") or url,
            "language": info.get("language"),
        },
        "tracks": list_tracks(info),
        "captions": {},
    }
    with _cache_lock:
        _cache[url] = (time.time(), entry)
    return entry


def get_captions(raw_url: str, track_key: str | None) -> dict:
    url = clean_url(raw_url)
    if not url:
        raise UserError("Link video kosong.")
    if not is_youtube(url):
        raise UserError("Saat ini hanya link YouTube yang didukung.")
    entry = load_video(url)
    tracks = entry["tracks"]
    if not tracks:
        raise UserError("Video ini tidak punya transkrip/subtitle di YouTube.")
    track = next((t for t in tracks if t["key"] == track_key), None) or pick_track(tracks, entry["video"]["language"])

    if track["key"] not in entry["captions"]:
        try:
            with yt_dlp.YoutubeDL(ydl_options()) as ydl:
                raw = ydl.urlopen(track["_url"]).read()
        except Exception as e:  # network errors arrive as several exception types
            raise UserError("Gagal mengunduh transkrip: " + friendly_error(e)) from e
        words, estimated = parse_json3(raw)
        if not words:
            raise UserError("Transkrip video ini kosong.")
        entry["captions"][track["key"]] = (words, estimated)
    words, estimated = entry["captions"][track["key"]]

    return {
        "video": entry["video"],
        "tracks": [{k: v for k, v in t.items() if not k.startswith("_")} for t in tracks],
        "track": track["key"],
        "word_timing": "estimated" if estimated else "exact",
        "words": words,
    }


# ------------------------------------------------------------- web app ---

APP_PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]*$")
APP_FRESH_SECONDS = 60
_app_cache: dict[str, tuple[float, int, str, bytes]] = {}


def _ssl_context() -> ssl.SSLContext:
    # python.org builds on macOS ship without root certificates; certifi comes with yt-dlp[default].
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_SSL = _ssl_context()


def _error_page(message: str) -> bytes:
    return (
        "<!doctype html><meta charset='utf-8'><title>AutoClip helper</title>"
        "<body style='font-family:system-ui;background:#0f1115;color:#e8eaf0;padding:40px'>"
        f"<h2>Web app tidak bisa dimuat</h2><p>{message}</p></body>"
    ).encode("utf-8")


def fetch_app_file(path: str) -> tuple[int, str, bytes]:
    """Serve a web app file by fetching it from CFG.app_url (e.g. GitHub Pages)."""
    if not APP_PATH_RE.match(path) or ".." in path:
        return 404, "text/plain; charset=utf-8", b"Not found"
    rel = path.lstrip("/") or "index.html"
    hit = _app_cache.get(rel)
    # Files under assets/ have content hashes in their names, so they never change.
    if hit and (rel.startswith("assets/") or time.time() - hit[0] < APP_FRESH_SECONDS):
        return hit[1:]
    url = CFG.app_url + rel
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"AutoClipHelper/{VERSION}"})
        with urllib.request.urlopen(req, timeout=15, context=_SSL) as r:
            result = (r.status, r.headers.get("Content-Type", "application/octet-stream"), r.read())
    except HTTPError as e:
        return e.code, "text/plain; charset=utf-8", f"{e.code}: {url}".encode()
    except (URLError, OSError) as e:
        if hit:  # offline: an older copy is better than nothing
            return hit[1:]
        sys.stderr.write(f"[helper] gagal memuat {url}: {e}\n")
        return 502, "text/html; charset=utf-8", _error_page(f"Gagal mengambil {url}. Cek koneksi internet dan alamat --app.")
    _app_cache[rel] = (time.time(), *result)
    return result


def health() -> dict:
    return {
        "ok": True,
        "name": "autoclip-helper",
        "version": VERSION,
        "yt_dlp": yt_dlp.version.__version__ if yt_dlp else None,
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "js_runtime": next((r for r in ("deno", "node", "bun") if shutil.which(r)), None),
        "app": CFG.app_url,
    }


def running_helper(port: int) -> dict | None:
    """Health of an AutoClip helper already listening on port, or None."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
            data = json.loads(r.read())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("name") == "autoclip-helper" else None


def open_browser(url: str):
    print(f"Membuka {url}", flush=True)
    webbrowser.open(url)


# ------------------------------------------------------------------ HTTP ---

class Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second process bind the same port; we want an error instead.
    allow_reuse_address = sys.platform != "win32"


class Handler(BaseHTTPRequestHandler):
    server_version = f"AutoClipHelper/{VERSION}"

    def log_message(self, fmt, *args):
        sys.stderr.write("[helper] " + (fmt % args) + "\n")

    @property
    def origin(self) -> str | None:
        return self.headers.get("Origin")

    def origin_allowed(self) -> bool:
        # Requests without Origin come from local tools (curl), not web pages.
        return not self.origin or self.origin.rstrip("/") in CFG.allowed_origins

    def host_allowed(self) -> bool:
        # Guards against DNS rebinding: only accept our own loopback host names.
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("127.0.0.1", "localhost", "::1")

    def cors(self, allow_any_origin: bool = False):
        if self.origin and (allow_any_origin or self.origin_allowed()):
            self.send_header("Access-Control-Allow-Origin", self.origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Max-Age", "600")

    def send_json(self, code: int, payload: dict, allow_any_origin: bool = False):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.cors(allow_any_origin)
        self.end_headers()
        self.wfile.write(body)

    def send_app_file(self, path: str):
        status, ctype, body = fetch_app_file(path)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def reject_origin(self):
        sys.stderr.write(
            f"[helper] Ditolak: {self.origin}. Jalankan ulang dengan --allow-origin {self.origin}\n"
        )
        self.send_json(403, {"error": "origin_not_allowed", "origin": self.origin})

    def do_OPTIONS(self):
        if not self.host_allowed() or not self.origin_allowed():
            self.send_response(403)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self.host_allowed():
            return self.send_json(403, {"error": "bad_host"})
        path = urlparse(self.path).path
        if path != "/health":
            if CFG.app_url:
                return self.send_app_file(path)
            return self.send_json(404, {"error": "not found"})
        if not self.origin_allowed():
            # Readable by the page so it can show the exact command to fix it.
            return self.send_json(
                200, {"ok": False, "error": "origin_not_allowed", "origin": self.origin}, allow_any_origin=True
            )
        self.send_json(200, health())

    def do_POST(self):
        if not self.host_allowed():
            return self.send_json(403, {"error": "bad_host"})
        if not self.origin_allowed():
            return self.reject_origin()
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            return self.send_json(413, {"error": "Permintaan terlalu besar."})
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self.send_json(400, {"error": "JSON tidak valid."})

        if urlparse(self.path).path != "/captions":
            return self.send_json(404, {"error": "not found"})
        try:
            self.send_json(200, get_captions(str(body.get("url", "")), body.get("track")))
        except UserError as e:
            self.send_json(400, {"error": str(e)})
        except Exception as e:  # keep the server alive and tell the user something useful
            sys.stderr.write(f"[helper] error: {e!r}\n")
            self.send_json(500, {"error": friendly_error(e)})


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except AttributeError:
            pass

    ap = argparse.ArgumentParser(description="Helper lokal untuk AutoClip Web.")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument(
        "--app",
        metavar="URL",
        help="Alamat web app, mis. https://USERNAME.github.io/REPO/. Situsnya otomatis diizinkan, dan "
        "helper ikut menyajikan web app di http://127.0.0.1:PORT/ (dibutuhkan untuk Safari).",
    )
    ap.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        metavar="URL",
        help="Alamat web app yang boleh memakai helper, mis. https://USERNAME.github.io (boleh diulang)",
    )
    ap.add_argument("--open", action="store_true", help="Buka web app di browser setelah helper siap")
    ap.add_argument("--cookies", metavar="FILE", help="File cookies.txt (format Netscape) untuk video yang butuh login")
    ap.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="Ambil cookies login YouTube dari browser: firefox, chrome, edge, brave, …",
    )
    args = ap.parse_args()

    if yt_dlp is None:
        print('yt-dlp belum terpasang. Jalankan:  pip install -U "yt-dlp[default,deno]"', file=sys.stderr)
        return 1

    CFG.allowed_origins |= {o.rstrip("/") for o in args.allow_origin}
    # Pages served by the helper itself call it from its own origin.
    CFG.allowed_origins |= {f"http://127.0.0.1:{args.port}", f"http://localhost:{args.port}"}
    if args.app:
        app = urlparse(args.app)
        if app.scheme not in ("http", "https") or not app.netloc:
            print(f"--app harus berupa alamat lengkap, mis. https://USERNAME.github.io/REPO/ (bukan {args.app})", file=sys.stderr)
            return 1
        CFG.app_url = args.app if args.app.endswith("/") else args.app + "/"
        CFG.allowed_origins.add(f"{app.scheme}://{app.netloc}")
    CFG.cookies_file = args.cookies
    CFG.cookies_from_browser = args.cookies_from_browser

    local_url = f"http://127.0.0.1:{args.port}/"

    def already_running(other: dict) -> int:
        # A second click on the launcher just opens the browser again.
        print(f"Helper sudah berjalan di {local_url}")
        target = local_url if other.get("app") else CFG.app_url
        if args.open and target:
            open_browser(target)
        return 0

    other = running_helper(args.port)
    if other:
        return already_running(other)
    try:
        server = Server(("127.0.0.1", args.port), Handler)
    except OSError as e:
        other = running_helper(args.port)
        if other:
            return already_running(other)
        print(f"Port {args.port} sudah dipakai program lain ({e}). Coba --port yang lain.", file=sys.stderr)
        return 1

    h = health()
    print(f"AutoClip helper {VERSION} berjalan di http://127.0.0.1:{args.port}")
    print(f"  yt-dlp {h['yt_dlp']} | ffmpeg: {'ada' if h['ffmpeg'] else 'tidak ada'} | JS runtime: {h['js_runtime'] or 'tidak ada'}")
    print("  Situs yang diizinkan:")
    for o in sorted(CFG.allowed_origins):
        print(f"    {o}")
    if CFG.app_url:
        print(f"  Web app juga tersedia di  http://127.0.0.1:{args.port}/  (pakai alamat ini di Safari)")
        print(f"    diambil dari {CFG.app_url}")
    elif not args.allow_origin:
        print("  (Tambahkan --app https://USERNAME.github.io/REPO/ untuk versi GitHub Pages.)")
    print("Tekan Ctrl+C atau tutup jendela ini untuk berhenti.", flush=True)
    if args.open:
        if CFG.app_url:
            open_browser(local_url)
        else:
            print("--open butuh --app, jadi browser tidak dibuka.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nHelper berhenti.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
