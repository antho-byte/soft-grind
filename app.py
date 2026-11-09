"""soft grind. studio: Suno music -> playlist -> thumbnail -> YouTube metadata."""
import datetime as dt
import html
import io
import json
import os
import time
import zipfile
from pathlib import Path

import streamlit as st
from PIL import Image

from soft_grind import animate, planning, shorts, youtube, ai, brand, errors, fixes, headlines, imagegen, library, metadata, names, playlist, projects, health, notify, security, settings, texts, theme, thumbnail as T, video

st.set_page_config(page_title="soft grind. studio", page_icon="🌴", layout="wide")
theme.inject()
if security.password_hash() and not st.session_state.get("_auth"):         # optional password gate: nothing else is shown before it
    st.markdown(theme.logo_html(), unsafe_allow_html=True)
    st.markdown('<div class="sg-sub">enter the password to continue.</div>', unsafe_allow_html=True)
    with st.form("login"):
        pw_in = st.text_input("password", type="password")
        go_in = st.form_submit_button("open", type="primary")
    if go_in:
        ok_, msg_ = security.check_login(pw_in)
        if ok_:
            st.session_state["_auth"] = True
            st.rerun()
        st.error(msg_)
    st.stop()
if not security.password_hash() and str(st.get_option("server.address") or "") not in ("", "127.0.0.1", "localhost"):
    st.markdown(theme.logo_html(), unsafe_allow_html=True)         # password removed while this window still listens on the network
    st.error("The password was removed while other devices could still connect. Close this window and start the app again.")
    st.stop()
PROJECTS = settings.projects_dir()
SAVED = settings.load_keys()

MENU = [("projects", "videos"), ("planning", "planning"), ("library", "images"), ("settings", "settings")]            # the whole app
TABS = [("music", "music"), ("thumbnail", "cover"), ("video", "video")]                         # inside one video
VIDEO_STEPS = {"music", "thumbnail", "video"}
TITLES = {
    "projects": ("your videos.", "every video you made, with its cover. open one to keep going."),
    "planning": ("planning.", "which video goes out on which day. free upload slots: monday, wednesday and friday at 15:00."),
    "library": ("the images.", "your folder of images: let the app look at them, then match them to your videos."),
    "settings": ("settings.", "keys, folders, security, and a check that everything is ready."),
    "music": ("make the music.", "pick a sound, press generate, get instrumental tracks. check and rename them below."),
    "thumbnail": ("the cover.", "one image, one headline, one logo."),
    "video": ("the video.", "watch it, check the words, pick a day to publish."),
}
_REMAP = {"setup": "settings", "playlist": "music", "fix images": "thumbnail"}                  # older names
st.session_state["step"] = _REMAP.get(st.session_state.get("step", "projects"), st.session_state.get("step", "projects"))

# settings that every page reads (the settings page edits them)
st.session_state.setdefault("_cfg_suno", os.getenv("ACEDATACLOUD_API_TOKEN") or SAVED.get("suno", ""))
st.session_state.setdefault("_cfg_image", os.getenv("ACEDATACLOUD_IMAGE_TOKEN") or SAVED.get("image", ""))
st.session_state.setdefault("_cfg_ai", os.getenv("ACEDATACLOUD_AI_TOKEN") or SAVED.get("ai", ""))
st.session_state.setdefault("_cfg_ai_model", SAVED.get("ai_model") or ai.DEFAULT_MODEL)
st.session_state.setdefault("_cfg_crossfade", metadata.CROSSFADE)


def read_cfg():
    """The current keys and switches (practice mode follows the key: no key = practice mode, unless you chose otherwise)."""
    g = st.session_state
    return (g["_cfg_suno"], g["_cfg_image"], g["_cfg_ai"], g["_cfg_ai_model"], g["_cfg_crossfade"],
            g.get("_cfg_mock", not g["_cfg_suno"]), g.get("_cfg_img_mock", not g["_cfg_image"]), g.get("_cfg_ai_mock", not g["_cfg_ai"]))


token, img_token, ai_token, ai_model, crossfade, mock, img_mock, ai_mock = read_cfg()



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
    nm = projects.create_project(PROJECTS)
    st.session_state.update(project=nm, step="music", tracks=[], fix_results={})
    for k in ("_style_before", "_ai_note", "_job_was_running"):
        st.session_state.pop(k, None)


def open_project(nm, stage_name):
    st.session_state.update(project=nm, tracks=[], fix_results={}, step={
        "new": "music", "making music": "music", "needs a thumbnail": "thumbnail", "needs the video": "video",
        "making the video": "video", "needs youtube text": "video", "ready": "video", "making it": "video",
        "needs attention": "library"}.get(stage_name, "music"))
    st.session_state.pop("_job_was_running", None)


REMOTE_HELP = (Path(__file__).resolve().parent / "docs" / "REMOTE.md").read_text(encoding="utf-8") if (Path(__file__).resolve().parent / "docs" / "REMOTE.md").exists() else "See docs/REMOTE.md."


def show_error(raw, kind="error", prefix=""):
    """A plain message with what to do, and the original text under 'technical details' (it has a copy button)."""
    e = errors.explain(raw)
    getattr(st, kind)(f"**{prefix}{e['title']}** {e['advice']}")
    if e["raw"]:
        with st.expander("technical details"):
            st.code(e["raw"], language=None)


def used_quotes(exclude=""):
    """Headlines of the last 30 videos: a headline may come back after that."""
    return projects.recent_quotes(PROJECTS, exclude, headlines.RECENT)


def set_headline(h):
    st.session_state[f"_s_{name}_quote"] = h
    st.session_state[f"_sv_{name}"] = st.session_state.get(f"_sv_{name}", 0) + 1
    projects.set_meta(pdir, quote=h, quote_placeholder=False)


def ensure_quote():
    """A project never starts from a shared default: give it a headline nobody else has."""
    m = projects.meta(pdir)
    if not m.get("quote"):
        h = headlines.suggest(m.get("mood") or "calm", m.get("topic") or [], used_quotes(name), 1)[0]
        projects.set_meta(pdir, quote=h, quote_placeholder=True)


def make_headline(analysis, mood, topic, use_ai=True):
    """A headline from your list that fits the image (the AI chooses from the list when a key is set). Never one used recently."""
    used = used_quotes(name) | {projects.meta(pdir).get("quote", "")}       # also not the one this video has now
    client = ai.AIClient(ai_token, ai_model) if (use_ai and ai_token and not ai_mock) else None
    h, cost = headlines.pick(analysis, mood, list(topic), used, client)
    if cost:
        st.session_state["_ai_spent"] = st.session_state.get("_ai_spent", 0.0) + cost
        projects.add_cost(name, "ai", cost, False)
    return h


def assign_image(path, analysis, mood, topic):
    """Use a library image for this video: 16:9 copy in the project, a matching headline, cover for the cover tab."""
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
            show_error(rs["error"], prefix="The video could not be made. ")
        elif rs["state"] == "interrupted":
            st.warning("The video job stopped unexpectedly (window closed or computer asleep). Press make the video again.")
    st.fragment(run_every=3 if projects.render_status(pdir_)["running"] else None)(body)()


def film_look_ui(pdir_, vname):
    """Film dust: a few faint specks, like an old print. Off = the fast plain picture. Try it on a 20-second test first."""
    cur = projects.film_look(pdir_) or {}
    on = st.toggle("film dust (faint specks)", value=bool(cur), key=f"look_on_{vname}")
    if on and not cur:
        projects.set_meta(pdir_, film_look=dict(video.LOOK_DEFAULT))
        st.rerun()
    if not on:
        if cur:
            projects.set_meta(pdir_, film_look={})
            st.rerun()
        st.caption("Off: a still picture, quickest to make and a small file.")
        return
    st.caption("Applies the next time you press make the video. It takes roughly half an hour per hour of video and adds almost nothing to the file size.")
    if st.button("20-second test", key=f"look_test_{vname}", disabled=not (pdir_ / "still.png").exists(),
                 help=None if (pdir_ / "still.png").exists() else "Make the cover first."):
        try:
            with st.spinner("making the test…"):
                video.look_preview(pdir_ / "still.png", pdir_ / "look_test.mp4", cur)
            st.session_state[f"_look_test_{vname}"] = True
        except video.VideoError as e:
            show_error(str(e))
    if st.session_state.get(f"_look_test_{vname}") and (pdir_ / "look_test.mp4").exists():
        st.video(str(pdir_ / "look_test.mp4"), loop=True, autoplay=True, muted=True)
    if st.button("use this for all new videos", key=f"look_default_{vname}", type="tertiary"):
        settings._write_settings(film_look_default=dict(cur))
        st.toast("saved as your default")


