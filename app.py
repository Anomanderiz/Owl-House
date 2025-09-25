import streamlit as st
import pandas as pd
import numpy as np
import math, random, io, json, base64, datetime as dt
from PIL import Image, ImageDraw, ImageFont
import os

st.set_page_config(page_title="Night Owls — Waterdeep Secret Club", page_icon="🦉", layout="wide")

# ---------- Assets ----------
def load_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

BG_B64 = load_b64("assets/bg.png")
LOGO = Image.open("assets/logo.png")

GOLD = "#d0a85c"; IVORY = "#eae7e1"

# Provide fallbacks for colours if not already defined elsewhere
try:
    IVORY
except NameError:
    IVORY = "#EAE6D7"
try:
    GOLD
except NameError:
    GOLD = "#D0A85C"

def load_b64_first(*paths):
    for p in paths:
        try:
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            continue
    return ""

RENOWN_IMG_B64 = load_b64_first(
    "assets/renown_gold.png",
    "/mnt/data/cabaed5d-81c5-4b62-bd7d-ed6fccca6077.png"  # fallback
)
NOTORIETY_IMG_B64 = load_b64_first(
    "assets/notoriety_red.png",
    "/mnt/data/bd0e7b0b-2ded-4272-8cd4-4753e0d0c8c8.png"  # fallback
)

st.markdown("""
<style>
/* Let KPI cards breathe; stop columns from cropping the bottom edge/shadow */
.kpi-card, .score-card{
  padding-bottom: 20px !important;
  margin-bottom: 12px !important;
  overflow: visible !important;
}
/* Streamlit column wrappers can clip children; allow overflow */
[data-testid="column"] > div:has(.kpi-card),
[data-testid="column"] > div:has(.score-card){
  overflow: visible !important;
  padding-bottom: 8px !important; /* extra room below the card */
}
</style>
""", unsafe_allow_html=True)

def score_card(title: str, value: int, img_b64: str, trigger_label: str, dom_id: str):
    """Minimal KPI badge: large crest + value; click fires the hidden Streamlit button."""
    html = '''
    <style>
      .score-badge{
        position: relative;
        display: inline-flex;
        align-items: center;
        gap: 14px;
        padding: 6px 0;              /* tiny breathing room; prevents clipping */
        background: transparent;      /* no rectangle */
        border: none;
        cursor: pointer; user-select: none;
      }
      .score-badge img{
        width: 250px; height: 250px; object-fit: contain;
        filter: drop-shadow(0 6px 12px rgba(0,0,0,.35));
      }
      .score-badge .label{
        font-size: 15px; color: __IVORY__; opacity: .85; letter-spacing: .4px;
      }
      .score-badge .val{
        font-size: 56px; color: __IVORY__; font-weight: 800; line-height: 1.05;
        text-shadow: 0 1px 0 rgba(0,0,0,.35);
      }
      @media (max-width: 900px){
        .score-badge img{ width: 72px; height: 72px; }
        .score-badge .val{ font-size: 42px; }
      }
    </style>

    <div class="score-badge" id="__DOMID__" title="Click to view tiers">
      <img src="data:image/png;base64,__IMG__" alt="__TITLE__">
      <div class="meta">
        <div class="label">__TITLE__</div>
        <div class="val">__VALUE__</div>
      </div>
    </div>

    <script>
      (function(){
        /* hide the trigger button and relay clicks to it */
        try{
          const btns = window.parent.document.querySelectorAll('button');
          for (const b of btns) if ((b.innerText||'').trim()==='__TRIGGER__') b.style.display='none';
        }catch(e){}
        const card = document.getElementById('__DOMID__');
        card?.addEventListener('click', ()=>{
          try{
            const btns = window.parent.document.querySelectorAll('button');
            for (const b of btns) { if ((b.innerText||'').trim()==='__TRIGGER__'){ b.click(); break; } }
          }catch(e){}
        });
      })();
    </script>
    '''
    html = (html
            .replace('__IVORY__', IVORY)
            .replace('__TITLE__', str(title))
            .replace('__VALUE__', str(value))
            .replace('__IMG__', img_b64)
            .replace('__TRIGGER__', trigger_label)
            .replace('__DOMID__', dom_id))
    st.components.v1.html(html, height=260)  # taller iFrame so the 96px crest + shadow never clips

