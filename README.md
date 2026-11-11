# soft grind. studio

Local app for the soft grind. YouTube channel: Suno music → playlist → thumbnail → YouTube metadata.

Start it by double-clicking `start-windows.bat` (or `start-mac.command`). It updates itself from GitHub each time, and keeps your keys and projects in `soft-grind-data` in your user folder.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ACEDATACLOUD_API_TOKEN=...   # optional; without it the app runs in mock mode
streamlit run app.py
```

Pages: **videos** (overview tiles, one card per mix with its next step, **review** mode for finished videos; new video step by step, automatic or batch), **planning** (month calendar of
what goes out when, free Mon/Wed/Fri slots, plan an undated video in two clicks), **images** (your picture library),
**settings** (keys, phone messages, password, setup check). Each video has three tabs: **music**, **cover**, **video**.

- **sound quality**: every song is levelled to the same loudness before the mix (then −14 LUFS for the whole video); songs can be removed or reordered on the music tab.
- **YouTube text**: matches the sound (lofi soul / japanese jazz / city pop funk), tags vary per video, and an optional honest line says the music is made with AI tools (settings → youtube and phone).
- **automatic mode** makes the whole video in the background: music, picture, headline, thumbnail, video, text.
- **batch** (new video → batch) makes 2–12 whole videos in one go, two at a time; each gets the next free upload slot. Nothing is uploaded.
- **headlines** come from `soft_grind/headline_list.json` (the owner's 100 headlines, in five groups); the AI only chooses from it.
- **phone messages** (settings): a free ntfy.sh topic pings your phone when a video is done or needs you.
- **credits used** are tracked per video (estimates) and shown on the videos page.
- **free up space** on a finished video deletes its songs and working images and keeps the video, thumbnail and upload text.
- **film dust** (video tab, video settings): faint dust specks like an old print, with a 20-second test before the long render.
- **shorts** (video tab): 1–3 vertical 1080×1920 Shorts per video from different tracks, with a slow zoom (free), your own loop clip (e.g. Midjourney Animate → Loop) or an AI loop (AceDataCloud Veo/Luma, image key), headline, logo, optional film dust. The batch can make them too.
- **upload to YouTube** (settings, youtube card): connect once with a Google Cloud 'Desktop app' login file; then each finished video uploads with
  its title, description, tags, cover and schedule (private until the scheduled time). Optional in automatic mode.
- **remote access** from your phone: see `docs/REMOTE.md` (Tailscale, always set a password first).
- The app updates itself on start and rolls back if a new version fails its self-test.

Everything is saved in `projects/<name>/`. Tests: `pytest tests`.
