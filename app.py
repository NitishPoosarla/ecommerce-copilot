"""
E-commerce Revenue & Customer Experience Intelligence — Streamlit dashboard.

Run:  ./venv/Scripts/python.exe -m streamlit run app.py
Then open the local URL it prints (usually http://localhost:8501).

HOW IT WORKS (beginner map):
  1. load_data()      — one SQL query pulls the warehouse into a DataFrame.
                        @st.cache_data means "run this ONCE, reuse the result"
                        so clicking filters never re-hits the database.
  2. Sidebar filters  — date range / state / category, applied IN PANDAS
                        (fast, in-memory) instead of new SQL per click.
  3. KPI cards        — 4 headline numbers recomputed from the filtered data.
  4. Tabs             — 4 pages of Plotly charts + an "Ask the Copilot"
                        tab (Phase 5 RAG chat: SQL + pgvector + Groq).

GRAIN RULE (from Phase 2): fact is 1 row per ORDER ITEM.
  - Money: sum directly at item grain.
  - Order-level KPIs (on-time %, reviews, delivery days): collapse to
    DISTINCT order first with drop_duplicates("order_id").
"""
import os

import pandas as pd
import plotly.express as px
import sqlalchemy as sa
import streamlit as st
from dotenv import load_dotenv

# ---------------------------------------------------------------- page setup
st.set_page_config(
    page_title="E-commerce Revenue & Customer Experience Intelligence",
    layout="wide",                    # full-width instead of narrow column
    initial_sidebar_state="expanded",
)

BRAND = "#2C3E50"      # dark blue-grey for chart accents
ACCENT = "#E74C3C"     # red for "bad" (late/1-star) series
OK = "#27AE60"         # green for "good" (on-time) series


# ------------------------------------------------------------- data loading
@st.cache_data(ttl=3600)   # cache for 1 hour: SQL runs once, not per click
def load_data() -> pd.DataFrame:
    """One joined query: fact_orders + customer state + product category."""
    load_dotenv()
    url = os.environ["DATABASE_URL"]
    # Force psycopg2 driver (SQLAlchemy 2 defaults to psycopg v3, not installed)
    url = url.replace("postgres://", "postgresql+psycopg2://", 1) \
        if url.startswith("postgres://") else \
        url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if "sslmode=" not in url:
        url += ("&" if "?" in url else "?") + "sslmode=require"
    eng = sa.create_engine(url)

    sql = """
        SELECT f.order_id,
               f.purchase_ts,
               f.price + f.freight_value AS item_revenue,   -- BRL per item
               f.delivery_days,
               f.is_delivered,
               f.is_on_time,
               f.review_score,                              -- order-level (05b-safe)
               c.customer_state,
               c.customer_unique_id,                        -- stable PERSON id
               p.product_category_en AS category
        FROM fact_orders f
        JOIN dim_customers c ON c.customer_id = f.customer_id
        JOIN dim_products  p ON p.product_id  = f.product_id
    """
    df = pd.read_sql(sql, eng)
    df["purchase_ts"] = pd.to_datetime(df["purchase_ts"])
    # BOOLEAN column with NULLs (undelivered orders) comes back as object
    # dtype from the driver; force pandas' nullable boolean so .mean() works.
    df["is_on_time"] = df["is_on_time"].astype("boolean")
    df["month"] = df["purchase_ts"].dt.strftime("%Y-%m")    # e.g. '2017-11'
    return df


