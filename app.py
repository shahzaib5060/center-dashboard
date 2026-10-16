"""
Center Repository – Live Dashboard
Chughtai Lab · Operations Excellence

Reads the "Center Repository – Master" Google Sheet live (Centers + Repository tabs),
scores every centre, and shows index.html full-width with that data — the same layout
as the Centre Agreements dashboard. Refreshes every 5 minutes, or with "Refresh data".

Files needed in the repo:  app.py · index.html · requirements.txt
Run locally:               streamlit run app.py
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

BASE = Path(__file__).parent

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
SHEET_ID = "15aOUCoH0DXNfuy4Mpr_Ug5aevKI9BDkNvn2pRlDPQEE"
REFRESH_SECONDS = 300
PKT = timezone(timedelta(hours=5))
PAGE_HEIGHT = 1700          # height of the dashboard frame in pixels
MAX_ATTEMPTS = 5

CONDITION_LABELS = {1: "1 - Critical", 2: "2 - Poor", 3: "3 - Fair", 4: "4 - Good", 5: "5 - Excellent"}

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
# Page setup — same look as the Centre Agreements dashboard
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Center Repository Dashboard", page_icon="🏥", layout="wide")
st.markdown(
    """<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"], .stApp { font-family: 'Inter', system-ui, sans-serif; }
    .block-container {padding: 0 !important; max-width: 100% !important;}
    header[data-testid="stHeader"] {display: none;}
    #MainMenu, footer {visibility: hidden;}
    iframe {display: block;}
    /* login card */
    .lg-brand {max-width: 400px; margin: 9vh auto 14px auto; text-align: center;}
    .lg-brand .lg-mark {width: 44px; height: 44px; border-radius: 12px; background: rgba(79,70,229,.10); color: #4F46E5;
        display: inline-flex; align-items: center; justify-content: center; font-weight: 700; font-size: 18px; margin-bottom: 10px;}
    .lg-brand h1 {font-size: 22px; font-weight: 600; margin: 0; color: #0F172A; letter-spacing: -.01em;}
    .lg-brand p {font-size: 13px; color: #64748B; margin: 4px 0 0 0;}
    div[data-testid="stForm"] {background: #fff; border: 1px solid #E5E7EB; border-radius: 14px; padding: 22px 22px 8px 22px;}
    .stFormSubmitButton button, .stButton button[kind="primary"] {background: #4F46E5 !important; border-color: #4F46E5 !important; color: #fff !important; border-radius: 10px !important;}
    /* thin bar above the dashboard */
    .tb-user {font-size: 12.5px; color: #64748B; padding-top: 9px; text-align: right;}
    .tb-user b {color: #0F172A; font-weight: 600;}
    div[data-testid="stHorizontalBlock"] .stButton button {font-size: 12.5px; padding: 2px 12px; min-height: 30px; border-radius: 10px; border: 1px solid #E5E7EB;}
    </style>""",
    unsafe_allow_html=True,
)


def secret(key, default=None):
    """Read a Streamlit secret without crashing when no secrets file exists."""
    try:
        return st.secrets[key] if key in st.secrets else default
    except Exception:  # noqa: BLE001
        return default


# ─────────────────────────────────────────────────────────────────────────────
# Login — users live in Streamlit Secrets:
#   [users]
#   shahzaib = "StrongPassword1"
# ─────────────────────────────────────────────────────────────────────────────
def check_login() -> bool:
    import hmac

    if st.session_state.get("auth_user"):
        return True
    users = dict(secret("users", {}) or {})
    st.markdown(
        '<div class="lg-brand"><div class="lg-mark">CR</div><h1>Center Repository</h1>'
        "<p>Chughtai Lab · Operations Excellence</p></div>",
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1, 1])
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
                st.error(f"Wrong username or password. {MAX_ATTEMPTS - attempts - 1} attempt(s) left.")
    return False


if not check_login():
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────────────────────────────────────
def _frame_from_values(values: list[list[str]]) -> pd.DataFrame:
    if not values:
        return pd.DataFrame()
    header = [h.strip() for h in values[0]]
    rows = [r + [""] * (len(header) - len(r)) for r in values[1:]]
    return pd.DataFrame(rows, columns=header)


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Reading the live sheet…")
def load_from_google() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Live read through the service account (read-only)."""
    if secret("gcp_json") or secret("gcp_service_account"):
        import gspread

        creds = json.loads(secret("gcp_json")) if secret("gcp_json") else dict(secret("gcp_service_account"))
        gc = gspread.service_account_from_dict(creds)
        sh = gc.open_by_key(secret("sheet_id", SHEET_ID))
        centers = _frame_from_values(sh.worksheet("Centers").get_all_values())
        repo = _frame_from_values(sh.worksheet("Repository").get_all_values())
        return centers, repo, "Google Sheet (service account)"
    base = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet="
    centers = pd.read_csv(base + "Centers", dtype=str, keep_default_na=False)
    repo = pd.read_csv(base + "Repository", dtype=str, keep_default_na=False)
    return centers, repo, "Google Sheet (link sharing)"


def load_from_file(path) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Local testing only: set CENTER_REPO_XLSX to an exported workbook."""
    xl = pd.ExcelFile(path)
    return (pd.read_excel(xl, "Centers", dtype=str, keep_default_na=False),
            pd.read_excel(xl, "Repository", dtype=str, keep_default_na=False), "Local file")


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
# Build the data the page needs
# ─────────────────────────────────────────────────────────────────────────────
def _txt(v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return str(v).strip()


def _int(v):
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def build_payload(data: pd.DataFrame, repo: pd.DataFrame, user: str) -> dict:
    centres = []
    for r in data.to_dict("records"):
        sv = bool(r.get("Surveyed"))
        sign_issues = r.get("Signboard Issues") if isinstance(r.get("Signboard Issues"), list) else []
        themes = r.get("Issue Themes") if isinstance(r.get("Issue Themes"), list) else []
        ts = r.get("Timestamp")
        centres.append({
            "code": _txt(r.get("Center Code")), "centre": _txt(r.get("Center Name")), "region": _txt(r.get("Region")),
            "city": _txt(r.get("City")), "al": _txt(r.get("Area Lead")), "rl": _txt(r.get("Regional Lead")),
            "sv": sv, "model": _txt(r.get("Model")) if sv else "", "layout": _txt(r.get("Layout Type")) if sv else "",
            "logo": _txt(r.get("Back-lit Logo (Reception)")) if sv else "", "sign": _txt(r.get("Signboard Condition")) if sv else "",
            "sign_n": len(sign_issues), "reno": _txt(r.get("Last Renovation (Year)")), "reno_p": _txt(r.get("Reno Problem")),
            "cond": _int(r.get("Condition")), "score": _int(r.get("Priority Score")), "band": _txt(r.get("Priority Band")) if sv else "",
            "issues": _txt(r.get("Key Issues")), "themes": themes, "photos": _int(r.get("Photos Uploaded")) or 0,
            "times": _int(r.get("Times Submitted")) or 0, "link": _txt(r.get("Photo Link")) if _txt(r.get("Photo Link")).startswith("http") else "",
            "by": _txt(r.get("Submitted By")), "ts": ts.strftime("%Y-%m-%d %H:%M") if isinstance(ts, pd.Timestamp) and not pd.isna(ts) else "",
        })

    # day-by-day progress: first submission per centre = new; later ones = re-submissions
    in_scope = set(data["Center Code"])
    sub = repo[repo["Center Code"].isin(in_scope)].dropna(subset=["Timestamp"]).sort_values("Timestamp").copy()
    region_of = dict(zip(data["Center Code"], data["Region"]))
    sub["region"] = sub["Center Code"].map(region_of)
    sub["d"] = sub["Timestamp"].dt.strftime("%Y-%m-%d")
    sub["fresh"] = ~sub.duplicated("Center Code", keep="first")
    times = pd.to_numeric(sub["Times Submitted"], errors="coerce").fillna(1).clip(lower=1)
    sub["resub"] = (times - 1).where(sub["fresh"], 0)  # sheet keeps one row per centre with a submission counter
    daily = (sub.groupby(["d", "region"]).agg(fresh=("fresh", "sum"), resub=("resub", "sum"), photos=("Photos Uploaded", "sum"))
             .reset_index())
    daily = [{"d": r.d, "region": r.region, "fresh": int(r.fresh), "resub": int(r.resub), "photos": int(r.photos)} for r in daily.itertuples()]

    return {"meta": {"as_of": datetime.now(PKT).strftime("%-d %b %Y, %-I:%M %p"), "user": user}, "centres": centres, "daily": daily}


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def page_template() -> str:
    return (BASE / "index.html").read_text(encoding="utf-8")


def render_page(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return re.sub(r"/\*DATA\*/.*?/\*END\*/", lambda m: "/*DATA*/" + data + "/*END*/", page_template(), count=1, flags=re.S)


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────
try:
    if os.environ.get("CENTER_REPO_XLSX"):
        centers_raw, repo_raw, source = load_from_file(os.environ["CENTER_REPO_XLSX"])
    else:
        centers_raw, repo_raw, source = load_from_google()
except Exception as e:  # noqa: BLE001
    st.error(
        "Couldn't read the Google Sheet. Check that the service-account key is in the app's Secrets "
        f"and that the sheet is shared with the service-account email as Viewer.\n\nDetails: `{e}`"
    )
    st.stop()

data, repo_all, _orphans = prepare(centers_raw, repo_raw)
user = st.session_state["auth_user"]

# thin bar: user · refresh · log out
_, c_user, c_ref, c_out = st.columns([6, 2.2, 1.1, 0.9])
c_user.markdown(f'<div class="tb-user">Signed in as <b>{user}</b></div>', unsafe_allow_html=True)
if c_ref.button("↻ Refresh data", width="stretch"):
    st.cache_data.clear()
    st.rerun()
if c_out.button("Log out", width="stretch"):
    st.session_state.pop("auth_user", None)
    st.rerun()

components.html(render_page(build_payload(data, repo_all, user)), height=PAGE_HEIGHT, scrolling=True)
