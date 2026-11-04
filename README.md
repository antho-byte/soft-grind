# soft grind. studio

Local app for the soft grind. YouTube channel: Suno music → playlist → thumbnail → YouTube metadata.

Start it by double-clicking `start-windows.bat` (or `start-mac.command`). It updates itself from GitHub each time, and keeps your keys and projects in `soft-grind-data` in your user folder.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ACEDATACLOUD_API_TOKEN=...   # optional; without it the app runs in mock mode
streamlit run app.py
```

1. **music** – style presets (lofi soul / japanese jazz / city pop funk), scene flavours, generates instrumental
   tracks through the AceDataCloud Suno API (the API behind SunoMCP). Max 360 s per request.
2. **playlist** – replaces usesuno.com: paste a published suno.com/playlist link, song links, or import a folder.
3. **thumbnail** – image + quote → 1280×720 thumbnail and 1920×1080 still (normal or cyberpunk), bulk mode + contact sheet.
4. **youtube** – title, description with real timestamps (minus crossfade), tags, pinned comment, `upload.txt`.

Everything is saved in `projects/<name>/`. Tests: `pytest tests`.
