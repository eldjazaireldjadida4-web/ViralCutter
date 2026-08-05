# -*- coding: utf-8 -*-
"""
Risk Scorecard — per-clip YouTube compliance report.

Turns every cut clip into a mini trust-and-safety report card so nothing
risky gets published silently:

    hate_speech : the text layers (keyword filter + AI review) verdicts
    visual      : frame-level red flags (letterboxed/pillarboxed look,
                  optional local ONNX nudity model if installed)
    reuse       : how similar the final clip still is to the raw source
                  window — the "reused content" (Content ID / monetization)
                  risk. This is THE big one for channels that cut videos.
    monetization: advertiser-friendliness (profanity inside the first 7s
                  = limited ads, even without a strike)

``compute_transformation_score`` compares frames of the final clip against
frames of the matching source window using a tiny perceptual hash (dHash).
No extra Python dependencies: ffmpeg scales to 9x8 grayscale and we read
raw bytes from a pipe.
"""

import glob
import json
import os
import subprocess

from scripts.safety_filter import find_matches, normalize_text
from scripts import visual_check

SCORECARD_FILENAME = "risk_scorecard.json"
PUBLISH_BLOCKLIST_FILENAME = "publish_blocklist.json"
FIRST_SECONDS_PROFANITY = 7.0

# reuse score >= this → the clip is effectively a repost of the source
HIGH_REUSE_THRESHOLD = 70.0


# ---------------------------------------------------------------------------
# ffmpeg frame helpers (pure stdlib)
# ---------------------------------------------------------------------------

def _grab_gray_frame(video_path, at_seconds, width=9, height=8):
    """Sample one grayscale frame (width*height bytes) via ffmpeg rawvideo pipe."""
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", "{:.3f}".format(at_seconds), "-i", video_path,
        "-frames:v", "1", "-vf", "scale={}:{},format=gray".format(width, height),
        "-f", "rawvideo", "pipe:1",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=60)
        raw = res.stdout
        if len(raw) < width * height:
            return None
        return raw[:width * height]
    except Exception:
        return None


def _dhash(frame, width=9, height=8):
    """Perceptual hash: 64-bit int from adjacent-pixel brightness."""
    h = 0
    for row in range(height):
        for col in range(width - 1):
            left = frame[row * width + col]
            right = frame[row * width + col + 1]
            h = (h << 1) | (1 if left > right else 0)
    return h


def _hamming(a, b):
    return bin(a ^ b).count("1")


def frame_similarity(video_a, video_b, sample_points):
    """Average similarity (0..100) between two videos at given relative points."""
    if not sample_points:
        return None
    hashes = []
    for frac in sample_points:
        ha = _grab_gray_frame(video_a, frac)
        hb = _grab_gray_frame(video_b, frac)
        if ha is None or hb is None:
            continue
        hashes.append(1.0 - _hamming(_dhash(ha), _dhash(hb)) / 64.0)
    if not hashes:
        return None
    return round(100.0 * sum(hashes) / len(hashes), 1)