def shorts_ui(pdir_, vname):
    """Vertical Shorts from this video: background motion (free zoom, your own loop clip, or an AI loop), then make 2-3 Shorts."""
    st.markdown("**shorts**")
    has_pic = shorts.source_picture(pdir_) is not None
    loop_path = pdir_ / shorts.LOOP
    a_st = animate.status(pdir_)

    def anim_body():
        s_ = animate.status(pdir_)
        if s_["running"]:
            st.info(f"animating the picture with AI · {s_['message']} (usually 1 to 5 minutes)")
        elif s_["state"] == "failed":
            show_error(s_["error"], prefix="The picture could not be animated. ")
    st.fragment(run_every=5 if a_st["running"] else None)(anim_body)()

    motion = st.segmented_control("background", ["slow zoom", "animated loop"], key=f"sh_motion_{vname}", required=True,
                                  default="animated loop" if loop_path.exists() else "slow zoom") or "slow zoom"
    if motion == "slow zoom":
        st.caption("Free: the cover picture slowly moves closer. Instant, no AI.")
    else:
        if loop_path.exists():
            c_v, c_t = st.columns([1, 1.6])
            c_v.video(str(loop_path), loop=True, autoplay=True, muted=True)
            m_ = projects.meta(pdir_)
            c_t.caption(f"this video's loop · {m_.get('loop_model') or 'your own clip'}"
                        + (f" · {m_['loop_made']}" if m_.get("loop_made") else ""))
            if c_t.button("remove this loop", key=f"sh_rmloop_{vname}", type="tertiary"):
                loop_path.unlink(missing_ok=True); projects.set_meta(pdir_, loop_model="", loop_made=""); st.rerun()
        up = st.file_uploader("drop in a loop clip (for example from Midjourney: Animate → Loop)", type=["mp4", "mov", "webm"],
                              key=f"sh_up_{vname}")
        if up is not None and st.button("use this clip", key=f"sh_useclip_{vname}"):
            loop_path.write_bytes(up.getvalue()); projects.set_meta(pdir_, loop_model="your own clip", loop_made=time.strftime("%Y-%m-%d %H:%M"))
            st.rerun()
        with st.expander("or let the AI animate the picture"):
            model = st.selectbox("video model", list(animate.MODELS), key=f"sh_model_{vname}")
            ep0, tpl0, price, loops = animate.MODELS[model]
            prompt = st.text_area("what should move", animate.DEFAULT_PROMPT, height=100, key=f"sh_prompt_{vname}")
            with st.expander("advanced: the exact request (edit if the service complains)"):
                ep = st.text_input("endpoint", ep0, key=f"sh_ep_{vname}_{model}")
                body = st.text_area("request (JSON)", json.dumps(tpl0, indent=2), height=170, key=f"sh_tpl_{vname}_{model}")
            st.caption((f"≈ ${price:.2f} per clip at the cheapest top-up tier" if price else "price: see your AceDataCloud console")
                       + (" · loops by itself" if loops else " · not a perfect loop: tick 'play forwards then backwards' below")
                       + (" · practice mode: a free fake clip" if img_mock else
                          " · uses your image key; the picture goes as a link via your platform token" if settings.load_keys().get("platform")
                          else " · uses your image key. Tip: add a platform token in settings, the video models want the picture as a link"))
            if st.button("animate the picture", type="primary", key=f"sh_animate_{vname}", disabled=not has_pic or a_st["running"]
                         or not (img_token or img_mock)):
                try:
                    animate.start(pdir_, model, ep, json.loads(body), prompt, img_token, img_mock)
                    st.rerun()
                except json.JSONDecodeError as e:
                    st.error(f"The request JSON is not valid: {e}")
                except RuntimeError as e:
                    st.error(str(e))
    s1, s2, s3 = st.columns(3)
    n_sh = s1.select_slider("how many", [1, 2, 3], 3, key=f"sh_n_{vname}")
    length = s2.select_slider("seconds", [15, 20, 30, 45, 60], 30, key=f"sh_len_{vname}")
    dust = s3.toggle("film dust", value=bool(projects.film_look(pdir_)), key=f"sh_dust_{vname}")
    ping = st.checkbox("play the loop forwards then backwards (for clips that do not loop by themselves)", key=f"sh_ping_{vname}",
                       disabled=motion != "animated loop")
    use_loop = motion == "animated loop" and loop_path.exists()
    if motion == "animated loop" and not loop_path.exists():
        st.caption("No loop clip yet: drop one in or let the AI make one, or switch to slow zoom.")

    def run_body():
        s_ = shorts.status(pdir_)
        if s_["running"]:
            st.progress(s_["progress"], text=f"making shorts · {s_['message']}")
            return
        if s_["state"] == "failed":
            show_error(s_["error"], prefix="The shorts could not be made. ")
        rows = shorts.listing(pdir_)
        if rows:
            cols = st.columns(len(rows))
            for col, r in zip(cols, rows):
                with col:
                    st.video(str(shorts.folder(pdir_) / r["file"]))
                    st.caption(f"{r['track']} · from {int(r['start'] // 60)}:{int(r['start'] % 60):02d}")
                    st.download_button("download", data=(shorts.folder(pdir_) / r["file"]).read_bytes(), file_name=f"{vname}-{r['file']}",
                                       mime="video/mp4", key=f"sh_dl_{vname}_{r['file']}", width="stretch", type="tertiary")
            with st.expander("title and description for the shorts"):
                st.code(rows[0]["title"], language=None)
                st.code(rows[0]["description"], language=None)
    st.fragment(run_every=3 if shorts.status(pdir_)["running"] else None)(run_body)()
    if st.button("make the shorts" if not shorts.listing(pdir_) else "make the shorts again", type="primary", width="stretch",
                 key=f"sh_make_{vname}", disabled=not has_pic or not tracks or shorts.status(pdir_)["running"]
                 or (motion == "animated loop" and not use_loop)):
        try:
            shorts.start(pdir_, {"n": n_sh, "length": length, "motion": "loop" if use_loop else "zoom", "dust": dust, "pingpong": ping})
            st.rerun()
        except RuntimeError as e:
            st.error(str(e))


def yt_panel(pdir_):
    """Upload to YouTube: the button, live progress, and the link once it is there."""
    def body():
        ys = projects.youtube_status(pdir_)
        m = projects.meta(pdir_)
        was = st.session_state.get("_yt_was_running") == pdir_.name
        if ys["running"]:
            st.session_state["_yt_was_running"] = pdir_.name
            st.progress(ys["progress"], text=ys["message"] or "uploading")
            st.caption("This runs in the background. Keep the black window open.")
            return
        if was:
            st.session_state.pop("_yt_was_running", None)
            st.rerun()
        if m.get("youtube_id"):
            st.markdown(f'<span class="sg-chk">✓</span> on YouTube since {html.escape(m.get("youtube_at", ""))} · '
                        f'[open in YouTube Studio]({youtube.studio_url(m["youtube_id"])})', unsafe_allow_html=True)
            if ys["note"]:
                st.warning(ys["note"])
            if m.get("schedule") and youtube.publish_at(m["schedule"]):
                st.caption(f"It is private and will go public by itself on {m['schedule']} (Amsterdam).")
            if st.button("upload again as a new video", type="tertiary", key="yt_again"):
                st.session_state["_yt_confirm_again"] = True
            if st.session_state.get("_yt_confirm_again"):
                st.warning("This makes a second copy on YouTube. The first one stays until you delete it in YouTube Studio.")
                if st.button("yes, upload again", key="yt_again_yes"):
                    st.session_state.pop("_yt_confirm_again", None)
                    try:
                        projects.start_youtube(pdir_, again=True)
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))
            return
        if ys["state"] == "failed":
            show_error(ys["error"], prefix="The upload did not finish. ")
        elif ys["state"] == "interrupted":
            st.warning("The upload stopped unexpectedly (window closed or computer asleep). Press upload again.")
        if not youtube.connected():
            st.caption("To upload straight to YouTube, connect it once in settings (youtube card).")
            return
        when = m.get("schedule", "")
        st.caption("Uploads as private" + (f" and publishes by itself on {when} (Amsterdam)." if youtube.publish_at(when) else
                   ": the scheduled time is in the past, so you publish it yourself in YouTube Studio."))
        if st.button("upload to YouTube", type="primary", width="stretch", disabled=not m.get("title"),
                     help=None if m.get("title") else "Write the YouTube text first."):
            try:
                projects.start_youtube(pdir_)
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))
    st.fragment(run_every=3 if projects.youtube_status(pdir_)["running"] else None)(body)()


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
            st.success("done: the tracks are in this project. Check and rename them in the tracks section below.")
        elif job["state"] == "failed":
            show_error(job["error"] or "unknown error", prefix="Stopped. ")
            st.caption("Tracks made so far are saved" + (f" ({len(job['task_ids'])} requests were started)." if job["task_ids"] else "."))
        elif job["state"] == "cancelled":
            st.info("cancelled. Tracks made so far are saved.")
        elif job["state"] == "interrupted":
            st.warning("The job stopped unexpectedly (the black window was closed, or the computer went to sleep). "
                       "Tracks made so far are saved.")
    st.fragment(run_every=3 if projects.job_status(pdir_)["running"] else None)(body)()


# ---------------- which video we are working on, the sidebar ----------------
proj_list = projects.list_projects(PROJECTS)
proj_names = [p["name"] for p in proj_list]
name = st.session_state.get("project") or (proj_names[0] if proj_names else "mix-001")
st.session_state["project"] = name
pdir = PROJECTS / (playlist.safe_name(name).replace(" ", "-") or "mix")
tracks_dir = pdir / "tracks"
step = st.session_state["step"]
if step in VIDEO_STEPS:
    tracks_dir.mkdir(parents=True, exist_ok=True)


def switch_video(nm):
    st.session_state.update(project=st.session_state[f"pick_{nm}"], tracks=[], fix_results={})
    for k in ("_job_was_running", "_render_was_running", "_ai_note", "_style_before"):
        st.session_state.pop(k, None)


with st.sidebar:
    st.markdown(theme.logo_html(), unsafe_allow_html=True)
    st.markdown('<div class="sg-tag">city pop to work and study to.</div>', unsafe_allow_html=True)
    menu_slot = st.container(key="menu")                   # filled at the end, so it shows fresh status
    if step in VIDEO_STEPS and proj_names:
        quotes = {p["name"]: p["quote"] for p in proj_list}
        options = proj_names if name in proj_names else [name] + proj_names
        st.selectbox("working on", options, index=options.index(name), key=f"pick_{name}", on_change=switch_video, args=(name,),
                     format_func=lambda n: f"{n} · {quotes[n]}" if quotes.get(n) else n)
    st.markdown('<div class="sg-foot">your keys and videos stay on this computer.</div>', unsafe_allow_html=True)



st.session_state.setdefault("tracks", [])
_files = projects.audio_files(tracks_dir)
_inside = all(Path(t["path"]).parent.resolve() == tracks_dir.resolve() for t in st.session_state["tracks"])  # not an imported folder
if st.session_state.pop("_reload", False) or (_inside and len(_files) != len(st.session_state["tracks"])):
    st.session_state["tracks"] = playlist.tracks_from_folder(tracks_dir) if _files else []
tracks = st.session_state["tracks"]
imgs_dir = pdir / "images"

topnav_slot = st.container(key="topnav")                  # the sidebar is hidden behind a button on phones, so the menu is repeated here
crumb = {"projects": "all videos", "planning": "planning", "library": "images", "settings": "settings"}.get(step, f"videos › {name}")
theme.page_title(crumb, *TITLES[step])
tabs_slot = st.container(key="vtabs") if step in VIDEO_STEPS else None
if st.session_state.get("_last_view") != (step, name):                    # a new page: start at the top, not where the last one was scrolled
    st.session_state["_last_view"] = (step, name)
    st.iframe("<script>const m=window.parent.document.querySelector('[data-testid=\"stMain\"]');if(m){m.scrollTo(0,0);}</script>", height=1)


