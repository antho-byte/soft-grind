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
.stApp .st-key-menu button[data-testid^="stBaseButton"]{justify-content:flex-start!important;text-align:left!important;border:0!important;background:transparent!important;border-radius:12px!important;padding:.55rem .8rem!important;box-shadow:none!important}
.stApp .st-key-menu button>div{justify-content:flex-start!important;width:100%}
.stApp .st-key-menu button p{font-size:15px!important;font-weight:600!important;color:var(--indigo)!important;text-align:left!important}
.stApp .st-key-menu button[data-testid="stBaseButton-primary"]{background:#FFE9E4!important;box-shadow:inset 3px 0 0 var(--coral)!important}
.stApp .st-key-menu button[data-testid="stBaseButton-primary"] p{font-weight:700!important}
.stApp .st-key-menu button:hover{background:#FBF1E6!important}
.sg-foot{font-size:12px;color:var(--muted);margin-top:18px;padding:0 .8rem}
.sg-step-sub{font-size:12.5px;color:var(--muted);margin:-12px 0 8px 2.9rem;line-height:1.3}
.sg-step-sub.done{color:#17614A}

/* tabs inside one video */
/* the menu again in the page, for phones where the sidebar is hidden */
.st-key-topnav{display:none;margin-bottom:10px}
@media (max-width: 900px){
  .st-key-topnav{display:block}
  .stApp button{min-height:46px}
  .block-container{padding-left:1rem!important;padding-right:1rem!important}
  .sg-title{font-size:36px}
  .st-key-topnav [data-testid="stHorizontalBlock"],.st-key-vtabs [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.4rem!important}
  .st-key-topnav [data-testid="stColumn"],.st-key-vtabs [data-testid="stColumn"]{min-width:0!important;flex:1 1 0!important;width:auto!important}
  .stApp .st-key-topnav button,.stApp .st-key-vtabs button{padding:.3rem .2rem!important}
  .stApp .st-key-topnav button p,.stApp .st-key-vtabs button p{font-size:14px!important}
}

/* cards */
[class*="st-key-card"]{background:#fff;border-radius:18px;padding:22px 24px!important;border:1px solid rgba(20,24,82,.06);
  box-shadow:0 1px 2px rgba(20,24,82,.04),0 8px 24px rgba(20,24,82,.06);margin-bottom:16px}

.sg-chk{display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-bottom:1px solid rgba(20,24,82,.08)}
.sg-chk b{min-width:190px;color:var(--indigo)}
.sg-chk span.d{color:var(--muted)}
.sg-badge{display:inline-block;min-width:54px;text-align:center;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px}
.sg-badge.ok{background:#DDF1E6;color:#17614A}.sg-badge.warn{background:#FFF0D9;color:#7A4B00}.sg-badge.fail{background:#FFD9D2;color:#8A2A1B}
.sg-saved{font-size:13px;font-weight:600;color:#17614A}
.sg-unsaved{font-size:13px;font-weight:600;color:#9A5B00}

/* projects overview */
[class*="st-key-card_proj"]{padding:12px 12px 14px!important;border-radius:16px;transition:box-shadow .15s,transform .15s}
[class*="st-key-card_proj"]:hover{box-shadow:0 2px 4px rgba(20,24,82,.05),0 14px 32px rgba(20,24,82,.10)}
[class*="st-key-card_proj"] [data-testid="stImage"] img{aspect-ratio:16/9;object-fit:cover;width:100%}
[class*="st-key-card_proj"] [data-testid="stCheckbox"] p{font-size:13px!important;font-weight:600!important;color:var(--muted)!important}
[class*="st-key-card_proj"] [data-testid="stElementContainer"]{margin-bottom:-4px}
.st-key-bulkbar{background:#fff;border:1px solid rgba(20,24,82,.08);border-radius:14px;padding:8px 14px!important;margin:4px 0 14px}
.sg-cover-empty{aspect-ratio:16/9;border-radius:12px;display:flex;align-items:center;justify-content:center;color:#4A4E7C;font-size:13px;
  background:linear-gradient(135deg,#E8E6FA,#FFE4EE 55%,#FFF0D9)}
.sg-proj-name{font-weight:700;font-size:16px;margin-top:6px;color:var(--indigo)}
.sg-proj-quote{font-family:'Abril Fatface',serif;font-size:21px;line-height:1.1;margin:0 0 8px;color:var(--indigo)}
.sg-pill{display:inline-block;font-size:12.5px;font-weight:600;padding:3px 11px;border-radius:999px;color:var(--indigo)}
.sg-proj-meta{font-size:12.5px;color:var(--muted)}

/* buttons: one solid primary (indigo), hairline secondary, quiet text-only tertiary */
.stApp button[data-testid="stBaseButton-secondary"],.stApp [data-testid="stDownloadButton"] button[data-testid="stBaseButton-secondary"],
.stApp [data-testid="stPopover"] button,.stApp a[data-testid="stBaseLinkButton-secondary"]{border-radius:10px!important;border:1px solid rgba(20,24,82,.14)!important;
  background:#fff!important;color:var(--indigo)!important;font-weight:600!important;box-shadow:0 1px 2px rgba(20,24,82,.06)!important;transition:background .12s,box-shadow .12s}
.stApp button[data-testid="stBaseButton-secondary"]:hover,.stApp [data-testid="stPopover"] button:hover,.stApp a[data-testid="stBaseLinkButton-secondary"]:hover{background:#FBF7F0!important;border-color:rgba(20,24,82,.24)!important}
.stApp button[data-testid="stBaseButton-primary"],.stApp [data-testid="stPopover"] button[data-testid="stPopoverButton"][kind="primary"],
.stApp a[data-testid="stBaseLinkButton-primary"]{border-radius:10px!important;border:0!important;background:var(--indigo)!important;color:#fff!important;
  font-weight:600!important;box-shadow:0 1px 2px rgba(20,24,82,.2),0 4px 12px rgba(20,24,82,.14)!important}
.stApp button[data-testid="stBaseButton-primary"]:hover{background:#262B78!important}
.stApp button[data-testid="stBaseButton-primary"] p,.stApp a[data-testid="stBaseLinkButton-primary"] p{color:#fff!important}
.stApp button[data-testid="stBaseButton-secondary"] p,.stApp a[data-testid="stBaseLinkButton-secondary"] p{color:var(--indigo)!important}
.stApp button:disabled{opacity:.45}
/* filter chips (segmented control) */
.stApp [data-testid="stButtonGroup"]>div,.stApp [data-testid="stButtonGroup"] [role="radiogroup"]{flex-wrap:wrap!important;row-gap:6px}
.stApp [data-testid="stButtonGroup"] button[data-variant="segmented_control"]{border-radius:999px!important;border:1px solid rgba(20,24,82,.12)!important;background:#fff!important;margin-right:6px!important;padding:6px 14px!important}
.stApp [data-testid="stButtonGroup"] button[data-variant="segmented_control"] p{color:var(--indigo)!important;font-weight:600!important}
.stApp [data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected="true"]{background:var(--indigo)!important;border-color:var(--indigo)!important}
.stApp [data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected="true"] p{color:#fff!important}
/* popover buttons: the primary one is white on indigo; the card menu is a quiet dots button */
.stApp [data-testid="stPopoverButton"][kind="primary"] p,.stApp [data-testid="stPopoverButton"][kind="primary"] span{color:#fff!important}
[class*="st-key-card_proj"] [data-testid="stPopoverButton"]{border:0!important;box-shadow:none!important;background:transparent!important;min-height:32px!important;padding:0 6px!important}
[class*="st-key-card_proj"] [data-testid="stPopoverButton"]:hover{background:rgba(20,24,82,.06)!important}
[class*="st-key-card_proj"] [data-testid="stPopoverButton"] [data-testid="stIconMaterial"]{display:none}
[class*="st-key-card_proj"] [data-testid="stPopoverButton"] p{font-size:20px!important;letter-spacing:1px;color:var(--muted)!important}
/* the sidebar menu keeps its own look (it uses primary for 'you are here') */
.stApp .st-key-menu button[data-testid="stBaseButton-primary"],.stApp .st-key-menu button[data-testid="stBaseButton-secondary"]{box-shadow:none!important;border:0!important}
.stApp .st-key-menu button[data-testid="stBaseButton-primary"]{background:#FFE9E4!important;box-shadow:inset 3px 0 0 var(--coral)!important}
.stApp .st-key-menu button[data-testid="stBaseButton-primary"] p,.stApp .st-key-menu button[data-testid="stBaseButton-secondary"] p{color:var(--indigo)!important}
.stApp .st-key-topnav button[data-testid="stBaseButton-primary"] p{color:#fff!important}
/* inputs */
.stApp [data-baseweb="input"],.stApp [data-baseweb="textarea"],.stApp [data-baseweb="select"]>div{background:#fff!important;border-radius:10px!important;border:1px solid rgba(20,24,82,.16)!important}
.stApp [data-baseweb="input"] input,.stApp [data-baseweb="textarea"] textarea,.stApp [data-baseweb="select"] div{color:var(--indigo)!important;-webkit-text-fill-color:var(--indigo)!important}
.stApp [data-testid="stWidgetLabel"] p,.stApp label p{font-size:13px!important;font-weight:600!important;color:var(--muted)!important}
.stApp [data-testid="stFileUploaderDropzone"]{background:#FBF7F0!important;border:1.5px dashed rgba(20,24,82,.25)!important;border-radius:14px!important}
.stApp [data-testid="stFileUploaderDropzone"] *{color:var(--muted)!important}
.stApp [role="slider"]{background:var(--coral)!important}
.stApp [data-testid="stExpander"]{border:1px solid rgba(20,24,82,.08)!important;border-radius:12px!important;background:#fff}
.stApp [data-testid="stExpander"] summary p{font-weight:600!important}
.stApp [data-testid="stAlert"]{border-radius:14px}
/* notices in the brand palette instead of the default blue / yellow / red / green */
[data-testid="stAlertContainer"]{border-radius:14px!important;border:0!important;background:#EDEBFF!important}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]){background:#FFF0D9!important}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]){background:#FFE0DA!important}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]){background:#DDF1E6!important}
[data-testid="stAlertContainer"] p,[data-testid="stAlertContainer"] li,[data-testid="stAlertContainer"] strong{color:var(--indigo)!important}
/* readable help text (Streamlit fades captions to 60%) */
.stApp [data-testid="stCaptionContainer"]{opacity:1!important}
/* readable tags */
[data-testid="stMultiSelectTagsContainer"] span{color:var(--indigo)!important}
/* disabled buttons that can still be read */
.stApp button[data-testid^="stBaseButton"]:disabled{opacity:1!important;background:#EDE3D3!important;color:rgba(20,24,82,.62)!important;border-color:transparent!important}
.stApp button[data-testid^="stBaseButton"]:disabled p{color:rgba(20,24,82,.62)!important}
/* quiet text buttons */
.stApp button[data-testid="stBaseButton-tertiary"]{color:var(--violet)!important;background:transparent!important;border:0!important;font-weight:600;box-shadow:none!important}
.stApp button[data-testid="stBaseButton-tertiary"] p{color:#3A3790!important}
.stApp button[data-testid="stBaseButton-tertiary"]:hover{background:rgba(94,94,224,.08)!important;border-radius:10px!important}
/* cards of one row share a height */
[data-testid="stColumn"]:has([class*="st-key-card_proj"])>[data-testid="stVerticalBlock"]{height:100%}
[data-testid="stColumn"]:has([class*="st-key-card_proj"])>[data-testid="stVerticalBlock"]>*:has([class*="st-key-card_proj"]),
[data-testid="stColumn"]:has([class*="st-key-card_proj"])>[data-testid="stVerticalBlock"]>*:has([class*="st-key-card_proj"])>*{height:100%}
[class*="st-key-card_proj"]{height:100%;box-sizing:border-box}
[data-testid="stAppDeployButton"],.stDeployButton{display:none!important}
.stApp [data-baseweb="input"]>div,.stApp [data-baseweb="base-input"],.stApp [data-baseweb="textarea"],.stApp [data-baseweb="textarea"] textarea,.stApp [data-baseweb="select"]>div,.stApp [data-baseweb="select"]>div>div{background:#fff!important}
.stApp [data-testid="stTextInputRootElement"],.stApp [data-testid="stNumberInputContainer"],.stApp [data-testid="stSelectbox"] [data-baseweb="select"]>div,.stApp [data-testid="stMultiSelect"] [data-baseweb="select"]>div,.stApp [data-testid="stTextArea"] [data-baseweb="textarea"]{background:#fff!important;border:1px solid rgba(20,24,82,.16)!important;border-radius:10px!important}
.stApp [data-testid="stTextInputRootElement"] input,.stApp [data-testid="stNumberInputContainer"] input,.stApp [data-testid="stTextArea"] textarea{background:transparent!important;color:var(--indigo)!important;-webkit-text-fill-color:var(--indigo)!important}
.stApp [data-testid="stFileUploaderFile"]{background:#fff!important;border-radius:10px}
.stApp [data-testid="stFileUploaderFile"] *{color:var(--indigo)!important}
.stApp [data-testid="stFileUploaderDropzone"] button{background:#fff!important}
.stApp [data-testid="stCheckbox"] p,.stApp [data-testid="stToggle"] p{color:var(--indigo)!important}
.stApp [data-testid="stSidebar"] [data-testid="stExpander"] summary,.stApp [data-testid="stSidebar"] [data-testid="stExpander"] summary *{color:var(--indigo)!important}
.stApp [data-testid="stImage"] img{border-radius:12px}
/* planning calendar */
.sg-cal-month{font-family:'Abril Fatface',serif;font-size:28px;color:var(--indigo);text-align:center;line-height:1}
.st-key-calendar{background:#fff;border:1px solid rgba(20,24,82,.06);border-radius:18px;padding:16px!important;
  box-shadow:0 1px 2px rgba(20,24,82,.04),0 8px 24px rgba(20,24,82,.06);margin-bottom:16px}
.sg-cal-head,.sg-cal-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px}
.sg-cal-head div{font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;padding:0 6px 6px}
.sg-cal-day{min-height:96px;border-radius:10px;background:#FBF7F0;padding:6px;display:flex;flex-direction:column;gap:4px;overflow:hidden}
.sg-cal-day .n{font-size:12.5px;font-weight:700;color:var(--indigo)}
.sg-cal-day.other{opacity:.38}
.sg-cal-day.past{background:#F6F1E8}
.sg-cal-day.today{box-shadow:inset 0 0 0 2px var(--coral)}
.sg-cal-day.today .n{color:var(--coral)}
.sg-cal-item{font-size:12px;line-height:1.25;border-radius:7px;padding:4px 6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sg-cal-item b{font-weight:700;margin-right:2px}
.sg-cal-free{font-size:11.5px;color:var(--muted);border:1px dashed rgba(20,24,82,.28);border-radius:7px;padding:3px 6px}
.sg-cal-legend{font-size:12px;color:var(--muted);margin-top:10px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.sg-cal-legend span{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.sg-cal-legend span.free{border:1px dashed rgba(20,24,82,.4)}
@media (max-width: 900px){
  .sg-cal-head,.sg-cal-grid{gap:3px}
  .sg-cal-day{min-height:58px;padding:3px}
  .sg-cal-item{font-size:0;padding:0;height:8px;border-radius:4px}
  .sg-cal-item b{display:none}
  .sg-cal-free{font-size:0;padding:0;height:8px;border-radius:4px}
  .sg-cal-head div{font-size:10px;padding:0 2px 4px}
  .st-key-plan_nav [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.4rem!important}
  .st-key-plan_nav [data-testid="stColumn"]{min-width:0!important;width:auto!important;flex:0 0 auto!important}
  .st-key-plan_nav [data-testid="stColumn"]:nth-child(2){flex:1 1 0!important}
  .st-key-plan_nav [data-testid="stColumn"]:nth-child(5){flex:1 1 100%!important}
  .sg-cal-month{font-size:22px}
}
.stApp pre,.stApp code{background:#FBF7F0!important;color:var(--indigo)!important}
/* tabs inside one video: a segmented control (last, so it wins over the general button look) */
.st-key-vtabs{margin:-6px 0 18px}
.st-key-vtabs [data-testid="stHorizontalBlock"]{background:rgba(20,24,82,.06);border-radius:14px;padding:4px;gap:4px!important;max-width:560px}
.stApp [data-testid="stMain"] .st-key-vtabs button{border-radius:10px!important;min-height:40px;border:0!important;box-shadow:none!important;background:transparent!important}
.stApp [data-testid="stMain"] .st-key-vtabs button p{color:var(--muted)!important;font-weight:600!important}
.stApp [data-testid="stMain"] .st-key-vtabs button[data-testid="stBaseButton-primary"]{background:#fff!important;box-shadow:0 1px 3px rgba(20,24,82,.12),0 2px 8px rgba(20,24,82,.06)!important}
.stApp [data-testid="stMain"] .st-key-vtabs button[data-testid="stBaseButton-primary"] p{color:var(--indigo)!important}
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
