"""soft grind. studio: Suno music -> playlist -> thumbnail -> YouTube metadata."""
import io
import json
import os
import random
import time
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

from soft_grind import ai, brand, headlines, imagegen, library, metadata, names, playlist, projects, settings, theme, thumbnail as T

st.set_page_config(page_title="soft grind. studio", page_icon="🌴", layout="wide")
theme.inject()
PROJECTS = settings.projects_dir()
SAVED = settings.load_keys()

STEPS = ["projects", "music", "playlist", "library", "fix images", "thumbnail", "video"]
TITLES = {
    "projects": ("your videos.", "every video you made, with its cover. open one to keep going."),
    "music": ("make the music.", "pick a sound, press generate, get instrumental tracks."),
    "playlist": ("the playlist.", "pull in your tracks, check the titles and the order."),
    "library": ("the images.", "your folder of images: let the app look at them, then match them to your videos."),
    "fix images": ("fix the photos.", "turn vertical photos into 16:9."),
    "thumbnail": ("the cover.", "one image, one quote, one logo."),
    "video": ("the video.", "watch it, check the words, pick a day to publish."),
}
st.session_state.setdefault("step", "projects")


def go(step_name):
    st.session_state["step"] = step_name


def sticky(widget, label, key, default, **kw):
    """A widget that remembers its value when you leave this step and come back (separately for each project)."""
    proj = st.session_state.get("project", "")
    sk = f"_s_{proj}_{key}"
    ver = st.session_state.get(f"_sv_{proj}", 0)             # bumped when code (not you) sets a value, e.g. a new headline
    val = widget(label, value=st.session_state.get(sk, default), key=f"w_{proj}_{key}_{ver}", **kw)
    st.session_state[sk] = val
    return val


def new_video():
    """A fresh project: next free name, a new unique playlist name, nothing carried over from the last video."""
    nm = projects.next_project_name(PROJECTS)
    pd = PROJECTS / nm
    pd.mkdir(parents=True, exist_ok=True)
    taken = [p["playlist_name"] for p in projects.list_projects(PROJECTS)]
    playlist_name = names.suggest([random.choice(brand.SCENES)], 1, taken, "calm")[0]
    projects.set_meta(pd, created=time.time(), playlist_name=playlist_name, scenario=random.choice(brand.SCENARIOS))
    st.session_state.update(project=nm, step="music", tracks=[], fix_results={})
    for k in ("_style_before", "_ai_note", "_job_was_running"):
        st.session_state.pop(k, None)


def open_project(nm, stage_name):
    st.session_state.update(project=nm, tracks=[], fix_results={}, step={
        "new": "music", "making music": "music", "needs a thumbnail": "thumbnail", "needs the video": "video",
        "making the video": "video", "needs youtube text": "video", "ready": "video"}.get(stage_name, "music"))
    st.session_state.pop("_job_was_running", None)


def used_quotes(exclude=""):
    return {p["quote"] for p in projects.list_projects(PROJECTS) if p["quote"] and p["name"] != exclude}


def set_headline(h):
    st.session_state[f"_s_{name}_quote"] = h
    st.session_state[f"_sv_{name}"] = st.session_state.get(f"_sv_{name}", 0) + 1
    projects.set_meta(pdir, quote=h)


def make_headline(analysis, mood, topic, use_ai=True):
    """A headline that fits the image: AI if a key is set, otherwise the built-in pools. Never one already used."""
    used = used_quotes(name) | {projects.meta(pdir).get("quote", "")}       # also not the one this video has now
    scenes = [s for s in analysis.get("scenes", []) if s in topic] or analysis.get("scenes", []) or list(topic)[:2]
    if use_ai and ai_token and not ai_mock:
        try:
            opts, cost = ai.AIClient(ai_token, ai_model).suggest_headlines(analysis.get("description", ""), mood, scenes, used)
            if opts:
                st.session_state["_ai_spent"] = st.session_state.get("_ai_spent", 0.0) + cost
                return opts[0]
        except ai.AIError:
            pass
    return headlines.suggest(mood, scenes, used, 1)[0]


