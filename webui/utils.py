"""Pure helper utilities for the WebUI.

Extracted from app.py to keep the interface module focused on UI wiring.
No gradio/psutil imports here so this module stays import-light and testable.
"""
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from i18n.i18n import I18nAuto, DEFAULT_LANGUAGE

i18n = I18nAuto(DEFAULT_LANGUAGE)

PROGRESS_STAGES = ["download", "transcribe", "ai", "cut", "edit", "subtitles", "done"]


def empty_progress_state(current=None):
    current = current or i18n("Loading...")
    loading = i18n("Loading...")
    state = {k: {"percent": 0, "message": loading} for k in PROGRESS_STAGES}
    state["overall"] = 0
    state["current"] = current
    return state


def convert_color_to_ass(hex_color, alpha="00"):
    try:
        if not hex_color:
            return f"&H{alpha}FFFFFF&"
        hex_clean = hex_color.lstrip('#').strip()
        if hex_clean.lower().startswith("rgb"):
            nums = re.findall(r"[\d\.]+", hex_clean)
            if len(nums) >= 3:
                r, g, b = [max(0, min(255, int(float(n)))) for n in nums[:3]]
                return f"&H{alpha}{b:02X}{g:02X}{r:02X}&".upper()
        if len(hex_clean) == 3:
            hex_clean = ''.join(c * 2 for c in hex_clean)
        if len(hex_clean) == 6 and re.fullmatch(r"[0-9a-fA-F]{6}", hex_clean):
            r, g, b = hex_clean[0:2], hex_clean[2:4], hex_clean[4:6]
            return f"&H{alpha}{b}{g}{r}&".upper()
    except Exception:
        pass
    return f"&H{alpha}FFFFFF&"


def safe_int(value, default):
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value, default):
    try:
        return float(value)
    except Exception:
        return default


def normalize_path(path):
    if not path:
        return path
    return os.path.normpath(str(path))


def build_subtitle_config(font_name, font_size, font_color, highlight_color, outline_color, outline_thickness, shadow_color, shadow_size, is_bold, is_italic, is_uppercase, vertical_pos, alignment, h_size, w_block, gap, mode, under, strike, border_s, remove_punc):
    return {
        "font": font_name,
        "base_size": safe_int(font_size, 12),
        "base_color": convert_color_to_ass(font_color),
        "highlight_color": convert_color_to_ass(highlight_color),
        "outline_color": convert_color_to_ass(outline_color),
        "outline_thickness": safe_float(outline_thickness, 1.5),
        "shadow_color": convert_color_to_ass(shadow_color),
        "shadow_size": safe_float(shadow_size, 2),
        "vertical_position": safe_int(vertical_pos, 210),
        "alignment": safe_int(alignment, 2),
        "bold": 1 if is_bold else 0,
        "italic": 1 if is_italic else 0,
        "underline": 1 if under else 0,
        "strikeout": 1 if strike else 0,
        "border_style": safe_int(border_s, 1),
        "words_per_block": safe_int(w_block, 3),
        "gap_limit": safe_float(gap, 0.5),
        "mode": mode,
        "highlight_size": safe_int(h_size, 14),
        "uppercase": 1 if is_uppercase else 0,
        "remove_punctuation": bool(remove_punc),
    }


# ---------------------------------------------------------------------------
# Panel renderers (used by webui/app.py; were referenced but never defined —
# fixed in v6.1 so the WebUI can actually start)
# ---------------------------------------------------------------------------

