"""Review & select AI-suggested viral segments before rendering.

Pure logic (no gradio imports) so it stays unit-testable:
- load segments from a project's viral_segments.txt
- convert to table rows for the UI
- apply a selection: keep only chosen segments, back up the original file,
  and invalidate stale cuts so the next render reflects the new selection.
"""
import json
import os
import shutil
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from i18n.i18n import DEFAULT_LANGUAGE, I18nAuto

i18n = I18nAuto(DEFAULT_LANGUAGE)

SEGMENTS_FILENAME = "viral_segments.txt"
BACKUP_FILENAME = "viral_segments.full_backup.json"
SAFETY_REPORT_FILENAME = "safety_report.json"

# Table columns: checkbox, title, score, start, end, duration, reason, caption, safety
HEADERS = ["✓", i18n("Title"), i18n("Rating"), i18n("Start"), i18n("End"), i18n("Duration (s)"), i18n("Why Viral?"), i18n("Publish Caption"), i18n("Safety")]


def segments_file_path(project_path):
    return os.path.join(project_path, SEGMENTS_FILENAME)


def backup_file_path(project_path):
    return os.path.join(project_path, BACKUP_FILENAME)


def load_segments(project_path):
    """Return the segments list from a project, or [] if none/invalid."""
    path = segments_file_path(project_path)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        segments = data.get("segments", [])
        return segments if isinstance(segments, list) else []
    except Exception:
        return []


def _fmt_time(seconds):
    try:
        seconds = float(seconds)
    except Exception:
        return str(seconds)
    m, s = divmod(int(round(seconds)), 60)
    return f"{m:02d}:{s:02d}"


def load_safety_map(project_path):
    """Read safety_report.json → {(title, start_time): status} for the table."""
    path = os.path.join(project_path, SAFETY_REPORT_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = {}
        for entry in data.get("segments", []):
            key = (entry.get("title", ""), entry.get("start_time"))
            result[key] = entry.get("status", "safe")
        for entry in data.get("ai_review", []):
            key = (entry.get("title", ""), entry.get("start_time"))
            result[key] = entry.get("status", "ai_flagged")
        return result
    except Exception:
        return {}


def _safety_badge(seg, safety_map):
    status = None
    annotation = seg.get("safety") or {}
    if annotation.get("ai_flagged"):
        status = "ai_flagged"
    elif annotation.get("flagged"):
        status = annotation.get("action", "flagged")
    if not status and safety_map:
        status = safety_map.get((seg.get("title", ""), seg.get("start_time")))
    return {
        "safe": "✅",
        "flagged": "⚠️",
        "blocked": "⛔",
        "censor": "🔇 " + i18n("Muted"),
        "ai_flagged": "🤖⚠️",
        "ai_blocked": "🤖⛔",
    }.get(status or "safe", "✅")


def rows_from_segments(segments, safety_map=None):
    """Build Dataframe rows: [selected, title, score, start, end, duration, reason, caption, safety]."""
    rows = []
    for seg in segments:
        start = seg.get("start_time", seg.get("start", 0))
        end = seg.get("end_time", seg.get("end", 0))
        try:
            duration = round(float(end) - float(start), 1)
        except Exception:
            duration = seg.get("duration", "")
        rows.append([
            True,
            seg.get("title", seg.get("hook", "")),
            seg.get("score", 0),
            _fmt_time(start),
            _fmt_time(end),
            duration,
            seg.get("reasoning", ""),
            seg.get("caption", ""),
            _safety_badge(seg, safety_map or {}),
        ])
    return rows


def _rows_to_bool_list(rows):
    """Normalize a Gradio Dataframe value (pandas or list) to a bool list."""
    if rows is None:
        return []
    # pandas DataFrame (gradio default) — avoid importing pandas
    if hasattr(rows, "iloc"):
        return [bool(x) for x in rows.iloc[:, 0].tolist()]
    return [bool(r[0]) for r in rows]


def apply_selection(project_path, rows):
    """Keep only selected segments. Returns (kept, total, cuts_invalidated)."""
    segments = load_segments(project_path)
    if not segments:
        return 0, 0, False

    selected = _rows_to_bool_list(rows)
    # If the table has fewer rows than segments, default the rest to selected
    if len(selected) < len(segments):
        selected += [True] * (len(segments) - len(selected))

    kept_segments = [s for s, keep in zip(segments, selected) if keep]
    if not kept_segments:
        kept_segments = segments  # never write an empty selection
        selected = [True] * len(segments)

    changed = len(kept_segments) != len(segments)

    seg_path = segments_file_path(project_path)
    bak_path = backup_file_path(project_path)
    if changed and not os.path.exists(bak_path):
        shutil.copy2(seg_path, bak_path)

    with open(seg_path, "w", encoding="utf-8") as f:
        json.dump({"segments": kept_segments}, f, ensure_ascii=False, indent=4)

    # Invalidate stale cuts so the next render respects the new selection
    cuts_invalidated = False
    if changed:
        cuts_dir = os.path.join(project_path, "cuts")
        if os.path.isdir(cuts_dir):
            shutil.rmtree(cuts_dir, ignore_errors=True)
            cuts_invalidated = True

    return len(kept_segments), len(segments), cuts_invalidated


def restore_all(project_path):
    """Restore the original full segments file from backup."""
    bak_path = backup_file_path(project_path)
    seg_path = segments_file_path(project_path)
    if not os.path.exists(bak_path):
        return False
    shutil.copy2(bak_path, seg_path)
    return True


def export_publish_metadata(project_path):
    """Write publish_metadata.txt: per segment title + caption + hashtags.

    Returns (path, text) or (None, "") when there are no segments.
    """
    segments = load_segments(project_path)
    if not segments:
        return None, ""

    lines = []
    for i, seg in enumerate(segments, 1):
        title = seg.get("title", "") or f"Segment {i}"
        caption = seg.get("caption", "")
        hashtags = seg.get("hashtags", []) or []
        if isinstance(hashtags, str):
            hashtags = [hashtags]
        tags = " ".join("#" + str(h).lstrip("#") for h in hashtags if str(h).strip())

        lines.append(f"━━━ {i}. {title} ━━━")
        if caption:
            lines.append(caption)
        if tags:
            lines.append(tags)
        lines.append("")

    text = "\n".join(lines).strip() + "\n"
    path = os.path.join(project_path, "publish_metadata.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path, text