def assign_image(path, analysis, mood, topic):
    """Use a library image for this video: 16:9 copy in the project, a matching headline, cover for the thumbnail step."""
    dest = library.prepare_for_project(Path(path), pdir)
    set_headline(make_headline(analysis, mood, topic))
    st.session_state["cover"] = (dest.name, dest.read_bytes())
    st.session_state.pop(f"_sugg_{name}", None)


def library_panel():
    def body():
        js = library.library_job_status()
        was = st.session_state.get("_lib_was_running", False)
        if js["running"]:
            st.session_state["_lib_was_running"] = True
            st.progress(js["progress"], text=f"{js['message']}")
            return
        if was:
            st.session_state["_lib_was_running"] = False
            st.rerun()
        if js["state"] == "done" and js["total"]:
            st.success(f"looked at {js['total']} images" + (f" · {js['spent']:.3f} credits" if js.get("spent") else ""))
        elif js["state"] == "failed":
            st.error(f"stopped: {js['error']}")
        elif js["state"] == "interrupted":
            st.warning("Looking at the images stopped unexpectedly. Press the button again: finished images are kept.")
    st.fragment(run_every=3 if library.library_job_status()["running"] else None)(body)()


def render_panel(pdir_):
    """Live progress of the background video render."""
    def body():
        rs = projects.render_status(pdir_)
        was = st.session_state.get("_render_was_running") == pdir_.name
        if rs["running"]:
            st.session_state["_render_was_running"] = pdir_.name
            st.progress(rs["progress"], text=f"{rs['message']} · {int(rs['progress'] * 100)}%")
            st.caption("This runs in the background. You can leave this page; keep the black window open.")
            return
        if was:
            st.session_state.pop("_render_was_running", None)
            st.rerun()
        if rs["state"] == "failed":
            st.error(f"The video could not be made: {rs['error']}")
        elif rs["state"] == "interrupted":
            st.warning("The video job stopped unexpectedly (window closed or computer asleep). Press make the video again.")
    st.fragment(run_every=3 if projects.render_status(pdir_)["running"] else None)(body)()


def job_panel(pdir_):
    """Live progress of the background music job. Refreshes itself while the job runs."""
    def body():
        job = projects.job_status(pdir_)
        was = st.session_state.get("_job_was_running") == pdir_.name
        if job["running"]:
            st.session_state["_job_was_running"] = pdir_.name
            st.progress(job["progress"], text=f"{job['done']} of {job['total']} requests · {job['message']}")
            st.button("cancel", key="cancel_job", on_click=projects.cancel_job, args=(pdir_,))
            return
        if was:                                     # it just finished: refresh the whole page once (rail, track list)
            st.session_state.pop("_job_was_running", None)
            st.rerun()
        if job["state"] == "done":
            st.success("done: the tracks are in this project. Open the playlist step to check the names.")
        elif job["state"] == "failed":
            st.error(f"stopped: {job['error'] or 'unknown error'}. Tracks made so far are saved"
                     + (f" ({len(job['task_ids'])} requests were started)." if job["task_ids"] else "."))
        elif job["state"] == "cancelled":
            st.info("cancelled. Tracks made so far are saved.")
        elif job["state"] == "interrupted":
            st.warning("The job stopped unexpectedly (the black window was closed, or the computer went to sleep). "
                       "Tracks made so far are saved.")
    st.fragment(run_every=3 if projects.job_status(pdir_)["running"] else None)(body)()


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
        st.caption("AI helper (AceDataCloud chat)")
        ai_token = st.text_input("AI helper token", os.getenv("ACEDATACLOUD_AI_TOKEN") or SAVED.get("ai", ""), type="password",
                                 help="Its own key with its own usage limit. Used for the “improve with AI” buttons.")
        ai_model = st.text_input("AI model", SAVED.get("ai_model") or ai.DEFAULT_MODEL,
                                 help="Exact model name from the Chat tab at platform.acedata.cloud/models, e.g. a Claude Haiku.")
        ai_mock = st.checkbox("AI mock mode (no API, free)", value=not ai_token)
        if st.button("save keys on this computer"):
            settings.save_keys(token, img_token, ai_token, ai_model)
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
_files = projects.audio_files(tracks_dir)
_inside = all(Path(t["path"]).parent.resolve() == tracks_dir.resolve() for t in st.session_state["tracks"])  # not an imported folder
if st.session_state.pop("_reload", False) or (_inside and len(_files) != len(st.session_state["tracks"])):
    st.session_state["tracks"] = playlist.tracks_from_folder(tracks_dir) if _files else []
