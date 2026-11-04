"""soft grind. studio: Suno music -> playlist -> thumbnail -> YouTube metadata."""
import io
import json
import os
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

from soft_grind import brand, imagegen, metadata, names, playlist, settings, theme, thumbnail as T
from soft_grind.suno import SunoClient, SunoError, download

st.set_page_config(page_title="soft grind. studio", page_icon="🌴", layout="wide")
theme.inject()
PROJECTS = settings.projects_dir()
SAVED = settings.load_keys()

STEPS = ["music", "playlist", "fix images", "thumbnail", "youtube"]
TITLES = {
    "music": ("make the music.", "pick a sound, press generate, get instrumental tracks."),
    "playlist": ("the playlist.", "pull in your tracks, check the titles and the order."),
    "fix images": ("fix the photos.", "turn vertical photos into 16:9."),
    "thumbnail": ("the cover.", "one image, one quote, one logo."),
    "youtube": ("the upload.", "title, description, tags and a pinned comment."),
}
st.session_state.setdefault("step", "music")


def go(step_name):
    st.session_state["step"] = step_name


def sticky(widget, label, key, default, **kw):
    """A widget that remembers its value when you leave this step and come back."""
    val = widget(label, value=st.session_state.get("_s_" + key, default), key="w_" + key, **kw)
    st.session_state["_s_" + key] = val
    return val


# ---------------- sidebar: logo, project, progress rail, settings ----------------
with st.sidebar:
    st.markdown(theme.logo_html(), unsafe_allow_html=True)
    st.markdown('<div class="sg-tag">city pop to work and study to.</div>', unsafe_allow_html=True)
    name = st.text_input("project name", st.session_state.get("project", "mix-001"))
    st.session_state["project"] = name
    pdir = PROJECTS / (playlist.safe_name(name).replace(" ", "-") or "mix")
    tracks_dir = pdir / "tracks"; tracks_dir.mkdir(parents=True, exist_ok=True)
    rail_slot = st.container(key="rail")  # filled at the end, so it shows fresh status
    with st.expander("keys and settings"):
        st.caption("suno (AceDataCloud)")
        token = st.text_input("API token", os.getenv("ACEDATACLOUD_API_TOKEN") or SAVED.get("suno", ""), type="password",
                              help="platform.acedata.cloud → Applications. Generation costs credits.")
        mock = st.checkbox("mock mode (no API, fake short tones)", value=not token)
        st.caption("image tool (AceDataCloud)")
        img_token = st.text_input("image API token", os.getenv("ACEDATACLOUD_IMAGE_TOKEN") or SAVED.get("image", ""), type="password",
                                  help="A separate key (own budget cap) for the Nano Banana image models.")
        img_mock = st.checkbox("image mock mode (no API, free)", value=not img_token)
        if st.button("save keys on this computer"):
            settings.save_keys(token, img_token)
            st.success("saved: you won't need to paste them again")
        crossfade = st.number_input("crossfade (s)", 0.0, 10.0, metadata.CROSSFADE, 0.5)
        st.caption("where your projects are saved")
        folder_in = st.text_input("projects folder", str(PROJECTS),
                                  help="Tracks, thumbnails and upload.txt of every project. Choosing the app's own folder uses its “projects” subfolder.")
        if st.button("use this folder"):
            newp = settings.save_projects_dir(folder_in)
            st.session_state["tracks"] = []
            st.toast(f"projects now live in {newp}")
            st.rerun()
        old_dir = settings.DEFAULT_PROJECTS
        if old_dir.is_dir() and old_dir.resolve() != PROJECTS.resolve() and any(p.is_dir() for p in old_dir.iterdir()):
            st.caption(f"projects found in the old folder: `{old_dir}`")
            if st.button("move my existing projects here"):
                moved, skipped = settings.move_projects(old_dir, PROJECTS)
                st.session_state["tracks"] = []
                if moved:
                    st.success("moved: " + ", ".join(moved))
                if skipped:
                    st.warning("left in place (already has files in the new folder): " + ", ".join(skipped))
        st.caption(f"your keys live in `{settings.DATA_DIR}`, outside the app folder")

