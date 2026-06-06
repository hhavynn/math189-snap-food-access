# Data Cleaning Summary

## Dataset

| Item | Value |
|---|---|
| File | `FoodAccessResearchAtlasData2019.xlsx` |
| Source sheet | `Food Access Research Atlas` |
| Variable reference | `Variable Lookup` sheet |

---

## Row / Column Counts

| Stage | Rows | Columns |
|---|---|---|
| Raw | 72,531 | 147 |
| After cleaning (all tracts) | 72,531 | 159 |
| Modeling subset | 42,156 | 26 |

No rows were dropped in the full cleaned dataset. Percentage variables with impossible values (below 0 or above 100, caused by denominator issues) were set to NaN and documented below.

The modeling subset dropped **30,375 rows** missing at least one required variable:
`pct_low_income_low_access`, `pct_snap`, `PovertyRate`, `MedianFamilyIncome`, `pct_no_vehicle`, or `Urban`. These tracts either have zero population/housing units or are missing key USDA measurements.

---

## Response and Explanatory Variables

**Main response variable:** `pct_low_income_low_access`  
Definition: The percentage of residents in a census tract who are both low-income and low-access to supermarkets (beyond 1 mile in urban areas, 10 miles in rural areas).  
Formula: `100 × LALOWI1_10 / Pop2010`

**Main explanatory variable:** `pct_snap`  
Definition: The percentage of occupied housing units in a census tract that receive SNAP benefits.  
Formula: `100 × TractSNAP / OHU2010`

---

## Variables Created

| New Variable | Formula | Notes |
|---|---|---|
| `pct_snap` | `100 × TractSNAP / OHU2010` | Main explanatory variable |
| `pct_no_vehicle` | `100 × TractHUNV / OHU2010` | No-vehicle households |
| `pct_low_income_low_access` | `100 × LALOWI1_10 / Pop2010` | Main response variable |
| `pct_children` | `100 × TractKids / Pop2010` | |
| `pct_seniors` | `100 × TractSeniors / Pop2010` | |
| `pct_white` | `100 × TractWhite / Pop2010` | |
| `pct_black` | `100 × TractBlack / Pop2010` | |
| `pct_asian` | `100 × TractAsian / Pop2010` | |
| `pct_hispanic` | `100 × TractHispanic / Pop2010` | |
| `urban_label` | `"Urban"` if `Urban==1`, else `"Rural"` | |
| `log_median_family_income` | `log(MedianFamilyIncome)` | NaN when ≤ 0 |
| `log_response` | `log1p(pct_low_income_low_access)` | Stabilizes right skew |

All percentage variables use safe division: denominator values ≤ 0 or NaN return NaN instead of crashing or producing Inf.

---

## Missing Value Handling

- **Pop2010:** 0 missing; used as denominator for population-based percentages.
- **OHU2010:** 106 rows have zero/missing; `pct_snap` and `pct_no_vehicle` are NaN for those rows.
- **Impossible percentage values** (outside [0, 100]) were set to NaN:
  - `pct_snap`: 21 rows
  - `pct_no_vehicle`: 52 rows
  - `pct_low_income_low_access`: 1 row
- Rows with any missing value in the required modeling columns were excluded from the modeling dataset only (30,375 rows).

---

## Outlier Summary (1.5 × IQR Rule, not removed)

| Variable | Fence (low, high) | Outlier count |
|---|---|---|
| `pct_snap` | [−16.55, 39.91] | 3,023 |
| `pct_no_vehicle` | [−10.19, 23.63] | 6,409 |
| `pct_low_income_low_access` | [−18.92, 34.92] | 2,741 |

Outliers are **not removed**. Because all three variables are non-negative, the lower IQR fence is meaningless (values cannot go below 0). Only the upper-tail counts are substantively relevant. Inspect high-value tracts before modeling; consider log transformation or robust regression if residuals are skewed.

---

## Notes for Regression (for teammates)

### Addressing spatial clustering / census-tract dependence

Census tracts are spatially autocorrelated. To partially address this without full spatial regression:

- Include **state fixed effects** (dummy variables for each state) to absorb state-level confounding.
- Or use **cluster-robust standard errors** clustered at the `State` or `County` level.
- `State` and `County` columns are preserved in both output files for this purpose.

### Suggested base regression model

```
pct_low_income_low_access ~
    pct_snap
  + PovertyRate
  + log_median_family_income
  + pct_no_vehicle
  + Urban
  + pct_children
  + pct_seniors
  + pct_black
  + pct_hispanic
  + pct_asian
```

### Suggested interaction model (urban vs. rural heterogeneity)

```
pct_low_income_low_access ~
    pct_snap
  + PovertyRate
  + log_median_family_income
  + pct_no_vehicle
  + Urban
  + pct_snap:Urban
  + pct_no_vehicle:Urban
```

The interaction terms test whether the SNAP–low-access relationship and the vehicle-access effect differ between urban and rural tracts — directly addressing the research question.

Consider using `log_response` as the dependent variable if residuals are right-skewed.
