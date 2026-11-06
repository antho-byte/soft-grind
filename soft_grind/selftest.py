"""Started by the setup check as a detached background process, to prove background jobs work on this computer."""
import json
import os
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    p = Path(sys.argv[1])
    p.write_text(json.dumps({"state": "done", "pid": os.getpid(), "python": sys.version.split()[0], "updated": time.time()}), encoding="utf-8")
