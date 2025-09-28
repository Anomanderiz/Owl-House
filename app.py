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
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        return df, None
    except Exception as e:
        return pd.DataFrame(columns=COLUMNS), str(e)

# ------------------------------ Mechanics ------------------------------

def clamp(v, lo, hi): return max(lo, min(hi, v))
def heat_multiplier(n): return 1.5 if n>=20 else (1.25 if n>=10 else 1.0)

def compute_BI(arc: str, inputs: Dict[str,int]) -> int:
    if arc=="Help the Poor":
        spend=inputs.get("spend",0); hh=inputs.get("households",0)
        sb = 1 if spend<25 else 2 if spend<50 else 3 if spend<100 else 4 if spend<200 else 5
        hb = 1 if hh<10   else 2 if hh<25   else 3 if hh<50   else 4 if hh<100  else 5
        return max(sb,hb)
    if arc=="Sabotage Evil":
        return inputs.get("impact_level",1)
    return inputs.get("expose_level",1)

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

# Bootstrap from Sheets (if configured) on first session
def _bootstrap_from_sheets():
    df, err = load_ledger_from_sheet()
    if err:
        # No sync — fine; start empty
        return
    if not df.empty:
        ledger_df.set(df)
        r = int(pd.to_numeric(df.get("renown_gain", pd.Series()), errors="coerce").fillna(0).sum())
        n = int(pd.to_numeric(df.get("notoriety_gain", pd.Series()), errors="coerce").fillna(0).sum())
        renown.set(r); notoriety.set(n)

_bootstrap_from_sheets()

# ------------------------------ UI ------------------------------

# Global CSS (glass, gold rims, hide headers, background image)
GLOBAL_CSS = f"""
<style>
@import url("https://fonts.googleapis.com/css2?family=Cinzel+Decorative:wght@400;700&family=IM+Fell+English+SC&display=swap");

html, body {{
  height: 100%;
  background: url('data:image/png;base64,{BG_B64}') no-repeat center center fixed;
  background-size: cover;
}}
#app-root {{
  background: rgba(12,17,40,0.62);
  backdrop-filter: blur(14px) saturate(1.15);
  -webkit-backdrop-filter: blur(14px) saturate(1.15);
  border: 1px solid rgba(208,168,92,0.22);
  border-radius: 24px;
  box-shadow: 0 20px 50px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.06);
  padding: 1.0rem 1.2rem;
  margin-top: .6rem;
}}
h1, h2, h3, h4 {{ color: {IVORY}; text-shadow: 0 1px 0 rgba(0,0,0,0.35); }}

.goldrim {{
  border: 1px solid rgba(208,168,92,.35) !important;
  border-radius: 14px !important;
  box-shadow: 0 10px 24px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.06) !important;
  background: rgba(14,18,38,.60);
}}

.welcome {{
  border: 1px solid rgba(208,168,92,0.35);
  border-radius: 18px;
  padding: 1rem 1.1rem;
  background: rgba(14,18,38,0.70);
  box-shadow: inset 0 0 0 1px rgba(255,255,255,0.04), 0 10px 30px rgba(0,0,0,0.35);
}}
.welcome h3 {{ font-family: "Cinzel Decorative", serif; color: {IVORY}; margin: 0 0 .35rem 0; }}
.welcome p {{ font-family: "IM Fell English SC", serif; font-size: 1.05rem; line-height: 1.3; color: {IVORY}; opacity: .92; }}

.score-badge {{
  position: relative; display: inline-flex; align-items: center; gap: 14px;
  padding: 6px 0; background: transparent; border: none; cursor: pointer; user-select: none;
}}
.score-badge img {{
  width: 250px; height: 250px; object-fit: contain;
  filter: drop-shadow(0 6px 12px rgba(0,0,0,.35));
}}
.score-badge .label {{ font-size: 15px; color: {IVORY}; opacity: .85; letter-spacing: .4px; }}
.score-badge .val   {{ font-size: 56px; color: {IVORY}; font-weight: 800; line-height: 1.05; text-shadow: 0 1px 0 rgba(0,0,0,.35); }}
@media (max-width: 900px){{
  .score-badge img{{ width: 72px; height: 72px; }}
  .score-badge .val{{ font-size: 42px; }}
}}

.tiers {{
  margin-top: 10px; padding: 14px 16px; border-radius: 16px;
  background: rgba(16,24,32,.55); border: 1px solid rgba(208,168,92,.45);
  box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
  color: {IVORY};
}}
.tier-table {{ width: 100%; border-collapse: collapse; color: {IVORY}; }}
.tier-table th, .tier-table td {{ border-top: 1px solid rgba(208,168,92,.25); padding: 8px 10px; vertical-align: top; }}
.tier-table tr:first-child th, .tier-table tr:first-child td {{ border-top: none; }}
.tt-badge {{ color: {GOLD}; font-weight: 700; }}

#wheel_wrap {{ position: relative; width: 600px; margin: 0 auto; }}
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

.result-card {{
  max-width: 900px; margin: 18px auto 0; padding: 18px 20px;
  border-radius: 14px;
  background: rgba(16,24,32,0.55);
  border: 1px solid rgba(208,168,92,0.45);
  box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,0.06);
  backdrop-filter: blur(6px) saturate(1.05);
  -webkit-backdrop-filter: blur(6px) saturate(1.05);
  animation: fadein .35s ease-out;
  color: {IVORY};
}}
.result-number {{ font-size: 13px; letter-spacing: .4px; color: {GOLD}; text-transform: uppercase; opacity: .9; margin-bottom: 6px; }}
.result-text {{ line-height: 1.5; font-size: 16px; }}
@keyframes fadein {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}

#sidebar-mural {{
  position: relative; height: 1120px; margin-top: 8px; z-index: 0;
  background: url('data:image/png;base64,{MURAL_B64}') no-repeat center top / contain;
  opacity: 0.8; filter: drop-shadow(0 6px 12px rgba(0,0,0,.25));
  pointer-events: none;
}}
</style>
"""

