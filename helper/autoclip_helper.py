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
import atexit
import copy
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
import webbrowser
import zipfile
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse

VERSION = "0.6.0"
DEFAULT_PORT = 8765
DEV_ORIGINS = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
}
CACHE_TTL = 20 * 60  # caption URLs from YouTube expire after a few hours
MAX_BODY = 512 * 1024

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
_info_cache: dict[str, tuple[float, dict]] = {}  # yt-dlp info by URL, reused by downloads
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


def remember_info(info: dict, *urls: str):
    """Keep yt-dlp's info so a later download can skip the slow extraction (~10 s)."""
    with _cache_lock:
        for u in urls:
            if u:
                _info_cache[u] = (time.time(), info)


def recall_info(url: str) -> dict | None:
    """A private copy of recently extracted info (downloading mutates it), or None."""
    with _cache_lock:
        hit = _info_cache.get(url)
    if not hit or time.time() - hit[0] >= CACHE_TTL:
        return None
    try:
        return copy.deepcopy(hit[1])
    except Exception:
        return None


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
    # The web app sends the canonical link back for previews and exports.
    remember_info(info, url, clean_url(info.get("webpage_url") or ""))
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


# ------------------------------------------------------------- export ---
#
# Export pipeline: download the clip section (<=1080p), find the faces so a vertical
# crop keeps the subject in frame, draw the captions with Pillow (no libass needed,
# so it works with any ffmpeg build) and render the final MP4 in one ffmpeg pass.

DATA_DIR = os.path.join(os.path.expanduser("~"), ".autoclip")
YUNET_URL = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
YUNET_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
OPTIONAL_PACKAGES = (("cv2", "opencv-python-headless"), ("PIL", "pillow"))
ASPECTS = ("16:9", "9:16_blur", "9:16_crop", "9:16_gaming")
# Gamer mode: gameplay over the top two thirds of the 1080x1920 frame, the webcam in the last third.
GAME_SLOT = (1080, 1280)
FACE_SLOT = (1080, 640)
BIG_FACE = 0.03  # share of the frame width: smaller faces are background, except a webcam's
WEBCAM_FACE = 0.012
CAPTION_STYLES = ("viral", "box", "classic", "neon", "none")
POSITIONS = ("bottom", "center", "top")
MAX_CLIP_SECONDS = 10 * 60  # also the limit for a whole compilation
MAX_SEGMENTS = 30  # scenes in one compilation
JOB_TTL = 2 * 60 * 60  # finished exports stay downloadable this long
SAMPLE_STEP = 0.25  # seconds between frames checked for faces
PREVIEW_HEIGHT = 480
# Previews are only played in the browser: small, quick, and in a format every browser decodes.
PREVIEW_ENCODE = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"]
MAX_PREVIEWS = 6  # previews kept on disk; older ones are dropped

# Exports and previews, told apart by "kind". A compilation preview lists the ids of its
# scenes' own previews in "parts", so the scenes are fetched once and shared.
_export_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_render_slot = threading.Semaphore(1)  # one export at a time keeps the computer usable
_preview_slot = threading.Semaphore(1)  # preview downloads, one after another
_face_slot = threading.Semaphore(1)  # face detection for previews runs beside the downloads


def get_ffmpeg_path() -> str | None:
    for candidate in (
        shutil.which("ffmpeg"),
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "", name).strip()
    return cleaned[:80] or "klip"


def _update(job: dict, **fields):
    with _jobs_lock:
        job.update(fields)


def _purge_old_jobs():
    """Drop finished jobs unused for JOB_TTL, and previews beyond the newest MAX_PREVIEWS.

    Scene previews that a kept compilation is built from stay, whatever their count.
    """
    now = time.time()
    with _jobs_lock:
        idle = {
            jid: now - j.get("touched", j.get("created_at", now))
            for jid, j in _export_jobs.items()
            if j.get("status") in ("done", "error", "ready") and j.get("crop_state") not in ("pending", "running")
        }
        old = {jid for jid, age in idle.items() if age > JOB_TTL}
        in_use = {p for jid, j in _export_jobs.items() if jid not in old for p in j.get("parts", ())}
        old -= in_use
        previews = sorted(
            (jid for jid in idle if _export_jobs[jid].get("kind") == "preview" and jid not in old and jid not in in_use),
            key=lambda jid: idle[jid],
        )
        old.update(previews[MAX_PREVIEWS:])
        dirs = [_export_jobs.pop(jid).get("tmpdir") for jid in old]
    for d in dirs:
        if d:
            shutil.rmtree(d, ignore_errors=True)


def _cleanup_all_jobs():
    for job in list(_export_jobs.values()):
        if job.get("tmpdir"):
            shutil.rmtree(job["tmpdir"], ignore_errors=True)


def probe_media(ffmpeg_bin: str, path: str) -> dict:
    """Size, duration, frame rate (0 when unknown) and whether there is sound, read from
    ffmpeg's own banner (no ffprobe needed)."""
    res = subprocess.run(
        [ffmpeg_bin, "-hide_banner", "-i", path], capture_output=True, text=True, errors="replace", timeout=60
    )
    size = re.search(r"Video:.*?\b(\d{2,5})x(\d{2,5})\b", res.stderr)
    dur = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", res.stderr)
    fps = re.search(r"Video:.*?(\d+(?:\.\d+)?) fps", res.stderr)
    if not size:
        raise UserError("Video hasil unduhan tidak bisa dibaca.")
    duration = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3)) if dur else 0.0
    return {
        "width": int(size.group(1)),
        "height": int(size.group(2)),
        "duration": duration,
        "fps": float(fps.group(1)) if fps else 0.0,
        "audio": bool(re.search(r"Stream #\S+.*?: Audio:", res.stderr)),
    }


# yt-dlp cuts a section by letting ffmpeg stream the format from the cut point, and YouTube
# throttles such long reads to about playback speed. Its DASH files start with an index
# (sidx) of their fragments, so the fragments a clip needs can be fetched directly, in
# parallel chunks at full speed; ffmpeg then cuts the local copy exactly.

FETCH_CHUNK = 2 * 1024 * 1024


def _mp4_boxes(data: bytes):
    """(type, start, end) of the top-level MP4 boxes in data; the last may run past its end."""
    pos = 0
    while pos + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if size == 1 and pos + 16 <= len(data):
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
        if size < 8:
            return
        yield kind.decode("latin-1"), pos, pos + size
        pos += size


def _parse_sidx(data: bytes, start: int, end: int) -> list[tuple[float, float, int, int]]:
    """Fragments as (start s, end s, first byte, end byte) from the sidx box at data[start:end]."""
    p = start + 8
    version = data[p]
    timescale = struct.unpack(">I", data[p + 8:p + 12])[0]
    p += 12
    if version == 0:
        t, first = struct.unpack(">II", data[p:p + 8])
        p += 8
    else:
        t, first = struct.unpack(">QQ", data[p:p + 16])
        p += 16
    count = struct.unpack(">H", data[p + 2:p + 4])[0]
    p += 4
    offset = end + first
    frags = []
    for _ in range(count):
        ref, dur, _sap = struct.unpack(">III", data[p:p + 12])
        p += 12
        if ref >> 31:
            raise ValueError("nested sidx")
        size = ref & 0x7FFFFFFF
        frags.append((t / timescale, (t + dur) / timescale, offset, offset + size))
        t += dur
        offset += size
    return frags


def _get_range(ydl, fmt: dict, first: int, last: int, exact: bool = True) -> bytes:
    """Bytes first..last of a format, with a few retries."""
    want = last - first + 1
    headers = {**(fmt.get("http_headers") or {}), "Range": f"bytes={first}-{last}"}
    for attempt in range(3):
        try:
            with ydl.urlopen(yt_dlp.networking.Request(fmt["url"], headers=headers)) as r:
                if r.status != 206:
                    raise ValueError(f"no range support (HTTP {r.status})")
                data = r.read(want)
            if exact and len(data) != want:
                raise ValueError(f"short read: {len(data)} of {want} bytes")
            return data
        except ValueError:
            raise
        except Exception:
            if attempt == 2:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise AssertionError("unreachable")