if step == "settings":
    with st.container(key="card_keys"):
        st.markdown("**keys**")
        st.caption("Without a key the app runs in practice mode: fake songs and images, no cost. Keys are stored on this computer only.")
        st.caption("suno (AceDataCloud)")
        st.session_state["_cfg_suno"] = st.text_input("API token", st.session_state["_cfg_suno"], type="password", key="w_cfg_suno",
                                                      help="platform.acedata.cloud → Applications. Generation costs credits.")
        st.session_state["_cfg_mock"] = st.checkbox("practice mode (no API, fake short tones)", value=not st.session_state["_cfg_suno"])
        st.caption("image tool (AceDataCloud)")
        st.session_state["_cfg_image"] = st.text_input("image API token", st.session_state["_cfg_image"], type="password", key="w_cfg_image",
                                                       help="A separate key (own budget cap) for the Nano Banana image models.")
        st.session_state["_cfg_img_mock"] = st.checkbox("image practice mode (no API, free)", value=not st.session_state["_cfg_image"])
        st.caption("AI helper (AceDataCloud chat)")
        st.session_state["_cfg_ai"] = st.text_input("AI helper token", st.session_state["_cfg_ai"], type="password", key="w_cfg_ai",
                                                    help="Its own key with its own usage limit. Used for the AI buttons.")
        st.session_state["_cfg_ai_model"] = st.text_input("AI model", st.session_state["_cfg_ai_model"], key="w_cfg_ai_model",
                                                          help="Exact model name from the Chat tab at platform.acedata.cloud/models, e.g. a Claude Haiku.")
        st.session_state["_cfg_ai_mock"] = st.checkbox("AI practice mode (no API, free)", value=not st.session_state["_cfg_ai"])
        st.caption("picture links for animated loops (AceDataCloud platform)")
        st.session_state.setdefault("_cfg_platform", SAVED.get("platform", ""))
        st.session_state["_cfg_platform"] = st.text_input(
            "platform token", st.session_state["_cfg_platform"], type="password", key="w_cfg_platform",
            help="Only for 'animate the picture'. The video models want the picture as a web link: with this token the app first "
                 "uploads the vertical picture to AceDataCloud's own file storage (cdn.acedata.cloud). Make one at "
                 "platform.acedata.cloud → console → platform tokens. Note: that link can be opened by anyone who has it.")
        token, img_token, ai_token, ai_model, crossfade, mock, img_mock, ai_mock = read_cfg()
        if st.button("save keys on this computer", type="primary"):
            settings.save_keys(token, img_token, ai_token, ai_model, st.session_state["_cfg_platform"])
            st.success("saved: you won't need to paste them again")
    with st.container(key="card_folders"):
        st.markdown("**folders and video**")
        st.session_state["_cfg_crossfade"] = st.number_input("crossfade (s)", 0.0, 10.0, st.session_state["_cfg_crossfade"], 0.5,
                                                             help="The overlap between songs. The timestamps in the description use it.")
        st.caption("where your videos are saved")
        folder_in = st.text_input("projects folder", str(PROJECTS),
                                  help="Tracks, thumbnails and upload.txt of every video. Choosing the app's own folder uses its “projects” subfolder.")
        if st.button("use this folder"):
            newp = settings.save_projects_dir(folder_in)
            st.session_state["tracks"] = []
            st.toast(f"videos now live in {newp}")
            st.rerun()
        old_dir = settings.DEFAULT_PROJECTS
        if old_dir.is_dir() and old_dir.resolve() != PROJECTS.resolve() and any(p.is_dir() for p in old_dir.iterdir()):
            st.caption(f"videos found in the old folder: `{old_dir}`")
            if st.button("move my existing videos here"):
                moved, skipped = settings.move_projects(old_dir, PROJECTS)
                st.session_state["tracks"] = []
                if moved:
                    st.success("moved: " + ", ".join(moved))
                if skipped:
                    st.warning("left in place (already has files in the new folder): " + ", ".join(skipped))
        st.caption(f"your keys live in `{settings.DATA_DIR}`, outside the app folder")
    with st.container(key="card_notify"):
        st.markdown("**phone messages**")
        notify_on = st.toggle("tell my phone when a video is ready, or needs me", value=notify.enabled(), key="notify_toggle")
        if notify_on != notify.enabled():
            notify.enable() if notify_on else notify.disable()
            st.rerun()
        if notify.enabled():
            st.markdown("1. Install the free app **ntfy** on your phone (iPhone or Android).  \n"
                        "2. In it, add a subscription with this exact name:")
            st.code(notify.topic(), language=None)
            st.markdown("3. Press the test button.")
            if st.button("send a test message"):
                st.toast("sent: check your phone" if notify.send("soft grind. test", "It works: you will hear from me here.", tags="tada")
                         else "could not send: check the internet connection")
            st.caption("Messages travel through ntfy.sh, a free public service. They contain only the video name and headline, never keys. "
                       "The name above is the secret that lets a phone receive them: don't share it.")
        else:
            st.caption("Off. Turn it on to get a message on your phone when a video is ready, needs you, or stops. Free, no account.")
    with st.container(key="card_youtube"):
        st.markdown("**youtube**")
        if youtube.connected():
            st.markdown('<span class="sg-chk">✓</span> connected. Finished videos can be uploaded from the video tab.', unsafe_allow_html=True)
            if st.button("disconnect youtube"):
                youtube.disconnect()
                st.rerun()
        else:
            st.caption("Lets the app upload a finished video with its title, description, tags, cover and schedule. Free; set up once.")
            up = st.file_uploader("1. the login file from Google Cloud (the JSON you downloaded)", type=["json"], key="yt_client_file")
            if up is not None and not youtube.has_client():
                try:
                    youtube.save_client(up.getvalue())
                    st.rerun()
                except youtube.YouTubeError as e:
                    st.error(str(e))
            if youtube.has_client():
                st.markdown('<span class="sg-chk">✓</span> login file saved.', unsafe_allow_html=True)
                st.caption("2. A Google window opens on this computer. Choose your channel's account, press Advanced, then continue, and allow access.")
                if st.button("connect youtube", type="primary"):
                    try:
                        with st.spinner("waiting for you in the Google window (up to 4 minutes)…"):
                            youtube.login()
                        st.rerun()
                    except youtube.YouTubeError as e:
                        st.error(str(e))
                if st.button("use a different login file", type="tertiary"):
                    youtube._client_file().unlink(missing_ok=True)
                    st.rerun()
    with st.container(key="card_security"):
        st.markdown("**security**")
        pw_new = st.text_input("app password", type="password", placeholder="set or change the password (8+ characters)",
                               help="Asked every time the app opens. Stored as a scrambled hash, not as text.")
        sp1, sp2 = st.columns(2)
        if sp1.button("save password", disabled=not pw_new):
            try:
                security.set_password(pw_new)
                st.session_state["_auth"] = True
                st.success("password saved")
            except ValueError as e:
                st.error(str(e))
        if sp2.button("remove password", disabled=not security.password_hash()):
            security.remove_password()
            st.rerun()
        remote_on = st.toggle("allow other devices (phone, other computer)", value=security.remote_wanted(),
                              disabled=not security.password_hash(),
                              help="By default only this computer can open the app. Turn this on only on a network you trust. Restart the app after changing it.")
        if remote_on != security.remote_wanted():
            try:
                security.set_remote(remote_on)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        if security.remote_wanted():
            st.caption(f"After a restart, open `{security.lan_url()}` on a device on the same network, and enter the password.")
        else:
            st.caption("Right now only this computer can open the app.")
        with st.expander("how to reach the app from your phone or work laptop, away from home"):
            st.markdown(REMOTE_HELP)
    with st.container(key="card_setup"):
        st.markdown("**check my setup**")
        st.caption("Each key is tested with a free question that does not make anything, so this costs nothing. "
                   "The AI key uses a few words of text (a fraction of a cent).")
        if st.button("check again", type="primary"):
            st.session_state.pop("_setup_results", None)
        if "_setup_results" not in st.session_state:
            with st.spinner("checking…"):
                st.session_state["_setup_results"] = health.run_all(token, img_token, ai_token, ai_model, SAVED)
        label = {"ok": "ok", "warn": "check", "fail": "fix"}
        for r in st.session_state["_setup_results"]:
            st.markdown(f'<div class="sg-chk"><span class="sg-badge {r["status"]}">{label[r["status"]]}</span>'
                        f'<b>{r["name"]}</b><span class="d">{r["detail"]}</span></div>', unsafe_allow_html=True)
    with st.container(key="card_diag"):
        st.markdown("**diagnostics**")
        st.caption("Something not working? Copy this and send it to me. Keys and passwords are removed automatically.")
        diag = health.diagnostics([token, img_token, ai_token, SAVED.get("platform", "")])
        st.code(diag, language=None)
        st.download_button("download diagnostics.txt", diag, "diagnostics.txt")

