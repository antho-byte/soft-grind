"""soft grind. look for the Streamlit app: sand background, Abril Fatface headings, coral accents, sunset strip.

Pure CSS injected from Python, so it works without any Streamlit config file (and survives the auto-updater).
The Abril Fatface font is embedded, so it also works offline.
"""
import base64
import html
from pathlib import Path

import streamlit as st
from PIL import Image

from .brand import FONT_DIR

CSS = """
:root{--indigo:#141852;--sand:#F6ECDD;--coral:#FF7A6B;--pink:#FF5F9E;--violet:#5E5EE0;--muted:#4A4E7C;--line:rgba(20,24,82,.14);color-scheme:light}
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--sand)!important;color:var(--indigo)!important;font-family:Inter,system-ui,sans-serif}
.stApp::before{content:"";position:fixed;top:0;left:0;right:0;height:8px;z-index:1000000;background:linear-gradient(90deg,#5E5EE0,#FF5F9E,#FF7A6B,#FFC27A)}
[data-testid="stHeader"]{background:transparent!important}
.block-container{padding-top:2.6rem!important;max-width:1180px}
.stApp [data-testid="stMarkdownContainer"] p{color:var(--indigo)}
.stApp [data-testid="stCaptionContainer"],.stApp [data-testid="stCaptionContainer"] p{color:var(--muted)!important}
h1,h2,h3{font-family:'Abril Fatface',serif!important;font-weight:400!important;color:var(--indigo)!important}

/* titles */
.sg-crumb{font-size:13px;color:var(--muted);margin-bottom:2px}
.sg-title{font-family:'Abril Fatface',serif;font-size:46px;line-height:1.05;color:var(--indigo)}
.sg-title i{color:var(--coral);font-style:normal}
.sg-sub{font-size:15px;color:var(--muted);margin:6px 0 22px}
.sg-logo{font-family:'Abril Fatface',serif;font-size:36px;line-height:1;color:var(--indigo)}
.sg-logo i{color:var(--coral);font-style:normal}
.sg-tag{font-size:13px;color:var(--muted);margin:4px 0 14px}

/* sidebar = progress rail */
[data-testid="stSidebar"]{background:#fff!important;border-right:1px solid var(--line)}
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{padding-top:1rem}
[data-testid="stSidebar"]{color:var(--indigo)}
.stApp .st-key-rail button[data-testid^="stBaseButton"]{justify-content:flex-start!important;text-align:left!important;border:0!important;background:transparent!important;border-radius:12px!important;padding:.55rem .8rem!important;box-shadow:none!important}
.stApp .st-key-rail button>div{justify-content:flex-start!important;width:100%}
.stApp .st-key-rail button p{font-size:15px!important;font-weight:600!important;color:var(--indigo)!important;text-align:left!important}
.stApp .st-key-rail button[data-testid="stBaseButton-primary"]{background:#FFE9E4!important;box-shadow:inset 3px 0 0 var(--coral)!important}
.stApp .st-key-rail button[data-testid="stBaseButton-primary"] p{font-weight:700!important}
.stApp .st-key-rail button:hover{background:#FBF1E6!important}
.sg-step-sub{font-size:12.5px;color:var(--muted);margin:-12px 0 8px 2.9rem;line-height:1.3}
.sg-step-sub.done{color:#17614A}

/* cards */
[class*="st-key-card"]{background:#fff;border-radius:22px;padding:26px 28px!important;box-shadow:0 10px 30px rgba(20,24,82,.07);margin-bottom:18px}

/* projects overview */
[class*="st-key-card_proj"]{padding:14px!important;border-radius:20px}
.sg-cover-empty{height:150px;border-radius:12px;display:flex;align-items:center;justify-content:center;color:#4A4E7C;font-size:13px;
  background:linear-gradient(135deg,#E8E6FA,#FFE4EE 55%,#FFF0D9)}
.sg-proj-name{font-weight:700;font-size:16px;margin-top:6px;color:var(--indigo)}
.sg-proj-quote{font-family:'Abril Fatface',serif;font-size:22px;line-height:1.1;margin:2px 0 6px;color:var(--indigo)}
.sg-pill{display:inline-block;font-size:12.5px;font-weight:600;padding:3px 11px;border-radius:999px;color:var(--indigo)}
.sg-proj-meta{font-size:12.5px;color:var(--muted)}

/* buttons */
.stApp button[data-testid="stBaseButton-secondary"],.stApp [data-testid="stDownloadButton"] button{border-radius:999px!important;border:1.5px solid rgba(20,24,82,.2)!important;background:#fff!important;color:var(--indigo)!important;font-weight:600!important}
.stApp button[data-testid="stBaseButton-primary"]{border-radius:999px!important;border:0!important;background:var(--coral)!important;color:var(--indigo)!important;font-weight:700!important}
.stApp button[data-testid="stBaseButton-primary"] p,.stApp button[data-testid="stBaseButton-secondary"] p{color:var(--indigo)!important}
.stApp button:disabled{opacity:.45}

/* inputs */
.stApp [data-baseweb="input"],.stApp [data-baseweb="textarea"],.stApp [data-baseweb="select"]>div{background:#FBF7F0!important;border-radius:12px!important;border:1.5px solid rgba(20,24,82,.18)!important}
.stApp [data-baseweb="input"] input,.stApp [data-baseweb="textarea"] textarea,.stApp [data-baseweb="select"] div{color:var(--indigo)!important;-webkit-text-fill-color:var(--indigo)!important}
.stApp [data-testid="stWidgetLabel"] p,.stApp label p{font-size:13px!important;font-weight:600!important;color:var(--muted)!important}
.stApp [data-testid="stFileUploaderDropzone"]{background:#FBF7F0!important;border:1.5px dashed rgba(20,24,82,.25)!important;border-radius:14px!important}
.stApp [data-testid="stFileUploaderDropzone"] *{color:var(--muted)!important}
.stApp [role="slider"]{background:var(--coral)!important}
.stApp [data-testid="stExpander"]{border:1px solid var(--line)!important;border-radius:14px!important;background:#fff}
.stApp [data-testid="stAlert"]{border-radius:14px}
[data-testid="stAppDeployButton"],.stDeployButton{display:none!important}
.stApp [data-baseweb="input"]>div,.stApp [data-baseweb="base-input"],.stApp [data-baseweb="textarea"],.stApp [data-baseweb="textarea"] textarea,.stApp [data-baseweb="select"]>div,.stApp [data-baseweb="select"]>div>div{background:#FBF7F0!important}
.stApp [data-testid="stTextInputRootElement"],.stApp [data-testid="stNumberInputContainer"],.stApp [data-testid="stSelectbox"] [data-baseweb="select"]>div,.stApp [data-testid="stMultiSelect"] [data-baseweb="select"]>div,.stApp [data-testid="stTextArea"] [data-baseweb="textarea"]{background:#FBF7F0!important;border:1.5px solid rgba(20,24,82,.18)!important;border-radius:12px!important}
.stApp [data-testid="stTextInputRootElement"] input,.stApp [data-testid="stNumberInputContainer"] input,.stApp [data-testid="stTextArea"] textarea{background:transparent!important;color:var(--indigo)!important;-webkit-text-fill-color:var(--indigo)!important}
.stApp [data-testid="stFileUploaderFile"]{background:#fff!important;border-radius:10px}
.stApp [data-testid="stFileUploaderFile"] *{color:var(--indigo)!important}
.stApp [data-testid="stFileUploaderDropzone"] button{background:#fff!important}
.stApp [data-testid="stCheckbox"] p,.stApp [data-testid="stToggle"] p{color:var(--indigo)!important}
.stApp [data-testid="stSidebar"] [data-testid="stExpander"] summary,.stApp [data-testid="stSidebar"] [data-testid="stExpander"] summary *{color:var(--indigo)!important}
.stApp [data-testid="stImage"] img{border-radius:12px}
.stApp pre,.stApp code{background:#FBF7F0!important;color:var(--indigo)!important}
"""


