-- =============================================================================
-- database/star_schema.sql
-- E-Commerce Analytics — Star Schema (Data Warehouse / OLAP Layer)
-- =============================================================================
-- WHY STAR SCHEMA?
-- ─────────────────
-- Your OLTP tables (schema.sql) are great for WRITING data fast.
-- But for ANALYTICS, you need to join many tables every time → slow.
--
-- Star Schema solves this by pre-joining everything into:
--   • 1 FACT TABLE   → stores the numbers (what happened)
--   • N DIM TABLES   → stores the context (who, what, when, where)
--
-- Result: Analytics queries that are 10-100x faster.
-- =============================================================================

DROP SCHEMA IF EXISTS warehouse CASCADE;
CREATE SCHEMA warehouse;
SET search_path TO warehouse;

-- ─────────────────────────────────────────────────────────────────────────────
-- DIM_DATE — "When did it happen?"
-- Pre-populated with every date for the next 10 years.
-- This is the most important dimension in analytics.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE dim_date (
    date_key        INT PRIMARY KEY,            -- Surrogate key: 20240115 (YYYYMMDD format — easy to query)
    full_date       DATE NOT NULL,
    day_of_month    SMALLINT,                   -- 1–31
    day_name        VARCHAR(10),                -- Monday, Tuesday…
    day_of_week     SMALLINT,                   -- 1=Monday … 7=Sunday
    week_of_year    SMALLINT,                   -- 1–52
    month_num       SMALLINT,                   -- 1–12
    month_name      VARCHAR(10),                -- January, February…
    month_short     VARCHAR(5),                 -- Jan, Feb…
    quarter         SMALLINT,                   -- 1–4
    quarter_label   VARCHAR(6),                 -- Q1-2024, Q2-2024…
    year            SMALLINT,
    is_weekend      BOOLEAN,
    is_holiday      BOOLEAN DEFAULT FALSE,
    financial_year  VARCHAR(10)                 -- FY2024-25 (important for Indian businesses)
);

-- Populate dim_date for 2020–2030
INSERT INTO dim_date
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT             AS date_key,
    d                                        AS full_date,
    EXTRACT(DAY   FROM d)::SMALLINT         AS day_of_month,
    TO_CHAR(d, 'Day')                        AS day_name,
    EXTRACT(ISODOW FROM d)::SMALLINT        AS day_of_week,
    EXTRACT(WEEK  FROM d)::SMALLINT         AS week_of_year,
    EXTRACT(MONTH FROM d)::SMALLINT         AS month_num,
    TO_CHAR(d, 'Month')                      AS month_name,
    TO_CHAR(d, 'Mon')                        AS month_short,
    EXTRACT(QUARTER FROM d)::SMALLINT       AS quarter,
    'Q' || EXTRACT(QUARTER FROM d) || '-' || EXTRACT(YEAR FROM d) AS quarter_label,
    EXTRACT(YEAR  FROM d)::SMALLINT         AS year,
    EXTRACT(ISODOW FROM d) IN (6, 7)        AS is_weekend,
    FALSE                                    AS is_holiday,
    CASE
        WHEN EXTRACT(MONTH FROM d) >= 4
        THEN 'FY' || EXTRACT(YEAR FROM d) || '-' || (EXTRACT(YEAR FROM d)+1)
        ELSE 'FY' || (EXTRACT(YEAR FROM d)-1) || '-' || EXTRACT(YEAR FROM d)
    END                                      AS financial_year
FROM generate_series('2020-01-01'::DATE, '2030-12-31'::DATE, '1 day') AS d;

