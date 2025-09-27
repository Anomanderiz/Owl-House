# Night Owls — Waterdeep Secret Club (client-first spin & crest toggles)
# Streamlit ≥ 1.33 recommended (supports st.fragment / st.experimental_fragment).
# British spelling in comments; minimal redraw; no network I/O on spin path.

import streamlit as st
import pandas as pd
import numpy as np
import math, random, io, json, base64, datetime as dt, uuid, os
from PIL import Image

# ──────────────────────────────────────────────────────────────────────────────
# Page & theme
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Night Owls — Waterdeep Secret Club", page_icon="🦉", layout="wide")

GOLD  = "#d0a85c"
IVORY = "#eae7e1"

# Prefer Streamlit's new fragment API; fall back if needed
_fragment = getattr(st, "fragment", None) or getattr(st, "experimental_fragment", None)
def fragment(fn):
    if _fragment:
        return _fragment(fn)
    # graceful fallback: return fn itself (no partial rerun, but code still runs)
    return fn

# ──────────────────────────────────────────────────────────────────────────────
# Caches — heavy assets & data loaded once
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

@st.cache_data(show_spinner=False)
def load_first_b64(*paths) -> str:
    for p in paths:
        try:
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            continue
    return ""

@st.cache_data(show_spinner=False)
def load_json(path: str):
    with open(path, "r") as f:
        return json.load(f)

# Background & branding (cache once)
BG_B64   = load_b64("assets/bg.png") if os.path.exists("assets/bg.png") else ""
LOGO_IMG = Image.open("assets/logo.png") if os.path.exists("assets/logo.png") else None
RENOWN_B64    = load_first_b64("assets/renown_gold.png")
NOTORIETY_B64 = load_first_b64("assets/notoriety_red.png")
MURAL_B64     = load_first_b64("assets/mural_sidebar.png", "assets/mural.png")

# ──────────────────────────────────────────────────────────────────────────────
# Styles — keep glass blur on small wrapper; avoid nested blurs
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url("https://fonts.googleapis.com/css2?family=Cinzel+Decorative:wght@400;700&family=IM+Fell+English+SC&display=swap");