def inject() -> None:
    abril = base64.b64encode((FONT_DIR / "AbrilFatface-Regular.ttf").read_bytes()).decode()
    face = ("@font-face{font-family:'Abril Fatface';font-style:normal;font-weight:400;"
            f"src:url(data:font/ttf;base64,{abril}) format('truetype')}}")
    inter = "@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;1,500&display=swap');"
    st.markdown(f"<style>{inter}{face}{CSS}</style>", unsafe_allow_html=True)


def logo_html() -> str:
    return '<div class="sg-logo">soft grind<i>.</i></div>'


def page_title(crumb: str, title: str, sub: str) -> None:
    st.markdown(f'<div class="sg-crumb">{html.escape(crumb)}</div>'
                f'<div class="sg-title">{html.escape(title)[:-1]}<i>.</i></div>'
                f'<div class="sg-sub">{html.escape(sub)}</div>', unsafe_allow_html=True)


def show_image(src, caption: str | None = None, **kw) -> bool:
    """st.image for a file path or picture; a missing or damaged file shows a quiet placeholder instead of crashing the page."""
    try:
        if isinstance(src, (str, Path)):
            with Image.open(src) as im:
                im.verify()
        st.image(src if not isinstance(src, Path) else str(src), caption=caption, **kw)
        return True
    except Exception:
        st.markdown('<div class="sg-cover-empty">picture can\'t be shown</div>', unsafe_allow_html=True)
        return False
