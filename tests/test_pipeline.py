"""Tests for the CLI command builder (webui/pipeline.py)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from webui.pipeline import WORKFLOW_MAP, build_command

MAIN = "/repo/main_improved.py"


def _flags(cmd):
    """Return dict of flag -> value for --flag value pairs, and set of bare flags."""
    pairs, bare = {}, set()
    i = 0
    while i < len(cmd):
        if cmd[i].startswith("--"):
            if i + 1 < len(cmd) and not cmd[i + 1].startswith("--"):
                pairs[cmd[i]] = cmd[i + 1]
                i += 2
            else:
                bare.add(cmd[i])
                i += 1
        else:
            i += 1
    return pairs, bare


def test_basic_command_url_source():
    cmd = build_command(MAIN, ["--url", "https://youtu.be/x"], face_model="insightface")
    assert cmd[1] == MAIN
    assert "--url" in cmd
    pairs, bare = _flags(cmd)
    assert pairs["--segments"] == "3"          # default
    assert pairs["--min-duration"] == "15"     # default
    assert pairs["--max-duration"] == "90"     # default
    assert pairs["--model"] == "large-v3-turbo"
    assert pairs["--ai-backend"] == "manual"   # default
    assert pairs["--workflow"] == "1"          # Full default
    assert pairs["--face-mode"] == "auto"
    assert pairs["--no-face-mode"] == "padding"
    assert "--skip-prompts" in bare


def test_workflow_mapping():
    assert WORKFLOW_MAP == {"Full": "1", "Cut Only": "2", "Subtitles Only": "3"}
    cmd = build_command(MAIN, [], workflow="Cut Only", face_model="mediapipe")
    pairs, _ = _flags(cmd)
    assert pairs["--workflow"] == "2"
    cmd = build_command(MAIN, [], workflow="unknown-thing", face_model="m")
    pairs, _ = _flags(cmd)
    assert pairs["--workflow"] == "1"  # falls back to Full


def test_optional_args_included_only_when_set():
    cmd = build_command(
        MAIN, ["--project-path", "/p"],
        api_key="secret", themes="funny,news", viral=True,
        translate_target="English", chunk_size="5000",
        face_model="insightface",
    )
    pairs, bare = _flags(cmd)
    assert pairs["--api-key"] == "secret"
    assert pairs["--themes"] == "funny,news"
    assert pairs["--translate-target"] == "English"
    assert pairs["--chunk-size"] == "5000"
    assert "--viral" in bare

    cmd2 = build_command(MAIN, [], face_model="m")
    assert "--api-key" not in cmd2
    assert "--themes" not in cmd2
    assert "--translate-target" not in cmd2
    assert "--chunk-size" not in cmd2
    assert "--viral" not in cmd2


def test_translate_target_none_is_skipped():
    cmd = build_command(MAIN, [], translate_target="None", face_model="m")
    assert "--translate-target" not in cmd


def test_active_speaker_group():
    cmd = build_command(
        MAIN, [], face_model="m",
        focus_active_speaker=True, active_speaker_mar=0.03,
        active_speaker_score_diff=1.5, include_motion=True,
        active_speaker_motion_threshold=3.0,
        active_speaker_motion_sensitivity=0.05, active_speaker_decay=2.0,
    )
    pairs, bare = _flags(cmd)
    assert "--focus-active-speaker" in bare
    assert "--include-motion" in bare
    assert pairs["--active-speaker-mar"] == "0.03"
    assert pairs["--active-speaker-decay"] == "2.0"

    # without focus, none of the group appears
    cmd2 = build_command(MAIN, [], face_model="m", include_motion=True,
                         active_speaker_mar=0.03)
    assert "--focus-active-speaker" not in cmd2
    assert "--include-motion" not in cmd2
    assert "--active-speaker-mar" not in cmd2


def test_subtitle_config_path():
    cmd = build_command(MAIN, [], face_model="m", subtitle_config_path="/tmp/sc.json")
    pairs, _ = _flags(cmd)
    assert pairs["--subtitle-config"] == "/tmp/sc.json"
    cmd2 = build_command(MAIN, [], face_model="m")
    assert "--subtitle-config" not in cmd2


def test_face_thresholds_zero_values_kept():
    """0.0 is a valid threshold and must not be dropped."""
    cmd = build_command(
        MAIN, [], face_model="m",
        face_filter_thresh=0.0, face_two_thresh=0.0,
        face_conf_thresh=0.0, face_dead_zone=0,
    )
    pairs, _ = _flags(cmd)
    assert pairs["--face-filter-threshold"] == "0.0"
    assert pairs["--face-two-threshold"] == "0.0"
    assert pairs["--face-confidence-threshold"] == "0.0"
    assert pairs["--face-dead-zone"] == "0"


def test_bad_numeric_inputs_fall_back_to_defaults():
    cmd = build_command(MAIN, [], segments="abc", min_duration=None,
                        max_duration="", chunk_size="x", face_model="m")
    pairs, _ = _flags(cmd)
    assert pairs["--segments"] == "3"
    assert pairs["--min-duration"] == "15"
    assert pairs["--max-duration"] == "90"
    assert pairs["--chunk-size"] == "70000"


class TestDownloadFriendlyErrors:
    """Friendly handling of private/age-restricted/unavailable videos (v6.2)."""

    def _import_dl(self):
        from scripts import download_video as dl
        return dl

    def test_private_video_message(self):
        dl = self._import_dl()
        msg = dl._friendly_download_error(
            "ERROR: [youtube] abc123: Private video. Sign in if you've been "
            "granted access to this video. Use --cookies-from-browser or "
            "--cookies for the authentication.")
        assert "PRIVATE" in msg
        assert "--cookies-from-browser" in msg

    def test_age_restricted_message(self):
        dl = self._import_dl()
        msg = dl._friendly_download_error(
            "ERROR: [youtube] xyz: Sign in to confirm your age")
        assert "age-restricted" in msg

    def test_unavailable_message(self):
        dl = self._import_dl()
        msg = dl._friendly_download_error(
            "ERROR: [youtube] qwe: Video unavailable. This video is not available")
        assert "unavailable" in msg

    def test_subtitle_429_returns_none(self):
        dl = self._import_dl()
        assert dl._friendly_download_error(
            "ERROR: Unable to download video subtitles (429)") is None


class TestDownloadNeverReturnsNone:
    """Regression: download() must RAISE on private videos, never return None.

    This guards against the v6.3 corruption where the main download block was
    accidentally nested inside a helper (download() returned None → crash).
    """

    def _run_private_video_sim(self, monkeypatch, tmp_path, sys_modules):
        import importlib
        import sys as _sys
        import types

        class FakeDownloadError(Exception):
            def __str__(self):
                return ("ERROR: [youtube] 2ExOHMwEDD4: Private video. Sign in if "
                        "you've been granted access to this video.")

        class FakeYDL:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, *a, **k):
                raise FakeDownloadError()

            def download(self, *a, **k):
                raise FakeDownloadError()

        fake = types.ModuleType("yt_dlp")
        fake.YoutubeDL = FakeYDL
        class _U:
            DownloadError = FakeDownloadError
        fake.utils = _U()
        _sys.modules["yt_dlp"] = fake

        from scripts import download_video as dl
        importlib.reload(dl)
        return dl

    def test_private_video_raises_auth_error(self, monkeypatch, tmp_path):
        dl = self._run_private_video_sim(monkeypatch, tmp_path, sys.modules)
        with pytest.raises(dl.AuthNeededError):
            dl.download("https://youtube.com/watch?v=2ExOHMwEDD4",
                        base_root=str(tmp_path), download_subs=False)

    def test_invalid_url_raises(self, monkeypatch, tmp_path):
        dl = self._run_private_video_sim(monkeypatch, tmp_path, sys.modules)
        # different message → SystemExit instead of AuthNeededError
        class FakeBadURL(Exception):
            def __str__(self):
                return "is not a valid URL"

        class BadYDL:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def extract_info(self, *a, **k):
                raise FakeBadURL()

            def download(self, *a, **k):
                raise FakeBadURL()

        import sys as _sys
        import types
        fake = types.ModuleType("yt_dlp")
        fake.YoutubeDL = BadYDL
        class _U:
            DownloadError = FakeBadURL
        fake.utils = _U()
        _sys.modules["yt_dlp"] = fake
        import importlib
        from scripts import download_video as dl2
        importlib.reload(dl2)
        with pytest.raises(SystemExit):
            dl2.download("not-a-url", base_root=str(tmp_path), download_subs=False)
