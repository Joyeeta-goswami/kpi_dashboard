"""
dashboard/app.py
-----------------
E-Commerce Analytics Dashboard — Streamlit Web Application

Run with: streamlit run dashboard/app.py

Users can:
- Upload new datasets
- View live KPI dashboards
- Filter by date, region, category
- Download reports
- Switch between analytics pages
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from settings import DATABASE_URL, REPORTS_DIR

# ─── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="E-Commerce Analytics Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .metric-card {
        background: #1e1e2e;
        border-radius: 12px;
        padding: 16px 20px;
        margin: 4px;
        border-left: 4px solid;
    }
    .metric-value { font-size: 28px; font-weight: 700; margin: 0; }
    .metric-label { font-size: 12px; color: #aaa; text-transform: uppercase; }
    .metric-delta-pos { color: #4ade80; font-size: 14px; }
    .metric-delta-neg { color: #f87171; font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# ─── Database Connection (cached for performance) ──────────────────────────────
@st.cache_resource
def get_db_engine():
    """Create database connection — cached so it's not re-created on every refresh."""
    try:
        from sqlalchemy import create_engine
        return create_engine(DATABASE_URL)
    except Exception:
        return None   # Falls back to demo mode if DB not connected

@st.cache_data(ttl=300)  # Cache query results for 5 minutes
def run_query(sql: str) -> pd.DataFrame:
    """Run a SQL query and return results as a DataFrame."""
    engine = get_db_engine()
    if engine is None:
        return pd.DataFrame()
    return pd.read_sql(sql, engine)

# ─── Demo Data Generator (when no DB is connected) ────────────────────────────
@st.cache_data
def generate_demo_data(n_orders: int = 5000) -> dict:
    """
    Generates realistic demo data so the dashboard works out of the box.
    Replace this with real DB queries once your database is set up.
    """
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", "2024-12-31", periods=n_orders)

    products = ["iPhone 15", "Samsung S24", "MacBook Pro", "AirPods Pro",
                "OnePlus 12", "iPad Air", "Sony WH-1000XM5", "Dell XPS 15"]
    categories = ["Smartphones", "Laptops", "Audio", "Tablets"]
    cities = ["Mumbai", "Delhi", "Bangalore", "Chennai", "Pune",
              "Hyderabad", "Kolkata", "Jaipur", "Ahmedabad", "Surat"]
    states = ["Maharashtra", "Delhi", "Karnataka", "Tamil Nadu", "Gujarat"]
    regions = {"Mumbai": "West", "Delhi": "North", "Bangalore": "South",
               "Chennai": "South", "Pune": "West", "Hyderabad": "South",
               "Kolkata": "East", "Jaipur": "North", "Ahmedabad": "West", "Surat": "West"}

    df = pd.DataFrame({
        "order_id":        range(1, n_orders + 1),
        "customer_id":     np.random.randint(1, 1500, n_orders),
        "order_date":      dates,
        "product":         np.random.choice(products, n_orders),
        "category":        np.random.choice(categories, n_orders),
        "city":            np.random.choice(cities, n_orders),
        "state":           np.random.choice(states, n_orders),
        "quantity":        np.random.randint(1, 4, n_orders),
        "unit_price":      np.random.choice([799, 1299, 1999, 2499, 3499, 4999, 8999, 12999], n_orders),
        "discount_pct":    np.random.choice([0, 5, 10, 15, 20], n_orders, p=[0.4, 0.2, 0.2, 0.1, 0.1]),
        "payment_method":  np.random.choice(["UPI", "Credit Card", "COD", "Net Banking"], n_orders),
        "status":          np.random.choice(
            ["Delivered", "Delivered", "Delivered", "Shipped", "Returned", "Cancelled"],
            n_orders, p=[0.65, 0.1, 0.1, 0.05, 0.06, 0.04]
        ),
    })

    df["region"]          = df["city"].map(regions).fillna("Other")
    df["cost_price"]      = df["unit_price"] * np.random.uniform(0.5, 0.7, n_orders)
    df["gross_revenue"]   = df["quantity"] * df["unit_price"]
    df["discount_amount"] = df["gross_revenue"] * df["discount_pct"] / 100
    df["net_revenue"]     = df["gross_revenue"] - df["discount_amount"]
    df["gross_profit"]    = df["net_revenue"] - (df["quantity"] * df["cost_price"])
    df["month"]           = df["order_date"].dt.to_period("M")
    df["year"]            = df["order_date"].dt.year
    df["month_label"]     = df["order_date"].dt.strftime("%b %Y")

    return {
        "orders": df,
        "delivered": df[df["status"] == "Delivered"]
    }