def show_renown_tiers():
    html = '''
    <style>
      .tiers {
        margin-top: 10px; padding: 14px 16px; border-radius: 16px;
        background: rgba(16,24,32,.55); border: 1px solid rgba(208,168,92,.45);
        box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
      }
      .tiers h4 { margin: 0 0 6px 0; color: __IVORY__; }
      .tier-table { width: 100%; border-collapse: collapse; color: __IVORY__; }
      .tier-table th, .tier-table td { border-top: 1px solid rgba(208,168,92,.25); padding: 8px 10px; vertical-align: top; }
      .tier-table tr:first-child th, .tier-table tr:first-child td { border-top: none; }
      .tt-badge { color: __GOLD__; font-weight: 700; }
    </style>
    <div class="tiers">
      <h4>Veil-Fame perks — subtle favours while the mask stays on</h4>
      <table class="tier-table">
        <tr><th>Tier</th><th>Threshold</th><th>Perks (quiet, deniable)</th></tr>
        <tr><td class="tt-badge">R1</td><td>5</td><td><b>Street Signals</b>: advantage to glean rumours from labourers/urchins; simple hand-signs recognised in Dock/Field/Trades wards.</td></tr>
        <tr><td class="tt-badge">R2</td><td>10</td><td><b>Quiet Hands</b>: once per session arrange a safe hand-off (stash, message, disguise kit) within a short walk in any ward you’ve worked.</td></tr>
        <tr><td class="tt-badge">R3</td><td>15</td><td><b>Crowd Cover</b>: once per long rest break line-of-sight in a crowd; gain one round of full cover while slipping away.</td></tr>
        <tr><td class="tt-badge">R4</td><td>20</td><td><b>Whisper Network</b>: one social check per scene at advantage vs non-elite townsfolk; plus one free d6 help per session for urban navigation or fast scrounge.</td></tr>
        <tr><td class="tt-badge">R5</td><td>25</td><td><b>Safehouses</b>: two hidden boltholes; short rests can’t be disturbed; once per adventure negate a post-job pursuit.</td></tr>
        <tr><td class="tt-badge">R6</td><td>30</td><td><b>Folk Halo</b> (anonymous): quiet −10% on mundane gear; once per adventure the crowd “coincidentally” intervenes (blocked alley, sudden distraction, etc.).</td></tr>
      </table>
    </div>
    '''
    st.markdown(html.replace('__IVORY__', IVORY).replace('__GOLD__', GOLD), unsafe_allow_html=True)

def show_notoriety_tiers():
    html = '''
    <style>
      .tiers {
        margin-top: 10px; padding: 14px 16px; border-radius: 16px;
        background: rgba(16,24,32,.55); border: 1px solid rgba(208,168,92,.45);
        box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
      }
      .tiers h4 { margin: 0 0 6px 0; color: __IVORY__; }
      .tier-table { width: 100%; border-collapse: collapse; color: __IVORY__; }
      .tier-table th, .tier-table td { border-top: 1px solid rgba(208,168,92,.25); padding: 8px 10px; vertical-align: top; }
      .tier-table tr:first-child th, .tier-table tr:first-child td { border-top: none; }
      .tt-badge { color: #E06565; font-weight: 700; }
    </style>
    <div class="tiers">
      <h4>City Heat — escalating responses without unmasking you</h4>
      <table class="tier-table">
        <tr><th>Band</th><th>Score</th><th>City response (mechanical pressure, no identity reveal)</th></tr>
        <tr><td class="tt-badge">N0 — Cold</td><td>0–4</td><td>Nothing special.</td></tr>
        <tr><td class="tt-badge">N1 — Warm</td><td>5–9</td><td><b>Ward sweeps</b>: after jobs in hot wards, DC X group Stealth/Deception or a patrol drifts close (minor time loss or +1 heat if ignored).</td></tr>
        <tr><td class="tt-badge">N2 — Hot</td><td>10–14</td><td><b>Pattern watch</b>: repeat MOs get +2 DCs; weekly bag checks on kits/disguises—fail adds +1 heat.</td></tr>
        <tr><td class="tt-badge">N3 — Scalding</td><td>15–19</td><td><b>Counter-ops</b>: rivals interfere 1 in 3 missions; residue detectors appear; reusing looks puts Disguise kits at disadvantage.</td></tr>
        <tr><td class="tt-badge">N4 — Burning</td><td>20–24</td><td><b>Scry-sweeps</b>: wide-angle divinations; any arcane casting during ops risks a Trace test (DC X Arcana/Stealth). Fail = +2 heat and a tail to the scene.</td></tr>
        <tr><td class="tt-badge">N5 — Inferno</td><td>25–30</td><td><b>Citywide dragnet</b>: curfews in hot wards; +2 DC to stealth/social; a bounty is posted for any intel on “the impostors”.</td></tr>
      </table>
    </div>
    '''
    st.markdown(html.replace('__IVORY__', IVORY), unsafe_allow_html=True)