st.session_state.setdefault("tracks", [])
if st.session_state.pop("_reload", False) or (not st.session_state["tracks"] and tracks_dir.exists()):
    existing = [p for p in tracks_dir.iterdir() if p.suffix.lower() in playlist.AUDIO_EXT]
    if existing:
        st.session_state["tracks"] = playlist.tracks_from_folder(tracks_dir)
tracks = st.session_state["tracks"]
imgs_dir = pdir / "images"

step = st.session_state["step"]
theme.page_title(f"{name} / {step}", *TITLES[step])

if step == "music":
    with st.container(key="card_music"):
            c1, c2 = st.columns(2)
            preset = c1.selectbox("sound", list(brand.PRESETS))
            model = c2.selectbox("model", brand.MODELS)
            style = st.text_area("style prompt (no artist names, suno blocks them)", brand.PRESETS[preset], height=90)
            c1, c2, c3 = st.columns(3)
            n_tracks = c1.slider("tracks wanted", 2, 20, 8, 2, help="each request returns 2 tracks")
            minutes = c2.slider("target length (min)", 2.0, 6.0, 6.0, 0.5, help="API duration cap is 360 s")
            scenes = c3.multiselect("scene flavours (rotated)", brand.SCENES, brand.SCENES[:6])
            n_req = n_tracks // 2
            mood_key = "groovy" if "groovy" in preset else "calm"
            st.info(f"{n_req} requests → {n_req * 2} tracks. Suno's own download cap (Pro 20/mo, Premier 60/mo) "
                    "does not apply to the API, but AceDataCloud charges per request." if not mock else
                    "mock mode: creates short test tones so you can try the rest of the app for free.")
            name_style = st.selectbox("track names", names.STYLES, help="mix = english and romanised japanese, e.g. “drizzle study” and “mado no ame”")
            if st.button("generate", type="primary", disabled=not (mock or token)):
                client = SunoClient(token, mock=mock, mock_dir=pdir)
                bar, status = st.progress(0.0), st.empty()
                added = list(tracks)
                try:
                    for i in range(n_req):
                        scene = scenes[i % len(scenes)] if scenes else "soft grind"
                        status.write(f"request {i + 1}/{n_req}: “{scene}”")
                        tid = client.generate(f"{style}, {scene}", scene, model, int(minutes * 60), brand.NEGATIVE_TAGS)
                        clips = client.wait(tid, on_tick=lambda s: status.write(
                            f"request {i + 1}/{n_req}: “{scene}” … {int(s)}s"))
                        for j, c in enumerate(clips, 1):
                            k = len(added) + 1
                            title = names.suggest([scene], 1, {t["title"] for t in added}, mood_key, style=name_style)[0]
                            p = download(c["audio_url"], tracks_dir / f"{k:02d} - {playlist.safe_name(title)}.mp3"
                                         if not c["audio_url"].endswith(".wav") else
                                         tracks_dir / f"{k:02d} - {playlist.safe_name(title)}.wav")
                            added.append({"id": c["id"], "title": title, "path": str(p),
                                          "duration": playlist.audio_duration(p) or c["duration"]})
                        bar.progress((i + 1) / n_req)
                    st.session_state["tracks"] = added
                    status.success(f"done: {len(added)} tracks in the project. Review them in the playlist step.")
                except SunoError as e:
                    status.error(f"suno error: {e}")
                    st.session_state["tracks"] = added

