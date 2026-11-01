# LIMITATIONS.md - System Boundaries & Constraints

This document details deliberate technical boundaries, out-of-scope domain features, and hardware operating parameters for the Marketplace Seller Payout Data Generator.

---

## 1. Domain & Scope Boundaries
- **Taxes & Shipping**: Value Added Tax (VAT), sales tax, and freight/shipping charges are not modeled. Line gross amounts equal `quantity * unit_price_cents`.
- **Single Currency**: All financial calculations are denominated strictly in US Dollars (USD) stored as integer cents. Multi-currency conversions are not supported.
- **Partial Returns**: Returns are all-or-nothing per order line. Partial quantity returns (e.g., returning 1 of 3 items on a line) are out of scope.
- **Single Dispute per Line**: An order line may have at most one dispute. Subsequent dispute appeals or re-opened claims are omitted.
- **No Negotiated Seller Rates**: Commission rates are resolved strictly by category, seller tenure (promotional rule), and priority. Individual 1-on-1 negotiated rate overrides are out of scope.

---

## 2. Hardware Operating Parameters
- **Target Architecture**: Designed and tested to operate within an 8 GB RAM boundary on low-power Intel Pentium dual-core CPUs without requiring dedicated GPU acceleration.
- **Memory Footprint**: Memory footprint is bounded by:
  - Streaming completed records to disk rather than retaining all 15 tables in memory simultaneously.
  - Employing compact native types (integer timestamps, boolean/status enums, integer cents).
- **Scale Configurations**:
  - Starter Scale (`--scale 0.01`): ~20 sellers, ~1,000 orders. Runs in < 15 seconds; memory peak < 150 MB.
  - Medium Scale (`--scale 0.10`): ~200 sellers, ~10,000 orders. Runs in < 2 minutes; memory peak < 400 MB.
  - Baseline Scale (`--scale 1.0`): 2,000 sellers, 100,000 orders. Runs in ~10-15 minutes on dual-core hardware; memory peak < 1.5 GB.

