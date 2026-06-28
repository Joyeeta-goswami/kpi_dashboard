"""
etl/pipeline.py
---------------
Reusable E-Commerce ETL Pipeline
Handles: Extract → Transform → Load for ANY e-commerce dataset.

To add a new data source: just add a new extractor function.
Everything else (cleaning, loading) stays the same.

Run with: python -m etl.pipeline
"""

import pandas as pd
import numpy as np
import logging
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from settings import (
    DATABASE_URL, RAW_DIR, CLEANED_DIR, CHUNK_SIZE, DATE_FORMAT
)

# ─── Logger Setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/pipeline.log"),
        logging.StreamHandler()          # Also print to terminal
    ]
)
log = logging.getLogger(__name__)


# =============================================================================
# EXTRACT LAYER — Read data from any source
# =============================================================================

class DataExtractor:
    """Reads raw data from CSV, Excel, or database."""

    @staticmethod
    def from_csv(filename: str, **kwargs) -> pd.DataFrame:
        """Load a CSV file from the raw data directory."""
        path = os.path.join(RAW_DIR, filename)
        log.info(f"Extracting: {path}")
        try:
            df = pd.read_csv(path, **kwargs)
            log.info(f"  → Loaded {len(df):,} rows, {len(df.columns)} columns")
            return df
        except FileNotFoundError:
            log.error(f"File not found: {path}")
            raise

    @staticmethod
    def from_excel(filename: str, sheet_name=0, **kwargs) -> pd.DataFrame:
        """Load an Excel file."""
        path = os.path.join(RAW_DIR, filename)
        log.info(f"Extracting Excel: {path} (sheet={sheet_name})")
        return pd.read_excel(path, sheet_name=sheet_name, **kwargs)

    @staticmethod
    def from_database(query: str, source_url: str) -> pd.DataFrame:
        """Read from another database (useful for migrating from MySQL)."""
        engine = create_engine(source_url)
        log.info(f"Extracting from database: {query[:60]}...")
        return pd.read_sql(query, engine)

    @staticmethod
    def from_directory(directory: str, file_pattern: str = "*.csv") -> pd.DataFrame:
        """Merge multiple CSV files from a folder into one DataFrame."""
        import glob
        files = glob.glob(os.path.join(RAW_DIR, directory, file_pattern))
        log.info(f"Found {len(files)} files matching {file_pattern}")
        dfs = [pd.read_csv(f) for f in files]
        return pd.concat(dfs, ignore_index=True)


# =============================================================================
# TRANSFORM LAYER — Clean and standardize data
# =============================================================================

