"""
clean_food_access.py
--------------------
Reusable cleaning pipeline for the USDA Food Access Research Atlas (2019).

Outputs:
  data/cleaned/food_access_cleaned.csv      -- full cleaned dataset
  data/cleaned/food_access_modeling.csv     -- regression-ready subset
  data/cleaned/data_dictionary_cleaned.csv  -- variable lookup from xlsx
"""

import glob
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
CLEANED_DIR = ROOT / "data" / "cleaned"
CLEANED_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def find_raw_xlsx(raw_dir: Path = RAW_DIR) -> Path:
    """Return the single Food Access xlsx in data/raw/. Raises if none/ambiguous."""
    candidates = list(raw_dir.glob("*.xlsx"))
    if len(candidates) == 0:
        raise FileNotFoundError(f"No .xlsx files found in {raw_dir}")
    if len(candidates) > 1:
        # prefer the one with 'FoodAccess' in the name
        fa = [f for f in candidates if "FoodAccess" in f.name or "food_access" in f.name.lower()]
        if len(fa) == 1:
            return fa[0]
        raise FileNotFoundError(
            f"Multiple .xlsx files in {raw_dir}; cannot determine which to use: {candidates}"
        )
    return candidates[0]


def load_raw(raw_dir: Path = RAW_DIR):
    """Load the main tract-level sheet and the variable lookup sheet."""
    xlsx_path = find_raw_xlsx(raw_dir)
    print(f"Loading: {xlsx_path.name}")
    xl = pd.ExcelFile(xlsx_path)

    df = pd.read_excel(xl, sheet_name="Food Access Research Atlas")
    print(f"  Raw data shape: {df.shape[0]:,} rows x {df.shape[1]} columns")

    # Load variable lookup if present
    dd = None
    if "Variable Lookup" in xl.sheet_names:
        dd = pd.read_excel(xl, sheet_name="Variable Lookup")

    return df, dd, xlsx_path.name


# ---------------------------------------------------------------------------
# Safe division
# ---------------------------------------------------------------------------

