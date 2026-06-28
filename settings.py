"""
config/settings.py
------------------
Central configuration for the E-Commerce Analytics System.
All settings are read from environment variables (.env file),
so this system is 100% reusable across different datasets and environments.
"""

import os
from dotenv import load_dotenv

load_dotenv()  # Reads your .env file automatically

# ─── Database ─────────────────────────────────────────────────────────────────
DB_HOST     = os.getenv("DB_HOST",     "localhost")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME",     "ecommerce_dw")
DB_USER     = os.getenv("DB_USER",     "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_password")

DATABASE_URL = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ─── File Paths ───────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR      = os.path.join(BASE_DIR, "data")
RAW_DIR       = os.path.join(DATA_DIR, "raw")
CLEANED_DIR   = os.path.join(DATA_DIR, "cleaned")
WAREHOUSE_DIR = os.path.join(DATA_DIR, "warehouse")
REPORTS_DIR   = os.path.join(BASE_DIR, "reports", "output")

# ─── ETL Settings ─────────────────────────────────────────────────────────────
CHUNK_SIZE         = 10_000   # Process data in chunks (scalable for large datasets)
DATE_FORMAT        = "%Y-%m-%d"
CURRENCY           = "USD"
DEFAULT_COUNTRY    = "India"

# ─── KPI Thresholds (business rules — change without touching code) ────────────
CHURN_DAYS         = 90        # Customer inactive for 90 days = churned
REPEAT_PURCHASE_DAYS = 30      # Orders within 30 days = repeat purchase
HIGH_VALUE_CLV     = 5000      # CLV above $5000 = high-value customer
RETURN_RATE_ALERT  = 0.15      # Alert if return rate exceeds 15%

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL  = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE   = os.path.join(BASE_DIR, "logs", "pipeline.log")