def render_progress_html(state):
    """HTML progress panel: per-stage bars + overall percentage."""
    state = state or {}
    stages = state.get("stages", {}) if isinstance(state.get("stages"), dict) else state
    overall = int(state.get("overall", 0) or 0)
    current = state.get("current", "")
    rows = []
    for stage in PROGRESS_STAGES:
        info = stages.get(stage) if isinstance(stages, dict) else state.get(stage, {})
        if not isinstance(info, dict):
            info = {}
        percent = int(info.get("percent", 0) or 0)
        message = info.get("message", "") or ""
        rows.append(
            '<div style="margin:2px 0;font-size:12px;">'
            '<span style="display:inline-block;width:90px;">{}</span>'
            '<div style="display:inline-block;width:60%;height:8px;background:#eee;'
            'border-radius:4px;vertical-align:middle;">'
            '<div style="width:{}%;height:8px;background:#4caf50;border-radius:4px;"></div>'
            '</div> <b>{}</b> {}</div>'.format(
                _html_escape(stage), percent, "{}%".format(percent), _html_escape(message)))
    return (
        '<div style="font-family:monospace;padding:6px;">'
        '<div style="font-size:14px;margin-bottom:6px;">'
        '<b>{} {}</b> — {}</div>{}</div>'.format(
            i18n("Overall"), "{}%".format(overall), _html_escape(current), "".join(rows)))


def render_tasks_html(state):
    """HTML tasks panel: current stage + last few messages."""
    state = state or {}
    current = state.get("current", "")
    stages = state.get("stages", {}) if isinstance(state.get("stages"), dict) else state
    lines = ["<b>{}</b>".format(i18n("Current task")), _html_escape(current)]
    for stage in PROGRESS_STAGES:
        info = stages.get(stage) if isinstance(stages, dict) else state.get(stage, {})
        if isinstance(info, dict) and info.get("message"):
            lines.append("<i>{}</i>: {}".format(_html_escape(stage),
                                                _html_escape(str(info["message"]))))
    return "<div style='padding:6px;font-size:13px;'>{}</div>".format("<br>".join(lines[:8]))


def render_error_html(error_items):
    """HTML errors panel: red list of accumulated error messages."""
    if not error_items:
        return ""
    items = "".join(
        "<li style='color:#b00020;margin:2px 0;'>{}</li>".format(_html_escape(str(e)))
        for e in error_items)
    return "<ul style='padding-left:18px;margin:6px 0;'>{}</ul>".format(items)


def _html_escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


# ---------------------------------------------------------------------------
# Error report summarizer (v6.4) — turn raw traceback tails into scannable
# cards with a friendly hint, instead of dumping 30 raw lines.
# ---------------------------------------------------------------------------

KNOWN_ERROR_HINTS = [
    ("private video", "الفيديو خاص — استعمل كوكيز المتصفح: من قائمة 🔒 أو أعد التشغيل بـ --cookies-from-browser chrome"),
    ("sign in", "الفيديو يتطلب تسجيل دخول يوتيوب — استعمل كوكيز متصفحك من قائمة 🔒"),
    ("cookiesfrombrowser", "تعذّرت قراءة كوكيز المتصفح (تشفير Chrome) — جرّب Firefox أو ملف cookies.txt مُصدَّر"),
    ("age", "الفيديو مقيد عمرياً — استعمل كوكيز متصفحك"),
    ("video unavailable", "الفيديو غير متاح (محذوف أو محجوب جغرافياً)"),
    ("google-generativeai", "مكتبة Gemini غير مثبّتة — شغّل: pip install google-generativeai (أو أعد تشغيل install_dependencies.bat)"),
    ("google.genai", "مكتبة Gemini غير مثبّتة — شغّل: pip install google-genai (أو أعد تشغيل install_dependencies.bat)"),
    ("gemini sdk", "مكتبة Gemini غير مثبّتة — شغّل: pip install google-generativeai"),
    ("403", "يوتيوب حجب التنزيل (403) — حدّث yt-dlp: uv pip install -U yt-dlp، أو استعمل كوكيز المتصفح، أو أعد المحاولة بعد دقائق"),
    ("forbidden", "يوتيوب حجب التنزيل (403) — حدّث yt-dlp: uv pip install -U yt-dlp، أو استعمل كوكيز المتصفح، أو أعد المحاولة بعد دقائق"),
    ("np.nan", "تعارض إصدارات: numpy 2.x غير متوافق مع pyannote/whisperx — شغّل: uv pip install 'numpy<2'"),
    ("numpy 2.0", "تعارض إصدارات: numpy 2.x غير متوافق مع pyannote/whisperx — شغّل: uv pip install 'numpy<2'"),
    ("invalid model size", "نموذج Whisper غير مدعوم في نسخة faster-whisper المثبتة — حدّثها: uv pip install -U faster-whisper، أو اختر نموذجاً آخر مثل large-v3 أو medium من القائمة"),
    ("expected one of", "نموذج Whisper غير مدعوم في نسخة faster-whisper المثبتة — حدّثها: uv pip install -U faster-whisper، أو اختر نموذجاً آخر مثل large-v3 أو medium من القائمة"),
    ("whisperx", "مكوّن التفريغ الصوتي غير مثبّت — أعد تشغيل install_dependencies.bat واختر تثبيت whisperx"),
    ("torch", "مكوّن التفريغ الصوتي غير مثبّت — أعد تشغيل install_dependencies.bat واختر تثبيت whisperx"),
    ("out of memory", "نفاد الذاكرة — أغلق البرامج الأخرى أو استعمل نموذج Whisper أصغر"),
    ("ffmpeg", "FFmpeg غير مثبّت أو غير موجود في المسار — شغّل install_dependencies.bat واختر تنزيل FFmpeg"),
    ("429", "يوتيوب يحدّ الطلبات مؤقتاً (429) — انتظر دقيقة وأعد المحاولة"),
    ("connection", "مشكلة اتصال بالإنترنت أو حجب DNS"),
]


