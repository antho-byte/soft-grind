# soft grind. studio

Local app for the soft grind. YouTube channel: Suno music → playlist → thumbnail → YouTube metadata.

Start it by double-clicking `start-windows.bat` (or `start-mac.command`). It updates itself from GitHub each time, and keeps your keys and projects in `soft-grind-data` in your user folder.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ACEDATACLOUD_API_TOKEN=...   # optional; without it the app runs in mock mode
streamlit run app.py
```

Pages: **videos** (one card per mix; new video step by step or fully automatic), **images** (your picture library),
**settings** (keys, phone messages, password, setup check). Each video has three tabs: **music**, **cover**, **video**.

- **automatic mode** makes the whole video in the background: music, picture, headline, thumbnail, video, text.
- **phone messages** (settings): a free ntfy.sh topic pings your phone when a video is done or needs you.
- **credits used** are tracked per video (estimates) and shown on the videos page.
- **free up space** on a finished video deletes its songs and working images and keeps the video, thumbnail and upload text.
- **film look** (video tab, video settings): subtle grain, vignette, flicker, dust and colour tint, with a 20-second test before the long render.
- **upload to YouTube** (settings, youtube card): connect once with a Google Cloud 'Desktop app' login file; then each finished video uploads with
  its title, description, tags, cover and schedule (private until the scheduled time). Optional in automatic mode.
- **remote access** from your phone: see `docs/REMOTE.md` (Tailscale, always set a password first).
- The app updates itself on start and rolls back if a new version fails its self-test.

Everything is saved in `projects/<name>/`. Tests: `pytest tests`.