# ---------- Styles (Glass + Welcome card) ----------
st.markdown(f"""
<style>
@import url("https://fonts.googleapis.com/css2?family=Cinzel+Decorative:wght@400;700&family=IM+Fell+English+SC&display=swap");
:root {{
  --glass-bg: rgba(12,17,40,0.62);
  --glass-alt: rgba(15,22,50,0.68);
}}
.stApp {{
  background: url("data:image/png;base64,{BG_B64}") no-repeat center center fixed;
  background-size: cover;
}}
.stApp::before {{
  content: "";
  position: fixed; inset: 0; pointer-events: none;
  background:
    radial-gradient(1000px 600px at 50% 20%, rgba(0,0,0,0.28), transparent 70%),
    linear-gradient(to bottom, rgba(0,0,0,0.40), rgba(0,0,0,0.55));
  z-index: 0;
}}
.main .block-container {{
  background: var(--glass-bg);
  backdrop-filter: blur(14px) saturate(1.15);
  -webkit-backdrop-filter: blur(14px) saturate(1.15);
  border: 1px solid rgba(208,168,92,0.22);
  border-radius: 24px;
  box-shadow: 0 20px 50px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);
  padding: 1.2rem 1.5rem !important;
  z-index: 1;
}}
h1, h2, h3, h4 {{ color: {IVORY}; text-shadow: 0 1px 0 rgba(0,0,0,0.35); }}
.kpi {{
  border: 1px solid rgba(208,168,92,0.25);
  padding: 0.8rem 1rem; border-radius: 18px;
  background: var(--glass-alt);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04);
}}
.stTabs [data-baseweb="tab-list"] {{ gap: .25rem; }}
.stTabs [data-baseweb="tab"] {{
  color: {IVORY};
  background: rgba(18,27,60,0.55);
  border: 1px solid rgba(208,168,92,0.18);
  border-bottom: 2px solid transparent;
  border-top-left-radius: 14px; border-top-right-radius: 14px;
  padding: .5rem .9rem;
}}
.stTabs [aria-selected="true"] {{
  background: rgba(18,27,60,0.78);
  border-color: rgba(208,168,92,0.35);
  border-bottom-color: {GOLD};
}}
#wheel_container {{ position: relative; width: 600px; height: 600px; margin: 0 auto; }}
#wheel_img {{
  width: 100%; height: 100%; border-radius: 50%;
  box-shadow: 0 10px 40px rgba(0,0,0,.55);
  background: radial-gradient(closest-side, rgba(255,255,255,0.06), transparent);
}}
#pointer {{
  position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
  width: 0; height: 0; border-left: 16px solid transparent; border-right: 16px solid transparent;
  border-bottom: 26px solid {GOLD}; filter: drop-shadow(0 2px 2px rgba(0,0,0,.4));
}}
.dataframe tbody tr {{ background: rgba(10,15,36,0.35); }}
.dataframe thead tr {{ background: rgba(10,15,36,0.55); }}

/* Welcome card in sidebar */
.welcome {{
  border: 1px solid rgba(208,168,92,0.35);
  border-radius: 18px;
  padding: 1rem 1.1rem;
  background: rgba(14,18,38,0.70);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 10px 30px rgba(0,0,0,0.35);
}}
.welcome h3 {{ font-family: "Cinzel Decorative", serif; color: {IVORY}; margin: 0 0 .35rem 0; }}
.welcome p {{ font-family: "IM Fell English SC", serif; font-size: 1.05rem; line-height: 1.3; color: {IVORY}; opacity: .92; }}
/* Hide Streamlit top bar / header / footer / menu */
header, footer, #MainMenu {{ visibility: hidden; }}
[data-testid="stToolbar"] {{ visibility: hidden; height: 0; position: fixed; }}
/* tighten top spacing a hair since the header is gone */
.main .block-container {{ padding-top: 0.8rem !important; }}

/* extra belt-and-suspenders for newer builds */
div[data-testid="stHeader"] {{ display: none; }}
</style>
""", unsafe_allow_html=True)

# ---------- Global gold borders & button glow ----------
st.markdown(f"""
<style>
/* Gold-rim boxes: inputs, tables, alerts, widgets, tabs, etc. */
.stTextInput > div, .stNumberInput > div, .stSelectbox > div, .stMultiSelect > div,
.stTextArea > div, .stFileUploader > div, .stAlert, .stDataFrame,
.stTabs [data-baseweb="tab"], .st-expander, .stMetric, .stCaptionContainer,
.kpi, .welcome, .result-card {{
  border: 1px solid rgba(208,168,92,.35) !important;
  border-radius: 14px !important;
  box-shadow: 0 10px 24px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.06) !important;
  background: rgba(14,18,38,.60);
}}
/* Buttons (including download/link buttons) */
.stButton > button, .stDownloadButton > button, .stLinkButton > a {{
  border: 1px solid rgba(208,168,92,.55);
  color: {IVORY} !important;
  background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02));
  border-radius: 12px; padding: .5rem .9rem;
  box-shadow: 0 6px 16px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.06);
  transition: border-color .15s ease, box-shadow .15s ease, transform .05s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover {{
  border-color: {GOLD};
  box-shadow: 0 8px 22px rgba(0,0,0,.35), 0 0 0 2px rgba(208,168,92,.25) inset;
  transform: translateY(-1px);
}}
</style>
""", unsafe_allow_html=True)