if step == "playlist":
    with st.container(key="card_playlist"):
            st.caption("Replaces the usesuno.com step: paste your published playlist, or import a folder you already downloaded.")
            src = st.radio("get tracks from", ["suno playlist link", "song links", "local folder"], horizontal=True)
            try:
                if src == "suno playlist link":
                    url = st.text_input("published playlist url (suno.com/playlist/…)")
                    if st.button("fetch playlist", disabled=not url):
                        with st.spinner("reading playlist…"):
                            pname, found = playlist.fetch_playlist(url)
                        bar = st.progress(0.0)
                        st.session_state["tracks"] = playlist.download_tracks(found, tracks_dir, lambda f, t: bar.progress(f, t))
                        st.success(f"“{pname}”: {len(found)} tracks")
                elif src == "song links":
                    links = st.text_area("one suno.com/song/… link per line")
                    if st.button("download songs", disabled=not links):
                        found = playlist.tracks_from_song_links(links)
                        bar = st.progress(0.0)
                        st.session_state["tracks"] = playlist.download_tracks(found, tracks_dir, lambda f, t: bar.progress(f, t))
                else:
                    folder = st.text_input("folder with downloaded tracks")
                    if st.button("import folder", disabled=not folder):
                        st.session_state["tracks"] = playlist.tracks_from_folder(folder)
            except Exception as e:
                st.error(f"{e}")
            tracks = st.session_state["tracks"]
            if tracks:
                nv = st.session_state.get("names_v", 0)
                with st.expander("give every track a new name"):
                    n1, n2, n3 = st.columns([3, 1, 1])
                    topic = n1.multiselect("playlist topic: the names are based on these scenes", brand.SCENES,
                                           st.session_state.get("_names_scenes", brand.SCENES[:4]), key=f"w_names_scenes{nv}")
                    st.session_state["_names_scenes"] = topic
                    nmood = n2.selectbox("mood", ["calm", "groovy"])
                    nstyle = n3.selectbox("style", names.STYLES)
                    if st.button("suggest new names for all tracks"):
                        new = names.suggest(topic, len(tracks), (), nmood, style=nstyle)
                        for t, nm in zip(tracks, new):
                            t["title"] = nm
                        playlist.rename_files(tracks, tracks_dir)
                        st.session_state["names_v"] = nv + 1
                        st.rerun()
                    st.caption("Every click gives a fresh set. You can still edit any name by hand below.")
                st.write(f"**{len(tracks)} tracks · {metadata.length_phrase(metadata.total_length([t['duration'] for t in tracks], crossfade))}**")
                for i, t in enumerate(tracks):
                    a, b, c, d = st.columns([0.07, 0.45, 0.1, 0.38])
                    a.write(f"{i + 1:02d}")
                    t["title"] = b.text_input("title", t["title"], key=f"t{st.session_state.get('names_v', 0)}_{i}{t.get('id')}", label_visibility="collapsed").lower()
                    c.write(metadata.fmt_ts(t["duration"]))
                    d.audio(t["path"])
                if st.button("remove all tracks from this view"):
                    st.session_state["tracks"] = []; st.rerun()
                if st.button("save these titles to the files"):
                    playlist.rename_files(tracks, tracks_dir)
                    st.success("saved: the titles are kept in the file names")
                st.caption("Track titles here feed the tracklist; edit them freely. Order = playback order.")