if step == "projects":
    def new_video_menu(where):
        with where.popover("＋ new video", width="stretch", type="primary"):
            st.button("step by step", on_click=new_video, width="stretch", type="primary")
            st.caption("you choose the music, the image and the words yourself, one tab at a time")
            st.button("automatic: the whole video", width="stretch",
                      on_click=lambda: st.session_state.update(_auto_open=True, auto_scenes=projects.fresh_scenes(PROJECTS, 4)))
            st.caption("one button: music, image, headline, cover, video and text")
            st.button("batch: several videos at once", width="stretch",
                      on_click=lambda: st.session_state.update(_batch_open=True, _auto_open=False))
            st.caption("make a stack of whole videos in one go; each one gets the next free upload slot")

    def auto_form():
        st.markdown("**make a whole video automatically**")
        st.caption("One button: the app makes the music, picks an image from your library, writes the headline, builds the thumbnail "
                   "and the video, and writes the YouTube text. You check it afterwards.")
        f1, f2 = st.columns(2)
        auto_scenes = f1.multiselect("topic: scenes for the music and the picture", brand.SCENES, key="auto_scenes")
        auto_sound = f2.selectbox("sound", list(brand.PRESETS), key="auto_sound")
        g1, g2, g3 = st.columns(3)
        LENGTHS = {"about 1 hour (10 songs)": 10, "about 2 hours (20 songs)": 20, "short test (4 songs)": 4}
        auto_len = g1.selectbox("length", list(LENGTHS), key="auto_len")
        auto_names = g2.selectbox("track names", names.STYLES, key="auto_names")
        ai_on = bool(ai_token and not ai_mock)
        auto_improve = g3.checkbox("AI improves the music prompt", value=ai_on, disabled=not ai_on, key="auto_improve")
        n_songs = LENGTHS[auto_len]
        auto_up = st.checkbox("upload to YouTube when it is ready (private until the scheduled time, so you can still check it)",
                              value=False, disabled=not youtube.connected(), key="auto_upload",
                              help="Connect YouTube in settings first." if not youtube.connected() else None)
        st.caption(f"about {n_songs / 2 * 0.28 + (0.03 if ai_on else 0):.1f} credits · runs in the background, so you can leave the page · "
                   "needs your image library to be looked at (images page) · start one video at a time for the first tries")
        if st.button("make the video", type="primary", disabled=not (mock or token) or not auto_scenes):
            nm = projects.create_project(PROJECTS)
            pd_ = PROJECTS / nm
            mood_key_ = "groovy" if "groovy" in auto_sound else "calm"
            projects.set_meta(pd_, topic=auto_scenes, mood=mood_key_, style=brand.PRESETS[auto_sound])
            projects.start_auto(pd_, {"style": brand.PRESETS[auto_sound], "scenes": auto_scenes, "n_req": n_songs // 2, "minutes": 6.0,
                                      "model": brand.MODELS[0], "name_style": auto_names, "mood_key": mood_key_, "mock": mock,
                                      "improve_prompt": bool(auto_improve and ai_on), "use_ai": ai_on, "ai_model": ai_model,
                                      "crossfade": crossfade, "fade_in": 3.0, "fade_out": 6.0,
                                      "upload": bool(auto_up and youtube.connected())},
                                token, ai_token if ai_on else "")
            st.session_state["_auto_open"] = False
            st.toast(f"started {nm}")
            st.rerun()
        if st.button("cancel", key="auto_cancel"):
            st.session_state["_auto_open"] = False
            st.rerun()

    disk = health.check_disk(PROJECTS)
    if disk["status"] != "ok":
        st.warning(f"Disk space: {disk['detail']}. Archive or delete finished videos below.")
    todo = [("Suno key", bool(token)), ("image key", bool(img_token)), ("AI helper key", bool(ai_token)),
            ("image folder", bool(settings.library_dir()))]
    if not all(ok for _, ok in todo) and not st.session_state.get("_hide_start"):
        with st.container(key="card_start"):
            st.markdown("**getting started**")
            st.markdown("   ".join(f"{'✓' if ok else '○'} {lbl}" for lbl, ok in todo))
            st.caption("Until the keys are in, the app runs in practice mode: fake songs and images, no cost. "
                       "Add them in settings, then use “check my setup”.")
            s1, s2, _ = st.columns([1, 1, 2])
            s1.button("open settings", on_click=go, args=("settings",), type="primary", width="stretch")
            s2.button("hide this", on_click=lambda: st.session_state.update(_hide_start=True), width="stretch")
    if st.session_state.get("_auto_open"):
        with st.container(key="card_auto"):
            auto_form()

    def batch_form():
        st.markdown("**make a batch of videos**")
        st.caption("Each video gets its own scenes, its own picture from your library, a headline from your list, a cover, the video "
                   "and the YouTube text, and the next free upload slot (mon / wed / fri 15:00). Nothing is uploaded: you check "
                   "them first, then upload them from the videos page.")
        b1, b2 = st.columns([1, 2])
        n_vid = b1.select_slider("how many videos", [2, 3, 4, 5, 6, 8, 10, 12], 10, key="batch_n")
        b_sounds = b2.multiselect("sound (pick one or more)", list(brand.PRESETS), [list(brand.PRESETS)[0]], key="batch_sounds")
        b_mode = "each"
        if len(b_sounds) > 1:
            b_mode = st.radio("how to use these sounds", ["each", "mix"], horizontal=True, key="batch_sound_mode",
                              format_func=lambda m: "one sound per video, taking turns" if m == "each" else "mixed inside every video")
            if b_mode == "each":
                st.caption(" · ".join(f"video {k + 1}: {b_sounds[k % len(b_sounds)].split(' (')[0]}" for k in range(min(n_vid, 6)))
                           + (" · …" if n_vid > 6 else ""))
            else:
                st.caption("Every video gets songs in all these sounds, taking turns (song 1–2 in the first, 3–4 in the second, …).")
        ai_on = bool(ai_token and not ai_mock)
        B_LEN = {"about 1 hour (10 songs)": 10, "about 2 hours (20 songs)": 20, "short test (4 songs)": 4}
        with st.expander("more options"):
            c1, c2 = st.columns(2)
            b_len = c1.selectbox("length", list(B_LEN), key="batch_len")
            b_names = c2.selectbox("track names", names.STYLES, key="batch_names")
            b_improve = st.checkbox("AI improves the music prompt", value=ai_on, disabled=not ai_on or b_mode == "mix", key="batch_improve")
            b_shorts = st.select_slider("shorts per video (vertical, 30 seconds, slow zoom)", [0, 1, 2, 3], 0, key="batch_shorts",
                                        help="Made right after each video. Animated loops can be added later per video.")
        songs = B_LEN[b_len]
        credits = n_vid * (songs / 2 * brand.CREDITS["suno_request"] + (0.03 if ai_on else 0))
        db_ = {k: v for k, v in library.load_db().items() if v.get("analysis") and Path(k).exists()}
        free_imgs = len(set(db_) - set(library.used_images(PROJECTS)))
        hours = n_vid * (0.35 if songs <= 10 else 0.7) / 2 + n_vid * (0.33 if songs <= 10 else 0.66)
        st.markdown(f"**≈ {credits:.1f} credits** · about {hours:.1f} hours on this computer · {free_imgs} unused pictures in your library")
        if not db_:
            st.warning("The app has not looked at your pictures yet: open **images**, choose your folder and press look at the images first.")
        elif free_imgs < n_vid:
            st.warning(f"Only {free_imgs} pictures have not been used yet, so some videos will reuse one. Add pictures to your folder "
                       "and let the app look at them, or make a smaller batch.")
        st.caption("Keep the black window open and the computer awake until it is done. Your phone gets one message at the end, "
                   "and one for any video that stops.")
        go_ok = (mock or token) and bool(db_) and bool(b_sounds)
        if st.button(f"make {n_vid} videos", type="primary", disabled=not go_ok, key="batch_go"):
            mood_key_ = "groovy" if "groovy" in b_sounds[0] else "calm"
            try:
                made = projects.start_batch(PROJECTS, n_vid, {"style": brand.PRESETS[b_sounds[0]], "sounds": b_sounds, "sound_mode": b_mode,
                                                               "n_req": songs // 2, "minutes": 6.0,
                                                               "model": brand.MODELS[0], "name_style": b_names, "mood_key": mood_key_,
                                                               "mock": mock, "improve_prompt": bool(b_improve and ai_on), "use_ai": ai_on,
                                                               "ai_model": ai_model, "crossfade": crossfade, "fade_in": 3.0, "fade_out": 6.0,
                                                               "plan": True, "shorts": int(b_shorts)},
                                            token, ai_token if ai_on else "")
                st.session_state["_batch_open"] = False
                st.toast(f"started {len(made)} videos: {made[0]} to {made[-1]}")
                st.rerun()
            except RuntimeError as e:
                st.error(str(e))
        if st.button("cancel", key="batch_cancel_form", type="tertiary"):
            st.session_state["_batch_open"] = False
            st.rerun()

    if st.session_state.get("_batch_open"):
        with st.container(key="card_batch_form"):
            batch_form()

    def batch_card():
        bs = projects.batch_status()
        if bs["state"] == "none" or (not bs["running"] and time.time() - bs.get("finished", bs.get("updated", 0)) > 6 * 3600):
            return
        with st.container(key="card_batch"):
            if bs["running"]:
                st.markdown(f"**batch · {bs['done']} of {bs['total']} videos made**")
                parts = [projects.auto_status(Path(i)) for i in bs["items"]]
                st.progress(sum(p["progress"] if p["state"] not in ("failed", "needs_attention", "cancelled") else 1.0 for p in parts) / max(1, len(parts)))
                busy = [f"{Path(i).name}: {p['step_name'] or p['message']}" for i, p in zip(bs["items"], parts) if p["state"] == "running"]
                st.caption(" · ".join(busy) if busy else "starting…")
                if bs.get("cancel"):
                    st.caption("stopping: the videos being made stop at the next safe point")
                elif st.button("stop the batch", key="batch_stop", type="tertiary"):
                    projects.cancel_batch(); st.rerun()
            else:
                made, probs = bs.get("made", []), bs.get("problems", [])
                label = {"done": "batch done", "cancelled": "batch stopped", "interrupted": "batch stopped unexpectedly"}.get(bs["state"], "batch")
                st.markdown(f"**{label} · {len(made)} of {bs['total']} videos made**")
                if probs:
                    st.caption("need a look: " + ", ".join(probs) + " (press continue on their cards)")
                if bs["state"] == "interrupted":
                    st.caption("The window was closed or the computer went to sleep. Press continue on the cards of the unfinished videos.")
                if st.button("hide", key="batch_hide", type="tertiary"):
                    b_ = projects.read_json(projects.batch_file()); b_.update(finished=0, updated=0); projects.write_json(projects.batch_file(), b_)
                    st.rerun()

    st.fragment(run_every=5 if projects.batch_status()["running"] else None)(batch_card)()
    dups = fixes.duplicates(PROJECTS)
    if dups:
        with st.expander(f"{sum(len(n) - 1 for _, n in dups)} videos share a headline with another video", expanded=True):
            for q, nms in dups:
                st.markdown(f"**{q}** is used by {', '.join(nms)}")
            st.caption("The oldest video of each group keeps its headline. The others get a new one: the title, the first line of the "
                       "description, upload.txt and the thumbnail picture are updated too. Nothing else changes.")
            if st.button("give each of them a new headline", type="primary"):
                rep = fixes.make_unique(PROJECTS)
                st.toast("updated: " + ", ".join(f"{r['name']} → {r['new']}" for r in rep))
                st.rerun()
    PILL = {"new": ("#EFEFF4", "#4A4D78"), "making music": ("#E7E5FF", "#3A3790"), "making it": ("#E7E5FF", "#3A3790"),
            "making the video": ("#E7E5FF", "#3A3790"), "in the queue": ("#E7E5FF", "#3A3790"), "uploading": ("#E7E5FF", "#3A3790"),
            "needs a thumbnail": ("#FFF0D9", "#7A5420"), "needs the video": ("#FFF0D9", "#7A5420"),
            "needs youtube text": ("#FFE4EE", "#7A2C4C"), "needs attention": ("#FFD9D2", "#8A2A1A"),
            "ready": ("#DDF1E6", "#1F5B43"), "scheduled": ("#1E2050", "#FFFFFF"), "on youtube": ("#1E2050", "#FFFFFF")}
    GROUPS = {"all": None, "to finish": ("new", "needs a thumbnail", "needs the video", "needs youtube text", "needs attention"),
              "ready": ("ready",), "on youtube": ("scheduled", "on youtube"),
              "busy": ("making music", "making the video", "making it", "uploading", "in the queue")}
    all_items = projects.list_projects(PROJECTS)
    counts = {g: sum(1 for i in all_items if stages is None or i["stage"] in stages) for g, stages in GROUPS.items()}
    fa, fb, fc = st.columns([3.2, 1.6, 1], vertical_alignment="bottom")
    flt = fa.segmented_control("show", [g for g in GROUPS if g == "all" or counts[g]], key="vid_filter", default="all",
                               format_func=lambda g: f"{g} {counts[g]}", label_visibility="collapsed", required=True) or "all"
    query = fb.text_input("search", placeholder="search", key="vid_search", label_visibility="collapsed").strip().lower()
    new_video_menu(fc)

    def next_step(info):
        """The one thing to do next for this video: (label, kind, target). kind = open | render | upload | link | none."""
        stg = info["stage"]
        if stg == "new": return ("make the music", "open", "music")
        if stg == "needs a thumbnail": return ("make the cover", "open", "thumbnail")
        if stg == "needs the video": return ("make the video", "render", None)
        if stg == "needs youtube text": return ("write the text", "open", "video")
        if stg == "ready":
            return ("upload to YouTube", "upload", None) if youtube.connected() else ("check and upload", "open", "video")
        if stg in ("scheduled", "on youtube"): return ("open in YouTube Studio", "link", youtube.studio_url(info["youtube_id"]))
        if stg == "needs attention": return ("see what is missing", "open", "library")
        return ("", "none", None)

    def run_queue(kind, infos):
        spec = {"crossfade": crossfade, "fade_in": 3.0, "fade_out": 6.0} if kind == "render" else None
        added = projects.start_queue(kind, [i["path"] for i in infos], spec)
        st.toast((("making " if kind == "render" else "uploading ") + ", ".join(added)) if added else "nothing to do for these")

    def grid():
        items = projects.list_projects(PROJECTS)
        if not items:
            st.info("No videos yet. Press **new video** to start the first one.")
            return
        stages = GROUPS.get(flt)
        items = [i for i in items if (stages is None or i["stage"] in stages)
                 and (not query or query in (i["name"] + " " + i["quote"] + " " + i["title"]).lower())]
        if not items:
            st.info("No video matches this filter.")
            return
        sel = [i for i in items if st.session_state.get(f"sel_{i['name']}")]
        with st.container(key="bulkbar"):
            if not sel:
                b0, b1 = st.columns([5, 1], vertical_alignment="center")
                b0.caption(f"{len(items)} video{'s' if len(items) != 1 else ''} · tick a name to select it for bulk actions")
                if b1.button("select all", type="tertiary", key="sel_all", width="stretch"):
                    for i in items: st.session_state[f"sel_{i['name']}"] = True
                    st.rerun()
            else:
                up = [i for i in sel if i["stage"] == "ready"]
                mk = [i for i in sel if i["stage"] == "needs the video"]
                c0, c1, c2, c3, c4 = st.columns([1.3, 1.6, 1.4, 1.3, 0.8], vertical_alignment="center")
                c0.markdown(f"**{len(sel)} selected**")
                if c1.button(f"upload {len(up)} to YouTube", type="primary", disabled=not up or not youtube.connected(), width="stretch",
                             help=None if youtube.connected() else "Connect YouTube in settings first.", key="bulk_up"):
                    run_queue("upload", up); st.rerun()
                if c2.button(f"make {len(mk)} video{'s' if len(mk) != 1 else ''}", disabled=not mk, width="stretch", key="bulk_mk",
                             help="Made one after another, so the computer stays usable."):
                    run_queue("render", mk); st.rerun()
                with c3.popover("more", width="stretch"):
                    if st.button("film dust on", width="stretch", key="bulk_dust_on"):
                        for i in sel: projects.set_meta(i["path"], film_look=dict(video.LOOK_DEFAULT))
                        st.toast("film dust on: used the next time each video is made"); st.rerun()
                    if st.button("film dust off", width="stretch", key="bulk_dust_off"):
                        for i in sel: projects.set_meta(i["path"], film_look={})
                        st.rerun()
                    if st.button(f"move {len(sel)} to the trash", width="stretch", key="bulk_trash"):
                        st.session_state["_bulk_trash"] = True
                    if st.session_state.get("_bulk_trash"):
                        st.warning("Move them to the trash? You can restore them from the trash below.")
                        if st.button("yes, move them", type="primary", key="bulk_trash_yes"):
                            done, busy = [], []
                            for i in sel:
                                try:
                                    projects.trash_project(i["path"]); done.append(i["name"])
                                except RuntimeError:
                                    busy.append(i["name"])
                                st.session_state.pop(f"sel_{i['name']}", None)
                            st.session_state.pop("_bulk_trash", None)
                            st.toast(f"moved {len(done)} to the trash" + (f" · still busy: {', '.join(busy)}" if busy else ""))
                            st.rerun()
                if c4.button("clear", type="tertiary", width="stretch", key="sel_clear"):
                    for i in items: st.session_state.pop(f"sel_{i['name']}", None)
                    st.session_state.pop("_bulk_trash", None)
                    st.rerun()
        rows = [st.columns(3) for _ in range((len(items) + 2) // 3)]                 # one row at a time, so cards line up
        for i, info in enumerate(items):
            nm = info["name"]
            with rows[i // 3][i % 3], st.container(key=f"card_proj_{nm}"):
                if info["cover"]:
                    theme.show_image(info["cover"], width="stretch")
                else:
                    st.markdown('<div class="sg-cover-empty">no cover yet</div>', unsafe_allow_html=True)
                h1, h2 = st.columns([4, 1], vertical_alignment="center")
                h1.checkbox(nm, key=f"sel_{nm}")
                with h2.popover("⋯", width="stretch"):
                    if info["has_video"] and (info["path"] / "tracks").is_dir() and not projects.is_busy(info["path"]):
                        if st.button("free up space", key=f"free_{nm}", width="stretch",
                                     help="Deletes the songs and working images of this finished video. The video, thumbnail and upload text stay."):
                            try:
                                st.toast(f"freed {projects.free_space(info['path']):.0f} MB from {nm}."); st.rerun()
                            except RuntimeError as e:
                                st.error(str(e))
                    if st.button("move to the trash", key=f"del_{nm}", width="stretch"):
                        st.session_state["_confirm_delete"] = nm
                    if st.session_state.get("_confirm_delete") == nm:
                        st.caption("Its songs, cover and video go with it. You can restore it from the trash.")
                        if st.button("yes, move it", key=f"delyes_{nm}", type="primary", width="stretch"):
                            try:
                                projects.trash_project(info["path"])
                                st.session_state.pop("_confirm_delete", None)
                                if st.session_state.get("project") == nm:
                                    st.session_state.update(project=projects.next_project_name(PROJECTS), tracks=[], fix_results={})
                                st.rerun()
                            except RuntimeError as e:
                                st.error(str(e))
                if info["quote"]:
                    st.markdown(f'<div class="sg-proj-quote">{html.escape(info["quote"])}</div>', unsafe_allow_html=True)
                bg, fg = PILL.get(info["stage"], ("#EFEFF4", "#4A4D78"))
                meta_bits = [f'{info["tracks"]} tracks · {round(info["seconds"] / 60)} min']
                if info["schedule"]:
                    meta_bits.append(("publishes " if info["stage"] != "on youtube" else "published ") + info["schedule"][5:].replace("-", "/"))
                if info["film"]:
                    meta_bits.append("film dust")
                st.markdown(f'<span class="sg-pill" style="background:{bg};color:{fg}">{info["stage"]}</span> '
                            f'<span class="sg-proj-meta">{html.escape(" · ".join(meta_bits))}</span>', unsafe_allow_html=True)
                if info["job"]["running"]:
                    st.progress(info["job"]["progress"], text=f"{info['job']['done']} of {info['job']['total']} requests")
                if info["render"]["running"]:
                    st.progress(info["render"]["progress"], text=info["render"]["message"] or "making the video")
                if info["yt"]["running"]:
                    st.progress(info["yt"]["progress"], text=info["yt"]["message"] or "uploading")
                if info["yt"]["state"] == "failed":
                    show_error(info["yt"]["error"], "warning", prefix="Upload stopped. ")
                au = info["auto"]
                if au["running"]:
                    st.progress(au["progress"], text=f"step {au['step'] + 1} of {len(projects.AUTO_STEPS)} · {au['step_name']}")
                    st.button("cancel", key=f"cancel_auto_{nm}", on_click=projects.cancel_job, args=(info["path"],), type="tertiary")
                elif au["state"] in ("needs_attention", "failed", "interrupted"):
                    if au["error"] and au["state"] == "needs_attention":
                        st.warning(au["error"])
                    else:
                        show_error(au["error"] or "The job stopped unexpectedly (the window was closed or the computer went to sleep).", "warning")
                    if st.button("continue", key=f"resume_auto_{nm}", width="stretch"):
                        try:
                            projects.start_auto(info["path"], projects.read_json(info["path"] / projects.AUTO)["spec"], token, ai_token)
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))
                label, kind, target = next_step(info)
                if kind == "link":
                    st.link_button(label, target, width="stretch", type="primary")
                elif kind != "none" and not au["running"]:
                    if st.button(label, key=f"next_{nm}", type="primary", width="stretch"):
                        if kind == "open":
                            st.session_state.update(project=nm, tracks=[], fix_results={}, step=target)
                            st.session_state.pop("_job_was_running", None)
                        else:
                            run_queue(kind, [info])
                        st.rerun()
                if st.button("open video", key=f"open_{nm}", width="stretch", type="secondary"):
                    open_project(nm, info["stage"]); st.rerun()

    running_any = any(p["job"]["running"] or p["render"]["running"] or p["auto"]["running"] or p["yt"]["running"] for p in all_items)
    st.fragment(run_every=4 if running_any else None)(grid)()
    st.caption(f"credits used this month ≈ {projects.credits_this_month():.1f} · {disk['detail']}")

    trashed = projects.list_trash(PROJECTS)
    if trashed:
        with st.expander(f"trash ({len(trashed)})"):
            st.caption("Deleted videos stay here until you empty the trash, so a mistake can be undone. They still take up disk space.")
            for tr in trashed:
                t1, t2, t3 = st.columns([3, 1, 1.3])
                t1.markdown(f"**{tr['name']}** {('· ' + tr['quote']) if tr['quote'] else ''}  \n"
                            f"<span class='sg-proj-meta'>{tr['tracks']} tracks · {tr['size_mb']:.0f} MB · deleted {tr['deleted']}</span>",
                            unsafe_allow_html=True)
                if t2.button("restore", key=f"restore_{tr['folder'].name}"):
                    st.toast(f"restored as {projects.restore_project(tr['folder'], PROJECTS)}")
                    st.rerun()
                if t3.button("delete forever", key=f"forever_{tr['folder'].name}"):
                    st.session_state["_confirm_forever"] = tr["folder"].name
                if st.session_state.get("_confirm_forever") == tr["folder"].name:
                    st.error(f"Delete {tr['name']} for good? This cannot be undone.")
                    z1, z2 = st.columns(2)
                    if z1.button("yes, delete for good", key=f"foreveryes_{tr['folder'].name}", type="primary"):
                        projects.delete_forever(tr["folder"])
                        st.session_state.pop("_confirm_forever", None)
                        st.rerun()
                    if z2.button("keep it", key=f"foreverno_{tr['folder'].name}"):
                        st.session_state.pop("_confirm_forever", None)
                        st.rerun()

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
                    projects.add_cost(name, "ai", cost, False)
                    st.session_state["_ai_note"] = "improved by AI" + (f" · {cost:.4f} credits" if cost else "")
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
            saved_topic = [s for s in (projects.meta(pdir).get("topic") or []) if s in brand.SCENES]
            scenes = c3.multiselect("scene flavours (rotated)", brand.SCENES, saved_topic or projects.fresh_scenes(PROJECTS),
                                    key=f"w_{name}_scenes", help="Each new video starts with its own mix. The requests take turns "
                                                                 "through the scenes you pick here.")
            if scenes and scenes != saved_topic:
                projects.set_meta(pdir, topic=scenes)                     # remembered for this video (and used by the cover tab)
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

if step == "music":
    with st.container(key="card_playlist"):
            st.markdown("**the tracks**")
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
                theme.show_image(library.safe_thumb(p) or p.with_name("missing"), width="stretch")
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

if step == "thumbnail":
    ensure_quote()
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
    has_source = bool(st.session_state.get("cover")) or (pdir / "cover_source.png").exists() or (
        imgs_dir.exists() and any(imgs_dir.glob("*_16x9.png")))
    src_box = st.expander("change the picture", expanded=False) if has_source else st.container()
    with src_box:
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
                            theme.show_image(library.safe_thumb(Path(r["path"])) or Path(r["path"]).with_name("missing"), width="stretch")
                            st.caption(r["analysis"].get("description", "") or Path(r["path"]).name)
                            st.markdown('<span class="sg-proj-meta">' + " · ".join(r["why"]) + "</span>", unsafe_allow_html=True)
                            if st.button("use this one", key=f"use_lib_{name}_{Path(r['path']).stem}"):
                                assign_image(r["path"], r["analysis"], mood_, topic_)
                                st.rerun()
        with st.container(key="card_source"):
            c1, c2 = st.columns(2)
            up = c1.file_uploader("image (16:9, ≥1920px, no text in the image)", type=["png", "jpg", "jpeg", "webp"])
            fixed = sorted(p.name for p in imgs_dir.glob("*_16x9.png")) if imgs_dir.exists() else []
            pick = c2.selectbox("…or pick an image you made 16:9 (switch below)", ["—"] + fixed)
    src_img, src_name = None, ""
    lay_saved = pm_.get("cover_layout") or {}
    if up:
        st.session_state["cover"] = (up.name, up.getvalue())
        src_name, src_img = up.name, Image.open(io.BytesIO(up.getvalue()))
    elif pick != "—":
        src_name, src_img = pick, Image.open(imgs_dir / pick)
    elif st.session_state.get("cover"):
        src_name, data = st.session_state["cover"]; src_img = Image.open(io.BytesIO(data))
    elif (pdir / "cover_source.png").exists():                       # the picture this cover was made from last time
        src_name, src_img = lay_saved.get("source_name") or "the picture of this cover", Image.open(pdir / "cover_source.png")
    elif fixed:                                                       # an image prepared for this video (library or photo fixer)
        newest = max(fixed, key=lambda n: (imgs_dir / n).stat().st_mtime)
        src_name, src_img = newest, Image.open(imgs_dir / newest)
    if src_img is None:
        st.info("Add an image above, or make a vertical photo 16:9 with the switch below.")
    else:
        src_img.load()
        for w in T.image_warnings(src_img): st.warning(w)
        st.caption(f"using {src_name}. Check the image for garbled Japanese, signatures, brand logos, number plates; "
                   "if it looks like a Hiroshi Nagai painting, do a reverse image search.")
        prev = st.container(key="card_preview")          # shown first, filled once the settings are known
        with st.container(key="card_settings"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                quote = sticky(st.text_input, "quote", "quote", pm_.get("quote") or "you've got this.")
                for w in T.check_quote(quote): st.caption(f":orange[{w}]")
                if quote in used_quotes(name):
                    st.caption(":orange[another video already uses this headline: press new headline]")
                hb1, hb2 = st.columns(2)
                hb1.button("new headline", on_click=lambda: st.session_state.update(_headline_req="random"),
                           help="A fresh headline that fits the mood and has not been used in another video.")
                hb2.button("match to image", on_click=lambda: st.session_state.update(_headline_req="ai"),
                           disabled=not (ai_token and not ai_mock), help="The AI writes a headline for this picture.")
                subline = sticky(st.text_input, "subline (optional)", "subline", "")
            with c2:
                cyber = sticky(st.toggle, "night city style", "cyber", bool(lay_saved.get("cyber", False)))
                tag = st.text_input("tag box", lay_saved.get("tag", "CYBERPUNK SYNTHWAVE"), disabled=not cyber, key=f"w_{name}_tag")
                logo = st.selectbox("logo colour", ["auto", "navy", "white"], ["auto", "navy", "white"].index(lay_saved.get("logo", "auto")),
                                    key=f"w_{name}_logo")
                hv = sticky(st.toggle, "headline on the video image", "hv", projects.meta(pdir).get("headline_on_video", True),
                            help="The picture under the music uses the thumbnail design, headline included.")
            with c3:
                anchor = st.selectbox("position", T.ANCHORS, T.ANCHORS.index(lay_saved.get("anchor", "top-center")
                                                                              if lay_saved.get("anchor") in T.ANCHORS else "top-center"),
                                      key=f"w_{name}_anchor",
                                      help=f"The house style is top-center. The calmest area of this image is {T.suggest_anchor(src_img, quote)}.")
                size = sticky(st.slider, "text size", "size", float(lay_saved.get("size", 1.5)), min_value=0.5, max_value=1.6, step=0.05,
                              help="1.50 is the house style. Longer headlines shrink by themselves if they would not fit.")
            with c4:
                dx = st.slider("nudge x", -300, 300, int(lay_saved.get("dx", 0)), 5, key=f"w_{name}_dx")
                dy = st.slider("nudge y", -300, 300, int(lay_saved.get("dy", 0)), 5, key=f"w_{name}_dy")
        lay_ = T.Layout(anchor, size, dx, dy)
        thumb = T.render_thumbnail(src_img, quote, lay_, cyber, tag, subline, logo_mode=logo)
        still = T.render_still(src_img, cyber, logo_mode=logo, quote=quote if hv else None, layout=lay_, tag=tag, subline=subline)
        with prev:
            a, b = st.columns([1.55, 1])
            a.image(thumb, caption="thumbnail · 1280×720")
            b.image(still, caption="video picture · 1920×1080 · " + ("with headline" if hv else "no headline"))
            zbuf = io.BytesIO()
            with zipfile.ZipFile(zbuf, "w") as z:
                for nm, pic in (("thumbnail.png", thumb), ("still.png", still)):
                    pb = io.BytesIO(); pic.save(pb, "PNG"); z.writestr(nm, pb.getvalue())
            sig = "|".join(map(str, (src_name, quote, anchor, size, dx, dy, cyber, logo, hv, subline, tag if cyber else "")))
            is_saved = (pm_.get("cover_sig") == sig) and (pdir / "thumbnail.png").exists()
            b1, b2, b3 = st.columns([1.1, 1, 2], vertical_alignment="center")
            if b1.button("✓ saved" if is_saved else "save the cover", type="secondary" if is_saved else "primary", disabled=is_saved,
                         width="stretch"):
                pdir.mkdir(parents=True, exist_ok=True)
                thumb.save(pdir / "thumbnail.png"); still.save(pdir / "still.png")
                if src_name != lay_saved.get("source_name") or not (pdir / "cover_source.png").exists():
                    src_img.convert("RGB").save(pdir / "cover_source.png")
                projects.set_meta(pdir, quote=quote, quote_placeholder=False, headline_on_video=bool(hv), cover_sig=sig,
                                  cover_layout={"source_name": src_name, "anchor": anchor, "size": size, "dx": dx, "dy": dy,
                                                "cyber": bool(cyber), "logo": logo, "tag": tag})
                st.rerun()
            b2.download_button("download both", zbuf.getvalue(), "softgrind_cover.zip", "application/zip", type="tertiary")
            if not is_saved and (pdir / "thumbnail.png").exists() and pm_.get("cover_sig"):
                b3.markdown('<span class="sg-unsaved">changes not saved yet: the video still uses the old cover</span>', unsafe_allow_html=True)
            elif is_saved and (pdir / "video.mp4").exists() and (pdir / "still.png").stat().st_mtime > (pdir / "video.mp4").stat().st_mtime + 1:
                b3.markdown('<span class="sg-unsaved">saved. Make the video again (video tab) to use the new picture.</span>', unsafe_allow_html=True)
    with st.expander("bulk: many images at once (thumbnails + stills + contact sheet)"):
        bq = st.text_area("quotes, one per line (matched to images in name order; last one repeats)", "you've got this.")
        files = st.file_uploader("images", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="bulk")
        if files and st.button("render all"):
            qs = [q.strip() for q in bq.splitlines() if q.strip()] or ["soft grind."]
            zbuf, sheet_items = io.BytesIO(), []
            with zipfile.ZipFile(zbuf, "w") as z:
                for i, f in enumerate(sorted(files, key=lambda f: f.name)):
                    im = Image.open(f); q = qs[min(i, len(qs) - 1)]
                    th = T.render_thumbnail(im, q, T.Layout()); stl = T.render_still(im, quote=q, layout=T.Layout())
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

if step == "thumbnail":
    with st.container(key="card_fix"):
        fix_on = st.toggle("need a different picture? make a vertical or small photo 16:9", key="fix_on",
                           help="Fills the sides of a vertical photo, free (blur) or with an AI model.")
    if fix_on:
        with st.container(key="card_fix_images"):
            st.caption("Drop in your photos. The free option fills the sides with a blurred copy; the AI option "
                       "extends the scene (like your Gemini step). Pick the ones you like and they show up on the cover tab.")
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
                            if not img_mock:
                                projects.add_cost(name, "image", brand.CREDITS["image_edit"], True)
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
                                st.success(f"saved {out_path.name}: now pick it in the list at the top of the cover tab")

if step == "video":
    ensure_quote()
    saved = projects.meta(pdir)
    video_path = pdir / "video.mp4"
    left, right = st.columns([1.35, 1], gap="large")

    # ---- the text generator: drawn under the form, but its values are needed first
    with right:
        publish_slot = st.container(key="card_publish")
        form_slot = st.container(key="card_form")
        with st.expander("write the text for me (settings)"):
            if len(tracks) < 3:
                st.warning("Add at least 3 tracks (music tab): the tracklist needs real durations for chapters.")
            c1, c2 = st.columns(2)
            with c1:
                quote_m = sticky(st.text_input, "quote", "quote", saved.get("quote") or "you've got this.")
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
            bt1, bt2 = st.columns(2)
            bt1.button("write unique text with AI", type="primary", disabled=not (ai_token and not ai_mock),
                       on_click=lambda: st.session_state.update(_regen_req=name, _regen_mode="ai"),
                       help="The AI writes a title phrase, subline, scene paragraph, pinned comment and question for THIS video, "
                            "different from your earlier videos. The quote stays first in the title.")
            bt2.button("fill from the settings above", on_click=lambda: st.session_state.update(_regen_req=name, _regen_mode="template"))
            st.caption("Either button replaces the text in the form. Edit it afterwards, then press save.")
        if (pl, sc, quote_m) != (saved.get("playlist_name"), saved.get("scenario"), saved.get("quote")):
            projects.set_meta(pdir, playlist_name=pl, scenario=sc, quote=quote_m,
                              quote_placeholder=saved.get("quote_placeholder", False) and quote_m == saved.get("quote"))
            saved = projects.meta(pdir)
        gen = {"title": metadata.make_title(tstyle, quote_m, pl, sc, emoji),
               "description": metadata.make_description(quote_m, subline_m, scene, tracks, use, artist, question,
                                                        brand.MOODS[mood], crossfade) if tracks else "",
               "tags": ", ".join(metadata.make_tags()), "pinned": pinned_choice}
        vkey = f"_text_v_{name}"
        if st.session_state.pop("_regen_req", None) == name:       # "write it for me": new widgets, filled with fresh text
            seed_new = gen
            if st.session_state.pop("_regen_mode", "template") == "ai":
                an_ = (library.load_db().get(saved.get("library_image", ""), {}) or {}).get("analysis") or {}
                seed_new, parts_, cost_, by_ai_ = texts.compose(
                    quote=quote_m, tracks=tracks, mood=saved.get("mood") or "calm", topic=saved.get("topic") or brand.SCENES[:4],
                    image_description=an_.get("description", ""), playlist_name=pl, scenario=sc, crossfade=crossfade,
                    idx=len(projects.project_dirs(PROJECTS)), previous=texts.previous_parts(PROJECTS, exclude=name),
                    ai_client=ai.AIClient(ai_token, ai_model))
                projects.set_meta(pdir, text_parts=parts_, text_by_ai=by_ai_)
                projects.add_cost(name, "ai", cost_, False)
                st.toast(("written by the AI" + (f" · {cost_:.3f} credits" if cost_ else "")) if by_ai_ else
                         "The AI text did not pass the checks, so the rotating templates were used instead.")
            st.session_state[vkey] = st.session_state.get(vkey, 0) + 1
            st.session_state[f"_seed_{name}"] = seed_new
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
        status_slot = st.empty()
        title = st.text_input("Title", init["title"], key=f"w_{name}_title{ver}", max_chars=100)
        st.caption(f"{len(title)}/100 characters · the first 60 matter most")
        desc = st.text_area("Description", init["description"], height=220, key=f"w_{name}_desc{ver}")
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
        base = {"title": init["title"], "description": init["description"], "tags": init["tags"], "pinned": init["pinned"],
                "schedule": f"{_slot:%Y-%m-%d %H:%M}"}
        has_saved = bool(saved.get("title"))
        edited = any(cur[k] != base[k] for k in cur)                    # you (or a "write it for me" button) changed the text

        def save_now(prev=None):
            keep = {}
            if prev is not None:                                        # the replaced version stays available for "undo"
                keep = {"text_history": ((prev.get("text_history") or [])[-9:]
                                         + [{**{k: prev.get(k, "") for k in cur}, "at": time.strftime("%d %b %H:%M")}])}
            projects.set_meta(pdir, **cur, **keep)
            (pdir / "upload.txt").write_text(metadata.upload_txt(title, desc, [t.strip() for t in tags.split(",") if t.strip()],
                                                                 pinned, cur["schedule"]), encoding="utf-8")

        differs = any(cur[k] != saved.get(k) for k in cur)
        if differs and (has_saved or edited):                           # autosave: nothing you type is lost
            save_now(saved if has_saved else None)
            saved = projects.meta(pdir)
            differs = False
        if not differs:
            status_slot.markdown('<span class="sg-saved">✓ all changes saved</span>', unsafe_allow_html=True)
        else:
            status_slot.markdown('<span class="sg-unsaved">not saved yet: this is a suggestion</span>', unsafe_allow_html=True)
            if st.button("use this text", type="primary"):
                save_now()
                st.rerun()
        hist = saved.get("text_history") or []
        if hist:
            if st.button(f"undo the last text change ({hist[-1]['at']})"):
                last = hist[-1]
                projects.set_meta(pdir, **{k: last[k] for k in cur}, text_history=hist[:-1])
                st.session_state[f"_seed_{name}"] = {k: last[k] for k in ("title", "description", "tags", "pinned")}
                st.session_state[vkey] = st.session_state.get(vkey, 0) + 1
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
                if still_ok and (pdir / "still.png").stat().st_mtime > video_path.stat().st_mtime + 1:
                    st.warning("The video picture (or its headline) changed after this video was built. Press **make the video again** to update it.")
                prev_path = pdir / "preview.mp4"
                if not prev_path.exists() or prev_path.stat().st_mtime < video_path.stat().st_mtime:
                    try:
                        video.make_preview(video_path, prev_path)
                    except Exception:
                        prev_path = None
                full = st.session_state.get(f"_full_{name}") or prev_path is None
                st.video(str(video_path if full else prev_path))
                mb = video_path.stat().st_size / 1_000_000
                st.caption(f"{metadata.fmt_ts(metadata.total_length([t['duration'] for t in tracks], crossfade))} · {mb:.0f} MB · 1920×1080"
                           + ("" if full else " · showing the first 90 seconds"))
                v1, v2 = st.columns(2)
                if prev_path is not None:
                    v1.button("quick preview" if full else "play the full video", width="stretch", type="tertiary",
                              on_click=lambda: st.session_state.update({f"_full_{name}": not full}))
                v2.download_button("download video", data=lambda: video_path.read_bytes(), file_name=f"{name}.mp4", mime="video/mp4",
                                   width="stretch", type="tertiary")
            else:
                if still_ok:
                    theme.show_image(pdir / "still.png", width="stretch")
                else:
                    st.markdown('<div class="sg-cover-empty">no video yet</div>', unsafe_allow_html=True)
                st.markdown(("✓" if tracks else "✗") + f" tracks ({len(tracks)}) &nbsp; " + ("✓" if still_ok else "✗")
                            + " video picture (cover tab)")
            if projects.credits_for(name):
                st.caption(f"credits used for this video: ≈ {projects.credits_for(name):.1f}")
            with st.expander("video settings"):
                f_in = st.number_input("fade in (s)", 0.0, 10.0, 3.0, 0.5)
                f_out = st.number_input("fade out (s)", 0.0, 20.0, 6.0, 0.5)
                st.caption(f"Crossfade {crossfade:g}s (set under keys and settings) · loudness −14 LUFS.")
            with st.expander("film dust"):
                film_look_ui(pdir, name)
            if not rs["running"]:
                if st.button("make the video again" if video_path.exists() else "make the video", type="secondary" if video_path.exists() else "primary",
                             disabled=not (tracks and still_ok), width="stretch"):
                    try:
                        projects.start_render(pdir, crossfade, f_in, f_out)
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))
            if (pdir / "thumbnail.png").exists():
                with st.expander("thumbnail"):
                    theme.show_image(pdir / "thumbnail.png", width="stretch")
                    st.download_button("download thumbnail", data=lambda: (pdir / "thumbnail.png").read_bytes(),
                                       file_name=f"{name}-thumbnail.png", mime="image/png", width="stretch", type="tertiary")
            with st.expander("tracklist"):
                st.code(metadata.tracklist_text(tracks, crossfade) if tracks else "no tracks yet", language=None)
        with st.container(key="card_shorts"):
            shorts_ui(pdir, name)

    # ---- publish (right, top): filled last, so it sees the text that was just saved
    with publish_slot:
        st.markdown("**publish**")
        if video_path.exists() and not projects.render_status(pdir)["running"]:
            yt_panel(pdir)
        else:
            st.caption("Make the video first (left). Then it can go to YouTube from here.")