# ---- scrub any accidental hex-code echoes from the top of the page ----
st.components.v1.html("""
<script>
(function(){
  const kill = ['#eae7e1', '#d0a85c'];
  try{
    const scope = window.parent?.document || document;
    scope.querySelectorAll('p,div,span,code').forEach(el=>{
      const t=(el.textContent||'').trim();
      if (kill.includes(t)) el.style.display='none';
    });
  }catch(e){}
})();
</script>
""", height=0)

# ---------- State ----------
if "renown" not in st.session_state: st.session_state.renown = 0
if "notoriety" not in st.session_state: st.session_state.notoriety = 0
if "ledger" not in st.session_state:
    st.session_state.ledger = pd.DataFrame(columns=[
        "timestamp","ward","archetype","BI","EB","OQM",
        "renown_gain","notoriety_gain","EI_breakdown","notes","complication"
    ])
if "last_angle" not in st.session_state: st.session_state.last_angle = 0

# ---------- Google Sheets (via Streamlit secrets) ----------
@st.cache_resource(show_spinner=False)
def _build_gspread_client(sa_json: dict):
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(sa_json, scopes=scopes)
    return gspread.authorize(creds)

def _load_sheets_secrets():
    """
    Expect .streamlit/secrets.toml with:

    [sheets]
    sheet_id = "YOUR_SHEET_ID"
    worksheet = "Log"         # optional, defaults to "Log"

    [gcp_service_account]     # full service-account JSON fields
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
    client_email = "..."
    client_id = "..."
    token_uri = "https://oauth2.googleapis.com/token"
    """
    try:
        sa_json = dict(st.secrets["gcp_service_account"])
        cfg = st.secrets["sheets"]
        sheet_id = cfg.get("sheet_id", "")
        ws_name = cfg.get("worksheet", "Log")
        if not (sa_json and sheet_id):
            return None, None, None, "Missing gcp_service_account or sheets.sheet_id in secrets."
        return sa_json, sheet_id, ws_name, None
    except Exception as e:
        return None, None, None, str(e)

def _ensure_worksheet(sa_json, sheet_id, worksheet_name="Log"):
    try:
        import gspread
        gc = _build_gspread_client(sa_json)
        sh = gc.open_by_key(sheet_id)
        try:
            sh.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=worksheet_name, rows="1000", cols="20")
            ws.append_row(list(st.session_state.ledger.columns))
        return True, None
    except Exception as e:
        return False, str(e)

def append_to_google_sheet(rows: list):
    sa_json, sheet_id, ws_name, err = _load_sheets_secrets()
    if err:
        return False, err
    ok, err = _ensure_worksheet(sa_json, sheet_id, worksheet_name=ws_name)
    if not ok:
        return False, err
    try:
        gc = _build_gspread_client(sa_json)
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(ws_name)
        for r in rows:
            ws.append_row(r, value_input_option="USER_ENTERED")
        return True, None
    except Exception as e:
        return False, str(e)

