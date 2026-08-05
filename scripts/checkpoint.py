# -*- coding: utf-8 -*-
"""
Checkpoint — crash-safe resume for long batch runs.

Roadmap item 4.2 ("استئناف ذكي بعد انقطاع"). The pipeline writes a tiny
checkpoint.json per project; on restart, finished stages are skipped and
only the interrupted stage re-runs. Complements the existing reuse of
transcription caches and cut files with explicit stage tracking.

    with StageTracker(project_folder) as st:
        st.run("transcribe", fn)      # skipped if already done
        st.run("cut", fn, force=True) # forced re-run
        st.run("edit", fn)

Design: pure stdlib, atomic JSON writes, never raises on I/O problems
(best-effort — a broken checkpoint must not break the pipeline).
"""

import json
import os
import tempfile
import time

CHECKPOINT_FILENAME = "checkpoint.json"
STAGES = [
    "download", "transcribe", "segments", "safety", "cut",
    "edit", "polish", "subtitles", "scorecard", "done",
]


def checkpoint_path(project_folder):
    return os.path.join(project_folder, CHECKPOINT_FILENAME)


def load_checkpoint(project_folder):
    path = checkpoint_path(project_folder)
    if not os.path.exists(path):
        return {"stages": {}, "updated": None}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("stages"), dict):
            return {"stages": {}, "updated": None}
        return data
    except Exception:
        return {"stages": {}, "updated": None}


def save_checkpoint(project_folder, stages):
    data = {"stages": stages, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    path = checkpoint_path(project_folder)
    try:
        os.makedirs(project_folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=project_folder, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except Exception:
                    pass
            raise
    except Exception:
        pass  # best-effort only


def is_done(project_folder, stage):
    """True when the stage completed in a previous run."""
    return load_checkpoint(project_folder)["stages"].get(stage) is True


def mark_done(project_folder, stage):
    data = load_checkpoint(project_folder)
    data["stages"][stage] = True
    save_checkpoint(project_folder, data["stages"])


def clear(project_folder, stage=None):
    """Remove one stage (or all) from the checkpoint."""
    data = load_checkpoint(project_folder)
    if stage is None:
        data["stages"] = {}
    else:
        data["stages"].pop(stage, None)
    save_checkpoint(project_folder, data["stages"])


def list_pending(project_folder):
    """Stages not yet done, in canonical order."""
    done = load_checkpoint(project_folder)["stages"]
    return [s for s in STAGES if not done.get(s)]


class StageTracker:
    """Context manager that wraps the checkpoint lifecycle for one run."""

    def __init__(self, project_folder, enabled=True):
        self.project_folder = project_folder
        self.enabled = enabled
        self._completed_this_run = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False  # never swallow exceptions

    def run(self, stage, fn, *args, force=False, **kwargs):
        """Run fn(*args, **kwargs) unless the stage is already done.

        Returns the fn result. Raises fn's exceptions normally (the stage
        is only marked done when fn returns successfully).
        """
        if not self.enabled:
            return fn(*args, **kwargs)
        if not force and is_done(self.project_folder, stage):
            print("[checkpoint] skipping completed stage '{}'".format(stage))
            return None
        result = fn(*args, **kwargs)
        mark_done(self.project_folder, stage)
        self._completed_this_run.append(stage)
        return result

    def resume_info(self):
        return {
            "skipped": self._completed_this_run,
            "pending": list_pending(self.project_folder),
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ViralCutter checkpoint tool.")
    parser.add_argument("--project", required=True, help="project folder")
    parser.add_argument("--status", action="store_true", help="show stage status")
    parser.add_argument("--mark", default=None, help="mark a stage done (e.g. cut)")
    parser.add_argument("--clear", nargs="?", const="__all__", default=None,
                        help="clear one stage or all (no value)")
    args = parser.parse_args()
    if args.status:
        for s in STAGES:
            print("{}: {}".format(s, "done" if is_done(args.project, s) else "pending"))
    elif args.mark:
        mark_done(args.project, args.mark)
        print("marked '{}' done".format(args.mark))
    elif args.clear is not None:
        clear(args.project, None if args.clear == "__all__" else args.clear)
        print("cleared checkpoint{}".format("" if args.clear == "__all__" else " for " + args.clear))
    else:
        print("pending: {}".format(", ".join(list_pending(args.project))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