@st.cache_data
def order_level(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse item rows -> one row per order (for delivery/review KPIs)."""
    return df.drop_duplicates("order_id")


# ------------------------------------------------------------- filter helpers
def fmt_brl(v: float) -> str:
    """1234567.8 -> '1,234,568 BRL'"""
    return f"{v:,.0f} BRL"


df_all = load_data()
min_d, max_d = df_all["purchase_ts"].min().date(), df_all["purchase_ts"].max().date()

# ------------------------------------------------------------------- sidebar
st.sidebar.title("Filters")
st.sidebar.caption("All charts + KPI cards below react instantly.")

date_range = st.sidebar.date_input(
    "Purchase date range", value=(min_d, max_d),
    min_value=min_d, max_value=max_d,
)
states = sorted(df_all["customer_state"].dropna().unique())
categories = sorted(df_all["category"].dropna().unique())
sel_states = st.sidebar.multiselect("Customer state", states, default=states)
sel_cats = st.sidebar.multiselect("Product category", categories, default=categories)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Source: Olist Brazilian e-commerce (2016–2018), Timescale Postgres. "
    "Revenue = item price + freight, BRL."
)

# ------------------------------------------------- apply filters (in pandas)
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_d, end_d = date_range
else:                                   # user is still picking the 2nd date
    start_d, end_d = min_d, max_d

df = df_all[
    (df_all["purchase_ts"].dt.date >= start_d)
    & (df_all["purchase_ts"].dt.date <= end_d)
    & (df_all["customer_state"].isin(sel_states))
    & (df_all["category"].isin(sel_cats))
]

# ------------------------------------------------------------------ header
st.title("E-commerce Revenue & Customer Experience Intelligence")
st.caption(
    "Answers the Operations Manager's three questions: where delivery breaks "
    "down, whether lateness drives bad reviews, and how revenue splits "
    "between repeat and one-time buyers."
)

if df.empty:
    st.warning("No data matches these filters — widen the date range or re-select states/categories.")
    st.stop()

# ------------------------------------------------------------- KPI cards row
orders = order_level(df)                       # 1 row per order
delivered = orders[orders["is_delivered"]]
reviewed = orders[orders["review_score"].notna()]
revenue = df["item_revenue"].sum()

on_time_pct = delivered["is_on_time"].mean() * 100 if len(delivered) else float("nan")
avg_score = reviewed["review_score"].mean() if len(reviewed) else float("nan")

# repeat rate needs person-level order counts inside the current filter
cust_order_counts = orders.groupby("customer_unique_id")["order_id"].nunique()
repeat_rate = (cust_order_counts >= 2).mean() * 100 if len(cust_order_counts) else float("nan")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Revenue", fmt_brl(revenue), help="Sum of item price + freight for the filtered selection.")
c2.metric("On-time Delivery %", f"{on_time_pct:.1f}%",
          help="Delivered orders arriving on/before the estimated date.")
c3.metric("Avg Review Score", f"{avg_score:.2f} / 5" if pd.notna(avg_score) else "n/a",
          help="Average star rating across reviewed orders.")
c4.metric("Repeat Purchase Rate", f"{repeat_rate:.1f}%",
          help="Customers (person-level) with 2+ orders in the selection.")

st.divider()

# ------------------------------------------------------------------- tabs
tab_rev, tab_del, tab_revu, tab_cust, tab_bot = st.tabs(
    ["Revenue", "Delivery", "Reviews", "Customers", "Ask the Copilot"]
)

# ============================================================ TAB 1: REVENUE
with tab_rev:
    # 1a. Monthly trend (item grain — money sums directly)
    monthly = (df.groupby("month", as_index=False)
                 .agg(revenue_brl=("item_revenue", "sum"),
                      orders=("order_id", "nunique")))
    fig = px.line(monthly, x="month", y="revenue_brl",
                  markers=True, template="plotly_white",
                  title="Monthly revenue trend (BRL)",
                  labels={"revenue_brl": "Revenue (BRL)", "month": "Month"})
    fig.update_traces(line_color=BRAND, hovertemplate="%{x}<br>%{y:,.0f} BRL<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)

    # 1b + 1c side by side: revenue by state / by category
    left, right = st.columns(2)

    with left:
        by_state = (df.groupby("customer_state", as_index=False)["item_revenue"]
                      .sum().sort_values("item_revenue").tail(15))
        fig = px.bar(by_state, x="item_revenue", y="customer_state",
                     orientation="h", template="plotly_white",
                     title="Top 15 states by revenue (BRL)",
                     labels={"item_revenue": "Revenue (BRL)", "customer_state": ""})
        fig.update_traces(marker_color=BRAND, hovertemplate="%{y}: %{x:,.0f} BRL<extra></extra>")
        st.plotly_chart(fig, use_container_width=True)

    with right:
        by_cat = (df.groupby("category", as_index=False)["item_revenue"]
                    .sum().sort_values("item_revenue").tail(15))
        fig = px.bar(by_cat, x="item_revenue", y="category",
                     orientation="h", template="plotly_white",
                     title="Top 15 categories by revenue (BRL)",
                     labels={"item_revenue": "Revenue (BRL)", "category": ""})
        fig.update_traces(marker_color=ACCENT, hovertemplate="%{y}: %{x:,.0f} BRL<extra></extra>")
        st.plotly_chart(fig, use_container_width=True)

# ============================================================ TAB 2: DELIVERY
with tab_del:
    st.caption("Order-level metrics — computed from DISTINCT orders, not items.")

    # 2a. Avg delivery days by state (worst first, min 200 orders)
    st_state = (orders[orders["delivery_days"].notna()]
                .groupby("customer_state")
                .agg(avg_days=("delivery_days", "mean"),
                     n=("order_id", "nunique")))
    st_state = st_state[st_state["n"] >= 200].reset_index().sort_values("avg_days")
    fig = px.bar(st_state, x="avg_days", y="customer_state",
                 orientation="h", template="plotly_white",
                 title="Avg delivery days by state (worst = longest, min 200 orders)",
                 labels={"avg_days": "Days", "customer_state": ""},
                 hover_data={"n": True, "avg_days": ":.1f"})
    fig.add_vline(x=orders["delivery_days"].mean(), line_dash="dash",
                  annotation_text=f"national avg {orders['delivery_days'].mean():.1f}d")
    fig.update_traces(marker_color=BRAND,
                      hovertemplate="%{y}: %{x:.1f} days (%{customdata[0]} orders)<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)

    # 2b. On-time % by month
    ot_month = (delivered.groupby("month", as_index=False)
                .agg(on_time_pct=("is_on_time", lambda s: s.mean() * 100),
                     n=("order_id", "nunique")))
    fig = px.line(ot_month, x="month", y="on_time_pct", markers=True,
                  template="plotly_white",
                  title="On-time delivery % by month",
                  labels={"on_time_pct": "On-time %", "month": "Month"})
    fig.update_traces(line_color=OK, hovertemplate="%{x}: %{y:.1f}%<extra></extra>")
    fig.add_hline(y=delivered["is_on_time"].mean() * 100, line_dash="dash",
                  annotation_text="overall")
    st.plotly_chart(fig, use_container_width=True)

    # 2c. Late deliveries by category (count of DISTINCT late orders)
    late = (delivered[delivered["is_on_time"] == False]   # noqa: E712
            .groupby("category", as_index=False)
            .agg(late_orders=("order_id", "nunique"))
            .sort_values("late_orders")   # ascending -> biggest bar on top
            .tail(15))                    # keep only the 15 worst categories
    fig = px.bar(late, x="late_orders", y="category", orientation="h",
                 template="plotly_white",
                 title="Most late deliveries by category (top 15, distinct orders)",
                 labels={"late_orders": "Late orders", "category": ""})
    fig.update_traces(marker_color=ACCENT,
                      hovertemplate="%{y}: %{x} late orders<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)

# ============================================================== TAB 3: REVIEWS
with tab_revu:
    # 3a. Score distribution (1-5)
    dist = (reviewed.groupby("review_score", as_index=False)
            .agg(orders=("order_id", "nunique")))
    dist["pct"] = dist["orders"] / dist["orders"].sum() * 100
    fig = px.bar(dist, x="review_score", y="orders", text="pct",
                 template="plotly_white",
                 title="Review score distribution (per order)",
                 labels={"review_score": "Stars", "orders": "Orders"})
    fig.update_traces(marker_color=BRAND, texttemplate="%{text:.1f}%",
                      hovertemplate="%{x} stars: %{y} orders (%{text:.1f}%)<extra></extra>")
    st.plotly_chart(fig, use_container_width=True)

    # 3b. THE hypothesis: late vs on-time scores
    lv = (reviewed[reviewed["is_on_time"].notna()]
          .groupby("is_on_time", as_index=False)
          .agg(avg_score=("review_score", "mean"),
               n=("order_id", "nunique")))
    lv["label"] = lv["is_on_time"].map({True: "On-time", False: "Late"})
    fig = px.bar(lv, x="label", y="avg_score", text="avg_score",
                 hover_data={"n": True, "is_on_time": False},
                 template="plotly_white",
                 title="Avg review score: late vs on-time orders",
                 labels={"label": "", "avg_score": "Avg stars"})
    fig.update_traces(marker_color=[OK, ACCENT], texttemplate="%{text:.2f}",
                      hovertemplate="%{x}: %{y:.2f} stars (%{customdata[0]} orders)<extra></extra>")
    fig.update_yaxes(range=[0, 5])
    st.plotly_chart(fig, use_container_width=True)

    st.caption("Key: a 1-star share comparison — late orders are far more "
               "likely to be rated 1 star.")

    # 3c. Worst-reviewed categories (min 200 reviewed orders)
    wc = (reviewed.groupby("category")
          .agg(avg_score=("review_score", "mean"),
               n=("order_id", "nunique"))
          .query("n >= 200").reset_index()
          .nsmallest(15, "avg_score")        # 15 worst categories
          .sort_values("avg_score", ascending=False))  # worst displays on top
    fig = px.bar(wc, x="avg_score", y="category", orientation="h",
                 template="plotly_white",
                 title="Worst-reviewed categories (min 200 reviews)",
                 labels={"avg_score": "Avg stars", "category": ""})
    fig.update_traces(marker_color=ACCENT,
                      hovertemplate="%{y}: %{x:.2f} stars<extra></extra>")
    fig.update_xaxes(range=[0, 5])
    st.plotly_chart(fig, use_container_width=True)

# ============================================================ TAB 4: CUSTOMERS
with tab_cust:
    # flag repeat customers (2+ orders IN THE CURRENT FILTER)
    orders = orders.copy()
    orders["n_orders_per_cust"] = orders.groupby("customer_unique_id")[
        "order_id"].transform("nunique")
    orders["buyer_type"] = orders["n_orders_per_cust"].map(
        lambda n: "Repeat (2+ orders)" if n >= 2 else "One-time")

    left, right = st.columns(2)

    with left:
        # customer COUNT share vs revenue SHARE — the punchline lives in the gap.
        # Built explicitly (not zipped from index order) so bar labels can't
        # silently mismatch their values.
        cust_counts = orders.drop_duplicates("customer_unique_id") \
            .groupby("buyer_type").size()
        order_rev = df.merge(orders[["order_id", "buyer_type"]], on="order_id") \
            .groupby("buyer_type")["item_revenue"].sum()
        rows = []
        for btype in ["One-time", "Repeat (2+ orders)"]:
            rows.append({"buyer_type": btype, "share_type": "% of customers",
                         "pct": cust_counts.get(btype, 0) / cust_counts.sum() * 100})
            rows.append({"buyer_type": btype, "share_type": "% of revenue",
                         "pct": order_rev.get(btype, 0) / order_rev.sum() * 100})
        cmp_df = pd.DataFrame(rows)
        fig = px.bar(cmp_df, x="share_type", y="pct", color="buyer_type",
                     barmode="group", template="plotly_white",
                     title="One-time vs repeat buyers: customers vs revenue",
                     labels={"pct": "%", "share_type": ""})
        fig.update_traces(hovertemplate="%{legendgroup}: %{y:.1f}%<extra></extra>")
        st.plotly_chart(fig, use_container_width=True)

    with right:
        # orders-per-customer distribution (capped at 5+ for readability)
        opc = orders.drop_duplicates("order_id") \
            .groupby("customer_unique_id")["order_id"].nunique().clip(upper=5)
        opc_df = opc.value_counts().sort_index().rename_axis("orders").reset_index(name="customers")
        opc_df["orders"] = opc_df["orders"].map(lambda n: f"{n}+" if n == 5 else str(n))
        fig = px.bar(opc_df, x="orders", y="customers",
                     template="plotly_white",
                     title="Orders per customer (5+ = five or more)",
                     labels={"orders": "Orders placed", "customers": "Customers"})
        fig.update_traces(marker_color=BRAND,
                          hovertemplate="%{x} orders: %{y:,} customers<extra></extra>")
        st.plotly_chart(fig, use_container_width=True)

    rp = repeat_rate
    st.info(
        f"**{rp:.1f}% of customers** in this selection bought 2+ times. "
        f"The brief expects this to be low — the marketplace is ~97% one-time buyers."
    )

# =========================================================== TAB 5: COPILOT
with tab_bot:
    # Lazy import: pulls in the RAG engine only when this tab's code runs.
    from copilot.copilot import ask as copilot_ask

    st.caption(
        "RAG copilot — numeric questions run SQL against the warehouse, "
        "document questions hit pgvector top-4 search over docs/, mixed "
        "questions do both. Every answer is written by Groq "
        "(openai/gpt-oss-120b) using ONLY the retrieved evidence, with "
        "citations below."
    )

    def _render_citations(citations: list, unsupported: list) -> None:
        """Sources in small text under the answer."""
        for c in citations:
            preview = " ".join(c["content"].split())[:140]
            st.caption(f"{c['eid']} · {c['label']} — {preview}…")
        if unsupported:
            st.warning(
                "Numbers not found in retrieved evidence (verify before "
                f"trusting): {', '.join(unsupported)}"
            )

    if "copilot_msgs" not in st.session_state:
        st.session_state.copilot_msgs = []

    for m in st.session_state.copilot_msgs:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            _render_citations(m.get("citations", []), m.get("unsupported", []))

    if prompt := st.chat_input("Ask the copilot — e.g. What was total revenue?"):
        st.session_state.copilot_msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Routing → SQL / pgvector → Groq…"):
                try:
                    res = copilot_ask(prompt, verbose=False)
                except Exception as exc:      # show, don't crash the dashboard
                    st.error(f"Copilot error: {exc}")
                    res = None
            if res:
                st.markdown(res["answer"])
                st.caption(
                    f"route: {res['route']} · {len(res['evidence'])} evidence "
                    f"blocks · model: openai/gpt-oss-120b"
                )
                _render_citations(res["citations"], res["unsupported_numbers"])
                st.session_state.copilot_msgs.append({
                    "role": "assistant",
                    "content": res["answer"],
                    "citations": [
                        {"eid": c["eid"], "label": c["label"],
                         "content": c["content"]}
                        for c in res["citations"]
                    ],
                    "unsupported": res["unsupported_numbers"],
                })