if step == "planning":
    import calendar as _cal
    items = projects.list_projects(PROJECTS)
    today = dt.date.today()
    st.session_state.setdefault("_plan_month", (today.year, today.month))
    py, pm = st.session_state["_plan_month"]
    plan = planning.by_day(items)
    PCOL = {"scheduled": ("#1E2050", "#FFFFFF"), "on youtube": ("#1E2050", "#FFFFFF"), "ready": ("#DDF1E6", "#1F5B43"),
            "uploading": ("#E7E5FF", "#3A3790"), "in the queue": ("#E7E5FF", "#3A3790")}

    nav = st.container(key="plan_nav")
    n1, n2, n3, n4, n5 = nav.columns([0.5, 2.2, 0.5, 0.8, 2.6], vertical_alignment="center")
    if n1.button("‹", key="plan_prev", width="stretch", help="previous month"):
        st.session_state["_plan_month"] = planning.shift_month(py, pm, -1); st.rerun()
    n2.markdown(f'<div class="sg-cal-month">{_cal.month_name[pm].lower()} {py}</div>', unsafe_allow_html=True)
    if n3.button("›", key="plan_next", width="stretch", help="next month"):
        st.session_state["_plan_month"] = planning.shift_month(py, pm, 1); st.rerun()
    if n4.button("today", key="plan_today", type="tertiary", width="stretch"):
        st.session_state["_plan_month"] = (today.year, today.month); st.rerun()
    view = n5.segmented_control("view", ["month", "list"], default="month", key="plan_view", required=True,
                                label_visibility="collapsed") or "month"
    weeks = planning.month_weeks(py, pm)
    in_month = [d for w in weeks for d in w if d.month == pm]
    n_planned = sum(len(plan.get(d, [])) for d in in_month)
    n_free = sum(1 for d in in_month if planning.is_free_slot(d, plan))
    st.caption(f"this month: {n_planned} video{'s' if n_planned != 1 else ''} planned · {n_free} free slot{'s' if n_free != 1 else ''}")

    def chip(v):
        bg, fg = PCOL.get(v["stage"], ("#FFF0D9", "#7A5420"))         # not finished yet: amber, so it stands out
        tip = html.escape(f'{v["name"]} · {v["stage"]}')
        return (f'<div class="sg-cal-item" style="background:{bg};color:{fg}" title="{tip}">'
                f'<b>{v["when"]:%H:%M}</b> {html.escape(v["quote"] or v["name"])}</div>')

    if view == "month":
        with st.container(key="calendar"):
            st.markdown('<div class="sg-cal-head">' + "".join(f"<div>{d}</div>" for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"))
                        + "</div>", unsafe_allow_html=True)
            cells = []
            for week in weeks:
                for d in week:
                    cls = "sg-cal-day" + (" other" if d.month != pm else "") + (" today" if d == today else "") + (" past" if d < today else "")
                    body = "".join(chip(v) for v in plan.get(d, []))
                    if not body and planning.is_free_slot(d, plan):
                        body = '<div class="sg-cal-free">free · 15:00</div>'
                    cells.append(f'<div class="{cls}"><div class="n">{d.day}</div>{body}</div>')
            st.markdown('<div class="sg-cal-grid">' + "".join(cells) + "</div>", unsafe_allow_html=True)
            st.markdown('<div class="sg-cal-legend"><span style="background:#1E2050"></span>on youtube '
                        '<span style="background:#DDF1E6"></span>ready to upload <span style="background:#FFF0D9"></span>not finished yet '
                        '<span class="free"></span>free slot</div>', unsafe_allow_html=True)

    # the videos of this month (month view) or everything coming up (list view), each with open
    if view == "month":
        rows = [v for d in sorted(plan) if d.year == py and d.month == pm for v in plan[d]]
        head = "planned this month"
    else:
        rows = [v for d in sorted(plan) if d >= today for v in plan[d]]
        head = "coming up"
    with st.container(key="card_plan_list"):
        st.markdown(f"**{head}**")
        if not rows:
            st.caption("Nothing planned here yet.")
        for v in rows:
            r1, r2, r3, r4 = st.columns([1.3, 2.6, 1.3, 0.9], vertical_alignment="center")
            r1.markdown(f'<span class="sg-proj-meta"><b>{v["when"]:%a %d %b}</b> · {v["when"]:%H:%M}</span>'.lower(), unsafe_allow_html=True)
            bg, fg = PCOL.get(v["stage"], ("#FFF0D9", "#7A5420"))
            r2.markdown(f'**{html.escape(v["quote"] or v["name"])}** <span class="sg-proj-meta">{html.escape(v["name"])}</span>',
                        unsafe_allow_html=True)
            r3.markdown(f'<span class="sg-pill" style="background:{bg};color:{fg}">{v["stage"]}</span>', unsafe_allow_html=True)
            if r4.button("open", key=f"plan_open_{v['name']}", width="stretch"):
                open_project(v["name"], v["stage"]); st.rerun()

    # videos without a date: give each one a free slot in two clicks
    todo = planning.unplanned(items)
    with st.container(key="card_plan_todo"):
        st.markdown(f"**not planned yet** · {len(todo)}")
        if not todo:
            st.caption("Every video has a date.")
        else:
            st.caption("Pick a free slot for a video. Videos already on YouTube keep the date YouTube has.")
            slots = planning.free_slots(items, 10)
            for k, v in enumerate(todo):
                u1, u2, u3, u4 = st.columns([2.4, 1.2, 1.8, 1], vertical_alignment="center")
                u1.markdown(f'**{html.escape(v["quote"] or v["name"])}** <span class="sg-proj-meta">{html.escape(v["name"])}</span>',
                            unsafe_allow_html=True)
                bg, fg = PCOL.get(v["stage"], ("#FFF0D9", "#7A5420"))
                u2.markdown(f'<span class="sg-pill" style="background:{bg};color:{fg}">{v["stage"]}</span>', unsafe_allow_html=True)
                choice = u3.selectbox("slot", slots, index=min(k, len(slots) - 1), key=f"plan_slot_{v['name']}",
                                      format_func=lambda w: w.strftime("%a %d %b · %H:%M").lower(), label_visibility="collapsed")
                if u4.button("plan", key=f"plan_set_{v['name']}", type="primary", width="stretch"):
                    try:
                        planning.assign(v["path"], choice)
                        st.toast(f"{v['name']} goes out {choice:%a %d %b %H:%M}".lower()); st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))

