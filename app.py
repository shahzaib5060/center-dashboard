"""
Center Repository – Live Dashboard
Chughtai Lab · Operations Excellence

Reads the "Center Repository – Master" Google Sheet live (Centers + Repository tabs),
recomputes coverage, condition and renovation priority from the raw rows, and refreshes
every 5 minutes (or on demand).

Run locally:   streamlit run app.py
"""

from __future__ import annotations

import io
import os
import re
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
SHEET_ID = "15aOUCoH0DXNfuy4Mpr_Ug5aevKI9BDkNvn2pRlDPQEE"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
REFRESH_SECONDS = 300
PKT = timezone(timedelta(hours=5))

NAVY = "#1B2A6B"
GOLD = "#F0B429"
INK = "#1F2937"
MUTED = "#6B7280"

CONDITION_LABELS = {1: "1 - Critical", 2: "2 - Poor", 3: "3 - Fair", 4: "4 - Good", 5: "5 - Excellent"}
CONDITION_COLORS = {
    "1 - Critical": "#B42318",
    "2 - Poor": "#E8590C",
    "3 - Fair": GOLD,
    "4 - Good": "#5B6BB0",
    "5 - Excellent": NAVY,
}
MODEL_COLORS = {"Older V6": "#B42318", "V6": GOLD, "V7": NAVY}
BAND_ORDER = ["Urgent", "High", "Medium", "Low"]
BAND_COLORS = {"Urgent": "#B42318", "High": "#E8590C", "Medium": GOLD, "Low": "#5B6BB0"}

# Keyword themes for the free-text "Key Issues" column
ISSUE_THEMES = {
    "Paint": r"paint|painr|colou?r|repaint|wall work",
    "Seepage / damp": r"seepage|saime|damp|leak|demak|crack",
    "Signboard / logo": r"sign\s?board|signboard|flex|skin|face\s?board|logo|pole board|tapa",
    "Ceiling": r"ceiling|celling|cieling|seiling|roof",
    "Floor / tiles": r"tile|tails|floor|farsh",
    "Washroom": r"washroom|wash room|w\.c\b|commode|toilet|sanitary|saintory|mirror",
    "Furniture / counter": r"sofa|chair|furniture|ferniture|seater|bench|table|counter|poshish|rack",
    "Cooling / AC": r"\bac\b|air condition|temperature|refrigerator|exhaust|fan",
    "Lighting / electrical": r"light|electric|voltage",
    "Space / relocation": r"space|congested|small|relocat|change location|store.*small|waiting area",
    "Doors / glass / shutter": r"door|glass|shutter",
    "Awning / shade": r"awning|owning|tarpaal|shed",
    "Full renovation / V7 upgrade": r"renovat|refurbish|upgrade|convert|\bv7\b|m-7|complete work|overall",
}
NO_ISSUE = re.compile(
    r"^\s*(no|none|nil|ok|good|fair|no issues?( observed| at all)?|no any (other )?issues?|"
    r"no more issue|all ok|everything is okay|no need to renovation|"
    r"centre is in good condition|center condition is satisfactory\.?)\W*$",
    re.I,
)

# ─────────────────────────────────────────────────────────────────────────────
# Page setup + styling
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Center Repository Dashboard", page_icon="🏥", layout="wide")

st.markdown(
    f"""
<style>
  .block-container {{ padding-top: 1.4rem; padding-bottom: 2rem; }}
  .cl-header {{ background: {NAVY}; color: white; padding: 18px 22px; border-radius: 10px;
               border-bottom: 4px solid {GOLD}; margin-bottom: 14px; }}
  .cl-header h1 {{ color: white; font-size: 1.55rem; margin: 0; font-weight: 700; }}
  .cl-header p  {{ color: #D6DBF0; margin: 4px 0 0 0; font-size: .9rem; }}
  .kpi {{ background: white; border: 1px solid #E5E7EB; border-left: 5px solid {NAVY};
          border-radius: 8px; padding: 12px 14px; height: 100%; }}
  .kpi.gold {{ border-left-color: {GOLD}; }}
  .kpi.red  {{ border-left-color: #B42318; }}
  .kpi .lbl {{ color: {MUTED}; font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; }}
  .kpi .val {{ color: {INK}; font-size: 1.7rem; font-weight: 700; line-height: 1.2; }}
  .kpi .sub {{ color: {MUTED}; font-size: .8rem; }}
  .note {{ color: {MUTED}; font-size: .85rem; }}
  div[data-testid="stTabs"] button p {{ font-weight: 600; }}
</style>
""",
    unsafe_allow_html=True,
)

