import streamlit as st
import pandas as pd
import math, random, io, json, base64, datetime as dt
from typing import Tuple, List
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(page_title="Night Owls — Waterdeep Secret Club", page_icon="🦉", layout="wide")

# ---------- Caching helpers ----------
@st.cache_data(show_spinner=False)
def b64_of(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

@st.cache_data(show_spinner=False)
def read_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()

@st.cache_data(show_spinner=False)
def first_existing_b64(paths: Tuple[str, ...]) -> str:
    for p in paths:
        try:
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            continue
    return ""

@st.cache_data(show_spinner=False, max_entries=8)
def load_complications(heat_state: str) -> List[str]:
    table_path = "assets/complications_high.json" if heat_state == "High" else "assets/complications_low.json"
    with open(table_path, "r") as fh:
        return json.load(fh)

@st.cache_data(show_spinner=False, max_entries=8)
def build_wheel_b64(labels: Tuple[str, ...], size: int, colours: Tuple[str, ...]) -> str:
    n = len(labels) or 1
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r = size // 2 - 6
    for i in range(n):
        start = 360 * i / n - 90
        end   = 360 * (i + 1) / n - 90
        d.pieslice([cx - r, cy - r, cx + r, cy + r], start, end,
                   fill=colours[i % len(colours)], outline="#213a53")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 14)
    except Exception:
        font = ImageFont.load_default()
    for i, lab in enumerate(labels):
        ang = math.radians(360 * (i + .5) / n - 90)
        tx = cx + int((r - 60) * math.cos(ang))
        ty = cy + int((r - 60) * math.sin(ang))
        d.text((tx, ty), lab, fill="#eae7e1", font=font, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

# ---------- Assets ----------
BG_B64 = b64_of("assets/bg.png")
LOGO = Image.open(io.BytesIO(read_bytes("assets/logo.png")))

RENOWN_IMG_B64 = first_existing_b64(("assets/renown_gold.png","assets/renown.png"))
NOTORIETY_IMG_B64 = first_existing_b64(("assets/notoriety_red.png","assets/notoriety.png"))
MURAL_B64 = first_existing_b64(("assets/mural_sidebar.png","assets/mural.png"))

GOLD  = "#d0a85c"
IVORY = "#eae7e1"

# ---------- App State ----------
if "renown" not in st.session_state: st.session_state.renown = 0
if "notoriety" not in st.session_state: st.session_state.notoriety = 0
if "ledger" not in st.session_state:
    st.session_state.ledger = pd.DataFrame(columns=[
        "timestamp","ward","archetype","BI","EB","OQM","renown_gain","notoriety_gain","EI_breakdown","notes","complication"
    ])
if "last_angle" not in st.session_state: st.session_state.last_angle = 0
if "selected_index" not in st.session_state: st.session_state.selected_index = None

# ---------- Styles ----------
st.markdown(f"""
<style>
.stApp {{
  background: url("data:image/png;base64,{BG_B64}") no-repeat center center fixed;
  background-size: cover;
}}
.stApp::before {{
  content:""; position:fixed; inset:0; pointer-events:none;
  background: linear-gradient(to bottom, rgba(0,0,0,.35), rgba(0,0,0,.6));
}}
.main .block-container {{
  background: rgba(12,17,40,.62);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(208,168,92,.25);
  border-radius: 22px; padding: 1rem 1.2rem !important;
}}
h1,h2,h3,h4 {{ color: {IVORY}; }}
header, footer, #MainMenu {{ visibility: hidden; }}
</style>
""", unsafe_allow_html=True)

# ---------- Sidebar ----------
with st.sidebar:
    st.image(LOGO, use_column_width=True)
    st.markdown(f"""
    <style>
    #sbm{{position:relative;height:1080px;margin-top:8px}}
    #sbm::before{{content:"";position:absolute;inset:0;
      background:url("data:image/png;base64,{MURAL_B64}") no-repeat center top/contain;
      opacity:.85; filter: drop-shadow(0 6px 12px rgba(0,0,0,.25)); }}
    </style>
    <div id="sbm" aria-hidden="true"></div>
    """, unsafe_allow_html=True)

# ---------- Score blocks (pure CSS toggle – no JS) ----------
def score_block(kind: str, value: int, img_b64: str, uid: str):
    title = "Renown" if kind=="renown" else "Notoriety"
    accent = GOLD if kind=="renown" else "#E06565"
    html = f"""
    <style>
    .score-{uid} {{ display:flex; align-items:center; gap:14px; }}
    .score-{uid} img {{ width: 172px; height: 172px; object-fit: contain;
        filter: drop-shadow(0 6px 12px rgba(0,0,0,.35)); }}
    .score-{uid} .v {{ font-size: 54px; color: {IVORY}; font-weight: 800; line-height: 1.05; }}
    .t-{uid} {{ margin-top:10px; padding:14px 16px; border-radius:16px;
        background: rgba(16,24,32,.55); border:1px solid rgba(208,168,92,.45); color:{IVORY}; }}
    .t-{uid} table {{ width:100%; border-collapse:collapse; }}
    .t-{uid} th,.t-{uid} td {{ border-top:1px solid rgba(208,168,92,.25); padding:8px 10px; }}
    .tt-{uid} {{ color:{accent}; font-weight:700; }}
    /* checkbox hack */
    #chk-{uid}{{display:none}}
    #chk-{uid} ~ .t-{uid}{{display:none}}
    #chk-{uid}:checked ~ .t-{uid}{{display:block}}
    .click-{uid}{{cursor:pointer; user-select:none;}}
    </style>
    <input id="chk-{uid}" type="checkbox" />
    <label class="click-{uid}" for="chk-{uid}">
      <div class="score-{uid}">
        <img src="data:image/png;base64,{img_b64}" alt="{title}"/>
        <div>
          <div style="opacity:.85;color:{IVORY};letter-spacing:.4px">{title}</div>
          <div class="v">{value}</div>
          <div style="font-size:12px;color:{accent};opacity:.9">Click crest to toggle tiers</div>
        </div>
      </div>
    </label>
    <div class="t-{uid}">
      {"".join([
        '<table><tr><th>Tier</th><th>Threshold</th><th>Perks</th></tr>',
        '<tr><td class="tt-'+uid+'">R1</td><td>5</td><td>Street Signals.</td></tr>',
        '<tr><td class="tt-'+uid+'">R2</td><td>10</td><td>Quiet Hands.</td></tr>',
        '<tr><td class="tt-'+uid+'">R3</td><td>15</td><td>Crowd Cover.</td></tr>',
        '<tr><td class="tt-'+uid+'">R4</td><td>20</td><td>Whisper Network.</td></tr>',
        '<tr><td class="tt-'+uid+'">R5</td><td>25</td><td>Safehouses.</td></tr>',
        '<tr><td class="tt-'+uid+'">R6</td><td>30</td><td>Folk Halo.</td></tr>'
      ]) if kind=="renown" else "".join([
        '<table><tr><th>Band</th><th>Score</th><th>Response</th></tr>',
        '<tr><td class="tt-'+uid+'">N0 — Cold</td><td>0–4</td><td>None.</td></tr>',
        '<tr><td class="tt-'+uid+'">N1 — Warm</td><td>5–9</td><td>Ward sweeps.</td></tr>',
        '<tr><td class="tt-'+uid+'">N2 — Hot</td><td>10–14</td><td>Pattern watch.</td></tr>',
        '<tr><td class="tt-'+uid+'">N3 — Scalding</td><td>15–19</td><td>Counter‑ops.</td></tr>',
        '<tr><td class="tt-'+uid+'">N4 — Burning</td><td>20–24</td><td>Scry‑sweeps.</td></tr>',
        '<tr><td class="tt-'+uid+'">N5 — Inferno</td><td>25–30</td><td>Dragnet.</td></tr>'
      ])}
      </table>
    </div>
    """
    st.components.v1.html(html, height=230+220, scrolling=False)

# ---------- KPI Row ----------
c1,c2,c3 = st.columns(3)
with c1: score_block("renown", st.session_state.renown, RENOWN_IMG_B64, "ren")
with c2: score_block("notoriety", st.session_state.notoriety, NOTORIETY_IMG_B64, "not")
with c3: ward_focus = st.selectbox("Active Ward", ["Dock","Field","South","North","Castle","Trades","Sea"])

# ---------- Tabs ----------
tab1, tab2, tab3, tab4 = st.tabs(["🗺️ Mission Generator","🎯 Resolve & Log","☸️ Wheel of Misfortune","📜 Ledger"])

# ---------- Mechanics helpers ----------
def clamp(v, lo, hi): return max(lo, min(hi, v))

# ---------- Tab 1: (minimal to keep this patch focused) ----------
with tab1:
    st.caption("Mission generator intact — focusing this patch on performance, tier toggles, and the wheel UI.")

# ---------- Tab 2 ----------
with tab2:
    st.markdown("### Resolve & Log")
    q = st.session_state.get("_queued_mission")
    if q:
        st.json(q)
        notes = st.text_input("Notes")
        if st.button("Apply Gains & Log", type="primary"):
            st.session_state.renown += q["renown_gain"]
            st.session_state.notoriety += q["notoriety_gain"]
            row = [dt.datetime.now().isoformat(timespec="seconds"), q["ward"], q["archetype"], q["BI"], q["EB"], q["OQM"], q["renown_gain"], q["notoriety_gain"], json.dumps(q["EI_breakdown"]), notes, ""]
            st.session_state.ledger.loc[len(st.session_state.ledger)] = row
            st.session_state._queued_mission = None
            st.success("Applied locally.")
    else:
        st.info("No queued mission.")

# ---------- Tab 3: Wheel with centred button (no side button) ----------
with tab3:
    st.markdown("### Wheel of Misfortune")
    WHEEL_SIZE = 560
    colours = ("#173b5a","#12213f","#0d3b4f","#112b44")
    heat_state = "High" if st.session_state.notoriety >= 10 else "Low"
    st.caption(f"Heat: **{heat_state}**")
    options = load_complications(heat_state)
    labels = tuple(str(i+1) for i in range(len(options)))
    wheel_b64 = build_wheel_b64(labels, WHEEL_SIZE, colours)

    # Query‑param trigger (centre button click reloads with ?spin=1)
    try:
        qp = st.query_params
        spin_flag = qp.get("spin", None)
    except Exception:
        qp = st.experimental_get_query_params()
        spin_flag = qp.get("spin", [None])[0] if isinstance(qp.get("spin"), list) else qp.get("spin")

    if spin_flag == "1":
        n = len(options) or 1
        idx = random.randrange(n)
        st.session_state.selected_index = idx
        seg = 360 / n
        st.session_state.last_angle = 4*360 + (idx + .5) * seg  # 4 rotations + landing centre
        # clear flag so refreshes don't retrigger
        try:
            st.query_params.clear()
        except Exception:
            st.experimental_set_query_params()

    angle = st.session_state.last_angle

    html = f"""
    <style>
      #wheel-anchor {{ position: relative; top: -8px; }}
      #wheel_wrap {{
        position: relative; width: {WHEEL_SIZE}px; height:{WHEEL_SIZE}px; margin: 0 auto 6px;
        border-radius: 50%;
        box-shadow: 0 10px 40px rgba(0,0,0,.55);
        background: radial-gradient(closest-side, rgba(255,255,255,0.06), transparent);
      }}
      #wheel_img {{
        width: 100%; height: 100%; border-radius: 50%;
        transform: rotate({angle}deg);
        animation: spin 1.05s cubic-bezier(.22,.8,.25,1);
      }}
      @keyframes spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate({angle}deg); }} }}
      #pointer {{
        width:0;height:0; margin: 0 auto 10px;
        border-left: 16px solid transparent; border-right: 16px solid transparent;
        border-bottom: 26px solid {GOLD};
        filter: drop-shadow(0 2px 2px rgba(0,0,0,.4));
      }}
      /* Centre circular button */
      .spin-btn {{
        position:absolute; left:50%; top:50%; transform:translate(-50%,-50%);
        width: 120px; height:120px; border-radius: 50%;
        border: 2px solid {GOLD};
        background: rgba(14,18,38,.72);
        display:flex; align-items:center; justify-content:center;
        font-weight:800; color:{IVORY}; text-decoration:none;
        box-shadow: inset 0 1px 0 rgba(255,255,255,.06), 0 6px 16px rgba(0,0,0,.35);
      }}
      .spin-btn:hover {{ filter: brightness(1.08); }}
    </style>
    <div id="pointer"></div>
    <div id="wheel-anchor"></div>
    <div id="wheel_wrap">
      <img id="wheel_img" src="data:image/png;base64,{wheel_b64}" alt="Wheel"/>
      <a class="spin-btn" href="?spin=1#wheel-anchor" title="Spin the wheel">SPIN</a>
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
    st.dataframe(st.session_state.ledger, use_container_width=True, height=420)
    csv = st.session_state.ledger.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", csv, "night_owls_ledger.csv", "text/csv")