def safe_pct(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """100 * num/denom; returns NaN when denom <= 0 or is NaN."""
    denom = denominator.copy().astype(float)
    denom[denom <= 0] = np.nan
    return 100.0 * numerator.astype(float) / denom


# ---------------------------------------------------------------------------
# Main cleaning function
# ---------------------------------------------------------------------------

def clean(df_raw: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    df = df_raw.copy()
    n_original = len(df)

    # -----------------------------------------------------------------------
    # 1. Core identifier / denominator checks
    # -----------------------------------------------------------------------
    # Flag rows where Pop2010 or OHU2010 are missing/zero (needed for pct vars)
    invalid_pop = df["Pop2010"].isna() | (df["Pop2010"] <= 0)
    invalid_ohu = df["OHU2010"].isna() | (df["OHU2010"] <= 0)

    if verbose:
        print(f"\n[Cleaning] Rows with missing/invalid Pop2010: {invalid_pop.sum()}")
        print(f"[Cleaning] Rows with missing/invalid OHU2010: {invalid_ohu.sum()}")

    # -----------------------------------------------------------------------
    # 2. Feature engineering -- percentage variables (safe division)
    # -----------------------------------------------------------------------
    pct_vars = {
        "pct_snap":                   ("TractSNAP",   "OHU2010"),
        "pct_no_vehicle":             ("TractHUNV",   "OHU2010"),
        "pct_low_income_low_access":  ("LALOWI1_10",  "Pop2010"),
        "pct_children":               ("TractKids",   "Pop2010"),
        "pct_seniors":                ("TractSeniors","Pop2010"),
        "pct_white":                  ("TractWhite",  "Pop2010"),
        "pct_black":                  ("TractBlack",  "Pop2010"),
        "pct_asian":                  ("TractAsian",  "Pop2010"),
        "pct_hispanic":               ("TractHispanic","Pop2010"),
    }

    for new_col, (num_col, den_col) in pct_vars.items():
        if num_col not in df.columns:
            warnings.warn(f"Column '{num_col}' not found; '{new_col}' will be all NaN.")
            df[new_col] = np.nan
        else:
            df[new_col] = safe_pct(df[num_col], df[den_col])

    # Flag impossible percentage values (outside [0, 100])
    for col in pct_vars:
        if col not in df.columns:
            continue
        out_of_range = (df[col] < 0) | (df[col] > 100)
        n_bad = out_of_range.sum()
        if n_bad > 0:
            if verbose:
                print(f"[QC] {n_bad} impossible values in '{col}' (set to NaN)")
            df.loc[out_of_range, col] = np.nan

    # -----------------------------------------------------------------------
    # 3. Additional derived variables
    # -----------------------------------------------------------------------
    df["urban_label"] = df["Urban"].map({1: "Urban", 0: "Rural"})

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df["log_median_family_income"] = np.where(
            df["MedianFamilyIncome"] > 0,
            np.log(df["MedianFamilyIncome"].astype(float)),
            np.nan,
        )

    df["log_response"] = np.log1p(df["pct_low_income_low_access"].astype(float))

    # -----------------------------------------------------------------------
    # 4. Outlier summary (1.5 IQR rule) -- report only, do NOT remove
    # -----------------------------------------------------------------------
    outlier_cols = ["pct_snap", "pct_no_vehicle", "pct_low_income_low_access"]
    if verbose:
        print("\n[Outliers] 1.5×IQR flagged counts (not removed):")
        for col in outlier_cols:
            s = df[col].dropna()
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            iqr = q3 - q1
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            n_out = ((s < lo) | (s > hi)).sum()
            print(f"  {col}: {n_out:,} outliers  (fence [{lo:.2f}, {hi:.2f}])")

    if verbose:
        print(f"\n[Cleaning] Cleaned dataset shape: {df.shape[0]:,} x {df.shape[1]}")

    return df


# ---------------------------------------------------------------------------
# Modeling subset
# ---------------------------------------------------------------------------

MODELING_COLS = [
    "CensusTract", "State", "County",
    "Urban", "urban_label",
    "Pop2010", "OHU2010",
    "PovertyRate", "MedianFamilyIncome", "log_median_family_income",
    "LowIncomeTracts",
    "TractSNAP", "TractHUNV",
    "pct_snap", "pct_no_vehicle",
    "pct_low_income_low_access", "log_response",
    "pct_children", "pct_seniors",
    "pct_white", "pct_black", "pct_asian", "pct_hispanic",
    "LILATracts_1And10", "LILATracts_halfAnd10", "LILATracts_Vehicle",
]

REQUIRED_FOR_MODEL = [
    "pct_low_income_low_access", "pct_snap",
    "PovertyRate", "MedianFamilyIncome",
    "pct_no_vehicle", "Urban",
]


def build_modeling_df(df_clean: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    # Keep only columns that actually exist
    cols = [c for c in MODELING_COLS if c in df_clean.columns]
    missing_cols = [c for c in MODELING_COLS if c not in df_clean.columns]
    if missing_cols and verbose:
        warnings.warn(f"Columns not found in cleaned data (skipped): {missing_cols}")

    df_model = df_clean[cols].copy()
    n_before = len(df_model)

    # Drop rows missing any required variable
    mask_drop = df_model[REQUIRED_FOR_MODEL].isna().any(axis=1)
    n_dropped = mask_drop.sum()
    df_model = df_model[~mask_drop].copy()

    if verbose:
        print(f"\n[Modeling] Dropped {n_dropped:,} rows missing required variables")
        print(f"[Modeling] Modeling dataset shape: {df_model.shape[0]:,} x {df_model.shape[1]}")

    return df_model


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_pipeline(raw_dir: Path = RAW_DIR, verbose: bool = True):
    df_raw, dd, xlsx_name = load_raw(raw_dir)
    df_clean = clean(df_raw, verbose=verbose)
    df_model = build_modeling_df(df_clean, verbose=verbose)

    # Save outputs
    clean_path = CLEANED_DIR / "food_access_cleaned.csv"
    model_path = CLEANED_DIR / "food_access_modeling.csv"
    dd_path    = CLEANED_DIR / "data_dictionary_cleaned.csv"

    df_clean.to_csv(clean_path, index=False)
    df_model.to_csv(model_path, index=False)
    if dd is not None:
        dd.to_csv(dd_path, index=False)
    else:
        warnings.warn("No Variable Lookup sheet found; data dictionary not saved.")

    if verbose:
        print(f"\n[Saved] {clean_path}")
        print(f"[Saved] {model_path}")
        if dd is not None:
            print(f"[Saved] {dd_path}")

    return df_clean, df_model, dd, xlsx_name


if __name__ == "__main__":
    run_pipeline()