px.defaults.template = "plotly_white"


def secret(key, default=None):
    """Read a Streamlit secret without crashing when no secrets file exists."""
    try:
        return st.secrets[key] if key in st.secrets else default
    except Exception:  # noqa: BLE001
        return default



# ─────────────────────────────────────────────────────────────────────────────
# Login
#   Users live in Streamlit Secrets, never in the code:
#       [users]
#       shahzaib = "StrongPassword1"
#       amber    = "AnotherPassword2"
#   If no [users] section exists, the dashboard stays locked.
# ─────────────────────────────────────────────────────────────────────────────
MAX_ATTEMPTS = 5


def check_login() -> bool:
    import hmac

    if st.session_state.get("auth_user"):
        return True

    users = dict(secret("users", {}) or {})

    st.markdown(
        f"""<div class="cl-header" style="max-width:460px;margin:60px auto 18px auto;text-align:center">
        <h1>Center Repository</h1><p>Chughtai Lab · Operations Excellence</p></div>""",
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        if not users:
            st.error("No users are set up yet. Add a [users] section in the app's Secrets.")
            return False
        attempts = st.session_state.get("auth_attempts", 0)
        if attempts >= MAX_ATTEMPTS:
            st.error("Too many wrong attempts. Close this tab and try again later.")
            return False
        with st.form("login"):
            u = st.text_input("Username").strip().lower()
            p = st.text_input("Password", type="password")
            ok = st.form_submit_button("Log in", width="stretch", type="primary")
        if ok:
            expected = {k.lower(): str(v) for k, v in users.items()}.get(u)
            if expected is not None and hmac.compare_digest(p.encode(), expected.encode()):
                st.session_state["auth_user"] = u
                st.session_state.pop("auth_attempts", None)
                st.rerun()
            else:
                st.session_state["auth_attempts"] = attempts + 1
                left = MAX_ATTEMPTS - attempts - 1
                st.error(f"Wrong username or password. {left} attempt(s) left.")
    return False


if not check_login():
    st.stop()


def style_fig(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=40, b=60),
        font=dict(family="Segoe UI, Arial, sans-serif", color=INK, size=12),
        title_font=dict(size=15, color=NAVY),
        legend=dict(orientation="h", yanchor="top", y=-0.06, xanchor="left", x=0, title=None),
        plot_bgcolor="white",
    )
    fig.update_xaxes(gridcolor="#EEF0F4")
    fig.update_yaxes(gridcolor="#EEF0F4")
    return fig


