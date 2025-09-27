import streamlit as st
import pandas as pd
import numpy as np
import math, random, io, json, base64, datetime as dt, os
from typing import Tuple, List
from PIL import Image, ImageDraw, ImageFont

# ------------------------------------------------------------
# Page config
# ------------------------------------------------------------
st.set_page_config(page_title="Night Owls — Waterdeep Secret Club", page_icon="🦉", layout="wide")

# ------------------------------------------------------------
# Cached helpers
# ------------------------------------------------------------
@st.cache_data(show_spinner=False)
def b64_of(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

@st.cache_data(show_spinner=False)
def first_existing_b64(paths: Tuple[str, ...]) -> str:
    for p in paths:
        try:
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            continue
    return ""

@st.cache_data(show_spinner=False)
def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

@st.cache_data(show_spinner=False, max_entries=8)
def load_complications(heat_state: str) -> List[str]:
    table_path = "assets/complications_high.json" if heat_state == "High" else "assets/complications_low.json"
    with open(table_path, "r") as fh:
        return json.load(fh)

@st.cache_data(show_spinner=False, max_entries=8)
def build_wheel_b64(labels: Tuple[str, ...], size: int, gold: str, ivory: str) -> str:
    n = len(labels)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 6
    cols = ["#173b5a", "#12213f", "#0d3b4f", "#112b44"]
    for i in range(n):
        start = 360 * i / n - 90
        end   = 360 * (i + 1) / n - 90
        d.pieslice([cx - r, cy - r, cx + r, cy + r], start, end,
                   fill=cols[i % len(cols)], outline="#213a53")
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=gold, width=6)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    for i, lab in enumerate(labels):
        ang = math.radians(360 * (i + .5) / n - 90)
        tx = cx + int((r - 60) * math.cos(ang))
        ty = cy + int((r - 60) * math.sin(ang))
        d.text((tx, ty), lab, fill=ivory, font=font, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

# ------------------------------------------------------------
# Assets & theme colours (define before any f-strings)
# ------------------------------------------------------------
BG_B64 = b64_of("assets/bg.png")
LOGO = Image.open(io.BytesIO(read_bytes("assets/logo.png")))

RENOWN_IMG_B64 = first_existing_b64((
    "assets/renown_gold.png",
    "assets/renown.png",
))
NOTORIETY_IMG_B64 = first_existing_b64((
    "assets/notoriety_red.png",
    "assets/notoriety.png",
))
MURAL_B64 = first_existing_b64((
    "assets/mural_sidebar.png",
    "assets/mural.png",
))

GOLD  = "#d0a85c"
IVORY = "#eae7e1"

# ------------------------------------------------------------
# Global styles
# ------------------------------------------------------------
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
  padding: 1.2rem 1.5rem !important; z-index: 1;
}}
h1, h2, h3, h4 {{ color: {IVORY}; text-shadow: 0 1px 0 rgba(0,0,0,0.35); }}
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
/* Sidebar welcome card + mural */
.welcome {{
  border: 1px solid rgba(208,168,92,0.35);
  border-radius: 18px; padding: 1rem 1.1rem;
  background: rgba(14,18,38,0.70);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.04), 0 10px 30px rgba(0,0,0,0.35);
}}
.welcome h3 {{ font-family: "Cinzel Decorative", serif; color: {IVORY}; margin: 0 0 .35rem 0; }}
.welcome p {{ font-family: "IM Fell English SC", serif; font-size: 1.05rem; line-height: 1.3; color: {IVORY}; opacity: .92; }}
/* Hide Streamlit chrome */
header, footer, #MainMenu {{ visibility: hidden; }}
[data-testid="stToolbar"] {{ visibility: hidden; height: 0; position: fixed; }}
.main .block-container {{ padding-top: 0.8rem !important; }}
div[data-testid="stHeader"] {{ display: none; }}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# State & ledger bootstrap
# ------------------------------------------------------------
if "renown" not in st.session_state: st.session_state.renown = 0
if "notoriety" not in st.session_state: st.session_state.notoriety = 0
if "ledger" not in st.session_state:
    st.session_state.ledger = pd.DataFrame(columns=[
        "timestamp","ward","archetype","BI","EB","OQM",
        "renown_gain","notoriety_gain","EI_breakdown","notes","complication"
    ])
if "last_angle" not in st.session_state: st.session_state.last_angle = 0
if "selected_index" not in st.session_state: st.session_state.selected_index = None

