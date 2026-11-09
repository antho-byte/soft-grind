# soft grind. studio — project summary (handoff for another Claude chat)

This file summarises a long build conversation. It describes a working app, the tools and APIs behind it, the decisions the owner made,
and the lessons learned. Use it as context for a new or related app. No API keys or tokens are included on purpose.

---

## 1. The owner and the channel

- **Channel:** "soft grind." — a faceless YouTube channel with instrumental city pop / lofi / japanese jazz mixes for working and studying.
  Tagline: *"city pop to work and study to."* Voice: lowercase, warm, calm, never "hustle-bro".
- **Owner:** works from a Windows PC at home (Python 3.15), also checks things from a phone and a work laptop.
  Not a developer: prefers clear, step-by-step instructions, Dutch/English mixed, likes being shown options with a recommendation.
- **Upload rhythm:** Monday / Wednesday / Friday at 15:00 Amsterdam time; videos are ~1 hour (10 songs) or ~2 hours (20 songs).

### Brand
- Colours: night indigo `#141852` (main), coral `#FF7A6B` (always the full stop in the logo), sand `#F6ECDD` (background),
  pool blue `#1466D6`, dusk violet `#5E5EE0`, sunset pink `#FF5F9E`, apricot `#FFC27A`, palm green `#1F7A5A`.
- Fonts: **Abril Fatface** (headings, logo, thumbnail headline), **Inter** (UI/body).
- Logo: the text `soft grind.` with a coral full stop, bottom-left on thumbnails/videos.
- Thumbnail style: one picture, one big lowercase headline at **text size 1.50, top-center**, logo bottom-left. Headlines auto-shrink if too wide.
- The video picture (1920×1080) uses the same design as the thumbnail (headline + logo).
- Titles always **start with the headline**, then a varying phrase, within ~60 characters
  (e.g. `2am clarity. | 80s japanese city pop to work & study to`).

### Headlines (owner's list, now the only source)
- 100 owner-written headlines in five groups: `focus`, `calm`, `night`, `motivation`, `study_work`
  (stored in `soft_grind/headline_list.json`). Examples: "lock in.", "2am clarity.", "the city sleeps, we don't.", "vibe coding.".
- Rules: lowercase, ends with "." or "?", up to 5 words, **never repeated within the last 30 videos**.
  Scene/mood decide which groups come first. The AI only *chooses* from this list (never invents).

---

## 2. What was built

A **local web app** ("soft grind. studio") that turns the whole channel workflow into a few clicks:
Suno music → playlist → thumbnail → video → YouTube text → planning → upload, plus Shorts.

- Repo: GitHub `antho-byte/soft-grind` (public). Branch `main`. CI on every push.
- Runs on the owner's PC; opens in the browser. Started by double-clicking `start-windows.bat` (or `start-mac.command`).
- **Self-updating:** `update.py` pulls the latest version from GitHub on every start, runs a self-test, and rolls back to the
  previous version if the new one fails (remembers a bad version so it is not retried).
- **Data lives outside the app folder** in `~/soft-grind-data` (override with env `SOFTGRIND_HOME`): keys, settings, image library index,
  credits ledger, queues; projects in `projects/<mix-NNN>/` (tracks, images, thumbnail.png, still.png, video.mp4, shorts/, project.json, upload.txt).

### Pages (sidebar menu)
1. **videos** — one card per video with cover, headline, status pill, schedule, and **two buttons**: the *next step*
   (make the music / make the cover / make the video / write the text / upload to YouTube / open in YouTube Studio) and *open video*.
   Filter chips with counts (all / to finish / ready / on youtube / busy), search, "⋯" menu (free up space, move to trash),
   tick-to-select **bulk actions** (upload N to YouTube, make N videos, film dust on/off, trash). Trash with restore.
   "+ new video" menu: step by step / automatic (one whole video) / **batch** (2–12 whole videos).
2. **planning** — month calendar (Mon–Sun) with each planned video on its day (colour = state), dashed "free · 15:00" slots
   on Mon/Wed/Fri, list view, "planned this month" with open buttons, and "not planned yet" with a slot dropdown + plan button.
3. **images** — the owner's image folder (library); the app "looks at" each image (AI description + scenes, or colours only) to match pictures to videos.
4. **settings** — keys, folders, crossfade, phone messages, YouTube connection, password/remote access, setup check, diagnostics.

