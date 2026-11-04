#!/bin/bash
# Double-click to start soft grind. studio (Mac)
# Your keys, projects and the installed helper files live in ~/soft-grind-data,
# so you can overwrite this app folder with a new version at any time.
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then echo "Python 3 is not installed. Get it from https://www.python.org/downloads/ then double-click this file again."; read -p "Press Enter to close"; exit 1; fi
DATA="$HOME/soft-grind-data"; mkdir -p "$DATA"
[ -d "$DATA/venv" ] || python3 -m venv "$DATA/venv"
source "$DATA/venv/bin/activate"
python update.py
pip install -q -r requirements.txt
streamlit run app.py
