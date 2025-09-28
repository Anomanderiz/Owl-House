# app.py — Night Owls (Shiny for Python, Posit Cloud-ready)
# Requires: shiny, pandas, numpy, pillow, gspread, google-auth, python-dotenv (optional)

from __future__ import annotations
import os, io, json, math, random, base64, datetime as dt
from typing import Optional, Tuple, List, Dict

import pandas as pd
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from shiny import App, ui, reactive, render, req, session as shiny_session

# ------------------------------ Config & Assets ------------------------------

APP_TITLE = "Night Owls — Waterdeep Secret Club"
GOLD = "#d0a85c"
IVORY = "#eae7e1"

COLUMNS = [
    "timestamp","ward","archetype","BI","EB","OQM",
    "renown_gain","notoriety_gain","EI_breakdown","notes","complication"
]

ASSETS_DIR = "assets"
BG_CANDIDATES = [f"{ASSETS_DIR}/bg.webp", f"{ASSETS_DIR}/bg.png"]
LOGO_CANDIDATES = [f"{ASSETS_DIR}/logo.webp", f"{ASSETS_DIR}/logo.png"]
RENOWN_IMG_CANDIDATES = [f"{ASSETS_DIR}/renown_gold.webp", f"{ASSETS_DIR}/renown_gold.png"]
NOTOR_IMG_CANDIDATES  = [f"{ASSETS_DIR}/notoriety_red.webp", f"{ASSETS_DIR}/notoriety_red.png"]
MURAL_CANDIDATES = [f"{ASSETS_DIR}/mural_sidebar.webp", f"{ASSETS_DIR}/mural_sidebar.png", f"{ASSETS_DIR}/mural.png"]

LOW_TABLE  = f"{ASSETS_DIR}/complications_low.json"
HIGH_TABLE = f"{ASSETS_DIR}/complications_high.json"

