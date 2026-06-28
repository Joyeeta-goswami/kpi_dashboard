-- =============================================================================
-- kpis/kpi_queries.sql
-- E-Commerce Analytics — Complete KPI Query Library
-- =============================================================================
-- Every query below uses the warehouse.fact_sales Star Schema.
-- Each query is commented line-by-line so you understand every part.
-- =============================================================================

SET search_path TO warehouse;

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 1: TOTAL REVENUE — How much money came in?
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    SUM(net_revenue)                              AS total_revenue,
    SUM(gross_revenue)                            AS gross_revenue,
    SUM(discount_amount)                          AS total_discounts_given,
    ROUND(SUM(discount_amount)/SUM(gross_revenue)*100, 2) AS discount_pct_of_gross
FROM fact_sales
WHERE order_status NOT IN ('Cancelled', 'Returned');
-- Only count revenue that actually completed (not cancelled orders)

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 2: GROSS PROFIT & PROFIT MARGIN — Are we actually making money?
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    SUM(net_revenue)                              AS total_revenue,
    SUM(cost_of_goods)                            AS total_cogs,
    SUM(gross_profit)                             AS gross_profit,
    ROUND(SUM(gross_profit) / NULLIF(SUM(net_revenue), 0) * 100, 2) AS gross_margin_pct
    -- NULLIF prevents division by zero (safety guard)
FROM fact_sales
WHERE order_status = 'Delivered';

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 3: AVERAGE ORDER VALUE (AOV) — How much does each order earn?
-- ─────────────────────────────────────────────────────────────────────────────
WITH order_totals AS (
    -- First aggregate to order level (since fact has one row per item)
    SELECT
        order_id,
        SUM(net_revenue) AS order_value
    FROM fact_sales
    WHERE order_status NOT IN ('Cancelled', 'Returned')
    GROUP BY order_id
)
SELECT
    COUNT(order_id)                AS total_orders,
    ROUND(AVG(order_value), 2)     AS average_order_value,
    ROUND(MIN(order_value), 2)     AS min_order_value,
    ROUND(MAX(order_value), 2)     AS max_order_value,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY order_value), 2) AS median_order_value
FROM order_totals;

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 4: MONTHLY REVENUE GROWTH — Is the business growing?
-- ─────────────────────────────────────────────────────────────────────────────
WITH monthly AS (
    SELECT
        d.year,
        d.month_num,
        d.month_short,
        d.month_name,
        SUM(fs.net_revenue) AS revenue
    FROM fact_sales fs
    JOIN dim_date d ON fs.date_key = d.date_key
    WHERE fs.order_status NOT IN ('Cancelled', 'Returned')
    GROUP BY d.year, d.month_num, d.month_short, d.month_name
)
SELECT
    year,
    month_num,
    month_short || ' ' || year      AS period,
    revenue,
    LAG(revenue) OVER (ORDER BY year, month_num) AS prev_month_revenue,
    -- LAG() looks at the previous row's value (previous month)
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY year, month_num))
        / NULLIF(LAG(revenue) OVER (ORDER BY year, month_num), 0) * 100
    , 2)                            AS mom_growth_pct
    -- MoM = Month-over-Month growth percentage
FROM monthly
ORDER BY year, month_num;

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 5: TOP 10 SELLING PRODUCTS (by revenue)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    dp.product_name,
    dp.category,
    dp.brand,
    COUNT(DISTINCT fs.order_id)     AS orders_count,
    SUM(fs.quantity)                AS units_sold,
    ROUND(SUM(fs.net_revenue), 2)   AS total_revenue,
    ROUND(SUM(fs.gross_profit), 2)  AS total_profit,
    ROUND(SUM(fs.gross_profit) / NULLIF(SUM(fs.net_revenue), 0) * 100, 2) AS margin_pct,
    -- RANK gives the same rank to ties, DENSE_RANK doesn't skip numbers after ties
    RANK() OVER (ORDER BY SUM(fs.net_revenue) DESC) AS revenue_rank
FROM fact_sales fs
JOIN dim_product dp ON fs.product_key = dp.product_key
WHERE fs.order_status = 'Delivered'
GROUP BY dp.product_name, dp.category, dp.brand
ORDER BY total_revenue DESC
LIMIT 10;

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 6: REPEAT CUSTOMER RATE — How many customers come back?
-- ─────────────────────────────────────────────────────────────────────────────
WITH customer_order_counts AS (
    SELECT
        customer_key,
        COUNT(DISTINCT order_id) AS num_orders
    FROM fact_sales
    WHERE order_status NOT IN ('Cancelled')
    GROUP BY customer_key
),
segmented AS (
    SELECT
        num_orders,
        CASE
            WHEN num_orders = 1 THEN 'One-time'
            WHEN num_orders BETWEEN 2 AND 3 THEN 'Occasional (2-3)'
            WHEN num_orders BETWEEN 4 AND 6 THEN 'Regular (4-6)'
            ELSE 'Loyal (7+)'
        END AS customer_type,
        COUNT(*) AS customer_count
    FROM customer_order_counts
    GROUP BY num_orders,
        CASE
            WHEN num_orders = 1 THEN 'One-time'
            WHEN num_orders BETWEEN 2 AND 3 THEN 'Occasional (2-3)'
            WHEN num_orders BETWEEN 4 AND 6 THEN 'Regular (4-6)'
            ELSE 'Loyal (7+)'
        END
)
SELECT
    customer_type,
    SUM(customer_count)           AS customers,
    ROUND(SUM(customer_count) * 100.0 / SUM(SUM(customer_count)) OVER (), 2) AS pct_of_customers