def _fetch_fragments(ydl, fmt: dict, start: float, end: float, tmpdir: str) -> tuple[str, float]:
    """Writes init + the fragments covering start..end to a local file; returns it and its start time."""
    if fmt.get("protocol") not in ("http", "https") or fmt.get("ext") not in ("mp4", "m4a"):
        raise ValueError(f"format {fmt.get('format_id')} is not a plain DASH MP4")
    head = _get_range(ydl, fmt, 0, 128 * 1024 - 1, exact=False)
    boxes: dict[str, tuple[int, int]] = {}
    for kind, a, b in _mp4_boxes(head):
        boxes.setdefault(kind, (a, b))
        if kind in ("moof", "mdat"):
            break
    if "moov" not in boxes or "sidx" not in boxes or boxes["moov"][1] > boxes["sidx"][0]:
        raise ValueError(f"no fragment index in format {fmt.get('format_id')}")
    if boxes["sidx"][1] > len(head):
        head = _get_range(ydl, fmt, 0, boxes["sidx"][1] - 1)
    frags = [f for f in _parse_sidx(head, *boxes["sidx"]) if f[1] > start and f[0] < end]
    if not frags:
        raise ValueError("clip lies outside the indexed fragments")
    if frags[-1][1] - frags[0][0] > end - start + 60:
        raise ValueError("fragments too coarse to fetch just the clip")
    first, stop = frags[0][2], frags[-1][3]
    init = head[:boxes["moov"][1]]  # ftyp + moov: the codec setup
    path = os.path.join(tmpdir, f"part_{fmt['format_id']}.{fmt['ext']}")
    lock = threading.Lock()
    with open(path, "wb") as f:
        f.write(init)

        def fetch(chunk: tuple[int, int]):
            data = _get_range(ydl, fmt, *chunk)
            with lock:  # chunks land in place as they arrive, so memory stays small
                f.seek(len(init) + chunk[0] - first)
                f.write(data)

        chunks = [(p, min(p + FETCH_CHUNK, stop) - 1) for p in range(first, stop, FETCH_CHUNK)]
        with ThreadPoolExecutor(6) as pool:
            list(pool.map(fetch, chunks))
    return path, frags[0][0]


def _fast_section(ydl, info: dict, start: float, end: float, tmpdir: str, ffmpeg_bin: str, encode: list[str]) -> str | None:
    """The section cut from directly fetched fragments, or None when the slow path is needed."""
    try:
        chosen = ydl.process_ie_result(info, download=False)
        fmts = sorted(chosen.get("requested_formats") or [], key=lambda f: f.get("vcodec") == "none")
        if len(fmts) != 2 or fmts[0].get("vcodec") == "none" or fmts[1].get("acodec") == "none":
            return None
        with ThreadPoolExecutor(2) as pool:
            parts = list(pool.map(lambda f: _fetch_fragments(ydl, f, start, end, tmpdir), fmts))
        out = os.path.join(tmpdir, "raw.mp4")
        cmd = [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y"]
        for path, t0 in parts:
            # -ss counts from the local file's own start, which is the first fetched fragment.
            cmd += ["-ss", f"{max(0.0, start - t0):.3f}", "-i", path]
        cmd += ["-t", f"{end - start:.3f}", "-map", "0:v:0", "-map", "1:a:0", *encode, out]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=max(120.0, (end - start) * 10))
        if res.returncode != 0 or not os.path.isfile(out):
            raise RuntimeError(res.stderr.strip()[-300:] or "ffmpeg failed")
        for path, _ in parts:
            os.remove(path)
        return out
    except Exception as e:
        sys.stderr.write(f"[helper] unduhan cepat tidak bisa ({e}); pakai cara biasa\n")
        for name in os.listdir(tmpdir):
            if name.startswith(("raw.", "part_")):
                try:
                    os.remove(os.path.join(tmpdir, name))
                except OSError:
                    pass
        return None


def download_section(
    url: str, start: float, end: float, tmpdir: str, ffmpeg_bin: str, height: int = 1080, preview: bool = False
) -> str:
    if preview:
        encode = PREVIEW_ENCODE
    else:
        # Exact cut points need a re-encode; keep it fast and near-lossless.
        encode = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "17", "-c:a", "aac", "-b:a", "192k"]
    opts = ydl_options()
    opts.pop("skip_download", None)
    opts.pop("extract_flat", None)
    opts.update({
        "outtmpl": os.path.join(tmpdir, "raw.%(ext)s"),
        # A 1080p source is plenty for a vertical clip, and H.264 decodes fastest.
        "format": "bv*+ba/b",
        "format_sort": [f"res:{height}", "vcodec:h264", "acodec:m4a"],
        "merge_output_format": "mp4",
        "download_ranges": yt_dlp.utils.download_range_func(None, [(start, end)]),
        "force_keyframes_at_cuts": True,
        "external_downloader_args": {"ffmpeg_o": encode},
        "ffmpeg_location": ffmpeg_bin,
        "noprogress": True,
        "socket_timeout": 30,
    })
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = recall_info(url)
            cached = info is not None
            if not cached:
                info = ydl.extract_info(url, download=False)
                remember_info(info, url)
                info = copy.deepcopy(info)
            fast = _fast_section(ydl, copy.deepcopy(info), start, end, tmpdir, ffmpeg_bin, encode)
            if fast:
                return fast
            try:
                ydl.process_ie_result(info, download=True)
            except DownloadError:
                if not cached:
                    raise
                ydl.download([url])  # the cached links went stale
    except DownloadError as e:
        raise UserError(friendly_error(e)) from e
    files = [f for f in os.listdir(tmpdir) if f.startswith("raw.") and not f.endswith((".part", ".ytdl"))]
    if not files:
        raise UserError("Segmen video tidak berhasil diunduh.")
    return os.path.join(tmpdir, files[0])


# -- faces -----------------------------------------------------------------

def yunet_model_path() -> str | None:
    """The YuNet face model (~230 KB), downloaded once and checked against a pinned hash."""
    path = os.path.join(DATA_DIR, "models", "face_detection_yunet_2023mar.onnx")
    if os.path.isfile(path):
        return path
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        req = urllib.request.Request(YUNET_URL, headers={"User-Agent": f"AutoClipHelper/{VERSION}"})
        with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != YUNET_SHA256:
            sys.stderr.write("[helper] model wajah tidak cocok dengan hash yang diharapkan; dilewati\n")
            return None
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
        return path
    except OSError as e:
        sys.stderr.write(f"[helper] gagal mengunduh model wajah: {e}\n")
        return None


class FaceDetector:
    """YuNet when its model is available, otherwise OpenCV's bundled Haar cascade."""

    def __init__(self):
        import cv2

        self.cv2 = cv2
        self.yunet = None
        self.haar = None
        model = yunet_model_path()
        if model:
            try:
                self.yunet = cv2.FaceDetectorYN.create(model, "", (320, 320), 0.6, 0.3, 50)
            except cv2.error as e:
                sys.stderr.write(f"[helper] YuNet tidak bisa dimuat: {e}\n")
        if self.yunet is None:
            cascades = getattr(getattr(cv2, "data", None), "haarcascades", "")
            self.haar = cv2.CascadeClassifier(os.path.join(cascades, "haarcascade_frontalface_default.xml"))

    def detect(self, img) -> list[tuple[float, float, float, float, float]]:
        """Faces as (x, y, w, h, confidence) in img pixels."""
        h, w = img.shape[:2]
        if self.yunet is not None:
            self.yunet.setInputSize((w, h))
            _, faces = self.yunet.detect(img)
            if faces is None:
                return []
            return [(float(f[0]), float(f[1]), float(f[2]), float(f[3]), float(f[14])) for f in faces]
        if self.haar is None or self.haar.empty():
            return []
        gray = self.cv2.cvtColor(img, self.cv2.COLOR_BGR2GRAY)
        found = self.haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(int(w * 0.04),) * 2)
        return [(float(x), float(y), float(fw), float(fh), 1.0) for x, y, fw, fh in found]