Inside one video: three tabs as a segmented control — **music**, **cover**, **video**.
- music: sound preset, Suno model, track count/length, scene flavours (fresh mix per new video), background generation, track list/rename.
- cover: pick from library (suggestions), upload, or the photo fixer (vertical → 16:9 via blur or Nano Banana AI); headline buttons
  (new headline / match to image); position/size/nudge; remembers its source picture and layout; "✓ saved" state.
- video: player (quick 90 s preview), make/remake the video, film dust, thumbnail, tracklist; right side **publish** card (upload to YouTube)
  and the YouTube text form (title, description with timestamps, tags, pinned comment, schedule) with autosave + undo;
  **shorts** card (see below).

### Automation
- **Automatic mode:** music → picks an unused library image → headline from the list → thumbnail + still → video → AI-written YouTube text
  → next free slot. Resumable; each step skips work already done (never pays twice).
- **Batch:** creates N videos at once; each gets its own scenes, picture, headline, slot. Music for two videos in parallel,
  video rendering one at a time (thread locks). Optional Shorts per video. **Does not upload** (owner's choice).
- **Queues:** bulk "make videos" and "upload to YouTube" run one after another in background queues.
- **Phone messages:** via ntfy.sh (free app, secret topic name). Batches send only problems + one summary.

### Video
- ffmpeg (bundled via `imageio-ffmpeg`): crossfades between songs, fades, **two-pass loudnorm to −14 LUFS / −1.5 dBTP**, still image at 2 fps,
  h264/AAC 256k, 1920×1080. Timestamps in the description account for the crossfade.
- **Film dust** (owner's chosen look): faint random dust specks only, 12 fps, nothing else (grain/vignette/flicker/scratches were tried and removed).
  Dust is a pre-drawn random texture with a random window per frame (ffmpeg's own `random()` made visible dotted lines — avoid it).

### Shorts
- 1–3 vertical **1080×1920** Shorts per video, each from a different track (starting ~⅓ into it), 15–60 s, headline high up, logo low-center
  (clear of the Shorts UI), audio fades + loudnorm, optional film dust, ready title/description linking to the full mix (#shorts).
- Background motion: **slow zoom** (free), **your own loop clip** (e.g. Midjourney → Animate → Loop), or an **AI loop** (see APIs).
  Optional ping-pong (forwards then backwards) for clips that do not loop by themselves.

### YouTube
- Official **YouTube Data API v3**, OAuth "Desktop app" client with PKCE, implemented with plain `requests` (no Google libraries).
  Resumable upload in 8 MB chunks, thumbnail set, `privacyStatus: private` + `publishAt` for scheduling (Amsterdam time incl. summer time),
  never uploads the same video twice (stores `youtube_id`). Limits: ~6 uploads/day on the default quota; pinned comments cannot be pinned via API;
  unaudited API projects may force uploads to stay private until an audit.
- Owner's Google Cloud project: YouTube Data API enabled, OAuth consent screen External, branding skipped, owner as test user,
  client JSON uploaded in the app's settings, connected.

### Security
- Listens on 127.0.0.1 by default; remote access only with a password (PBKDF2 hash, lockout after 5 tries).
- Keys stored owner-only in the data folder, never in the repo, never in logs (diagnostics scrub secrets).
- Remote use from phone/laptop: guide in `docs/REMOTE.md` (Tailscale).

---

## 3. Tools, libraries and APIs

| What | Used for |
|---|---|
| Python 3.13 (CI) / 3.15 (owner's PC) | app language |
| **Streamlit 1.66.1** (pinned) | the web UI (single `app.py`, custom CSS theme injected from `soft_grind/theme.py`) |
| Pillow, numpy | thumbnails, image work, dust texture |
| requests | all HTTP APIs |
| mutagen | audio durations |
| imageio-ffmpeg (ffmpeg) | video, loudness, Shorts |
| pytest, pyflakes, Streamlit AppTest, Playwright (screenshots) | tests and visual checks |
| GitHub + GitHub Actions | repo, CI on windows-latest + ubuntu-latest |
| **AceDataCloud** (`https://api.acedata.cloud`, Bearer key) | one provider for: **Suno** music (`/suno/audios`, `/suno/tasks`, 2 songs per request), **Nano Banana** image edits (`/nano-banana/images`), **chat** (`/v1/chat/completions`, OpenAI-compatible, owner uses Claude Haiku) for headlines/texts/prompt improvement/image analysis, **video** models (`/veo/videos`, `/luma/videos`, also Wan/Sora) for AI loops |
| AceDataCloud file upload | `POST https://platform.acedata.cloud/api/v1/files/` (multipart field `file`, **platform token**) → `file_url` on cdn.acedata.cloud; the video models want the picture as a link |
| YouTube Data API v3 + Google OAuth | uploads |
| ntfy.sh | phone notifications |
| Midjourney (owner, manual) | images (prompts given for the brand palette, empty sky at the top for the headline) and loop clips (Animate → Loop) |
| Pinterest (owner's earlier workflow) | vertical images — **copyright risk**, prefer own/generated/licensed images |

### Prices the owner gave / we used
- AceDataCloud top-up: €15 ≈ 100 credits. Suno ≈ 0.14 credits per song (0.28 per request of 2 songs). Image edit ≈ 0.20 credits.
- One 1-hour video ≈ 1.4 credits of music + a few cents of AI text → ~65–70 videos per 100 credits.
- Veo 3.1 fast ≈ $0.11 per clip, Veo 2 fast ≈ $0.07 (from AceDataCloud docs, unverified).

---

## 4. How the code is organised (`soft_grind/`)

`app.py` (UI, one file, pages chosen by `st.session_state["step"]`) plus modules:
`projects` (data, job files, queues, batch, trash, credits ledger), `auto` (whole-video pipeline), `batch`, `queue`, `worker` (music),
`render` (video job), `video` (ffmpeg, film dust), `shorts`, `animate` (AI loops), `thumbnail`, `headlines` + `headline_list.json`,
`library` + `library_worker` (image folder analysis), `imagegen` (Nano Banana), `ai` (chat), `texts` (YouTube text, uniqueness checks),
`metadata`, `names` (song titles), `playlist`, `planning`, `youtube` + `youtube_worker`, `notify`, `errors` (plain-language errors),
`health` (setup check, diagnostics), `security`, `settings`, `net` (friendly network errors, safe retries), `theme`, `brand`, `fixes`.

Patterns worth reusing:
- **Background jobs as detached processes** (`python -m soft_grind.<module> <jobfile>`), each writing a JSON job file
  with `state / progress / message / updated`; the UI polls with `st.fragment(run_every=…)`; a heartbeat + 120 s "stale" rule
  turns dead jobs into "interrupted" with a continue button.
- Atomic JSON writes (with a Windows `PermissionError` retry) and a small lock file for shared files.
- Every paid step is resumable and never repeats a paid request.
- Every error is shown in plain language with advice, with the raw text under "technical details".
- Streamlit tips: keyed containers (`st.key-…`) for CSS; per-project widget keys with a version counter; `st.popover` instead of dialogs
  (testable with AppTest); popovers render outside `.stApp`, so they need their own CSS.

---

## 5. Working agreements and lessons learned

- **Never push unless all tests pass** — check the pytest exit code, not just the tail of the output (this went wrong twice).
- Never write the owner's API keys into files, tests or commits; tests use fake keys. The owner once pasted a key in chat:
  they were told to rotate it and never paste keys in chat.
- Check visuals with real screenshots (desktop 1440 px and phone 390 px) after UI changes; several bugs were only visible there
  (inverted tabs, invisible button text, colour casts from ffmpeg blends, dotted-line dust).
- ffmpeg gotchas: blend only the luma plane for overlays (`c0_mode=screen … c1_expr=A:c2_expr=A`), and map video-range black (16) to 0
  before screen-blending; `crop` uses `n` (lowercase) for the frame number, `geq` uses `N`.
- The owner likes: one clear recommendation, cleaner/Apple-like UI (solid indigo primary button, hairline secondary, segmented controls),
  automation with a human check before publishing.

---

## 6. Open items / where things stand

- **AI loops for Shorts:** first try gave `HTTP 502 all_channels_failed` from `/veo/videos` (picture was sent embedded as base64).
  Fix shipped: upload the picture first with a **platform token** and send the link. Owner still has to create the platform token and retry.
  Unknowns: whether that token is the one `/files/` accepts, and whether uploads cost credits.
- **Soundbar overlay — on hold** (owner's request): a 15-minute green-screen soundbar clip looped bottom-right of the video.
  When resumed, ask for a ~10 s sample, the clip path, size/position, and whether it applies to every video or per video.
- Not built yet (ideas): bulk "write the text" / "new headline" for many videos, YouTube upload of Shorts, drag-and-drop on the calendar.
- YouTube risk notes given to the owner: the API upload itself is fine; real risks are copyright strikes (images, especially Pinterest),
  music rights (check Suno/AceDataCloud commercial terms), YPP "inauthentic/mass-produced content" (keep real variety), and AI-content disclosure.