tracks = st.session_state["tracks"]
imgs_dir = pdir / "images"

step = st.session_state["step"]
theme.page_title("all videos" if step == "projects" else (f"videos › {name}" if step == "video" else f"{name} / {step}"), *TITLES[step])

if step == "projects":
    h1, h2 = st.columns([4, 1])
    h2.button("new video", type="primary", on_click=new_video, width="stretch")
    PILL = {"making music": "#E7E5FF", "new": "#EFEFEF", "needs a thumbnail": "#FFF0D9", "needs the video": "#FFF0D9",
            "making the video": "#E7E5FF", "needs youtube text": "#FFE4EE", "ready": "#DDF1E6"}

    def grid():
        items = projects.list_projects(PROJECTS)
        if not items:
            st.info("No videos yet. Press **new video** to start the first one.")
            return
        cols = st.columns(3)
        for i, info in enumerate(items):
            with cols[i % 3], st.container(key=f"card_proj_{info['name']}"):
                if info["cover"]:
                    st.image(str(info["cover"]), width="stretch")
                else:
                    st.markdown('<div class="sg-cover-empty">no cover yet</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="sg-proj-name">{info["name"]}</div>', unsafe_allow_html=True)
                if info["quote"]:
                    st.markdown(f'<div class="sg-proj-quote">{info["quote"]}</div>', unsafe_allow_html=True)
                st.markdown(f'<span class="sg-pill" style="background:{PILL.get(info["stage"], "#EFEFEF")}">{info["stage"]}</span> '
                            f'<span class="sg-proj-meta">{info["tracks"]} tracks · {round(info["seconds"] / 60)} min</span>',
                            unsafe_allow_html=True)
                if info["schedule"]:
                    st.markdown(f'<span class="sg-proj-meta">publishes {info["schedule"]}</span>', unsafe_allow_html=True)
                if info["job"]["running"]:
                    st.progress(info["job"]["progress"], text=f"{info['job']['done']} of {info['job']['total']} requests")
                if info["render"]["running"]:
                    st.progress(info["render"]["progress"], text="making the video")
                if st.button("open", key=f"open_{info['name']}"):
                    open_project(info["name"], info["stage"])
                    st.rerun()                                           # full rerun, so the page switches

    running_any = any(p["job"]["running"] or p["render"]["running"] for p in projects.list_projects(PROJECTS))
    st.fragment(run_every=5 if running_any else None)(grid)()

