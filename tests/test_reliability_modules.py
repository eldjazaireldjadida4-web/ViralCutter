# -*- coding: utf-8 -*-
"""Tests for reliability modules: checkpoint, secure_config, oom_guard, auto_updater."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import checkpoint, secure_config, oom_guard, auto_updater


# ---------------------------------------------------------------------------
# checkpoint
# ---------------------------------------------------------------------------

class TestCheckpoint:
    def test_run_marks_done(self, tmp_path):
        calls = []
        with checkpoint.StageTracker(str(tmp_path)) as st:
            st.run("cut", lambda: calls.append("x") or "result")
        assert calls == ["x"]
        assert checkpoint.is_done(str(tmp_path), "cut")

    def test_second_run_skips(self, tmp_path):
        calls = []
        with checkpoint.StageTracker(str(tmp_path)) as st:
            st.run("cut", lambda: calls.append(1))
            st.run("cut", lambda: calls.append(2))
        assert calls == [1]  # second call skipped

    def test_force_reruns(self, tmp_path):
        calls = []
        with checkpoint.StageTracker(str(tmp_path)) as st:
            st.run("cut", lambda: calls.append(1))
            st.run("cut", lambda: calls.append(2), force=True)
        assert calls == [1, 2]

    def test_failed_stage_not_marked(self, tmp_path):
        with pytest.raises(ValueError):
            with checkpoint.StageTracker(str(tmp_path)) as st:
                st.run("cut", lambda: (_ for _ in ()).throw(ValueError("boom")))
        assert not checkpoint.is_done(str(tmp_path), "cut")

    def test_clear_and_pending(self, tmp_path):
        checkpoint.mark_done(str(tmp_path), "cut")
        checkpoint.mark_done(str(tmp_path), "edit")
        assert "cut" not in checkpoint.list_pending(str(tmp_path))
        checkpoint.clear(str(tmp_path), "edit")
        assert "edit" in checkpoint.list_pending(str(tmp_path))

    def test_disabled_tracker_runs_everything(self, tmp_path):
        calls = []
        with checkpoint.StageTracker(str(tmp_path), enabled=False) as st:
            st.run("cut", lambda: calls.append(1))
            st.run("cut", lambda: calls.append(2))
        assert calls == [1, 2]

    def test_corrupt_checkpoint_is_safe(self, tmp_path):
        (tmp_path / checkpoint.CHECKPOINT_FILENAME).write_text("{not json", encoding="utf-8")
        assert checkpoint.is_done(str(tmp_path), "cut") is False


# ---------------------------------------------------------------------------
# secure_config
# ---------------------------------------------------------------------------

class TestSecureConfig:
    def test_set_get_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secure_config, "_base_dir", lambda: str(tmp_path))
        path = secure_config.set_key("sk-test-123", passphrase="hunter2")
        assert os.path.exists(path)
        assert secure_config.get_key(passphrase="hunter2") == "sk-test-123"

    def test_wrong_passphrase_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secure_config, "_base_dir", lambda: str(tmp_path))
        secure_config.set_key("sk-test-123", passphrase="right")
        assert secure_config.get_key(passphrase="wrong") is None

    def test_env_var_takes_priority(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secure_config, "_base_dir", lambda: str(tmp_path))
        secure_config.set_key("sk-file", passphrase="p")
        monkeypatch.setenv("GEMINI_API_KEY", "sk-env")
        assert secure_config.resolve_api_key() == "sk-env"

    def test_legacy_plaintext_warns(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secure_config, "_base_dir", lambda: str(tmp_path))
        with open(secure_config.legacy_config_path(), "w", encoding="utf-8") as f:
            json.dump({"gemini": {"api_key": "sk-legacy"}}, f)
        assert secure_config.resolve_api_key(warn=False) == "sk-legacy"

    def test_load_api_config_injects_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secure_config, "_base_dir", lambda: str(tmp_path))
        monkeypatch.setenv("VIRALCUTTER_CONFIG_PASSPHRASE", "p")
        secure_config.set_key("sk-injected", passphrase="p")
        config = secure_config.load_api_config()
        assert config["gemini"]["api_key"] == "sk-injected"

    def test_no_passphrase_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(secure_config, "_base_dir", lambda: str(tmp_path))
        with pytest.raises(ValueError):
            secure_config.set_key("sk", passphrase="")


# ---------------------------------------------------------------------------
# oom_guard
# ---------------------------------------------------------------------------

class _FakeOOM(Exception):
    pass


class TestOomGuard:
    def test_retries_smaller_on_oom(self, tmp_path):
        used = []

        def fake_transcribe(_in, model, project_folder=None):
            used.append(model)
            if model == "large-v3-turbo":
                raise _FakeOOM("CUDA out of memory")
            return ("x.srt", "x.tsv")

        result = oom_guard.transcribe_with_fallback(
            "in.mp4", "large-v3-turbo", str(tmp_path),
            transcribe_fn=fake_transcribe, verbose=False)
        assert result == ("x.srt", "x.tsv")
        assert used == ["large-v3-turbo", "medium"]

    def test_non_oom_error_propagates(self, tmp_path):
        def fake_transcribe(_in, model, project_folder=None):
            raise ValueError("transcript empty")

        with pytest.raises(ValueError):
            oom_guard.transcribe_with_fallback(
                "in.mp4", "large", str(tmp_path),
                transcribe_fn=fake_transcribe, verbose=False)

    def test_success_first_try(self, tmp_path):
        used = []

        def fake_transcribe(_in, model, project_folder=None):
            used.append(model)
            return ("a", "b")

        oom_guard.transcribe_with_fallback(
            "in.mp4", "small", str(tmp_path),
            transcribe_fn=fake_transcribe, verbose=False)
        assert used == ["small"]

    def test_chain_exhausted_raises(self, tmp_path):
        def fake_transcribe(_in, model, project_folder=None):
            raise _FakeOOM("CUDA out of memory")

        with pytest.raises(_FakeOOM):
            oom_guard.transcribe_with_fallback(
                "in.mp4", "tiny", str(tmp_path),
                transcribe_fn=fake_transcribe, verbose=False)


# ---------------------------------------------------------------------------
# auto_updater
# ---------------------------------------------------------------------------

class TestAutoUpdater:
    def test_no_update_when_versions_equal(self):
        info = auto_updater.check_for_update(
            current_version="0.9.0", timeout=1,
            urlopen=lambda t: json.dumps({
                "tag_name": "v0.9.0",
                "assets": [{"name": "ViralCutter.exe",
                            "browser_download_url": "https://x/ViralCutter.exe"}],
                "body": "release notes",
            }).encode())
        assert info["update_available"] is False
        assert info["latest_version"] == "v0.9.0"

    def test_update_available_when_remote_newer(self):
        info = auto_updater.check_for_update(
            current_version="0.8.0", timeout=1,
            urlopen=lambda t: json.dumps({
                "tag_name": "v1.0.0",
                "assets": [{"name": "ViralCutter.exe",
                            "browser_download_url": "https://x/ViralCutter.exe"}],
            }).encode())
        assert info["update_available"] is True
        assert info["download_url"] == "https://x/ViralCutter.exe"

    def test_offline_is_safe(self):
        info = auto_updater.check_for_update(timeout=1,
                                             urlopen=lambda t: (_ for _ in ()).throw(
                                                 RuntimeError("network down")))
        assert info["update_available"] is False
        assert info["error"] is not None

    def test_parse_version(self):
        assert auto_updater._parse_version("v0.9.0") == (0, 9, 0)
        assert auto_updater._parse_version("1.2") == (1, 2, 0)
        assert auto_updater._parse_version("garbage") == (0, 0, 0)

    def test_download_update(self, tmp_path, monkeypatch):
        class FakeResp:
            def __init__(self):
                self._left = 2

            def read(self, n):
                if self._left > 0:
                    self._left -= 1
                    return b"BINARY"
                return b""

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        monkeypatch.setattr(auto_updater.urllib.request, "urlopen",
                            lambda *a, **k: FakeResp())
        dest = tmp_path / "upd"
        path = auto_updater.download_update("https://x/ViralCutter.exe",
                                            dest_dir=str(dest))
        assert os.path.exists(path)
        with open(path, "rb") as f:
            assert f.read() == b"BINARYBINARY"
        info = auto_updater.update_info(dest_dir=str(dest))
        assert info[1] == "ViralCutter.exe"


class TestAutoUpdaterTagsFallback:
    def test_falls_back_to_tags_when_no_releases(self, monkeypatch):
        calls = {}

        def fake_github(path, timeout=8):
            calls["path"] = path
            if "releases" in path:
                raise RuntimeError("Not Found (no release)")
            return [{"name": "v0.9.1"}]

        monkeypatch.setattr(auto_updater, "_github_api", fake_github)
        info = auto_updater.check_for_update(current_version="0.9.0", timeout=1)
        assert info["update_available"] is True
        assert info["latest_version"] == "v0.9.1"
        assert "tags" in calls["path"]

    def test_tag_same_version_no_update(self, monkeypatch):
        def fake_github(path, timeout=8):
            if "releases" in path:
                raise RuntimeError("no release")
            return [{"name": "v0.9.0"}]

        monkeypatch.setattr(auto_updater, "_github_api", fake_github)
        info = auto_updater.check_for_update(current_version="0.9.0", timeout=1)
        assert info["update_available"] is False