def summarize_error(text, max_title=160):
    """Turn a raw error blob into (title, detail, hint).

    title  — first meaningful line (ERROR: … if present)
    detail — full text (capped)
    hint   — friendly Arabic guidance for known problems ("" if unknown)
    """
    text = (text or "").strip()
    lines = [ln for ln in text.splitlines() if ln.strip()]
    title = lines[0] if lines else "خطأ غير معروف"
    for ln in lines:
        low = ln.lower()
        if low.startswith("error") or "error:" in low[:40]:
            title = ln
            break
    hint = ""
    # prefer matching the hint against the TITLE line first (the real error),
    # so older messages in the log tail don't hijack the hint
    low_title = title.lower()
    for key, msg in KNOWN_ERROR_HINTS:
        if key in low_title:
            hint = msg
            break
    if not hint:
        low_text = text.lower()
        for key, msg in KNOWN_ERROR_HINTS:
            if key in low_text:
                hint = msg
                break
    return title[:max_title], text[:3000], hint


def render_error_html(error_items):
    """HTML errors panel: scannable cards (title + hint + collapsible detail).

    Accepts strings (old format) or dicts {"title","detail","hint","code"}.
    """
    if not error_items:
        return ""
    cards = []
    for item in error_items:
        if isinstance(item, dict):
            title = item.get("title") or "خطأ"
            detail = item.get("detail") or ""
            hint = item.get("hint") or ""
            code = item.get("code")
        else:
            title, detail, hint = summarize_error(item)
            code = None
        badge = '<span style="background:#b00020;color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;">خطأ</span>'
        if code:
            badge = '<span style="background:#7f1d1d;color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;">رمز الخروج {}</span>'.format(code)
        hint_html = (
            '<div style="color:#7a5c00;background:#fff7e0;border:1px solid #f0dc9a;'
            'border-radius:4px;padding:4px 8px;margin-top:4px;font-size:12px;">💡 {}</div>'
            .format(_html_escape(hint))) if hint else ""
        detail_html = (
            '<details style="margin-top:4px;"><summary style="cursor:pointer;'
            'font-size:12px;color:#666;">التفاصيل التقنية</summary>'
            '<pre style="white-space:pre-wrap;background:#1e1e1e;color:#eee;'
            'border-radius:4px;padding:8px;font-size:11px;max-height:200px;'
            'overflow:auto;">{}</pre></details>'.format(_html_escape(detail))) if detail else ""
        cards.append(
            '<div style="border:1px solid #f0c4c4;background:#fff5f5;border-radius:6px;'
            'margin:6px 0;padding:6px 10px;">'
            '<div style="font-size:13px;font-weight:600;color:#b00020;">{} {}</div>'
            '{}{}</div>'.format(badge, _html_escape(title), hint_html, detail_html))
    return "<div style='font-family:sans-serif;'>" + "".join(cards) + "</div>"