if step == "music":
    with st.container(key="card_music"):
            c1, c2 = st.columns(2)
            preset = c1.selectbox("sound", list(brand.PRESETS))
            model = c2.selectbox("model", brand.MODELS)
            if st.session_state.get("_preset_seen") != preset:           # picking another sound loads its prompt
                st.session_state["_style_keep"] = brand.PRESETS[preset]
                st.session_state["_preset_seen"] = preset
                st.session_state["style_v"] = st.session_state.get("style_v", 0) + 1
            if st.session_state.pop("_improve_req", False):             # set by the button below, handled before the box is drawn
                try:
                    better, cost = ai.AIClient(ai_token, ai_model, mock=ai_mock).improve_music_prompt(
                        st.session_state["_style_keep"], st.session_state.get("_scenes_hint"))
                    st.session_state["_style_before"] = st.session_state["_style_keep"]
                    st.session_state["_style_keep"] = better
                    st.session_state["style_v"] += 1
                    st.session_state["_ai_spent"] = st.session_state.get("_ai_spent", 0.0) + cost
                    st.session_state["_ai_note"] = f"improved by AI" + (f" · {cost:.4f} credits" if cost else "")
                except ai.AIError as e:
                    st.session_state["_ai_note"] = f"AI helper error: {e}"
            if st.session_state.pop("_undo_req", False) and st.session_state.get("_style_before"):
                st.session_state["_style_keep"] = st.session_state.pop("_style_before")
                st.session_state["style_v"] += 1
                st.session_state["_ai_note"] = "back to your previous prompt"
            style = st.text_area("style prompt (no artist names, suno blocks them)", st.session_state["_style_keep"],
                                 height=110, key=f"w_style{st.session_state['style_v']}")
            st.session_state["_style_keep"] = style
            ai_c1, ai_c2, ai_c3 = st.columns([1.2, 1, 2.8])
            ai_c1.button("improve with AI", on_click=lambda: st.session_state.update(_improve_req=True),
                         disabled=not (ai_token or ai_mock), help="Rewrites your prompt so Suno gets a clearer, more specific brief.")
            ai_c2.button("undo", on_click=lambda: st.session_state.update(_undo_req=True),
                         disabled=not st.session_state.get("_style_before"))
            if st.session_state.get("_ai_note"):
                ai_c3.caption(st.session_state["_ai_note"])
            c1, c2, c3 = st.columns(3)
            n_tracks = c1.slider("tracks wanted", 2, 20, 8, 2, help="each request returns 2 tracks")
            minutes = c2.slider("target length (min)", 2.0, 6.0, 6.0, 0.5, help="API duration cap is 360 s")
            scenes = c3.multiselect("scene flavours (rotated)", brand.SCENES, brand.SCENES[:6])
            st.session_state["_scenes_hint"] = scenes
            n_req = n_tracks // 2
            mood_key = "groovy" if "groovy" in preset else "calm"
            st.info(f"{n_req} requests → {n_req * 2} tracks. Suno's own download cap (Pro 20/mo, Premier 60/mo) "
                    "does not apply to the API, but AceDataCloud charges per request." if not mock else
                    "mock mode: creates short test tones so you can try the rest of the app for free.")
            name_style = st.selectbox("track names", names.STYLES, help="mix = english and romanised japanese, e.g. “drizzle study” and “mado no ame”")
            job0 = projects.job_status(pdir)
            if st.button("generate in the background", type="primary", disabled=job0["running"] or not (mock or token)):
                spec = {"style": style, "scenes": scenes, "n_req": n_req, "minutes": minutes, "model": model,
                        "name_style": name_style, "mood_key": mood_key, "mock": mock}
                try:
                    projects.set_meta(pdir, topic=scenes, mood=mood_key, style=style,
                                      created=projects.meta(pdir).get("created") or time.time())
                    projects.start_music_job(pdir, spec, token)
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))
            st.caption("It keeps running in the background: open other steps or the projects page meanwhile. "
                       "Keep the black window open and the computer awake.")
            job_panel(pdir)

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

