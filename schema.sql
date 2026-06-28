-- =============================================================================
-- database/schema.sql
-- E-Commerce Analytics — OLTP Database Schema (PostgreSQL)
-- =============================================================================
-- This is your "source of truth" database.
-- Tables mirror what a real e-commerce system stores.
-- Run this ONCE to create all tables.
-- =============================================================================

-- Drop and recreate cleanly (ONLY in dev — remove in production!)
DROP SCHEMA IF EXISTS ecommerce CASCADE;
CREATE SCHEMA ecommerce;
SET search_path TO ecommerce;

-- ─────────────────────────────────────────────────
-- 1. CUSTOMERS TABLE
-- Stores every registered customer.
-- ─────────────────────────────────────────────────
CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,          -- Auto-incrementing unique ID
    email         VARCHAR(255) UNIQUE NOT NULL, -- Must be unique, never null
    first_name    VARCHAR(100) NOT NULL,
    last_name     VARCHAR(100) NOT NULL,
    phone         VARCHAR(20),
    gender        VARCHAR(10) CHECK (gender IN ('Male', 'Female', 'Other')),
    date_of_birth DATE,
    city          VARCHAR(100),
    state         VARCHAR(100),
    country       VARCHAR(100) DEFAULT 'India',
    pincode       VARCHAR(20),
    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────────────