def kpi(col, label, value, sub="", tone=""):
    col.markdown(
        f'<div class="kpi {tone}"><div class="lbl">{label}</div>'
        f'<div class="val">{value}</div><div class="sub">{sub}</div></div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Data loading (three sources, tried in order)
# ─────────────────────────────────────────────────────────────────────────────
def _frame_from_values(values: list[list[str]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    header = [h.strip() for h in values[0]]
    rows = [r + [""] * (len(header) - len(r)) for r in values[1:]]
    df = pd.DataFrame(rows, columns=header)
    return df


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Reading the live sheet…")
def load_from_google() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Live read. Uses a service account if configured, else the public CSV export."""
    if secret("gcp_json") or secret("gcp_service_account"):
        import json
        import gspread

        if secret("gcp_json"):  # whole JSON key pasted as one block
            creds = json.loads(secret("gcp_json"))
        else:
            creds = dict(secret("gcp_service_account"))
        gc = gspread.service_account_from_dict(creds)
        sh = gc.open_by_key(secret("sheet_id", SHEET_ID))
        centers = _frame_from_values(sh.worksheet("Centers").get_all_values())
        repo = _frame_from_values(sh.worksheet("Repository").get_all_values())
        return centers, repo, "Google Sheet (service account)"

    base = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet="
    centers = pd.read_csv(base + "Centers", dtype=str, keep_default_na=False)
    repo = pd.read_csv(base + "Repository", dtype=str, keep_default_na=False)
    return centers, repo, "Google Sheet (link sharing)"


def load_from_upload(file) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    xl = pd.ExcelFile(file)
    centers = pd.read_excel(xl, "Centers", dtype=str, keep_default_na=False)
    repo = pd.read_excel(xl, "Repository", dtype=str, keep_default_na=False)
    return centers, repo, f"Uploaded file ({getattr(file, 'name', 'workbook')})"


# ─────────────────────────────────────────────────────────────────────────────
# Cleaning + derived fields
# ─────────────────────────────────────────────────────────────────────────────
def clean_code(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.replace(r"\.0$", "", regex=True)


def clean_reno_year(value, ref_year: int) -> tuple[float, str]:
    """Return (year or NaN, problem). Problem is '' when the entry is a usable year."""
    s = str(value).strip()
    if s in ("", "nan", "None"):
        return np.nan, "Blank"
    m = re.fullmatch(r"(\d{4})(\.0+)?", s)
    if m:
        y = int(m.group(1))
        if 2000 <= y <= ref_year:
            return y, ""
        return np.nan, "Future year" if y > ref_year else "Implausible year"
    m = re.fullmatch(r"(\d{1,2})[./-](\d{4})", s)  # month.year e.g. 8.2023
    if m:
        y = int(m.group(2))
        if 2000 <= y <= ref_year:
            return y, "Month.year format"
        return np.nan, "Future year" if y > ref_year else "Implausible year"
    if re.fullmatch(r"-?\d{1,2}", s):
        return np.nan, "Years-ago / short number"
    return np.nan, "Unreadable"


def tag_issues(text: str) -> list[str]:
    t = str(text).strip()
    low = t.lower()
    if (not t or NO_ISSUE.match(t)
            or (len(t) < 90 and re.search(r"no issu|new(ly)? (opened|cent)|recently new", low))):
        return []
    tags = [name for name, pat in ISSUE_THEMES.items() if re.search(pat, low)]
    return tags or ["Other"]


def prepare(centers_raw: pd.DataFrame, repo_raw: pd.DataFrame):
    centers = centers_raw.copy()
    centers.columns = [c.strip() for c in centers.columns]
    centers = centers[centers["Center Code"].astype(str).str.strip() != ""]
    centers["Center Code"] = clean_code(centers["Center Code"])
    centers["In Survey"] = centers["In Survey"].str.strip().str.lower().eq("yes")

    repo = repo_raw.copy()
    cols = list(repo.columns)
    cols[0] = "Timestamp"  # first header is blank in the sheet
    repo.columns = [c.strip() for c in cols]
    repo = repo[repo["Center Code"].astype(str).str.strip() != ""]
    repo["Center Code"] = clean_code(repo["Center Code"])
    repo["Timestamp"] = pd.to_datetime(repo["Timestamp"], errors="coerce")
    repo["Condition"] = pd.to_numeric(repo["Condition (1-5)"].str[:1], errors="coerce")
    repo["Photos Uploaded"] = pd.to_numeric(repo["Photos Uploaded"], errors="coerce").fillna(0).astype(int)
    repo["Times Submitted"] = pd.to_numeric(repo["Times Submitted"], errors="coerce").fillna(1).astype(int)

    ref_year = datetime.now(PKT).year
    yr = repo["Last Renovation (Year)"].apply(lambda v: clean_reno_year(v, ref_year))
    repo["Reno Year"] = [a for a, _ in yr]
    repo["Reno Problem"] = [b for _, b in yr]

    sb = repo["Signboard Condition"].fillna("").str.lower()
    repo["Signboard Issues"] = sb.apply(
        lambda s: [x.strip().title() for x in s.split(",") if x.strip() and x.strip() != "good"]
    )
    repo["Signboard Needs Work"] = repo["Signboard Issues"].str.len() > 0
    repo["No Back-lit Logo"] = repo["Back-lit Logo (Reception)"].str.strip().str.lower().eq("no")
    repo["Issue Themes"] = repo["Key Issues"].apply(tag_issues)

    # One row per center: latest submission wins
    latest = repo.sort_values("Timestamp").drop_duplicates("Center Code", keep="last")

    survey = centers[centers["In Survey"]].copy()
    keep = [
        "Center Code", "Timestamp", "Submitted By", "Model", "Reception Position", "Layout Type",
        "Back-lit Logo (Reception)", "Signboard Condition", "Last Renovation (Year)", "Condition",
        "Key Issues", "Photo Folder", "Photos Uploaded", "Times Submitted", "Reno Year",
        "Reno Problem", "Signboard Issues", "Signboard Needs Work", "No Back-lit Logo", "Issue Themes",
    ]
    merged = survey.merge(
        latest[keep].rename(columns={"Photo Folder": "Photo Link"}), on="Center Code", how="left"
    )
    merged["Surveyed"] = merged["Timestamp"].notna()
    merged["Condition Label"] = merged["Condition"].map(CONDITION_LABELS)

    # Renovation priority score (0–100)
    s = merged
    cond_pts = ((5 - s["Condition"]) / 4 * 50).fillna(0)
    model_pts = s["Model"].map({"Older V6": 20, "V6": 10, "V7": 0}).fillna(0)
    sign_pts = (s["Signboard Issues"].apply(lambda x: len(x) if isinstance(x, list) else 0).clip(0, 3) / 3 * 15)
    logo_pts = s["No Back-lit Logo"].fillna(False).astype(int) * 5
    age = (ref_year - s["Reno Year"]).clip(lower=0, upper=8)
    age_pts = (age / 8 * 10).fillna(5)
    s["Priority Score"] = (cond_pts + model_pts + sign_pts + logo_pts + age_pts).round(0)
    s.loc[~s["Surveyed"], "Priority Score"] = np.nan
    s["Priority Band"] = pd.cut(
        s["Priority Score"], bins=[-1, 30, 45, 60, 101], labels=["Low", "Medium", "High", "Urgent"]
    ).astype(object)

    orphans = repo[~repo["Center Code"].isin(centers["Center Code"])]
    return merged, repo, orphans


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar: source + filters
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"<h3 style='color:{NAVY};margin-bottom:0'>Center Repository</h3>", unsafe_allow_html=True)
    st.caption("Chughtai Lab · Operations Excellence")

    if st.button("🔄 Refresh now", width="stretch"):
        st.cache_data.clear()
        st.rerun()

source_error = None
try:
    if os.environ.get("CENTER_REPO_XLSX"):  # optional: point at a local export
        centers_raw, repo_raw, source = load_from_upload(os.environ["CENTER_REPO_XLSX"])
    else:
        centers_raw, repo_raw, source = load_from_google()
except Exception as e:  # noqa: BLE001
    source_error = e
    centers_raw = repo_raw = None

if source_error is not None or centers_raw is None:
    st.error(
        "Couldn't read the Google Sheet. Check that the service-account key is in the app's Secrets "
        "and that the sheet is shared with the service-account email as Viewer, then click Refresh now."
        f"\n\nDetails: `{source_error}`"
    )
    st.stop()

data, repo_all, orphans = prepare(centers_raw, repo_raw)
loaded_at = datetime.now(PKT).strftime("%d %b %Y, %I:%M %p")

with st.sidebar:
    st.divider()
    st.markdown("**Filters**")
    regions = sorted(data["Region"].dropna().unique())
    f_region = st.multiselect("Region", regions)
    pool = data[data["Region"].isin(f_region)] if f_region else data
    f_rl = st.multiselect("Regional Lead", sorted(pool["Regional Lead"].dropna().unique()))
    pool = pool[pool["Regional Lead"].isin(f_rl)] if f_rl else pool
    f_al = st.multiselect("Area Lead", sorted(pool["Area Lead"].dropna().unique()))
    f_model = st.multiselect("Model", ["Older V6", "V6", "V7"])
    f_cond = st.multiselect("Condition", list(CONDITION_LABELS.values()))
    st.divider()
    st.caption(f"👤 Logged in as **{st.session_state['auth_user']}**")
    if st.button("Log out", width="stretch"):
        st.session_state.pop("auth_user", None)
        st.rerun()
    st.caption(f"Source: {source}")
    st.caption(f"Loaded: {loaded_at} PKT · auto-refresh every {REFRESH_SECONDS // 60} min")
    st.markdown(f"[Open the sheet ↗]({SHEET_URL})")

df = data.copy()
if f_region:
    df = df[df["Region"].isin(f_region)]
if f_rl:
    df = df[df["Regional Lead"].isin(f_rl)]
if f_al:
    df = df[df["Area Lead"].isin(f_al)]
if f_model:
    df = df[df["Model"].isin(f_model) | ~df["Surveyed"]]
if f_cond:
    df = df[df["Condition Label"].isin(f_cond) | ~df["Surveyed"]]

sv = df[df["Surveyed"]]

# ─────────────────────────────────────────────────────────────────────────────
# Header + KPIs
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(
    f"""<div class="cl-header"><h1>Center Repository — Renovation Readiness</h1>
    <p>Live view of the network center survey · {len(df)} centers in scope · updated {loaded_at} PKT</p></div>""",
    unsafe_allow_html=True,
)

total, done = len(df), int(df["Surveyed"].sum())
cov = done / total * 100 if total else 0
poor = int((sv["Condition"] <= 2).sum())
avg_c = sv["Condition"].mean()
v7 = (sv["Model"] == "V7").mean() * 100 if len(sv) else 0
older = int((sv["Model"] == "Older V6").sum())
signw = int(sv["Signboard Needs Work"].sum())
nologo = int(sv["No Back-lit Logo"].sum())
urgent = int((sv["Priority Band"] == "Urgent").sum())

c = st.columns(4)
kpi(c[0], "Survey coverage", f"{cov:.0f}%", f"{done} of {total} centers · {total - done} pending")
kpi(c[1], "Average condition", f"{avg_c:.2f} / 5" if len(sv) else "–", f"{poor} centers rated Poor or Critical", "red" if poor else "")
kpi(c[2], "Urgent renovation", f"{urgent}", "priority score ≥ 60", "red" if urgent else "")
kpi(c[3], "V7 model share", f"{v7:.0f}%", f"{older} still on Older V6", "gold")
st.write("")
c = st.columns(4)
kpi(c[0], "Signboard needs work", f"{signw}", f"{signw / len(sv) * 100:.0f}% of surveyed" if len(sv) else "", "gold")
kpi(c[1], "No back-lit logo", f"{nologo}", "at reception", "gold")
kpi(c[2], "Photos collected", f"{int(sv['Photos Uploaded'].sum()):,}", f"avg {sv['Photos Uploaded'].mean():.1f} per center" if len(sv) else "")
kpi(c[3], "Re-submissions", f"{int((sv['Times Submitted'] > 1).sum())}", "centers submitted more than once")
st.write("")

tabs = st.tabs(["📊 Overview", "🛠️ Renovation Priority", "🔎 Issues", "📋 Survey Tracker", "⚠️ Data Quality", "🏥 Center Lookup"])

# ─────────────────────────────────────────────────────────────────────────────
# 1. Overview
# ─────────────────────────────────────────────────────────────────────────────
with tabs[0]:
    reg = (
        df.groupby("Region")
        .agg(Centers=("Center Code", "size"), Surveyed=("Surveyed", "sum"))
        .assign(Pending=lambda x: x.Centers - x.Surveyed, Coverage=lambda x: x.Surveyed / x.Centers * 100)
        .reset_index()
    )
    regc = sv.groupby("Region").agg(
        Avg=("Condition", "mean"), Poor=("Condition", lambda x: (x <= 2).sum())
    ).reset_index()
    reg = reg.merge(regc, on="Region", how="left")

    l, r = st.columns(2)
    with l:
        rr = reg.sort_values(["Coverage", "Pending"], ascending=[False, True])  # least covered on top
        fig = go.Figure()
        fig.add_bar(y=rr.Region, x=rr.Surveyed, name="Surveyed", orientation="h", marker_color=NAVY)
        fig.add_bar(y=rr.Region, x=rr.Pending, name="Pending", orientation="h", marker_color=GOLD,
                    text=[f"{c:.0f}%" if p else "" for c, p in zip(rr.Coverage, rr.Pending)],
                    textposition="outside")
        fig.update_layout(barmode="stack", title="Survey coverage by region (least covered on top)")
        st.plotly_chart(style_fig(fig, 30 * len(rr) + 120), width="stretch")
    with r:
        mix = (
            sv.groupby(["Region", "Condition Label"]).size().reset_index(name="n")
            .merge(reg[["Region", "Avg"]], on="Region")
        )
        mix["share"] = mix.n / mix.groupby("Region").n.transform("sum") * 100
        order = reg.sort_values("Avg", ascending=False).Region.tolist()
        fig = px.bar(
            mix, y="Region", x="share", color="Condition Label", orientation="h",
            category_orders={"Region": order, "Condition Label": list(CONDITION_LABELS.values())},
            color_discrete_map=CONDITION_COLORS, title="Condition mix by region (worst average at bottom)",
            hover_data={"n": True, "share": ":.0f"},
        )
        fig.update_xaxes(title="% of surveyed centers", range=[0, 100])
        fig.update_yaxes(title=None)
        st.plotly_chart(style_fig(fig, 30 * len(order) + 120), width="stretch")

    l, m, r = st.columns(3)
    with l:
        mc = sv["Model"].value_counts().reindex(["Older V6", "V6", "V7"]).fillna(0).reset_index()
        mc.columns = ["Model", "Centers"]
        fig = px.bar(mc, x="Model", y="Centers", color="Model", color_discrete_map=MODEL_COLORS,
                     text="Centers", title="Model mix")
        fig.update_layout(showlegend=False)
        st.plotly_chart(style_fig(fig, 320), width="stretch")
    with m:
        lc = sv["Layout Type"].value_counts().reset_index()
        lc.columns = ["Layout", "Centers"]
        fig = px.bar(lc.sort_values("Centers"), y="Layout", x="Centers", orientation="h", text="Centers",
                     title="Layout type", color_discrete_sequence=[NAVY])
        st.plotly_chart(style_fig(fig, 320), width="stretch")
    with r:
        cc = sv["Condition Label"].value_counts().reindex(list(CONDITION_LABELS.values())).fillna(0).reset_index()
        cc.columns = ["Condition", "Centers"]
        fig = px.bar(cc, x="Condition", y="Centers", color="Condition", color_discrete_map=CONDITION_COLORS,
                     text="Centers", title="Condition rating")
        fig.update_layout(showlegend=False)
        st.plotly_chart(style_fig(fig, 320), width="stretch")

    st.markdown("##### Region scorecard")
    sign_r = sv.groupby("Region").agg(
        Signboard=("Signboard Needs Work", "sum"), NoLogo=("No Back-lit Logo", "sum"),
        OlderV6=("Model", lambda x: (x == "Older V6").sum()), V7=("Model", lambda x: (x == "V7").sum()),
        Urgent=("Priority Band", lambda x: (x == "Urgent").sum()),
    ).reset_index()
    card = reg.merge(sign_r, on="Region", how="left").sort_values("Avg")
    st.dataframe(
        card[["Region", "Centers", "Surveyed", "Coverage", "Avg", "Poor", "Urgent", "OlderV6", "V7", "Signboard", "NoLogo"]],
        hide_index=True, width="stretch",
        column_config={
            "Coverage": st.column_config.ProgressColumn("Coverage", format="%.0f%%", min_value=0, max_value=100),
            "Avg": st.column_config.NumberColumn("Avg condition", format="%.2f"),
            "Poor": "Poor/Critical", "OlderV6": "Older V6", "Signboard": "Signboard work", "NoLogo": "No back-lit logo",
        },
    )

# ─────────────────────────────────────────────────────────────────────────────
# 2. Renovation priority
# ─────────────────────────────────────────────────────────────────────────────
with tabs[1]:
    with st.expander("How the priority score works (0–100)"):
        st.markdown(
            "- **Condition** – up to 50 pts (Critical = 50, Excellent = 0)\n"
            "- **Model** – Older V6 = 20, V6 = 10, V7 = 0\n"
            "- **Signboard** – up to 15 pts (5 per issue: rough / skin change / lights dim)\n"
            "- **No back-lit logo** – 5 pts\n"
            "- **Years since renovation** – up to 10 pts (8+ years = 10; unknown year = 5)\n\n"
            "Bands: **Urgent ≥ 60**, High 45–59, Medium 31–44, Low ≤ 30."
        )
    l, r = st.columns([1, 2])
    with l:
        bc = sv["Priority Band"].value_counts().reindex(BAND_ORDER).fillna(0).reset_index()
        bc.columns = ["Band", "Centers"]
        fig = px.bar(bc, x="Band", y="Centers", color="Band", color_discrete_map=BAND_COLORS, text="Centers",
                     title="Centers by priority band")
        fig.update_layout(showlegend=False)
        st.plotly_chart(style_fig(fig, 340), width="stretch")
    with r:
        hb = sv.groupby(["Region", "Priority Band"]).size().unstack(fill_value=0).reindex(columns=BAND_ORDER, fill_value=0)
        hb = hb.sort_values(["Urgent", "High"], ascending=True)
        fig = go.Figure()
        for b in BAND_ORDER:
            fig.add_bar(y=hb.index, x=hb[b], name=b, orientation="h", marker_color=BAND_COLORS[b])
        fig.update_layout(barmode="stack", title="Priority mix by region")
        st.plotly_chart(style_fig(fig, max(340, 26 * len(hb) + 120)), width="stretch")

    bands = st.multiselect("Show bands", BAND_ORDER, default=["Urgent", "High"])
    pr = sv[sv["Priority Band"].isin(bands)] if bands else sv
    pr = pr.sort_values(["Priority Score", "Condition"], ascending=[False, True])
    show = pr[[
        "Priority Score", "Priority Band", "Center Code", "Center Name", "Region", "Area Lead", "Model",
        "Condition Label", "Signboard Condition", "Back-lit Logo (Reception)", "Last Renovation (Year)",
        "Key Issues", "Photo Link",
    ]]
    st.dataframe(
        show, hide_index=True, width="stretch", height=520,
        column_config={
            "Priority Score": st.column_config.ProgressColumn("Score", format="%d", min_value=0, max_value=100),
            "Photo Link": st.column_config.LinkColumn("Photos", display_text="Open ↗"),
            "Condition Label": "Condition", "Back-lit Logo (Reception)": "Back-lit logo",
            "Last Renovation (Year)": "Last reno (as entered)",
            "Key Issues": st.column_config.TextColumn("Key issues", width="large"),
        },
    )
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as xw:
        show.to_excel(xw, sheet_name="Renovation Priority", index=False)
    st.download_button("⬇️ Download this list (Excel)", out.getvalue(), "renovation_priority.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Issues
# ─────────────────────────────────────────────────────────────────────────────
with tabs[2]:
    ex = sv[["Center Code", "Center Name", "Region", "Area Lead", "Condition Label", "Key Issues", "Issue Themes"]].explode("Issue Themes")
    ex = ex.dropna(subset=["Issue Themes"])
    reported = sv["Issue Themes"].str.len().gt(0).sum()
    st.caption(
        f"{reported} of {len(sv)} surveyed centers reported at least one issue. Themes are picked up from "
        "keywords in the free-text *Key Issues* field, so one comment can count under several themes."
    )
    l, r = st.columns([1, 1.4])
    with l:
        tc = ex["Issue Themes"].value_counts().reset_index()
        tc.columns = ["Theme", "Centers"]
        fig = px.bar(tc.sort_values("Centers"), y="Theme", x="Centers", orientation="h", text="Centers",
                     title="What centers are reporting", color_discrete_sequence=[NAVY])
        st.plotly_chart(style_fig(fig, 30 * len(tc) + 120), width="stretch")
    with r:
        hm = ex.groupby(["Region", "Issue Themes"]).size().unstack(fill_value=0)
        if not hm.empty:
            hm = hm[tc["Theme"].tolist()]
            fig = px.imshow(hm, text_auto=True, aspect="auto", color_continuous_scale=["#FFFFFF", GOLD, NAVY],
                            title="Issue themes by region")
            fig.update_layout(coloraxis_showscale=False)
            fig.update_xaxes(tickangle=-35, title=None)
            fig.update_yaxes(title=None)
            st.plotly_chart(style_fig(fig, max(380, 24 * len(hm) + 160)), width="stretch")

    theme = st.selectbox("Read the comments for a theme", ["All"] + tc["Theme"].tolist())
    q = st.text_input("Search comments", placeholder="e.g. seepage, sofa, AC")
    lst = sv[sv["Key Issues"].fillna("").str.strip() != ""].copy()
    if theme != "All":
        lst = lst[lst["Issue Themes"].apply(lambda t: theme in t)]
    if q:
        lst = lst[lst["Key Issues"].str.contains(q, case=False, na=False)]
    lst["Themes"] = lst["Issue Themes"].apply(", ".join)
    st.dataframe(
        lst[["Center Code", "Center Name", "Region", "Area Lead", "Condition Label", "Themes", "Key Issues"]],
        hide_index=True, width="stretch", height=440,
        column_config={"Key Issues": st.column_config.TextColumn("Key issues", width="large"), "Condition Label": "Condition"},
    )

# ─────────────────────────────────────────────────────────────────────────────
# 4. Survey tracker
# ─────────────────────────────────────────────────────────────────────────────
with tabs[3]:
    al = (
        df.groupby(["Area Lead", "Region"])
        .agg(Assigned=("Center Code", "size"), Surveyed=("Surveyed", "sum"))
        .assign(Pending=lambda x: x.Assigned - x.Surveyed, Coverage=lambda x: x.Surveyed / x.Assigned * 100)
        .reset_index()
        .sort_values(["Coverage", "Pending"], ascending=[True, False])
    )
    l, r = st.columns([1.1, 1])
    with l:
        st.markdown("##### Area lead coverage")
        st.dataframe(
            al, hide_index=True, width="stretch", height=480,
            column_config={"Coverage": st.column_config.ProgressColumn("Coverage", format="%.0f%%", min_value=0, max_value=100)},
        )
    with r:
        pend = df[~df["Surveyed"]][["Center Code", "Center Name", "Region", "City", "Area Lead", "Regional Lead", "Survey Status"]]
        st.markdown(f"##### Pending centers ({len(pend)})")
        if pend.empty:
            st.success("Every center in scope has been surveyed.")
        else:
            st.dataframe(pend, hide_index=True, width="stretch", height=480)

    daily = repo_all.dropna(subset=["Timestamp"]).copy()
    if f_region:
        daily = daily[daily["Region"].isin(f_region)]
    daily["Day"] = daily["Timestamp"].dt.date
    dd = daily.groupby("Day").size().reset_index(name="Submissions")
    dd["Cumulative"] = dd["Submissions"].cumsum()
    fig = go.Figure()
    fig.add_bar(x=dd.Day, y=dd.Submissions, name="Per day", marker_color=GOLD)
    fig.add_scatter(x=dd.Day, y=dd.Cumulative, name="Cumulative", mode="lines+markers", line=dict(color=NAVY, width=3), yaxis="y2")
    fig.update_layout(title="Submissions over time", yaxis2=dict(overlaying="y", side="right", showgrid=False))
    st.plotly_chart(style_fig(fig, 320), width="stretch")

# ─────────────────────────────────────────────────────────────────────────────
# 5. Data quality
# ─────────────────────────────────────────────────────────────────────────────
with tabs[4]:
    st.caption("Things in the sheet that will distort the numbers above until they are fixed at source.")
    bad_year = sv[sv["Reno Problem"].isin(["Future year", "Implausible year", "Years-ago / short number", "Unreadable"])]
    blank_year = sv[sv["Reno Problem"] == "Blank"]
    low_photos = sv[sv["Photos Uploaded"] < 4]
    no_link = sv[~sv["Photo Link"].fillna("").str.startswith("http")]
    c = st.columns(4)
    kpi(c[0], "Unusable renovation year", len(bad_year), "e.g. 0, 1, -4, 22025, 2027", "red" if len(bad_year) else "")
    kpi(c[1], "Renovation year blank", len(blank_year), "left empty on the form", "gold")
    kpi(c[2], "Codes not in Centers tab", len(orphans), "submissions that don't match the master list", "red" if len(orphans) else "")
    kpi(c[3], "Missing photo folder link", len(no_link), "", "red" if len(no_link) else "")
    st.write("")

    st.markdown("##### Renovation year entries that can't be read as a year")
    st.dataframe(
        bad_year[["Center Code", "Center Name", "Region", "Area Lead", "Submitted By", "Last Renovation (Year)", "Reno Problem"]]
        .rename(columns={"Last Renovation (Year)": "Entered", "Reno Problem": "Problem"}),
        hide_index=True, width="stretch",
    )
    l, r = st.columns(2)
    with l:
        st.markdown("##### Submitted more than once (latest version used)")
        st.dataframe(sv[sv["Times Submitted"] > 1][["Center Code", "Center Name", "Region", "Times Submitted", "Submitted By"]],
                     hide_index=True, width="stretch")
    with r:
        st.markdown("##### Codes in Repository but not in Centers")
        st.dataframe(orphans[["Center Code", "Center Name", "Region", "Submitted By"]], hide_index=True, width="stretch")
    if len(no_link):
        st.markdown("##### Missing photo folder link")
        st.dataframe(no_link[["Center Code", "Center Name", "Region", "Area Lead", "Photos Uploaded"]], hide_index=True, width="stretch")

# ─────────────────────────────────────────────────────────────────────────────
# 6. Center lookup
# ─────────────────────────────────────────────────────────────────────────────
with tabs[5]:
    opts = (df["Center Code"] + " · " + df["Center Name"]).tolist()
    pick = st.selectbox("Find a center", opts, index=None, placeholder="Type a code or name…")
    if pick:
        row = df[df["Center Code"] == pick.split(" · ")[0]].iloc[0]
        st.markdown(f"### {row['Center Name']}  \n<span class='note'>{row['Center Code']} · {row['City']} · {row['Region']}</span>", unsafe_allow_html=True)
        if not row["Surveyed"]:
            st.warning(f"Not surveyed yet. Area lead: **{row['Area Lead']}** · Regional lead: **{row['Regional Lead']}**")
        else:
            c = st.columns(4)
            kpi(c[0], "Condition", row["Condition Label"] or "–", "")
            kpi(c[1], "Model / layout", row["Layout Type"], f"Reception: {row['Reception Position']}", "gold")
            kpi(c[2], "Priority", f"{row['Priority Score']:.0f}", row["Priority Band"], "red" if row["Priority Band"] == "Urgent" else "")
            kpi(c[3], "Photos", int(row["Photos Uploaded"]), f"submitted {int(row['Times Submitted'])}×")
            st.write("")
            st.markdown(
                f"**Area lead:** {row['Area Lead']} · **Regional lead:** {row['Regional Lead']}  \n"
                f"**Signboard:** {row['Signboard Condition']} · **Back-lit logo:** {row['Back-lit Logo (Reception)']} · "
                f"**Last renovation (as entered):** {row['Last Renovation (Year)'] or '–'}  \n"
                f"**Submitted by:** {row['Submitted By']} on {row['Timestamp']:%d %b %Y %I:%M %p}"
            )
            st.info(row["Key Issues"] or "No issues reported.")
            if str(row["Photo Link"]).startswith("http"):
                st.link_button("📷 Open photo folder", row["Photo Link"])