if step == "library":
    lib_dir = settings.library_dir()
    lib_files = library.scan(lib_dir)
    db = library.load_db()
    with st.container(key="card_libsettings"):
        folder_in = st.text_input("images folder", str(lib_dir or ""), placeholder=r"C:\Users\you\Documents\my-images",
                                  help="The folder with your images. Subfolders are included. The app only reads it: it never changes or moves your files.")
        l1, l2, l3 = st.columns([1, 1.3, 2.5])
        if l1.button("use this folder", disabled=not folder_in.strip()):
            settings.save_library_dir(folder_in)
            st.rerun()
        pending = [p for p in lib_files if library.needs_analysis(db, p)]
        job = library.library_job_status()
        use_ai_look = l3.checkbox("let the AI look at the pictures", value=bool(ai_token), disabled=not ai_token,
                                  help="Much better matching than colours alone. About 0.01 credits per image; the total is shown when it finishes.")
        if l2.button(f"look at {len(pending)} new images" if pending else "all images looked at", type="primary",
                     disabled=not pending or job["running"]):
            try:
                library.start_library_job(str(lib_dir), bool(use_ai_look and ai_token), ai_token, ai_model)
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))
        if not ai_token:
            st.caption("No AI helper token yet: the app will guess from colours only. Add a token under keys and settings for real matching.")
        library_panel()
    if not lib_dir:
        st.info("Choose the folder with your images above.")
    elif not lib_files:
        st.warning(f"No images found in {lib_dir}.")
    else:
        used_map = library.used_images(PROJECTS)
        looked = [p for p in lib_files if not library.needs_analysis(db, p)]
        f1, f2 = st.columns([1, 3])
        flt = f1.selectbox("show", ["all", "not used yet", "calm", "groovy", "vertical (need 16:9)", "flagged"])
        f2.caption(f"{len(lib_files)} images · {len(looked)} looked at · {len(used_map)} used in videos")
        shown = []
        for p in lib_files:
            an = (db.get(str(p)) or {}).get("analysis") or {}
            if flt == "not used yet" and str(p) in used_map: continue
            if flt in ("calm", "groovy") and an.get("mood") != flt: continue
            if flt.startswith("vertical") and an.get("orientation") != "vertical": continue
            if flt == "flagged" and not (an.get("risks") or an.get("has_text")): continue
            shown.append((p, an))
        cols = st.columns(4)
        for i, (p, an) in enumerate(shown):
            with cols[i % 4], st.container(key=f"card_proj_img{i}"):
                st.image(str(library.thumb(p)), width="stretch")
                if an:
                    chips = [an.get("mood", ""), an.get("time", "")] + an.get("scenes", [])[:1]
                    st.markdown('<span class="sg-proj-meta">' + " · ".join(c for c in chips if c) + "</span>", unsafe_allow_html=True)
                    if an.get("description"):
                        st.caption(an["description"])
                    if an.get("orientation") == "vertical":
                        st.markdown('<span class="sg-pill" style="background:#FFF0D9">vertical</span>', unsafe_allow_html=True)
                    if an.get("risks") or an.get("has_text"):
                        st.markdown('<span class="sg-pill" style="background:#FFE4EE">check: ' + ", ".join(an.get("risks", []) or ["text in image"]) + "</span>",
                                    unsafe_allow_html=True)
                else:
                    st.caption("not looked at yet")
                if str(p) in used_map:
                    st.markdown(f'<span class="sg-pill" style="background:#E7E5FF">used in {used_map[str(p)]}</span>', unsafe_allow_html=True)

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
    pm_ = projects.meta(pdir)
    topic_ = pm_.get("topic") or brand.SCENES[:6]
    mood_ = pm_.get("mood") or "calm"
    req = st.session_state.pop("_headline_req", None)           # set by the buttons next to the quote
    if req:
        lib_an = (library.load_db().get(pm_.get("library_image", ""), {}) or {}).get("analysis")
        if req == "ai" and not lib_an and st.session_state.get("cover"):
            lib_an = library.heuristic_analysis(Image.open(io.BytesIO(st.session_state["cover"][1])))
        an_ = lib_an or {"description": "", "scenes": list(topic_)[:2]}
        set_headline(make_headline(an_, mood_, topic_, use_ai=(req == "ai")) if req == "ai" else
                     headlines.suggest(mood_, [s for s in an_.get("scenes", []) if s in topic_] or list(topic_), used_quotes(name) | {pm_.get("quote", "")}, 1)[0])
    with st.container(key="card_match"):
        have = {k: v for k, v in library.load_db().items() if v.get("analysis") and Path(k).exists()}
        if not have:
            st.markdown("**pick an image from your library**")
            st.caption("Nothing looked at yet. Choose your image folder in the **library** step, and this card will suggest images that fit this video.")
        else:
            used_ = {k: v for k, v in library.used_images(PROJECTS).items() if v != name}
            m1, m2, m3 = st.columns([3, 1, 1.3])
            m1.markdown(f"**pick an image from your library** · {len(have)} images · fits: {', '.join(topic_[:3])} · {mood_}")
            if m2.button("suggest 3"):
                st.session_state[f"_sugg_{name}"] = library.suggest(have, topic_, mood_, used_, seed=f"{name}{time.time()}", n=3)
            if m3.button("use the best match", type="primary"):
                best = library.suggest(have, topic_, mood_, used_, seed=f"{name}{time.time()}", n=1)
                if best:
                    assign_image(best[0]["path"], best[0]["analysis"], mood_, topic_)
            sugg = st.session_state.get(f"_sugg_{name}") or []
            if sugg:
                for col, r in zip(st.columns(3), sugg):
                    with col:
                        st.image(str(library.thumb(Path(r["path"]))), width="stretch")
                        st.caption(r["analysis"].get("description", "") or Path(r["path"]).name)
                        st.markdown('<span class="sg-proj-meta">' + " · ".join(r["why"]) + "</span>", unsafe_allow_html=True)
                        if st.button("use this one", key=f"use_lib_{name}_{Path(r['path']).stem}"):
                            assign_image(r["path"], r["analysis"], mood_, topic_)
                            st.rerun()
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
                hb1, hb2 = st.columns(2)
                hb1.button("new headline", on_click=lambda: st.session_state.update(_headline_req="random"),
                           help="A fresh headline that fits the mood and has not been used in another video.")
                hb2.button("match to image", on_click=lambda: st.session_state.update(_headline_req="ai"),
                           disabled=not (ai_token and not ai_mock), help="The AI writes a headline for this picture.")
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
                projects.set_meta(pdir, quote=quote)
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

