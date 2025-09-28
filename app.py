# app.py — Night Owls (snappy edition)
# Beautiful, functional, and fast: cached assets, one-time CSS, client-first wheel.
# Requires: Streamlit >= 1.32 (for st.fragment); assets/ (bg.webp, logo.webp, complications_low.json, complications_high.json)

import json, math, random
import streamlit as st
from typing import List

st.set_page_config(page_title="Night Owls — Waterdeep Secret Club", page_icon="🦉", layout="wide")

# ----------------------------- Theme ---------------------------------
GOLD  = "#D0A85C"
IVORY = "#EAE6D7"
INK   = "rgba(14,18,38,1.0)"          # deep navy
GLASS = "rgba(14,18,38,0.60)"         # frosted panel

def inject_css_once():
    if st.session_state.get("_css_done"):
        return
    st.session_state["_css_done"] = True
    st.markdown(f"""
    <style>
      :root {{
        --gold: {GOLD};
        --ivory: {IVORY};
        --ink: {INK};
        --glass: {GLASS};
      }}
      /* Background served as a normal URL: lets the browser cache it */
      .stApp {{
        background-image: url('assets/bg.webp');
        background-size: cover;
        background-attachment: scroll;
        background-position: center center;
      }}

      /* Global typography & chrome */
      html, body, .stApp {{
        color: var(--ivory);
      }}
      h1, h2, h3, h4 {{
        color: var(--ivory);
        text-shadow: 0 1px 0 rgba(0,0,0,.35);
      }}
      header, footer, #MainMenu {{ visibility: hidden; }}

      /* Glass cards */
      .glass {{
        background: var(--glass);
        border: 1px solid rgba(208,168,92,.35);
        border-radius: 16px;
        box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
        -webkit-backdrop-filter: blur(6px); backdrop-filter: blur(6px);
      }}

      /* Title row */
      .titlebar {{
        display: grid; grid-template-columns: 72px 1fr; gap: 16px; align-items: center;
        padding: 12px 16px; margin-bottom: 10px;
      }}
      .titlebar img {{
        width: 72px; height: 72px; object-fit: contain; image-rendering: -webkit-optimize-contrast;
        filter: drop-shadow(0 6px 12px rgba(0,0,0,.45));
      }}
      .subtitle {{ color: rgba(234,230,215,.85); font-size: 0.95rem; }}

      /* Result card under wheel (server-rendered) */
      .result-card {{
        margin-top: 14px; padding: 14px 16px; border-radius: 14px;
        border: 1px solid rgba(208,168,92,.45); background: rgba(14,18,38,.66);
        box-shadow: 0 8px 24px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.05);
      }}
      .result-number {{ letter-spacing: .02em; opacity: .9; margin-bottom: 8px; }}
      .result-text {{ line-height: 1.45; }}

      /* Hide the plumbing (hidden form & inputs) */
      .visually-hidden {{
        position: absolute !important; height: 1px; width: 1px; overflow: hidden;
        clip: rect(1px, 1px, 1px, 1px); white-space: nowrap;
      }}
    </style>
    """, unsafe_allow_html=True)

# ----------------------------- Data ----------------------------------

@st.cache_data(show_spinner=False)
def load_complications(heat: str) -> List[str]:
    """Load complications text for 'High' or 'Low' heat; cached to avoid disk on reruns."""
    path = "assets/complications_high.json" if heat == "High" else "assets/complications_low.json"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Normalise: accept either list[str] or list[dict{{"text": ...}}]
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return data
        elif isinstance(data, list) and all(isinstance(x, dict) and "text" in x for x in data):
            return [x["text"] for x in data]
        else:
            return [str(x) for x in data]
    except Exception as e:
        return [f"(Error loading {path}: {e})"]

def get_heat_state(notoriety: int) -> str:
    return "High" if notoriety >= 10 else "Low"

# ----------------------------- UI: Header ----------------------------