# ---------- Persistent load from Google Sheets ----------
@st.cache_data(ttl=60, show_spinner=False)
def load_ledger_from_sheets():
    """Return (df, err). df has correct dtypes or empty DF on new sheet."""
    sa_json, sheet_id, ws_name, err = _load_sheets_secrets()
    if err:
        return pd.DataFrame(columns=st.session_state.ledger.columns), err
    ok, err = _ensure_worksheet(sa_json, sheet_id, worksheet_name=ws_name)
    if not ok:
        return pd.DataFrame(columns=st.session_state.ledger.columns), err
    try:
        gc = _build_gspread_client(sa_json)
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(ws_name)
        values = ws.get_all_values()  # header + rows
        if not values:
            return pd.DataFrame(columns=st.session_state.ledger.columns), None
        df = pd.DataFrame(values[1:], columns=values[0])  # skip header

        # normalize / coerce numeric cols
        for col in ["BI", "EB", "OQM", "renown_gain", "notoriety_gain"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        return df, None
    except Exception as e:
        return pd.DataFrame(columns=st.session_state.ledger.columns), str(e)

def recalc_totals(df: pd.DataFrame):
    r = int(pd.to_numeric(df.get("renown_gain", pd.Series()), errors="coerce").fillna(0).sum())
    n = int(pd.to_numeric(df.get("notoriety_gain", pd.Series()), errors="coerce").fillna(0).sum())
    return r, n

# ---------- Bootstrap from Sheets once ----------
if "bootstrapped" not in st.session_state:
    df_remote, err = load_ledger_from_sheets()
    if err:
        st.sidebar.info("Sheets not loaded (check secrets or access). Running with local session state.")
    else:
        if not df_remote.empty:
            st.session_state.ledger = df_remote
        st.session_state.renown, st.session_state.notoriety = recalc_totals(st.session_state.ledger)
    st.session_state.bootstrapped = True

# ---------- Mechanics ----------
def clamp(v, lo, hi): return max(lo, min(hi, v))
def heat_multiplier(n): return 1.5 if n>=20 else (1.25 if n>=10 else 1.0)
def renown_from_score(base, arc): return int(round(base * {"Help the Poor":1.0,"Sabotage Evil":1.5,"Expose Corruption":2.0}[arc]))
def notoriety_gain(cat_base, EI, n): return max(0, math.ceil((cat_base + max(0, EI-1)) * heat_multiplier(n)))
def compute_BI(arc, inputs):
    if arc=="Help the Poor":
        spend=inputs.get("spend",0); hh=inputs.get("households",0)
        sb = 1 if spend<25 else 2 if spend<50 else 3 if spend<100 else 4 if spend<200 else 5
        hb = 1 if hh<10 else 2 if hh<25 else 3 if hh<50 else 4 if hh<100 else 5
        return max(sb,hb)
    if arc=="Sabotage Evil": return inputs.get("impact_level",1)
    return inputs.get("expose_level",1)
def compute_base_score(BI, EB, OQM_list): return clamp(BI+EB+clamp(sum(OQM_list),-2,2),1,7)
def compute_EI(vals):
    vis,noise,sig,wit,mag,conc,mis = vals
    return (vis+noise+sig+wit+mag)-(conc+mis)
def low_or_high(n): return "High" if n>=10 else "Low"

# ---------- Sidebar (Welcome only) ----------
with st.sidebar:
    st.image(LOGO, use_column_width=True)
    st.markdown("""
    <div class="welcome">
      <h3>Night Owls</h3>
      <p>By moonlight take flight,\n
      By your deed will the city be freed.\n
      You give a hoot!</p>
    </div>
    """, unsafe_allow_html=True)

# Put the mural file in /assets (or keep your current path)
MURAL_B64 = load_b64_first(
    "assets/mural_sidebar.png",
    "assets/mural.png",
)

MURAL_H      = 1120      # height of the mural area in px (tune to taste)
MURAL_OPACITY = 0.8    # 0 = invisible, 1 = opaque

st.sidebar.markdown(f"""
<style>
/* Ensure the sidebar can host positioned children */
[data-testid="stSidebar"] {{ position: relative; }}

/* A dedicated block that paints the mural and ignores pointer events */
#sidebar-mural {{
  position: relative;
  height: {MURAL_H}px;
  margin-top: 8px;                 /* sits just beneath your text box */
  z-index: 0;
}}
#sidebar-mural::before {{
  content: "";
  position: absolute; inset: 0;
  background: url("data:image/png;base64,{MURAL_B64}") no-repeat center top / contain;
  opacity: {MURAL_OPACITY};
  pointer-events: none;            /* don't block clicks/scrolls */
  filter: drop-shadow(0 6px 12px rgba(0,0,0,.25));
}}
</style>
<div id="sidebar-mural" aria-hidden="true"></div>
""", unsafe_allow_html=True)

# ---------- KPI score cards (click to reveal tiers) ----------
RENOWN_TRIGGER_LABEL = "RENOWN_SCORE_CARD__CLICK"
NOTORIETY_TRIGGER_LABEL = "NOTORIETY_SCORE_CARD__CLICK"
renown_clicked = st.button(RENOWN_TRIGGER_LABEL, key="renown_hidden_click")
notor_clicked  = st.button(NOTORIETY_TRIGGER_LABEL, key="notoriety_hidden_click")

if renown_clicked:
    st.session_state["show_renown_tiers"] = not st.session_state.get("show_renown_tiers", False)
if notor_clicked:
    st.session_state["show_notoriety_tiers"] = not st.session_state.get("show_notoriety_tiers", False)

c1, c2, c3 = st.columns(3)

with c1:
    score_card("Renown", st.session_state.renown, RENOWN_IMG_B64,
               RENOWN_TRIGGER_LABEL, "renown_card_dom")

with c2:
    score_card("Notoriety", st.session_state.notoriety, NOTORIETY_IMG_B64,
               NOTORIETY_TRIGGER_LABEL, "notoriety_card_dom")

    # --- heat controls live directly under Notoriety ---
    btnL, btnP = st.columns(2)

    with btnL:
        if st.button("Lie Low (−1/−2 Heat)", key="btn_lie_low"):
            drop = 2 if st.session_state.notoriety >= 10 else 1
            st.session_state.notoriety = max(0, st.session_state.notoriety - drop)
            # log + try to sync (unchanged)
            adj = [dt.datetime.now().isoformat(timespec="seconds"), ward_focus,
                   "Adjustment: Lie Low", "-", "-", "-", 0, -drop, "-", "auto", ""]
            st.session_state.ledger.loc[len(st.session_state.ledger)] = adj
            ok, err = append_to_google_sheet([adj])
            if ok:
                df_remote, _ = load_ledger_from_sheets()
                if not df_remote.empty: st.session_state.ledger = df_remote
                st.session_state.renown, st.session_state.notoriety = recalc_totals(st.session_state.ledger)
                st.success(f"Heat reduced by {drop} and logged.")
            else:
                st.warning(f"Logged locally but not synced: {err or 'check secrets/permissions'}")

    with btnP:
        if st.button("Proxy Charity (−1 Heat)", key="btn_proxy_charity"):
            st.session_state.notoriety = max(0, st.session_state.notoriety - 1)
            adj = [dt.datetime.now().isoformat(timespec="seconds"), ward_focus,
                   "Adjustment: Proxy Charity", "-", "-", "-", 0, -1, "-", "auto", ""]
            st.session_state.ledger.loc[len(st.session_state.ledger)] = adj
            ok, err = append_to_google_sheet([adj])
            if ok:
                df_remote, _ = load_ledger_from_sheets()
                if not df_remote.empty: st.session_state.ledger = df_remote
                st.session_state.renown, st.session_state.notoriety = recalc_totals(st.session_state.ledger)
                st.success("Heat −1 and logged.")
            else:
                st.warning(f"Logged locally but not synced: {err or 'check secrets/permissions'}")

with c3:
    ward_focus = st.selectbox("Active Ward", ["Dock","Field","South","North","Castle","Trades","Sea"])

tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Mission Generator","🎯 Resolve & Log","☸️ Wheel of Fortune","📜 Ledger"])

# ---------- Tab 1 ----------
with tab1:
    st.markdown("### Create a Mission")
    arc = st.radio("Archetype", ["Help the Poor","Sabotage Evil","Expose Corruption"], horizontal=True)
    col1,col2,col3 = st.columns(3)
    if arc=="Help the Poor":
        spend = col1.number_input("Gold Spent", 0, step=5, value=40)
        hh = col2.number_input("Households Aided", 0, step=5, value=25)
        plan = col3.checkbox("Solid Plan (+1 OQM)", True)
        inputs = {"spend":spend,"households":hh}
    elif arc=="Sabotage Evil":
        impact = col1.slider("Impact Level (1 minor→5 dismantled)",1,5,3)
        plan = col2.checkbox("Inside Contact (+1 OQM)")
        rushed = col3.checkbox("Rushed/Loud (−1 OQM)")
        inputs = {"impact_level":impact}
    else:
        expose = col1.slider("Exposure Level (1 clerk→5 city scandal)",1,5,3)
        proof = col2.checkbox("Hard Proof / Magical Corroboration (+1 OQM)")
        reused = col3.checkbox("Reused Signature (−1 OQM)")
        inputs = {"expose_level":expose}

    st.markdown("#### Execution")
    e1,e2,e3 = st.columns(3)
    with e1: margin = st.number_input("Success Margin",0,20,2)
    with e2: nat20 = st.checkbox("Natural 20")
    with e3: nat1 = st.checkbox("Critical botch")
    EB = 3 if nat20 else (2 if margin>=5 else (1 if margin>=1 else 0))

    OQM = []
    if arc=="Help the Poor":
        if plan: OQM.append(+1)
    if arc=="Sabotage Evil":
        if plan: OQM.append(+1)
        if rushed: OQM.append(-1)
    if arc=="Expose Corruption":
        if proof: OQM.append(+1)
        if reused: OQM.append(-1)

    BI = compute_BI(arc, inputs)
    base_score = compute_base_score(BI, EB, OQM)
    st.markdown(f"**Base Impact:** {BI} • **EB:** {EB} • **OQM sum:** {sum(OQM)} → **Base Score:** {base_score}")

    st.markdown("#### Exposure Index")
    a,b = st.columns(2)
    with a:
        vis = st.slider("Visibility (0–3)",0,3,1)
        noise = st.slider("Noise (0–3)",0,3,1)
        sig = st.slider("Signature (0–2)",0,2,0)
        wit = st.slider("Witnesses (0–2)",0,2,1)
    with b:
        mag = st.slider("Magic Trace (0–2)",0,2,0)
        conc = st.slider("Concealment (0–3)",0,3,2)
        mis = st.slider("Misdirection (0–2)",0,2,1)

    EI = (vis+noise+sig+wit+mag)-(conc+mis)
    ren_gain = int(round(base_score * {"Help the Poor":1.0,"Sabotage Evil":1.5,"Expose Corruption":2.0}[arc]))
    def _hm(n): return 1.5 if n>=20 else (1.25 if n>=10 else 1.0)
    cat_base = {"Help the Poor":1,"Sabotage Evil":2,"Expose Corruption":3}[arc]
    heat = max(0, math.ceil((cat_base + max(0,EI-1) + (1 if nat1 else 0)) * _hm(st.session_state.notoriety)))
    if nat20: heat = max(0, heat-1)

    st.markdown(f"**Projected Renown:** {ren_gain} • **Projected Notoriety:** {heat} • **EI:** {EI}")

    if st.button("Queue Mission → Resolve & Log", type="primary"):
        st.session_state._queued_mission = dict(
            ward=ward_focus, archetype=arc, BI=BI, EB=EB, OQM=sum(OQM),
            renown_gain=ren_gain, notoriety_gain=heat,
            EI_breakdown={"visibility":vis,"noise":noise,"signature":sig,"witnesses":wit,"magic":mag,"concealment":conc,"misdirection":mis}
        )
        st.success("Mission queued.")

# ---------- Tab 2 ----------
with tab2:
    st.markdown("### Resolve Mission & Write to Log")
    q = st.session_state.get("_queued_mission")
    if q:
        st.json(q)
        notes = st.text_input("Notes (optional)", "")
        if st.button("Apply Gains & Log", type="primary"):
            st.session_state.renown += q["renown_gain"]
            st.session_state.notoriety += q["notoriety_gain"]

            row = [
                dt.datetime.now().isoformat(timespec="seconds"), q["ward"], q["archetype"],
                q["BI"], q["EB"], q["OQM"], q["renown_gain"], q["notoriety_gain"],
                json.dumps(q["EI_breakdown"]), notes, ""
            ]
            # add locally
            st.session_state.ledger.loc[len(st.session_state.ledger)] = row

            # try to persist immediately
            ok, err = append_to_google_sheet([row])
            if ok:
                st.success("Applied, logged, and synced to Google Sheets.")
                # reload from sheets so counters reflect any external edits
                df_remote, _ = load_ledger_from_sheets()
                if not df_remote.empty:
                    st.session_state.ledger = df_remote
                st.session_state.renown, st.session_state.notoriety = recalc_totals(st.session_state.ledger)
            else:
                st.warning(f"Applied & logged locally, but not synced: {err or 'check secrets/permissions'}")

            st.session_state._queued_mission = None

    else:
        st.info("No queued mission.")

    st.markdown("#### Push Log to Google Sheets")
    if st.button("Append All Rows to Sheets", type="secondary"):
        rows = st.session_state.ledger.values.tolist()
        ok, err = append_to_google_sheet(rows)
        if ok:
            st.success(f"Appended {len(rows)} rows.")
        else:
            st.error(f"Sheets error: {err or 'Unknown error'}")

# ---------- Tab 3 ----------
with tab3:
    st.markdown("### Wheel of Fortune")

    # ---------- defaults & palette ----------
    st.session_state.setdefault("last_angle", 0)
    st.session_state.setdefault("selected_index", None)

    GOLD  = globals().get("GOLD",  "#d0a85c")
    IVORY = globals().get("IVORY", "#eae7e1")

    # --- sizing & feel ---
    WHEEL_SIZE = 600
    SPIN_ROTATIONS = random.randint(4, 7)

    # --- table by heat ---
    heat_state = "High" if st.session_state.notoriety >= 10 else "Low"
    st.caption(f"Heat: **{heat_state}**")
    table_path = "assets/complications_high.json" if heat_state == "High" else "assets/complications_low.json"
    options = json.load(open(table_path, "r"))

    # --- draw wheel helpers ---
    def draw_wheel(labels, colors=None, size=WHEEL_SIZE):
        n = len(labels)
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        cx, cy = size // 2, size // 2
        r = size // 2 - 6
        cols = colors or ["#173b5a", "#12213f", "#0d3b4f", "#112b44"]
        for i, _ in enumerate(labels):
            start = 360 * i / n - 90
            end   = 360 * (i + 1) / n - 90
            d.pieslice([cx - r, cy - r, cx + r, cy + r], start, end,
                       fill=cols[i % len(cols)], outline="#213a53")
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GOLD, width=6)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 14)
        except:
            font = ImageFont.load_default()
        for i, lab in enumerate(labels):
            ang = math.radians(360 * (i + .5) / n - 90)
            tx = cx + int((r - 60) * math.cos(ang))
            ty = cy + int((r - 60) * math.sin(ang))
            d.text((tx, ty), lab, fill=IVORY, font=font, anchor="mm")
        return img

    def b64(img):
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        import base64
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    wheel_b64 = b64(draw_wheel([str(i + 1) for i in range(len(options))], size=WHEEL_SIZE))

    # ---------- hidden Streamlit trigger (clicked by the centre overlay) ----------
    HIDDEN_LABEL = "SPIN_TRIGGER__73ab"   # keep it machine-ish and unique
    hidden_clicked = st.button(HIDDEN_LABEL, key="spin_hidden_internal")

    if hidden_clicked:
        n = len(options)
        idx = random.randrange(n)
        st.session_state.selected_index = idx
        seg = 360 / n
        st.session_state.last_angle = SPIN_ROTATIONS * 360 + (idx + .5) * seg

        # journal entry (soft-fails if not configured)
        try:
            comp = options[idx]
            row = [dt.datetime.now().isoformat(timespec="seconds"),
                   ward_focus, "Complication", "-", "-", "-", 0, 0, "-", "-", comp]
            st.session_state.ledger.loc[len(st.session_state.ledger)] = row
        except Exception:
            pass

    angle = st.session_state.last_angle
    btn_diam = max(96, int(WHEEL_SIZE * 0.18))

    # ---------- wheel + true centre overlay button ----------
    html = f"""
    <style>
      #wheel_wrap {{
        position: relative; width: {WHEEL_SIZE}px; margin: 0 auto;
      }}
      #wheel_container {{
        position: relative; width: {WHEEL_SIZE}px; height: {WHEEL_SIZE}px;
      }}
      #wheel_img {{
        width: 100%; height: 100%; border-radius: 50%;
        box-shadow: 0 10px 40px rgba(0,0,0,.55);
        background: radial-gradient(closest-side, rgba(255,255,255,0.06), transparent);
      }}
      #pointer {{
        position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
        width: 0; height: 0; border-left: 16px solid transparent; border-right: 16px solid transparent;
        border-bottom: 26px solid {GOLD}; filter: drop-shadow(0 2px 2px rgba(0,0,0,.4));
      }}
      #spin_overlay {{
        position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%);
        width: {btn_diam}px; height: {btn_diam}px; border-radius: {btn_diam/2}px;
        border: 1px solid rgba(208,168,92,0.45);
        background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02));
        backdrop-filter: blur(8px) saturate(1.1);
        -webkit-backdrop-filter: blur(8px) saturate(1.1);
        box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,0.06);
        color: {IVORY}; font-weight: 700; letter-spacing: .5px; text-transform: uppercase;
        cursor: pointer; user-select: none; display: grid; place-items: center;
      }}
      #spin_overlay:hover {{ transform: translate(-50%,-50%) scale(1.02); }}
    </style>

    <div id="wheel_wrap">
      <div id="wheel_container">
        <div id="pointer"></div>
        <img id="wheel_img" src="data:image/png;base64,{wheel_b64}" />
        <div id="spin_overlay">SPIN!</div>
      </div>
    </div>

    <script>
      // Hide the real Streamlit trigger button immediately
      (function() {{
        try {{
          const btns = window.parent.document.querySelectorAll('button');
          for (const b of btns) {{
            if ((b.innerText || '').trim() === '{HIDDEN_LABEL}') {{
              b.style.display = 'none';
              break;
            }}
          }}
        }} catch (e) {{}}
      }})();

      // Overlay → click hidden Streamlit button
      document.getElementById('spin_overlay').addEventListener('click', () => {{
        try {{
          const btns = window.parent.document.querySelectorAll('button');
          for (const b of btns) {{
            if ((b.innerText || '').trim() === '{HIDDEN_LABEL}') {{ b.click(); break; }}
          }}
        }} catch (e) {{}}
      }});

      // Animate wheel to latest angle
      const w = document.getElementById('wheel_img');
      if (w) {{
        w.style.transition = 'transform 3.2s cubic-bezier(.17,.67,.32,1.35)';
        requestAnimationFrame(() => {{ w.style.transform = 'rotate({angle}deg)'; }});
      }}
    </script>
    """
    st.components.v1.html(html, height=WHEEL_SIZE + 40)

    # ---------- Result card (dynamic, bordered, pretty) ----------
