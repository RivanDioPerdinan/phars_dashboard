import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime

# ----------------------------
# Page config + minimal styling
# ----------------------------
st.set_page_config(page_title="PHARS-COVID 19", layout="wide")
st.markdown("""
<style>
    .block-container { padding-top: 1.2rem; padding-bottom: 1.5rem; }
    .stMetric { background: #ffffff; border: 1px solid #eee; padding: 12px; border-radius: 14px; }
    div[data-testid="stSidebar"] { border-right: 1px solid #f0f0f0; }
</style>
""", unsafe_allow_html=True)

st.title("PHARS")
st.caption("Public Health Analytics & Reporting System (M8 • M10 • M12) — baseline analytics upgraded into a deployable pitch.")

# ----------------------------
# Sidebar
# ----------------------------
with st.sidebar:
    st.header("Config")
    API_BASE = st.text_input("API Base URL", value="https://web-production-1a8ae.up.railway.app/api").rstrip("/")
    TIMEOUT = st.slider("API Timeout (sec)", 3, 30, 10)

    st.divider()
    st.header("Filters")

# ----------------------------
# Helpers
# ----------------------------
@st.cache_data(show_spinner=False)
def api_get(url, params=None, timeout=10):
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

@st.cache_data(show_spinner=False)
def fetch_metadata(api_base, timeout):
    return api_get(f"{api_base}/metadata", timeout=timeout)

@st.cache_data(show_spinner=False)
def fetch_summary(api_base, level, location, start_date, end_date, timeout):
    return api_get(
        f"{api_base}/summary",
        params={
            "level": level,
            "location": location,
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
        },
        timeout=timeout
    )

@st.cache_data(show_spinner=False)
def fetch_cases(api_base, level, location, start_date, end_date, timeout, limit=6000):
    payload = api_get(
        f"{api_base}/cases",
        params={
            "level": level,
            "location": location,
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d"),
            "limit": limit
        },
        timeout=timeout
    )
    df = pd.DataFrame(payload.get("data", []))
    if not df.empty and "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df

def safe(v, fallback="—"):
    if v is None: return fallback
    if isinstance(v, str) and v.strip() == "": return fallback
    return v

# ----------------------------
# Load metadata
# ----------------------------
try:
    meta = fetch_metadata(API_BASE, TIMEOUT)
except Exception as e:
    st.error("API tidak bisa diakses. Pastikan `python3 api.py` sedang running dan URL benar.")
    st.code(str(e))
    st.stop()

min_date = pd.to_datetime(meta["min_date"]).date()
max_date = pd.to_datetime(meta["max_date"]).date()
levels = meta.get("levels", ["Country"])
locations_by_level = meta.get("locations_by_level", {})