inject_css_once()
st.markdown("""
<div class="titlebar glass">
  <img src="assets/logo.webp" alt="Night Owls logo"/>
  <div>
    <div style="font-size:1.35rem; font-weight:700; letter-spacing:.02em;">Night Owls — Waterdeep Secret Club</div>
    <div class="subtitle">Snappier than a green dragon’s temper.</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ----------------------------- State --------------------------------

if "renown" not in st.session_state:    st.session_state.renown = 0
if "notoriety" not in st.session_state: st.session_state.notoriety = 0
if "spin_last_idx" not in st.session_state: st.session_state.spin_last_idx = None

# ----------------------------- Score Row (simple, light) ------------

col1, col2, colsp = st.columns([1,1,2], gap="large")
with col1:
    st.caption("Renown")
    st.number_input(" ", key="renown", min_value=0, max_value=999, step=1, label_visibility="collapsed")
with col2:
    st.caption("Notoriety")
    st.number_input("  ", key="notoriety", min_value=0, max_value=999, step=1, label_visibility="collapsed")

# ----------------------------- Wheel Fragment -----------------------

# Use a fragment so only this region reruns when we log a result.
@st.fragment
def wheel_block():
    st.markdown("### Wheel of Misfortune")

    heat_state = get_heat_state(st.session_state.notoriety)
    st.caption(f"Heat: **{heat_state}**")

    options = load_complications(heat_state)
    n = max(1, len(options))

    # A unique token so our hidden input can be targeted deterministically from JS
    input_key = st.session_state.get("_spin_input_key")
    if not input_key:
        input_key = st.session_state["_spin_input_key"] = f"spin_{random.randint(10**6, 10**7-1)}"

    # ---- Client-first wheel (instant) ----
    # We do not ship the long option texts to the canvas — the browser only needs N.
    # After animation ends, JS writes the chosen index into a hidden text input and clicks a hidden submit button.
    # That triggers a tiny rerun of this fragment only; then we render the pretty server-side result box.

    wheel_html = f"""
    <div id="wheel-wrapper" class="glass" style="padding:16px; text-align:center;">
      <div style="display:flex; justify-content:center; align-items:center; position:relative;">
        <canvas id="wheelCanvas" width="560" height="560" style="max-width: 92vw; height:auto; border-radius:50%; box-shadow:0 18px 40px rgba(0,0,0,.45);"></canvas>
        <button id="spinButton" aria-label="Spin" style="
            position:absolute; width:132px; height:132px; border-radius:50%;
            border:1px solid rgba(208,168,92,.6);
            background: radial-gradient(ellipse at top, rgba(255,255,255,.18), rgba(255,255,255,.03));
            color: {IVORY}; font-weight:700; letter-spacing:.03em; cursor:pointer;
            box-shadow: 0 12px 28px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.08);
        ">SPIN</button>
      </div>
      <div id="clientResult" style="margin-top:12px; opacity:.85; font-size:.95rem;"></div>
    </div>

    <script>
    (function() {{
      const N = {n};
      const canvas = document.getElementById('wheelCanvas');
      const ctx = canvas.getContext('2d');
      const size = canvas.width;
      const r = size/2;
      const TAU = Math.PI*2;

      // Palette: simple alternating segments for clarity (no heavy shadows per segment)
      const A = '#2a2f4a', B = '#3a3f5f';

      function drawWheel(angle) {{
        ctx.clearRect(0,0,size,size);
        ctx.save();
        ctx.translate(r, r);
        ctx.rotate(angle);
        for (let i=0; i<N; i++) {{
          const a0 = i * TAU/N, a1 = (i+1) * TAU/N;
          ctx.beginPath();
          ctx.moveTo(0,0); ctx.arc(0,0, r-6, a0, a1);
          ctx.closePath();
          ctx.fillStyle = (i % 2 === 0) ? A : B;
          ctx.fill();

          // Labels: just numbers to keep the canvas cheap
          const mid = (a0 + a1)/2;
          ctx.save();
          ctx.rotate(mid);
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillStyle = 'rgba(234,230,215,0.95)';
          ctx.font = '700 18px system-ui, sans-serif';
          ctx.fillText(String(i+1).padStart(2,'0'), (r-60), 0);
          ctx.restore();
        }}
        // Pointer
        ctx.restore();
        ctx.beginPath();
        ctx.moveTo(r, r-12);
        ctx.lineTo(r+26, r);
        ctx.lineTo(r, r+12);
        ctx.closePath();
        ctx.fillStyle = '{GOLD}';
        ctx.shadowColor = 'rgba(0,0,0,.4)';
        ctx.shadowBlur = 8;
        ctx.fill();
        ctx.shadowBlur = 0;
      }}

      let spinning = false;
      let current = 0;    // radians
      drawWheel(current);

      function easeOutCubic(t) {{ return 1 - Math.pow(1-t, 3); }}

      function spin() {{
        if (spinning) return;
        spinning = true;
        document.getElementById('clientResult').textContent = '...';
        // Choose a target segment; random rotations for drama
        const targetIdx = Math.floor(Math.random() * N);
        const spins = 4 + Math.floor(Math.random()*3); // 4–6 rotations
        // Compute angle so that the pointer (at 0 rad) lands in the middle of target segment.
        const segAngle = TAU / N;
        const targetAngle = TAU * spins + ((targetIdx + 0.5) * segAngle);
        const duration = 2200 + Math.random()*650; // ms

        const start = performance.now();
        const startAngle = current;

        function frame(now) {{
          let t = (now - start) / duration;
          if (t > 1) t = 1;
          const eased = easeOutCubic(t);
          const angle = startAngle + (targetAngle - startAngle) * eased;
          drawWheel(angle);
          if (t < 1) requestAnimationFrame(frame);
          else finish(targetIdx, angle);
        }}
        requestAnimationFrame(frame);
      }}

      function finish(idx, angle) {{
        current = angle % TAU;
        document.getElementById('clientResult').textContent = 'Result: #' + String(idx+1).padStart(2,'0') + ' (revealed)';
        // After the animation finishes, notify Streamlit via hidden input + submit.
        const input = document.getElementById('{input_key}');
        if (input) {{
          input.value = String(idx);
        }}
        const btn = document.getElementById('submit_{input_key}');
        if (btn) {{
          // Click the hidden submit to trigger a tiny rerun of just this fragment.
          btn.click();
        }}
        spinning = false;
      }}

      document.getElementById('spinButton').addEventListener('click', spin);
    }})();
    </script>
    """

    st.components.v1.html(wheel_html, height=680, scrolling=False)

    # Hidden form: indexed by a deterministic key so JS can target it directly
    with st.form(key=f"form_{input_key}"):
        _ = st.text_input("spin_index", key=input_key, label_visibility="collapsed")
        # The button is visible to the DOM but we hide it via CSS; give it a deterministic ID for JS.
        submitted = st.form_submit_button("SPIN_RERUN_TRIGGER", type="secondary")
        st.markdown(
            f"<script>document.currentScript.previousElementSibling.querySelector('button').id = 'submit_{input_key}';</script>",
            unsafe_allow_html=True
        )

    if submitted:
        # Minimal server work: just parse the index and store
        try:
            idx = int(st.session_state.get(input_key, "").strip())
            st.session_state.spin_last_idx = idx if 0 <= idx < n else None
        except Exception:
            st.session_state.spin_last_idx = None
        # Clear the input to avoid stale clicks
        st.session_state[input_key] = ""

    # Pretty, server-rendered result (full text)
    if st.session_state.get("spin_last_idx") is not None:
        i = st.session_state["spin_last_idx"]
        txt = options[i] if 0 <= i < n else "—"
        st.markdown(f"""
        <div class="result-card">
          <div class="result-number">Result {i+1:02d} / {n:02d} • Heat: {heat_state}</div>
          <div class="result-text">{txt}</div>
        </div>
        """, unsafe_allow_html=True)

# Render the wheel block (fragment)
wheel_block()