:root {{
  --glass-bg: rgba(12,17,40,0.62);
  --glass-alt: rgba(15,22,50,0.68);
  --ivory: {IVORY};
  --gold:  {GOLD};
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
h1, h2, h3, h4 {{ color: var(--ivory); text-shadow: 0 1px 0 rgba(0,0,0,0.35); }}

.stTabs [data-baseweb="tab-list"] {{ gap: .25rem; }}
.stTabs [data-baseweb="tab"] {{
  color: var(--ivory);
  background: rgba(18,27,60,0.55);
  border: 1px solid rgba(208,168,92,0.18);
  border-bottom: 2px solid transparent;
  border-top-left-radius: 14px; border-top-right-radius: 14px;
  padding: .5rem .9rem;
}}
.stTabs [aria-selected="true"] {{
  background: rgba(18,27,60,0.78);
  border-color: rgba(208,168,92,0.35);
  border-bottom-color: var(--gold);
}}
/* Hide Streamlit furniture */
header, footer, #MainMenu {{ visibility: hidden; }}
[data-testid="stToolbar"] {{ visibility: hidden; height: 0; position: fixed; }}
div[data-testid="stHeader"] {{ display: none; }}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# State (lightweight); keep ledger in-memory only; do not render dataframes
# ──────────────────────────────────────────────────────────────────────────────
ss = st.session_state
ss.setdefault("renown", 0)
ss.setdefault("notoriety", 0)
ss.setdefault("last_angle", 0.0)         # last rendered wheel angle
ss.setdefault("selected_index", None)    # last complication index
ss.setdefault("spin_nonce", "")          # guards against duplicate query-param signals
ss.setdefault("ledger", pd.DataFrame(columns=[
    "timestamp","ward","archetype","BI","EB","OQM",
    "renown_gain","notoriety_gain","EI_breakdown","notes","complication"
]))  # local-only; batch-sync from Resolve tab if you like

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    if LOGO_IMG is not None:
        st.image(LOGO_IMG, use_column_width=True)
    st.markdown("""
    <div style="
      border:1px solid rgba(208,168,92,.35);
      border-radius:18px;padding:1rem 1.1rem;
      background:rgba(14,18,38,.70);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,.04), 0 10px 30px rgba(0,0,0,.35);">
      <h3 style="font-family:'Cinzel Decorative',serif;color:var(--ivory);margin:0 0 .35rem 0;">Night Owls</h3>
      <p style="font-family:'IM Fell English SC',serif;font-size:1.05rem;line-height:1.3;color:var(--ivory);opacity:.92;">
      By moonlight take flight — by your deed will the city be freed.</p>
    </div>
    """, unsafe_allow_html=True)
    # mural below the text box (pure overlay; pointer-events none)
    st.markdown(f"""
    <div style="position:relative;height:1080px;margin-top:8px;">
      <div style="
        position:absolute;inset:0;opacity:.82;pointer-events:none;
        background:url('data:image/png;base64,{MURAL_B64}') no-repeat center top / contain;
        filter: drop-shadow(0 6px 12px rgba(0,0,0,.25));">
      </div>
    </div>
    """, unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Crest badges — client-first toggles; no Python round-trip
# ──────────────────────────────────────────────────────────────────────────────
def crest_badge(title: str, value: int, img_b64: str, panel_html: str, dom_id: str):
    html = f"""
    <style>
      #{dom_id} .badge {{
        display:inline-flex; align-items:center; gap:14px; padding:6px 0;
        cursor:pointer; user-select:none; background:transparent; border:none;
      }}
      #{dom_id} img {{
        width: 220px; height: 220px; object-fit: contain;
        filter: drop-shadow(0 6px 12px rgba(0,0,0,.35));
      }}
      #{dom_id} .meta .label {{
        font-size: 15px; color: {IVORY}; opacity: .85; letter-spacing: .4px;
      }}
      #{dom_id} .meta .val {{
        font-size: 56px; color: {IVORY}; font-weight: 800; line-height: 1.05;
        text-shadow: 0 1px 0 rgba(0,0,0,.35);
      }}
      #{dom_id} .tiers {{
        display:none; margin-top:10px; padding:14px 16px; border-radius:16px;
        background: rgba(16,24,32,.55); border:1px solid rgba(208,168,92,.45);
        box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
      }}
      #{dom_id}.open .tiers {{ display:block; animation: fadein .25s ease-out; }}
      @keyframes fadein {{ from {{opacity:0; transform: translateY(6px);}} to {{opacity:1; transform:none;}} }}
      @media (max-width: 900px) {{
        #{dom_id} img{{ width:72px; height:72px; }}
        #{dom_id} .meta .val{{ font-size:42px; }}
      }}
    </style>
    <div id="{dom_id}">
      <div class="badge" title="Click to toggle tiers">
        <img src="data:image/png;base64,{img_b64}" alt="{title}">
        <div class="meta">
          <div class="label">{title}</div>
          <div class="val">{value}</div>
        </div>
      </div>
      <div class="tiers">{panel_html}</div>
    </div>
    <script>
      (function(){{
        const root = document.getElementById("{dom_id}");
        const badge = root?.querySelector('.badge');
        badge?.addEventListener('click', () => root.classList.toggle('open'));
      }})();
    </script>
    """
    st.components.v1.html(html, height=260)

def renown_panel_html():
    return f"""
    <h4 style="color:{IVORY};margin:.1rem 0 .5rem 0;">Veil-Fame perks — subtle favours while the mask stays on</h4>
    <table style="width:100%;border-collapse:collapse;color:{IVORY};">
      <tr><th style="text-align:left;padding:6px 8px;">Tier</th><th style="text-align:left;padding:6px 8px;">Threshold</th><th style="text-align:left;padding:6px 8px;">Perks</th></tr>
      <tr><td style="color:{GOLD};font-weight:700;">R1</td><td>5</td><td><b>Street Signals</b>: glean rumours; recognised hand-signs in Dock/Field/Trades.</td></tr>
      <tr><td style="color:{GOLD};font-weight:700;">R2</td><td>10</td><td><b>Quiet Hands</b>: once/session arrange a safe hand-off nearby.</td></tr>
      <tr><td style="color:{GOLD};font-weight:700;">R3</td><td>15</td><td><b>Crowd Cover</b>: once/long rest break line-of-sight for a round.</td></tr>
      <tr><td style="color:{GOLD};font-weight:700;">R4</td><td>20</td><td><b>Whisper Network</b>: one social check at advantage vs townsfolk; free d6 help.</td></tr>
      <tr><td style="color:{GOLD};font-weight:700;">R5</td><td>25</td><td><b>Safehouses</b>: two boltholes; negate one post-job pursuit/adventure.</td></tr>
      <tr><td style="color:{GOLD};font-weight:700;">R6</td><td>30</td><td><b>Folk Halo</b>: quiet −10% on mundane gear; the crowd “coincidentally” helps once/adventure.</td></tr>
    </table>
    """

def notoriety_panel_html():
    return f"""
    <h4 style="color:{IVORY};margin:.1rem 0 .5rem 0;">City Heat — escalating responses without unmasking you</h4>
    <table style="width:100%;border-collapse:collapse;color:{IVORY};">
      <tr><th style="text-align:left;padding:6px 8px;">Band</th><th style="text-align:left;padding:6px 8px;">Score</th><th style="text-align:left;padding:6px 8px;">Response</th></tr>
      <tr><td style="color:#E06565;font-weight:700;">N0 — Cold</td><td>0–4</td><td>Nothing special.</td></tr>
      <tr><td style="color:#E06565;font-weight:700;">N1 — Warm</td><td>5–9</td><td><b>Ward sweeps</b> after jobs in hot wards.</td></tr>
      <tr><td style="color:#E06565;font-weight:700;">N2 — Hot</td><td>10–14</td><td><b>Pattern watch</b>: repeat MOs harder; bag checks.</td></tr>
      <tr><td style="color:#E06565;font-weight:700;">N3 — Scalding</td><td>15–19</td><td><b>Counter-ops</b>: rivals interfere; residue detectors.</td></tr>
      <tr><td style="color:#E06565;font-weight:700;">N4 — Burning</td><td>20–24</td><td><b>Scry-sweeps</b>: casting risks a Trace test.</td></tr>
      <tr><td style="color:#E06565;font-weight:700;">N5 — Inferno</td><td>25–30</td><td><b>Citywide dragnet</b>: curfews; bounty posted.</td></tr>
    </table>
    """

# ──────────────────────────────────────────────────────────────────────────────
# Mechanics helpers (unchanged maths; concise)
# ──────────────────────────────────────────────────────────────────────────────
def heat_multiplier(n): return 1.5 if n >= 20 else (1.25 if n >= 10 else 1.0)
def clamp(v, lo, hi): return max(lo, min(hi, v))

def compute_BI(arc, inputs):
    if arc == "Help the Poor":
        spend=inputs.get("spend",0); hh=inputs.get("households",0)
        sb = 1 if spend<25 else 2 if spend<50 else 3 if spend<100 else 4 if spend<200 else 5
        hb = 1 if hh<10 else 2 if hh<25 else 3 if hh<50 else 4 if hh<100 else 5
        return max(sb,hb)
    if arc == "Sabotage Evil":
        return inputs.get("impact_level",1)
    return inputs.get("expose_level",1)

def compute_base_score(BI, EB, OQM_list): return clamp(BI+EB+clamp(sum(OQM_list),-2,2),1,7)

# ──────────────────────────────────────────────────────────────────────────────
# KPI row — crest badges + quick actions
# ──────────────────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns([1,1,1])
with c1:
    crest_badge("Renown",    ss.renown,    RENOWN_B64,    renown_panel_html(),    "renown_crest")
with c2:
    crest_badge("Notoriety", ss.notoriety, NOTORIETY_B64, notoriety_panel_html(), "notoriety_crest")
with c3:
    ward_focus = st.selectbox("Active Ward", ["Dock","Field","South","North","Castle","Trades","Sea"])

    # Heat management (server-side; light)
    colA, colB = st.columns(2)
    with colA:
        if st.button("Lie Low (−1/−2 Heat)"):
            drop = 2 if ss.notoriety >= 10 else 1
            ss.notoriety = max(0, ss.notoriety - drop)
            # local log only (no network)
            ss.ledger.loc[len(ss.ledger)] = [
                dt.datetime.now().isoformat(timespec="seconds"), ward_focus,
                "Adjustment: Lie Low", "-", "-", "-", 0, -drop, "-", "auto", ""
            ]
            st.success(f"Heat reduced by {drop}.")
    with colB:
        if st.button("Proxy Charity (−1 Heat)"):
            ss.notoriety = max(0, ss.notoriety - 1)
            ss.ledger.loc[len(ss.ledger)] = [
                dt.datetime.now().isoformat(timespec="seconds"), ward_focus,
                "Adjustment: Proxy Charity", "-", "-", "-", 0, -1, "-", "auto", ""
            ]
            st.success("Heat −1.")

# ──────────────────────────────────────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🗺️ Mission Generator","🎯 Resolve & Log","☸️ Wheel of Fortune"])

# ──────────────────────────────────────────────────────────────────────────────
# Tab 1 — Mission Generator (unchanged logic; practical UI)
# ──────────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("### Create a Mission")
    arc = st.radio("Archetype", ["Help the Poor","Sabotage Evil","Expose Corruption"], horizontal=True)
    col1,col2,col3 = st.columns(3)
    if arc=="Help the Poor":
        spend = col1.number_input("Gold Spent", 0, step=5, value=40)
        hh    = col2.number_input("Households Aided", 0, step=5, value=25)
        plan  = col3.checkbox("Solid Plan (+1 OQM)", True)
        inputs = {"spend":spend,"households":hh}
    elif arc=="Sabotage Evil":
        impact = col1.slider("Impact Level (1 minor→5 dismantled)",1,5,3)
        plan   = col2.checkbox("Inside Contact (+1 OQM)")
        rushed = col3.checkbox("Rushed/Loud (−1 OQM)")
        inputs = {"impact_level":impact}
    else:
        expose = col1.slider("Exposure Level (1 clerk→5 city scandal)",1,5,3)
        proof  = col2.checkbox("Hard Proof / Magical Corroboration (+1 OQM)")
        reused = col3.checkbox("Reused Signature (−1 OQM)")
        inputs = {"expose_level":expose}

    st.markdown("#### Execution")
    e1,e2,e3 = st.columns(3)
    with e1: margin = st.number_input("Success Margin",0,20,2)
    with e2: nat20  = st.checkbox("Natural 20")
    with e3: nat1   = st.checkbox("Critical botch")

    EB = 3 if nat20 else (2 if margin>=5 else (1 if margin>=1 else 0))
    OQM = []
    if plan: OQM.append(+1)
    if arc=="Sabotage Evil" and rushed: OQM.append(-1)
    if arc=="Expose Corruption" and reused: OQM.append(-1)
    if arc=="Expose Corruption" and 'proof' in locals() and proof: OQM.append(+1)

    BI         = compute_BI(arc, inputs)
    base_score = compute_base_score(BI, EB, OQM)
    st.markdown(f"**Base Impact:** {BI} • **EB:** {EB} • **OQM sum:** {sum(OQM)} → **Base Score:** {base_score}")

    st.markdown("#### Exposure Index")
    a,b = st.columns(2)
    with a:
        vis  = st.slider("Visibility (0–3)",0,3,1)
        noise= st.slider("Noise (0–3)",0,3,1)
        sig  = st.slider("Signature (0–2)",0,2,0)
        wit  = st.slider("Witnesses (0–2)",0,2,1)
    with b:
        mag  = st.slider("Magic Trace (0–2)",0,2,0)
        conc = st.slider("Concealment (0–3)",0,3,2)
        mis  = st.slider("Misdirection (0–2)",0,2,1)

    EI = (vis+noise+sig+wit+mag)-(conc+mis)
    ren_mult = {"Help the Poor":1.0,"Sabotage Evil":1.5,"Expose Corruption":2.0}[arc]
    ren_gain = int(round(base_score * ren_mult))
    cat_base = {"Help the Poor":1,"Sabotage Evil":2,"Expose Corruption":3}[arc]
    heat = max(0, math.ceil((cat_base + max(0,EI-1) + (1 if nat1 else 0)) * heat_multiplier(ss.notoriety)))
    if nat20: heat = max(0, heat-1)

    st.markdown(f"**Projected Renown:** {ren_gain} • **Projected Notoriety:** {heat} • **EI:** {EI}")

    if st.button("Queue Mission → Resolve & Log", type="primary"):
        ss._queued_mission = dict(
            ward=ward_focus, archetype=arc, BI=BI, EB=EB, OQM=sum(OQM),
            renown_gain=ren_gain, notoriety_gain=heat,
            EI_breakdown={"visibility":vis,"noise":noise,"signature":sig,"witnesses":wit,"magic":mag,"concealment":conc,"misdirection":mis}
        )
        st.success("Mission queued.")

# ──────────────────────────────────────────────────────────────────────────────
# Tab 2 — Resolve & Log (optional push to Sheets lives here, not on spin path)
# ──────────────────────────────────────────────────────────────────────────────
# Minimal, practical; keeps all network calls off the spin path.
with tab2:
    st.markdown("### Resolve Mission & Write to Log")
    q = ss.get("_queued_mission")
    if q:
        st.json(q)
        notes = st.text_input("Notes (optional)", "")
        if st.button("Apply Gains & Log", type="primary"):
            ss.renown    += q["renown_gain"]
            ss.notoriety += q["notoriety_gain"]
            row = [
                dt.datetime.now().isoformat(timespec="seconds"), q["ward"], q["archetype"],
                q["BI"], q["EB"], q["OQM"], q["renown_gain"], q["notoriety_gain"],
                json.dumps(q["EI_breakdown"]), notes, ""
            ]
            ss.ledger.loc[len(ss.ledger)] = row
            ss._queued_mission = None
            st.success("Applied and logged locally.")
    else:
        st.info("No queued mission.")

    st.caption("Tip: Batch-sync this session’s rows to Google Sheets with your own helper if desired — not included here to keep the spin path pristine.")

# ──────────────────────────────────────────────────────────────────────────────
# Tab 3 — Wheel of Fortune (client-first spin, SVG canvas, no blocking I/O)
# ──────────────────────────────────────────────────────────────────────────────
@fragment
def wheel_fragment():
    with tab3:
        st.markdown("### Wheel of Fortune")

        # Heat affects which table to load; cache IO separately
        heat_state = "High" if ss.notoriety >= 10 else "Low"
        st.caption(f"Heat: **{heat_state}**")
        table_path = "assets/complications_high.json" if heat_state=="High" else "assets/complications_low.json"
        options    = load_json(table_path)
        n          = len(options)
        WHEEL_SIZE = 600

        # Hidden sentinel button — scoped; clicked only after client animation ends
        sentinel_label = f"SPIN_SENTINEL_{uuid.uuid4().hex[:8]}"
        anchor_id      = f"wheel_anchor_{uuid.uuid4().hex[:6]}"
        st.markdown(f'<div id="{anchor_id}"></div>', unsafe_allow_html=True)
        sentinel_clicked = st.button(sentinel_label, key=sentinel_label)

        # Query param channel — client writes spin index + nonce after animation completes
        qp = getattr(st, "query_params", {})
        def _get(name, default=None):
            try:
                v = qp.get(name)
                # query_params may be dict-like of str->str
                return v if v is not None else default
            except Exception:
                return default

        spin_idx_str = _get("spin", None)
        nonce_str    = _get("spinNonce", None)

        # If the sentinel fired AND we see a new nonce, accept the client-selected index
        if sentinel_clicked and spin_idx_str is not None and nonce_str and nonce_str != ss.spin_nonce:
            try:
                idx = int(spin_idx_str)
                if 0 <= idx < n:
                    ss.selected_index = idx
                    ss.spin_nonce     = nonce_str
                    # compute final angle purely for display continuity
                    seg = 360.0 / n
                    rotations = 6  # purely cosmetic on server; real animation is client-side
                    ss.last_angle = rotations*360.0 + (idx + 0.5)*seg
                    # local log only; no network
                    comp = options[idx]
                    ss.ledger.loc[len(ss.ledger)] = [
                        dt.datetime.now().isoformat(timespec="seconds"), ward_focus,
                        "Complication", "-", "-", "-", 0, 0, "-", "-", comp
                    ]
            except Exception:
                pass

        # Build a lightweight SVG once per rerun (no PNG decode)
        def wheel_svg(n_seg: int, size: int = 600) -> str:
            r = size/2 - 6
            cx = cy = size/2
            cols = ["#173b5a", "#12213f", "#0d3b4f", "#112b44"]
            parts = [f'<svg id="wheel_svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
                     f'style="border-radius:50%;box-shadow:0 10px 40px rgba(0,0,0,.55);'
                     f'background:radial-gradient(closest-side, rgba(255,255,255,.06), transparent);">'
                     ]
            for i in range(n_seg):
                a0 = 2*math.pi*i/n_seg - math.pi/2
                a1 = 2*math.pi*(i+1)/n_seg - math.pi/2
                x0, y0 = cx + r*math.cos(a0), cy + r*math.sin(a0)
                x1, y1 = cx + r*math.cos(a1), cy + r*math.sin(a1)
                large = 1 if (a1 - a0) % (2*math.pi) > math.pi else 0
                path = (f"M {cx},{cy} L {x0:.2f},{y0:.2f} "
                        f"A {r:.2f},{r:.2f} 0 {large} 1 {x1:.2f},{y1:.2f} Z")
                parts.append(f'<path d="{path}" fill="{cols[i%len(cols)]}" stroke="#213a53" stroke-width="1"/>')
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{GOLD}" stroke-width="6"/>')
            # optional minimalist numbers
            for i in range(n_seg):
                ang = 2*math.pi*(i+0.5)/n_seg - math.pi/2
                tx  = cx + (r-58)*math.cos(ang)
                ty  = cy + (r-58)*math.sin(ang)
                parts.append(f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" '
                             f'fill="{IVORY}" font-size="14" font-family="sans-serif">{i+1}</text>')
            parts.append("</svg>")
            return "".join(parts)

        svg_markup = wheel_svg(n, WHEEL_SIZE)
        btn_diam   = max(96, int(WHEEL_SIZE * 0.18))

        # Current display angle (for immediate visual continuity across reruns)
        angle = ss.last_angle

        # Wheel UI — centre overlay button is cheap, flat (no heavy blur)
        comp_html = f"""
        <style>
          #wheel_wrap {{
            position: relative; width: {WHEEL_SIZE}px; height: {WHEEL_SIZE}px; margin: 0 auto;
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
            background: rgba(255,255,255,.06); /* flat, cheap */
            box-shadow: 0 8px 18px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.06);
            color: {IVORY}; font-weight: 700; letter-spacing: .5px; text-transform: uppercase;
            cursor: pointer; user-select: none; display: grid; place-items: center;
            transition: transform .08s ease;
          }}
          #spin_overlay:hover {{ transform: translate(-50%,-50%) scale(1.015); }}
        </style>
        <div id="wheel_wrap">
          <div id="pointer"></div>
          {svg_markup}
          <div id="spin_overlay">SPIN!</div>
        </div>

        <script>
        (function(){{
          const hiddenText = "{sentinel_label}";
          const anchorId   = "{anchor_id}";
          const n          = {n};
          const rotateMs   = 3200; // same as CSS transition time
          let spinning = false;

          const w = document.getElementById('wheel_svg');
          if (w) {{
            w.style.transition = 'transform 3.2s cubic-bezier(.17,.67,.32,1.35)';
            // apply server-known angle immediately for visual continuity
            requestAnimationFrame(() => {{ w.style.transform = 'rotate({angle}deg)'; }});
          }}

          // Hide the sentinel button within the local block only (no global scans)
          try {{
            const scope = window.parent.document;
            const anchor = scope.getElementById(anchorId);
            const block  = anchor ? anchor.closest('div[data-testid="stVerticalBlock"]') : scope;
            const btn = Array.from(block.querySelectorAll('button'))
              .find(b => (b.innerText||'').trim() === hiddenText);
            if (btn) btn.style.display = 'none';
          }} catch(e) {{ /* ignore */ }}

          function clickSentinelWith(index) {{
            try {{
              const scope  = window.parent.document;
              const anchor = scope.getElementById(anchorId);
              const block  = anchor ? anchor.closest('div[data-testid="stVerticalBlock"]') : scope;

              // write spin index & nonce to query params to make state explicit
              const url = new URL(window.parent.location.href);
              url.searchParams.set('spin', String(index));
              url.searchParams.set('spinNonce', String(Date.now()));
              window.parent.history.replaceState({{}}, '', url.toString());

              // now click the sentinel in this same block to trigger a rerun
              const btn = Array.from(block.querySelectorAll('button'))
                .find(b => (b.innerText||'').trim() === hiddenText);
              btn && btn.click();
            }} catch(e) {{}}
          }}

          document.getElementById('spin_overlay')?.addEventListener('click', () => {{
            if (spinning || !w) return;
            spinning = true;
            // client-first: choose random result immediately
            const idx = Math.floor(Math.random() * n);
            const seg = 360 / n;
            const spins = 4 + Math.floor(Math.random() * 3); // 4–6
            const angle = spins*360 + (idx + 0.5)*seg;

            // start animation immediately
            requestAnimationFrame(() => {{ w.style.transform = `rotate(${angle}deg)`; }});

            // after animation completes, notify Python via sentinel + query params
            setTimeout(() => {{
              clickSentinelWith(idx);
              spinning = false;
            }}, rotateMs + 50);
          }});
        }})();
        </script>
        """
        st.components.v1.html(comp_html, height=WHEEL_SIZE + 40)

        # Pretty result card (renders only if a result exists; no heavy effects)
        if ss.get("selected_index") is not None:
            idx = ss["selected_index"]
            st.markdown(f"""
            <div style="
              max-width:900px;margin:18px auto 0;padding:18px 20px;border-radius:14px;
              background:rgba(16,24,32,.55);border:1px solid rgba(208,168,92,.45);
              box-shadow:0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
              animation:fadein .35s ease-out;">
              <div style="font-size:13px;letter-spacing:.4px;color:{GOLD};text-transform:uppercase;opacity:.9;margin-bottom:6px;">
                Result {idx+1:02d} / {n:02d}
              </div>
              <div style="color:{IVORY};line-height:1.5;font-size:16px;">{options[idx]}</div>
            </div>
            <style>@keyframes fadein {{ from {{opacity:0; transform: translateY(6px);}} to {{opacity:1; transform:none;}} }}</style>
            """, unsafe_allow_html=True)

# Run the (partial) wheel region
wheel_fragment()
