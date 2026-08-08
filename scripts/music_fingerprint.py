# -*- coding: utf-8 -*-
"""
Music fingerprinting — Roadmap item 2.3 (بصمة الموسيقى Chromaprint).

Protects against audio copyright claims before you publish a clip:

  * Local fingerprinting with Chromaprint via `pyacoustid` or the `fpcalc`
    CLI (Windows: drop fpcalc.exe next to the app / on PATH).
  * Identification against the public AcoustID database (free API key,
    override with ACOUSTID_API_KEY; a public default key is bundled).
  * Optional LOCAL database matching: point the tool at a folder of songs
    you are licensed to use (or must avoid); any clip that borrows more
    than a threshold of their audio is flagged — no network needed.

Pipeline integration
--------------------
  * `analyze_project()` fingerprints every clip in `final/`, writes
    `music_fingerprint.json`, and returns a report.
  * The upload gate consults that report: with `gate="warn"` (default) a
    matching clip is flagged but can still be uploaded; with `gate="block"`
    the clip is REFUSED before it ever reaches a platform.

Everything degrades gracefully when Chromaprint is missing: the module
never raises on import, and `analyze_project()` reports `no_fpcalc` per
clip instead of crashing the pipeline.
"""

import json
import os
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

REPORT_NAME = "music_fingerprint.json"

# Public default client key used by open-source Chromaprint tools.
# Override with the ACOUSTID_API_KEY env var.
DEFAULT_ACOUSTID_KEY = "8XaBELgH"
ACOUSTID_LOOKUP_URL = "https://api.acoustid.org/v2/lookup"

# Fraction of n-gram overlap (0..1) before a local match counts as "matched".
LOCAL_MATCH_THRESHOLD = 0.10


def get_acoustid_key():
    return os.getenv("ACOUSTID_API_KEY") or DEFAULT_ACOUSTID_KEY


class FpcalcUnavailable(RuntimeError):
    """Chromaprint (fpcalc / pyacoustid) is not available on this machine."""


def _import_acoustid():
    """Best-effort import of pyacoustid; never raises."""
    try:
        import acoustid  # noqa: F401
        return acoustid
    except Exception:
        return None


def fpcalc_available():
    """True when we can fingerprint locally (pyacoustid lib or fpcalc CLI)."""
    if _import_acoustid() is not None:
        return True
    return shutil.which("fpcalc") is not None


