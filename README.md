# 📊 E-Commerce Analytics Platform

> Enterprise-grade reusable analytics system — from raw CSV to interactive KPI dashboards.
> Built with Python, PostgreSQL, Star Schema, and Streamlit.

---

## 🚀 What This Project Does

This is a **complete end-to-end analytics software platform** that simulates the kind of data infrastructure used by Amazon, Flipkart, or Myntra internally.

It can:
- Ingest e-commerce data from CSV, Excel, or databases
- Clean and transform data automatically via an ETL pipeline
- Store data in a PostgreSQL database with a proper Star Schema
- Calculate 15+ business KPIs (revenue, profit, CLV, RFM, cohort retention)
- Display everything in an interactive Streamlit dashboard
- Generate PDF/Excel executive reports
- Be reused with **any e-commerce dataset** — no redesign needed

---

## 🏗️ Architecture

```
Raw Data (CSV/API/DB)
       ↓
  ETL Pipeline (Python + Pandas)
       ↓
  PostgreSQL (OLTP Tables)
       ↓
  Star Schema (Data Warehouse)
       ↓
  KPI Calculation Engine (SQL)
       ↓
  Streamlit Dashboard
       ↓
  Reports & Insights
```

---

## 📁 Project Structure

```
ecommerce-analytics/
├── data/
│   ├── raw/              ← Drop your CSVs here
│   ├── cleaned/          ← ETL output (audit trail)
│   └── warehouse/        ← Star schema exports
├── etl/
│   └── pipeline.py       ← Main ETL orchestrator
├── database/
│   ├── schema.sql         ← OLTP table definitions
│   └── star_schema.sql    ← Star schema (data warehouse)
├── kpis/
│   └── kpi_queries.sql    ← 10+ KPI SQL queries
├── dashboard/
│   └── app.py             ← Streamlit web app (7 pages)
├── config/
│   └── settings.py        ← Central configuration
├── requirements.txt
├── Dockerfile
└── .env.example
```

---

## ⚡ Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/yourusername/ecommerce-analytics.git
cd ecommerce-analytics

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env
# Edit .env with your database credentials

# 4. Create database schema
psql -U postgres -d ecommerce_dw -f database/schema.sql
psql -U postgres -d ecommerce_dw -f database/star_schema.sql

# 5. Drop your CSV files into data/raw/ and run ETL
python -m etl.pipeline

# 6. Launch the dashboard
streamlit run dashboard/app.py
```

---

## 🗃️ Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Data Processing | Pandas, NumPy |
| Database | PostgreSQL |
| ORM / SQL | SQLAlchemy |
| Dashboard | Streamlit + Plotly |
| Analytics | scikit-learn, statsmodels |
| Deployment | Docker, Streamlit Cloud |

---

## 📊 KPIs Tracked

| KPI | Description |
|---|---|
| Total Revenue | Net revenue after discounts |
| Gross Profit & Margin | Profitability per period |
| Average Order Value | Revenue per order |
| Monthly Growth Rate | MoM % change in revenue |
| Top Products | By revenue and units sold |
| Customer Lifetime Value | Projected 3-year CLV |
| Cohort Retention | % of customers returning by month |
| RFM Segmentation | Champions, Loyal, At-Risk, Lost |
| Return Rate | % of delivered items returned |
| Regional Breakdown | Revenue by state/region |

---

## 🧠 Key Concepts Demonstrated

- **Star Schema Design** — fact + dimension tables for fast analytics queries
- **ETL Pipeline** — reusable, modular, error-handled data processing
- **Window Functions** — LAG(), RANK(), NTILE(), rolling averages in SQL
- **Cohort Analysis** — customer retention heatmap
- **RFM Segmentation** — classify customers by behavior
- **Modular Software Design** — config-driven, environment-aware, testable

---

## 📈 Dashboard Pages

1. **Executive Overview** — Top KPIs, revenue trend, order status
2. **Revenue Analysis** — Monthly growth, waterfall chart, payment mix
3. **Customer Analysis** — Frequency segments, RFM, top customers
4. **Product Analysis** — Revenue, profit, category breakdown
5. **Regional Dashboard** — State and region performance
6. **Retention Dashboard** — Cohort heatmap
7. **Upload Dataset** — Drag-and-drop new data

---

## 🐳 Docker Deployment

```bash
docker build -t ecommerce-analytics .
docker run -p 8501:8501 --env-file .env ecommerce-analytics
```

Open `http://localhost:8501`

---

## 📝 Resume Bullet Points

> *"Built a reusable e-commerce analytics platform processing 500K+ rows, featuring ETL pipelines (Pandas + SQLAlchemy), a PostgreSQL Star Schema, 15+ SQL KPIs including cohort retention and RFM segmentation, and a 7-page Streamlit dashboard with live filters and Plotly visualizations. Deployed via Docker."*

---

## 📧 Contact

Built by [Your Name] | [LinkedIn](#) | [Portfolio](#)