# Crest widgets (click → JS sets input values)
CREST_JS = """
<script>
(function(){
  // Utility to pulse an input event (so every click is distinct)
  const pulse = (id) => {
    if (window.Shiny && Shiny.setInputValue) {
      Shiny.setInputValue(id, Date.now(), {priority: 'event'});
    } else if (window.pyshiny && pyshiny.setInputValue) {
      pyshiny.setInputValue(id, Date.now(), {priority: 'event'});
    }
  };
  const r = document.getElementById('renown_badge');
  const n = document.getElementById('notor_badge');
  if (r) r.addEventListener('click', ()=>pulse('renown_clicked'));
  if (n) n.addEventListener('click', ()=>pulse('notor_clicked'));

  const spin = document.getElementById('spin_overlay');
  if (spin) spin.addEventListener('click', ()=>pulse('spin_clicked'));
})();
</script>
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
    <tr><td class="tt-badge">R1</td><td>5</td><td><b>Street Signals</b>: advantage to glean rumours; hand-signs recognised across working wards.</td></tr>
    <tr><td class="tt-badge">R2</td><td>10</td><td><b>Quiet Hands</b>: once/session arrange a safe hand-off (stash, message, disguise kit) nearby.</td></tr>
    <tr><td class="tt-badge">R3</td><td>15</td><td><b>Crowd Cover</b>: once/long rest break line-of-sight; one round of full cover while slipping away.</td></tr>
    <tr><td class="tt-badge">R4</td><td>20</td><td><b>Whisper Network</b>: one social check/scene at advantage vs townsfolk; one free d6 help/session for urban navigation or scrounge.</td></tr>
    <tr><td class="tt-badge">R5</td><td>25</td><td><b>Safehouses</b>: two boltholes; short rests can’t be disturbed; once/adventure negate a post-job pursuit.</td></tr>
    <tr><td class="tt-badge">R6</td><td>30</td><td><b>Folk Halo</b> (anonymous): −10% mundane gear; once/adventure the crowd “coincidentally” intervenes.</td></tr>
  </table>
</div>
"""