if step == "fix images":
    with st.container(key="card_fix_images"):
            st.caption("Drop in your photos. The free option fills the sides with a blurred copy; the AI option "
                       "extends the scene (like your Gemini step). Pick the ones you like and they show up in the thumbnail step.")
            st.warning("Only use photos you have the rights to (your own, licensed, or AI-generated). "
                       "Pinterest photos usually belong to someone else. Check each result for garbled text, "
                       "signatures or logos.")
            if img_mock:
                st.info("image mock mode is ON: the AI results are fake (just a colour-boosted blur). "
                        "Paste your image API token under “keys and settings” in the sidebar and untick “image mock mode” to use the real models.")
            ups = st.file_uploader("photos", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="fix_up")
            c1, c2 = st.columns(2)
            use_blur = c1.checkbox("free blur fill", True)
            models = c2.multiselect("AI models to compare", list(imagegen.MODELS), ["nano-banana-2.1"])
            resolution = st.select_slider("AI output size", ["1K", "2K", "4K"], "2K",
                                          help="2K is about 2048px wide, enough for your 1920px rule. "
                                               "nano-banana (the plain one) only does 1K. Bigger sizes may cost more.")
            prompt = st.text_area("AI instruction", imagegen.DEFAULT_PROMPT, height=110)
            templates = {}
            with st.expander("advanced: the exact request sent to the AI (edit if you get an error)"):
                st.caption("{image}, {prompt} and {model} are filled in automatically. Keys are named per the "
                           "AceDataCloud Nano Banana docs; if the API complains about a field, change it here.")
                for m in models:
                    ep0, tpl0, _, _ = imagegen.MODELS[m]
                    ep = st.text_input(f"{m}: endpoint", ep0, key=f"ep_{m}")
                    body = st.text_area(f"{m}: request (JSON)", json.dumps(tpl0, indent=2), height=170, key=f"tpl_{m}")
                    templates[m] = (ep, body)
            if ups and models:
                cost = sum(imagegen.MODELS[m][2] for m in models) * len(ups)
                st.info(f"{len(ups)} photos × {len(models)} models = {len(ups) * len(models)} AI calls ≈ ${cost:.2f} "
                        "at the cheapest top-up tier (your real price per credit is probably higher).")
            st.session_state.setdefault("fix_results", {})
            if ups and st.button("make 16:9 versions", type="primary"):
                imgs_dir.mkdir(parents=True, exist_ok=True)
                client = imagegen.ImageClient(img_token, mock=img_mock)
                results, prog = {}, st.progress(0.0); total = len(ups) * (len(models) + int(use_blur)); done = 0
                for f in ups:
                    src = Image.open(f); src.load(); src = src.convert("RGB")
                    stem = Path(f.name).stem
                    src.save(imgs_dir / f"{stem}_source.png")
                    canvas = imagegen.blur_fill(src)
                    row = {"source": src, "outs": {}}
                    if use_blur:
                        row["outs"]["blur fill"] = (canvas, ""); done += 1; prog.progress(done / total)
                    for m in models:
                        try:
                            ep, body = templates[m]
                            out = client.edit(ep, json.loads(body), m, canvas, prompt, resolution)
                            row["outs"][m] = imagegen.finish_16x9(out)
                        except json.JSONDecodeError as e:
                            row["outs"][m] = (None, f"request JSON is invalid: {e}")
                        except Exception as e:
                            row["outs"][m] = (None, str(e))
                        done += 1; prog.progress(done / total)
                    results[stem] = row
                st.session_state["fix_results"] = results
            for stem, row in st.session_state["fix_results"].items():
                st.markdown(f"**{stem}**")
                cols = st.columns(1 + len(row["outs"]))
                cols[0].image(row["source"], caption="original")
                for col, (label, (img, note)) in zip(cols[1:], row["outs"].items()):
                    with col:
                        if img is None:
                            st.error(f"{label}: {note}")
                        else:
                            st.image(img, caption=f"{label} {note}".strip())
                            if st.button("use this", key=f"use_{stem}_{label}"):
                                imgs_dir.mkdir(parents=True, exist_ok=True)
                                out_path = imgs_dir / f"{stem}_16x9.png"; img.save(out_path)
                                st.success(f"saved {out_path.name}: now pick it in the thumbnail step")

