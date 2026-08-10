# -*- coding: utf-8 -*-
"""
Polish — one-command professional editing pass over the `final/` folder.

Runs the Sprint-3 enhancement chain on every rendered clip:

    jump cuts (silence/filler removal)  → punch-in zoom → background music
    (auto-duck) → watermark → intro/outro

Output goes to `final_polished/` (burn_subtitles now prefers that folder).
Every stage is independently optional and safe: a missing asset (music,
logo, intro/outro) only skips that stage, never the clip.
"""

import glob
import json
import os
import subprocess
import sys

from scripts import background_music, branding, jump_cuts, punch_zoom

STAGE_ORDER = ["jump_cuts", "punch_zoom", "background_music", "branding"]


def _video_files(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(
        f for f in glob.glob(os.path.join(folder, "*.mp4"))
        if "temp_video_no_audio" not in os.path.basename(f))


def _subs_json_for(final_dir, video_file, subs_dir):
    """Map a final/*.mp4 to its subs/*_processed.json (word timings)."""
    name = os.path.splitext(os.path.basename(video_file))[0]
    candidates = [
        os.path.join(subs_dir, name + "_processed.json"),
        os.path.join(subs_dir, name + ".json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _probe_duration(path):
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30)
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def retime_subs(subs_json_path, cuts, intro_duration=0.0):
    """Re-time word/segment timings after jump cuts + intro prepend.

    Keeps burned subtitles in sync with the polished video:
      new_t = (t − removed_before(t)) + intro_duration
    Words/segments fully removed by a cut are dropped.
    Overwrites the file in place (called BEFORE adjust_subtitles).
    """
    if not subs_json_path or not os.path.exists(subs_json_path):
        return None
    try:
        with open(subs_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    cuts = [(float(s), float(e)) for s, e in (cuts or []) if e > s]

    def removed_before(t):
        return sum(e - s for s, e in cuts if e <= t)

    def fully_cut(ws, we):
        return any(s <= ws and we <= e for s, e in cuts)

    new_segments = []
    for seg in data.get("segments", []):
        try:
            s0, e0 = float(seg["start"]), float(seg["end"])
        except Exception:
            continue
        if fully_cut(s0, e0):
            continue
        ns = s0 - removed_before(s0) + intro_duration
        ne = e0 - removed_before(e0) + intro_duration
        if ne <= ns:
            continue
        out_seg = dict(seg)
        out_seg["start"], out_seg["end"] = ns, ne
        words = seg.get("words")
        if words:
            kept = []
            for w in words:
                try:
                    ws, we = float(w["start"]), float(w["end"])
                except Exception:
                    continue
                if fully_cut(ws, we):
                    continue
                nws = ws - removed_before(ws) + intro_duration
                nwe = we - removed_before(we) + intro_duration
                if nwe > nws:
                    nw = dict(w)
                    nw["start"], nw["end"] = nws, nwe
                    kept.append(nw)
            if kept:
                out_seg["words"] = kept
        new_segments.append(out_seg)

    data["segments"] = new_segments
    try:
        with open(subs_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        return None
    return data


def polish_project(project_folder, enable=None, keywords=None,
                   music_path=None, logo_path=None, intro=None, outro=None,
                   music_volume=0.15, punch_zoom_amount=1.18,
                   punch_auto_interval=0.0, zoom_keywords=None,
                   watermark_position="bottom-right", watermark_size=0.12,
                   watermark_opacity=0.9, verbose=True):
    """Run the enhancement chain on every clip in final/ → final_polished/.

    `enable` is a set/list of stages from STAGE_ORDER; None = all.
    Returns a list of per-clip reports.
    """
    enable = set(enable or STAGE_ORDER)
    final_dir = os.path.join(project_folder, "final")
    subs_dir = os.path.join(project_folder, "subs")
    out_dir = os.path.join(project_folder, "final_polished")
    os.makedirs(out_dir, exist_ok=True)

    files = _video_files(final_dir)
    reports = []
    for video_file in files:
        base = os.path.basename(video_file)
        tmp_dir = os.path.join(project_folder, ".polish_tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        current = video_file
        subs_json = _subs_json_for(final_dir, video_file, subs_dir)
        applied_cuts = []
        intro_duration = 0.0
        stage_report = {"video": base, "stages": {}}
        try:
            # 1. jump cuts
            if "jump_cuts" in enable:
                next_work = os.path.join(tmp_dir, "jc_" + base)
                rep = jump_cuts.process_file(current, subs_json=subs_json, out_path=next_work)
                stage_report["stages"]["jump_cuts"] = {
                    "cuts": len(rep.get("cuts", [])), "removed": rep.get("removed", 0.0)}
                if rep.get("ok"):
                    applied_cuts = rep.get("cuts", [])
                    current = next_work
            # 2. punch zoom
            if "punch_zoom" in enable:
                subs = _subs_json_for(final_dir, video_file, subs_dir)
                next_work = os.path.join(tmp_dir, "pz_" + base)
                rep = punch_zoom.process_file(
                    current, subs_json=subs, out_path=next_work,
                    keywords=zoom_keywords, zoom=punch_zoom_amount,
                    auto_interval=punch_auto_interval)
                stage_report["stages"]["punch_zoom"] = {"punches": rep.get("count", 0)}
                if rep.get("ok"):
                    current = next_work
            # 3. background music
            if "background_music" in enable:
                music = background_music.find_music_file(music_path, project_folder)
                next_work = os.path.join(tmp_dir, "bm_" + base)
                rep = background_music.apply_background_music(
                    current, music, next_work, music_volume=music_volume)
                stage_report["stages"]["background_music"] = {
                    "music": rep.get("music"),
                    "skipped": rep.get("skipped")}
                if rep.get("ok"):
                    current = next_work
            # 4. branding
            if "branding" in enable:
                if intro and os.path.exists(intro):
                    intro_duration = _probe_duration(intro)
                next_work = os.path.join(tmp_dir, "br_" + base)
                rep = branding.process_file(
                    current, out_path=next_work, logo_path=logo_path,
                    position=watermark_position, size_fraction=watermark_size,
                    opacity=watermark_opacity, intro=intro, outro=outro)
                stage_report["stages"]["branding"] = {
                    "watermark": rep.get("watermark"), "intro_outro": rep.get("intro_outro")}
                if rep.get("ok"):
                    current = next_work

            # re-time subtitles for the final polished video (jump cuts + intro)
            if subs_json and (applied_cuts or intro_duration):
                retime_subs(subs_json, applied_cuts, intro_duration)
                stage_report["retimed_subs"] = True

            os.replace(current, os.path.join(out_dir, base))
            stage_report["ok"] = True
        except Exception as e:
            stage_report["ok"] = False
            stage_report["error"] = str(e)
            import shutil
            shutil.copy2(video_file, os.path.join(out_dir, base))
        finally:
            for leftover in glob.glob(os.path.join(tmp_dir, "*")):
                try:
                    os.remove(leftover)
                except Exception:
                    pass
        if verbose:
            print(json.dumps(stage_report, ensure_ascii=False))
        reports.append(stage_report)

    # remove empty temp dir
    try:
        os.rmdir(tmp_dir)
    except Exception:
        pass
    return reports


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ViralCutter polish pass (Sprint 3).")
    parser.add_argument("--project", required=True, help="project folder")
    parser.add_argument("--stages", default=",".join(STAGE_ORDER),
                        help="comma-separated stages: " + ",".join(STAGE_ORDER))
    parser.add_argument("--keywords", default=None,
                        help="punch-zoom keywords (comma-separated)")
    parser.add_argument("--music", default=None, help="music file path")
    parser.add_argument("--music-volume", type=float, default=0.15)
    parser.add_argument("--logo", default=None, help="channel logo PNG")
    parser.add_argument("--intro", default=None)
    parser.add_argument("--outro", default=None)
    parser.add_argument("--zoom", type=float, default=1.18)
    parser.add_argument("--zoom-interval", type=float, default=0.0,
                        help="auto punch every N seconds")
    parser.add_argument("--watermark-position", default="bottom-right")
    args = parser.parse_args()

    reports = polish_project(
        args.project,
        enable=[s for s in args.stages.split(",") if s.strip()],
        keywords=args.keywords,
        music_path=args.music,
        music_volume=args.music_volume,
        logo_path=args.logo,
        intro=args.intro,
        outro=args.outro,
        punch_zoom_amount=args.zoom,
        punch_auto_interval=args.zoom_interval,
        zoom_keywords=args.keywords,
        watermark_position=args.watermark_position,
    )
    ok = sum(1 for r in reports if r.get("ok"))
    print("polish: {}/{} clips ok".format(ok, len(reports)))
    return 0 if ok == len(reports) and reports else 1


if __name__ == "__main__":
    sys.exit(main())
