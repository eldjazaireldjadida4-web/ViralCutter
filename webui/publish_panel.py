"""Publish panel — per-clip play / translate / music-check / upload.

Pure logic extracted from the WebUI so it stays unit-testable:
- list rendered clips of a project (final/ first, then cuts/)
- find the subtitle JSON for a clip
- translate one clip's subtitles (reuses scripts/translate_json)
- run the music fingerprint check (scripts/music_fingerprint)
- upload one clip through the safety gate (scripts/upload_gate)

No gradio imports in this module.
"""
import asyncio
import json
import os
import queue
import sys
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# Clip discovery
# ---------------------------------------------------------------------------

def list_clips(project_path):
    """Rendered clips of a project: final/*.mp4, falling back to cuts/*.mp4."""
    if not project_path or not os.path.isdir(project_path):
        return []
    final_dir = os.path.join(project_path, "final")
    if os.path.isdir(final_dir):
        hits = sorted(f for f in os.listdir(final_dir) if f.lower().endswith(".mp4"))
        if hits:
            return [os.path.join(final_dir, f) for f in hits]
    cuts_dir = os.path.join(project_path, "cuts")
    if os.path.isdir(cuts_dir):
        return sorted(os.path.join(cuts_dir, f) for f in os.listdir(cuts_dir)
                      if f.lower().endswith(".mp4"))
    return []


def clip_index(video_path):
    """Leading digits of the filename → segment index (for gate checks)."""
    import re
    m = re.match(r"(\d+)", os.path.basename(video_path))
    return int(m.group(1)) if m else None


def _subtitle_files_for_clip(project_path, video_path):
    """Candidate subtitle JSONs for a clip (subs/<stem>*_processed.json etc)."""
    stem = os.path.splitext(os.path.basename(video_path))[0]
    subs_dir = os.path.join(project_path, "subs")
    if not os.path.isdir(subs_dir):
        return []
    candidates = []
    for name in sorted(os.listdir(subs_dir)):
        if not name.endswith(".json"):
            continue
        base = os.path.splitext(name)[0]
        if base.startswith(stem):
            candidates.append(os.path.join(subs_dir, name))
    return candidates


def find_subs_for_clip(project_path, video_path):
    """Best subtitle JSON for a clip (prefer *_processed.json)."""
    candidates = _subtitle_files_for_clip(project_path, video_path)
    if not candidates:
        return None
    processed = [c for c in candidates if "_processed" in os.path.basename(c)]
    return (processed or candidates)[0]


def segments_for_project(project_path):
    """The viral_segments.txt segments list (for title/caption suggestions)."""
    path = os.path.join(project_path, "viral_segments.txt")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        segments = data.get("segments", [])
        return segments if isinstance(segments, list) else []
    except Exception:
        return []


def clip_suggestion(project_path, video_path):
    """Suggested title+caption for a clip from its viral segment entry."""
    idx = clip_index(video_path)
    segments = segments_for_project(project_path)
    if idx is None or idx >= len(segments):
        return "", ""
    seg = segments[idx]
    return (seg.get("title") or ""), (seg.get("caption") or "")


# ---------------------------------------------------------------------------
# Per-clip translate
# ---------------------------------------------------------------------------

def translate_clip(project_path, video_path, target_lang):
    """Translate one clip's subtitles to target_lang (deep-translator).

    Returns (ok: bool, message: str). Writes <stem>_<lang>.json in subs/.
    """
    if not video_path or not os.path.exists(video_path):
        return False, "Clip not found."
    if not target_lang or target_lang.strip() == "":
        return False, "Target language is required (e.g. en, ar, fr)."

    src = find_subs_for_clip(project_path, video_path)
    if not src:
        return False, "No subtitle file for this clip."
    lang = target_lang.strip().lower().split("-")[0]
    dst = os.path.join(project_path, "subs",
                       "{}_translated_{}.json".format(
                           os.path.splitext(os.path.basename(src))[0], lang))
    try:
        from scripts.translate_json import translate_json_file
    except Exception as e:
        return False, ("Translation unavailable — install deps first: "
                       "pip install deep-translator tqdm ({})".format(e))
    try:
        data = asyncio.run(translate_json_file(src, dst, lang))
        count = len(data.get("segments", []))
        return True, "Copied: {} (translation for {})".format(
            os.path.basename(dst), lang) + " — {} segments".format(count)
    except Exception as e:
        return False, "Translation failed: {}".format(str(e)[:300])


