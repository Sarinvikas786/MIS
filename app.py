import re

import pandas as pd
import plotly.express as px
import streamlit as st

# ------------------------------------------------------------------ config
SHEET_ID = "1sE0isqBf2Qisb_HJKaI-mKXYKpeXiWfctBOzEHG6Drg"
GID = "654595383"
URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"

BUYER, STYLE, COLOR = "Buyer Name", "Style Number", "Color Name"
ORDER_DATE, ORD, FULL = "Timestamp", "Order Qnty", "COMPLETE STYLE"
CUT, STITCH, PACK, DISP = "QNTY (CUTTING)", "QNTY (STITCHING)", "QNTY (PACKING)", "QNTY (DISP)"
REJ, SHORT = "REJECTION (4M DISPATCH APP)", "SHORTAGE (4M DISPATCH APP)"
DELAY = "NO OF DAYS DELAY :(CUTTING)"
STATUS_COLS = {
    "Fabric receipt": "STATUS",
    "Bulk cutting": "BULK CUTTING STATUS -COMPLETED/NOT COMPLETED",
    "Feeding": "FEEDING STATUS -COMPLETED/NOT COMPLETED",
    "Finishing": "FINISHING STATUS -COMPLETED/NOT COMPLETED",
    "Dispatch": "DISPATCH STATUS -COMPLETED/NOT COMPLETED",
}
NUMERIC = [ORD, CUT, STITCH, PACK, DISP, REJ, SHORT, DELAY, "CUTTING QNTY", "DISPATCH QNTY", "DIFFERENCE"]