def analyze_faces(path: str, duration: float, on_progress, min_face: float = BIG_FACE) -> tuple[list[dict], int]:
    """Faces and scene cuts sampled every SAMPLE_STEP seconds, plus the frame width.

    min_face is the smallest face kept, as a share of the width; a webcam in the corner
    of a game stream needs WEBCAM_FACE.
    """
    import cv2

    detector = FaceDetector()
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise UserError("Video tidak bisa dibaca untuk deteksi wajah.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    iw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    ih = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    step = max(1, round(fps * SAMPLE_STEP))
    scale = min(1.0, 640 / max(iw, 1))
    samples: list[dict] = []
    prev_tiny = None
    diffs: list[float] = []
    idx = 0
    try:
        while cap.grab():
            ok, frame = cap.retrieve()
            if not ok:
                idx += 1
                continue
            # Shot changes are found frame by frame: consecutive frames of one shot look alike,
            # so a jump in the difference well above the recent level is a cut.
            tiny = cv2.cvtColor(cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            cut = False
            if prev_tiny is not None:
                diff = float(cv2.absdiff(tiny, prev_tiny).mean())
                recent = sorted(diffs[-25:])
                typical = recent[len(recent) // 2] if recent else 0.0
                cut = diff > 18 and diff > 4 * max(typical, 2.0)
                diffs.append(diff)
            prev_tiny = tiny
            # Check faces every SAMPLE_STEP, and right after every cut.
            if idx % step == 0 or cut:
                small = cv2.resize(frame, (round(iw * scale), round(ih * scale))) if scale < 1 else frame
                faces = [
                    (x / scale, y / scale, w / scale, h / scale, c)
                    for x, y, w, h, c in detector.detect(small)
                    if w / scale >= min_face * iw  # ignore tiny faces in the background
                ]
                t = idx / fps
                samples.append({"t": t, "faces": faces, "cut": cut})
                if duration > 0 and len(samples) % 8 == 0:
                    on_progress(min(1.0, t / duration))
            idx += 1
    finally:
        cap.release()
    return samples, iw


def _subject_centers(samples: list[dict], crop_w: float) -> list[tuple[float, float] | None]:
    """(centre x, width) of what to keep in frame for each sample; None when no face is visible."""
    targets: list[tuple[float, float] | None] = []
    current: tuple[float, float] | None = None  # (centre x, width) of the face being followed
    challenger: float | None = None
    streak = 0
    for s in samples:
        if s["cut"]:
            current, challenger, streak = None, None, 0
        faces = s["faces"]
        if not faces:
            targets.append(None)
            continue
        biggest = max(f[2] * f[3] for f in faces)
        main = [f for f in faces if f[2] * f[3] >= 0.35 * biggest]
        left = min(f[0] for f in main)
        right = max(f[0] + f[2] for f in main)
        if len(main) > 1 and right - left <= 0.85 * crop_w:
            # Everyone who matters fits in the crop: frame the whole group.
            current = ((left + right) / 2, right - left)
            targets.append(current)
            continue

        def weight(f):
            return f[2] * f[3] * f[4]

        best = max(main, key=weight)
        if current is not None:
            # Look among all faces: the person we follow may briefly look smaller.
            same = [f for f in faces if abs(f[0] + f[2] / 2 - current[0]) < max(current[1], f[2])]
            if same:
                stay = max(same, key=weight)
                if stay is not best:
                    # Someone else is more prominent; only switch if that lasts ~0.75 s.
                    bcx = best[0] + best[2] / 2
                    streak = streak + 1 if challenger is not None and abs(challenger - bcx) < best[2] else 1
                    challenger = bcx
                    if streak < 3:
                        best = stay
                    else:
                        streak, challenger = 0, None
                else:
                    streak, challenger = 0, None
        current = (best[0] + best[2] / 2, best[2])
        targets.append(current)
    return targets


def _median3(values: list[float]) -> list[float]:
    """Centred 3-point median: drops single-sample glitches without lagging behind real moves."""
    if len(values) < 3:
        return list(values)
    inner = [sorted(values[k - 1: k + 2])[1] for k in range(1, len(values) - 1)]
    return [values[0], *inner, values[-1]]


def _simplify(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker on (t, x), measuring the error in x only."""
    if len(points) < 3:
        return points
    (t0, x0), (t1, x1) = points[0], points[-1]
    worst, index = 0.0, 0
    for i in range(1, len(points) - 1):
        t, x = points[i]
        expected = x0 + (x1 - x0) * ((t - t0) / (t1 - t0) if t1 > t0 else 0)
        if abs(x - expected) > worst:
            worst, index = abs(x - expected), i
    if worst <= tol:
        return [points[0], points[-1]]
    return _simplify(points[: index + 1], tol)[:-1] + _simplify(points[index:], tol)


def big_faces(samples: list[dict], iw: int) -> list[dict]:
    """The samples with only the faces big enough to steer the camera."""
    return [dict(s, faces=[f for f in s["faces"] if f[2] >= BIG_FACE * iw]) for s in samples]


def plan_crop_path(samples: list[dict], iw: int, crop_w: int) -> list[tuple[float, float]]:
    """Keyframes (t, x) for the left edge of a crop window that follows the subject."""
    max_x = max(0.0, iw - crop_w)
    if not samples:
        return [(0.0, max_x / 2)]
    samples = big_faces(samples, iw)
    subjects = _subject_centers(samples, crop_w)

    # Split into shots; within a shot fill gaps with the nearest known subject.
    scenes: list[list[int]] = []
    for i, s in enumerate(samples):
        if i == 0 or s["cut"]:
            scenes.append([])
        scenes[-1].append(i)

    keys: list[tuple[float, float]] = []
    deadzone = 0.06 * crop_w
    speed = 1.0 * crop_w  # px per second
    for scene in scenes:
        known = [subjects[i] for i in scene if subjects[i] is not None]
        if not known:
            want = [(iw / 2, 0.0)] * len(scene)
        else:
            want, last = [], known[0]
            for i in scene:
                last = subjects[i] or last
                want.append(last)
        centers = _median3([c for c, _ in want])
        widths = [w for _, w in want]
        targets = [min(max_x, max(0.0, c - crop_w / 2)) for c in centers]

        def bounds(k):
            """Crop positions that keep the whole subject inside, with a small margin.

            Uses the raw detection, not the smoothed centre: smoothing steers the camera,
            but must never push a real face out of frame.
            """
            c, w = want[k][0], min(widths[k], crop_w)
            margin = min(0.1 * crop_w, (crop_w - w) / 2)
            lo, hi = c + w / 2 + margin - crop_w, c - w / 2 - margin
            return min(max_x, max(0.0, lo)), min(max_x, max(0.0, hi))

        # A virtual camera: it ignores small movements and pans smoothly to follow big ones,
        # but never lets the subject slip out of frame (a sudden jump is followed at once).
        cam = min(max(targets[0], bounds(0)[0]), bounds(0)[1])
        if keys:
            keys.append((samples[scene[0]]["t"] - 0.001, keys[-1][1]))  # hold until the cut, then jump
        points = [(samples[scene[0]]["t"], cam)]
        for k in range(1, len(scene)):
            dt = samples[scene[k]]["t"] - samples[scene[k - 1]]["t"]
            gap = targets[k] - cam
            if abs(gap) > deadzone:
                cam += math.copysign(min(abs(gap) - deadzone, speed * dt), gap)
            lo, hi = bounds(k)
            cam = min(max(cam, lo), hi)
            points.append((samples[scene[k]]["t"], cam))
        keys.extend(_simplify(points, max(2.0, 0.01 * crop_w)))
    if keys[0][0] > 0:
        keys.insert(0, (0.0, keys[0][1]))
    return keys


def plan_facecam(samples: list[dict], iw: int, ih: int) -> dict | None:
    """Where the webcam is in a game stream: the face that stays in one place the longest.

    Faces in the game come and go and move; the streamer's sits in its corner for most of
    the clip. Returns the box to show in the camera slot (head and shoulders, as shares of
    the frame) and how often that face was seen, or None when there is no face at all.
    """
    faces = [(x + w / 2, y + h / 2, w, h, i) for i, s in enumerate(samples) for x, y, w, h, _ in s["faces"]]
    if not faces:
        return None
    probe = faces[:: max(1, len(faces) // 400)]  # enough candidates to find the cluster quickly

    def near(f, g):
        # A streamer moves inside the webcam frame, about a face width either way.
        return abs(g[0] - f[0]) < f[2] and abs(g[1] - f[1]) < f[3] and 0.5 < g[3] / f[3] < 2

    best = max(probe, key=lambda f: sum(1 for g in faces if near(f, g)))
    cluster = [g for g in faces if near(best, g)]

    def median(k):
        vals = sorted(g[k] for g in cluster)
        return vals[len(vals) // 2]

    cx, cy, h = median(0), median(1), median(3)
    bh = min(ih, 2.2 * h)  # the face and some shoulders, still inside a typical webcam frame
    bw = bh * FACE_SLOT[0] / FACE_SLOT[1]
    top = cy + 0.15 * h - bh / 2  # a little lower than the face's centre
    return {
        "box": [round(v, 4) for v in ((cx - bw / 2) / iw, top / ih, bw / iw, bh / ih)],
        "support": round(len({g[4] for g in cluster}) / len(samples), 2),
    }


def fit_box(box, iw: int, ih: int, aspect: float) -> tuple[int, int, int, int]:
    """A box (shares of the frame) made exactly `aspect` wide in pixels, around its centre and
    inside the frame, with even sizes for the encoder. The web app does the same (fitBox)."""
    x, y, w, h = box
    cx, cy = (x + w / 2) * iw, (y + h / 2) * ih
    ph = max(32.0, h * ih)
    pw = ph * aspect
    if pw > iw:
        pw, ph = iw, iw / aspect
    if ph > ih:
        pw, ph = ih * aspect, ih
    pw, ph = int(pw) // 2 * 2, int(ph) // 2 * 2
    px = round(min(max(cx - pw / 2, 0), iw - pw))
    py = round(min(max(cy - ph / 2, 0), ih - ph))
    return px, py, pw, ph


def clean_box(raw) -> list[float] | None:
    """A box from the web app ([x, y, w, h] as shares of the frame), or None."""
    try:
        x, y, w, h = (float(v) for v in raw)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (x, y, w, h)) or w < 0.02 or h < 0.02:
        return None
    return [min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0), min(w, 1.0), min(h, 1.0)]


def crop_x_expression(keys: list[tuple[float, float]]) -> str:
    """Piecewise-linear x(t) as a flat sum of clamped ramps (ffmpeg crop evaluates it per frame).

    A flat sum avoids deeply nested if() calls. The caller wraps it in single quotes,
    which protects the commas inside the filtergraph.
    """
    parts = [f"{keys[0][1]:.1f}"]
    for (ta, xa), (tb, xb) in zip(keys, keys[1:]):
        dx = xb - xa
        if abs(dx) >= 0.5:
            parts.append(f"{dx:+.1f}*clip((t-{ta:.3f})/{max(tb - ta, 0.001):.3f},0,1)")
    return "".join(parts)


# -- captions --------------------------------------------------------------

_FONT_FILES = (
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/Library/Fonts/Arial Black.ttf",
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "ariblk.ttf"),
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arialbd.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)
_font_cache: dict[int, object] = {}


def caption_font(size: int):
    from PIL import ImageFont

    if size not in _font_cache:
        font = None
        for path in _FONT_FILES:
            if os.path.isfile(path):
                try:
                    font = ImageFont.truetype(path, size)
                    break
                except OSError:
                    continue
        _font_cache[size] = font or ImageFont.load_default(size=size)
    return _font_cache[size]


# Colours follow the editor preview (CaptionOverlay.svelte).
STYLE_LOOK = {
    "viral": {"size": 0.063, "stroke": (0, 0, 0, 255), "stroke_w": 0.09, "active": (250, 204, 21, 255), "active_bg": (0, 0, 0, 110)},
    "neon": {"size": 0.063, "stroke": (30, 27, 75, 255), "stroke_w": 0.09, "active": (34, 211, 238, 255), "glow": (34, 211, 238, 230)},
    "box": {"size": 0.054, "stroke": None, "stroke_w": 0, "active": (253, 224, 71, 255), "box": (0, 0, 0, 199), "underline": True},
    "classic": {"size": 0.05, "stroke": (0, 0, 0, 200), "stroke_w": 0.05, "active": None, "shadow": True},
}


class CaptionRenderer:
    """Draws caption states into same-sized transparent PNG bands for ffmpeg's overlay."""

    def __init__(self, style: str, position: str, out_w: int, out_h: int, area: tuple[int, int] | None = None):
        self.look = STYLE_LOOK[style]
        self.out_w, self.out_h = out_w, out_h
        vertical = out_h > out_w
        self.size = round(self.look["size"] * min(out_w, out_h) * (1.0 if vertical else 0.82))
        self.font = caption_font(self.size)
        self.space = self.font.getlength(" ")
        self.line_h = round(self.size * 1.3)
        self.max_w = 0.85 * out_w - (0.8 * self.size if self.look.get("box") else 0)
        self.stroke = max(1, round(self.look["stroke_w"] * self.size)) if self.look["stroke"] else 0
        self.pad = round(self.size * 0.6)
        self.position = position
        self.margin = round(out_h * (0.14 if vertical else 0.08))
        # In gamer mode captions stay over the gameplay, close to its edges, never on the face.
        self.area = area or (0, out_h)
        if area:
            self.margin = round(out_h * 0.05)

    def _lines(self, words: list[str]) -> list[list[int]]:
        lines: list[list[int]] = []
        cur: list[int] = []
        width = 0.0
        for i, w in enumerate(words):
            ww = self.font.getlength(w)
            add = ww if not cur else self.space + ww
            if cur and width + add > self.max_w:
                lines.append(cur)
                cur, width, add = [], 0.0, ww
            cur.append(i)
            width += add
        if cur:
            lines.append(cur)
        return lines

    def band(self, all_words: list[list[str]]) -> tuple[int, int]:
        """Top y and height of one band that fits every caption."""
        tallest = max((len(self._lines(ws)) for ws in all_words), default=1) * self.line_h
        height = tallest + 2 * self.pad
        a_top, a_h = self.area
        if self.position == "top":
            top = a_top + self.margin - self.pad
        elif self.position == "center":
            top = a_top + (a_h - height) // 2
        else:
            top = a_top + a_h - self.margin + self.pad - height
        top = max(0, min(self.out_h - height, top))
        return top - top % 2, height + height % 2

    def render(self, words: list[str], active: int | None, band_h: int):
        from PIL import Image, ImageDraw, ImageFilter

        look = self.look
        lines = self._lines(words)
        widths = [sum(self.font.getlength(words[i]) for i in ln) + self.space * (len(ln) - 1) for ln in lines]
        block_h = len(lines) * self.line_h
        if self.position == "top":
            y0 = self.pad
        elif self.position == "center":
            y0 = (band_h - block_h) // 2
        else:
            y0 = band_h - self.pad - block_h

        back = Image.new("RGBA", (self.out_w, band_h), (0, 0, 0, 0))
        front = Image.new("RGBA", (self.out_w, band_h), (0, 0, 0, 0))
        bd, fd = ImageDraw.Draw(back), ImageDraw.Draw(front)
        if look.get("box"):
            px, py = 0.4 * self.size, 0.2 * self.size
            bw = max(widths)
            bd.rounded_rectangle(
                [(self.out_w - bw) / 2 - px, y0 - py, (self.out_w + bw) / 2 + px, y0 + block_h + py],
                radius=0.25 * self.size, fill=look["box"],
            )

        placed = []  # (x, y, text, is_active)
        for li, ln in enumerate(lines):
            x = (self.out_w - widths[li]) / 2
            y = y0 + li * self.line_h + (self.line_h - self.size) / 2
            for i in ln:
                placed.append((x, y, words[i], i == active))
                x += self.font.getlength(words[i]) + self.space

        for x, y, text, is_active in placed:
            if look.get("shadow"):
                bd.text((x, y + 0.06 * self.size), text, font=self.font, fill=(0, 0, 0, 220))
            if is_active and look["active"]:
                if look.get("active_bg"):
                    # Hug the drawn glyphs, not the font's line box.
                    p = 0.18 * self.size
                    gl, gt, gr, gb = self.font.getbbox(text)
                    bd.rounded_rectangle([x + gl - p, y + gt - 0.7 * p, x + gr + p, y + gb + 0.7 * p],
                                         radius=0.2 * self.size, fill=look["active_bg"])
                if look.get("glow"):
                    bd.text((x, y), text, font=self.font, fill=look["glow"],
                            stroke_width=self.stroke * 2, stroke_fill=look["glow"])
        if look.get("glow") or look.get("shadow"):
            # Only glow/shadow text lives on the back layer for these styles, so blurring it is safe.
            back = back.filter(ImageFilter.GaussianBlur(0.12 * self.size if look.get("glow") else 0.05 * self.size))

        for x, y, text, is_active in placed:
            colour = look["active"] if is_active and look["active"] else (255, 255, 255, 255)
            fd.text((x, y), text, font=self.font, fill=colour,
                    stroke_width=self.stroke, stroke_fill=look["stroke"] or colour)
            if is_active and look.get("underline"):
                uy = y + self.font.getbbox(text)[3] + 0.1 * self.size
                fd.line([x, uy, x + self.font.getlength(text), uy], fill=colour, width=max(2, round(0.06 * self.size)))
        return Image.alpha_composite(back, front)


def _clean_cues(raw) -> list[dict]:
    cues: list[dict] = []
    if not isinstance(raw, list):
        return cues
    try:
        for c in raw[:600]:
            words = []
            for w in (c.get("words") or [])[:40]:
                text = str(w.get("text", "")).strip()[:40]
                if text:
                    words.append({"start": float(w.get("start", 0)), "end": float(w.get("end", 0)), "text": text})
            if words:
                cues.append({
                    "start": float(c.get("start", words[0]["start"])),
                    "end": float(c.get("end", words[-1]["end"])),
                    "words": words,
                })
    except (TypeError, ValueError, AttributeError) as e:
        raise UserError("Data caption tidak valid.") from e
    return cues


def caption_states(cues: list[dict], highlight: bool) -> list[tuple[float, float, list[str], int | None]]:
    """(start, end, words, active word) intervals; the active word follows the speech."""
    states = []
    for cue in cues:
        ws = cue["words"]
        texts = [w["text"] for w in ws]
        cs, ce = cue["start"], max(cue["end"], cue["start"] + 0.05)
        if not highlight:
            states.append((cs, ce, texts, None))
            continue
        if ws[0]["start"] > cs + 0.02:
            states.append((cs, ws[0]["start"], texts, None))
        for i, w in enumerate(ws):
            a = max(cs, w["start"])
            b = ws[i + 1]["start"] if i + 1 < len(ws) else ce
            if b > a:
                states.append((a, min(b, ce), texts, i))
    states.sort(key=lambda s: s[0])
    return states


def render_caption_track(cues: list[dict], style: str, position: str, out_w: int, out_h: int, tmpdir: str,
                         area: tuple[int, int] | None = None):
    """PNG bands plus an ffconcat playlist that shows each one at the right time."""
    from PIL import Image

    renderer = CaptionRenderer(style, position, out_w, out_h, area)
    states = caption_states(cues, highlight=style != "classic")
    if not states:
        return None
    band_y, band_h = renderer.band([s[2] for s in states])
    Image.new("RGBA", (out_w, band_h), (0, 0, 0, 0)).save(os.path.join(tmpdir, "cap_blank.png"))
    lines = ["ffconcat version 1.0"]
    clock = 0.0
    for n, (a, b, words, active) in enumerate(states):
        a = max(a, clock)
        if b - a < 0.001:
            continue
        if a - clock >= 0.001:
            lines += ["file 'cap_blank.png'", f"duration {a - clock:.3f}"]
        name = f"cap_{n:05d}.png"
        renderer.render(words, active, band_h).save(os.path.join(tmpdir, name), compress_level=1)
        lines += [f"file '{name}'", f"duration {b - a:.3f}"]
        clock = b
    # The concat demuxer ignores the last duration, so finish on a repeated blank.
    lines += ["file 'cap_blank.png'", "duration 1.000", "file 'cap_blank.png'"]
    playlist = os.path.join(tmpdir, "captions.ffconcat")
    with open(playlist, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return playlist, band_y


# -- compilations ----------------------------------------------------------
#
# A compilation joins several scenes of one video into a single clip. The web app lays
# captions and the face path on a timeline where scene i starts at the summed lengths of
# the scenes before it, so every join below lands within half a frame of those sums.

def parse_segments(params: dict) -> list[tuple[float, float]]:
    """The scenes to cut, in play order: `segments` for a compilation, else start/end."""
    raw = params.get("segments")
    if raw is None:
        raw = [{"start": params.get("start", 0), "end": params.get("end", 0)}]
    if not isinstance(raw, list) or not raw:
        raise UserError("Daftar adegan kosong.")
    if len(raw) > MAX_SEGMENTS:
        raise UserError(f"Kompilasi maksimal {MAX_SEGMENTS} adegan.")
    segs = []
    try:
        for s in raw:
            start, end = max(0.0, float(s.get("start", 0))), float(s.get("end", 0))
            if not (math.isfinite(start) and math.isfinite(end)):
                raise ValueError
            segs.append((start, end))
    except (TypeError, ValueError, AttributeError) as e:
        raise UserError("Waktu klip tidak valid.") from e
    if any(e - s < 0.5 for s, e in segs):
        raise UserError("Klip terlalu pendek." if len(segs) == 1 else "Ada adegan yang terlalu pendek (kurang dari 0,5 detik).")
    if sum(e - s for s, e in segs) > MAX_CLIP_SECONDS:
        raise UserError("Klip lebih dari 10 menit. Pendekkan dulu." if len(segs) == 1
                        else "Total kompilasi lebih dari 10 menit. Keluarkan atau pendekkan beberapa adegan.")
    return segs


def frame_rate(fps: float) -> str:
    """ffmpeg rate for a probed fps; NTSC rates print rounded (29.97) but are exact fractions."""
    if fps <= 0:
        return "30"
    for n in (24, 30, 48, 60, 120):
        if abs(fps - n * 1000 / 1001) < 0.01:
            return f"{n * 1000}/1001"
    return f"{round(fps, 3):g}"


def segment_frames(durations: list[float], rate: str) -> list[int]:
    """Whole frames per scene, rounded on the running total so the error never adds up."""
    fps = Fraction(rate)
    frames, done, total = [], 0, 0.0
    for d in durations:
        total += d
        k = max(1, round(total * fps) - done)
        frames.append(k)
        done += k
    return frames


def layout_graph(src: str, out: str, layout: str, ih: int, crop_w: int, crop_expr: str | None,
                 out_w: int, out_h: int, tag: str = "", gaming=None) -> str:
    """Filters that place one video in the output frame the way the chosen format does.

    gaming: (gameplay box, camera box, camera on top) in pixels, for the gamer layout.
    """
    if layout == "crop":
        return f"{src}crop=w={crop_w}:h={ih}:x='{crop_expr}':y=0,scale={out_w}:{out_h},setsar=1{out}"
    if layout == "blur":
        bw, bh = out_w // 4, out_h // 4
        return (
            f"{src}split=2[a{tag}][b{tag}];"
            f"[a{tag}]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},"
            f"boxblur=10:2,scale={out_w}:{out_h}[bg{tag}];"
            f"[b{tag}]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg{tag}];"
            f"[bg{tag}][fg{tag}]overlay=(W-w)/2:(H-h)/2,setsar=1{out}"
        )
    if layout == "fit":
        return (
            f"{src}scale={out_w}:{out_h}:force_original_aspect_ratio=decrease,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2,setsar=1{out}"
        )
    if layout == "gaming":
        (gx, gy, gw, gh), (fx, fy, fw, fh), face_top = gaming
        game = f"[gs{tag}]crop={gw}:{gh}:{gx}:{gy},scale={GAME_SLOT[0]}:{GAME_SLOT[1]},setsar=1[gt{tag}]"
        face = f"[fs{tag}]crop={fw}:{fh}:{fx}:{fy},scale={FACE_SLOT[0]}:{FACE_SLOT[1]},setsar=1[ft{tag}]"
        order = f"[ft{tag}][gt{tag}]" if face_top else f"[gt{tag}][ft{tag}]"
        return f"{src}split=2[gs{tag}][fs{tag}];{game};{face};{order}vstack=inputs=2,setsar=1{out}"
    return f"{src}scale={out_w}:{out_h},setsar=1{out}"  # "same": the scenes as they are


def join_graph(scenes: list[str], audio: list[bool], durations: list[float], rate: str) -> str:
    """Plays scene graphs one after another into [base] and [aout].

    scenes[i] turns [s{i}] (input i, its clock starting at 0) into [l{i}]. Each scene gets a
    whole number of frames (segment_frames) and exactly as much sound, faded over a few
    milliseconds at both ends so the joins do not click.
    """
    fps = Fraction(rate)
    parts, pads = [], []
    for i, (graph, has_audio, k) in enumerate(zip(scenes, audio, segment_frames(durations, rate))):
        d = float(k / fps)
        parts.append(f"[{i}:v]setpts=PTS-STARTPTS[s{i}]")
        parts.append(graph)
        # tpad covers a scene that came out a frame or two short; trim then cuts it exactly.
        parts.append(f"[l{i}]fps={rate},tpad=stop_mode=clone:stop_duration=1,trim=end_frame={k},"
                     f"setpts=N/FRAME_RATE/TB[v{i}]")
        sound = f"[{i}:a]asetpts=PTS-STARTPTS," if has_audio else "anullsrc=r=48000:cl=stereo,"
        parts.append(f"{sound}aformat=sample_rates=48000:channel_layouts=stereo,apad,atrim=end={d:.6f},"
                     f"asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st={max(0.0, d - 0.03):.6f}:d=0.03[sa{i}]")
        pads.append(f"[v{i}][sa{i}]")
    parts.append(f"{''.join(pads)}concat=n={len(pads)}:v=1:a=1[base][aout]")
    return ";".join(parts)


def combine_crops(crops: list[dict | None], durations: list[float], center: float) -> list[list[float]]:
    """One face path for the joined preview: each scene's keys moved to where the scene starts.

    The camera holds until a join and then jumps, as the export does with one path per scene.
    A scene without a path (detection failed) keeps a centred crop.
    """
    keys: list[list[float]] = []
    offset = 0.0
    for crop, d in zip(crops, durations):
        own = (crop or {}).get("keys") or [[0.0, center]]
        if keys:
            keys.append([round(offset - 0.001, 3), keys[-1][1]])
        for t, x in [[0.0, own[0][1]], *own]:
            if t < d and (not keys or round(offset + t, 3) > keys[-1][0]):
                keys.append([round(offset + t, 3), x])
        offset += d
    return keys


# -- render ----------------------------------------------------------------

def run_ffmpeg(cmd: list[str], duration: float, tmpdir: str, on_progress):
    """Run ffmpeg with -progress on stdout; the log goes to a file to avoid pipe stalls."""
    log_path = os.path.join(tmpdir, "ffmpeg.log")
    timeout = max(300.0, duration * 20)
    started = time.time()
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=log, text=True, errors="replace", cwd=tmpdir)
        try:
            for line in proc.stdout:
                if line.startswith("out_time_us=") and duration > 0:
                    try:
                        on_progress(min(1.0, int(line.split("=", 1)[1]) / 1e6 / duration))
                    except ValueError:
                        pass
                if time.time() - started > timeout:
                    proc.kill()
                    raise UserError("Render terlalu lama dan dihentikan. Coba klip yang lebih pendek.")
            proc.wait()
        finally:
            if proc.poll() is None:
                proc.kill()
    if proc.returncode != 0:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            tail = f.read().splitlines()[-30:]
        reason = next(
            (ln.strip() for ln in reversed(tail) if re.search(r"error|invalid|no such|not found|failed", ln, re.I)),
            tail[-1].strip() if tail else "tanpa keterangan",
        )
        raise UserError(f"FFmpeg gagal merender video: {reason[:300]}")


def _run_export_job(job: dict, params: dict):
    notes: list[str] = []
    try:
        url = clean_url(str(params.get("url", "")))
        segs = parse_segments(params)
        many = len(segs) > 1
        aspect = params.get("aspectRatio") if params.get("aspectRatio") in ASPECTS else "9:16_blur"
        style = params.get("captionStyle") if params.get("captionStyle") in CAPTION_STYLES else "viral"
        position = params.get("captionPosition") if params.get("captionPosition") in POSITIONS else "bottom"
        cues = _clean_cues(params.get("cues")) if style != "none" else []

        ffmpeg_bin = get_ffmpeg_path()
        if not ffmpeg_bin:
            raise UserError("FFmpeg belum terpasang. Mac: brew install ffmpeg. Windows: winget install ffmpeg.")

        if not _render_slot.acquire(blocking=False):
            _update(job, status="pending", message="Menunggu ekspor lain selesai...")
            _render_slot.acquire()
        try:
            tmpdir = job["tmpdir"]
            n = len(segs)
            raws, probes = [], []
            # Each scene is probed while the next one downloads (starting ffmpeg can take seconds).
            with ThreadPoolExecutor(max_workers=2) as pool:
                for i, (start, end) in enumerate(segs):
                    where = os.path.join(tmpdir, f"scene_{i:02d}") if many else tmpdir
                    os.makedirs(where, exist_ok=True)
                    _update(job, status="downloading", progress=8 + round(26 * i / n),
                            message=f"Mengunduh adegan {i + 1} dari {n} (maks. 1080p)..." if many
                            else "Mengunduh segmen video (maks. 1080p)...")
                    raws.append(download_section(url, start, end, where, ffmpeg_bin))
                    probes.append(pool.submit(probe_media, ffmpeg_bin, raws[-1]))
                metas = [p.result() for p in probes]
            duration = sum(e - s for s, e in segs) if many else (metas[0]["duration"] or segs[0][1] - segs[0][0])

            vertical = aspect != "16:9"
            out_w, out_h = (1080, 1920) if vertical else (1920, 1080)
            layout = {"16:9": "fit", "9:16_blur": "blur", "9:16_crop": "crop", "9:16_gaming": "gaming"}[aspect]
            iw, ih = metas[0]["width"], metas[0]["height"]
            if layout == "crop" and round(ih * 9 / 16) // 2 * 2 > iw:
                layout = "blur"  # the source is already narrower than 9:16
                notes.append("Video sumber sudah vertikal, jadi dipakai latar blur.")

            # One face path per scene: a cut between scenes is a cut for the camera too.
            crop_ws = [min(round(m["height"] * 9 / 16) // 2 * 2, m["width"] // 2 * 2) for m in metas]
            exprs: list[str | None] = [None] * n
            faceless: list[int] = []
            if layout == "crop":
                if not has_module("cv2"):
                    notes.append("Deteksi wajah belum terpasang, jadi dipakai potongan tengah.")
                for i, ((start, end), raw, m, crop_w) in enumerate(zip(segs, raws, metas, crop_ws)):
                    siw = m["width"]
                    reused = _preview_crop(None if many else params.get("previewId"), url, start, end)
                    if reused:
                        # Same path the preview showed, so the export frames exactly like it.
                        keys = [(t, min(siw - crop_w, max(0.0, f * siw))) for t, f in reused["keys"]]
                        found = reused["faces"]
                    elif has_module("cv2"):
                        lo, span = 35 + 20 * i / n, 20 / n
                        _update(job, status="analyzing", progress=round(lo),
                                message=f"Mendeteksi wajah di adegan {i + 1} dari {n}..." if many else "Mendeteksi wajah...")
                        samples, _ = analyze_faces(raw, m["duration"] or end - start,
                                                   lambda f: _update(job, progress=round(lo + span * f)))
                        keys = plan_crop_path(samples, siw, crop_w)
                        found = any(s["faces"] for s in samples)
                    else:
                        keys, found = None, True
                    exprs[i] = crop_x_expression(keys) if keys else f"{(siw - crop_w) / 2:.1f}"
                    if not found:
                        faceless.append(i + 1)
            if faceless and len(faceless) == n:
                notes.append("Tidak ada wajah terdeteksi, jadi dipakai potongan tengah.")
            elif faceless:
                notes.append(f"Di adegan {', '.join(map(str, faceless))} tidak ada wajah terdeteksi, "
                             "jadi di sana dipakai potongan tengah.")

            # Gamer mode: one gameplay box and one webcam box for every scene of the video.
            boxes: list = [None] * n
            area = None
            if layout == "gaming":
                g = params.get("gaming") if isinstance(params.get("gaming"), dict) else {}
                face_top = bool(g.get("faceTop"))
                game_box = clean_box(g.get("game")) or [0.0, 0.0, 1.0, 1.0]
                face_box = clean_box(g.get("face")) or _find_facecam(job, url, segs, raws, metas)
                if face_box is None:
                    face_box = [0.0, 0.0, 1.0, 1.0]
                    notes.append("Kamera wajah tidak terdeteksi, jadi bagian kamera memakai seluruh layar. "
                                 "Atur area kamera di pratinjau.")
                boxes = [
                    (fit_box(game_box, m["width"], m["height"], GAME_SLOT[0] / GAME_SLOT[1]),
                     fit_box(face_box, m["width"], m["height"], FACE_SLOT[0] / FACE_SLOT[1]), face_top)
                    for m in metas
                ]
                area = (FACE_SLOT[1], GAME_SLOT[1]) if face_top else (0, GAME_SLOT[1])

            captions = None
            if cues:
                if has_module("PIL"):
                    _update(job, status="rendering", progress=56, message="Membuat caption...")
                    captions = render_caption_track(cues, style, position, out_w, out_h, tmpdir, area)
                else:
                    notes.append("Caption dilewati karena Pillow belum terpasang.")

            if many:
                scenes = [
                    layout_graph(f"[s{i}]", f"[l{i}]", layout, m["height"], crop_ws[i], exprs[i], out_w, out_h,
                                 tag=str(i), gaming=boxes[i])
                    for i, m in enumerate(metas)
                ]
                graph = join_graph(scenes, [m["audio"] for m in metas], [e - s for s, e in segs],
                                   frame_rate(metas[0]["fps"]))
                sound = ["-map", "[aout]"]
            else:
                graph = layout_graph("[0:v]", "[base]", layout, ih, crop_ws[0], exprs[0], out_w, out_h, gaming=boxes[0])
                sound = ["-map", "0:a?"]
            cmd = [ffmpeg_bin, "-hide_banner", "-y"]
            for raw in raws:
                cmd += ["-i", raw]
            if captions:
                playlist, band_y = captions
                cmd += ["-f", "concat", "-safe", "0", "-i", playlist]
                graph += f";[base][{n}:v]overlay=0:{band_y}:eof_action=pass:format=auto[vout]"
            else:
                graph += ";[base]null[vout]"
            final = os.path.join(tmpdir, "final.mp4")
            cmd += [
                "-filter_complex", graph, "-map", "[vout]", *sound,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                "-progress", "pipe:1", "-nostats", final,
            ]
            _update(job, status="rendering", progress=60, message="Merender video...")
            run_ffmpeg(cmd, duration, tmpdir, lambda f: _update(job, progress=60 + round(39 * f)))
        finally:
            _render_slot.release()

        _update(job, status="done", progress=100, output_file=final, notes=notes,
                message="Selesai!" + (" " + " ".join(notes) if notes else ""))
    except UserError as e:
        _update(job, status="error", error=str(e), notes=notes, message=f"Gagal: {e}")
    except Exception as e:  # keep the helper alive and report something useful
        sys.stderr.write(f"[helper] export error: {e!r}\n")
        _update(job, status="error", error=f"Terjadi kesalahan: {e}", notes=notes, message="Gagal.")


def zip_exports(jobs: list[dict], folder: str) -> str:
    """One .zip of finished exports, in the given order. MP4 is already compressed: stored."""
    path = os.path.join(folder, "klip.zip")
    used: set[str] = set()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
        for j in jobs:
            stem, ext = os.path.splitext(j.get("filename") or "klip.mp4")
            name, n = f"{stem}{ext}", 2
            while name.lower() in used:
                name, n = f"{stem} ({n}){ext}", n + 1
            used.add(name.lower())
            z.write(j["output_file"], name)
    return path


def start_export(params: dict) -> str:
    url = clean_url(str(params.get("url", "")))
    if not url or not is_youtube(url):
        raise UserError("Link YouTube tidak valid.")
    parse_segments(params)  # a bad scene list is answered right away, not as a failed job
    _purge_old_jobs()
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "status": "pending",
        "progress": 2,
        "message": "Menyiapkan ekspor...",
        "created_at": time.time(),
        "tmpdir": tempfile.mkdtemp(prefix="autoclip_"),
        "filename": f"{safe_filename(str(params.get('title') or 'klip'))}.mp4",
        "notes": [],
    }
    with _jobs_lock:
        _export_jobs[job_id] = job
    threading.Thread(target=_run_export_job, args=(job, params), daemon=True).start()
    return job_id


# ------------------------------------------------------------ preview ---
#
# A light 480p copy of the clip that the web app plays and frames the way the export
# will (layout, face-following crop, captions), so the result can be checked first.

def _analyze_preview(job: dict, raw: str, iw: int, crop_w: int):
    """The face-following path for the 9:16 crop, kept so the export can reuse it."""
    try:
        _update(job, crop_state="running")
        samples, _ = analyze_faces(raw, job["duration"], lambda f: _update(job, crop_progress=round(100 * f)),
                                   min_face=WEBCAM_FACE)
        keys = plan_crop_path(samples, iw, crop_w)
        _update(job, crop_state="done", crop_progress=100, facecam=plan_facecam(samples, iw, job["height"]), crop={
            "keys": [[round(t, 3), round(x / iw, 5)] for t, x in keys],  # x as a share of the width
            "width": crop_w / iw,
            "faces": any(s["faces"] for s in big_faces(samples, iw)),
        })
    except Exception as e:  # the video itself is fine; the preview falls back to a centre crop
        sys.stderr.write(f"[helper] preview face error: {e!r}\n")
        _update(job, crop_state="error")


def _run_preview_job(job: dict):
    try:
        ffmpeg_bin = get_ffmpeg_path()
        if not ffmpeg_bin:
            raise UserError("FFmpeg belum terpasang. Mac: brew install ffmpeg. Windows: winget install ffmpeg.")
        if not _preview_slot.acquire(blocking=False):
            _update(job, message="Menunggu pratinjau lain selesai...")
            _preview_slot.acquire()
        try:
            _update(job, status="downloading", progress=15, message=f"Mengunduh potongan pratinjau ({PREVIEW_HEIGHT}p)...")
            raw = download_section(job["url"], job["start"], job["end"], job["tmpdir"], ffmpeg_bin,
                                   height=PREVIEW_HEIGHT, preview=True)
            m = probe_media(ffmpeg_bin, raw)
        finally:
            _preview_slot.release()  # the next scene can download while this one looks for faces
        iw, ih = m["width"], m["height"]
        crop_w = round(ih * 9 / 16) // 2 * 2
        crop_state = "none" if crop_w > iw else ("pending" if has_module("cv2") else "unavailable")
        # fps and audio are kept for compilations: starting ffmpeg just to probe can take seconds.
        _update(job, status="ready", progress=100, message="Pratinjau siap.", file=raw, width=iw, height=ih,
                duration=m["duration"] or job["end"] - job["start"], fps=m["fps"], audio=m["audio"],
                crop_state=crop_state)
        if crop_state == "pending":
            with _face_slot:
                _analyze_preview(job, raw, iw, crop_w)
    except UserError as e:
        _update(job, status="error", error=str(e), message=f"Gagal: {e}")
    except Exception as e:
        sys.stderr.write(f"[helper] preview error: {e!r}\n")
        _update(job, status="error", error=f"Terjadi kesalahan: {e}", message="Gagal.")


CROP_SETTLED = ("done", "error", "none", "unavailable")


def _run_compilation_preview(job: dict):
    """Joins the scenes' own previews into one video, then their face paths into one path."""
    try:
        ffmpeg_bin = get_ffmpeg_path()
        if not ffmpeg_bin:
            raise UserError("FFmpeg belum terpasang. Mac: brew install ffmpeg. Windows: winget install ffmpeg.")
        with _jobs_lock:
            parts = [_export_jobs[p] for p in job["parts"]]
        n = len(parts)
        while True:
            with _jobs_lock:
                states = [p["status"] for p in parts]
            failed = next((i for i, s in enumerate(states) if s == "error"), None)
            if failed is not None:
                raise UserError(f"Adegan {failed + 1}: {parts[failed].get('error') or 'gagal disiapkan.'}")
            done = states.count("ready")
            if done == n:
                break
            _update(job, status="downloading", progress=5 + round(80 * done / n),
                    message=f"Mengunduh adegan {done + 1} dari {n} ({PREVIEW_HEIGHT}p)...")
            time.sleep(0.25)

        _update(job, progress=86, message="Menggabungkan adegan...")
        metas = [{k: p[k] for k in ("width", "height", "fps", "audio")} for p in parts]
        iw, ih = metas[0]["width"], metas[0]["height"]
        durations = [e - s for s, e in job["segments"]]
        scenes = [layout_graph(f"[s{i}]", f"[l{i}]", "same", 0, 0, None, iw, ih) for i in range(n)]
        graph = join_graph(scenes, [m["audio"] for m in metas], durations, frame_rate(metas[0]["fps"]))
        out = os.path.join(job["tmpdir"], "preview.mp4")
        cmd = [ffmpeg_bin, "-hide_banner", "-y"]
        for p in parts:
            cmd += ["-i", p["file"]]
        cmd += ["-filter_complex", graph, "-map", "[base]", "-map", "[aout]", *PREVIEW_ENCODE,
                "-progress", "pipe:1", "-nostats", out]
        run_ffmpeg(cmd, sum(durations), job["tmpdir"], lambda f: _update(job, progress=86 + round(13 * f)))

        crop_w = round(ih * 9 / 16) // 2 * 2
        crop_state = "none" if crop_w > iw else ("pending" if has_module("cv2") else "unavailable")
        _update(job, status="ready", progress=100, message="Pratinjau siap.", file=out, width=iw, height=ih,
                duration=sum(durations), crop_state=crop_state)
        if crop_state != "pending":
            return
        while True:
            with _jobs_lock:
                states = [p.get("crop_state") for p in parts]
                progress = sum(100 if p.get("crop_state") in CROP_SETTLED else p.get("crop_progress", 0)
                               for p in parts) // n
            if all(s in CROP_SETTLED for s in states):
                break
            _update(job, crop_state="running" if "running" in states else "pending", crop_progress=progress)
            time.sleep(0.25)
        crops = [p.get("crop") if p.get("crop_state") == "done" else None for p in parts]
        cams = [p["facecam"] for p in parts if p.get("facecam")]
        _update(job, crop_state="done", crop_progress=100,
                facecam=max(cams, key=lambda c: c["support"]) if cams else None, crop={
            "keys": combine_crops(crops, durations, round((1 - crop_w / iw) / 2, 5)),
            "width": crop_w / iw,
            "faces": any(c and c["faces"] for c in crops),
        })
    except UserError as e:
        _update(job, status="error", error=str(e), message=f"Gagal: {e}")
    except Exception as e:
        sys.stderr.write(f"[helper] compilation preview error: {e!r}\n")
        _update(job, status="error", error=f"Terjadi kesalahan: {e}", message="Gagal.")


def _scene_preview(url: str, start: float, end: float) -> str:
    """Id of the preview of one scene; an existing one for the same scene is reused."""
    with _jobs_lock:
        for j in _export_jobs.values():
            if (j.get("kind") == "preview" and "parts" not in j and j["status"] != "error"
                    and (j["url"], j["start"], j["end"]) == (url, start, end)):
                j["touched"] = time.time()
                return j["id"]
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "kind": "preview",
            "status": "pending",
            "progress": 5,
            "message": "Menyiapkan pratinjau...",
            "created_at": time.time(),
            "tmpdir": tempfile.mkdtemp(prefix="autoclip_preview_"),
            "url": url,
            "start": start,
            "end": end,
        }
        _export_jobs[job_id] = job
    threading.Thread(target=_run_preview_job, args=(job,), daemon=True).start()
    return job_id


def start_preview(params: dict) -> str:
    """Id of a preview job for a clip (start/end) or a compilation (segments); same input, same job."""
    url = clean_url(str(params.get("url", "")))
    if not url or not is_youtube(url):
        raise UserError("Link YouTube tidak valid.")
    segs = [(round(s, 2), round(e, 2)) for s, e in parse_segments(params)]
    _purge_old_jobs()
    if len(segs) == 1:
        return _scene_preview(url, *segs[0])
    with _jobs_lock:
        for j in _export_jobs.values():
            if (j.get("kind") == "preview" and j.get("segments") == segs and j["url"] == url
                    and j["status"] != "error"):
                j["touched"] = time.time()
                return j["id"]
    parts = [_scene_preview(url, s, e) for s, e in segs]
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "kind": "preview",
        "status": "pending",
        "progress": 5,
        "message": "Menyiapkan pratinjau...",
        "created_at": time.time(),
        "tmpdir": tempfile.mkdtemp(prefix="autoclip_preview_"),
        "url": url,
        "segments": segs,
        "parts": parts,
    }
    with _jobs_lock:
        _export_jobs[job_id] = job
    threading.Thread(target=_run_compilation_preview, args=(job,), daemon=True).start()
    return job_id


def preview_status(job: dict) -> dict:
    return {
        "ok": True,
        "id": job["id"],
        "status": job.get("status", "pending"),
        "progress": job.get("progress", 0),
        "message": job.get("message", ""),
        "error": job.get("error"),
        "width": job.get("width"),
        "height": job.get("height"),
        "duration": job.get("duration"),
        "crop_state": job.get("crop_state"),
        "crop_progress": job.get("crop_progress", 0),
        "crop": job.get("crop"),
        "facecam": job.get("facecam"),
    }


def _preview_scan(preview_id, url: str, start: float, end: float) -> dict | None:
    """The preview whose face scan of exactly this scene is done, if any (that preview first)."""
    def fits(j):
        return (j is not None and j.get("kind") == "preview" and "parts" not in j and j.get("crop_state") == "done"
                and j["url"] == url and abs(j["start"] - start) <= 0.02 and abs(j["end"] - end) <= 0.02)

    with _jobs_lock:
        job = _export_jobs.get(str(preview_id or ""))
        if not fits(job):
            job = next((j for j in _export_jobs.values() if fits(j)), None)
        return job


def _preview_crop(preview_id, url: str, start: float, end: float) -> dict | None:
    """The face path a preview already found for exactly this scene, if any."""
    job = _preview_scan(preview_id, url, start, end)
    return job["crop"] if job else None


def _find_facecam(job: dict, url: str, segs, raws, metas) -> list[float] | None:
    """The webcam box for an export that was not given one: from the scenes' previews when
    they scanned for faces, else by scanning the downloaded scenes. The surest one wins."""
    found = []
    for (start, end), raw, m in zip(segs, raws, metas):
        scan = _preview_scan(None, url, start, end)
        if scan:
            if scan.get("facecam"):
                found.append(scan["facecam"])
        elif has_module("cv2"):
            _update(job, status="analyzing", progress=40, message="Mencari kamera wajah...")
            samples, _ = analyze_faces(raw, m["duration"] or end - start, lambda f: None, min_face=WEBCAM_FACE)
            cam = plan_facecam(samples, m["width"], m["height"])
            if cam:
                found.append(cam)
    return max(found, key=lambda c: c["support"])["box"] if found else None


def ensure_optional_packages():
    """Install face detection and caption drawing packages into the helper's own venv."""
    missing = [pkg for mod, pkg in OPTIONAL_PACKAGES if not has_module(mod)]
    if not missing:
        return
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if not in_venv:
        print(f"  Untuk deteksi wajah & caption, pasang: pip install {' '.join(missing)}")
        return
    print(f"Memasang komponen tambahan (sekali saja): {', '.join(missing)} ...", flush=True)
    res = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", *missing])
    importlib.invalidate_caches()
    if res.returncode != 0:
        print("  Gagal memasang; ekspor tetap jalan tanpa deteksi wajah/caption.")


def health() -> dict:
    ff_path = get_ffmpeg_path()
    return {
        "ok": True,
        "name": "autoclip-helper",
        "version": VERSION,
        "yt_dlp": yt_dlp.version.__version__ if yt_dlp else None,
        "ffmpeg": bool(ff_path),
        "face_detect": has_module("cv2"),
        "captions": has_module("PIL"),
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

    def log_request(self, code="-", size="-"):
        # Progress polls and video range requests would flood the window; failures still show.
        path = urlparse(self.path).path
        if str(code) in ("200", "206") and (path.endswith("/status") or path == "/preview/video"):
            return
        super().log_request(code, size)

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

    def send_file_download(self, filepath: str, filename: str, mime: str = "video/mp4", ext: str = ".mp4"):
        if not os.path.isfile(filepath):
            return self.send_json(404, {"error": "file not found"})
        size = os.path.getsize(filepath)
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(size))
        clean_name = safe_filename(filename)
        if not clean_name.lower().endswith(ext):
            clean_name += ext
        # Headers are Latin-1: an ASCII name for old browsers, the real one (any script) beside it.
        plain = clean_name.encode("ascii", "ignore").decode().strip() or f"klip{ext}"
        self.send_header("Content-Disposition", f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(clean_name)}")
        self.send_header("Cache-Control", "no-cache")
        self.cors()
        self.end_headers()
        try:
            with open(filepath, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the browser cancelled the download

    def send_video(self, filepath: str):
        """A video with HTTP range support; Safari will not play media served without it."""
        try:
            size = os.path.getsize(filepath)
        except OSError:
            return self.send_json(404, {"error": "file not found"})
        start, end = 0, size - 1
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        partial = bool(m and (m.group(1) or m.group(2)))
        if partial:
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            else:  # "bytes=-N": the last N bytes
                start = max(0, size - int(m.group(2)))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "no-cache")
        self.cors()
        self.end_headers()
        try:
            with open(filepath, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # the player seeked elsewhere and dropped this request

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
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/health":
            if not self.origin_allowed():
                return self.send_json(
                    200, {"ok": False, "error": "origin_not_allowed", "origin": self.origin}, allow_any_origin=True
                )
            return self.send_json(200, health())

        if not self.origin_allowed():
            return self.reject_origin()

        if path == "/export/status":
            qs = parse_qs(parsed.query)
            job_id = (qs.get("jobId") or [""])[0]
            with _jobs_lock:
                job = _export_jobs.get(job_id)
            if not job or job.get("kind") == "preview":
                return self.send_json(404, {"error": "Pekerjaan ekspor tidak ditemukan."})
            return self.send_json(200, {
                "ok": True,
                "jobId": job_id,
                "status": job.get("status", "pending"),
                "progress": job.get("progress", 0),
                "message": job.get("message", ""),
                "filename": job.get("filename", "clip.mp4"),
                "error": job.get("error"),
                "notes": job.get("notes", []),
            })

        if path == "/export/download":
            qs = parse_qs(parsed.query)
            job_id = (qs.get("jobId") or [""])[0]
            with _jobs_lock:
                job = _export_jobs.get(job_id)
            if not job:
                return self.send_json(404, {"error": "Pekerjaan ekspor tidak ditemukan."})
            if job.get("status") != "done" or not job.get("output_file"):
                return self.send_json(400, {"error": "Video belum selesai diproses."})
            return self.send_file_download(job["output_file"], job.get("filename", "clip.mp4"))

        if path == "/export/zip":
            qs = parse_qs(parsed.query)
            ids = [i for i in (qs.get("jobs") or [""])[0].split(",") if i][:100]
            with _jobs_lock:
                done = [j for j in (_export_jobs.get(i) for i in ids)
                        if j and j.get("kind") != "preview" and j.get("status") == "done" and j.get("output_file")]
            if not done:
                return self.send_json(404, {"error": "Belum ada video yang selesai untuk dibungkus."})
            folder = tempfile.mkdtemp(prefix="autoclip_zip_")
            try:
                archive = zip_exports(done, folder)
                return self.send_file_download(archive, (qs.get("name") or ["klip"])[0], "application/zip", ".zip")
            finally:
                shutil.rmtree(folder, ignore_errors=True)

        if path in ("/preview/status", "/preview/video"):
            job_id = (parse_qs(parsed.query).get("id") or [""])[0]
            with _jobs_lock:
                job = _export_jobs.get(job_id)
                if job and job.get("kind") == "preview":
                    job["touched"] = time.time()
            if not job or job.get("kind") != "preview":
                return self.send_json(404, {"error": "Pratinjau tidak ditemukan. Buka pratinjau lagi."})
            if path == "/preview/status":
                return self.send_json(200, preview_status(job))
            if job.get("status") != "ready":
                return self.send_json(409, {"error": "Pratinjau belum siap."})
            return self.send_video(job["file"])

        if CFG.app_url:
            return self.send_app_file(path)
        return self.send_json(404, {"error": "not found"})

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

        path = urlparse(self.path).path
        if path == "/captions":
            try:
                self.send_json(200, get_captions(str(body.get("url", "")), body.get("track")))
            except UserError as e:
                self.send_json(400, {"error": str(e)})
            except Exception as e:
                sys.stderr.write(f"[helper] error: {e!r}\n")
                self.send_json(500, {"error": friendly_error(e)})
            return

        if path == "/export":
            try:
                return self.send_json(200, {"ok": True, "jobId": start_export(body)})
            except UserError as e:
                return self.send_json(400, {"error": str(e)})

        if path == "/preview":
            try:
                return self.send_json(200, {"ok": True, "id": start_preview(body)})
            except UserError as e:
                return self.send_json(400, {"error": str(e)})

        return self.send_json(404, {"error": "not found"})


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

    ensure_optional_packages()
    atexit.register(_cleanup_all_jobs)

    h = health()
    yes = lambda v: "ada" if v else "tidak ada"  # noqa: E731
    print(f"AutoClip helper {VERSION} berjalan di http://127.0.0.1:{args.port}")
    print(f"  yt-dlp {h['yt_dlp']} | ffmpeg: {yes(h['ffmpeg'])} | JS runtime: {h['js_runtime'] or 'tidak ada'}")
    print(f"  deteksi wajah: {yes(h['face_detect'])} | caption: {yes(h['captions'])}")
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