# ---------------- menu, tabs and phone navigation: filled last so they show fresh status ----------------
proj_count = len(projects.project_dirs(PROJECTS))
_lf = library.scan(settings.library_dir())
_ldb = library.load_db()
lib_looked = sum(1 for p in _lf if not library.needs_analysis(_ldb, p))
keys_set = sum(bool(x) for x in (token, img_token, ai_token))
job_now = projects.job_status(pdir)
render_now = projects.render_status(pdir)
cover_done = (pdir / "thumbnail.png").exists()
yt_done = bool(projects.meta(pdir).get("title")) and (pdir / "upload.txt").exists()
video_done = (pdir / "video.mp4").exists()
n_tracks_now = len(projects.audio_files(tracks_dir))
_upcoming = sorted(w for w in (planning.parse(p["schedule"]) for p in projects.list_projects(PROJECTS)) if w and w > dt.datetime.now())
plan_n, plan_next = len(_upcoming), (_upcoming[0].strftime("%a %d %b").lower() if _upcoming else "")
MENU_SUB = {"projects": f"{proj_count} video{'s' if proj_count != 1 else ''}" if proj_count else "start your first video",
            "planning": (f"{plan_n} planned · next {plan_next}" if plan_n else "nothing planned yet"),
            "library": f"{lib_looked} of {len(_lf)} looked at" if _lf else "choose your folder",
            "settings": f"{keys_set} of 3 keys set"}
