# app_final.py
import streamlit as st
import json, base64, random, math
from PIL import Image

st.set_page_config(page_title="Night Owls — Waterdeep Secret Club", page_icon="🦉", layout="wide")

# ---------------- Assets & helpers ----------------
def load_b64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""

def load_b64_first(*paths):
    for p in paths:
        b64 = load_b64(p)
        if b64:
            return b64
    return ""

GOLD  = "#d0a85c"
IVORY = "#eae7e1"

BG_B64   = load_b64_first("assets/bg.png")
LOGO_IMG = None
try:
    LOGO_IMG = Image.open("assets/logo.png")
except Exception:
    LOGO_IMG = None

RENOWN_IMG_B64    = load_b64_first("assets/renown_gold.png")
NOTORIETY_IMG_B64 = load_b64_first("assets/notoriety_red.png")

# ---------------- Global styles (token replacement to avoid f-string brace hell) ----------------
STYLE_CSS = """
<style>
.stApp {
  background: url("data:image/png;base64,__BG__") no-repeat center center fixed;
  background-size: cover;
}
.stApp::before {
  content: "";
  position: fixed; inset: 0; pointer-events: none;
  background: linear-gradient(to bottom, rgba(0,0,0,0.35), rgba(0,0,0,0.60));
  z-index: 0;
}
.main .block-container {
  background: rgba(12,17,40,0.62);
  border: 1px solid rgba(208,168,92,0.22);
  border-radius: 20px;
  box-shadow: 0 14px 36px rgba(0,0,0,0.45);
  padding: 1.0rem 1.2rem !important;
  z-index: 1;
}
h1, h2, h3, h4 { color: __IVORY__; text-shadow: 0 1px 0 rgba(0,0,0,0.35); }
.stButton > button {
  border: 1px solid rgba(208,168,92,.55);
  color: __IVORY__ !important;
  background: linear-gradient(180deg, rgba(255,255,255,.06), rgba(255,255,255,.02));
  border-radius: 12px; padding: .45rem .9rem;
  box-shadow: 0 6px 16px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.06);
  transition: border-color .15s ease, transform .05s ease;
}
.stButton > button:hover { border-color: __GOLD__; transform: translateY(-1px); }
header, footer, #MainMenu { visibility: hidden; }
div[data-testid="stHeader"] { display: none; }

.score-badge {
  position: relative; display: inline-flex; align-items: center; gap: 14px;
  padding: 6px 0; background: transparent; border: none; user-select: none; cursor:pointer;
}
.score-badge img { width: 160px; height: 160px; object-fit: contain; filter: drop-shadow(0 6px 12px rgba(0,0,0,.35)); }
.score-badge .label { font-size: 14px; color: __IVORY__; opacity: .85; letter-spacing: .4px; }
.score-badge .val { font-size: 46px; color: __IVORY__; font-weight: 800; line-height: 1.05; text-shadow: 0 1px 0 rgba(0,0,0,.35); }
.tiers-box {
  display: none; margin-top: 8px; padding: 12px 14px; border-radius: 14px;
  background: rgba(16,24,32,.55); border: 1px solid rgba(208,168,92,.45);
  box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
  color: __IVORY__;
}
.tier-table { width: 100%; border-collapse: collapse; }
.tier-table th, .tier-table td { border-top: 1px solid rgba(208,168,92,.25); padding: 6px 8px; vertical-align: top; }
.tier-table tr:first-child th, .tier-table tr:first-child td { border-top: none; }
.tt-badge { color: __GOLD__; font-weight: 700; }

#wheel_wrap { position: relative; width: 600px; margin: 0 auto; }
#pointer {
  position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
  width: 0; height: 0; border-left: 16px solid transparent; border-right: 16px solid transparent;
  border-bottom: 26px solid __GOLD__; filter: drop-shadow(0 2px 2px rgba(0,0,0,.4));
}
.result-card {
  max-width: 900px; margin: 14px auto 0; padding: 16px 18px; border-radius: 14px;
  background: rgba(16,24,32,0.55); border: 1px solid rgba(208,168,92,0.45);
  box-shadow: 0 10px 30px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.06);
}
.result-number { font-size: 12px; letter-spacing: .4px; color: __GOLD__; text-transform: uppercase; opacity: .9; margin-bottom: 6px; }
.result-text { color: __IVORY__; line-height: 1.5; font-size: 16px; }
</style>
"""
st.markdown(
    STYLE_CSS.replace("__BG__", BG_B64).replace("__IVORY__", IVORY).replace("__GOLD__", GOLD),
    unsafe_allow_html=True,
)