# ------------------------------------------------------------
# Google Sheets (optional – safe no-ops if secrets missing)
# ------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _build_gspread_client(sa_json: dict):
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(sa_json, scopes=scopes)
    return gspread.authorize(creds)

def _load_sheets_secrets():
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

@st.cache_data(ttl=60, show_spinner=False)
def load_ledger_from_sheets():
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
        values = ws.get_all_values()
        if not values:
            return pd.DataFrame(columns=st.session_state.ledger.columns), None
        df = pd.DataFrame(values[1:], columns=values[0])
        for col in ["BI", "EB", "OQM", "renown_gain", "notoriety_gain"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        return df, None
    except Exception as e:
        return pd.DataFrame(columns=st.session_state.ledger.columns), str(e)

# ------------------------------------------------------------
# Mechanics helpers
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# Sidebar (logo + welcome + mural)
# ------------------------------------------------------------
with st.sidebar:
    st.image(LOGO, use_column_width=True)
    st.markdown("""
    <div class="welcome">
      <h3>Night Owls</h3>
      <p>By moonlight take flight,<br>
      By your deed will the city be freed.<br>
      You give a hoot!</p>
    </div>
    """, unsafe_allow_html=True)

st.sidebar.markdown(f"""
<style>
[data-testid="stSidebar"] {{ position: relative; }}
#sidebar-mural {{
  position: relative; height: 1120px; margin-top: 8px; z-index: 0;
}}
#sidebar-mural::before {{
  content: ""; position: absolute; inset: 0;
  background: url("data:image/png;base64,{MURAL_B64}") no-repeat center top / contain;
  opacity: 0.8; pointer-events: none;
  filter: drop-shadow(0 6px 12px rgba(0,0,0,0.25));
}}
</style>
<div id="sidebar-mural" aria-hidden="true"></div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------
# Crest + tiers — single component (no cross-frame)
# ------------------------------------------------------------
def render_renown_block(value: int):
    html = f"""
    <style>
      .score-wrap {{
        display:flex; align-items:center; gap:14px; cursor:pointer; user-select:none;
      }}
      .score-wrap img{{ width: 180px; height:180px; object-fit:contain;
        filter: drop-shadow(0 6px 12px rgba(0,0,0,.35)); }}
      .score-wrap .meta .label{{ font-size:15px; color:{IVORY}; opacity:.85; letter-spacing:.4px; }}
      .score-wrap .meta .val{{ font-size:56px; color:{IVORY}; font-weight:800; line-height:1.05; text-shadow:0 1px 0 rgba(0,0,0,.35); }}
      .tiers {{ margin-top:10px; padding:14px 16px; border-radius:16px;
        background: rgba(16,24,32,.55); border:1px solid rgba(208,168,92,.45);
        box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06); }}
      .tiers h4 {{ margin:0 0 6px 0; color:{IVORY}; }}
      .tier-table {{ width:100%; border-collapse:collapse; color:{IVORY}; }}
      .tier-table th, .tier-table td {{ border-top:1px solid rgba(208,168,92,.25); padding:8px 10px; vertical-align:top; }}
      .tier-table tr:first-child th, .tier-table tr:first-child td {{ border-top:none; }}
      .tt-badge {{ color:{GOLD}; font-weight:700; }}
      #renown_tiers:not(.open) {{ display:none; }}
    </style>
    <div id="renown_card" class="score-wrap" title="Click to view tiers">
      <img src="data:image/png;base64,{RENOWN_IMG_B64}" alt="Renown">
      <div class="meta"><div class="label">Renown</div><div class="val">{value}</div></div>
    </div>
    <div id="renown_tiers" class="tiers">
      <h4>Veil-Fame perks — subtle favours while the mask stays on</h4>
      <table class="tier-table">
        <tr><th>Tier</th><th>Threshold</th><th>Perks</th></tr>
        <tr><td class="tt-badge">R1</td><td>5</td><td>Street Signals (rumours + ward hand-signs).</td></tr>
        <tr><td class="tt-badge">R2</td><td>10</td><td>Quiet Hands (once/session safe hand-off nearby).</td></tr>
        <tr><td class="tt-badge">R3</td><td>15</td><td>Crowd Cover (one round full cover slip-away).</td></tr>
        <tr><td class="tt-badge">R4</td><td>20</td><td>Whisper Network (advantage vs townsfolk; +1d6 help/session).</td></tr>
        <tr><td class="tt-badge">R5</td><td>25</td><td>Safehouses (two boltholes; negate one pursuit/adventure).</td></tr>
        <tr><td class="tt-badge">R6</td><td>30</td><td>Folk Halo (quiet −10% mundane gear; crowd aid once/adventure).</td></tr>
      </table>
    </div>
    <script>
      document.getElementById('renown_card')?.addEventListener('click',()=>{
        const el = document.getElementById('renown_tiers');
        if (el) el.classList.toggle('open');
      });
    </script>
    """
    st.components.v1.html(html, height=260 + 220)

def render_notoriety_block(value: int):
    html = f"""
    <style>
      .score-wrap {{
        display:flex; align-items:center; gap:14px; cursor:pointer; user-select:none;
      }}
      .score-wrap img{{ width: 180px; height:180px; object-fit:contain;
        filter: drop-shadow(0 6px 12px rgba(0,0,0,.35)); }}
      .score-wrap .meta .label{{ font-size:15px; color:{IVORY}; opacity:.85; letter-spacing:.4px; }}
      .score-wrap .meta .val{{ font-size:56px; color:{IVORY}; font-weight:800; line-height:1.05; text-shadow:0 1px 0 rgba(0,0,0,.35); }}
      .tiers {{ margin-top:10px; padding:14px 16px; border-radius:16px;
        background: rgba(16,24,32,.55); border:1px solid rgba(208,168,92,.45);
        box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06); }}
      .tiers h4 {{ margin:0 0 6px 0; color:{IVORY}; }}
      .tier-table {{ width:100%; border-collapse:collapse; color:{IVORY}; }}
      .tier-table th, .tier-table td {{ border-top:1px solid rgba(208,168,92,.25); padding:8px 10px; vertical-align:top; }}
      .tier-table tr:first-child th, .tier-table tr:first-child td {{ border-top:none; }}
      .tt-badge {{ color:#E06565; font-weight:700; }}
      #notoriety_tiers:not(.open) {{ display:none; }}
    </style>
    <div id="notoriety_card" class="score-wrap" title="Click to view tiers">
      <img src="data:image/png;base64,{NOTORIETY_IMG_B64}" alt="Notoriety">
      <div class="meta"><div class="label">Notoriety</div><div class="val">{value}</div></div>
    </div>
    <div id="notoriety_tiers" class="tiers">
      <h4>City Heat — escalating responses without unmasking you</h4>
      <table class="tier-table">
        <tr><th>Band</th><th>Score</th><th>Response</th></tr>
        <tr><td class="tt-badge">N0 — Cold</td><td>0–4</td><td>Nothing special.</td></tr>
        <tr><td class="tt-badge">N1 — Warm</td><td>5–9</td><td>Ward sweeps; ignore → +1 heat.</td></tr>
        <tr><td class="tt-badge">N2 — Hot</td><td>10–14</td><td>Pattern watch; repeat MOs +2 DC.</td></tr>
        <tr><td class="tt-badge">N3 — Scalding</td><td>15–19</td><td>Counter-ops; residue detectors.</td></tr>
        <tr><td class="tt-badge">N4 — Burning</td><td>20–24</td><td>Scry-sweeps; Trace test; fail +2 heat.</td></tr>
        <tr><td class="tt-badge">N5 — Inferno</td><td>25–30</td><td>Citywide dragnet; curfews; +2 DC.</td></tr>
      </table>
    </div>
    <script>
      document.getElementById('notoriety_card')?.addEventListener('click',()=>{
        const el = document.getElementById('notoriety_tiers');
        if (el) el.classList.toggle('open');
      });
    </script>
    """
    st.components.v1.html(html, height=260 + 220)

# ------------------------------------------------------------
# KPI row
# ------------------------------------------------------------
c1, c2, c3 = st.columns(3)
with c1: render_renown_block(st.session_state.renown)
with c2: render_notoriety_block(st.session_state.notoriety)
with c3: ward_focus = st.selectbox("Active Ward", ["Dock","Field","South","North","Castle","Trades","Sea"])

# ------------------------------------------------------------
# Tabs
# ------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Mission Generator","🎯 Resolve & Log","☸️ Wheel of Misfortune","📜 Ledger"])

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
    base_score = clamp(BI + EB + clamp(sum(OQM), -2, 2), 1, 7)

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

    EI = (vis+noise+sig+wit+mag) - (conc+mis)
    ren_gain = int(round(base_score * {"Help the Poor":1.0,"Sabotage Evil":1.5,"Expose Corruption":2.0}[arc]))
    cat_base = {"Help the Poor":1,"Sabotage Evil":2,"Expose Corruption":3}[arc]
    heat = max(0, math.ceil((cat_base + max(0, EI-1) + (1 if nat1 else 0)) * (1.5 if st.session_state.notoriety>=20 else 1.25 if st.session_state.notoriety>=10 else 1.0)))
    if nat20: heat = max(0, heat-1)

    st.markdown(f"**Base Impact:** {BI} • **EB:** {EB} • **OQM:** {sum(OQM)} → **Base Score:** {base_score}")
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
            st.session_state.ledger.loc[len(st.session_state.ledger)] = row
            ok, err = append_to_google_sheet([row])
            if ok:
                st.success("Applied, logged, and synced to Sheets.")
                df_remote, _ = load_ledger_from_sheets()
                if not df_remote.empty:
                    st.session_state.ledger = df_remote
            else:
                st.warning(f"Local only; Sheets sync failed: {err or 'check secrets/permissions'}")
            st.session_state._queued_mission = None
    else:
        st.info("No queued mission.")

# ---------- Tab 3 ----------
with tab3:
    st.markdown("### Wheel of Misfortune")
    WHEEL_SIZE = 600
    SPIN_ROTATIONS = random.randint(4, 7)

    heat_state = "High" if st.session_state.notoriety >= 10 else "Low"
    st.caption(f"Heat: **{heat_state}**")
    options = load_complications(heat_state)
    labels = tuple(str(i + 1) for i in range(len(options)))
    wheel_b64 = build_wheel_b64(labels, WHEEL_SIZE, GOLD, IVORY)

    # Real Streamlit button — robust and fast
    spin = st.button("SPIN!", type="primary")
    if spin:
        n = len(options) or 1
        idx = random.randrange(n)
        st.session_state.selected_index = idx
        seg = 360 / n
        st.session_state.last_angle = SPIN_ROTATIONS * 360 + (idx + .5) * seg
        # Optional: append a log row for the spin
        try:
            row = [dt.datetime.now().isoformat(timespec="seconds"),
                   ward_focus, "Complication", "-", "-", "-", 0, 0, "-", "-", options[idx]]
            st.session_state.ledger.loc[len(st.session_state.ledger)] = row
        except Exception:
            pass

    angle = st.session_state.last_angle
    html = f"""
    <style>
      #wheel_wrap {{
        position: relative; width: {WHEEL_SIZE}px; margin: 0 auto 6px;
      }}
      #wheel_img {{
        width: 100%; height: {WHEEL_SIZE}px; border-radius: 50%;
        box-shadow: 0 10px 40px rgba(0,0,0,.55);
        background: radial-gradient(closest-side, rgba(255,255,255,0.06), transparent);
        transform: rotate({angle}deg);
        transition: transform 1.05s cubic-bezier(.22,.8,.25,1);
      }}
      #pointer {{
        position: relative; width: 0; height: 0; margin: 0 auto 10px;
        border-left: 16px solid transparent; border-right: 16px solid transparent;
        border-bottom: 26px solid {GOLD}; filter: drop-shadow(0 2px 2px rgba(0,0,0,.4));
      }}
    </style>
    <div id="pointer"></div>
    <div id="wheel_wrap">
      <img id="wheel_img" src="data:image/png;base64,{wheel_b64}" />
    </div>
    """
    st.components.v1.html(html, height=WHEEL_SIZE + 56)

    if st.session_state.get("selected_index") is not None and options:
        idx = st.session_state["selected_index"]
        st.markdown(f"""
        <style>
          .result-card {{
            max-width: 900px; margin: 12px auto 0; padding: 18px 20px;
            border-radius: 14px; background: rgba(16,24,32,0.55);
            border: 1px solid rgba(208,168,92,0.45);
            box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.06);
            backdrop-filter: blur(6px) saturate(1.05);
            -webkit-backdrop-filter: blur(6px) saturate(1.05);
            animation: fadein .35s ease-out;
          }}
          .result-number {{ font-size: 13px; letter-spacing: .4px; color: {GOLD}; text-transform: uppercase; opacity: .9; margin-bottom: 6px; }}
          .result-text {{ color: {IVORY}; line-height: 1.5; font-size: 16px; }}
          @keyframes fadein {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
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
            st.success("Ledger reloaded.")
    st.dataframe(st.session_state.ledger, use_container_width=True, height=420)
    csv = st.session_state.ledger.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "night_owls_ledger.csv", "text/csv")
