"""
schema_mapper.py
-----------------
Column-mapping / schema-detection layer for uploaded datasets.

Uploaded CSVs rarely use this project's exact internal column names
(order_id, customer_id, order_date, ...). This module normalizes whatever
column names a file has, maps them onto the project's canonical schema using
a configurable alias table, flags anything it isn't confident about for the
user to confirm, and derives the revenue/profit columns the dashboard needs
using the same formulas already used elsewhere in this project (see
pipeline.py: DataTransformer.clean_order_items and app.py's demo-data
generation).

Nothing here talks to Streamlit directly except the small `render_mapping_ui`
helper at the bottom, which is the only place that needs `st`. Everything
else is plain pandas so it stays testable and reusable from the ETL pipeline
too, if that's ever wired up to uploaded files instead of RAW_DIR CSVs.

Pipeline:
    raw df
      -> normalize_column_names(df)        # formatting only, no renaming
      -> detect_and_map_columns(df)         # alias lookup -> mapping + confidence
      -> (user confirms ambiguous ones via render_mapping_ui, if any)
      -> apply_column_mapping(df, mapping)  # renames to canonical names
      -> derive_missing_columns(df)         # gross_revenue, net_revenue, ...
      -> validate_required_columns(df)      # raises SchemaValidationError if unusable
"""

from __future__ import annotations

import re
import difflib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


# =============================================================================
# CANONICAL SCHEMA
# =============================================================================
# Required: the dashboard cannot function at all without these.
REQUIRED_COLUMNS = ["order_id", "customer_id", "order_date"]

# Optional: dashboard pages degrade gracefully (fall back to "Unknown" / skip
# a chart) if these are missing — see TEXT_DEFAULTS below.
OPTIONAL_COLUMNS = [
    "product", "category", "city", "state", "region",
    "payment_method", "status", "cost_price",
]

# Derived: calculated from other columns if not present directly, using the
# same formulas as the demo-data generator and pipeline.py's order_items
# cleaning (quantity * unit_price, etc.).
DERIVED_COLUMNS = [
    "quantity", "unit_price", "discount_pct",
    "gross_revenue", "discount_amount", "net_revenue", "gross_profit",
]

TEXT_DEFAULTS = {
    "product": "Unknown", "category": "Unknown", "city": "Unknown",
    "state": "Unknown", "region": "Unknown", "payment_method": "Unknown",
    "status": "Delivered",
}

# ── Alias table ──────────────────────────────────────────────────────────────
# Keys are canonical column names; values are the *normalized* forms (see
# normalize_text below) of names a raw file might use instead. The canonical
# name itself is always implicitly included.
COLUMN_ALIASES: dict[str, list[str]] = {
    "order_id": [
        "order_id", "id_order", "order_number", "order_no", "orderid", "order",
    ],
    "customer_id": [
        "customer_id", "id_customer", "customer", "customer_number",
        "customerid", "client_id", "cust_id",
    ],
    "order_date": [
        "order_date", "date_order", "order_date_time", "order_datetime",
        "date", "purchase_date", "orderdate",
    ],
    "product": [
        "product", "product_name", "item", "item_name", "productname",
    ],
    "category": [
        "category", "product_category", "category_name", "product_type",
    ],
    "quantity": [
        "quantity", "qty", "units", "item_quantity", "order_quantity",
    ],
    "unit_price": [
        "unit_price", "price", "selling_price", "item_price", "unitprice",
    ],
    "discount_pct": [
        "discount_pct", "discount", "discount_percent", "discount_percentage",
        "discountpct",
    ],
    "cost_price": [
        "cost_price", "costprice", "cost", "unit_cost",
    ],
    "payment_method": [
        "payment_method", "payment", "payment_type", "payment_mode",
        "paymentmethod",
    ],
    "status": [
        "status", "order_status", "order_state", "orderstatus",
    ],
    "city": [
        "city", "customer_city", "shipping_city",
    ],
    "state": [
        "state", "customer_state", "shipping_state",
    ],
    "region": [
        "region", "sales_region", "geographic_region",
    ],
}