FROM segmented
GROUP BY customer_type
ORDER BY MIN(num_orders);

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 7: CUSTOMER LIFETIME VALUE (CLV)
-- CLV = Average Order Value × Purchase Frequency × Customer Lifespan
-- ─────────────────────────────────────────────────────────────────────────────
WITH customer_stats AS (
    SELECT
        fs.customer_key,
        MIN(d.full_date)             AS first_purchase_date,
        MAX(d.full_date)             AS last_purchase_date,
        COUNT(DISTINCT fs.order_id)  AS total_orders,
        SUM(fs.net_revenue)          AS total_spent,
        -- Days active = span from first to last purchase
        MAX(d.full_date) - MIN(d.full_date) AS days_active
    FROM fact_sales fs
    JOIN dim_date d ON fs.date_key = d.date_key
    WHERE fs.order_status NOT IN ('Cancelled', 'Returned')
    GROUP BY fs.customer_key
)
SELECT
    dc.customer_key,
    dc.full_name,
    dc.city,
    dc.customer_segment,
    cs.total_orders,
    ROUND(cs.total_spent, 2)                       AS total_spent,
    ROUND(cs.total_spent / NULLIF(cs.total_orders, 0), 2) AS avg_order_value,
    cs.days_active,
    -- Annualize CLV: (total spent / years active) projected for 3 years
    ROUND(
        cs.total_spent / NULLIF(cs.days_active, 0) * 365 * 3
    , 2)                                           AS clv_3yr_estimate
FROM customer_stats cs
JOIN dim_customer dc ON cs.customer_key = dc.customer_key
ORDER BY clv_3yr_estimate DESC
LIMIT 100;

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 8: RETURN RATE — How many products are being returned?
-- A high return rate signals product quality or mismatch problems.
-- ─────────────────────────────────────────────────────────────────────────────
WITH delivered_and_returned AS (
    SELECT
        dp.category,
        dp.product_name,
        COUNT(CASE WHEN fs.order_status = 'Delivered' THEN 1 END) AS delivered_orders,
        COUNT(CASE WHEN fs.order_status = 'Returned'  THEN 1 END) AS returned_orders,
        SUM(CASE WHEN fs.order_status = 'Returned'  THEN fs.net_revenue ELSE 0 END) AS returned_revenue
    FROM fact_sales fs
    JOIN dim_product dp ON fs.product_key = dp.product_key
    GROUP BY dp.category, dp.product_name
)
SELECT
    category,
    product_name,
    delivered_orders,
    returned_orders,
    ROUND(returned_revenue, 2)            AS returned_revenue,
    ROUND(
        returned_orders::NUMERIC /
        NULLIF(delivered_orders + returned_orders, 0) * 100
    , 2)                                  AS return_rate_pct
FROM delivered_and_returned
WHERE delivered_orders > 10           -- Only show products with enough volume
ORDER BY return_rate_pct DESC
LIMIT 20;

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 9: REGION-WISE SALES BREAKDOWN
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    dl.region,
    dl.state,
    COUNT(DISTINCT fs.order_id)     AS total_orders,
    COUNT(DISTINCT fs.customer_key) AS unique_customers,
    ROUND(SUM(fs.net_revenue), 2)   AS total_revenue,
    ROUND(AVG(fs.net_revenue), 2)   AS avg_order_value,
    ROUND(SUM(fs.gross_profit), 2)  AS total_profit,
    ROUND(SUM(fs.net_revenue) / SUM(SUM(fs.net_revenue)) OVER () * 100, 2) AS revenue_share_pct
    -- Window function: each row shows its share of total revenue
FROM fact_sales fs
JOIN dim_location dl ON fs.location_key = dl.location_key
WHERE fs.order_status = 'Delivered'
GROUP BY dl.region, dl.state
ORDER BY total_revenue DESC;

