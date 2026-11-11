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
/* ===== soft grind. design system: sand app, white cards, indigo ink, coral accent. Apple-like: calm, rounded, soft depth ===== */
:root{--indigo:#141852;--ink2:#4A4E7C;--ink3:rgba(20,24,82,.45);--sand:#F6ECDD;--sand2:#FBF6EE;--fill:rgba(20,24,82,.06);
  --fill2:rgba(20,24,82,.10);--coral:#FF7A6B;--pink:#FF5F9E;--violet:#5E5EE0;--apricot:#FFC27A;--palm:#1F7A5A;--line:rgba(20,24,82,.08);
  --sh1:0 1px 2px rgba(20,24,82,.04),0 6px 20px rgba(20,24,82,.06);--sh2:0 2px 6px rgba(20,24,82,.06),0 18px 40px rgba(20,24,82,.11);
  --r-card:20px;--r-ctl:12px;color-scheme:light}
html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--sand)!important;color:var(--indigo)!important;
  font-family:Inter,-apple-system,BlinkMacSystemFont,"SF Pro Text",system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.stApp::before{content:"";position:fixed;top:0;left:0;right:0;height:5px;z-index:1000000;background:linear-gradient(90deg,#5E5EE0,#FF5F9E,#FF7A6B,#FFC27A)}
[data-testid="stHeader"]{background:transparent!important}
.block-container{padding-top:2.4rem!important;max-width:1200px}
.stApp [data-testid="stMarkdownContainer"] p{color:var(--indigo)}
.stApp [data-testid="stCaptionContainer"],.stApp [data-testid="stCaptionContainer"] p{color:var(--ink2)!important;opacity:1!important}
h1,h2,h3{font-family:'Abril Fatface',serif!important;font-weight:400!important;color:var(--indigo)!important}
[data-testid="stAppDeployButton"],.stDeployButton{display:none!important}

/* ----- page header ----- */
.sg-crumb{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--ink3);margin-bottom:4px}
.sg-title{font-family:'Abril Fatface',serif;font-size:44px;line-height:1.04;color:var(--indigo);letter-spacing:-.01em}
.sg-title i{color:var(--coral);font-style:normal}
.sg-sub{font-size:15px;color:var(--ink2);margin:8px 0 24px;max-width:720px}
.sg-logo{font-family:'Abril Fatface',serif;font-size:34px;line-height:1;color:var(--indigo)}
.sg-logo i{color:var(--coral);font-style:normal}
.sg-tag{font-size:13px;color:var(--ink2);margin:6px 0 18px}

/* ----- sidebar: a source list ----- */
[data-testid="stSidebar"]{background:var(--sand2)!important;border-right:0!important;box-shadow:inset -1px 0 0 var(--line)}
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{padding-top:1rem}
.stApp .st-key-menu button[data-testid^="stBaseButton"]{justify-content:flex-start!important;text-align:left!important;border:0!important;
  background:transparent!important;border-radius:12px!important;padding:.6rem .85rem!important;box-shadow:none!important;min-height:44px}
.stApp .st-key-menu button>div{justify-content:flex-start!important;width:100%;gap:.7rem}
.stApp .st-key-menu button p{font-size:15px!important;font-weight:600!important;color:var(--indigo)!important;text-align:left!important}
.stApp .st-key-menu button [data-testid="stIconMaterial"]{color:var(--ink2)!important;font-size:20px!important}
.stApp .st-key-menu button[data-testid="stBaseButton-primary"]{background:#fff!important;box-shadow:var(--sh1)!important}
.stApp .st-key-menu button[data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"]{color:var(--coral)!important}
.stApp .st-key-menu button[data-testid="stBaseButton-primary"] p{font-weight:700!important}
.stApp .st-key-menu button[data-testid="stBaseButton-secondary"]:hover{background:var(--fill)!important}
.sg-step-sub{font-size:12.5px;color:var(--ink3);margin:-10px 0 10px 2.4rem;line-height:1.3}
.sg-step-sub.done{color:#17614A}
.sg-foot{font-size:12px;color:var(--ink3);margin-top:18px;padding:0 .9rem}

/* ----- cards ----- */
[class*="st-key-card"]{background:#fff;border-radius:var(--r-card);padding:24px 26px!important;border:0;box-shadow:var(--sh1);margin-bottom:18px}
.sg-chk{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--line)}
.sg-chk b{min-width:190px;color:var(--indigo)}
.sg-chk span.d{color:var(--ink2)}
.sg-badge{display:inline-block;min-width:54px;text-align:center;font-size:12px;font-weight:700;padding:3px 10px;border-radius:999px}
.sg-badge.ok{background:#DDF1E6;color:#17614A}.sg-badge.warn{background:#FFF0D9;color:#7A4B00}.sg-badge.fail{background:#FFD9D2;color:#8A2A1B}
.sg-saved{font-size:13px;font-weight:600;color:#17614A}
.sg-unsaved{font-size:13px;font-weight:600;color:#9A5B00}

/* ----- the videos page ----- */
[class*="st-key-card_proj"]{padding:12px 12px 16px!important;border-radius:22px;transition:box-shadow .2s,transform .2s;height:100%;box-sizing:border-box}
[class*="st-key-card_proj"]:hover{box-shadow:var(--sh2);transform:translateY(-2px)}
[class*="st-key-card_proj"] [data-testid="stImage"] img{aspect-ratio:16/9;object-fit:cover;width:100%;border-radius:14px!important}
[class*="st-key-card_proj"] [data-testid="stCheckbox"] p{font-size:12.5px!important;font-weight:600!important;color:var(--ink3)!important;letter-spacing:.02em}
[class*="st-key-card_proj"] [data-testid="stElementContainer"]{margin-bottom:-4px}
[data-testid="stColumn"]:has([class*="st-key-card_proj"])>[data-testid="stVerticalBlock"]{height:100%}
[data-testid="stColumn"]:has([class*="st-key-card_proj"])>[data-testid="stVerticalBlock"]>*:has([class*="st-key-card_proj"]),
[data-testid="stColumn"]:has([class*="st-key-card_proj"])>[data-testid="stVerticalBlock"]>*:has([class*="st-key-card_proj"])>*{height:100%}
.st-key-bulkbar{background:rgba(255,255,255,.65);border-radius:16px;padding:6px 8px 6px 18px!important;margin:6px 0 16px;box-shadow:inset 0 0 0 1px var(--line)}
.sg-cover-empty{aspect-ratio:16/9;border-radius:14px;display:flex;align-items:center;justify-content:center;color:var(--ink2);font-size:13px;
  background:linear-gradient(135deg,#E8E6FA,#FFE4EE 55%,#FFF0D9)}
.sg-proj-name{font-weight:700;font-size:16px;margin-top:6px;color:var(--indigo)}
.sg-proj-quote{font-family:'Abril Fatface',serif;font-size:22px;line-height:1.1;margin:2px 0 8px;color:var(--indigo)}
.sg-pill{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:3px 10px 3px 8px;border-radius:999px;color:var(--indigo)}
.sg-pill::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;opacity:.7}
.sg-proj-meta{font-size:12.5px;color:var(--ink2)}
/* overview tiles */
.sg-dash{display:grid;grid-template-columns:1.6fr 1fr 1fr 1fr;gap:16px;margin:0 0 22px}
.sg-tile{background:#fff;border-radius:var(--r-card);padding:18px 20px;box-shadow:var(--sh1);min-height:118px;display:flex;flex-direction:column;justify-content:space-between}
.sg-tile .k{font-size:12px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--ink3)}
.sg-tile .v{font-size:34px;font-weight:700;line-height:1;color:var(--indigo);letter-spacing:-.02em}
.sg-tile .s{font-size:12.5px;color:var(--ink2)}
.sg-tile.hero{background:linear-gradient(135deg,#141852 0%,#3B3A9E 62%,#5E5EE0 100%);color:#fff;flex-direction:row;align-items:center;gap:18px;justify-content:flex-start}
.sg-tile.hero .k{color:rgba(255,255,255,.7)}.sg-tile.hero .v{color:#fff;font-size:22px}.sg-tile.hero .s{color:rgba(255,255,255,.82)}
.sg-tile.hero .txt{display:flex;flex-direction:column;gap:6px}
.sg-tile .dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;vertical-align:1px}

/* ----- buttons: capsule. solid indigo = the main action, tinted = everything else, text = small actions ----- */
.stApp button[data-testid^="stBaseButton"],.stApp a[data-testid^="stBaseLinkButton"],.stApp [data-testid="stPopoverButton"],
[data-testid="stPopoverBody"] button[data-testid^="stBaseButton"]{border-radius:999px!important;font-weight:600!important;min-height:40px;
  transition:background .15s,box-shadow .15s,transform .08s}
.stApp button[data-testid^="stBaseButton"]:active{transform:scale(.98)}
.stApp button[data-testid="stBaseButton-primary"],.stApp a[data-testid="stBaseLinkButton-primary"],
.stApp [data-testid="stPopoverButton"][kind="primary"],[data-testid="stPopoverBody"] button[data-testid="stBaseButton-primary"]{
  border:0!important;background:var(--indigo)!important;color:#fff!important;box-shadow:0 1px 2px rgba(20,24,82,.25),0 6px 16px rgba(20,24,82,.18)!important}
.stApp button[data-testid="stBaseButton-primary"]:hover,.stApp a[data-testid="stBaseLinkButton-primary"]:hover,
.stApp [data-testid="stPopoverButton"][kind="primary"]:hover{background:#262C80!important}
.stApp button[data-testid="stBaseButton-primary"] p,.stApp a[data-testid="stBaseLinkButton-primary"] p,
.stApp [data-testid="stPopoverButton"][kind="primary"] p,.stApp [data-testid="stPopoverButton"][kind="primary"] span,
[data-testid="stPopoverBody"] button[data-testid="stBaseButton-primary"] p,
.stApp button[data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"]{color:#fff!important}
.stApp button[data-testid="stBaseButton-secondary"],.stApp [data-testid="stDownloadButton"] button[data-testid="stBaseButton-secondary"],
.stApp a[data-testid="stBaseLinkButton-secondary"],.stApp [data-testid="stPopoverButton"]:not([kind="primary"]),
[data-testid="stPopoverBody"] button[data-testid="stBaseButton-secondary"]{border:0!important;background:var(--fill)!important;color:var(--indigo)!important;box-shadow:none!important}
.stApp button[data-testid="stBaseButton-secondary"]:hover,.stApp a[data-testid="stBaseLinkButton-secondary"]:hover,
.stApp [data-testid="stPopoverButton"]:not([kind="primary"]):hover,[data-testid="stPopoverBody"] button[data-testid="stBaseButton-secondary"]:hover{background:var(--fill2)!important}
.stApp button[data-testid="stBaseButton-secondary"] p,.stApp a[data-testid="stBaseLinkButton-secondary"] p,
[data-testid="stPopoverBody"] button[data-testid="stBaseButton-secondary"] p{color:var(--indigo)!important}
.stApp button[data-testid="stBaseButton-tertiary"]{color:#3A3790!important;background:transparent!important;border:0!important;box-shadow:none!important;min-height:36px}
.stApp button[data-testid="stBaseButton-tertiary"] p{color:#3A3790!important}
.stApp button[data-testid="stBaseButton-tertiary"]:hover{background:rgba(94,94,224,.09)!important}
.stApp button[data-testid^="stBaseButton"]:disabled{opacity:1!important;background:var(--fill)!important;color:var(--ink3)!important;box-shadow:none!important}
.stApp button[data-testid^="stBaseButton"]:disabled p{color:var(--ink3)!important}
.stApp button[data-testid="stBaseButton-tertiary"]:disabled{background:transparent!important}
[data-testid="stPopoverBody"]{border-radius:18px!important;box-shadow:var(--sh2)!important;border:0!important;background:#fff!important}
/* the card's "more" button: quiet dots */
[class*="st-key-card_proj"] [data-testid="stPopoverButton"],[class*="st-key-trackrow"] [data-testid="stPopoverButton"]{background:transparent!important;min-height:32px!important;padding:0 8px!important}
[class*="st-key-card_proj"] [data-testid="stPopoverButton"]:hover,[class*="st-key-trackrow"] [data-testid="stPopoverButton"]:hover{background:var(--fill)!important}
[class*="st-key-card_proj"] [data-testid="stPopoverButton"] [data-testid="stIconMaterial"],
[class*="st-key-trackrow"] [data-testid="stPopoverButton"] [data-testid="stIconMaterial"]{display:none}
[class*="st-key-card_proj"] [data-testid="stPopoverButton"] p,[class*="st-key-trackrow"] [data-testid="stPopoverButton"] p{font-size:20px!important;letter-spacing:1px;color:var(--ink2)!important}

/* ----- chips (filters, view switches) ----- */
.stApp [data-testid="stButtonGroup"]>div,.stApp [data-testid="stButtonGroup"] [role="radiogroup"]{flex-wrap:wrap!important;row-gap:6px}
.stApp [data-testid="stButtonGroup"] button[data-variant="segmented_control"]{border-radius:999px!important;border:0!important;background:var(--fill)!important;
  margin-right:6px!important;padding:7px 15px!important;min-height:36px}
.stApp [data-testid="stButtonGroup"] button[data-variant="segmented_control"] p{color:var(--indigo)!important;font-weight:600!important}
.stApp [data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected="true"]{background:var(--indigo)!important}
.stApp [data-testid="stButtonGroup"] button[data-variant="segmented_control"][data-selected="true"] p{color:#fff!important}

/* ----- inputs: filled, no hard borders ----- */
.stApp [data-baseweb="input"],.stApp [data-baseweb="textarea"],.stApp [data-baseweb="select"]>div,.stApp [data-baseweb="input"]>div,
.stApp [data-baseweb="base-input"],.stApp [data-baseweb="textarea"] textarea,.stApp [data-baseweb="select"]>div>div{background:var(--sand2)!important}
.stApp [data-testid="stTextInputRootElement"],.stApp [data-testid="stNumberInputContainer"],.stApp [data-testid="stSelectbox"] [data-baseweb="select"]>div,
.stApp [data-testid="stMultiSelect"] [data-baseweb="select"]>div,.stApp [data-testid="stTextArea"] [data-baseweb="textarea"],
.stApp [data-testid="stDateInput"] [data-baseweb="input"],.stApp [data-testid="stTimeInput"] [data-baseweb="select"]>div{
  background:var(--sand2)!important;border:1px solid transparent!important;border-radius:var(--r-ctl)!important;box-shadow:inset 0 0 0 1px var(--line)!important}
.stApp [data-testid="stTextInputRootElement"]:focus-within,.stApp [data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within,
.stApp [data-testid="stSelectbox"] [data-baseweb="select"]>div:focus-within{box-shadow:0 0 0 3px rgba(94,94,224,.22),inset 0 0 0 1px rgba(94,94,224,.6)!important}
.stApp [data-testid="stTextInputRootElement"] input,.stApp [data-testid="stNumberInputContainer"] input,.stApp [data-testid="stTextArea"] textarea,
.stApp [data-baseweb="input"] input,.stApp [data-baseweb="select"] div{background:transparent!important;color:var(--indigo)!important;-webkit-text-fill-color:var(--indigo)!important}
.stApp [data-testid="stWidgetLabel"] p,.stApp label p{font-size:13px!important;font-weight:600!important;color:var(--ink2)!important}
.stApp [data-testid="stCheckbox"] p,.stApp [data-testid="stToggle"] p{color:var(--indigo)!important}
.stApp [data-baseweb="tag"],.stApp [data-testid="stMultiSelectTagsContainer"] [data-tag]{background:rgba(94,94,224,.13)!important;border-radius:999px!important;border:0!important}
.stApp [data-baseweb="tag"] span,[data-testid="stMultiSelectTagsContainer"] span{color:var(--indigo)!important}
.stApp [data-baseweb="tag"] svg,.stApp [data-testid="stMultiSelectTagsContainer"] [data-tag] svg{fill:var(--ink2)!important;color:var(--ink2)!important}
.stApp [role="slider"]{background:var(--coral)!important;box-shadow:0 1px 4px rgba(20,24,82,.25)!important}
.stApp [data-testid="stFileUploaderDropzone"]{background:var(--sand2)!important;border:1.5px dashed rgba(20,24,82,.2)!important;border-radius:16px!important}
.stApp [data-testid="stFileUploaderDropzone"] *{color:var(--ink2)!important}
.stApp [data-testid="stFileUploaderDropzone"] button{background:#fff!important}
.stApp [data-testid="stFileUploaderFile"]{background:#fff!important;border-radius:12px}
.stApp [data-testid="stFileUploaderFile"] *{color:var(--indigo)!important}

/* ----- disclosure groups, notices, progress, media ----- */
.stApp [data-testid="stExpander"]{border:0!important;border-radius:14px!important;background:#fff;box-shadow:inset 0 0 0 1px var(--line)}
.stApp [data-testid="stExpander"] details{border:0!important;border-radius:14px!important}
.stApp [data-testid="stExpander"] summary{border-radius:14px!important}
.stApp textarea,.stApp [data-baseweb="textarea"] textarea{font-size:14px!important;line-height:1.55!important;padding:10px 12px!important}
.stApp [data-testid="stExpander"] summary:hover{background:rgba(20,24,82,.025)}
.stApp [data-testid="stExpander"] summary p{font-weight:600!important}
[class*="st-key-card"] [data-testid="stExpander"]{background:var(--sand2)}
.stApp [data-testid="stSidebar"] [data-testid="stExpander"] summary,.stApp [data-testid="stSidebar"] [data-testid="stExpander"] summary *{color:var(--indigo)!important}
[data-testid="stAlertContainer"]{border-radius:16px!important;border:0!important;background:#EDEBFF!important}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]){background:#FFF0D9!important}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]){background:#FFE0DA!important}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]){background:#DDF1E6!important}
[data-testid="stAlertContainer"] p,[data-testid="stAlertContainer"] li,[data-testid="stAlertContainer"] strong{color:var(--indigo)!important}
.stApp [data-testid="stProgressBarTrack"]{background:var(--fill)!important;border-radius:999px!important;height:6px!important;overflow:hidden}
.stApp [data-testid="stProgressBarTrack"]>div{background:linear-gradient(90deg,var(--coral),var(--pink))!important;border-radius:999px!important}
.stApp [data-testid="stImage"] img{border-radius:14px}
.stApp video{border-radius:16px}
.stApp pre,.stApp code{background:var(--sand2)!important;color:var(--indigo)!important;border-radius:12px}
.stApp [data-testid="stTabs"] [role="tablist"]{gap:4px;background:var(--fill);padding:4px;border-radius:14px;width:fit-content;margin-bottom:16px;border:0!important}
.stApp [data-testid="stTabs"] [role="tablist"]::after,.stApp [data-testid="stTabs"] [role="tablist"]::before{display:none!important}
.stApp [data-testid="stTab"]{border-radius:10px!important;padding:7px 16px!important;height:auto!important;border:0!important}
.stApp [data-testid="stTab"] p{font-weight:600!important;color:var(--ink2)!important;font-size:14px!important}
.stApp [data-testid="stTab"][aria-selected="true"]{background:#fff!important;box-shadow:0 1px 3px rgba(20,24,82,.12),0 2px 8px rgba(20,24,82,.06)}
.stApp [data-testid="stTab"][aria-selected="true"] p{color:var(--indigo)!important}
.stApp [data-testid="stTab"]::after,.stApp [data-testid="stTab"]::before{display:none!important}
.stApp [data-testid="stTabs"] [role="tablist"]>div:not([data-testid="stTab"]){display:none!important}

/* ----- planning calendar ----- */
.sg-cal-month{font-family:'Abril Fatface',serif;font-size:28px;color:var(--indigo);text-align:center;line-height:1}
.st-key-calendar{background:#fff;border-radius:var(--r-card);padding:16px!important;box-shadow:var(--sh1);margin-bottom:18px}
.sg-cal-head,.sg-cal-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px}
.sg-cal-head div{font-size:11.5px;font-weight:700;color:var(--ink3);text-transform:uppercase;letter-spacing:.07em;padding:0 6px 6px}
.sg-cal-day{min-height:96px;border-radius:12px;background:var(--sand2);padding:7px;display:flex;flex-direction:column;gap:4px;overflow:hidden}
.sg-cal-day .n{font-size:12.5px;font-weight:700;color:var(--indigo)}
.sg-cal-day.other{opacity:.38}
.sg-cal-day.past{background:#F4EEE4}
.sg-cal-day.today{box-shadow:inset 0 0 0 2px var(--coral)}
.sg-cal-day.today .n{color:var(--coral)}
.sg-cal-item{font-size:12px;line-height:1.25;border-radius:8px;padding:4px 7px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sg-cal-item b{font-weight:700;margin-right:2px}
.sg-cal-free{font-size:11.5px;color:var(--ink2);border:1px dashed rgba(20,24,82,.25);border-radius:8px;padding:3px 7px}
.sg-cal-legend{font-size:12px;color:var(--ink2);margin-top:10px;display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center}
.sg-cal-legend span{display:inline-block;width:11px;height:11px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.sg-cal-legend span.free{border:1px dashed rgba(20,24,82,.4)}

/* ----- tabs inside one video: a segmented control ----- */
.st-key-vtabs{margin:-6px 0 20px}
.st-key-vtabs [data-testid="stHorizontalBlock"]{background:var(--fill);border-radius:14px;padding:4px;gap:4px!important;max-width:560px}
.stApp [data-testid="stMain"] .st-key-vtabs button{border-radius:10px!important;min-height:38px;border:0!important;box-shadow:none!important;background:transparent!important}
.stApp [data-testid="stMain"] .st-key-vtabs button p,.stApp [data-testid="stMain"] .st-key-vtabs button [data-testid="stIconMaterial"]{color:var(--ink2)!important;font-weight:600!important}
.stApp [data-testid="stMain"] .st-key-vtabs button[data-testid="stBaseButton-primary"]{background:#fff!important;box-shadow:0 1px 3px rgba(20,24,82,.12),0 2px 8px rgba(20,24,82,.06)!important}
.stApp [data-testid="stMain"] .st-key-vtabs button[data-testid="stBaseButton-primary"] p,
.stApp [data-testid="stMain"] .st-key-vtabs button[data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"]{color:var(--indigo)!important}

/* ----- the sidebar menu keeps its own colours (it uses 'primary' to mean 'you are here') ----- */
.stApp .st-key-menu button[data-testid="stBaseButton-primary"]{background:#fff!important;box-shadow:var(--sh1)!important}
.stApp .st-key-menu button[data-testid="stBaseButton-secondary"]{background:transparent!important}
.stApp .st-key-menu button[data-testid="stBaseButton-secondary"]:hover{background:var(--fill)!important}
.stApp .st-key-menu button[data-testid="stBaseButton-primary"] p,.stApp .st-key-menu button[data-testid="stBaseButton-secondary"] p{color:var(--indigo)!important}
.stApp .st-key-menu button[data-testid="stBaseButton-primary"] [data-testid="stIconMaterial"]{color:var(--coral)!important}
.stApp .st-key-menu button[data-testid="stBaseButton-secondary"] [data-testid="stIconMaterial"]{color:var(--ink2)!important}

/* ----- phones (kept working, not the focus) ----- */
.st-key-topnav{display:none;margin-bottom:10px}
@media (max-width: 900px){
  .st-key-topnav{display:block}
  .block-container{padding-left:1rem!important;padding-right:1rem!important}
  .sg-title{font-size:34px}
  .sg-dash{grid-template-columns:1fr 1fr}
  .st-key-topnav [data-testid="stHorizontalBlock"],.st-key-vtabs [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.4rem!important}
  .st-key-topnav [data-testid="stColumn"],.st-key-vtabs [data-testid="stColumn"]{min-width:0!important;flex:1 1 0!important;width:auto!important}
  .stApp .st-key-topnav button,.stApp .st-key-vtabs button{padding:.3rem .2rem!important}
  .stApp .st-key-topnav button p,.stApp .st-key-vtabs button p{font-size:14px!important}
  .stApp .st-key-topnav button[data-testid="stBaseButton-primary"] p{color:#fff!important}
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