-- 2. PRODUCT CATEGORIES TABLE
-- Hierarchy: Electronics > Smartphones > iPhone 15
-- ─────────────────────────────────────────────────
CREATE TABLE categories (
    category_id   SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    parent_id     INT REFERENCES categories(category_id), -- Self-referencing for subcategories
    created_at    TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────────────
-- 3. PRODUCTS TABLE
-- Every item sold on the platform.
-- ─────────────────────────────────────────────────
CREATE TABLE products (
    product_id    SERIAL PRIMARY KEY,
    product_name  VARCHAR(255) NOT NULL,
    sku           VARCHAR(100) UNIQUE NOT NULL,  -- Stock Keeping Unit — unique product code
    category_id   INT REFERENCES categories(category_id),
    brand         VARCHAR(100),
    cost_price    DECIMAL(12, 2) NOT NULL,       -- What we paid the supplier
    selling_price DECIMAL(12, 2) NOT NULL,       -- What we sell it for
    weight_kg     DECIMAL(6, 2),
    is_active     BOOLEAN DEFAULT TRUE,
    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW(),
    CONSTRAINT positive_cost  CHECK (cost_price > 0),
    CONSTRAINT positive_price CHECK (selling_price > 0)
);

-- ─────────────────────────────────────────────────
-- 4. INVENTORY TABLE
-- Tracks stock levels per product per warehouse.
-- ─────────────────────────────────────────────────
CREATE TABLE inventory (
    inventory_id    SERIAL PRIMARY KEY,
    product_id      INT NOT NULL REFERENCES products(product_id),
    warehouse_code  VARCHAR(50) NOT NULL,
    quantity_on_hand INT NOT NULL DEFAULT 0,
    reorder_level   INT DEFAULT 50,
    last_updated    TIMESTAMP DEFAULT NOW(),
    CONSTRAINT non_negative_qty CHECK (quantity_on_hand >= 0)
);

-- ─────────────────────────────────────────────────
-- 5. ORDERS TABLE
-- One row = one order placed by a customer.
-- ─────────────────────────────────────────────────
CREATE TABLE orders (
    order_id        SERIAL PRIMARY KEY,
    customer_id     INT NOT NULL REFERENCES customers(customer_id),
    order_date      TIMESTAMP NOT NULL DEFAULT NOW(),
    status          VARCHAR(30) NOT NULL
                    CHECK (status IN ('Pending','Confirmed','Shipped','Delivered','Cancelled','Returned')),
    shipping_city   VARCHAR(100),
    shipping_state  VARCHAR(100),
    shipping_country VARCHAR(100),
    shipping_pincode VARCHAR(20),
    total_amount    DECIMAL(14, 2),        -- Calculated: sum of order items
    discount_amount DECIMAL(12, 2) DEFAULT 0,
    coupon_code     VARCHAR(50),
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);

-- ─────────────────────────────────────────────────
-- 6. ORDER ITEMS TABLE (the bridge/junction table)
-- One order can have multiple products.
-- Each row = one product line in one order.
-- ─────────────────────────────────────────────────
CREATE TABLE order_items (
    item_id         SERIAL PRIMARY KEY,
    order_id        INT NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id      INT NOT NULL REFERENCES products(product_id),
    quantity        INT NOT NULL CHECK (quantity > 0),
    unit_price      DECIMAL(12, 2) NOT NULL,   -- Price at time of purchase (may differ from current price)
    discount_pct    DECIMAL(5, 2) DEFAULT 0,   -- Item-level discount percentage
    line_total      DECIMAL(14, 2) GENERATED ALWAYS AS  -- Auto-calculated column
                    (quantity * unit_price * (1 - discount_pct / 100)) STORED
);

-- ─────────────────────────────────────────────────
-- 7. PAYMENTS TABLE
-- Tracks how each order was paid.
-- ─────────────────────────────────────────────────
CREATE TABLE payments (
    payment_id      SERIAL PRIMARY KEY,
    order_id        INT NOT NULL REFERENCES orders(order_id),
    payment_date    TIMESTAMP DEFAULT NOW(),
    amount          DECIMAL(14, 2) NOT NULL,
    payment_method  VARCHAR(50)
                    CHECK (payment_method IN ('Credit Card','Debit Card','UPI','Net Banking','COD','Wallet')),
    status          VARCHAR(20)
                    CHECK (status IN ('Pending','Success','Failed','Refunded')),
    transaction_id  VARCHAR(100) UNIQUE
);

-- ─────────────────────────────────────────────────
-- 8. RETURNS TABLE
-- When customers return products.
-- ─────────────────────────────────────────────────
CREATE TABLE returns (
    return_id       SERIAL PRIMARY KEY,
    order_id        INT NOT NULL REFERENCES orders(order_id),
    product_id      INT NOT NULL REFERENCES products(product_id),
    return_date     TIMESTAMP DEFAULT NOW(),
    reason          VARCHAR(255),
    quantity        INT NOT NULL DEFAULT 1,
    refund_amount   DECIMAL(12, 2),
    status          VARCHAR(30)
                    CHECK (status IN ('Requested','Approved','Rejected','Refunded'))
);

-- ─────────────────────────────────────────────────
-- 9. SHIPPING TABLE
-- Tracks delivery of each order.
-- ─────────────────────────────────────────────────
CREATE TABLE shipping (
    shipping_id     SERIAL PRIMARY KEY,
    order_id        INT NOT NULL REFERENCES orders(order_id),
    carrier         VARCHAR(100),              -- BlueDart, Delhivery, FedEx
    tracking_number VARCHAR(100),
    shipped_date    TIMESTAMP,
    delivered_date  TIMESTAMP,
    expected_date   TIMESTAMP,
    status          VARCHAR(30)
                    CHECK (status IN ('Not Shipped','In Transit','Delivered','Failed'))
);

-- ─────────────────────────────────────────────────
-- INDEXES (speed up common queries dramatically)
-- ─────────────────────────────────────────────────
CREATE INDEX idx_orders_customer     ON orders(customer_id);
CREATE INDEX idx_orders_date         ON orders(order_date);
CREATE INDEX idx_orders_status       ON orders(status);
CREATE INDEX idx_order_items_order   ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);
CREATE INDEX idx_payments_order      ON payments(order_id);
CREATE INDEX idx_returns_order       ON returns(order_id);
CREATE INDEX idx_inventory_product   ON inventory(product_id);

-- ─────────────────────────────────────────────────
-- TRIGGER: auto-update updated_at timestamps
-- ─────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_customers_updated
    BEFORE UPDATE ON customers
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

CREATE TRIGGER trg_products_updated
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_timestamp();

COMMENT ON TABLE customers IS 'All registered customers with demographics and location';
COMMENT ON TABLE orders IS 'Order headers — one row per order placed';
COMMENT ON TABLE order_items IS 'Line items within each order — products, qty, price';
COMMENT ON TABLE products IS 'Product catalog with pricing and category';
COMMENT ON TABLE payments IS 'Payment transactions linked to orders';
COMMENT ON TABLE returns IS 'Return requests and their status';
COMMENT ON TABLE shipping IS 'Shipment tracking for each order';
