import json

from scripts.pipeline_engine import PipelineEngine
from webui.editor_core import EditorState
from webui.render_queue import RenderQueue


def test_editor_undo_and_roundtrip(tmp_path):
    p = tmp_path / "project.json"
    e = EditorState("input.mp4")
    e.add_clip("input.mp4", 0, 10)
    e.set_transform(0, aspect="9:16", zoom=1.2)
    assert e.undo()
    assert e.clips[0]["zoom"] == 1.0
    e.redo()
    assert e.clips[0]["zoom"] == 1.2
    e.save(p)
    loaded = EditorState.load(p)
    assert loaded.clips[0]["aspect"] == "9:16"
    assert loaded.clips[0]["zoom"] == 1.2

def test_render_queue_persists_and_recovers(tmp_path):
    p = tmp_path / "queue.json"
    q = RenderQueue(p)
    jid = q.add({"source": "a.mp4"})
    q.jobs[jid].status = "running"
    q._save()
    q2 = RenderQueue(p)
    assert q2.jobs[jid].status == "queued"

def test_pipeline_dependencies_and_persistence(tmp_path):
    p = tmp_path / "run.json"
    out = []
    e = PipelineEngine(p)
    e.register("a", lambda c,r: out.append("a") or 1)
    e.register("b", lambda c,r: out.append("b") or 2, deps=["a"])
    result = e.run()
    assert out == ["a", "b"]
    assert result["b"] == 2
    assert json.loads(p.read_text())["stages"]["b"]["status"] == "success"

def test_pipeline_cycle_detection(tmp_path):
    e = PipelineEngine(tmp_path / "run.json")
    e.register("a", lambda c,r: 1, deps=["b"])
    e.register("b", lambda c,r: 2, deps=["a"])
    try:
        e.order()
        raise AssertionError("cycle should fail")
    except ValueError:
        pass