with menu_slot:
    for sid, label in MENU:
        active = step == sid or (sid == "projects" and step in VIDEO_STEPS)
        st.button(label, key=f"menu_{sid}", type="primary" if active else "secondary", width="stretch", on_click=go, args=(sid,))
        st.markdown(f'<div class="sg-step-sub">{MENU_SUB[sid]}</div>', unsafe_allow_html=True)
with topnav_slot:                                                                           # visible on phones only (CSS)
    for col, (sid, label) in zip(st.columns(len(MENU)), MENU):
        col.button(label, key=f"topnav_{sid}", type="primary" if (step == sid or (sid == "projects" and step in VIDEO_STEPS)) else "secondary",
                   width="stretch", on_click=go, args=(sid,))
if tabs_slot is not None:
    done_map = {"music": n_tracks_now > 0 and not job_now["running"], "thumbnail": cover_done, "video": video_done and yt_done}
    extra = {"music": f" · {job_now['done']}/{job_now['total']}" if job_now["running"] else "",
             "video": f" · {int(render_now['progress'] * 100)}%" if render_now["running"] else ""}
    with tabs_slot:
        for col, (sid, label) in zip(st.columns(3), TABS):
            col.button(f"{'✓ ' if done_map[sid] else ''}{label}{extra.get(sid, '')}", key=f"tab_{sid}",
                       type="primary" if step == sid else "secondary", width="stretch", on_click=go, args=(sid,))