def _letterbox_ratio(video_path, at_seconds):
    """Detect letterbox/pillarbox black bars on a frame (repurposed look).

    Returns a fraction of the frame that is dead black bars (0..1).
    """
    frame = _grab_gray_frame(video_path, at_seconds, width=64, height=36)
    if frame is None:
        return 0.0
    w, h = 64, 36

    def row_mean(r):
        row = frame[r * w:(r + 1) * w]
        return sum(row) / len(row)

    def col_mean(c):
        return sum(frame[r * w + c] for r in range(h)) / h

    top = sum(row_mean(r) for r in range(3)) / 3
    bottom = sum(row_mean(r) for r in range(h - 3, h)) / 3
    mid = sum(row_mean(r) for r in range(h // 2 - 2, h // 2 + 2)) / 4

    dark = lambda v: v < 20.0

    bars = 0.0
    if mid > 35.0 and dark(top) and dark(bottom):
        bars += 0.35
    left = sum(col_mean(c) for c in range(3)) / 3
    right = sum(col_mean(c) for c in range(w - 3, w)) / 3
    mid_col = sum(col_mean(c) for c in range(w // 2 - 2, w // 2 + 2)) / 4
    if mid_col > 35.0 and dark(left) and dark(right):
        bars += 0.35
    return round(bars, 2)


# ---------------------------------------------------------------------------
# Text signals
# ---------------------------------------------------------------------------

def profanity_in_first_seconds(segment, words, seconds=FIRST_SECONDS_PROFANITY):
    """Any policy-violating word inside the first N seconds of the clip?

    Returns (any_offense, profanity_only_list) where profanity_only_list are
    the matched terms with category in {profanity, harassment} (the ones that
    mainly hurt ad revenue rather than causing strikes).
    """
    seg_start = float(segment.get("start_time", 0) or 0)
    window_end = seg_start + seconds
    in_window = []
    for w in words:
        try:
            ws, we = float(w["start"]), float(w["end"])
        except Exception:
            continue
        if ws >= seg_start - 0.05 and ws <= window_end:
            in_window.append(w["word"])
        elif ws > window_end:
            break
    if not in_window:
        return False, []

    text = " ".join(in_window)
    matches = find_matches(text, min_severity="low")
    if not matches:
        return False, []
    profanity = [m for m in matches if m["category"] in ("profanity", "harassment")]
    return True, profanity


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------

def _find_source_video(project_folder):
    for name in ("input.mp4", "input_video.mp4"):
        p = os.path.join(project_folder, name)
        if os.path.exists(p):
            return p
    return None


def _find_clip_video(project_folder, index):
    """Prefer the final edited video, fall back to the raw cut."""
    final = sorted(glob.glob(os.path.join(
        project_folder, "final", "*{0:03d}*.mp4".format(index)))) + sorted(
        glob.glob(os.path.join(project_folder, "final",
                               "final-output{0:03d}_processed.mp4".format(index))))
    if final:
        return final[0]
    cuts = sorted(glob.glob(os.path.join(
        project_folder, "cuts", "{0:03d}_*_original_scale.mp4".format(index))))
    return cuts[0] if cuts else None


def _load_words(project_folder):
    path = os.path.join(project_folder, "input.json")
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []) or []:
            try:
                words.append({"word": str(w.get("word", "")),
                              "start": float(w.get("start", 0)),
                              "end": float(w.get("end", 0))})
            except Exception:
                continue
    words.sort(key=lambda w: w["start"])
    return words


def score_segment(segment, index, project_folder, words, source_video,
                  visual_model_path=None, visual_classifier=None):
    """Compute the risk axes for one segment. Returns a dict (never raises)."""
    entry = {
        "index": index,
        "title": segment.get("title", f"Segment_{index}"),
        "start_time": segment.get("start_time"),
        "end_time": segment.get("end_time"),
        "axes": {},
        "overall": "unknown",
        "overall_score": 0,
    }
    seg_start = float(segment.get("start_time", 0) or 0)
    seg_end = float(segment.get("end_time", seg_start) or seg_start)
    duration = max(0.0, seg_end - seg_start)

    # --- text axis (recap of keyword layer + first-N-seconds monetization) ---
    text_scores = {"hate_speech": 0, "first7s": 0, "first7_profanity": 0}
    any_off, profanity = profanity_in_first_seconds(segment, words)
    if any_off:
        text_scores["first7s"] = 60 if profanity else 80
    if profanity:
        text_scores["first7_profanity"] = 50
        text_scores["first7s"] = max(text_scores["first7s"], 50)
    entry["axes"]["text"] = text_scores

    # --- reuse / transformation axis (the Content ID + reused-content risk) ---
    reuse = {"similarity": None, "letterboxed": 0.0, "score": 0}
    clip = _find_clip_video(project_folder, index)
    if clip and source_video and os.path.exists(clip):
        points = [0.15, 0.5, 0.85]
        sim = frame_similarity(clip, source_video,
                               [seg_start + (seg_end - seg_start) * f for f in points])
        if sim is not None:
            reuse["similarity"] = sim
            reuse["letterboxed"] = _letterbox_ratio(clip, 0.5 * duration)
            score = 0.75 * sim + 15.0 * reuse["letterboxed"]
            if duration > 60:
                score += 10  # long raw excerpts are riskier
            reuse["score"] = round(min(100.0, score), 1)
    entry["axes"]["reuse"] = reuse

    # --- visual axis (graphic content; optional local ONNX classifier) ---
    visual = {"letterboxed": reuse["letterboxed"], "model": None, "score": 0}
    if visual_model_path and os.path.exists(visual_model_path):
        visual["model"] = os.path.basename(visual_model_path)
    # Real ONNX inference (NudeNet-lite style) — Roadmap 2.1. Runs only when a
    # classifier object is available so a missing model is a silent no-op.
    if visual_classifier is not None and visual_classifier.available and clip and os.path.exists(clip):
        vreport = visual_classifier.analyze_video(clip, num_frames=4)
        if vreport.get("graphic_score") is not None:
            visual["score"] = round(vreport["graphic_score"], 1)
            visual["graphic"] = vreport["graphic"]
            visual["top_class"] = vreport["top_class"]
            visual["frames"] = vreport["frames"]
            visual["model"] = vreport["model"] or visual["model"]
            if visual["score"] >= 70.0:
                visual["flag"] = "graphic content ({}% probability)".format(visual["score"])
    entry["axes"]["visual"] = visual

    # --- overall ---
    scores = [text_scores["first7s"], reuse["score"], visual["score"]]
    overall = max(scores)
    entry["overall_score"] = round(overall, 1)
    entry["overall"] = ("danger" if overall >= 85 else
                        "high" if overall >= 70 else
                        "medium" if overall >= 40 else "low")
    return entry


def analyze_project(project_folder, viral_segments=None, gate_threshold=HIGH_REUSE_THRESHOLD,
                    visual_model_path=None, auto_download_visual=False, i18n=lambda k: k):
    """Score every segment, persist risk_scorecard.json + publish_blocklist.json.

    Returns {"segments": [...], "blocked": [...], "summary": {...}}.
    """
    if viral_segments is None:
        path = os.path.join(project_folder, "viral_segments.txt")
        if not os.path.exists(path):
            return {"segments": [], "blocked": [], "summary": {}}
        with open(path, "r", encoding="utf-8") as f:
            viral_segments = json.load(f)

    # Real visual classifier (Roadmap 2.1): explicit path > default models dir.
    classifier = None
    model_path = visual_model_path
    if not model_path or not os.path.exists(model_path):
        default = visual_check.default_model_path()
        if os.path.exists(default):
            model_path = default
    if auto_download_visual and (not model_path or not os.path.exists(model_path)):
        try:
            model_path = visual_check.download_model()
        except Exception as e:
            print("[risk] visual model download skipped: {}".format(e))
    if model_path and os.path.exists(model_path):
        classifier = visual_check.NudeNetClassifier(model_path)
        if not classifier.available:
            print("[risk] visual classifier unavailable ({}); continuing text-only".format(
                classifier.error))

    segments = (viral_segments or {}).get("segments", [])
    source_video = _find_source_video(project_folder)
    words = _load_words(project_folder)

    entries = []
    for i, seg in enumerate(segments):
        entries.append(score_segment(seg, i, project_folder, words,
                                     source_video, visual_model_path=model_path,
                                     visual_classifier=classifier))

    blocked = [e for e in entries if
               e["axes"]["reuse"].get("score", 0) >= gate_threshold
               or e["overall"] in ("high", "danger")]

    summary = {
        "total": len(entries),
        "low": sum(1 for e in entries if e["overall"] == "low"),
        "medium": sum(1 for e in entries if e["overall"] == "medium"),
        "high": sum(1 for e in entries if e["overall"] == "high"),
        "danger": sum(1 for e in entries if e["overall"] == "danger"),
        "blocked_for_publish": len(blocked),
        "gate_threshold": gate_threshold,
        "visual_model": os.path.basename(model_path) if model_path and os.path.exists(model_path) else None,
    }

    report = {"summary": summary, "segments": entries, "blocked": blocked}
    try:
        with open(os.path.join(project_folder, SCORECARD_FILENAME), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[risk] could not save scorecard: {e}")

    if blocked:
        try:
            with open(os.path.join(project_folder, PUBLISH_BLOCKLIST_FILENAME), "w", encoding="utf-8") as f:
                json.dump({"blocked": blocked}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # console summary
    print(i18n("[risk] Scorecard: {} total — {} low / {} medium / {} high / {} danger — {} blocked for publish").format(
        summary["total"], summary["low"], summary["medium"], summary["high"],
        summary["danger"], summary["blocked_for_publish"]))
    for e in entries:
        reuse = e["axes"]["reuse"].get("score")
        reuse_s = "{:.0f}".format(reuse) if reuse is not None else "n/a"
        print(i18n("[risk]   {} '{}': overall={} reuse={} first7s={}").format(
            "⛔" if e in blocked else "  ",
            e["title"], e["overall"], reuse_s, e["axes"]["text"]["first7s"]))
        if e in blocked:
            print(i18n("[risk]       → DO NOT PUBLISH: {}").format(
                "clip is still ~{:.0f}% identical to the source (reused content risk)".format(e["axes"]["reuse"]["score"])
                if e["axes"]["reuse"].get("score") and e["axes"]["reuse"]["score"] >= gate_threshold
                else "high overall risk"))
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Per-clip YouTube risk scorecard.")
    parser.add_argument("--project", required=True, help="Project folder")
    parser.add_argument("--gate-threshold", type=float, default=HIGH_REUSE_THRESHOLD)
    parser.add_argument("--visual-model", default=None,
                        help="Path to an optional local ONNX visual classifier (e.g. models/nudenet_lite.onnx)")
    parser.add_argument("--auto-download-visual", action="store_true",
                        help="Download the default small visual classifier into models/ if missing")
    parser.add_argument("--exit-on-blocked", action="store_true",
                        help="Exit code 1 if any clip is blocked for publish")
    args = parser.parse_args()

    report = analyze_project(args.project, gate_threshold=args.gate_threshold,
                             visual_model_path=args.visual_model,
                             auto_download_visual=args.auto_download_visual)
    blocked = len(report.get("blocked", []))
    if args.exit_on_blocked and blocked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
