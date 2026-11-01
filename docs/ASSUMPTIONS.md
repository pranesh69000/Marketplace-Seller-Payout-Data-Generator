# ASSUMPTIONS.md - Project Assumptions & Technical Clarifications

This document records technical interpretations, operational assumptions, and disambiguations agreed upon for the Marketplace Seller Payout Data Generator.

---

## 1. Timeline & Calendar
- **As-of Date**: `2026-10-31 23:59:59` UTC is fixed in configuration and used as the reference point for all time-relative checks. The generator never inspects host system time.
- **Weekly Cycles**: Payouts and seller evaluations occur on Mondays (`2026-01-05`, `2026-01-12`, ..., `2026-10-26`). Events occurring mid-week are settled on the subsequent Monday cycle.

---

## 2. Dispute Volume Modeling
- **Section 4.7 Fallback Adopted**: In the master prompt, Section 4.7 allows:
  > *"Fallback if too complex: calibrate the rate and accept 10,000 plus or minus 2-3%, documented."*
- **Reasoning**: A dispute cannot exist before an order line has shipped and delivered. Imposing an exact quota of 10,000 upfront across weeks creates a backwards causal paradox where unfulfilled or future lines are pre-assigned disputes.
- **Implementation**: We calibrate a causal dispute propensity model based on:
  - Seller quality tier (`POOR` sellers experience significantly higher dispute rates).
  - Transit delays (shipment delivered > 5 days late).
  - Failed deliveries and rejected return requests.
  The baseline parameters are tuned to deliver $\approx 10,000 \pm 2\%$ disputes at 1.0 scale (and proportionally at other scales).

---

## 3. Post-Suspension Evaluation Window
- **Context**: A seller suspended on Monday $W$ must remain suspended for a minimum of 30 days before transitioning back to `WATCHLIST`.
- **The Issue**: Because suspended sellers cannot receive new orders during those 30 days, their raw trailing 60-day window would still contain the old breached orders, causing immediate re-suspension upon reinstatement.
- **Adopted Policy**: Upon transitioning from `SUSPENDED` to `WATCHLIST`, the trailing metrics window resets to evaluate only orders fulfilled *after* the reinstatement date. Until the seller accumulates the required minimum volume of 15 delivered lines under the new period, their status remains `WATCHLIST` without triggering another suspension.

---

## 4. Financial & Monetary Representation
- **Integer Cents**: All monetary amounts (`total_gross_cents`, `unit_price_cents`, `commission_cents`, `total_cents`, `amount_cents`) are strictly stored and computed as integer cents. Floating-point types are prohibited in financial pathways.
- **Currency**: Single currency (USD).
- **Excluded Items**: Sales tax, shipping carrier charges, customer shipping fees, and negotiated seller-specific rate overrides are excluded from the scope as specified in Section 4.4 and 4.6.

---

## 5. Anomaly 3 ID Sequencing
- **Context**: Anomaly 3 injects a listing created during an active suspension period.
- **Adopted Policy**: The injected listing uses the seller's next incremental sequence counter (e.g. `LIST-SELL-000042-000012`), but carries a `created_at` timestamp inside the historical suspension window. In the data export, listings are sorted by primary key (`listing_id`), meaning date order may not strictly match sequential ID order for these injected rows. This is documented as expected behavior.

---

## 6. Seed & Reproducibility Scope
- Fixed seed `20261022` is supplied to `numpy.random.default_rng(20261022)` and threaded explicitly.
- Identical SHA-256 file checksums are guaranteed for consecutive runs executed with identical Python and NumPy versions on the same OS platform.

