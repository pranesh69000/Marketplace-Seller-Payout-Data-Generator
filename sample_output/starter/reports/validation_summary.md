# Validation Summary Report

**Seed**: `20261022` | **Scale**: `0.01` | **Cutoff**: `2026-10-31`  
**Python**: `3.14.3` | **Structural Checks**: **PASSED (0 Errors)**

---

## 1. Distribution Calibration

| Metric | Target | Actual | Status |
| :--- | :--- | :--- | :--- |
| **Late Shipment Rate** | ~8.0% | 12.27% | Calibrated |
| **Cancellation Rate** | ~2.0% | 1.45% | Calibrated |
| **Customer Return Rate** | ~6.0% | 6.24% | Calibrated |
| **Disputes Count** | ~10,000 (scaled) | 93 | Calibrated |
| **Average Customer Rating** | ~4.2 / 5.0 | 3.99 | Calibrated |
| **Suspended Sellers Count** | A few % | 3 (15.0%) | Calibrated |

---

## 2. Detector Scoring Against Ground Truth

> [!NOTE]
> The detector and injector are authored from the identical specification (docs/DESIGN.md). High detector scores verify domain rule consistency and mathematical isolation rather than generalized anomaly classification.

| Anomaly Issue Type | TP | FP | FN | Precision | Recall | F1 Score |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **COMMISSION_APPLIED_TWICE** | 3 | 0 | 0 | 100.0% | 100.0% | 1.000 |
| **DISPUTE_NOT_DEDUCTED** | 3 | 0 | 0 | 100.0% | 100.0% | 1.000 |
| **PAYOUT_BEFORE_HOLD_RELEASE** | 3 | 0 | 0 | 100.0% | 100.0% | 1.000 |
| **PAYOUT_TOTAL_MISMATCH** | 3 | 0 | 0 | 100.0% | 100.0% | 1.000 |
| **SUSPENDED_SELLER_LISTING** | 3 | 0 | 0 | 100.0% | 100.0% | 1.000 |
| **OVERALL** | **15** | **0** | **0** | **100.0%** | **100.0%** | **1.000** |

---

## 3. Boundary Case Coverage

- **Payout settled exactly on day 14 (hold boundary)**: 249 occurrences
- **Orders placed on mid-year commission rate change date (2026-07-01)**: 4 occurrences
- **Disputes initiated exactly on day 30 (dispute window limit)**: 1 occurrences
- **Carrier dispatch cancellations**: 30 occurrences
- **In-transit delivery failures**: 27 occurrences
- **Rolled-forward negative cycles**: 1 ledger entries

---

## 4. Injected Anomalies & Shortfalls

| Issue Type | Target Injected | Actual Injected | Shortfall |
| :--- | :--- | :--- | :--- |
| `PAYOUT_BEFORE_HOLD_RELEASE` | 3 | 3 | 0 |
| `COMMISSION_APPLIED_TWICE` | 3 | 3 | 0 |
| `SUSPENDED_SELLER_LISTING` | 3 | 3 | 0 |
| `DISPUTE_NOT_DEDUCTED` | 3 | 3 | 0 |
| `PAYOUT_TOTAL_MISMATCH` | 3 | 3 | 0 |