# ---------------- State ----------------
st.session_state.setdefault("renown", 0)
st.session_state.setdefault("notoriety", 0)
st.session_state.setdefault("spin_last_idx", None)
st.session_state.setdefault("spin_last_heat", "Low")

# ---------------- Sidebar ----------------
with st.sidebar:
    if LOGO_IMG is not None:
        st.image(LOGO_IMG, use_column_width=True)
    st.markdown(
        f"""
    <div style="border:1px solid rgba(208,168,92,0.35); border-radius:14px; padding:10px 12px; background: rgba(14,18,38,0.70);">
      <h3 style="margin:0 0 4px 0; font-family:'Cinzel Decorative',serif; color:{IVORY};">Night Owls</h3>
      <p style="margin:0; font-family:'IM Fell English SC',serif; color:{IVORY}; opacity:.92;">By moonlight take flight — by your deed will the city be freed.</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

# ---------------- Crest components (client-side toggle; no rerun) ----------------
def render_crest_with_tiers(title: str, value: int, img_b64: str, dom_id: str, tiers_html: str):
    tpl = """
    <div class="score-badge" id="__DOMID__" title="Click to view tiers">
      <img src="data:image/png;base64,__IMG__" alt="__TITLE__">
      <div class="meta">
        <div class="label">__TITLE__</div>
        <div class="val">__VALUE__</div>
      </div>
    </div>
    <div class="tiers-box" id="__DOMID____tiers">__TIERS__</div>
    <script>
      (function(){
        const crest = document.getElementById("__DOMID__");
        const box   = document.getElementById("__DOMID____tiers");
        if (crest && box) {
          crest.addEventListener("click", ()=>{ box.style.display = (box.style.display==="block") ? "none" : "block"; });
        }
      })();
    </script>
    """
    html = (
        tpl.replace("__DOMID__", dom_id)
        .replace("__IMG__", img_b64 or "")
        .replace("__TITLE__", title)
        .replace("__VALUE__", str(value))
        .replace("__TIERS__", tiers_html)
    )
    st.components.v1.html(html, height=220)

RENOWN_TIERS_HTML = """
  <table class="tier-table">
    <tr><th>Tier</th><th>Threshold</th><th>Perks</th></tr>
    <tr><td class="tt-badge">R1</td><td>5</td><td>Street Signals — glean rumours; ward hand-signs.</td></tr>
    <tr><td class="tt-badge">R2</td><td>10</td><td>Quiet Hands — once/session safe hand-off nearby.</td></tr>
    <tr><td class="tt-badge">R3</td><td>15</td><td>Crowd Cover — one round full cover to slip away.</td></tr>
    <tr><td class="tt-badge">R4</td><td>20</td><td>Whisper Network — 1 social check at advantage vs townsfolk; +1d6 urban help/session.</td></tr>
    <tr><td class="tt-badge">R5</td><td>25</td><td>Safehouses — two boltholes; negate one pursuit/adventure.</td></tr>
    <tr><td class="tt-badge">R6</td><td>30</td><td>Folk Halo — quiet −10% mundane gear; crowd “coincidences”.</td></tr>
  </table>
"""

NOTORIETY_TIERS_HTML = """
  <table class="tier-table">
    <tr><th>Band</th><th>Score</th><th>City Response</th></tr>
    <tr><td class="tt-badge">N0 — Cold</td><td>0–4</td><td>No special action.</td></tr>
    <tr><td class="tt-badge">N1 — Warm</td><td>5–9</td><td>Ward sweeps; patrols drift close after hot jobs.</td></tr>
    <tr><td class="tt-badge">N2 — Hot</td><td>10–14</td><td>Pattern watch; repeat MO +2 DC; kit checks.</td></tr>
    <tr><td class="tt-badge">N3 — Scalding</td><td>15–19</td><td>Counter-ops; residue detectors; disguise disadvantage if reused.</td></tr>
    <tr><td class="tt-badge">N4 — Burning</td><td>20–24</td><td>Scry-sweeps; casting risks Trace test; tails.</td></tr>
    <tr><td class="tt-badge">N5 — Inferno</td><td>25–30</td><td>Dragnets; curfews; +2 stealth/social DCs; bounties.</td></tr>
  </table>
"""

c1, c2 = st.columns(2)
with c1:
    render_crest_with_tiers("Renown", st.session_state.renown, RENOWN_IMG_B64, "crest_renown", RENOWN_TIERS_HTML)
with c2:
    render_crest_with_tiers("Notoriety", st.session_state.notoriety, NOTORIETY_IMG_B64, "crest_notoriety", NOTORIETY_TIERS_HTML)

# ---------------- Minimal counters (no ledger, local only) ----------------
with st.expander("Quick counters (session-only)"):
    col1, col2, col3 = st.columns(3)
    with col1:
        add_r = st.number_input("Add Renown", 0, 50, 0)
    with col2:
        add_n = st.number_input("Add Notoriety", 0, 50, 0)
    with col3:
        if st.button("Apply"):
            st.session_state.renown += int(add_r)
            st.session_state.notoriety = max(0, st.session_state.notoriety + int(add_n))
            try:
                st.rerun()
            except Exception:
                st.experimental_rerun()

# ---------------- Wheel of Fortune (client-first spin) ----------------
st.markdown("### Wheel of Fortune")

heat_state = "High" if st.session_state.notoriety >= 10 else "Low"
st.session_state.spin_last_heat = heat_state

# Load options (fallback to numbered results if file missing)
table_path = "assets/complications_high.json" if heat_state == "High" else "assets/complications_low.json"
try:
    with open(table_path, "r") as f:
        options = json.load(f)
except Exception:
    options = [f"Result {i+1}" for i in range(12)]

# Hidden input to receive the client result
_ = st.text_input("spin_result", value="", placeholder="spin_result_input_marker",
                  label_visibility="collapsed", key="spin_result_input_key")

# Hidden trigger that JS will click *after* animation to cause a rerun
TRIGGER_LABEL = "SPIN_RERUN_TRIGGER"
_ = st.button(TRIGGER_LABEL, key="spin_hidden_trigger")

WHEEL_SIZE = 600
colors = ["#173b5a", "#12213f", "#0d3b4f", "#112b44"]

WHEEL_HTML = """
<div id="wheel_wrap">
  <div id="pointer"></div>
  <canvas id="wheel_canvas" width="__WHEEL_SIZE__" height="__WHEEL_SIZE__"
          style="border-radius:50%; box-shadow:0 10px 40px rgba(0,0,0,.55);
                 background: radial-gradient(closest-side, rgba(255,255,255,0.06), transparent);"></canvas>
  <div id="spin_overlay" style="position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
       width:110px; height:110px; border-radius:55px; border:1px solid rgba(208,168,92,0.45);
       display:grid; place-items:center; color:__IVORY__; font-weight:700; letter-spacing:.5px;
       text-transform:uppercase; cursor:pointer; background:linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.02));">SPIN!</div>