class DataTransformer:
    """
    All data cleaning and transformation logic.
    Each method is independent and reusable.
    """

    @staticmethod
    def clean_customers(df: pd.DataFrame) -> pd.DataFrame:
        """Clean the customers dataset."""
        log.info("Transforming: customers")
        original_count = len(df)

        # 1. Standardize column names (lowercase, no spaces)
        df.columns = df.columns.str.lower().str.replace(" ", "_").str.strip()

        # 2. Drop complete duplicates
        df = df.drop_duplicates()

        # 3. Remove rows where email is missing (it's our unique identifier)
        df = df.dropna(subset=["email"])

        # 4. Normalize email (lowercase, strip whitespace)
        df["email"] = df["email"].str.lower().str.strip()

        # 5. Remove duplicate emails (keep first occurrence)
        df = df.drop_duplicates(subset=["email"], keep="first")

        # 6. Standardize names
        for col in ["first_name", "last_name", "city", "state", "country"]:
            if col in df.columns:
                df[col] = df[col].str.strip().str.title()

        # 7. Parse dates
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")

        # 8. Fill missing country with default
        df["country"] = df.get("country", pd.Series()).fillna("India")

        # 9. Validate gender values
        valid_genders = {"Male", "Female", "Other"}
        if "gender" in df.columns:
            df["gender"] = df["gender"].str.title()
            df.loc[~df["gender"].isin(valid_genders), "gender"] = "Other"

        # 10. Add age group
        if "date_of_birth" in df.columns:
            df["date_of_birth"] = pd.to_datetime(df["date_of_birth"], errors="coerce")
            today = pd.Timestamp.today()
            df["age"] = ((today - df["date_of_birth"]).dt.days / 365.25).astype("Int64")
            df["age_group"] = pd.cut(
                df["age"],
                bins=[0, 24, 34, 44, 54, 200],
                labels=["18-24", "25-34", "35-44", "45-54", "55+"]
            )

        removed = original_count - len(df)
        log.info(f"  → Cleaned: {len(df):,} rows ({removed} removed)")
        return df

    @staticmethod
    def clean_orders(df: pd.DataFrame) -> pd.DataFrame:
        """Clean the orders dataset."""
        log.info("Transforming: orders")

        df.columns = df.columns.str.lower().str.replace(" ", "_").str.strip()
        df = df.drop_duplicates(subset=["order_id"], keep="first")
        df = df.dropna(subset=["order_id", "customer_id"])

        # Parse order date
        df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
        df = df.dropna(subset=["order_date"])  # Drop rows with invalid dates

        # Standardize status values
        valid_statuses = {"Pending", "Confirmed", "Shipped", "Delivered", "Cancelled", "Returned"}
        if "status" in df.columns:
            df["status"] = df["status"].str.title()
            df.loc[~df["status"].isin(valid_statuses), "status"] = "Pending"

        # Ensure amounts are numeric
        for col in ["total_amount", "discount_amount"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
                df.loc[df[col] < 0, col] = 0   # No negative amounts

        log.info(f"  → Orders cleaned: {len(df):,} rows")
        return df

    @staticmethod
    def clean_products(df: pd.DataFrame) -> pd.DataFrame:
        """Clean the products dataset."""
        log.info("Transforming: products")

        df.columns = df.columns.str.lower().str.replace(" ", "_").str.strip()
        df = df.drop_duplicates(subset=["product_id"], keep="first")

        # Prices must be positive
        for col in ["cost_price", "selling_price"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=[col])
                df = df[df[col] > 0]

        # Add price band (useful for segmentation)
        if "selling_price" in df.columns:
            df["price_band"] = pd.cut(
                df["selling_price"],
                bins=[0, 500, 2000, float("inf")],
                labels=["Budget", "Mid-Range", "Premium"]
            )

        # Standardize text fields
        for col in ["product_name", "category", "brand"]:
            if col in df.columns:
                df[col] = df[col].str.strip().str.title()

        log.info(f"  → Products cleaned: {len(df):,} rows")
        return df

    @staticmethod
    def clean_order_items(df: pd.DataFrame) -> pd.DataFrame:
        """Clean order items dataset."""
        log.info("Transforming: order_items")

        df.columns = df.columns.str.lower().str.replace(" ", "_").str.strip()
        df = df.drop_duplicates()
        df = df.dropna(subset=["order_id", "product_id"])

        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1).astype(int)
        df = df[df["quantity"] > 0]

        df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
        df = df.dropna(subset=["unit_price"])
        df = df[df["unit_price"] > 0]

        df["discount_pct"] = pd.to_numeric(df.get("discount_pct", 0), errors="coerce").fillna(0)
        df["discount_pct"] = df["discount_pct"].clip(0, 100)

        # Calculate line total
        df["gross_revenue"]  = df["quantity"] * df["unit_price"]
        df["discount_amount"] = df["gross_revenue"] * (df["discount_pct"] / 100)
        df["net_revenue"]     = df["gross_revenue"] - df["discount_amount"]

        log.info(f"  → Order items cleaned: {len(df):,} rows")
        return df

    @staticmethod
    def enrich_with_star_schema(
        orders: pd.DataFrame,
        order_items: pd.DataFrame,
        customers: pd.DataFrame,
        products: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Build the fact_sales table by joining all cleaned datasets.
        This is the core transformation step.
        """
        log.info("Building fact_sales...")

        # Join order_items with orders
        fact = order_items.merge(
            orders[["order_id", "customer_id", "order_date", "status",
                    "shipping_city", "shipping_state", "shipping_country"]],
            on="order_id", how="left"
        )

        # Add date_key (YYYYMMDD integer format for star schema)
        fact["date_key"] = fact["order_date"].dt.strftime("%Y%m%d").astype(int)

        # Join with customers
        fact = fact.merge(
            customers[["customer_id", "customer_key"]],
            on="customer_id", how="left"
        )

        # Join with products (to get cost_price for profit calculation)
        fact = fact.merge(
            products[["product_id", "product_key", "cost_price"]],
            on="product_id", how="left"
        )

        # Calculate profit
        fact["cost_of_goods"] = fact["quantity"] * fact["cost_price"]
        fact["gross_profit"]  = fact["net_revenue"] - fact["cost_of_goods"]
        fact["order_status"]  = fact["status"]

        log.info(f"  → fact_sales built: {len(fact):,} rows")
        return fact


# =============================================================================
# LOAD LAYER — Push cleaned data to PostgreSQL
# =============================================================================

class DataLoader:
    """Loads cleaned DataFrames into PostgreSQL."""

    def __init__(self):
        self.engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)
        log.info(f"Connected to database: {DATABASE_URL[:40]}...")

    def load_table(
        self,
        df: pd.DataFrame,
        table_name: str,
        schema: str = "ecommerce",
        if_exists: str = "append",    # "replace" to overwrite, "append" to add
        chunk_size: int = CHUNK_SIZE
    ):
        """
        Load a DataFrame into a PostgreSQL table in chunks.
        Chunking prevents memory issues with large datasets.
        """
        log.info(f"Loading {len(df):,} rows → {schema}.{table_name}")

        df.to_sql(
            name=table_name,
            con=self.engine,
            schema=schema,
            if_exists=if_exists,
            index=False,
            chunksize=chunk_size,
            method="multi"             # Faster bulk insert
        )

        log.info(f"  ✓ Loaded successfully → {schema}.{table_name}")

    def save_to_csv(self, df: pd.DataFrame, filename: str):
        """Save cleaned data to the cleaned data directory (for debugging)."""
        path = os.path.join(CLEANED_DIR, filename)
        df.to_csv(path, index=False)
        log.info(f"  ✓ Saved cleaned file: {path}")

    def run_sql(self, sql: str):
        """Run a raw SQL statement (e.g., TRUNCATE before reload)."""
        with self.engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()


# =============================================================================
# PIPELINE ORCHESTRATOR — Run everything in order
# =============================================================================

class EcommercePipeline:
    """
    Main pipeline class. Run this to process all data end-to-end.

    To add a new dataset:
    1. Add an extract method in DataExtractor
    2. Add a clean method in DataTransformer
    3. Add a load step here in run()
    """

    def __init__(self):
        self.extractor   = DataExtractor()
        self.transformer = DataTransformer()
        self.loader      = DataLoader()
        self.start_time  = datetime.now()
        log.info("=" * 60)
        log.info("E-Commerce Analytics Pipeline — STARTING")
        log.info(f"Run started at: {self.start_time}")
        log.info("=" * 60)

    def run(self):
        """Execute the full ETL pipeline."""
        try:
            # ── STEP 1: Extract ──────────────────────────────────────────────
            log.info("\n[STEP 1] EXTRACT")
            raw_customers   = self.extractor.from_csv("customers.csv")
            raw_orders      = self.extractor.from_csv("orders.csv")
            raw_products    = self.extractor.from_csv("products.csv")
            raw_order_items = self.extractor.from_csv("order_items.csv")

            # ── STEP 2: Transform ─────────────────────────────────────────────
            log.info("\n[STEP 2] TRANSFORM")
            clean_customers   = self.transformer.clean_customers(raw_customers)
            clean_orders      = self.transformer.clean_orders(raw_orders)
            clean_products    = self.transformer.clean_products(raw_products)
            clean_order_items = self.transformer.clean_order_items(raw_order_items)

            # Save cleaned files (useful for debugging and audit trail)
            self.loader.save_to_csv(clean_customers,   "customers_clean.csv")
            self.loader.save_to_csv(clean_orders,      "orders_clean.csv")
            self.loader.save_to_csv(clean_products,    "products_clean.csv")
            self.loader.save_to_csv(clean_order_items, "order_items_clean.csv")

            # ── STEP 3: Load OLTP Tables ──────────────────────────────────────
            log.info("\n[STEP 3] LOAD — OLTP Tables")
            self.loader.load_table(clean_customers,   "customers",   "ecommerce", if_exists="replace")
            self.loader.load_table(clean_products,    "products",    "ecommerce", if_exists="replace")
            self.loader.load_table(clean_orders,      "orders",      "ecommerce", if_exists="replace")
            self.loader.load_table(clean_order_items, "order_items", "ecommerce", if_exists="replace")

            # ── STEP 4: Build Star Schema ─────────────────────────────────────
            log.info("\n[STEP 4] BUILD STAR SCHEMA")
            fact_sales = self.transformer.enrich_with_star_schema(
                clean_orders, clean_order_items, clean_customers, clean_products
            )
            self.loader.load_table(fact_sales, "fact_sales", "warehouse", if_exists="replace")

            # ── DONE ──────────────────────────────────────────────────────────
            elapsed = (datetime.now() - self.start_time).seconds
            log.info(f"\n{'=' * 60}")
            log.info(f"✓ Pipeline COMPLETE in {elapsed}s")
            log.info(f"{'=' * 60}\n")

        except Exception as e:
            log.error(f"Pipeline FAILED: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    pipeline = EcommercePipeline()
    pipeline.run()
