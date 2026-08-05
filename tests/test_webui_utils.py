"""Tests for the extracted WebUI helper utilities (webui/utils.py)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webui.utils import (
    PROGRESS_STAGES,
    build_subtitle_config,
    convert_color_to_ass,
    empty_progress_state,
    normalize_path,
    safe_float,
    safe_int,
)


@pytest.mark.parametrize(
    "color,expected",
    [
        ("#FF0000", "&H000000FF&"),  # red -> BGR
        ("#00FF00", "&H0000FF00&"),
        ("#0000FF", "&H00FF0000&"),
        ("#FFFFFF", "&H00FFFFFF&"),
        ("#0F0", "&H0000FF00&"),     # 3-digit hex expands
        ("rgb(255, 0, 0)", "&H000000FF&"),
        ("", "&H00FFFFFF&"),         # empty -> white fallback
        ("garbage", "&H00FFFFFF&"),  # invalid -> white fallback
        (None, "&H00FFFFFF&"),
    ],
)
def test_convert_color_to_ass(color, expected):
    assert convert_color_to_ass(color) == expected


def test_convert_color_to_ass_alpha():
    assert convert_color_to_ass("#FF0000", alpha="7F") == "&H7F0000FF&"


@pytest.mark.parametrize(
    "value,default,expected",
    [("5", 0, 5), (5, 0, 5), (4.7, 0, 4), ("abc", 3, 3), (None, 7, 7), ("", 1, 1)],
)
def test_safe_int(value, default, expected):
    assert safe_int(value, default) == expected


@pytest.mark.parametrize(
    "value,default,expected",
    [("1.5", 0.0, 1.5), (2, 0.0, 2.0), ("x", 2.5, 2.5), (None, 0.25, 0.25)],
)
def test_safe_float(value, default, expected):
    assert safe_float(value, default) == expected


def test_normalize_path_passthrough_falsy():
    assert normalize_path("") == ""
    assert normalize_path(None) is None


def test_normalize_path_normalizes():
    assert normalize_path("a/b/") == os.path.normpath("a/b/")


def test_empty_progress_state_structure():
    state = empty_progress_state("starting")
    for stage in PROGRESS_STAGES:
        assert state[stage] == {"percent": 0, "message": state[stage]["message"]}
        assert state[stage]["percent"] == 0
    assert state["overall"] == 0
    assert state["current"] == "starting"


def test_build_subtitle_config():
    cfg = build_subtitle_config(
        font_name="Arial", font_size="20", font_color="#FF0000",
        highlight_color="#00FF00", outline_color="#000000",
        outline_thickness="2.5", shadow_color="#111111", shadow_size="3",
        is_bold=True, is_italic=False, is_uppercase=True, vertical_pos="200",
        alignment="2", h_size="16", w_block="4", gap="0.7", mode="word",
        under=False, strike=False, border_s="1", remove_punc=True,
    )
    assert cfg["font"] == "Arial"
    assert cfg["base_size"] == 20
    assert cfg["base_color"] == "&H000000FF&"
    assert cfg["highlight_color"] == "&H0000FF00&"
    assert cfg["outline_thickness"] == 2.5
    assert cfg["bold"] == 1
    assert cfg["italic"] == 0
    assert cfg["uppercase"] == 1
    assert cfg["words_per_block"] == 4
    assert cfg["remove_punctuation"] is True


def test_build_subtitle_config_defaults_on_bad_input():
    cfg = build_subtitle_config(
        font_name="Arial", font_size="bad", font_color="zzz",
        highlight_color="", outline_color=None,
        outline_thickness="bad", shadow_color=None, shadow_size=None,
        is_bold=False, is_italic=False, is_uppercase=False, vertical_pos=None,
        alignment=None, h_size=None, w_block=None, gap=None, mode="block",
        under=False, strike=False, border_s=None, remove_punc=False,
    )
    assert cfg["base_size"] == 12
    assert cfg["base_color"] == "&H00FFFFFF&"
    assert cfg["outline_thickness"] == 1.5
    assert cfg["vertical_position"] == 210
    assert cfg["remove_punctuation"] is False


# --- v6 flags (Roadmap 5.2 / Sprint 3 / 4.2 / 2.4) ---

class TestV6Flags:
    def _cmd(self, **kw):
        from webui.pipeline import build_command
        return build_command("main.py", ["--url", "https://x"], segments=3, **kw)

    def test_platform_flag(self):
        cmd = self._cmd(platform="tiktok")
        assert "--platform" in cmd and cmd[cmd.index("--platform") + 1] == "tiktok"

    def test_polish_on_adds_music_and_logo(self):
        cmd = self._cmd(polish=True, music="bed.m4a", logo="logo.png")
        assert "--polish" in cmd
        assert "--music" in cmd and cmd[cmd.index("--music") + 1] == "bed.m4a"
        assert "--logo" in cmd and cmd[cmd.index("--logo") + 1] == "logo.png"

    def test_polish_default_off(self):
        cmd = self._cmd()
        assert "--polish" not in cmd

    def test_checkpoint_off_passed(self):
        cmd = self._cmd(checkpoint="off")
        assert "--checkpoint" in cmd and cmd[cmd.index("--checkpoint") + 1] == "off"

    def test_checkpoint_default_not_passed(self):
        cmd = self._cmd()
        assert "--checkpoint" not in cmd

    def test_metadata_gate_block_passed(self):
        cmd = self._cmd(metadata_gate="block")
        assert "--metadata-gate" in cmd and cmd[cmd.index("--metadata-gate") + 1] == "block"

    def test_cookies_browser_flag(self):
        cmd = self._cmd(cookies_browser="chrome")
        assert "--cookies-from-browser" in cmd
        assert cmd[cmd.index("--cookies-from-browser") + 1] == "chrome"