# Columns that are easy to confuse with each other because they share
# substrings (e.g. "id"). Exact alias matches are always safe — this only
# matters for the fuzzy fallback, where we refuse to suggest one of a pair
# for the other's raw name even at reasonably high similarity.
CONFUSABLE_PAIRS = {
    frozenset({"order_id", "customer_id"}),
    frozenset({"unit_price", "cost_price"}),
    frozenset({"city", "state"}),
    frozenset({"state", "region"}),
}

FUZZY_THRESHOLD = 0.82  # difflib ratio; below this we don't even suggest it


# =============================================================================
# STEP 1 — Formatting normalization (no renaming yet)
# =============================================================================
def normalize_text(name: str) -> str:
    """lowercase / strip / spaces+dashes -> underscores / drop stray punctuation."""
    name = str(name).strip().lower()
    name = re.sub(r"[\s\-]+", "_", name)
    name = re.sub(r"[^a-z0-9_]", "", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name


def normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of df with column *formatting* normalized (not mapped)."""
    out = df.copy()
    out.columns = [normalize_text(c) for c in out.columns]
    return out


# =============================================================================
# STEP 2 — Schema detection / mapping
# =============================================================================
@dataclass
class ColumnMapping:
    raw_column: str
    canonical: str | None          # None if nothing plausible was found
    confidence: str                 # "High" | "Medium" | "Low"
    candidates: list[str] = field(default_factory=list)  # for ambiguous cases


# Build a reverse lookup: normalized alias -> canonical name. We validate at
# import time that no alias is claimed by two canonical columns — that would
# be exactly the kind of dangerous, silent mis-mapping requirement #4 warns
# against, so we fail loudly instead.
def _build_alias_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in {canonical, *aliases}:
            norm = normalize_text(alias)
            if norm in lookup and lookup[norm] != canonical:
                raise ValueError(
                    f"Alias '{norm}' is claimed by both '{lookup[norm]}' and "
                    f"'{canonical}' in COLUMN_ALIASES — fix the alias table."
                )
            lookup[norm] = canonical
    return lookup


_ALIAS_LOOKUP = _build_alias_lookup()


def _is_confusable(a: str, b: str) -> bool:
    return frozenset({a, b}) in CONFUSABLE_PAIRS


def detect_and_map_columns(df: pd.DataFrame) -> list[ColumnMapping]:
    """
    Work out a canonical mapping for every (already formatting-normalized)
    column in df. Exact alias matches are always "High" confidence and never
    second-guessed. Only when a column has no exact alias do we fall back to
    a conservative fuzzy match, which is at best "Medium"/"Low" confidence
    and always left for the user to confirm.

    Returns one ColumnMapping per raw column (raw columns that don't match
    anything get canonical=None and should just be left alone / ignored).
    """
    results: list[ColumnMapping] = []
    claimed: dict[str, str] = {}  # canonical -> raw_column already assigned to it

    raw_columns = list(df.columns)

    # Pass 1: exact alias matches (safe, high-confidence, priority)
    unresolved = []
    for raw in raw_columns:
        canonical = _ALIAS_LOOKUP.get(raw)
        if canonical is None:
            unresolved.append(raw)
            continue
        if canonical in claimed:
            # Two raw columns both exactly match the same canonical name —
            # a genuine duplicate-candidate situation. Flag both as Low so
            # the user picks, rather than silently keeping the first.
            results.append(ColumnMapping(
                raw, canonical, "Low",
                candidates=[claimed[canonical], raw],
            ))
            # Retroactively downgrade the one we'd already accepted.
            for r in results:
                if r.raw_column == claimed[canonical]:
                    r.confidence = "Low"
                    r.candidates = [claimed[canonical], raw]
            continue
        claimed[canonical] = raw
        results.append(ColumnMapping(raw, canonical, "High"))

    # Pass 2: conservative fuzzy fallback for whatever's left, against
    # canonical names that haven't already been claimed by an exact match.
    available_canonicals = [c for c in COLUMN_ALIASES if c not in claimed]
    for raw in unresolved:
        best_canonical, best_score = None, 0.0
        for canonical in available_canonicals:
            all_names = {canonical, *COLUMN_ALIASES[canonical]}
            score = max(
                difflib.SequenceMatcher(None, raw, normalize_text(n)).ratio()
                for n in all_names
            )
            if score > best_score:
                best_canonical, best_score = canonical, score

        if best_canonical is None or best_score < FUZZY_THRESHOLD:
            results.append(ColumnMapping(raw, None, "Low"))
            continue

        # Refuse a confusable mapping outright (e.g. never silently suggest
        # customer_id for a column that's ambiguous with order_id).
        if any(_is_confusable(best_canonical, other) for other in available_canonicals
               if other != best_canonical):
            results.append(ColumnMapping(
                raw, best_canonical,
                "Medium" if best_score >= 0.9 else "Low",
                candidates=[best_canonical],
            ))
            continue

        confidence = "Medium" if best_score >= 0.9 else "Low"
        results.append(ColumnMapping(raw, best_canonical, confidence))

    return results


def apply_column_mapping(df: pd.DataFrame, mappings: list[ColumnMapping]) -> pd.DataFrame:
    """Rename columns per the (user-confirmed) mappings. Unmapped columns are dropped
    from the canonical frame but the originals are left untouched by the caller
    if it wants to keep them around for reference."""
    rename = {m.raw_column: m.canonical for m in mappings if m.canonical}
    unmapped = [m.raw_column for m in mappings if m.canonical is None]
    out = df.rename(columns=rename)
    # Drop columns nothing matched — they're safely ignored, not just left
    # cluttering the canonical frame under their original raw name.
    out = out.drop(columns=[c for c in unmapped if c in out.columns], errors="ignore")
    # If confirmation left two raw columns pointing at the same canonical
    # name (shouldn't happen after the UI step, but be defensive), keep the
    # first and drop the rest rather than crashing on a duplicate column.
    out = out.loc[:, ~out.columns.duplicated(keep="first")]
    return out


# =============================================================================
# STEP 3 — Derive missing revenue/profit columns
# =============================================================================
# Formulas mirror pipeline.py (DataTransformer.clean_order_items) and the
# demo-data generator in app.py exactly, so uploaded data and demo data
# behave identically once they reach the dashboard pages.
def derive_missing_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    df = df.copy()
    notes: list[str] = []

    if "quantity" not in df.columns:
        df["quantity"] = 1
        notes.append("No quantity column found — assumed 1 unit per row.")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(1)

    if "unit_price" in df.columns:
        df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")

    if "discount_pct" not in df.columns:
        df["discount_pct"] = 0.0
        notes.append("No discount_pct column found — assumed 0% discount.")
    df["discount_pct"] = pd.to_numeric(df["discount_pct"], errors="coerce").fillna(0)

    if "gross_revenue" not in df.columns:
        if "unit_price" not in df.columns:
            raise SchemaValidationError(
                "Can't calculate revenue: no gross_revenue, net_revenue, "
                "total_amount, or unit_price column was found or mapped.",
                missing=["gross_revenue (or unit_price)"],
                detected=list(df.columns),
            )
        df["gross_revenue"] = df["quantity"] * df["unit_price"]
        notes.append("gross_revenue calculated as quantity x unit_price.")

    if "discount_amount" not in df.columns:
        df["discount_amount"] = df["gross_revenue"] * df["discount_pct"] / 100
        notes.append("discount_amount calculated as gross_revenue x discount_pct / 100.")

    if "net_revenue" not in df.columns:
        df["net_revenue"] = df["gross_revenue"] - df["discount_amount"]
        notes.append("net_revenue calculated as gross_revenue - discount_amount.")

    if "gross_profit" not in df.columns:
        if "cost_price" in df.columns:
            df["cost_price"] = pd.to_numeric(df["cost_price"], errors="coerce")
            df["gross_profit"] = df["net_revenue"] - (df["quantity"] * df["cost_price"])
            notes.append("gross_profit calculated as net_revenue - (quantity x cost_price).")
        else:
            df["cost_price"] = np.nan
            df["gross_profit"] = np.nan
            notes.append(
                "No cost_price column found — gross_profit and margin will show as 0."
            )

    return df, notes


def fill_optional_defaults(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Fill OPTIONAL_COLUMNS that are missing with their documented default,
    so the dashboard's group-by charts never crash on a missing column."""
    df = df.copy()
    notes = []
    filled = []
    for col, default in TEXT_DEFAULTS.items():
        if col not in df.columns:
            df[col] = default
            filled.append(col)
        else:
            df[col] = df[col].fillna(default).astype(str).str.strip()
    if "status" in df.columns:
        df["status"] = df["status"].str.title()
    if filled:
        notes.append("Columns not found, filled with 'Unknown': " + ", ".join(
            c for c in filled if c != "status"
        ))
        if "status" in filled:
            notes.append("No status column found — all orders treated as Delivered.")
    if "cost_price" not in df.columns:
        df["cost_price"] = np.nan
    return df, notes


# =============================================================================
# STEP 4 — Validation
# =============================================================================
class SchemaValidationError(ValueError):
    """Raised when an uploaded dataset can't be used even after mapping."""
    def __init__(self, message, missing=None, detected=None):
        super().__init__(message)
        self.missing = missing or []
        self.detected = detected or []


def validate_required_columns(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaValidationError(
            f"Missing required column(s) after mapping: {', '.join(missing)}.",
            missing=missing,
            detected=list(df.columns),
        )


# =============================================================================
# Full pipeline helper (for callers that don't need the manual-confirmation
# step, e.g. when every mapping came back High confidence)
# =============================================================================
def prepare_uploaded_frame(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, list[ColumnMapping], list[str]]:
    """
    Normalize + map + derive + validate in one call, for the common case
    where nothing is ambiguous. Returns (canonical_df, mappings, notes).
    Raises SchemaValidationError if required columns can't be found even
    after mapping. Caller is responsible for checking whether any mapping
    needs user confirmation (confidence != "High") before trusting the
    result for anything but a preview.
    """
    normalized = normalize_column_names(raw_df)
    mappings = detect_and_map_columns(normalized)
    mapped = apply_column_mapping(normalized, mappings)

    notes: list[str] = []
    mapped, derive_notes = derive_missing_columns(mapped)
    notes += derive_notes
    mapped, default_notes = fill_optional_defaults(mapped)
    notes += default_notes

    # Dates
    mapped["order_date"], dayfirst = _parse_dates(mapped.get("order_date", pd.Series(dtype="object")))
    if dayfirst:
        notes.append("Dates were read as day-first (DD-MM-YYYY).")
    before = len(mapped)
    mapped = mapped.dropna(subset=[c for c in ["order_date", "order_id", "customer_id"] if c in mapped.columns])
    if len(mapped) < before:
        notes.append(f"Dropped {before - len(mapped):,} rows with a missing/invalid order_id, customer_id or order_date.")

    validate_required_columns(mapped)
    if mapped.empty:
        raise SchemaValidationError(
            "No valid rows left after removing missing order_id / customer_id / order_date.",
            detected=list(mapped.columns),
        )

    mapped = mapped.sort_values("order_date").reset_index(drop=True)
    mapped["month"] = mapped["order_date"].dt.to_period("M")
    mapped["year"] = mapped["order_date"].dt.year
    mapped["month_label"] = mapped["order_date"].dt.strftime("%b %Y")

    return mapped, mappings, notes


def _parse_dates(series: pd.Series) -> tuple[pd.Series, bool]:
    """Parse dates, retrying day-first (DD-MM-YYYY) if that recovers more rows."""
    default = pd.to_datetime(series, errors="coerce")
    if default.notna().all() or default.empty:
        return default, False
    dayfirst = pd.to_datetime(series, errors="coerce", dayfirst=True)
    if dayfirst.notna().sum() > default.notna().sum():
        return dayfirst, True
    return default, False


# =============================================================================
# Streamlit UI helper — the only function here that imports streamlit
# =============================================================================
def render_mapping_ui(mappings: list[ColumnMapping], key_prefix: str) -> list[ColumnMapping] | None:
    """
    Show a "Column Mapping Required" confirmation table whenever the system
    isn't fully confident. Two situations trigger it:
      1. A raw column matched a canonical name, but only via fuzzy matching
         (Medium/Low confidence) — the user confirms or corrects it.
      2. A REQUIRED canonical column (order_id, customer_id, order_date) has
         no confident match at all — the user is asked to pick which, if
         any, of the leftover raw columns it actually is.
    High-confidence exact-alias mappings are applied automatically and just
    listed for transparency; the user never has to touch those.

    Returns the confirmed list of ColumnMapping once the user clicks confirm,
    or None if confirmation is still pending (caller should stop rendering
    further for this file).
    """
    import streamlit as st

    needs_review = [m for m in mappings if m.confidence != "High" and m.canonical is not None]
    auto_mapped = [m for m in mappings if m.confidence == "High"]
    unmatched = [m for m in mappings if m.canonical is None]

    mapped_canonicals = {m.canonical for m in auto_mapped} | {m.canonical for m in needs_review if m.canonical}
    missing_required = [c for c in REQUIRED_COLUMNS if c not in mapped_canonicals]

    if auto_mapped:
        st.caption(
            "Automatically mapped: " + ", ".join(f"{m.raw_column} -> {m.canonical}" for m in auto_mapped)
        )
    if unmatched:
        st.caption(
            "Not used (no confidently matching column): " + ", ".join(m.raw_column for m in unmatched)
        )

    if not needs_review and not missing_required:
        return mappings

    st.warning("Column Mapping Required — please confirm these before continuing.")
    canonical_options = ["(ignore this column)"] + sorted(COLUMN_ALIASES.keys())
    raw_options = ["(none of these)"] + [m.raw_column for m in unmatched]

    confirmed = list(auto_mapped)

    if needs_review:
        st.markdown("**Columns we're not fully sure about:**")
        header = st.columns([2, 2, 1])
        header[0].markdown("Detected column")
        header[1].markdown("Expected column")
        header[2].markdown("Confidence")
        for m in needs_review:
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.write(m.raw_column)
            default_idx = canonical_options.index(m.canonical) if m.canonical in canonical_options else 0
            chosen = c2.selectbox(
                " ", canonical_options, index=default_idx,
                key=f"{key_prefix}_map_{m.raw_column}", label_visibility="collapsed",
            )
            c3.write(m.confidence)
            canonical = None if chosen == "(ignore this column)" else chosen
            confirmed.append(ColumnMapping(m.raw_column, canonical, "Confirmed"))
            if canonical is None:
                unmatched.append(m)  # freed up, could still be picked below
    else:
        confirmed += unmatched  # nothing ambiguous to review; carry unmatched through as-is

    if missing_required:
        st.markdown("**Required columns we couldn't find automatically:**")
        st.caption(
            "These are needed for the dashboard to work (order id, customer id, order date). "
            "Pick the raw column that holds this data, or leave it unmatched if your file "
            "truly doesn't have it."
        )
        header = st.columns([2, 2, 1])
        header[0].markdown("Expected column")
        header[1].markdown("Pick a detected column")
        header[2].markdown("Confidence")
        current_raw_options = ["(none of these)"] + [m.raw_column for m in unmatched]
        for canonical in missing_required:
            c1, c2, c3 = st.columns([2, 2, 1])
            c1.write(canonical)
            chosen = c2.selectbox(
                " ", current_raw_options, index=0,
                key=f"{key_prefix}_required_{canonical}", label_visibility="collapsed",
            )
            c3.write("Needs input")
            if chosen != "(none of these)":
                confirmed.append(ColumnMapping(chosen, canonical, "Confirmed"))

    missing_still = [c for c in missing_required
                     if c not in {m.canonical for m in confirmed if m.canonical}]
    if missing_still:
        st.error(
            "Still missing after your selections: " + ", ".join(missing_still) + ". "
            "Detected columns in this file: " + ", ".join(m.raw_column for m in mappings) + ". "
            "Pick a column above, or re-upload a file that includes this data."
        )

    if st.button("Confirm mapping", key=f"{key_prefix}_confirm_mapping", disabled=bool(missing_still)):
        return confirmed
    return None