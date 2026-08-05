# -*- coding: utf-8 -*-
"""Tests for the upload gate (forced refusal before publishing)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import upload_gate as ug


def _write(project, name, data):
    with open(os.path.join(project, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class TestBlocklist:
    def test_clean_project_allows(self, tmp_path):
        verdict = ug.check_clip(str(tmp_path), 0, "Nice title", "Nice caption", ["shorts"])
        assert verdict["allowed"] is True
        assert verdict["reasons"] == []

    def test_blocked_clip_refused(self, tmp_path):
        _write(tmp_path, ug.PUBLISH_BLOCKLIST, {
            "blocked": [{"index": 0, "title": "Bad", "axes": {"reuse": {"score": 80}}}]})
        verdict = ug.check_clip(str(tmp_path), 0, "Title", "Caption", [])
        assert verdict["allowed"] is False
        assert any(r["source"] == "publish_blocklist" for r in verdict["reasons"])

    def test_other_index_not_blocked(self, tmp_path):
        _write(tmp_path, ug.PUBLISH_BLOCKLIST, {
            "blocked": [{"index": 1, "title": "Bad", "axes": {"reuse": {"score": 80}}}]})
        verdict = ug.check_clip(str(tmp_path), 0, "Title", "Caption", [])
        assert verdict["allowed"] is True

    def test_gate_upload_raises(self, tmp_path):
        _write(tmp_path, ug.PUBLISH_BLOCKLIST, {
            "blocked": [{"index": 0, "title": "Bad", "axes": {"reuse": {"score": 90}}}]})
        with pytest.raises(ug.UploadGateError) as ei:
            ug.gate_upload(str(tmp_path), 0, "Title", "Caption", [])
        assert any(r["severity"] == "high" for r in ei.value.reasons)


class TestSafetyReport:
    def test_safety_blocked_refused(self, tmp_path):
        _write(tmp_path, ug.SAFETY_REPORT, {
            "blocked": [{"index": 2, "reason": "hate speech (high)"}]})
        verdict = ug.check_clip(str(tmp_path), 2, "Title", "Caption", [])
        assert verdict["allowed"] is False
        assert any(r["source"] == "safety_report" for r in verdict["reasons"])


class TestMetadataGate:
    def test_medical_claim_blocks(self, tmp_path):
        verdict = ug.check_clip(str(tmp_path), 0, "This cures cancer", "", [])
        assert verdict["allowed"] is False
        assert any(r["source"] == "metadata_compliance" for r in verdict["reasons"])

    def test_clean_metadata_allows(self, tmp_path):
        verdict = ug.check_clip(str(tmp_path), 0, "Top 5 Tips", "Full video", ["shorts"])
        assert verdict["allowed"] is True


class TestUploaders:
    def test_uploader_blocks_before_any_sdk_call(self, tmp_path, monkeypatch):
        _write(tmp_path, ug.PUBLISH_BLOCKLIST, {
            "blocked": [{"index": 0, "title": "Bad", "axes": {"reuse": {"score": 85}}}]})
        uploader = ug.YouTubeUploader(str(tmp_path), dry_run=True)
        with pytest.raises(ug.UploadGateError):
            uploader.upload("clip.mp4", "Title", "Caption", [], index=0)

    def test_uploader_dry_run_allows_clean(self, tmp_path, capsys):
        uploader = ug.YouTubeUploader(str(tmp_path), dry_run=True)
        result = uploader.upload("clip.mp4", "Title", "Caption", ["shorts"], index=0)
        assert result["status"] == "dry-run"
        out = capsys.readouterr().out
        assert "DRY-RUN" in out

    def test_uploader_without_credentials_fails_loudly(self, tmp_path):
        uploader = ug.TikTokUploader(str(tmp_path), dry_run=False)
        with pytest.raises(RuntimeError, match="OAuth credentials"):
            uploader.upload("clip.mp4", "Title", "Caption", [], index=0)


class TestAudit:
    def test_audit_project(self, tmp_path):
        _write(tmp_path, ug.SCORECARD, {
            "segments": [
                {"index": 0, "title": "Clean"},
                {"index": 1, "title": "Dangerous cure"},
            ]})
        _write(tmp_path, ug.PUBLISH_BLOCKLIST, {
            "blocked": [{"index": 1, "title": "Dangerous cure", "axes": {"reuse": {"score": 75}}}]})
        allowed, blocked = ug.audit_project(str(tmp_path))
        assert allowed == [0]
        assert len(blocked) == 1
        assert blocked[0]["index"] == 1