if step == "video":
    saved = projects.meta(pdir)
    video_path = pdir / "video.mp4"
    left, right = st.columns([1, 1.5], gap="large")

    # ---- the text generator: drawn under the form, but its values are needed first
    with right:
        form_slot = st.container(key="card_form")
        with st.expander("write the text for me (settings)"):
            if len(tracks) < 3:
                st.warning("Add at least 3 tracks (music or playlist step): the tracklist needs real durations for chapters.")
            c1, c2 = st.columns(2)
            with c1:
                quote_m = sticky(st.text_input, "quote", "quote", "you've got this.")
                subline_m = sticky(st.text_input, "subline", "subline_yt", "one more hour, then rest.")
                tstyle = st.radio("title format", ["quote", "playlist"], horizontal=True,
                                  format_func=lambda s: "[quote] | 80s japanese city pop to work & study to"
                                  if s == "quote" else "[playlist] you're [scenario] [emoji] 80s city pop")
                pl = st.text_input("playlist name", saved.get("playlist_name", "night desk"), key=f"w_{name}_plname", disabled=tstyle == "quote")
                sc = st.text_input("scenario", saved.get("scenario", "studying at 2am"), key=f"w_{name}_scen", disabled=tstyle == "quote")
                emoji = st.text_input("emoji", "🌴", disabled=tstyle == "quote")
            with c2:
                scene = st.text_area("scene + mood (2–3 sentences)", "a quiet desk, a warm lamp and the city glowing outside. "
                                     "slow, soft grooves that keep you company while you work.", height=110)
                use = st.text_input("for…", "working and studying")
                artist = st.selectbox("inspired by (title/description only)", brand.ARTISTS, index=len(tracks) % len(brand.ARTISTS))
                mood = st.selectbox("mood hashtag", list(brand.MOODS))
                question = st.selectbox("question to viewers", brand.DESCRIPTION_QUESTIONS)
                pinned_choice = st.selectbox("pinned comment", brand.PINNED_COMMENTS)
            st.button("write title, description and tags for me", on_click=lambda: st.session_state.update(_regen_req=name))
            st.caption("This replaces the text in the form above. Edit it afterwards, then press save.")
        if (pl, sc, quote_m) != (saved.get("playlist_name"), saved.get("scenario"), saved.get("quote")):
            projects.set_meta(pdir, playlist_name=pl, scenario=sc, quote=quote_m)
            saved = projects.meta(pdir)
        gen = {"title": metadata.make_title(tstyle, quote_m, pl, sc, emoji),
               "description": metadata.make_description(quote_m, subline_m, scene, tracks, use, artist, question,
                                                        brand.MOODS[mood], crossfade) if tracks else "",
               "tags": ", ".join(metadata.make_tags()), "pinned": pinned_choice}
        vkey = f"_text_v_{name}"
        if st.session_state.pop("_regen_req", None) == name:       # "write it for me": new widgets, filled with fresh text
            st.session_state[vkey] = st.session_state.get(vkey, 0) + 1
            st.session_state[f"_seed_{name}"] = gen
        ver = st.session_state.get(vkey, 0)
        seed = st.session_state.get(f"_seed_{name}") or {}
        init = {k: seed.get(k) or saved.get(k) or gen[k] for k in gen}
        import datetime as _dt
        if saved.get("schedule"):
            _slot = _dt.datetime.strptime(saved["schedule"], "%Y-%m-%d %H:%M")
        else:
            _slot = projects.next_free_slot({p["schedule"] for p in projects.list_projects(PROJECTS) if p["name"] != name})

    # ---- the form (right)
    with form_slot:
        title = st.text_input("Title", init["title"], key=f"w_{name}_title{ver}", max_chars=100)
        st.caption(f"{len(title)}/100 characters · the first 60 matter most")
        desc = st.text_area("Description", init["description"], height=300, key=f"w_{name}_desc{ver}")
        tags = st.text_area("Tags", init["tags"], height=70, key=f"w_{name}_tags{ver}")
        pinned = st.text_input("Pinned comment", init["pinned"], key=f"w_{name}_pin{ver}")
        st.markdown("**Scheduled date**")
        d1, d2, d3 = st.columns([1.2, 1, 1.6])
        sdate = d1.date_input("date", _slot.date(), key=f"w_{name}_date{ver}", label_visibility="collapsed")
        stime = d2.time_input("time (Amsterdam)", _slot.time(), key=f"w_{name}_time{ver}", label_visibility="collapsed")
        d3.caption("Mon / Wed / Fri 15:00 · next free slot suggested · upload as private and scheduled")
        for issue in metadata.validate(title, tracks, pinned): st.warning(issue)
        if "<" in title or ">" in title:
            st.warning("YouTube titles cannot contain < or >.")
        cur = {"title": title, "description": desc, "tags": tags, "pinned": pinned,
               "schedule": f"{sdate:%Y-%m-%d} {stime:%H:%M}"}
        dirty = any(cur[k] != saved.get(k) for k in cur)
        if st.button("save changes" if dirty else "all changes saved", type="primary" if dirty else "secondary", disabled=not dirty):
            projects.set_meta(pdir, **cur)
            (pdir / "upload.txt").write_text(metadata.upload_txt(title, desc, [t.strip() for t in tags.split(",") if t.strip()],
                                                                 pinned, cur["schedule"]), encoding="utf-8")
            st.rerun()
        with st.expander("copy"):
            for lbl, val in (("title", title), ("description", desc), ("tags", tags), ("pinned comment", pinned)):
                st.caption(lbl); st.code(val, language=None)
        st.caption("Channel guidelines: " + " / ".join(brand.CHANNEL_GUIDELINES))

    # ---- the video (left)
    with left:
        with st.container(key="card_video"):
            rs = projects.render_status(pdir)
            still_ok = (pdir / "still.png").exists()
            if rs["running"] or (rs["state"] in ("failed", "interrupted")):
                render_panel(pdir)
            if rs["running"]:
                pass
            elif video_path.exists():
                st.video(str(video_path))
                mb = video_path.stat().st_size / 1_000_000
                st.caption(f"{metadata.fmt_ts(metadata.total_length([t['duration'] for t in tracks], crossfade))} · {mb:.0f} MB · 1920×1080")
                st.download_button("download video", data=lambda: video_path.read_bytes(), file_name=f"{name}.mp4", mime="video/mp4",
                                   width="stretch")
            else:
                if still_ok:
                    st.image(str(pdir / "still.png"), width="stretch")
                else:
                    st.markdown('<div class="sg-cover-empty">no video yet</div>', unsafe_allow_html=True)
                st.markdown(("✓" if tracks else "✗") + f" tracks ({len(tracks)}) &nbsp; " + ("✓" if still_ok else "✗")
                            + " still image (thumbnail step)")
            with st.expander("video settings"):
                f_in = st.number_input("fade in (s)", 0.0, 10.0, 3.0, 0.5)
                f_out = st.number_input("fade out (s)", 0.0, 20.0, 6.0, 0.5)
                st.caption(f"Crossfade {crossfade:g}s (set under keys and settings) · loudness −14 LUFS · still image, no animation.")
            if not rs["running"]:
                if st.button("make the video again" if video_path.exists() else "make the video", type="secondary" if video_path.exists() else "primary",
                             disabled=not (tracks and still_ok), width="stretch"):
                    try:
                        projects.start_render(pdir, crossfade, f_in, f_out)
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))
            if (pdir / "thumbnail.png").exists():
                st.image(str(pdir / "thumbnail.png"), caption="thumbnail", width="stretch")
                st.download_button("download thumbnail", data=lambda: (pdir / "thumbnail.png").read_bytes(),
                                   file_name=f"{name}-thumbnail.png", mime="image/png", width="stretch")
            with st.expander("tracklist"):
                st.code(metadata.tracklist_text(tracks, crossfade) if tracks else "no tracks yet", language=None)