# ----------------------------
# Filters (level -> location) to prevent KPI N/A
# ----------------------------
with st.sidebar:
    level = st.selectbox("Location Level", options=levels, index=0)

    locs = locations_by_level.get(level, [])
    if not locs:
        st.warning("Tidak ada location untuk level ini.")
        st.stop()

    default_loc = "Indonesia" if "Indonesia" in locs else locs[0]
    location = st.selectbox("Location", options=locs, index=locs.index(default_loc))

    start_date, end_date = st.date_input(
        "Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    if isinstance(start_date, (list, tuple)):
        start_date, end_date = start_date[0], start_date[1]

    if start_date > end_date:
        st.error("Start date tidak boleh lebih besar dari end date.")
        st.stop()

# ----------------------------
# Fetch data
# ----------------------------
with st.spinner("Loading from API..."):
    summary = fetch_summary(API_BASE, level, location, start_date, end_date, TIMEOUT)
    df = fetch_cases(API_BASE, level, location, start_date, end_date, TIMEOUT, limit=8000)

kpi = summary.get("kpi", {})
if df.empty:
    st.warning("Tidak ada data untuk filter yang dipilih. Coba ganti level/location atau rentang tanggal.")
    st.stop()

# ----------------------------
# SC4 (M8): Executive KPIs
# ----------------------------
st.subheader("Executive KPIs (Operational Dashboard)")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Cases", safe(kpi.get("total_cases")))
c2.metric("Total Deaths", safe(kpi.get("total_deaths")))
c3.metric("New Cases (7d)", safe(kpi.get("new_cases_7d")))
c4.metric("Data Range", f"{safe(kpi.get('min_date'))} → {safe(kpi.get('max_date'))}")

# ----------------------------
# Tabs (clean: Overview • Report • Governance)
# ----------------------------
tab_overview, tab_report, tab_gov = st.tabs(["📈 Overview", "🧾 Report", "🛡 Governance"])

# ----------------------------
# Overview (baseline analytics + operational trend)
# ----------------------------
with tab_overview:
    left, right = st.columns([2, 1])

    # Normalize numeric
    for col in ["new_cases", "new_deaths", "total_cases", "total_deaths"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    with left:
        if "new_cases" in df.columns:
            fig = px.line(df.sort_values("date"), x="date", y="new_cases", title="New Cases Over Time")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Kolom `new_cases` tidak tersedia.")

        if "new_deaths" in df.columns:
            fig = px.line(df.sort_values("date"), x="date", y="new_deaths", title="New Deaths Over Time")
            st.plotly_chart(fig, use_container_width=True)

    with right:
        st.markdown("### Snapshot")
        st.write(f"**Level:** {level}")
        st.write(f"**Location:** {location}")
        st.write(f"**Window:** {start_date} → {end_date}")
        st.write(f"**Rows:** {len(df):,}")

        if "date" in df.columns and pd.notna(df["date"].max()):
            st.write(f"**Latest record:** {df['date'].max().date()}")

        # Small table preview
        st.markdown("### Preview")
        st.dataframe(df.sort_values("date").tail(10), use_container_width=True)

# ----------------------------
# Report (M8): Situation report + export
# ----------------------------
with tab_report:
    st.markdown("### Situation Report (SC4 – Module 8)")
    st.write("Audience: Public Health Agency / Hospital Management")
    st.write("Purpose: weekly monitoring & resource planning.")

    latest_record = df["date"].max().date() if "date" in df.columns and pd.notna(df["date"].max()) else "—"

    st.markdown(f"""
**Context**
- **Level:** {level}
- **Location:** {location}
- **Reporting window:** {start_date} → {end_date}
- **Latest record date:** {latest_record}

**Decision Value**
- Executive KPIs + trends support quicker situational awareness.
- API-based design enables interoperability across systems.
""")

    st.markdown("#### Export (CSV)")
    export_df = df.sort_values("date").copy()
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "Download CSV Report",
        data=csv_bytes,
        file_name=f"PHARS_Report_{level}_{location}_{start_date}_{end_date}.csv",
        mime="text/csv"
    )

# ----------------------------
# Governance (M12): quality checks + ethics + audit log
# ----------------------------
with tab_gov:
    st.markdown("### Data Quality & Governance (SC6 – Module 12)")

    issues = []
    status = "OK"

    # Completeness
    required = ["date", "location"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        status = "CRITICAL"
        issues.append(f"Missing columns: {missing}")

    # Date validity
    if "date" in df.columns:
        null_dates = int(df["date"].isna().sum())
        if null_dates > 0:
            status = "WARNING" if status == "OK" else status
            issues.append(f"Invalid date rows: {null_dates}")

    # Negative checks
    for col in ["new_cases", "new_deaths", "total_cases", "total_deaths"]:
        if col in df.columns:
            neg = int((pd.to_numeric(df[col], errors="coerce").fillna(0) < 0).sum())
            if neg > 0:
                status = "WARNING" if status == "OK" else status
                issues.append(f"Negative values detected in {col}: {neg}")

    # Timeliness (optional)
    if "date" in df.columns and pd.notna(df["date"].max()):
        latest = df["date"].max().date()
        gap = (datetime.now().date() - latest).days
        if gap > 30:
            status = "WARNING" if status == "OK" else status
            issues.append(f"Data timeliness warning: latest record is {gap} days old.")

    # Status badge
    if status == "OK":
        st.success("Quality Status: OK ✅")
    elif status == "WARNING":
        st.warning("Quality Status: WARNING ⚠️")
    else:
        st.error("Quality Status: CRITICAL ❌")

    if issues:
        st.markdown("**Findings**")
        for it in issues:
            st.write(f"- {it}")
    else:
        st.write("No quality issues detected for the selected window.")

    st.markdown("### Governance Notes")
    st.markdown("""
- This system uses **aggregated public health data** (no personal identifiers).
- Recommended deployment policy:
  - **Public view:** aggregate KPIs only
  - **Analyst view:** trend + export features
- Auditability is supported through reproducible filters and exportable reports.
""")

st.caption("Tip: Untuk video, tampilkan 1) API endpoint, 2) filter level+location, 3) KPI berubah, 4) export report, 5) governance tab.")