</div>
<script>
(function(){
  const options = __OPTS_JSON__;
  const colors  = __COLORS_JSON__;
  const gold    = "__GOLD__";
  const ivory   = "__IVORY__";
  const size    = __WHEEL_SIZE__;
  const n       = options.length;
  const seg     = 2*Math.PI/n;
  const canvas  = document.getElementById('wheel_canvas');
  const ctx     = canvas.getContext('2d');

  function drawWheel(angle){
    const r = size/2 - 6, cx = size/2, cy = size/2;
    ctx.clearRect(0,0,size,size);
    for (let i=0;i<n;i++) {
      ctx.beginPath();
      ctx.moveTo(cx,cy);
      ctx.arc(cx,cy,r, -Math.PI/2 + i*seg + angle, -Math.PI/2 + (i+1)*seg + angle, false);
      ctx.closePath();
      ctx.fillStyle = colors[i % colors.length];
      ctx.fill();
      ctx.strokeStyle = "#213a53"; ctx.lineWidth = 1; ctx.stroke();
    }
    ctx.beginPath(); ctx.arc(cx,cy,r,0,2*Math.PI); ctx.strokeStyle = gold; ctx.lineWidth = 6; ctx.stroke();
    ctx.fillStyle = ivory;
    ctx.font = "14px sans-serif";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (let i=0;i<n;i++) {
      const ang = -Math.PI/2 + (i+0.5)*seg + angle;
      const tx = cx + (r-60)*Math.cos(ang), ty = cy + (r-60)*Math.sin(ang);
      ctx.fillText(String(i+1), tx, ty);
    }
  }

  let currentAngle = 0;
  drawWheel(0);

  function spinNow(){
    const idx = Math.floor(Math.random()*n);
    const rotations = 5 + Math.floor(Math.random()*3); // 5–7 turns
    const targetAngle = rotations*2*Math.PI + (idx+0.5)*seg; // pointer at top
    const duration = 3200; // ms
    const start = performance.now();
    function easeOutCubic(t){ return 1 - Math.pow(1 - t, 3); }
    function animate(ts){
      const p = Math.min(1, (ts - start)/duration);
      const eased = easeOutCubic(p);
      const ang = currentAngle + eased*(targetAngle - currentAngle);
      drawWheel(ang);
      if (p < 1) requestAnimationFrame(animate);
      else { currentAngle = ang; finish(idx); }
    }
    requestAnimationFrame(animate);
  }

  function finish(idx){
    try {
      const scope = window.parent.document;
      const input = scope.querySelector("input[placeholder='spin_result_input_marker']");
      if (input) {
        input.value = String(idx);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
      const btns = scope.querySelectorAll('button');
      for (const b of btns) {
        if ((b.innerText||'').trim()==='__TRIGGER__') {
          b.style.display = 'none';
          setTimeout(()=>b.click(), 50);
          break;
        }
      }
    } catch(e){}
  }

  try {
    const scope = window.parent.document;
    const btns  = scope.querySelectorAll('button');
    for (const b of btns) { if ((b.innerText||'').trim()==='__TRIGGER__') b.style.display='none'; }
  } catch(e){}

  document.getElementById('spin_overlay').addEventListener('click', spinNow);
})();
</script>
"""
wheel_html = (
    WHEEL_HTML
    .replace("__WHEEL_SIZE__", str(WHEEL_SIZE))
    .replace("__IVORY__", IVORY)
    .replace("__GOLD__", GOLD)
    .replace("__TRIGGER__", TRIGGER_LABEL)
    .replace("__OPTS_JSON__", json.dumps(options))
    .replace("__COLORS_JSON__", json.dumps(colors))
)
st.components.v1.html(wheel_html, height=WHEEL_SIZE + 40)

# After rerun, read result and display
if st.session_state.get("spin_result_input_key"):
    try:
        idx_val = int(st.session_state["spin_result_input_key"])
        st.session_state.spin_last_idx = idx_val
    except Exception:
        st.session_state.spin_last_idx = None
    st.session_state["spin_result_input_key"] = ""

if st.session_state.get("spin_last_idx") is not None:
    i = st.session_state["spin_last_idx"]
    txt = options[i] if 0 <= i < len(options) else "—"
    st.markdown(
        f"""
    <div class="result-card">
      <div class="result-number">Result {i+1:02d} / {len(options):02d} • Heat: {heat_state}</div>
      <div class="result-text">{txt}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )
