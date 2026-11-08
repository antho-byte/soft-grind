"""Make a batch of whole videos: python -m soft_grind.batch <data>/batch.json

Two videos are worked on at the same time (their music is made by the service, so that costs the computer nothing);
building the videos themselves happens one at a time (see auto.RENDER_LOCK). One phone message at the end, plus one for
every video that stops or needs you.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

from . import auto, notify, projects


def run(batch_path: str) -> None:
    bf = Path(batch_path)
    b = projects.read_json(bf)
    items = [Path(i) for i in b.get("items", [])]
    lock = threading.Lock()
    todo = list(items)
    stop = threading.Event()

    def beat():                                       # the batch and the videos still waiting stay 'alive' for the app
        while not stop.wait(20):
            cur = projects.read_json(bf); cur["updated"] = time.time(); projects.write_json(bf, cur)
            for p in items:
                j = projects.read_json(p / projects.AUTO)
                if j.get("state") == "queued":
                    j["updated"] = time.time(); projects.write_json(p / projects.AUTO, j)

    def worker():
        while True:
            with lock:
                if not todo or projects.read_json(bf).get("cancel"):
                    return
                p = todo.pop(0)
            if projects.read_json(p / projects.AUTO).get("state") != "queued":
                continue                                  # cancelled or deleted meanwhile
            auto.run(str(p / projects.AUTO))
            st = projects.auto_status(p)
            if st["state"] in ("failed", "needs_attention"):
                notify.send(f"{p.name} stopped" if st["state"] == "failed" else f"{p.name} needs you",
                            "Open soft grind. to see what happened. The rest of the batch goes on.", priority="high", tags="warning")

    b.update(state="running", updated=time.time()); projects.write_json(bf, b)
    threading.Thread(target=beat, daemon=True).start()
    threads = [threading.Thread(target=worker) for _ in range(projects.BATCH_PARALLEL)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    states = {p.name: projects.auto_status(p)["state"] for p in items}
    made = [n for n, s in states.items() if s == "done"]
    dates = sorted(projects.meta(p).get("schedule", "") for p in items if states[p.name] == "done" and projects.meta(p).get("schedule"))
    cur = projects.read_json(bf)
    cur.update(state="cancelled" if cur.get("cancel") else "done", finished=time.time(), updated=time.time(),
               made=made, problems=[n for n, s in states.items() if s in ("failed", "needs_attention")])
    projects.write_json(bf, cur)
    when = f" · planned {dates[0][5:10].replace('-', '/')} to {dates[-1][5:10].replace('-', '/')}" if dates else ""
    notify.send("batch done" if not cur.get("cancel") else "batch stopped",
                f"{len(made)} of {len(items)} videos made{when}. Open soft grind. to check them.", priority="high", tags="tada")


if __name__ == "__main__":
    run(sys.argv[1])
