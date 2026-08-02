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
