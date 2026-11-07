"""Work through a queue: python -m soft_grind.queue <data>/queue_<kind>.json  (kind = render | upload).

Each video keeps its own job file (render.json / youtube.json) so its card shows 'waiting in line', then its own progress.
New videos can be added while the queue runs: the list is re-read after every video.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from . import projects


def run(queue_path: str) -> None:
    qf = Path(queue_path)
    kind = qf.stem.split("_", 1)[1]
    jobname = projects.QUEUES[kind]
    stop = threading.Event()

    def heartbeat():                                 # keeps the queue and the videos still waiting 'alive' for the app
        while not stop.wait(20):
            with projects._locked(qf):
                q = projects.read_json(qf); q["updated"] = time.time(); projects.write_json(qf, q)
            for item in q.get("items", []):
                jp = Path(item) / jobname
                j = projects.read_json(jp)
                if j.get("state") == "queued":
                    j["updated"] = time.time(); projects.write_json(jp, j)

    threading.Thread(target=heartbeat, daemon=True).start()
    with projects._locked(qf):
        q = projects.read_json(qf); q.update(state="running", updated=time.time()); projects.write_json(qf, q)
    try:
        while True:
            with projects._locked(qf):
                q = projects.read_json(qf)
                items = q.get("items", [])
                if not items:
                    projects.write_json(qf, {"state": "done", "items": [], "updated": time.time()})
                    return
                item = items[0]
            jp = Path(item) / jobname
            if projects.read_json(jp).get("state") == "queued":          # not cancelled meanwhile
                try:
                    if kind == "render":
                        from . import render
                        render.run(str(jp))
                    else:
                        from . import youtube_worker
                        youtube_worker.run(str(jp))
                except Exception as e:                                   # one bad video never stops the rest
                    projects.write_json(jp, {"state": "failed", "message": "failed", "error": f"{e.__class__.__name__}: {e}",
                                             "updated": time.time()})
            with projects._locked(qf):
                q = projects.read_json(qf)
                q["items"] = [i for i in q.get("items", []) if i != item]
                q["updated"] = time.time()
                projects.write_json(qf, q)
    finally:
        stop.set()


if __name__ == "__main__":
    run(sys.argv[1])