-- ─────────────────────────────────────────────────────────────────────────────
-- DIM_CUSTOMER — "Who bought?"
-- Snapshot of customer data at time of analysis.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE dim_customer (
    customer_key    SERIAL PRIMARY KEY,         -- Surrogate key (internal DW ID)
    customer_id     INT UNIQUE NOT NULL,        -- Natural key (from OLTP system)
    email           VARCHAR(255),
    full_name       VARCHAR(200),
    gender          VARCHAR(10),
    age_group       VARCHAR(20),                -- 18-24, 25-34, 35-44, 45-54, 55+
    city            VARCHAR(100),
    state           VARCHAR(100),
    country         VARCHAR(100),
    region          VARCHAR(50),                -- North, South, East, West
    signup_date     DATE,
    customer_segment VARCHAR(50),              -- New, Regular, VIP, At-Risk, Churned
    is_active       BOOLEAN DEFAULT TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- DIM_PRODUCT — "What was sold?"
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE dim_product (
    product_key     SERIAL PRIMARY KEY,
    product_id      INT UNIQUE NOT NULL,
    product_name    VARCHAR(255),
    sku             VARCHAR(100),
    category        VARCHAR(100),
    subcategory     VARCHAR(100),
    brand           VARCHAR(100),
    cost_price      DECIMAL(12, 2),
    selling_price   DECIMAL(12, 2),
    price_band      VARCHAR(20),               -- Budget (<500), Mid (500-2000), Premium (>2000)
    is_active       BOOLEAN DEFAULT TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- DIM_LOCATION — "Where did it ship to?"
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE dim_location (
    location_key    SERIAL PRIMARY KEY,
    city            VARCHAR(100),
    state           VARCHAR(100),
    country         VARCHAR(100),
    pincode         VARCHAR(20),
    region          VARCHAR(50),               -- North, South, East, West, Metro
    is_metro        BOOLEAN DEFAULT FALSE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- FACT_SALES — The Heart of the Star
-- Every row = one product sold in one order.
-- Contains only KEYS + MEASURES (numbers).
-- No descriptive text — that all lives in the dimension tables.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE fact_sales (
    sale_id             BIGSERIAL PRIMARY KEY,

    -- Foreign keys to dimensions (the "arms" of the star)
    date_key            INT NOT NULL REFERENCES dim_date(date_key),
    customer_key        INT NOT NULL REFERENCES dim_customer(customer_key),
    product_key         INT NOT NULL REFERENCES dim_product(product_key),
    location_key        INT NOT NULL REFERENCES dim_location(location_key),

    -- Natural keys (from source system — for tracing back if needed)
    order_id            INT NOT NULL,
    item_id             INT NOT NULL,

    -- MEASURES — the actual numbers analysts query
    quantity            INT NOT NULL,
    unit_price          DECIMAL(12, 2) NOT NULL,
    discount_pct        DECIMAL(5, 2) DEFAULT 0,
    gross_revenue       DECIMAL(14, 2),         -- quantity × unit_price
    discount_amount     DECIMAL(12, 2),         -- gross_revenue × discount_pct/100
    net_revenue         DECIMAL(14, 2),         -- gross_revenue - discount_amount
    cost_of_goods       DECIMAL(14, 2),         -- quantity × cost_price
    gross_profit        DECIMAL(14, 2),         -- net_revenue - cost_of_goods
    is_returned         BOOLEAN DEFAULT FALSE,
    payment_method      VARCHAR(50),
    order_status        VARCHAR(30)
);

-- Indexes on fact table (very important for query speed)
CREATE INDEX idx_fact_date      ON fact_sales(date_key);
CREATE INDEX idx_fact_customer  ON fact_sales(customer_key);
CREATE INDEX idx_fact_product   ON fact_sales(product_key);
CREATE INDEX idx_fact_location  ON fact_sales(location_key);
CREATE INDEX idx_fact_order     ON fact_sales(order_id);
CREATE INDEX idx_fact_returned  ON fact_sales(is_returned);

-- ─────────────────────────────────────────────────────────────────────────────
-- FACT_CUSTOMER_METRICS — Pre-aggregated customer-level KPIs
-- Updated by ETL pipeline periodically (daily/weekly).
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE fact_customer_metrics (
    metric_id           SERIAL PRIMARY KEY,
    customer_key        INT REFERENCES dim_customer(customer_key),
    snapshot_date       DATE NOT NULL,

    total_orders        INT DEFAULT 0,
    total_revenue       DECIMAL(14, 2) DEFAULT 0,
    avg_order_value     DECIMAL(12, 2) DEFAULT 0,
    days_since_last_order INT,
    first_order_date    DATE,
    last_order_date     DATE,

    -- RFM Scores (Recency, Frequency, Monetary)
    recency_score       SMALLINT CHECK (recency_score BETWEEN 1 AND 5),
    frequency_score     SMALLINT CHECK (frequency_score BETWEEN 1 AND 5),
    monetary_score      SMALLINT CHECK (monetary_score BETWEEN 1 AND 5),
    rfm_segment         VARCHAR(50),            -- Champions, Loyal, At-Risk, etc.

    clv_estimated       DECIMAL(14, 2),         -- Customer Lifetime Value estimate
    churn_risk_score    DECIMAL(5, 4)           -- 0.0 to 1.0 probability of churning
);

COMMENT ON TABLE fact_sales IS 'Grain: one row per product sold per order. Central fact table.';
COMMENT ON TABLE dim_date IS 'Date dimension pre-populated 2020-2030. Always join here for time analysis.';
COMMENT ON TABLE dim_customer IS 'Customer dimension with demographics and segmentation.';
COMMENT ON TABLE dim_product IS 'Product dimension with hierarchy and pricing bands.';
COMMENT ON TABLE dim_location IS 'Geographic dimension for regional analysis.';