st.set_page_config(page_title="Production Dashboard", page_icon="🧵", layout="wide")
st.markdown(
    """<style>
.block-container{padding-top:1.5rem}
.hero{background:linear-gradient(120deg,#4f46e5,#06b6d4);padding:22px 28px;border-radius:16px;margin-bottom:18px}
.hero h1{margin:0;font-size:1.8rem;color:#fff}.hero p{margin:4px 0 0;color:#e0f2fe}
div[data-testid="stMetric"]{background:rgba(128,128,128,.08);border:1px solid rgba(128,128,128,.25);
border-radius:14px;padding:14px 18px}
</style>""",
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="hero"><h1>🧵 Production Dashboard</h1>'
    "<p>Live from Google Sheets · cutting → stitching → finishing → dispatch</p></div>",
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------ data
def to_date(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s, format="%d/%b/%y", errors="coerce")
    rest = pd.to_datetime(s[d.isna()], dayfirst=True, errors="coerce")
    return d.fillna(rest)


@st.cache_data(ttl=300, show_spinner="Loading data from Google Sheet…")
def load() -> pd.DataFrame:
    df = pd.read_csv(URL, header=1, dtype=str)  # row 1 = group titles, row 2 = real headers
    df.columns = [re.sub(r"\s+", " ", str(c)).replace(" )", ")").strip() for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()].dropna(how="all")
    df = df.apply(lambda s: s.str.strip())
    for c in NUMERIC:
        if c in df:
            df[c] = pd.to_numeric(df[c].str.replace(",", "", regex=False), errors="coerce")
    if ORDER_DATE in df:
        df[ORDER_DATE] = to_date(df[ORDER_DATE])
    return df


df = load()
f = df.copy()

# ------------------------------------------------------------------ filters
with st.sidebar:
    st.header("🔎 Filters")
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.rerun()

    q = st.text_input("Search style (name / number)")
    if q and FULL in f:
        f = f[f[FULL].str.contains(q, case=False, na=False)]

    def multi(frame, label, col):
        if col not in df:
            return frame
        sel = st.multiselect(label, sorted(df[col].dropna().unique()))
        return frame[frame[col].isin(sel)] if sel else frame

    f = multi(f, "Buyer", BUYER)
    f = multi(f, "Style number", STYLE)
    f = multi(f, "Colour", COLOR)

    if ORDER_DATE in df and df[ORDER_DATE].notna().any():
        lo, hi = df[ORDER_DATE].min().date(), df[ORDER_DATE].max().date()
        r = st.date_input("Order date range", (lo, hi), min_value=lo, max_value=hi)
        if len(r) == 2 and (r[0], r[1]) != (lo, hi):
            f = f[f[ORDER_DATE].between(pd.Timestamp(r[0]), pd.Timestamp(r[1]))]

    if ORD in df and df[ORD].max() > df[ORD].min():
        qlo, qhi = float(df[ORD].min()), float(df[ORD].max())
        sel = st.slider("Order quantity", qlo, qhi, (qlo, qhi))
        if sel != (qlo, qhi):
            f = f[f[ORD].between(*sel)]

    st.subheader("Status")
    for label, col in STATUS_COLS.items():
        f = multi(f, label, col)

if f.empty:
    st.warning("No rows match these filters.")
    st.stop()


# ------------------------------------------------------------------ KPIs
def total(c):
    return f[c].sum() if c in f else 0


order, disp = total(ORD), total(DISP)
k = st.columns(6)
k[0].metric("Styles / colours", f"{len(f):,}")
k[1].metric("Order qty", f"{order:,.0f}")
k[2].metric("Cut qty", f"{total(CUT):,.0f}")
k[3].metric("Dispatched", f"{disp:,.0f}", f"{disp / order:.0%} of order" if order else None, delta_color="off")
k[4].metric("Rejection", f"{total(REJ):,.0f}")
k[5].metric("Shortage", f"{total(SHORT):,.0f}")


def show(fig, h=340):
    fig.update_layout(margin=dict(l=10, r=10, t=45, b=10), height=h)
    st.plotly_chart(fig)


tab1, tab2, tab3 = st.tabs(["📈 Overview", "🏭 Process progress", "📋 Data"])

# ------------------------------------------------------------------ overview
with tab1:
    a, b = st.columns(2)
    if BUYER in f and ORD in f:
        g = f.groupby(BUYER, as_index=False)[ORD].sum().nlargest(15, ORD)
        fig = px.bar(g, x=ORD, y=BUYER, orientation="h", title="Order qty by buyer (top 15)",
                     color=ORD, color_continuous_scale="Tealgrn")
        fig.update_layout(yaxis=dict(categoryorder="total ascending"), coloraxis_showscale=False)
        with a:
            show(fig)
    if ORDER_DATE in f and f[ORDER_DATE].notna().any():
        m = f.dropna(subset=[ORDER_DATE]).assign(Month=lambda d: d[ORDER_DATE].dt.to_period("M").dt.to_timestamp())
        m = m.groupby("Month", as_index=False)[ORD].sum()
        with b:
            show(px.area(m, x="Month", y=ORD, title="Orders received per month", markers=True))

    st.subheader("Status split")
    cols = st.columns(len(STATUS_COLS))
    for c, (label, col) in zip(cols, STATUS_COLS.items()):
        if col in f:
            g = f[col].fillna("(blank)").value_counts().reset_index()
            g.columns = ["Status", "Count"]
            with c:
                show(px.pie(g, names="Status", values="Count", hole=0.55, title=label), 280)

# ------------------------------------------------------------------ progress
with tab2:
    stages = [("Order", ORD), ("Cutting", CUT), ("Stitching", STITCH), ("Packing", PACK), ("Dispatch", DISP)]
    stages = [(n, c) for n, c in stages if c in f]
    a, b = st.columns(2)
    with a:
        show(px.funnel(x=[f[c].sum() for _, c in stages], y=[n for n, _ in stages], title="Quantity through each stage"))
    if BUYER in f:
        top = f.groupby(BUYER)[ORD].sum().nlargest(10).index
        g = f[f[BUYER].isin(top)].groupby(BUYER)[[c for _, c in stages]].sum().reset_index()
        g = g.melt(BUYER, var_name="Stage", value_name="Qty")
        with b:
            show(px.bar(g, x=BUYER, y="Qty", color="Stage", barmode="group", title="Stage quantities by buyer (top 10)"))
    if DELAY in f and FULL in f:
        d = f.nlargest(10, DELAY)[[FULL, DELAY]].dropna()
        fig = px.bar(d, x=DELAY, y=FULL, orientation="h", title="Top 10 cutting delays (days)",
                     color=DELAY, color_continuous_scale="Reds")
        fig.update_layout(yaxis=dict(categoryorder="total ascending"), coloraxis_showscale=False)
        show(fig, 380)

# ------------------------------------------------------------------ data
with tab3:
    key = [c for c in [FULL, ORDER_DATE, BUYER, STYLE, COLOR, ORD, CUT, STITCH, PACK, DISP, REJ, SHORT,
                       *STATUS_COLS.values()] if c in f]
    show_all = st.toggle("Show all columns", value=False)
    view = f if show_all else f[key]
    st.dataframe(view, height=520)
    st.download_button("⬇️ Download filtered data (CSV)", view.to_csv(index=False).encode(), "filtered_data.csv", "text/csv")