def fingerprint_file(video_path, timeout=600):
    """Return {"fingerprint", "duration", "engine", "format"} for a media file.

    format is "compressed" (pyacoustid, AcoustID-ready) or "raw" (fpcalc ints).
    Raises FpcalcUnavailable when no backend exists; RuntimeError when a
    backend exists but fails on this file.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError("media not found: {}".format(video_path))

    acoustid = _import_acoustid()
    if acoustid is not None:
        try:
            duration, fingerprint = acoustid.fingerprint_file(
                str(video_path), timeout=timeout)
            return {"fingerprint": fingerprint, "duration": float(duration),
                    "engine": "pyacoustid", "format": "compressed"}
        except Exception:
            pass  # fall through to the fpcalc CLI

    fpcalc = shutil.which("fpcalc")
    if fpcalc is None:
        raise FpcalcUnavailable(
            "Chromaprint not found. Install it:\n"
            "  • Windows: download fpcalc.exe from the chromaprint releases "
            "(https://github.com/acoustid/chromaprint/releases) and put it in "
            "the app folder or on PATH, OR\n"
            "  • pip install pyacoustid  (also needs the native chromaprint lib), OR\n"
            "  • Linux: sudo apt-get install libchromaprint-tools")

    cmd = [fpcalc, "-raw", str(video_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        raise RuntimeError("fpcalc failed to start: {}".format(e)) from None
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:300]
        raise RuntimeError("fpcalc failed ({}): {}".format(proc.returncode, detail))

    duration = 0.0
    ints = []
    for line in (proc.stdout or "").splitlines():
        if line.startswith("DURATION="):
            try:
                duration = float(line.split("=", 1)[1])
            except ValueError:
                pass
        elif line.startswith("FINGERPRINT="):
            raw = line.split("=", 1)[1].strip()
            if raw and raw != "0":
                ints = [int(x) for x in raw.split(",") if x.strip()]
    if not ints:
        raise RuntimeError(
            "fpcalc produced no fingerprint ({}). Is the file a valid video "
            "with audio?".format(video_path))
    return {"fingerprint": ints, "duration": duration, "engine": "fpcalc",
            "format": "raw"}


def decode_fingerprint(fingerprint, fmt="compressed"):
    """Return the raw list of 32-bit sub-fingerprints (ints).

    Works for both formats; returns [] when decoding is impossible.
    """
    if fmt == "raw" or isinstance(fingerprint, (list, tuple)):
        return [int(x) for x in fingerprint]
    acoustid = _import_acoustid()
    if acoustid is not None:
        try:
            from acoustid.chromaprint import decode_fingerprint as _decode
            return list(_decode(fingerprint))
        except Exception:
            pass
    return []


# ---------------------------------------------------------------------------
# AcoustID identification (network)
# ---------------------------------------------------------------------------

def identify_acoustid(fingerprint, duration, api_key=None, timeout=60):
    """Query the AcoustID lookup API.

    Requires a COMPRESSED fingerprint (pyacoustid engine). Returns a list of
    {"artist", "title", "score", "id", "sources"} sorted by score, or [] when
    nothing matched or the lookup cannot run.
    """
    if isinstance(fingerprint, (list, tuple)):
        return []  # raw ints — can't query without an encoder
    params = {
        "client": api_key or get_acoustid_key(),
        "fingerprint": fingerprint,
        "duration": int(round(float(duration or 0))),
        "meta": "recordings+releasegroups+sources",
    }
    url = "{}?{}".format(ACOUSTID_LOOKUP_URL, urllib.parse.urlencode(params))
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception:
        return []
    if payload.get("status") != "ok":
        return []
    results = []
    for item in payload.get("results", []):
        for recording in item.get("recordings", []):
            artists = ", ".join(
                a.get("name", "") for a in recording.get("artists", [])
                if a.get("name"))
            results.append({
                "id": recording.get("id", ""),
                "artist": artists,
                "title": recording.get("title", ""),
                "score": item.get("score", 0.0),
                "sources": recording.get("sources", 0),
            })
    results.sort(key=lambda r: (r["score"], r["sources"]), reverse=True)
    return results


# ---------------------------------------------------------------------------
# Local database matching (offline)
# ---------------------------------------------------------------------------

def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def build_local_db(music_dir, cache_path=None):
    """Fingerprint every audio/video file under `music_dir`.

    Returns a database dict: {"songs": [{"path", "title", "duration",
    "fingerprint", "format"}]}. Unreadable files are skipped (never crash).
    """
    if not os.path.isdir(music_dir):
        raise NotADirectoryError("local music dir not found: {}".format(music_dir))
    supported = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus",
                 ".mp4", ".mkv", ".webm", ".mov")
    songs = []
    for root, _dirs, files in os.walk(music_dir):
        for name in sorted(files):
            if not name.lower().endswith(supported):
                continue
            path = os.path.join(root, name)
            try:
                fp = fingerprint_file(path)
            except Exception:
                continue
            songs.append({
                "path": path,
                "title": os.path.splitext(name)[0],
                "duration": fp["duration"],
                "fingerprint": fp["fingerprint"],
                "format": fp["format"],
            })
    db = {"songs": songs}
    if cache_path:
        _atomic_write(cache_path, db)
    return db


def load_local_db(db_path):
    if not os.path.exists(db_path):
        return {"songs": []}
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"songs": []}


def _grams(ints, window=8):
    """Sliding-window n-grams of raw sub-fingerprints."""
    if len(ints) < window:
        return {tuple(ints)}
    return {tuple(ints[i:i + window]) for i in range(len(ints) - window + 1)}


def match_local(db, fingerprint, fmt="compressed", threshold=None):
    """Compare a clip fingerprint against a local DB.

    score = fraction of the clip's n-grams that appear in the best song.
    Returns {"matched", "song", "score", "threshold", "error"}.
    """
    threshold = LOCAL_MATCH_THRESHOLD if threshold is None else threshold
    clip_ints = decode_fingerprint(fingerprint, fmt)
    if not clip_ints:
        return {"matched": False, "song": None, "score": 0.0,
                "threshold": threshold, "error": "decode_failed"}
    clip_grams = _grams(clip_ints)
    if not clip_grams:
        return {"matched": False, "song": None, "score": 0.0,
                "threshold": threshold, "error": "empty_fingerprint"}

    best = {"score": 0.0, "song": None}
    for song in (db or {}).get("songs", []):
        song_ints = decode_fingerprint(song.get("fingerprint"),
                                       song.get("format", "compressed"))
        if not song_ints:
            continue
        song_grams = _grams(song_ints)
        if not song_grams:
            continue
        overlap = len(clip_grams & song_grams)
        if overlap == 0:
            continue
        score = overlap / float(len(clip_grams))
        if score > best["score"]:
            best = {"score": score, "song": song["title"]}

    return {
        "matched": best["score"] >= threshold and best["song"] is not None,
        "song": best["song"],
        "score": round(best["score"], 4),
        "threshold": threshold,
    }


# ---------------------------------------------------------------------------
# Project analysis
# ---------------------------------------------------------------------------

def _find_clips(project_folder):
    import glob
    final_dir = os.path.join(project_folder, "final")
    hits = sorted(glob.glob(os.path.join(final_dir, "*.mp4")))
    if hits:
        return hits
    return sorted(glob.glob(os.path.join(project_folder, "cuts", "*.mp4")))


def _index_from_path(path):
    import re
    m = re.match(r"(\d+)", os.path.basename(path))
    return int(m.group(1)) if m else None


def analyze_project(project_folder, acoustid_key=None, local_db=None,
                    gate="warn", threshold=None, do_acoustid=True,
                    do_local=True):
    """Fingerprint every clip and write `music_fingerprint.json`.

    `local_db` may be a db dict (from build_local_db) or a path to a cached
    JSON db. Returns the report dict.
    """
    if isinstance(local_db, str) or local_db is None:
        local_db = load_local_db(local_db) if local_db else {"songs": []}

    report = {
        "gate": gate,
        "threshold": threshold or LOCAL_MATCH_THRESHOLD,
        "acoustid_key_configured": bool(os.getenv("ACOUSTID_API_KEY")),
        "clips": [],
        "summary": {"checked": 0, "matched": 0, "warned": 0,
                    "no_fpcalc": 0, "errors": 0},
    }
    for clip in _find_clips(project_folder):
        entry = {"index": _index_from_path(clip), "video": clip,
                 "verdict": "clean", "suggestion": None}
        try:
            fp = fingerprint_file(clip)
        except FpcalcUnavailable as e:
            entry["verdict"] = "no_fpcalc"
            entry["suggestion"] = str(e).splitlines()[0]
            report["summary"]["no_fpcalc"] += 1
            report["clips"].append(entry)
            continue
        except Exception as e:
            entry["verdict"] = "error"
            entry["suggestion"] = str(e)[:200]
            report["summary"]["errors"] += 1
            report["clips"].append(entry)
            continue

        entry["duration"] = round(fp["duration"], 2)
        entry["engine"] = fp["engine"]
        report["summary"]["checked"] += 1

        # Local reference matching (offline, both engines work).
        if do_local and local_db.get("songs"):
            local = match_local(local_db, fp["fingerprint"], fp["format"],
                                threshold=threshold)
            entry["local_match"] = local
            if local["matched"]:
                entry["verdict"] = "local_match"
                entry["suggestion"] = ("Audio overlaps local reference "
                                       "'{}' ({:.0%})".format(
                                           local["song"], local["score"]))

        # AcoustID lookup (needs compressed fingerprint → pyacoustid engine).
        acoustid_matches = []
        if do_acoustid and fp["format"] == "compressed":
            acoustid_matches = identify_acoustid(fp["fingerprint"],
                                                 fp["duration"],
                                                 api_key=acoustid_key)
            entry["acoustid"] = acoustid_matches[:3]
            if acoustid_matches and acoustid_matches[0]["score"] >= 0.5:
                top = acoustid_matches[0]
                if entry["verdict"] == "clean":
                    entry["verdict"] = "acoustid_match"
                entry["suggestion"] = (
                    "AcoustID: '{}' by {} (score {:.0%}, {} sources)".format(
                        top["title"], top["artist"], top["score"],
                        top.get("sources", 0)))

        if entry["verdict"] == "acoustid_match":
            report["summary"]["matched"] += 1
        elif entry["verdict"] == "local_match":
            report["summary"]["matched"] += 1
            report["summary"]["warned"] += 1
        report["clips"].append(entry)

    _atomic_write(os.path.join(project_folder, REPORT_NAME), report)
    return report


# ---------------------------------------------------------------------------
# Upload-gate integration
# ---------------------------------------------------------------------------

def music_gate_reasons(project_folder, index=None, gate=None):
    """Reasons a clip should not be published, from the music report.

    gate: "off" → no reasons; "warn" → medium-severity flag; "block" → high.
    Returns [] when there is no report or no match (safe default).
    """
    if gate == "off":
        return []
    path = os.path.join(project_folder, REPORT_NAME)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            report = json.load(f)
    except Exception:
        return []
    if gate is None:
        gate = report.get("gate", "warn")
    reasons = []
    for entry in report.get("clips", []):
        if index is not None and entry.get("index") != index:
            continue
        if entry.get("verdict") in ("acoustid_match", "local_match"):
            detail = entry.get("suggestion") or "audio fingerprint matched"
            reasons.append({
                "source": "music_fingerprint",
                "detail": "clip #{} — {}".format(entry.get("index", "?"), detail),
                "severity": "high" if gate == "block" else "medium",
            })
    return reasons


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        description="ViralCutter music fingerprint check (Chromaprint/AcoustID).")
    parser.add_argument("--project", help="Project folder to analyze")
    parser.add_argument("--acoustid-key", default=None, help="AcoustID API key (or ACOUSTID_API_KEY env)")
    parser.add_argument("--local-db", default=None,
                        help="JSON db from --build-local-db, or a folder of reference songs")
    parser.add_argument("--build-local-db", default=None,
                        help="Fingerprint a folder of songs into a JSON cache (no project needed)")
    parser.add_argument("--db-cache", default=None, help="Cache path for --build-local-db")
    parser.add_argument("--gate", choices=["warn", "block", "off"], default="warn")
    parser.add_argument("--threshold", type=float, default=None)
    args = parser.parse_args(argv)

    if args.build_local_db:
        cache = args.db_cache or os.path.join(
            os.path.expanduser("~"), ".viralcutter", "music_db.json")
        db = build_local_db(args.build_local_db, cache_path=cache)
        print("local DB: {} songs → {}".format(len(db["songs"]), cache))
        return 0

    if not args.project:
        parser.error("--project is required (or use --build-local-db)")

    local_db = None
    if args.local_db:
        if os.path.isdir(args.local_db):
            cache = args.db_cache or os.path.join(
                os.path.expanduser("~"), ".viralcutter", "music_db.json")
            local_db = build_local_db(args.local_db, cache_path=cache)
            print("local DB built: {} songs".format(len(local_db["songs"])))
        else:
            local_db = load_local_db(args.local_db)

    report = analyze_project(args.project, acoustid_key=args.acoustid_key,
                             local_db=local_db, gate=args.gate,
                             threshold=args.threshold)
    s = report["summary"]
    print("music check: {} clips, {} matched, {} no_fpcalc, {} errors".format(
        s["checked"], s["matched"], s["no_fpcalc"], s["errors"]))
    for clip in report["clips"]:
        verdict = clip["verdict"]
        mark = {"clean": "✅", "acoustid_match": "🎵⚠️", "local_match": "🎵⚠️",
                "no_fpcalc": "⚠️", "error": "❌"}.get(verdict, "?")
        print("  {} #{} {} — {}".format(mark, clip.get("index", "?"),
                                        os.path.basename(clip["video"]), verdict))
        if clip.get("suggestion"):
            print("      ↳ {}".format(clip["suggestion"]))
    print("report → {}".format(os.path.join(args.project, REPORT_NAME)))
    return 3 if s["matched"] and args.gate == "block" else 0


if __name__ == "__main__":
    sys.exit(main())