def _b64_from_file(paths: List[str]) -> str:
    for p in paths:
        try:
            with open(p, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            continue
    return ""

BG_B64     = _b64_from_file(BG_CANDIDATES)
LOGO_B64   = _b64_from_file(LOGO_CANDIDATES)
RENOWN_B64 = _b64_from_file(RENOWN_IMG_CANDIDATES)
NOTOR_B64  = _b64_from_file(NOTOR_IMG_CANDIDATES)
MURAL_B64  = _b64_from_file(MURAL_CANDIDATES)

# ------------------------------ Google Sheets (optional) ------------------------------

# Environment variables (set these in Posit Cloud -> Environment):
#  SHEET_ID="your_google_sheet_id"
#  WORKSHEET_NAME="Log"  (optional; defaults to Log)
#  GCP_SA_JSON="<entire service-account JSON string>"
#
# If these are missing, the app runs entirely in-session without failing.

def _get_sheets_cfg() -> Tuple[Optional[dict], Optional[str], str, Optional[str]]:
    sheet_id = os.environ.get("SHEET_ID", "").strip()
    ws_name  = os.environ.get("WORKSHEET_NAME", "Log").strip() or "Log"
    sa_raw   = os.environ.get("GCP_SA_JSON", "").strip()
    if not (sheet_id and sa_raw):
        return None, None, ws_name, "Missing SHEET_ID or GCP_SA_JSON env var."
    try:
        sa_json = json.loads(sa_raw)
        return sa_json, sheet_id, ws_name, None
    except Exception as e:
        return None, None, ws_name, f"Bad GCP_SA_JSON: {e}"

def _build_gspread_client(sa_json: dict):
    import gspread
    from google.oauth2.service_account import Credentials
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(sa_json, scopes=scopes)
    return gspread.authorize(creds)

def _ensure_worksheet(sa_json, sheet_id, worksheet_name="Log") -> Tuple[bool, Optional[str]]:
    try:
        import gspread
        gc = _build_gspread_client(sa_json)
        sh = gc.open_by_key(sheet_id)
        try:
            sh.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(title=worksheet_name, rows="1000", cols="20")
            ws.append_row(COLUMNS)
        return True, None
    except Exception as e:
        return False, str(e)

def append_rows_to_sheet(rows: List[List]) -> Tuple[bool, Optional[str]]:
    sa_json, sheet_id, ws_name, err = _get_sheets_cfg()
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

def load_ledger_from_sheet() -> Tuple[pd.DataFrame, Optional[str]]:
    sa_json, sheet_id, ws_name, err = _get_sheets_cfg()
    if err:
        return pd.DataFrame(columns=COLUMNS), err
    ok, err = _ensure_worksheet(sa_json, sheet_id, worksheet_name=ws_name)
    if not ok:
        return pd.DataFrame(columns=COLUMNS), err
    try:
        gc = _build_gspread_client(sa_json)
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet(ws_name)
        values = ws.get_all_values()
        if not values:
            return pd.DataFrame(columns=COLUMNS), None
        df = pd.DataFrame(values[1:], columns=values[0])
        for col in ["BI","EB","OQM","renown_gain","notoriety_gain"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(float)
        return df, None
    except Exception as e:
        return pd.DataFrame(columns=COLUMNS), str(e)

# ------------------------------ Mechanics ------------------------------

# ---------- Points thresholds ----------
RENOWN_THRESH = [5, 10, 15, 20, 25, 30]
NOTORIETY_THRESH = [5, 10, 15, 20, 25, 30]

def current_tier(total: float, thresholds: list[int]) -> int:
    t = 0
    for th in thresholds:
        if total >= th: t += 1
        else: break
    return t

def points_to_next(total: float, thresholds: list[int]) -> tuple[float, int|None]:
    for i, th in enumerate(thresholds, start=1):
        if total < th:
            return round(th - total, 2), i
    return 0.0, None

def mission_count(df: pd.DataFrame) -> int:
    if df.empty or "archetype" not in df.columns: return 0
    mask = df["archetype"].isin(["Help the Poor","Sabotage Evil","Expose Corruption"])
    return int(mask.sum())

# ---------- Points award functions ----------
# ---------- Points Engine (drop-in replace) ----------
import math

# Tier thresholds (points) — keep if you use "points to next tier" on crests
RENOWN_THRESH    = [5, 10, 15, 20, 25, 30]
NOTORIETY_THRESH = [5, 10, 15, 20, 25, 30]

# Arc flavour multipliers (tempered)
RENOWN_ARC_MULT = {
    "Help the Poor":   1.00,
    "Sabotage Evil":   1.15,
    "Expose Corruption": 1.30,
}
RISK_ARC_MULT = {
    "Help the Poor":   0.80,
    "Sabotage Evil":   1.10,
    "Expose Corruption": 1.30,
}

def current_tier(total: float, thresholds: list[int]) -> int:
    """0-based count of thresholds met."""
    t = 0
    for th in thresholds:
        if total >= th: t += 1
        else: break
    return t

def renown_points_from(*, gold: float, missions: int, arc: str,
                       impact: int | None, exposure: int | None,
                       oqm: int, eb: int,  # oqm: net Ops; eb: result bucket −3..+3
                       nat20: bool = False, nat1: bool = False) -> float:
    """
    Gold: diminishing returns hardened by mission count.
    Ops: minor effect (+3% per Ops).
    Result (EB): moderate (+4% per step, −3..+3).
    Impact/Exposure: moderate, only on their archetypes.
    Crits: +0.5 RP on nat20, −0.3 on nat1.
    """
    base = 2.0 * math.log1p(max(0.0, gold) / (50.0 + 10.0 * max(0, missions)))

    # minor Ops, moderate Result
    oqm_mult = 1.0 + 0.03 * oqm
    eb_mult  = 1.0 + 0.04 * eb

    # archetype-specific spice
    if arc == "Sabotage Evil":
        eff_mult = 1.0 + 0.07 * (((impact or 3) - 3))      # impact 1..5 → ±0.14
    elif arc == "Expose Corruption":
        eff_mult = 1.0 + 0.10 * (((exposure or 3) - 3))    # exposure 1..5 → ±0.20
    else:
        eff_mult = 1.0

    pts = RENOWN_ARC_MULT.get(arc, 1.0) * oqm_mult * eb_mult * eff_mult * base
    pts += 0.5 if nat20 else 0.0
    pts -= 0.3 if nat1  else 0.0
    return round(max(0.0, pts), 2)

def notoriety_points_from(*, gold: float, missions: int, arc: str,
                          impact: int | None, exposure: int | None,
                          oqm: int, eb: int,
                          current_notor_total: float,
                          nat20: bool = False, nat1: bool = False) -> float:
    """
    Mirrors renown but tuned ‘hotter’ and damped by good ops.
    Tier feedback: +8% per current notoriety tier.
    Ops: minor reduction (−3% per Ops, floored at −15%).
    Result (EB): moderate reduction (−3% per step, floored at −20%).
    Crits: −0.3 NP on nat20, +0.5 on nat1.
    """
    base = 1.6 * math.log1p(max(0.0, gold) / (80.0 + 12.0 * max(0, missions)))
    tier = current_tier(current_notor_total, NOTORIETY_THRESH)
    heat_scale = 1.0 + 0.08 * tier

    # minor dampers
    oqm_mult = max(0.85, 1.0 - 0.03 * oqm)
    eb_mult  = max(0.80, 1.0 - 0.03 * eb)

    if arc == "Sabotage Evil":
        eff_mult = 1.0 + 0.09 * (((impact or 3) - 3))      # ±0.18
    elif arc == "Expose Corruption":
        eff_mult = 1.0 + 0.12 * (((exposure or 3) - 3))    # ±0.24
    else:
        eff_mult = 1.0

    pts = RISK_ARC_MULT.get(arc, 1.0) * heat_scale * oqm_mult * eb_mult * eff_mult * base
    pts -= 0.3 if nat20 else 0.0
    pts += 0.5 if nat1  else 0.0
    return round(max(0.0, pts), 2)



def clamp(v, lo, hi): return max(lo, min(hi, v))
def heat_multiplier(n): return 1.5 if n>=20 else (1.25 if n>=10 else 1.0)

def compute_BI(arc: str, inputs: Dict[str,int]) -> int:
    if arc == "Help the Poor":
        spend = inputs.get("spend", 0)
        sb = 1 if spend < 25 else 2 if spend < 50 else 3 if spend < 100 else 4 if spend < 200 else 5
        return sb  # hb was undefined
    if arc == "Sabotage Evil":
        return inputs.get("impact_level", 1)
    return inputs.get("expose_level", 1)

def compute_base_score(BI:int, EB:int, OQM_list:List[int]) -> int:
    return clamp(BI + EB + clamp(sum(OQM_list), -2, 2), 1, 7)

def renown_from_score(base:int, arc:str) -> int:
    mult = {"Help the Poor":1.0,"Sabotage Evil":1.5,"Expose Corruption":2.0}[arc]
    return int(round(base*mult))

def notoriety_gain(cat_base:int, EI:int, n:int) -> int:
    return max(0, math.ceil((cat_base + max(0, EI-1)) * heat_multiplier(n)))

def low_or_high(n:int) -> str:
    return "High" if n>=10 else "Low"

def draw_wheel(labels: List[str], size:int=600, cols: Optional[List[str]]=None) -> Image.Image:
    n = len(labels)
    img = Image.new("RGBA", (size, size), (0,0,0,0))
    d = ImageDraw.Draw(img)
    cx, cy = size//2, size//2
    r = size//2 - 6
    palette = cols or ["#173b5a", "#12213f", "#0d3b4f", "#112b44"]
    for i,_ in enumerate(labels):
        start = 360*i/n - 90
        end   = 360*(i+1)/n - 90
        d.pieslice([cx-r, cy-r, cx+r, cy+r], start, end, fill=palette[i%len(palette)], outline="#213a53")
    d.ellipse([cx-r, cy-r, cx+r, cy+r], outline=GOLD, width=6)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 14)
    except:
        font = ImageFont.load_default()
    for i, lab in enumerate(labels):
        ang = math.radians(360*(i+.5)/n - 90)
        tx = cx + int((r-60)*math.cos(ang))
        ty = cy + int((r-60)*math.sin(ang))
        d.text((tx, ty), lab, fill=IVORY, font=font, anchor="mm")
    return img

def img_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

# ---- helper: build the projected-points line (pure string) ----
def projected_points_line(df: pd.DataFrame, arc: str, gold: float,
                          nat20: bool, nat1: bool, notor_total: float,
                          impact: int|None, exposure: int|None, oqm: int, eb: int) -> str:
    M  = mission_count(df)
    rp = renown_points_from(gold=gold, missions=M, arc=arc,
                            impact=impact, exposure=exposure, oqm=oqm, eb=eb,
                            nat20=nat20, nat1=nat1)
    np = notoriety_points_from(gold=gold, missions=M, arc=arc,
                               impact=impact, exposure=exposure, oqm=oqm, eb=eb,
                               current_notor_total=notor_total, nat20=nat20, nat1=nat1)
    return f"Projected Renown Points: {rp:.2f} • Projected Notoriety Points: {np:.2f} (Gold {gold:.0f}, Missions {M})"


# ------------------------------ Reactive State ------------------------------

renown      = reactive.Value(0)
notoriety   = reactive.Value(0)
ward_focus  = reactive.Value("Dock")
ledger_df   = reactive.Value(pd.DataFrame(columns=COLUMNS))

show_renown = reactive.Value(False)
show_notor  = reactive.Value(False)

last_angle       = reactive.Value(0)
selected_index   = reactive.Value(None)  # type: ignore
wheel_options    = reactive.Value([])    # list[str]

queued_mission   = reactive.Value(None)  # dict or None
spin_token = reactive.Value(None)  # bump on each spin to re-animate

# Bootstrap from Sheets (if configured) on first session
def _bootstrap_from_sheets():
    df, err = load_ledger_from_sheet()
    if err:
        # No sync — fine; start empty
        return
    if not df.empty:
        ledger_df.set(df)
        # in _reload()
        r = float(pd.to_numeric(remote.get("renown_gain", pd.Series()), errors="coerce").fillna(0).sum())
        n = float(pd.to_numeric(remote.get("notoriety_gain", pd.Series()), errors="coerce").fillna(0).sum())
        renown.set(r); notoriety.set(n)


_bootstrap_from_sheets()

# --- Palette from background image ---
def _first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None

def _avg_rgb(path: str) -> tuple[int, int, int]:
    try:
        im = Image.open(path).convert("RGB").resize((64, 64))
        arr = np.array(im).reshape(-1, 3)
        r, g, b = arr.mean(axis=0)
        return int(r), int(g), int(b)
    except Exception:
        return (32, 42, 64)  # sane dark fallback

def _hex(rgb): return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
def _lighten(rgb, f):  # f in [0..1]
    return tuple(int(min(255, c + (255 - c) * f)) for c in rgb)
def _darken(rgb, f):
    return tuple(int(max(0, c * (1 - f))) for c in rgb)

_BG_PATH = _first_existing(BG_CANDIDATES)
_ACCENT_RGB = _avg_rgb(_BG_PATH) if _BG_PATH else (32, 42, 64)
ACCENT = _hex(_ACCENT_RGB)
ACCENT_LIGHT = _hex(_lighten(_ACCENT_RGB, 0.35))
ACCENT_DARK  = _hex(_darken(_ACCENT_RGB, 0.25))

# ------------------------------ UI ------------------------------

GLOBAL_CSS = f"""
<style>
@import url("https://fonts.googleapis.com/css2?family=Cinzel+Decorative:wght@400;700&family=IM+Fell+English+SC&display=swap");

:root {{
  --accent: {ACCENT};
  --accent-light: {ACCENT_LIGHT};
  --accent-dark: {ACCENT_DARK};
  --ivory: {IVORY};
  --gold: {GOLD};
  --heat-red: #e24a3c;       /* scarlet for Notoriety */
  --midnight: #0b1424;       /* deep theme blue behind the mural */
  --bs-body-bg: transparent;
  --bs-body-color: var(--ivory);
  --bs-border-color: rgba(255,255,255,0.12);
}}

html, body {{
  min-height: 100%;
  color: var(--ivory);
  background-color: var(--midnight); /* solid canvas behind the image */
  background-image: url('data:image/png;base64,{BG_B64}');
  background-repeat: no-repeat;
  background-position: center center;
  background-attachment: fixed;
  background-size: cover;
}}

h1, h2, h3, h4, label, .form-label {{ color: var(--ivory); }}
/* Title: punch up legibility everywhere */
#app-root h2 {{
  color: var(--ivory) !important;
  text-shadow: 0 4px 14px rgba(0,0,0,.85), 0 0 2px rgba(0,0,0,.95);
  letter-spacing: .2px;
}}

a {{ color: var(--accent-light); }}

/* ---------- App shell ---------- */
#app-root {{
  background: linear-gradient(180deg, rgba(0,0,0,0.36), rgba(0,0,0,0.64));
  backdrop-filter: blur(14px) saturate(1.15);
  -webkit-backdrop-filter: blur(14px) saturate(1.15);
  border: 1px solid var(--gold);
  border-radius: 24px;
  box-shadow: 0 20px 50px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);
  padding: 1.0rem 1.2rem;
  margin-top: .6rem;
}}

.goldrim,
.card,
.tiers,
.result-card {{
  background: rgba(10,14,28,0.74);
  border: 1px solid var(--gold) !important;   /* ← gold outlines on all boxes */
  border-radius: 14px;
  color: var(--ivory);
}}

/* ---------- Sidebar ---------- */
aside.sidebar {{
  background: linear-gradient(180deg, rgba(10,14,28,0.92), rgba(10,14,28,0.82));
  border-right: 1px solid var(--gold);
  backdrop-filter: blur(10px) saturate(1.1);
  -webkit-backdrop-filter: blur(10px) saturate(1.1);
}}
aside.sidebar .card {{ background: transparent; }}
#sidebar-mural {{
  position: relative; height: 1120px; margin-top: 8px; z-index: 0;
  background: url('data:image/png;base64,{MURAL_B64}') no-repeat center top / contain;
  opacity: 0.9; filter: drop-shadow(0 6px 12px rgba(0,0,0,.25));
  pointer-events: none;
}}

/* ---------- Tabs ---------- */
.nav-tabs .nav-link {{
  color: var(--ivory);
  background: rgba(10,14,28,0.45);
  border: 1px solid var(--gold);
}}
.nav-tabs .nav-link.active {{
  color: #fff;
  background-color: var(--accent-dark);
  border-color: var(--gold);
}}

/* ---------- Inputs: dark glass + gold borders ---------- */
.form-control,
.form-select,
.selectize-input,
.input-group-text {{
  color: var(--ivory);
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(208,168,92,.65);      /* soft gold */
}}
.form-control:focus,
.form-select:focus,
.selectize-input.focus {{
  color: var(--ivory);
  background: rgba(255,255,255,0.10);
  border-color: var(--gold);
  box-shadow: 0 0 0 .2rem rgba(208,168,92,.35);
}}
.form-check-label {{ color: var(--ivory); }}
.form-check-input {{ background-color: rgba(255,255,255,0.1); border-color: rgba(208,168,92,.65); }}
.form-check-input:checked {{ background-color: var(--gold); border-color: var(--gold); }}

/* Sliders */
.form-range::-webkit-slider-thumb {{ background: var(--gold); }}
.form-range::-webkit-slider-runnable-track {{ background: rgba(255,255,255,0.18); }}
.form-range::-moz-range-thumb {{ background: var(--gold); }}
.form-range::-moz-range-track {{ background: rgba(255,255,255,0.18); }}

/* ---------- Buttons ---------- */
.btn-primary {{ background-color: var(--accent); border-color: var(--gold); }}
.btn-secondary {{ background-color: var(--accent-dark); border-color: var(--gold); }}

/* Specific gold actions (IDs come from input_action_button ids) */
#lie_low, #proxy_charity {{
  background-color: var(--gold) !important;
  border-color: var(--gold) !important;
  color: #0d1323 !important;
}}
#lie_low:hover, #proxy_charity:hover,
#lie_low:focus, #proxy_charity:focus {{
  filter: brightness(1.05);
  box-shadow: 0 0 0 .2rem rgba(208,168,92,.35);
}}

/* ---------- Crests ---------- */
.score-badge {{ position: relative; display: inline-flex; align-items: center; gap: 14px; padding: 6px 0; }}
.score-badge img {{ width: 220px; height: 220px; object-fit: contain; filter: drop-shadow(0 6px 12px rgba(0,0,0,.35)); }}
.score-badge .label {{ font-size: 15px; opacity: .95; letter-spacing: .4px; }}
.score-badge .val   {{ font-size: 58px; font-weight: 800; line-height: 1.05; text-shadow: 0 2px 6px rgba(0,0,0,.55); }}

/* Invisible overlay button — never grey on hover */
.ghost-btn, .ghost-btn:hover, .ghost-btn:active, .ghost-btn:focus {{
  position:absolute; inset:0;
  background: transparent !important;
  border: none !important;
  color: transparent !important;
  box-shadow: none !important;
  outline: none !important;
  cursor: pointer;
}}

/* ---------- Wheel ---------- */
#wheel_wrap {{ position: relative; width: 600px; margin: 0 auto; }}
#wheel_img {{ width: 100%; height: 100%; border-radius: 50%; box-shadow: 0 10px 40px rgba(0,0,0,.55); background: radial-gradient(closest-side, rgba(255,255,255,0.06), transparent); }}
#pointer {{
  position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
  width: 0; height: 0; border-left: 16px solid transparent; border-right: 16px solid transparent;
  border-bottom: 26px solid var(--gold); filter: drop-shadow(0 2px 2px rgba(0,0,0,.4));
}}
.spin-btn {{
  position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
  min-width: 120px; height: 120px; border-radius: 60px;
  display:grid; place-items:center; font-weight:700; letter-spacing:.5px; text-transform:uppercase;
  border:1px solid var(--gold);
  background:linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02));
  backdrop-filter: blur(8px) saturate(1.1); -webkit-backdrop-filter: blur(8px) saturate(1.1);
  box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
  color: var(--ivory);
}}
@keyframes wheelspin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(var(--spin-deg, 1440deg)); }} }}
#wheel_img.spinning {{ animation: wheelspin 3.2s cubic-bezier(.17,.67,.32,1.35); }}

/* ---------- Tier tables ---------- */
.tier-table {{ width: 100%; border-collapse: collapse; color: var(--ivory); }}
.tier-table th, .tier-table td {{ border-top: 1px solid rgba(208,168,92,.35); padding: 8px 10px; vertical-align: top; }}
.tier-table tr:first-child th, .tier-table tr:first-child td {{ border-top: none; }}
.tt-badge {{ font-weight: 800; }}
.tt-gold {{ color: var(--gold); }}      /* Renown labels */
.tt-red  {{ color: var(--heat-red); }}  /* Notoriety labels */
</style>
"""




def crest_html(label: str, value: int, b64: str, dom_id: str) -> ui.HTML:
    return ui.HTML(f"""
    <div class="score-badge" id="{dom_id}" title="Click to view tiers">
      <img src="data:image/png;base64,{b64}" alt="{label}">
      <div class="meta">
        <div class="label">{label}</div>
        <div class="val">{value}</div>
      </div>
    </div>
    """)

# Tiers HTML
RENOWN_TIERS_HTML = f"""
<div class="tiers">
  <h4>Veil-Fame perks — subtle favours while the mask stays on</h4>
  <table class="tier-table">
    <tr><th>Tier</th><th>Threshold</th><th>Perks (quiet, deniable)</th></tr>
    <tr><td class="tt-badge tt-gold">R1</td><td>5</td><td><b>Street Signals</b>: advantage to glean rumours; hand-signs recognised across working wards.</td></tr>
    <tr><td class="tt-badge tt-gold">R2</td><td>10</td><td><b>Quiet Hands</b>: once/session arrange a safe hand-off (stash, message, disguise kit) nearby.</td></tr>
    <tr><td class="tt-badge tt-gold">R3</td><td>15</td><td><b>Crowd Cover</b>: once/long rest break line-of-sight; one round of full cover while slipping away.</td></tr>
    <tr><td class="tt-badge tt-gold">R4</td><td>20</td><td><b>Whisper Network</b>: one social check/scene at advantage vs townsfolk; one free d6 help/session for urban navigation or scrounge.</td></tr>
    <tr><td class="tt-badge tt-gold">R5</td><td>25</td><td><b>Safehouses</b>: two boltholes; short rests can’t be disturbed; once/adventure negate a post-job pursuit.</td></tr>
    <tr><td class="tt-badge tt-gold">R6</td><td>30</td><td><b>Folk Halo</b> (anonymous): −10% mundane gear; once/adventure the crowd “coincidentally” intervenes.</td></tr>
  </table>
</div>
"""

NOTOR_TIERS_HTML = f"""
<div class="tiers">
  <h4>City Heat — escalating responses without unmasking you</h4>
  <table class="tier-table">
    <tr><th>Band</th><th>Score</th><th>City response</th></tr>
    <tr><td class="tt-badge tt-red">N0 — Cold</td><td>0–4</td><td>Nothing special.</td></tr>
    <tr><td class="tt-badge tt-red">N1 — Warm</td><td>5–9</td><td><b>Ward sweeps</b>: DC checks after hot jobs; ignore at peril of +1 heat.</td></tr>
    <tr><td class="tt-badge tt-red">N2 — Hot</td><td>10–14</td><td><b>Pattern watch</b>: repeat MOs +2 DC; kit spot-checks risk +1 heat.</td></tr>
    <tr><td class="tt-badge tt-red">N3 — Scalding</td><td>15–19</td><td><b>Counter-ops</b>: rivals meddle; residue detectors; reused looks at disadvantage.</td></tr>
    <tr><td class="tt-badge tt-red">N4 — Burning</td><td>20–24</td><td><b>Scry-sweeps</b>: casting risks Trace test; fail = +2 heat and a tail.</td></tr>
    <tr><td class="tt-badge tt-red">N5 — Inferno</td><td>25–30</td><td><b>Citywide dragnet</b>: curfews; +2 DC to stealth/social; bounty posted.</td></tr>
  </table>
</div>
"""

# Sidebar (logo + welcome + mural)
sidebar = ui.sidebar(
    ui.div(
        ui.img(src=f"data:image/png;base64,{LOGO_B64}", style="width:100%;"),
        ui.div(
            ui.h3("Night Owls"),
            ui.p("By moonlight take flight,\nBy your deed will the city be freed.\nYou give a hoot!"),
            class_="welcome"
        ),
        ui.div(id="sidebar-mural"),
    ),
    open="always",
    width=360
)

# Tabs
tab_mission = ui.nav_panel(
    "🗺️ Mission Generator",
    ui.input_radio_buttons("arc", "Archetype",
        ["Help the Poor","Sabotage Evil","Expose Corruption"], inline=True),
    ui.layout_columns(
        ui.card(
            ui.input_numeric("spend", "Gold Spent", 40, min=0, step=5),
            ui.input_checkbox("plan_help", "Ops Prep (+1 Ops)", True),
            id="help_inputs"
        ),
        ui.card(
            ui.input_slider("impact","Impact Level (1→5)", 1, 5, 3),
            ui.input_checkbox("plan_sab","Inside Contact (+1 Ops)", False),
            ui.input_checkbox("rushed","Rushed/Loud (−1 Ops)", False),
            id="sab_inputs"
        ),
        ui.card(
            ui.input_slider("expose","Exposure Level (1→5)", 1, 5, 3),
            ui.input_checkbox("proof","Hard Proof / Magical Corroboration (+1 Ops)", False),
            ui.input_checkbox("reused","Reused Signature (−1 Ops)", False),
            id="exp_inputs"
        ),
    ),
    ui.hr(),
    ui.h4("Resolution"),
    ui.layout_columns(
        ui.input_slider("roll", "Result (0–30)", 0, 30, 15),
        ui.input_checkbox("nat20","Natural 20", False),
        ui.input_checkbox("nat1","Critical botch", False),
    ),
)  # ← this closing paren was missing

tab_resolve = ui.nav_panel(
    "🎯 Resolve & Log",
    ui.output_ui("queued_json"),
    ui.input_text("notes","Notes (optional)"),
    ui.input_action_button("apply", "Apply Gains & Log", class_="btn btn-primary"),
    ui.hr(),
    ui.h4("Push Log to Google Sheets"),
    ui.input_action_button("append_all", "Append All Rows to Sheets", class_="btn btn-secondary"),
    ui.output_text("append_status"),
)

tab_wheel = ui.nav_panel(
    "☸️ Wheel of Fortune",
    ui.output_text("heat_caption"),
    ui.output_ui("wheel_ui"),
    ui.output_ui("wheel_result"),
)

tab_ledger = ui.nav_panel(
    "📜 Ledger",
    ui.input_action_button("reload", "Refresh from Google Sheets", class_="btn btn-secondary"),
    ui.output_text("reload_status"),
    ui.output_ui("ledger_table"),
    ui.download_button("dl_csv", "Download CSV"),
)

# Top row: KPI crests + ward select + heat buttons
kpi_row = ui.layout_columns(
    ui.card(ui.output_ui("renown_badge"), ui.output_ui("_tiers_renown")),
    ui.card(
        ui.output_ui("notor_badge"), ui.output_ui("_tiers_notor"),
        ui.layout_columns(
            ui.input_action_button("lie_low", "Lie Low (−1/−2 Heat)"),
            ui.input_action_button("proxy_charity", "Proxy Charity (−1 Heat)"),
        )
    ),
    ui.card(ui.input_select("ward","Active Ward",
           choices=["Dock","Field","South","North","Castle","Trades","Sea"], selected="Dock"))
)

app_ui = ui.page_sidebar(
    sidebar,
    ui.head_content(ui.HTML(GLOBAL_CSS)),  # ← use head_content for 1.5
    ui.div(
        ui.h2(APP_TITLE),
        kpi_row,
        ui.navset_tab(tab_mission, tab_resolve, tab_wheel, tab_ledger),
        id="app-root", class_="goldrim"
    ),
    title=APP_TITLE
)


# ------------------------------ Server ------------------------------

def server(input, output, session):
    # Ward binding
    @reactive.Effect
    def _ward():
        ward_focus.set(input.ward())

    def _eb_from_roll(roll: int, nat20: bool) -> int:
        if nat20:
            return 3
        # map 0..30 to -3..+3 in 5-pt steps; clamp
        return max(-3, min(3, int(round((roll - 15) / 5))))


    def _arc_params():
        arc  = input.arc()
        gold = float(input.spend())
        roll = int(input.roll())
        eb   = _eb_from_roll(roll, input.nat20())
        if arc == "Sabotage Evil":
            impact, exposure = int(input.impact()), None
        elif arc == "Expose Corruption":
            impact, exposure = None, int(input.expose())
        else:
            impact, exposure = None, None
        oqm = oqm_from_inputs(arc, input)
        return arc, gold, eb, impact, exposure, oqm

    # Crest values → badges
    @output
    @render.ui
    def renown_badge():
        total = renown.get()
        to_next, nxt = points_to_next(total, RENOWN_THRESH)
        sub = f'{to_next:.1f} pts to R{nxt}' if nxt else 'Max tier'
        return ui.div(
            ui.HTML(f"""
              <div class="score-badge">
                <img src="data:image/png;base64,{RENOWN_B64}" alt="Renown">
                <div class="meta">
                  <div class="label">Renown</div>
                  <div class="val">{total:.1f}</div>
                  <div class="sub" style="font-size:12px;color:var(--gold);opacity:.95;">{sub}</div>
                </div>
              </div>
            """),
            ui.input_action_button("renown_clicked", "", class_="ghost-btn"),
            style="position:relative; display:inline-block;"
        )


    @reactive.Effect
    @reactive.event(input.renown_clicked)
    def _toggle_r():
        show_renown.set(not show_renown.get())

    @reactive.Effect
    @reactive.event(input.notor_clicked)
    def _toggle_n():
        show_notor.set(not show_notor.get())


    @output
    @render.ui
    def notor_badge():
        total = notoriety.get()
        to_next, nxt = points_to_next(total, NOTORIETY_THRESH)
        sub = f'{to_next:.1f} pts to N{nxt}' if nxt else 'Max tier'
        return ui.div(
            ui.HTML(f"""
              <div class="score-badge">
                <img src="data:image/png;base64,{NOTOR_B64}" alt="Notoriety">
                <div class="meta">
                  <div class="label">Notoriety</div>
                  <div class="val">{total:.1f}</div>
                  <div class="sub" style="font-size:12px;color:var(--heat-red);opacity:.95;">{sub}</div>
                </div>
              </div>
            """),
            ui.input_action_button("notor_clicked", "", class_="ghost-btn"),
            style="position:relative; display:inline-block;"
        )


    # Heat buttons
    @reactive.Effect
    @reactive.event(input.lie_low)
    def _lie_low():
        drop = 2 if notoriety.get() >= 10 else 1
        notoriety.set(max(0, notoriety.get() - drop))
        row = [
            dt.datetime.now().isoformat(timespec="seconds"), ward_focus.get(),
            "Adjustment: Lie Low", "-", "-", "-", 0, -drop, "-", "auto", ""
        ]
        df = ledger_df.get().copy()
        df.loc[len(df)] = row
        ledger_df.set(df)
        ok, err = append_rows_to_sheet([row])
        # Silent soft-fail; status appears in Append All and Reload sections

    @reactive.Effect
    @reactive.event(input.proxy_charity)
    def _proxy_charity():
        notoriety.set(max(0, notoriety.get() - 1))
        row = [
            dt.datetime.now().isoformat(timespec="seconds"), ward_focus.get(),
            "Adjustment: Proxy Charity", "-", "-", "-", 0, -1, "-", "auto", ""
        ]
        df = ledger_df.get().copy()
        df.loc[len(df)] = row
        ledger_df.set(df)
        append_rows_to_sheet([row])

    # Mission panel visibility controls
    def _arc_state():
        return input.arc()

    @output
    @render.text
    def base_summary():
        arc, gold, eb, impact, exposure, oqm = _arc_params()
        return projected_points_line(ledger_df.get(), arc, gold, input.nat20(), input.nat1(),
                                     notoriety.get(), impact, exposure, oqm, eb)

    @output
    @render.text
    def proj_summary():
        arc, gold, eb, impact, exposure, oqm = _arc_params()
        return projected_points_line(
            ledger_df.get(), arc, gold, input.nat20(), input.nat1(),
            notoriety.get(), impact, exposure, oqm, eb
        )

    # Queue mission
    @reactive.Effect
    @reactive.event(input.queue)
    def _queue():
        arc, gold, eb, impact, exposure, oqm = _arc_params()
        M = mission_count(ledger_df.get())

        rp = renown_points_from(gold=gold, missions=M, arc=arc,
                                impact=impact, exposure=exposure, oqm=oqm, eb=eb,
                                nat20=input.nat20(), nat1=input.nat1())
        np = notoriety_points_from(gold=gold, missions=M, arc=arc,
                                   impact=impact, exposure=exposure, oqm=oqm, eb=eb,
                                   current_notor_total=notoriety.get(),
                                   nat20=input.nat20(), nat1=input.nat1())

        queued_mission.set(dict(
            ward=ward_focus.get(), archetype=arc, BI="-", EB=eb, OQM=oqm,
            renown_gain=rp, notoriety_gain=np,
            EI_breakdown=dict(gold=gold, missions_so_far=M, impact=impact, exposure=exposure)
        ))


    @output
    @render.ui
    def queued_json():
        q = queued_mission.get()
        if not q:
            return ui.div({"class": "alert alert-info goldrim", "role": "alert"}, "No queued mission.")
        # pretty JSON
        return ui.pre(json.dumps(q, indent=2), class_="goldrim", style="padding:10px;")

    # Apply mission
    @reactive.Effect
    @reactive.event(input.apply)
    def _apply():
        q = queued_mission.get()
        if not q: return

        renown.set(renown.get() + float(q["renown_gain"]))
        notoriety.set(notoriety.get() + float(q["notoriety_gain"]))

        row = [
            dt.datetime.now().isoformat(timespec="seconds"),
            q["ward"], q["archetype"],
            q["BI"], q["EB"], q["OQM"],
            q["renown_gain"], q["notoriety_gain"],
            json.dumps(q["EI_breakdown"]), input.notes() or "", ""
        ]
        df = ledger_df.get().copy()
        df.loc[len(df)] = row
        ledger_df.set(df)

        ok, _err = append_rows_to_sheet([row])
        # Optional: reload and recompute floats if you want source-of-truth from Sheets.
        queued_mission.set(None)


    # Append all
    @output
    @render.text
    def append_status():
        return ""

    @reactive.Effect
    @reactive.event(input.append_all)
    def _append_all():
        rows = ledger_df.get().values.tolist()
        ok, err = append_rows_to_sheet(rows)
        if ok:
            ui.notification_show(f"Appended {len(rows)} rows.", type="message", duration=4)
        else:
            ui.notification_show(f"Sheets error: {err or 'Unknown error'}", type="warning", duration=6)

    # Wheel — options table based on heat
    def _load_options() -> List[str]:
        tpath = HIGH_TABLE if notoriety.get() >= 10 else LOW_TABLE
        with open(tpath, "r") as f:
            data = json.load(f)
        # Force to list[str]
        return [str(x) for x in data]

    @output
    @render.text
    def heat_caption():
        return f"Heat: **{low_or_high(notoriety.get())}**"

    @output
    @render.ui
    def wheel_ui():
        # Load/remember options (with fallback if JSON is missing/empty)
        def _safe_opts():
            tpath = HIGH_TABLE if notoriety.get() >= 10 else LOW_TABLE
            try:
                with open(tpath, "r") as f:
                    data = [str(x) for x in json.load(f)]
                return data if data else [f"Complication {i}" for i in range(1, 13)]
            except Exception:
                return [f"Complication {i}" for i in range(1, 13)]

        opts = _safe_opts()
        wheel_options.set(opts)

        size = 600
        b64 = img_b64(draw_wheel([str(i + 1) for i in range(len(opts))], size=size))
        angle = last_angle.get()
        spinning = "spinning" if spin_token.get() else ""

        # One container with both the image and the button as children.
        return ui.div(
            {"id": "wheel_wrap", "style": f"position:relative;width:{size}px;height:{size}px;margin:0 auto;"},
            ui.HTML(f"""
              <div id="pointer"></div>
              <img id="wheel_img" class="{spinning}" src="data:image/png;base64,{b64}"
                   style="--spin-deg:{angle}deg;width:100%;height:100%;border-radius:50%;" />
            """),
            ui.input_action_button("spin_clicked", "SPIN!", class_="spin-btn")
        )


    @reactive.Effect
    @reactive.event(input.spin_clicked)
    def _spin():
        opts = wheel_options.get()
        if not opts: return
        n = len(opts)
        idx = random.randrange(n)
        selected_index.set(idx)
        seg = 360 / n

        # Guarantee a new animation cycle
        spin_token.set(None)
        last_angle.set(random.randint(4, 7) * 360 + (idx + 0.5) * seg)
        spin_token.set(dt.datetime.now().isoformat())

        # Log a journal line
        row = [dt.datetime.now().isoformat(timespec="seconds"),
               ward_focus.get(), "Complication", "-", "-", "-", 0, 0, "-", "-", opts[idx]]
        df = ledger_df.get().copy()
        df.loc[len(df)] = row
        ledger_df.set(df)

    @output
    @render.ui
    def wheel_result():
        idx = selected_index.get()
        opts = wheel_options.get()
        if idx is None or not opts:
            return ui.HTML("")
        return ui.HTML(f"""
        <div class="result-card">
          <div class="result-number">Result {idx+1:02d} / {len(opts):02d}</div>
          <div class="result-text">{opts[idx]}</div>
        </div>
        """)

    # Ledger
    @reactive.Effect
    @reactive.event(input.reload)
    def _reload():
        remote, err = load_ledger_from_sheet()
        if err:
            ui.notification_show(f"Reload failed: {err}", type="warning", duration=6)
        else:
            ledger_df.set(remote)
            r = int(pd.to_numeric(remote.get("renown_gain", pd.Series()), errors="coerce").fillna(0).sum())
            n = int(pd.to_numeric(remote.get("notoriety_gain", pd.Series()), errors="coerce").fillna(0).sum())
            renown.set(r); notoriety.set(n)
            ui.notification_show("Ledger reloaded and counters recalculated.", type="message", duration=4)

    @output
    @render.text
    def reload_status():
        return ""

    @output
    @render.ui
    def ledger_table():
        df = ledger_df.get()
        if df.empty:
            return ui.div({"class":"alert alert-info goldrim", "role":"alert"}, "Ledger is empty.")
        sty = "width:100%; overflow:auto; max-height:460px; display:block;"
        return ui.HTML(f'<div class="goldrim" style="padding:8px; {sty}">{df.to_html(index=False, classes="table table-sm text-light")}</div>')

    # Download CSV
    @session.download(filename="night_owls_ledger.csv")
    def dl_csv():
        df = ledger_df.get()
        yield df.to_csv(index=False)

    # Crest tier reveals (render beneath crests)
    @output
    @render.ui
    def _tiers_renown():
        return ui.HTML(RENOWN_TIERS_HTML) if show_renown.get() else ui.HTML("")

    @output
    @render.ui
    def _tiers_notor():
        return ui.HTML(NOTOR_TIERS_HTML) if show_notor.get() else ui.HTML("")

# Mount the app
app = App(app_ui, server)