if step == "thumbnail":
    with st.container(key="card_source"):
        c1, c2 = st.columns(2)
        up = c1.file_uploader("image (16:9, ≥1920px, no text in the image)", type=["png", "jpg", "jpeg", "webp"])
        fixed = sorted(p.name for p in imgs_dir.glob("*_16x9.png")) if imgs_dir.exists() else []
        pick = c2.selectbox("…or pick an image you made 16:9 in the fix images step", ["—"] + fixed)
    src_img, src_name = None, ""
    if up:
        st.session_state["cover"] = (up.name, up.getvalue())
        src_name, src_img = up.name, Image.open(io.BytesIO(up.getvalue()))
    elif pick != "—":
        src_name, src_img = pick, Image.open(imgs_dir / pick)
    elif st.session_state.get("cover"):
        src_name, data = st.session_state["cover"]; src_img = Image.open(io.BytesIO(data))
    if src_img is None:
        st.info("Add an image above, or make one 16:9 in the fix images step.")
    else:
        src_img.load()
        for w in T.image_warnings(src_img): st.warning(w)
        st.caption(f"using {src_name}. Check the image for garbled Japanese, signatures, brand logos, number plates; "
                   "if it looks like a Hiroshi Nagai painting, do a reverse image search.")
        prev = st.container(key="card_preview")          # shown first, filled once the settings are known
        with st.container(key="card_settings"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                quote = sticky(st.text_input, "quote", "quote", "you've got this.")
                for w in T.check_quote(quote): st.caption(f":orange[{w}]")
                subline = sticky(st.text_input, "subline (optional)", "subline", "")
            with c2:
                cyber = sticky(st.toggle, "night city style", "cyber", False)
                tag = st.text_input("tag box", "CYBERPUNK SYNTHWAVE", disabled=not cyber)
                logo = st.selectbox("logo colour", ["auto", "navy", "white"])
            with c3:
                auto = T.suggest_anchor(src_img, quote)
                anchor = st.selectbox("position", T.ANCHORS, T.ANCHORS.index(auto), help=f"calmest area: {auto}")
                size = sticky(st.slider, "text size", "size", 0.9, min_value=0.5, max_value=1.6, step=0.05)
            with c4:
                dx = st.slider("nudge x", -300, 300, 0, 5)
                dy = st.slider("nudge y", -300, 300, 0, 5)
        thumb = T.render_thumbnail(src_img, quote, T.Layout(anchor, size, dx, dy), cyber, tag, subline, logo_mode=logo)
        still = T.render_still(src_img, cyber, logo_mode=logo)
        with prev:
            a, b = st.columns([1.55, 1])
            a.image(thumb, caption="thumbnail · 1280×720")
            b.image(still, caption="still · 1920×1080 · no quote")
            zbuf = io.BytesIO()
            with zipfile.ZipFile(zbuf, "w") as z:
                for nm, pic in (("thumbnail.png", thumb), ("still.png", still)):
                    pb = io.BytesIO(); pic.save(pb, "PNG"); z.writestr(nm, pb.getvalue())
            b1, b2, _ = st.columns([1, 1, 2])
            if b1.button("save to project", type="primary"):
                pdir.mkdir(parents=True, exist_ok=True)
                thumb.save(pdir / "thumbnail.png"); still.save(pdir / "still.png")
                st.success(f"saved thumbnail.png + still.png in {pdir}")
            b2.download_button("download both", zbuf.getvalue(), "softgrind_cover.zip", "application/zip")
    with st.expander("bulk: many images at once (thumbnails + stills + contact sheet)"):
        bq = st.text_area("quotes, one per line (matched to images in name order; last one repeats)", "you've got this.")
        files = st.file_uploader("images", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="bulk")
        if files and st.button("render all"):
            qs = [q.strip() for q in bq.splitlines() if q.strip()] or ["soft grind."]
            zbuf, sheet_items = io.BytesIO(), []
            with zipfile.ZipFile(zbuf, "w") as z:
                for i, f in enumerate(sorted(files, key=lambda f: f.name)):
                    im = Image.open(f); q = qs[min(i, len(qs) - 1)]
                    th = T.render_thumbnail(im, q, T.Layout(T.suggest_anchor(im, q), 0.9)); stl = T.render_still(im)
                    stem = Path(f.name).stem
                    for nm, pic in ((f"{stem}_thumbnail.png", th), (f"{stem}_still.png", stl)):
                        b = io.BytesIO(); pic.save(b, "PNG"); z.writestr(nm, b.getvalue())
                    sheet_items.append(th)
                cols = 3; tw, thh = 640, 360
                rows = (len(sheet_items) + cols - 1) // cols
                sheet = Image.new("RGB", (cols * tw, rows * thh), (20, 24, 82))
                for i, th in enumerate(sheet_items):
                    sheet.paste(th.resize((tw, thh)), ((i % cols) * tw, (i // cols) * thh))
                b = io.BytesIO(); sheet.save(b, "PNG"); z.writestr("contact_sheet.png", b.getvalue())
            st.image(sheet, caption="contact sheet")
            st.download_button("download zip", zbuf.getvalue(), "softgrind_bulk.zip", "application/zip")

if step == "youtube":
    with st.container(key="card_youtube"):
            if len(tracks) < 3:
                st.warning("Add at least 3 tracks (music or playlist step): the tracklist needs real durations for chapters.")
            c1, c2 = st.columns(2)
            with c1:
                quote_m = sticky(st.text_input, "quote", "quote", "you've got this.")
                subline_m = st.text_input("subline", "one more hour, then rest.")
                tstyle = st.radio("title format", ["quote", "playlist"], horizontal=True,
                                  format_func=lambda s: "[quote] | 80s japanese city pop to work & study to"
                                  if s == "quote" else "[playlist] you're [scenario] [emoji] 80s city pop")
                pl = st.text_input("playlist name", "night desk", disabled=tstyle == "quote")
                sc = st.text_input("scenario", "studying at 2am", disabled=tstyle == "quote")
                emoji = st.text_input("emoji", "🌴", disabled=tstyle == "quote")
            with c2:
                scene = st.text_area("scene + mood (2–3 sentences)", "a quiet desk, a warm lamp and the city glowing outside. "
                                     "slow, soft grooves that keep you company while you work.", height=110)
                use = st.text_input("for…", "working and studying")
                artist = st.selectbox("inspired by (title/description only)", brand.ARTISTS,
                                      index=len(tracks) % len(brand.ARTISTS))
                mood = st.selectbox("mood hashtag", list(brand.MOODS))
                question = st.selectbox("question to viewers", brand.DESCRIPTION_QUESTIONS)
                pinned = st.selectbox("pinned comment", brand.PINNED_COMMENTS)
            title = metadata.make_title(tstyle, quote_m, pl, sc, emoji)
            desc = metadata.make_description(quote_m, subline_m, scene, tracks, use, artist, question,
                                             brand.MOODS[mood], crossfade) if tracks else ""
            tags = metadata.make_tags()
            sig = abs(hash((title, desc, tuple(tags), pinned)))  # refresh fields when inputs change, keep manual edits otherwise
            st.text_input("title", title, key=f"title_out{sig}")
            st.caption(f"{len(title)} chars")
            st.text_area("description (editable)", desc, height=420, key=f"desc_out{sig}")
            st.text_area("tags", ", ".join(tags), height=70, key=f"tags_out{sig}")
            st.text_input("pinned comment", pinned, key=f"pin_out{sig}")
            for issue in metadata.validate(title, tracks, pinned): st.warning(issue)
            st.markdown("**copy:** use the copy icon on code blocks below")
            for lbl, val in (("title", st.session_state[f"title_out{sig}"]), ("description", st.session_state[f"desc_out{sig}"]),
                             ("tags", st.session_state[f"tags_out{sig}"]), ("pinned comment", st.session_state[f"pin_out{sig}"])):
                st.caption(lbl); st.code(val, language=None)
            txt = metadata.upload_txt(title, st.session_state[f"desc_out{sig}"], tags, st.session_state[f"pin_out{sig}"])
            cA, cB = st.columns(2)
            if cA.button("save upload.txt"):
                (pdir / "upload.txt").write_text(txt, encoding="utf-8"); st.success(f"saved {pdir / 'upload.txt'}")
            cB.download_button("download upload.txt", txt, "upload.txt")
            st.caption("Upload as private/scheduled · Mon/Wed/Fri 15:00 Amsterdam · channel guidelines: "
                       + " / ".join(brand.CHANNEL_GUIDELINES))

# ---------------- progress rail (left), filled last so it shows fresh status ----------------
tracks = st.session_state["tracks"]
n = len(tracks)
mins = round(metadata.total_length([t["duration"] for t in tracks], crossfade) / 60)
fixed_n = len(list(imgs_dir.glob("*_16x9.png"))) if imgs_dir.exists() else 0
cover_done = (pdir / "thumbnail.png").exists()
yt_done = (pdir / "upload.txt").exists()
RAIL = {
    "music": (n > 0, f"{n} tracks · {mins} min" if n else "no tracks yet"),
    "playlist": (n > 0, "titles ready" if n else "after the music"),
    "fix images": (fixed_n > 0, f"{fixed_n} made 16:9" if fixed_n else "optional"),
    "thumbnail": (cover_done, "saved" if cover_done else ("in progress" if step == "thumbnail" else "not made yet")),
    "youtube": (yt_done, "upload.txt saved" if yt_done else "title, description, tags"),
}
with rail_slot:
    for i, s in enumerate(STEPS, 1):
        done, sub = RAIL[s]
        st.button(f"{'✓' if done else i}   {s}", key=f"step_{s}", use_container_width=True,
                  type="primary" if s == step else "secondary", on_click=go, args=(s,))
        st.markdown(f'<div class="sg-step-sub{" done" if done else ""}">{sub}</div>', unsafe_allow_html=True)
