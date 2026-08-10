# -*- coding: utf-8 -*-
"""Publish panel (WebUI per-clip play/translate/music/upload) — pure logic."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "webui"))

from webui import publish_panel as pp  # noqa: E402


def _project(tmp_path):
    project = tmp_path / "proj"
    (project / "final").mkdir(parents=True)
    (project / "subs").mkdir()
    (project / "cuts").mkdir()
    for i in range(2):
        (project / "final" / "{:03d}_clip.mp4".format(i)).write_bytes(b"x")
        (project / "cuts" / "{:03d}_clip_original_scale.mp4".format(i)).write_bytes(b"x")
    (project / "viral_segments.txt").write_text(json.dumps({
        "segments": [
            {"title": "First Title", "caption": "cap 1", "start_time": 0, "end_time": 5},
            {"title": "Second Title", "caption": "cap 2", "start_time": 5, "end_time": 10},
        ]}), encoding="utf-8")
    return str(project)


class TestClips:
    def test_list_prefers_final(self, tmp_path):
        project = _project(tmp_path)
        clips = pp.list_clips(project)
        assert len(clips) == 2
        assert all("final" in c for c in clips)

    def test_list_falls_back_to_cuts(self, tmp_path):
        project = _project(tmp_path)
        shutil_rmtree(project, "final")
        clips = pp.list_clips(project)
        assert len(clips) == 2
        assert all("cuts" in c for c in clips)

    def test_index_parsed_from_filename(self):
        assert pp.clip_index("/x/000_clip.mp4") == 0
        assert pp.clip_index("/x/012_final.mp4") == 12
        assert pp.clip_index("/x/final_foo.mp4") is None

    def test_empty_project(self, tmp_path):
        assert pp.list_clips(str(tmp_path / "nope")) == []


class TestSubtitles:
    def test_find_processed_preferred(self, tmp_path):
        project = _project(tmp_path)
        clip = os.path.join(project, "final", "000_clip.mp4")
        (tmp_path / "proj" / "subs" / "000_clip_original.json").write_text("{}")
        (tmp_path / "proj" / "subs" / "000_clip_processed.json").write_text("{}")
        found = pp.find_subs_for_clip(project, clip)
        assert found.endswith("000_clip_processed.json")

    def test_no_subs(self, tmp_path):
        project = _project(tmp_path)
        clip = os.path.join(project, "final", "001_clip.mp4")
        assert pp.find_subs_for_clip(project, clip) is None

    def test_suggestion_from_segments(self, tmp_path):
        project = _project(tmp_path)
        clip = os.path.join(project, "final", "001_clip.mp4")
        title, caption = pp.clip_suggestion(project, clip)
        assert title == "Second Title"
        assert caption == "cap 2"

    def test_subtitle_preview(self, tmp_path):
        project = _project(tmp_path)
        clip = os.path.join(project, "final", "000_clip.mp4")
        sub = os.path.join(project, "subs", "000_clip_processed.json")
        with open(sub, "w", encoding="utf-8") as f:
            json.dump({"segments": [{"text": "hello"}, {"text": "world"}]}, f)
        preview = pp.clip_subtitle_preview(project, clip)
        assert "hello" in preview and "world" in preview


class TestTranslate:
    def test_missing_clip(self, tmp_path):
        ok, msg = pp.translate_clip(str(tmp_path), "/nope.mp4", "en")
        assert ok is False

    def test_missing_lang(self, tmp_path):
        project = _project(tmp_path)
        clip = os.path.join(project, "final", "000_clip.mp4")
        ok, _msg = pp.translate_clip(project, clip, "  ")
        assert ok is False

    def test_translates_and_writes(self, tmp_path, monkeypatch):
        # translate_json has heavy module-level deps (tqdm/deep_translator) —
        # stub them so the import succeeds, then patch the function itself.
        import types
        tqdm_mod = types.ModuleType("tqdm")
        tqdm_asyncio = types.ModuleType("tqdm.asyncio")
        tqdm_asyncio.tqdm_asyncio = None
        deep_tr = types.ModuleType("deep_translator")
        deep_tr.GoogleTranslator = type("GoogleTranslator", (), {})
        monkeypatch.setitem(sys.modules, "tqdm", tqdm_mod)
        monkeypatch.setitem(sys.modules, "tqdm.asyncio", tqdm_asyncio)
        monkeypatch.setitem(sys.modules, "deep_translator", deep_tr)

        project = _project(tmp_path)
        clip = os.path.join(project, "final", "000_clip.mp4")
        sub = os.path.join(project, "subs", "000_clip_processed.json")
        with open(sub, "w", encoding="utf-8") as f:
            json.dump({"segments": [{"text": "مرحبا", "words": [{"word": "مرحبا"}]}]}, f)

        import scripts.translate_json as tj

        async def fake_translate(src, dst, lang):
            with open(src, encoding="utf-8") as f:
                data = json.load(f)
            data["segments"][0]["text"] = "hello"
            with open(dst, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return data

        monkeypatch.setattr(tj, "translate_json_file", fake_translate)
        ok, msg = pp.translate_clip(project, clip, "en")
        assert ok is True
        assert "_translated_en.json" in msg
        out = os.path.join(project, "subs", "000_clip_processed_translated_en.json")
        assert os.path.exists(out)


class TestMusicCheck:
    def test_report_formatted(self, tmp_path, monkeypatch):
        project = _project(tmp_path)
        report = {
            "summary": {"checked": 2, "matched": 1, "no_fpcalc": 0, "errors": 0},
            "clips": [
                {"index": 0, "video": "a.mp4", "verdict": "clean"},
                {"index": 1, "video": "b.mp4", "verdict": "local_match",
                 "suggestion": "Audio overlaps 'T' (80%)"},
            ],
        }
        import scripts.music_fingerprint as mf
        monkeypatch.setattr(mf, "analyze_project", lambda *a, **k: report)
        monkeypatch.setattr(mf, "build_local_db", lambda *a, **k: {"songs": []})
        monkeypatch.setattr(mf, "load_local_db", lambda *a: {"songs": []})
        text = pp.run_music_check(project)
        assert "2 clips checked" in text
        assert "🎵⚠️" in text
        assert "Licensed" not in text


class TestStreamUpload:
    def test_missing_clip(self):
        lines = list(pp.stream_upload("/tmp/x", "youtube", "/nope.mp4",
                                      "T", "C", [], True, "warn"))
        assert any("Clip not found" in label for label in lines)

    def test_upload_flow(self, tmp_path, monkeypatch):
        project = _project(tmp_path)
        clip = os.path.join(project, "final", "000_clip.mp4")
        captured = {}

        class FakeUploader:
            def __init__(self, project_folder, dry_run=False, music_gate=None):
                captured["project"] = project_folder
                captured["dry_run"] = dry_run
                captured["music_gate"] = music_gate

            def upload(self, video_path, title, caption, hashtags, index=None):
                captured["video"] = video_path
                captured["title"] = title
                captured["index"] = index
                return {"status": "uploaded", "platform": "youtube",
                        "video_id": "ABC"}

        import scripts.upload_gate as ug
        monkeypatch.setattr(ug, "UPLOADERS",
                            {"youtube": lambda *a, **k: FakeUploader(*a, **k)})
        lines = list(pp.stream_upload(project, "youtube", clip, "My Title",
                                      "Cap", ["#shorts"], False, "block"))
        out = "\n".join(lines)
        assert captured["video"] == clip
        assert captured["index"] == 0
        assert captured["music_gate"] == "block"
        assert captured["dry_run"] is False
        assert "Upload finished." in out

    def test_blocked_clip_reported(self, tmp_path, monkeypatch):
        project = _project(tmp_path)
        clip = os.path.join(project, "final", "000_clip.mp4")

        class FakeUploader:
            def __init__(self, *a, **k):
                pass

            def upload(self, *a, **k):
                raise Exception("Upload refused by ViralCutter safety gate: blocked")

        import scripts.upload_gate as ug
        monkeypatch.setattr(ug, "UPLOADERS",
                            {"youtube": lambda *a, **k: FakeUploader(*a, **k)})
        lines = list(pp.stream_upload(project, "youtube", clip, "T", "C", [],
                                      True, "warn"))
        out = "\n".join(lines)
        assert "Upload refused" in out


def shutil_rmtree(project, sub):
    import shutil
    shutil.rmtree(os.path.join(project, sub))
