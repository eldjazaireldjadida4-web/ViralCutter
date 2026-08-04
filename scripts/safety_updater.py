# -*- coding: utf-8 -*-
"""
Safety blocklist auto-updater.

YouTube's policies and the evasion vocabulary evolve constantly. Instead of
waiting for a code release, ViralCutter keeps a *versioned blocklist pack*
in the GitHub repo and every installation updates itself from it:

    repo: safety_blocklist.json            (canonical, versioned)
    user: safety_blocklist_cache.json      (downloaded copy, git-ignored)

Guarantees:
* Offline-safe — any network/parse failure keeps the previous cache (and if
  there is no cache at all, the built-in list still protects the user).
* Only *newer* versions replace the cache.
* Cheap — a daily stamp file prevents hammering GitHub on every run.
* No dependencies — pure urllib (works on Windows out of the box).
"""

import json
import os
import time
import urllib.request

REMOTE_URL = ("https://raw.githubusercontent.com/"
              "eldjazaireldjadida4-web/ViralCutter/main/safety_blocklist.json")

CACHE_FILENAME = "safety_blocklist_cache.json"
STAMP_FILENAME = ".safety_update_stamp"
FETCH_TIMEOUT = 10          # seconds
MAX_TERMS = 20000           # sanity limit for a downloaded pack
ONE_DAY = 24 * 3600


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cache_path(base_dir=None):
    return os.path.join(base_dir or _repo_root(), CACHE_FILENAME)


def stamp_path(base_dir=None):
    return os.path.join(base_dir or _repo_root(), STAMP_FILENAME)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_pack(data):
    """Return the normalized {"version": int, "terms": [...]} or None."""
    if not isinstance(data, dict):
        return None
    terms = data.get("terms")
    if not isinstance(terms, list) or not terms or len(terms) > MAX_TERMS:
        return None
    clean = []
    for t in terms:
        if not isinstance(t, dict) or not t.get("term"):
            continue
        clean.append({
            "term": str(t["term"])[:200],
            "lang": str(t.get("lang", "multi"))[:20],
            "severity": t.get("severity") if t.get("severity") in ("low", "medium", "high") else "high",
            "category": str(t.get("category", "custom"))[:50],
        })
    if not clean:
        return None
    try:
        version = int(data.get("version", 0))
    except Exception:
        version = 0
    return {"version": version, "terms": clean,
            "updated": str(data.get("updated", ""))[:40]}


def load_cached_pack(base_dir=None):
    """Read the downloaded cache (None if missing/corrupt)."""
    path = cache_path(base_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return validate_pack(json.load(f))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Update logic
# ---------------------------------------------------------------------------

def _fetch_json(url, timeout=FETCH_TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": "ViralCutter-safety-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(2 * 1024 * 1024)  # 2 MB cap
    return json.loads(raw.decode("utf-8"))


def check_and_update(base_dir=None, url=REMOTE_URL, force=False):
    """Fetch the remote pack and replace the cache if it is newer.

    Returns a status dict: {status: updated|up-to-date|offline|error,
                            version, previous_version, message}
    Never raises.
    """
    cached = load_cached_pack(base_dir)
    cached_version = cached["version"] if cached else 0

    # daily throttle (unless forced)
    stamp = stamp_path(base_dir)
    if not force and os.path.exists(stamp):
        try:
            last = float(open(stamp, encoding="utf-8").read().strip() or "0")
            if time.time() - last < ONE_DAY:
                return {"status": "up-to-date", "version": cached_version,
                        "previous_version": cached_version,
                        "message": "checked recently (daily throttle)"}
        except Exception:
            pass

    try:
        remote = validate_pack(_fetch_json(url))
    except Exception as e:
        return {"status": "offline", "version": cached_version,
                "previous_version": cached_version,
                "message": f"could not reach update server ({e}) — using local list"}

    try:
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except Exception:
        pass

    if remote is None:
        return {"status": "error", "version": cached_version,
                "previous_version": cached_version,
                "message": "remote pack invalid — keeping local list"}

    if remote["version"] <= cached_version:
        return {"status": "up-to-date", "version": cached_version,
                "previous_version": cached_version,
                "message": f"list is current (v{cached_version})"}

    try:
        with open(cache_path(base_dir), "w", encoding="utf-8") as f:
            json.dump(remote, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {"status": "error", "version": cached_version,
                "previous_version": cached_version,
                "message": f"could not write cache ({e})"}

    return {"status": "updated", "version": remote["version"],
            "previous_version": cached_version,
            "message": f"updated v{cached_version} → v{remote['version']} "
                       f"({len(remote['terms'])} terms)"}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Update the hate-speech blocklist from GitHub.")
    parser.add_argument("--force", action="store_true", help="ignore the daily throttle")
    parser.add_argument("--url", default=REMOTE_URL, help="override the pack URL")
    args = parser.parse_args()

    result = check_and_update(force=args.force, url=args.url)
    print(f"[safety-updater] {result['status']}: {result['message']}")


if __name__ == "__main__":
    main()