if st.session_state.get("selected_index") is not None:
    idx = st.session_state["selected_index"]
    st.markdown(f"""
    <style>
      .result-card {{
        max-width: 900px; margin: 18px auto 0; padding: 18px 20px;
        border-radius: 14px;
        background: rgba(16,24,32,0.55);
        border: 1px solid rgba(208,168,92,0.45);
        box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,0.06);
        backdrop-filter: blur(6px) saturate(1.05);
        -webkit-backdrop-filter: blur(6px) saturate(1.05);
        animation: fadein .35s ease-out;
      }}
      .result-number {{
        font-size: 13px; letter-spacing: .4px; color: {GOLD}; text-transform: uppercase; opacity: .9;
        margin-bottom: 6px;
      }}
      .result-text {{
        color: {IVORY}; line-height: 1.5; font-size: 16px;
      }}
      @keyframes fadein {{
        from {{ opacity: 0; transform: translateY(6px); }}
        to   {{ opacity: 1; transform: none; }}
      }}
    </style>
    <div class="result-card">
      <div class="result-number">Result {idx+1:02d} / {len(options):02d}</div>
      <div class="result-text">{options[idx]}</div>
    </div>
    """, unsafe_allow_html=True)
# ---------- Tab 4 ----------
with tab4:
    st.markdown("### Ledger")
    if st.button("Refresh from Google Sheets", type="secondary"):
        df_remote, err = load_ledger_from_sheets()
        if err:
            st.error(f"Reload failed: {err}")
        else:
            st.session_state.ledger = df_remote
            st.session_state.renown, st.session_state.notoriety = recalc_totals(st.session_state.ledger)
            st.success("Ledger reloaded and counters recalculated.")
    st.dataframe(st.session_state.ledger, use_container_width=True, height=420)
    csv = st.session_state.ledger.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "night_owls_ledger.csv", "text/csv")