-- ─────────────────────────────────────────────────────────────────────────────
-- KPI 10: DAILY REVENUE TREND (last 90 days)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT
    d.full_date,
    d.day_name,
    d.is_weekend,
    COUNT(DISTINCT fs.order_id)             AS orders,
    ROUND(SUM(fs.net_revenue), 2)           AS daily_revenue,
    -- 7-day rolling average (smooths out daily spikes)
    ROUND(AVG(SUM(fs.net_revenue)) OVER (
        ORDER BY d.full_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2)                                   AS rolling_7d_avg,
    -- Running total (cumulative)
    ROUND(SUM(SUM(fs.net_revenue)) OVER (
        ORDER BY d.full_date
        ROWS UNBOUNDED PRECEDING
    ), 2)                                   AS cumulative_revenue
FROM fact_sales fs
JOIN dim_date d ON fs.date_key = d.date_key
WHERE
    fs.order_status NOT IN ('Cancelled', 'Returned')
    AND d.full_date >= CURRENT_DATE - INTERVAL '90 days'
GROUP BY d.full_date, d.day_name, d.is_weekend
ORDER BY d.full_date;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADVANCED: COHORT RETENTION ANALYSIS
-- "Of customers who first purchased in Month X, what % returned in Month X+1, X+2..."
-- This is the gold standard for understanding loyalty.
-- ─────────────────────────────────────────────────────────────────────────────
WITH first_purchase AS (
    -- Step 1: Find each customer's first ever purchase month
    SELECT
        fs.customer_key,
        DATE_TRUNC('month', MIN(d.full_date)) AS cohort_month
    FROM fact_sales fs
    JOIN dim_date d ON fs.date_key = d.date_key
    WHERE fs.order_status NOT IN ('Cancelled')
    GROUP BY fs.customer_key
),
customer_activity AS (
    -- Step 2: Find every month each customer was active
    SELECT DISTINCT
        fs.customer_key,
        DATE_TRUNC('month', d.full_date) AS activity_month
    FROM fact_sales fs
    JOIN dim_date d ON fs.date_key = d.date_key
    WHERE fs.order_status NOT IN ('Cancelled')
),
cohort_data AS (
    -- Step 3: For each customer, calculate how many months after cohort they were active
    SELECT
        fp.cohort_month,
        EXTRACT(YEAR FROM AGE(ca.activity_month, fp.cohort_month)) * 12
        + EXTRACT(MONTH FROM AGE(ca.activity_month, fp.cohort_month)) AS months_since_first
        -- months_since_first=0 means cohort month itself, =1 means one month later, etc.
    FROM first_purchase fp
    JOIN customer_activity ca ON fp.customer_key = ca.customer_key
)
SELECT
    TO_CHAR(cohort_month, 'Mon YYYY')  AS cohort,
    months_since_first                  AS month_number,
    COUNT(*)                            AS customers_active,
    -- Retention rate = active in this period / total cohort size
    ROUND(
        COUNT(*) * 100.0 /
        FIRST_VALUE(COUNT(*)) OVER (
            PARTITION BY cohort_month
            ORDER BY months_since_first
        )
    , 1)                                AS retention_pct
FROM cohort_data
GROUP BY cohort_month, months_since_first
ORDER BY cohort_month, months_since_first;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADVANCED: RFM SEGMENTATION
-- Recency: How recently did the customer buy?
-- Frequency: How often do they buy?
-- Monetary: How much do they spend?
-- ─────────────────────────────────────────────────────────────────────────────
WITH rfm_raw AS (
    SELECT
        fs.customer_key,
        MAX(d.full_date)                     AS last_purchase_date,
        CURRENT_DATE - MAX(d.full_date)      AS recency_days,
        COUNT(DISTINCT fs.order_id)          AS frequency,
        SUM(fs.net_revenue)                  AS monetary
    FROM fact_sales fs
    JOIN dim_date d ON fs.date_key = d.date_key
    WHERE fs.order_status NOT IN ('Cancelled', 'Returned')
    GROUP BY fs.customer_key
),
rfm_scores AS (
    SELECT
        customer_key,
        recency_days,
        frequency,
        ROUND(monetary, 2) AS monetary,
        -- NTILE(5) divides customers into 5 equal groups (quintiles)
        -- For recency: lower days = better = higher score (hence 6 - NTILE)
        6 - NTILE(5) OVER (ORDER BY recency_days DESC)  AS r_score,
        NTILE(5) OVER (ORDER BY frequency)              AS f_score,
        NTILE(5) OVER (ORDER BY monetary)               AS m_score
    FROM rfm_raw
)
SELECT
    rs.*,
    dc.full_name,
    dc.email,
    -- Combine RFM into a segment label
    CASE
        WHEN r_score >= 4 AND f_score >= 4 AND m_score >= 4 THEN 'Champions'
        WHEN r_score >= 3 AND f_score >= 3                  THEN 'Loyal Customers'
        WHEN r_score >= 4 AND f_score <= 2                  THEN 'Recent Customers'
        WHEN r_score >= 3 AND f_score >= 1 AND m_score >= 3 THEN 'Potential Loyalists'
        WHEN r_score <= 2 AND f_score >= 4                  THEN 'At Risk'
        WHEN r_score <= 2 AND f_score <= 2 AND m_score <= 2 THEN 'Lost'
        WHEN m_score >= 4                                    THEN 'Big Spenders'
        ELSE 'Needs Attention'
    END AS rfm_segment
FROM rfm_scores rs
JOIN dim_customer dc ON rs.customer_key = dc.customer_key
ORDER BY r_score DESC, f_score DESC, m_score DESC;
