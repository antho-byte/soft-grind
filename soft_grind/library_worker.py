"""Background job: python -m soft_grind.library_worker <data>/library_job.json  (looks at every new image in the folder)."""
from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path

from . import ai, library, projects, settings


def run(job_path: str) -> None:
    jp = Path(job_path)
    job = projects.read_json(jp)
    spec = job["spec"]

    def save(**kw):
        job.update(kw); job["updated"] = time.time(); projects.write_json(jp, job)

    token = os.getenv("SOFTGRIND_AI_TOKEN", "") if spec.get("use_ai") else ""
    model = spec.get("model") or settings.load_keys().get("ai_model") or ai.DEFAULT_MODEL
    client = ai.AIClient(token or settings.load_keys().get("ai", ""), model) if spec.get("use_ai") else None
    files = library.scan(spec["folder"])
    todo = [p for p in files if library.needs_analysis(library.load_db(), p)]
    save(state="running", done=0, total=len(todo), message="looking at the images", error="", spent=0.0)
    try:
        spent = [0.0]
        def progress(i, n, name):
            save(done=i, total=n, message=f"{i}/{n} · {name}")
        spent[0] = library.analyse_pending(files, client, progress)
        save(state="done", message=f"done: {len(todo)} images", spent=spent[0], finished=time.time())
    except Exception as e:
        traceback.print_exc()
        save(state="failed", message="failed", error=f"{e.__class__.__name__}: {e}")


if __name__ == "__main__":
    run(sys.argv[1])