def clip_subtitle_preview(project_path, video_path):
    """First lines of the clip's subtitle text for the UI preview."""
    src = find_subs_for_clip(project_path, video_path)
    if not src:
        return ""
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
        texts = [s.get("text", "") for s in data.get("segments", []) if s.get("text")]
        return " | ".join(texts[:8])
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Music check
# ---------------------------------------------------------------------------

def run_music_check(project_path, local_db_path=""):
    """Run the Chromaprint check on the project. Returns a readable report."""
    try:
        from scripts import music_fingerprint as mf
    except Exception as e:
        return "Music fingerprint module unavailable: {}".format(e)

    local_db = None
    if local_db_path and os.path.isdir(local_db_path):
        cache = os.path.join(os.path.expanduser("~"), ".viralcutter", "music_db.json")
        try:
            local_db = mf.build_local_db(local_db_path, cache_path=cache)
        except Exception as e:
            return "Local DB build failed: {}".format(e)
    elif local_db_path:
        local_db = mf.load_local_db(local_db_path)

    try:
        report = mf.analyze_project(project_path, local_db=local_db, gate="warn")
    except Exception as e:
        return "Music check failed: {}".format(e)

    s = report["summary"]
    lines = ["Music check: {} clips checked, {} matched.".format(
        s.get("checked", 0), s.get("matched", 0))]
    if s.get("no_fpcalc"):
        lines.append("⚠️ {} clips: Chromaprint not installed (see docs).".format(
            s["no_fpcalc"]))
    for clip in report.get("clips", []):
        verdict = clip.get("verdict", "?")
        mark = {"clean": "✅", "acoustid_match": "🎵⚠️", "local_match": "🎵⚠️",
                "no_fpcalc": "⚠️", "error": "❌"}.get(verdict, "?")
        lines.append("  {} #{} {} — {}".format(
            mark, clip.get("index", "?"),
            os.path.basename(clip.get("video", "")), verdict))
        if clip.get("suggestion"):
            lines.append("      ↳ {}".format(clip["suggestion"]))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Upload through the safety gate (streaming)
# ---------------------------------------------------------------------------

def _upload_worker(project_path, platform, video_path, title, caption,
                   hashtags, dry_run, music_gate, out_queue):
    def emit(msg):
        out_queue.put(str(msg))

    try:
        from scripts import upload_gate as ug
        emit("[gate] running safety checks for #{} ...".format(clip_index(video_path)))
        uploader = ug.UPLOADERS[platform](project_path, dry_run=dry_run,
                                          music_gate=music_gate)
        result = uploader.upload(video_path, title, caption, hashtags,
                                 index=clip_index(video_path))
        emit("✅ {}".format(json.dumps(result, ensure_ascii=False)))
    except Exception as e:
        emit("❌ {}".format(e))
    finally:
        out_queue.put("__DONE__")


def stream_upload(project_path, platform, video_path, title, caption,
                  hashtags, dry_run, music_gate):
    """Generator for Gradio: runs the gated upload and yields log lines."""
    out_queue = queue.Queue()
    if not video_path or not os.path.exists(video_path):
        yield "Clip not found."
        return
    thread = threading.Thread(
        target=_upload_worker,
        args=(project_path, platform, video_path, title, caption, hashtags,
              dry_run, music_gate, out_queue),
        daemon=True)
    thread.start()

    lines = []
    while True:
        try:
            msg = out_queue.get(timeout=0.5)
        except queue.Empty:
            if not thread.is_alive():
                break
            yield "\n".join(lines)
            continue
        if msg == "__DONE__":
            break
        lines.append(msg)
        yield "\n".join(lines)
    lines.append("Upload finished.")
    yield "\n".join(lines)
