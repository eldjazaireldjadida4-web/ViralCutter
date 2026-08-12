# -*- coding: utf-8 -*-
"""Persistent render queue with cancellation and atomic state."""
from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass


@dataclass
class RenderJob:
    id: str
    plan: dict
    status: str = "queued"
    created: float = 0.0
    started: float | None = None
    finished: float | None = None
    output: str | None = None
    error: str | None = None

class RenderQueue:
    def __init__(self, state_path):
        self.state_path = str(state_path)
        self.jobs = {}
        self._load()

    def _load(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.jobs = {k: RenderJob(**v) for k, v in raw.get("jobs", {}).items()}
            # A process cannot still be running after a crash.
            for j in self.jobs.values():
                if j.status == "running":
                    j.status = "queued"
        except Exception:
            self.jobs = {}

    def _save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.state_path)), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(self.state_path)), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump({"jobs": {k: asdict(v) for k,v in self.jobs.items()}},
                          f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.state_path)
        finally:
            if os.path.exists(tmp):
                try: os.remove(tmp)
                except OSError: pass

    def add(self, plan):
        jid = uuid.uuid4().hex
        self.jobs[jid] = RenderJob(jid, plan, created=time.time())
        self._save()
        return jid

    def cancel(self, job_id):
        j = self.jobs[job_id]
        if j.status in {"queued", "running"}:
            j.status = "cancelled"
            self._save()
        return j.status

    def pending(self):
        return [j for j in self.jobs.values() if j.status == "queued"]