NOTOR_TIERS_HTML = f"""
<div class="tiers">
  <h4>City Heat — escalating responses without unmasking you</h4>
  <table class="tier-table">
    <tr><th>Band</th><th>Score</th><th>City response</th></tr>
    <tr><td class="tt-badge">N0 — Cold</td><td>0–4</td><td>Nothing special.</td></tr>
    <tr><td class="tt-badge">N1 — Warm</td><td>5–9</td><td><b>Ward sweeps</b>: DC checks after hot jobs; ignore at peril of +1 heat.</td></tr>
    <tr><td class="tt-badge">N2 — Hot</td><td>10–14</td><td><b>Pattern watch</b>: repeat MOs +2 DC; kit spot-checks risk +1 heat.</td></tr>
    <tr><td class="tt-badge">N3 — Scalding</td><td>15–19</td><td><b>Counter-ops</b>: rivals meddle; residue detectors; reused looks at disadvantage.</td></tr>
    <tr><td class="tt-badge">N4 — Burning</td><td>20–24</td><td><b>Scry-sweeps</b>: casting risks Trace test; fail = +2 heat and a tail.</td></tr>
    <tr><td class="tt-badge">N5 — Inferno</td><td>25–30</td><td><b>Citywide dragnet</b>: curfews; +2 DC to stealth/social; bounty posted.</td></tr>
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
tab_mission = ui.nav(
    "🗺️ Mission Generator",
    ui.input_radio_buttons("arc", "Archetype", ["Help the Poor","Sabotage Evil","Expose Corruption"], inline=True),
    ui.layout_columns(
        ui.card(ui.input_numeric("spend", "Gold Spent", 40, min=0, step=5), ui.input_numeric("households","Households Aided", 25, min=0, step=5), ui.input_checkbox("plan_help","Solid Plan (+1 OQM)", True), id="help_inputs"),
        ui.card(ui.input_slider("impact","Impact Level (1→5)", 1, 5, 3), ui.input_checkbox("plan_sab","Inside Contact (+1 OQM)", False), ui.input_checkbox("rushed","Rushed/Loud (−1 OQM)", False), id="sab_inputs"),
        ui.card(ui.input_slider("expose","Exposure Level (1→5)", 1, 5, 3), ui.input_checkbox("proof","Hard Proof / Magical Corroboration (+1 OQM)", False), ui.input_checkbox("reused","Reused Signature (−1 OQM)", False), id="exp_inputs"),
    ),
    ui.hr(),
    ui.h4("Execution"),
    ui.layout_columns(
        ui.input_numeric("margin","Success Margin", 2, min=0, max=20),
        ui.input_checkbox("nat20","Natural 20", False),
        ui.input_checkbox("nat1","Critical botch", False),
    ),
    ui.output_text("base_summary"),
    ui.output_text("proj_summary"),
    ui.input_action_button("queue", "Queue Mission → Resolve & Log", class_="btn btn-primary"),
)

tab_resolve = ui.nav(
    "🎯 Resolve & Log",
    ui.output_ui("queued_json"),
    ui.input_text("notes","Notes (optional)"),
    ui.input_action_button("apply", "Apply Gains & Log", class_="btn btn-primary"),
    ui.hr(),
    ui.h4("Push Log to Google Sheets"),
    ui.input_action_button("append_all", "Append All Rows to Sheets", class_="btn btn-secondary"),
    ui.output_text("append_status"),
)

tab_wheel = ui.nav(
    "☸️ Wheel of Fortune",
    ui.output_text("heat_caption"),
    ui.output_ui("wheel_ui"),
    ui.output_ui("wheel_result"),
)

tab_ledger = ui.nav(
    "📜 Ledger",
    ui.input_action_button("reload", "Refresh from Google Sheets", class_="btn btn-secondary"),
    ui.output_text("reload_status"),
    ui.output_ui("ledger_table"),
    ui.download_button("dl_csv", "Download CSV"),
)

# Top row: KPI crests + ward select + heat buttons
kpi_row = ui.layout_columns(
    ui.card(ui.output_ui("renown_badge")),
    ui.card(
        ui.output_ui("notor_badge"),
        ui.layout_columns(
            ui.input_action_button("lie_low", "Lie Low (−1/−2 Heat)"),
            ui.input_action_button("proxy_charity", "Proxy Charity (−1 Heat)"),
        )
    ),
    ui.card(ui.input_select("ward","Active Ward", choices=["Dock","Field","South","North","Castle","Trades","Sea"], selected="Dock"))
)

app_ui = ui.page_sidebar(
    sidebar,
    ui.tags.head(ui.HTML(GLOBAL_CSS)),
    ui.tags.head(ui.HTML(CREST_JS)),
    ui.div(
        ui.h2(APP_TITLE),
        kpi_row,
        ui.navset_tab(
            tab_mission, tab_resolve, tab_wheel, tab_ledger
        ),
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

    # Crest values → badges
    @output
    @render.ui
    def renown_badge():
        return crest_html("Renown", renown.get(), RENOWN_B64, "renown_badge")

    @output
    @render.ui
    def notor_badge():
        return crest_html("Notoriety", notoriety.get(), NOTOR_B64, "notor_badge")

    # Toggle tier panels via crest clicks
    @reactive.Effect
    @reactive.event(input.renown_clicked)
    def _toggle_r():
        show_renown.set(not show_renown.get())

    @reactive.Effect
    @reactive.event(input.notor_clicked)
    def _toggle_n():
        show_notor.set(not show_notor.get())

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
        # Gather inputs per arc
        arc = _arc_state()
        OQM = []
        if arc=="Help the Poor":
            BI = compute_BI(arc, {"spend": input.spend(), "households": input.households()})
            if input.plan_help(): OQM.append(+1)
        elif arc=="Sabotage Evil":
            BI = compute_BI(arc, {"impact_level": input.impact()})
            if input.plan_sab(): OQM.append(+1)
            if input.rushed():   OQM.append(-1)
        else:
            BI = compute_BI(arc, {"expose_level": input.expose()})
            if input.proof():  OQM.append(+1)
            if input.reused(): OQM.append(-1)

        EB = 3 if input.nat20() else (2 if input.margin()>=5 else (1 if input.margin()>=1 else 0))
        base_score = compute_base_score(BI, EB, OQM)
        return f"Base Impact: {BI} • EB: {EB} • OQM sum: {sum(OQM)} → Base Score: {base_score}"

    @output
    @render.text
    def proj_summary():
        arc = _arc_state()
        # recompute a minimal set consistently with base_summary
        if arc=="Help the Poor":
            BI = compute_BI(arc, {"spend": input.spend(), "households": input.households()})
            OQM = [1] if input.plan_help() else []
        elif arc=="Sabotage Evil":
            BI = compute_BI(arc, {"impact_level": input.impact()})
            OQM = ([1] if input.plan_sab() else []) + ([-1] if input.rushed() else [])
        else:
            BI = compute_BI(arc, {"expose_level": input.expose()})
            OQM = ([1] if input.proof() else []) + ([-1] if input.reused() else [])

        EB = 3 if input.nat20() else (2 if input.margin()>=5 else (1 if input.margin()>=1 else 0))
        base_score = compute_base_score(BI, EB, OQM)

        vis=input.get("vis", 1) or 1  # not exposed here; keep projection consistent with original summary control set
        noise=input.get("noise",1) or 1
        sig=input.get("sig",  0) or 0
        wit=input.get("wit",  1) or 1
        mag=input.get("mag",  0) or 0
        conc=input.get("conc",2) or 2
        mis=input.get("mis",  1) or 1
        EI = (vis+noise+sig+wit+mag)-(conc+mis)

        ren_gain = renown_from_score(base_score, arc)
        cat_base = {"Help the Poor":1,"Sabotage Evil":2,"Expose Corruption":3}[arc]
        nat1 = input.nat1()
        n20 = input.nat20()
        heat = max(0, math.ceil((cat_base + max(0,EI-1) + (1 if nat1 else 0)) * heat_multiplier(notoriety.get())))
        if n20: heat = max(0, heat-1)

        return f"Projected Renown: {ren_gain} • Projected Notoriety: {heat} • EI: {EI}"

    # Queue mission
    @reactive.Effect
    @reactive.event(input.queue)
    def _queue():
        arc = input.arc()
        if arc=="Help the Poor":
            BI = compute_BI(arc, {"spend": input.spend(), "households": input.households()})
            OQM = [1] if input.plan_help() else []
        elif arc=="Sabotage Evil":
            BI = compute_BI(arc, {"impact_level": input.impact()})
            OQM = ([1] if input.plan_sab() else []) + ([-1] if input.rushed() else [])
        else:
            BI = compute_BI(arc, {"expose_level": input.expose()})
            OQM = ([1] if input.proof() else []) + ([-1] if input.reused() else [])

        EB = 3 if input.nat20() else (2 if input.margin()>=5 else (1 if input.margin()>=1 else 0))
        base_score = compute_base_score(BI, EB, OQM)
        ren_gain = renown_from_score(base_score, arc)

        # Simplified EI controls (mirror of original defaults)
        vis=noise=1; sig=0; wit=1; mag=0; conc=2; mis=1
        cat_base = {"Help the Poor":1,"Sabotage Evil":2,"Expose Corruption":3}[arc]
        heat = max(0, math.ceil((cat_base + max(0,(vis+noise+sig+wit+mag)-(conc+mis)-1) + (1 if input.nat1() else 0)) * heat_multiplier(notoriety.get())))
        if input.nat20(): heat = max(0, heat-1)

        queued_mission.set(dict(
            ward=ward_focus.get(), archetype=arc, BI=BI, EB=EB, OQM=sum(OQM),
            renown_gain=ren_gain, notoriety_gain=heat,
            EI_breakdown=dict(visibility=vis, noise=noise, signature=sig, witnesses=wit, magic=mag, concealment=conc, misdirection=mis)
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
        renown.set(renown.get() + q["renown_gain"])
        notoriety.set(notoriety.get() + q["notoriety_gain"])

        row = [
            dt.datetime.now().isoformat(timespec="seconds"), q["ward"], q["archetype"],
            q["BI"], q["EB"], q["OQM"], q["renown_gain"], q["notoriety_gain"],
            json.dumps(q["EI_breakdown"]), input.notes() or "", ""
        ]
        df = ledger_df.get().copy()
        df.loc[len(df)] = row
        ledger_df.set(df)

        ok, err = append_rows_to_sheet([row])
        if ok:
            # pull back remote copy so totals reflect any outside edits
            remote, _ = load_ledger_from_sheet()
            if not remote.empty:
                ledger_df.set(remote)
                r = int(pd.to_numeric(remote.get("renown_gain", pd.Series()), errors="coerce").fillna(0).sum())
                n = int(pd.to_numeric(remote.get("notoriety_gain", pd.Series()), errors="coerce").fillna(0).sum())
                renown.set(r); notoriety.set(n)
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
        # Build wheel graphic
        opts = _load_options()
        wheel_options.set(opts)
        size = 600
        b64 = img_b64(draw_wheel([str(i+1) for i in range(len(opts))], size=size))

        angle = last_angle.get()
        btn_diam = max(96, int(size*0.18))
        # Wheel container with centre overlay — clicking fires JS → input.spin_clicked
        html = f"""
        <div id="wheel_wrap" style="position:relative;width:{size}px;height:{size}px;margin:0 auto;">
          <div id="pointer"></div>
          <img id="wheel_img" src="data:image/png;base64,{b64}" style="transform:rotate({angle}deg);transition:transform 3.2s cubic-bezier(.17,.67,.32,1.35);" />
          <div id="spin_overlay" style="
            position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
            width:{btn_diam}px; height:{btn_diam}px; border-radius:{btn_diam/2}px;
            border:1px solid rgba(208,168,92,0.45);
            background:linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.02));
            backdrop-filter: blur(8px) saturate(1.1);
            -webkit-backdrop-filter: blur(8px) saturate(1.1);
            box-shadow: 0 10px 30px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.06);
            color:{IVORY}; font-weight:700; letter-spacing:.5px; text-transform:uppercase;
            cursor:pointer; user-select:none; display:grid; place-items:center;">
            SPIN!
          </div>
        </div>
        """
        return ui.HTML(html)

    # Handle spin
    @reactive.Effect
    @reactive.event(input.spin_clicked)
    def _spin():
        opts = wheel_options.get()
        if not opts: return
        n = len(opts)
        idx = random.randrange(n)
        selected_index.set(idx)
        seg = 360 / n
        # add multiple full rotations for drama
        last_angle.set(random.randint(4,7)*360 + (idx + 0.5)*seg)

        # Journal it
        try:
            row = [dt.datetime.now().isoformat(timespec="seconds"),
                   ward_focus.get(), "Complication", "-", "-", "-", 0, 0, "-", "-", opts[idx]]
            df = ledger_df.get().copy()
            df.loc[len(df)] = row
            ledger_df.set(df)
        except Exception:
            pass

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