# ---------------- progress rail (left), filled last so it shows fresh status ----------------
tracks = st.session_state["tracks"]
n = len(tracks)
mins = round(metadata.total_length([t["duration"] for t in tracks], crossfade) / 60)
fixed_n = len(list(imgs_dir.glob("*_16x9.png"))) if imgs_dir.exists() else 0
cover_done = (pdir / "thumbnail.png").exists()
yt_done = bool(projects.meta(pdir).get("title")) and (pdir / "upload.txt").exists()
video_done = (pdir / "video.mp4").exists()
render_now = projects.render_status(pdir)
proj_count = len(projects.list_projects(PROJECTS))
_lf = library.scan(settings.library_dir())
_ldb = library.load_db()
lib_looked = sum(1 for p in _lf if not library.needs_analysis(_ldb, p))
job_now = projects.job_status(pdir)
RAIL = {
    "projects": (False, f"{proj_count} video{'s' if proj_count != 1 else ''}" if proj_count else "start your first video"),
    "music": (n > 0 and not job_now["running"], f"generating {job_now['done']}/{job_now['total']}" if job_now["running"]
              else (f"{n} tracks · {mins} min" if n else "no tracks yet")),
    "playlist": (n > 0, "titles ready" if n else "after the music"),
    "library": (bool(_lf) and lib_looked == len(_lf), f"{lib_looked} of {len(_lf)} looked at" if _lf else "choose your folder"),
    "fix images": (fixed_n > 0, f"{fixed_n} made 16:9" if fixed_n else "optional"),
    "thumbnail": (cover_done, "saved" if cover_done else ("in progress" if step == "thumbnail" else "not made yet")),
    "video": (video_done and yt_done, "ready to upload" if (video_done and yt_done) else
              (f"making it {int(render_now['progress'] * 100)}%" if render_now["running"] else
               ("write the text" if video_done else "make the video"))),
}
with rail_slot:
    for i, s in enumerate(STEPS):
        done, sub = RAIL[s]
        st.button(f"{'✓' if done else ('•' if i == 0 else i)}   {s}", key=f"step_{s}", width="stretch",
                  type="primary" if s == step else "secondary", on_click=go, args=(s,))
        st.markdown(f'<div class="sg-step-sub{" done" if done else ""}">{sub}</div>', unsafe_allow_html=True)