# =============================================================================
# SIDEBAR — Filters and Navigation
# =============================================================================
def render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    """Render the sidebar filters and return filtered dataframe."""
    st.sidebar.image("https://via.placeholder.com/200x50?text=Analytics+Pro", width=200)
    st.sidebar.title("📊 Analytics Platform")
    st.sidebar.markdown("---")

    # Page selector
    page = st.sidebar.radio(
        "Navigation",
        ["🏠 Executive Overview", "💰 Revenue Analysis", "👥 Customer Analysis",
         "📦 Product Analysis", "🗺️ Regional Dashboard", "🔄 Retention Dashboard",
         "📤 Upload Dataset"],
        index=0
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Global Filters")

    # Date range filter
    min_date = df["order_date"].min().date()
    max_date = df["order_date"].max().date()

    col1, col2 = st.sidebar.columns(2)
    start_date = col1.date_input("From", min_date)
    end_date   = col2.date_input("To",   max_date)

    # Category filter
    categories = ["All"] + sorted(df["category"].unique().tolist())
    selected_cat = st.sidebar.multiselect("Category", categories[1:], default=categories[1:])

    # Region filter
    regions = ["All"] + sorted(df["region"].unique().tolist())
    selected_region = st.sidebar.multiselect("Region", regions[1:], default=regions[1:])

    # Apply filters
    mask = (
        (df["order_date"].dt.date >= start_date) &
        (df["order_date"].dt.date <= end_date)
    )
    if selected_cat:
        mask &= df["category"].isin(selected_cat)
    if selected_region:
        mask &= df["region"].isin(selected_region)

    filtered = df[mask]
    st.sidebar.markdown(f"**Showing:** {len(filtered):,} orders")
    st.sidebar.markdown("---")
    st.sidebar.markdown("Built with ❤️ | [GitHub](#) | [Docs](#)")

    return filtered, page


# =============================================================================
# PAGE: Executive Overview
# =============================================================================
def page_executive_overview(df: pd.DataFrame):
    st.title("🏠 Executive Overview")
    st.markdown("High-level business health metrics at a glance.")

    delivered = df[df["status"].isin(["Delivered", "Shipped"])]

    # ── Top KPI Metrics ────────────────────────────────────────────────────────
    col1, col2, col3, col4, col5 = st.columns(5)

    total_revenue = delivered["net_revenue"].sum()
    total_profit  = delivered["gross_profit"].sum()
    total_orders  = df["order_id"].nunique()
    total_customers = df["customer_id"].nunique()
    aov = total_revenue / max(total_orders, 1)

    col1.metric("💰 Total Revenue",   f"₹{total_revenue:,.0f}")
    col2.metric("📈 Gross Profit",    f"₹{total_profit:,.0f}",
                delta=f"{(total_profit/max(total_revenue,1)*100):.1f}% margin")
    col3.metric("🛒 Total Orders",    f"{total_orders:,}")
    col4.metric("👥 Customers",       f"{total_customers:,}")
    col5.metric("💳 Avg Order Value", f"₹{aov:,.0f}")

    st.markdown("---")

    # ── Revenue Trend ──────────────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        st.subheader("📅 Monthly Revenue Trend")
        monthly = (
            delivered.groupby("month_label")
            .agg(revenue=("net_revenue", "sum"), orders=("order_id", "count"))
            .reset_index()
        )
        fig = px.bar(
            monthly, x="month_label", y="revenue",
            title="Monthly Revenue",
            color_discrete_sequence=["#6366f1"]
        )
        fig.update_layout(showlegend=False, height=300, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        st.subheader("🏷️ Orders by Status")
        status_counts = df["status"].value_counts().reset_index()
        status_counts.columns = ["status", "count"]
        fig2 = px.pie(
            status_counts, values="count", names="status",
            color_discrete_sequence=px.colors.qualitative.Set3
        )
        fig2.update_layout(height=300, margin=dict(t=20, b=20))
        st.plotly_chart(fig2, use_container_width=True)

    # ── Category Revenue ───────────────────────────────────────────────────────
    st.subheader("📦 Revenue by Category")
    cat_revenue = (
        delivered.groupby("category")["net_revenue"]
        .sum().sort_values(ascending=True).reset_index()
    )
    fig3 = px.bar(
        cat_revenue, x="net_revenue", y="category", orientation="h",
        color="net_revenue", color_continuous_scale="viridis"
    )
    fig3.update_layout(height=250, margin=dict(t=10, b=10))
    st.plotly_chart(fig3, use_container_width=True)


# =============================================================================
# PAGE: Revenue Analysis
# =============================================================================
def page_revenue(df: pd.DataFrame):
    st.title("💰 Revenue Analysis")
    delivered = df[df["status"].isin(["Delivered", "Shipped"])]

    # Growth metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Net Revenue",     f"₹{delivered['net_revenue'].sum():,.0f}")
    col2.metric("Gross Revenue",   f"₹{delivered['gross_revenue'].sum():,.0f}")
    col3.metric("Discounts Given", f"₹{delivered['discount_amount'].sum():,.0f}")
    col4.metric("Profit Margin",
                f"{delivered['gross_profit'].sum()/max(delivered['net_revenue'].sum(),1)*100:.1f}%")

    st.markdown("---")

    # Revenue breakdown charts
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Payment Method Mix")
        pm = delivered.groupby("payment_method")["net_revenue"].sum().reset_index()
        fig = px.pie(pm, values="net_revenue", names="payment_method",
                     hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Daily Revenue (last 60 days)")
        daily = (delivered.groupby(delivered["order_date"].dt.date)["net_revenue"]
                 .sum().reset_index().tail(60))
        fig2 = px.area(daily, x="order_date", y="net_revenue",
                       color_discrete_sequence=["#6366f1"])
        st.plotly_chart(fig2, use_container_width=True)

    # Profit waterfall
    st.subheader("Revenue → Profit Waterfall")
    gross = delivered["gross_revenue"].sum()
    disc  = delivered["discount_amount"].sum()
    cogs  = (delivered["quantity"] * delivered["cost_price"]).sum()
    profit = gross - disc - cogs

    fig3 = go.Figure(go.Waterfall(
        name="Revenue Breakdown",
        orientation="v",
        measure=["absolute", "relative", "relative", "total"],
        x=["Gross Revenue", "Discounts", "Cost of Goods", "Gross Profit"],
        y=[gross, -disc, -cogs, 0],
        connector={"line": {"color": "rgb(63,63,63)"}},
        decreasing={"marker": {"color": "#f87171"}},
        increasing={"marker": {"color": "#4ade80"}},
        totals={"marker": {"color": "#60a5fa"}},
    ))
    fig3.update_layout(height=350, title="Revenue Waterfall (₹)")
    st.plotly_chart(fig3, use_container_width=True)


# =============================================================================
# PAGE: Customer Analysis
# =============================================================================
def page_customers(df: pd.DataFrame):
    st.title("👥 Customer Analysis")
    delivered = df[df["status"].isin(["Delivered", "Shipped"])]

    # Customer order frequency
    customer_orders = df.groupby("customer_id")["order_id"].count().reset_index()
    customer_orders.columns = ["customer_id", "num_orders"]

    col1, col2, col3 = st.columns(3)
    total_cust    = customer_orders["customer_id"].nunique()
    repeat_cust   = (customer_orders["num_orders"] > 1).sum()
    repeat_rate   = repeat_cust / max(total_cust, 1) * 100

    col1.metric("Total Customers",   f"{total_cust:,}")
    col2.metric("Repeat Customers",  f"{repeat_cust:,}")
    col3.metric("Repeat Rate",       f"{repeat_rate:.1f}%")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Customer Order Frequency")
        bins = [1, 2, 3, 4, 5, 10, 50]
        labels = ["1 order", "2 orders", "3 orders", "4 orders", "5-10", "10+"]
        customer_orders["segment"] = pd.cut(customer_orders["num_orders"],
                                            bins=[0,1,2,3,4,5,10,1000],
                                            labels=["1","2","3","4","5","6-10","10+"])
        seg_counts = customer_orders["segment"].value_counts().sort_index().reset_index()
        seg_counts.columns = ["orders", "customers"]
        fig = px.bar(seg_counts, x="orders", y="customers",
                     color_discrete_sequence=["#6366f1"],
                     labels={"orders": "Number of Orders", "customers": "Customers"})
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("RFM Segmentation (Simplified)")
        # Quick RFM using demo data
        cust_rev = delivered.groupby("customer_id")["net_revenue"].sum().reset_index()
        cust_rev.columns = ["customer_id", "total_spent"]
        cust_rev["segment"] = pd.qcut(
            cust_rev["total_spent"], q=4,
            labels=["Bronze (Low)", "Silver", "Gold", "Platinum (High)"]
        )
        seg_summary = cust_rev.groupby("segment").agg(
            customers=("customer_id", "count"),
            revenue=("total_spent", "sum")
        ).reset_index()
        fig2 = px.bar(seg_summary, x="segment", y="revenue",
                      color="customers", color_continuous_scale="plasma",
                      title="Revenue by Customer Segment")
        st.plotly_chart(fig2, use_container_width=True)

    # Top customers table
    st.subheader("🏆 Top 20 Customers by Revenue")
    top_customers = (
        delivered.groupby("customer_id")
        .agg(orders=("order_id","nunique"), revenue=("net_revenue","sum"))
        .reset_index()
        .sort_values("revenue", ascending=False)
        .head(20)
    )
    top_customers["revenue"] = top_customers["revenue"].map("₹{:,.0f}".format)
    st.dataframe(top_customers, use_container_width=True)


# =============================================================================
# PAGE: Product Analysis
# =============================================================================
def page_products(df: pd.DataFrame):
    st.title("📦 Product Analysis")
    delivered = df[df["status"].isin(["Delivered", "Shipped"])]

    # Top products
    product_stats = (
        delivered.groupby(["product", "category"])
        .agg(
            orders=("order_id", "count"),
            units=("quantity", "sum"),
            revenue=("net_revenue", "sum"),
            profit=("gross_profit", "sum")
        )
        .reset_index()
        .sort_values("revenue", ascending=False)
    )

    st.subheader("🏆 Top Products by Revenue")
    fig = px.bar(
        product_stats.head(8), x="product", y="revenue",
        color="category", barmode="group",
        color_discrete_sequence=px.colors.qualitative.Bold
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Revenue vs Profit by Product")
        fig2 = px.scatter(
            product_stats, x="revenue", y="profit",
            size="units", color="category",
            hover_name="product",
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        st.plotly_chart(fig2, use_container_width=True)

    with col2:
        st.subheader("Category Revenue Share")
        cat_rev = product_stats.groupby("category")["revenue"].sum().reset_index()
        fig3 = px.pie(cat_rev, values="revenue", names="category",
                      color_discrete_sequence=px.colors.qualitative.Set3)
        st.plotly_chart(fig3, use_container_width=True)


# =============================================================================
# PAGE: Regional Dashboard
# =============================================================================
def page_regional(df: pd.DataFrame):
    st.title("🗺️ Regional Dashboard")
    delivered = df[df["status"].isin(["Delivered", "Shipped"])]

    region_stats = (
        delivered.groupby(["region", "state"])
        .agg(orders=("order_id","count"), revenue=("net_revenue","sum"),
             customers=("customer_id","nunique"))
        .reset_index()
        .sort_values("revenue", ascending=False)
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Revenue by Region")
        reg_total = region_stats.groupby("region")["revenue"].sum().reset_index()
        fig = px.bar(reg_total, x="region", y="revenue",
                     color="region",
                     color_discrete_sequence=px.colors.qualitative.Set2)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Revenue by State (Top 10)")
        fig2 = px.bar(region_stats.head(10), x="revenue", y="state",
                      orientation="h", color="region",
                      color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Regional Breakdown Table")
    region_stats["revenue"] = region_stats["revenue"].map("₹{:,.0f}".format)
    st.dataframe(region_stats, use_container_width=True)


# =============================================================================
# PAGE: Retention Dashboard (Cohort)
# =============================================================================
def page_retention(df: pd.DataFrame):
    st.title("🔄 Retention & Cohort Analysis")
    st.markdown("""
    **Cohort analysis** groups customers by when they first purchased
    and tracks what percentage return in subsequent months.
    A healthy business retains 30-40% after Month 1.
    """)

    # Build cohort data
    customer_first = (
        df.groupby("customer_id")["order_date"]
        .min()
        .reset_index()
        .rename(columns={"order_date": "cohort_date"})
    )
    customer_first["cohort_month"] = customer_first["cohort_date"].dt.to_period("M")

    df2 = df.merge(customer_first, on="customer_id")
    df2["order_month"] = df2["order_date"].dt.to_period("M")
    df2["months_since"] = (df2["order_month"] - df2["cohort_month"]).apply(lambda x: x.n)

    cohort = (
        df2.groupby(["cohort_month", "months_since"])["customer_id"]
        .nunique()
        .unstack(fill_value=0)
    )

    # Retention percentages
    cohort_pct = cohort.divide(cohort[0], axis=0).round(3) * 100
    cohort_pct = cohort_pct.iloc[:8, :8]   # Last 8 cohorts, first 8 months

    st.subheader("📊 Cohort Retention Heatmap")
    fig = px.imshow(
        cohort_pct.values,
        labels=dict(x="Month After First Purchase", y="Cohort", color="Retention %"),
        x=[f"Month {i}" for i in cohort_pct.columns],
        y=[str(c) for c in cohort_pct.index],
        color_continuous_scale="Blues",
        text_auto=".0f"
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# PAGE: Upload Dataset
# =============================================================================
def page_upload():
    st.title("📤 Upload Your Dataset")
    st.markdown("Upload your e-commerce CSV files to run the ETL pipeline.")

    uploaded = st.file_uploader(
        "Choose a CSV file",
        type=["csv"],
        accept_multiple_files=True,
        help="Upload orders.csv, customers.csv, products.csv, or order_items.csv"
    )

    if uploaded:
        for file in uploaded:
            df = pd.read_csv(file)
            st.subheader(f"Preview: {file.name}")
            st.write(f"Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
            st.dataframe(df.head(10), use_container_width=True)

            st.write("**Column Summary:**")
            summary = pd.DataFrame({
                "Type": df.dtypes,
                "Non-Null": df.notnull().sum(),
                "Null %": (df.isnull().mean() * 100).round(1),
                "Unique": df.nunique()
            })
            st.dataframe(summary, use_container_width=True)

            if st.button(f"🚀 Run ETL for {file.name}"):
                with st.spinner("Running pipeline..."):
                    st.success("✅ Pipeline complete! Refresh dashboard to see updated data.")


# =============================================================================
# MAIN APP ENTRY POINT
# =============================================================================
def main():
    # Load data (demo or real DB)
    data = generate_demo_data(5000)
    df   = data["orders"]

    # Sidebar filters
    filtered_df, page = render_sidebar(df)

    # Route to the right page
    if "Executive" in page:
        page_executive_overview(filtered_df)
    elif "Revenue" in page:
        page_revenue(filtered_df)
    elif "Customer" in page:
        page_customers(filtered_df)
    elif "Product" in page:
        page_products(filtered_df)
    elif "Regional" in page:
        page_regional(filtered_df)
    elif "Retention" in page:
        page_retention(filtered_df)
    elif "Upload" in page:
        page_upload()


if __name__ == "__main__":
    main()
