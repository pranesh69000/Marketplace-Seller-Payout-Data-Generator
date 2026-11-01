# DESIGN.md - Marketplace Seller Payout Data Generator

**Status**: LOCKED (Source of Truth)  
**Seed**: `20261022`  
**Reference Timeline**: 2026-01-01 to 2026-10-15  
**As-Of Evaluation Date**: 2026-10-31  

This document locks all architecture and business-rule specifications for the synthetic data generator. Values marked *(calibrate)* are starting defaults to be validated during test runs.

---

## 1. Timeline & Scheduling
- **Order placement window**: `2026-01-01` to `2026-10-15` inclusive.
- **As-of cutoff date**: `2026-10-31`. Fixed in configuration; never derived from system clock.
- **Hold window**: 14 calendar days post-delivery (`delivered_at + 14 days <= cycle_date`).
- **Dispute window**: 30 calendar days post-delivery.
- **Payout & status evaluation cycle**: Weekly on Mondays (`2026-01-05`, `2026-01-12`, ..., `2026-10-26`).

---

## 2. ID Specification (Deterministic & Monotonic)
All IDs are produced by a single centralized `IdGenerator` instance. Zero-padded counters, immutable, strictly monotonic, never reused, deterministic assignment order.

| Entity Type | Format | Example |
| :--- | :--- | :--- |
| **Seller** | `SELL-NNNNNN` (6 digits) | `SELL-000001` |
| **Product Listing** | `LIST-<seller-id>-NNNNNN` | `LIST-SELL-000042-000001` |
| **Order** | `ORD-2026-NNNNNN` (6 digits) | `ORD-2026-000001` |
| **Order Line** | `<order-id>-NN` (2 digits) | `ORD-2026-000317-01` |
| **Fulfillment** | `FUL-<order-line-id>` (1:1 with Line) | `FUL-ORD-2026-000317-01` |
| **Customer Review** | `REV-2026-NNNNNN` | `REV-2026-000001` |
| **Dispute** | `DSP-2026-NNNNNN` | `DSP-2026-000001` |
| **Commission Rule** | `RULE-NNNN` (4 digits) | `RULE-0001` |
| **Payout** | `PAYOUT-2026-NNNNNN` | `PAYOUT-2026-000001` |
| **Payout Line** | `PLINE-2026-NNNNNN` | `PLINE-2026-000001` |
| **Customer** | `CUST-NNNNNN` (plain attribute) | `CUST-000001` |
| **Events** | `EVT-<prefix>-NNNNNN` | `EVT-STATUS-000001` |
| **Anomaly Ground Truth** | `GT-NNNNNN` | `GT-000001` |

---

## 3. Schema & Relational Integrity (15 Tables)

### 3.1 Core Entity Tables (10)
1. **Seller**: Primary seller master table with business name, onboarded date, rating, status (`ACTIVE`, `WATCHLIST`, `SUSPENDED`).
2. **ProductListing**: SKU and catalog data attached to a seller, including category, base price in cents, and nullable `deactivated_at`.
3. **CommissionRule**: Category and promo commission rates in basis points (`rate_bps`), priority, and effective date ranges.
4. **Order**: Order header with customer ID, placement timestamp, and gross total.
5. **OrderLine**: Specific line item referencing `order_id`, `listing_id`, and `seller_id` (denormalized for join efficiency), quantity, and price.
6. **Fulfillment**: 1:1 with OrderLine; tracks carrier, tracking number, ship date, delivery date, and fulfillment status (`PENDING`, `SHIPPED`, `DELIVERED`, `CANCELLED`, `FAILED_DELIVERY`, `RETURNED`).
7. **CustomerReview**: 0..1 per OrderLine; customer rating (1-5) and comment timestamp.
8. **Dispute**: 0..1 per OrderLine; dispute reason, status (`OPEN`, `RESOLVED_SELLER_WON`, `RESOLVED_BUYER_WON`), dispute amount in cents, initiated and resolved dates.
9. **Payout**: Weekly settlement summary per seller; net payout total in cents, status (`PENDING`, `PAID`, `HELD`).
10. **PayoutLine**: Individual signed ledger entries backing a Payout.

### 3.2 Bridge Table (1)
11. **SellerCommissionAssignment**: N:M bridge connecting sellers to specific promotional or standard commission rules with `effective_from` and `effective_to`.

### 3.3 Event / Audit Tables (4)
12. **SellerStatusEvent**: Audit trail of every seller state transition with snapshot metric values.
13. **FulfillmentEvent**: Discrete milestone events (`PLACED`, `SHIPPED`, `OUT_FOR_DELIVERY`, `DELIVERED`, `RETURN_REQUESTED`, `RETURN_COMPLETED`).
14. **DisputeEvent**: Status updates throughout dispute lifecycle.
15. **PayoutEvent**: Status changes of payouts (`GENERATED`, `HELD`, `RELEASED`, `PAID`).

---

## 4. Financial & Ledger Rules
- **Money Representation**: 100% integer cents (USD). No floats used in financial calculation.
- **Commission Calculation**: Single source of truth function using strict half-up rounding:
  $$\text{commission\_cents} = \left\lfloor \frac{\text{line\_gross\_cents} \times \text{rate\_bps} + 5000}{10000} \right\rfloor$$
- **Ledger Entry Types & Signed Amounts**:
  - `SALE` (+): Gross item price $\times$ quantity.
  - `COMMISSION` (-): Deducted marketplace commission.
  - `REFUND` (-): Amount returned to customer upon return.
  - `COMMISSION_REVERSAL` (+): Marketplace commission credited back on return.
  - `DISPUTE_DEDUCTION` (-): Amount clawed back when buyer wins dispute.
  - `RESERVE_HOLD` (-): 10% of (gross - commission) withheld for sellers on `WATCHLIST`.
  - `RESERVE_RELEASE` (+): Release of previously held reserve after 60 days if seller is not `SUSPENDED`.
- **Payout Eligibility**:
  - Item must be delivered (`delivered_at + 14 days <= cycle_date`).
  - No active/open dispute on the order line.
  - Line not returned prior to eligibility cutoff.
- **Negative Balances**: If a weekly cycle net is negative for a seller, no Payout record is created; balance rolls forward to the following Monday cycle.
- **Suspended Sellers**: Payout records are created, but state remains `HELD` until reinstatement.

---

## 5. Seller Governance & Status State Machine
- **Evaluation Cadence**: Trailing 60 calendar days evaluated every Monday. Minimum threshold of 15 delivered/shipped lines required to trigger status changes.
- **Allowed States**: `ACTIVE`, `WATCHLIST`, `SUSPENDED`. Everyone begins as `ACTIVE`.
- **Allowed Transitions**:
  - `ACTIVE` $\to$ `WATCHLIST`: Late rate $\ge 12\%$ OR Dispute rate $\ge 9\%$.
  - `WATCHLIST` $\to$ `SUSPENDED`: Late rate $\ge 20\%$ OR Dispute rate $\ge 14\%$, OR 2 consecutive weekly evaluations at watchlist levels.
  - `ACTIVE` $\to$ `SUSPENDED`: Late rate $\ge 20\%$ OR Dispute rate $\ge 14\%$ (severe breach).
  - `WATCHLIST` $\to$ `ACTIVE`: 2 consecutive clean evaluations below thresholds.
  - `SUSPENDED` $\to$ `WATCHLIST`: Automatically eligible after 30-day minimum suspension cooldown.
- **Suspension Enforcement**:
  - Existing listings deactivated (`deactivated_at = event_timestamp`).
  - No new orders routed to seller.
  - Existing in-flight orders are fulfilled normally.
  - Payout balances remain `HELD`.

---

## 6. Anomalies & Ground Truth
Injected post-baseline validation. Targets selected deterministically from sorted eligible candidates.
1. `PAYOUT_BEFORE_HOLD_RELEASE`: Payout line moved before 14-day hold or delivery date.
2. `COMMISSION_APPLIED_TWICE`: Duplicate `COMMISSION` entry in the same payout.
3. `SUSPENDED_SELLER_LISTING`: Listing created during active suspension window.
4. `DISPUTE_NOT_DEDUCTED`: Seller lost dispute, but `DISPUTE_DEDUCTION` missing from payout.
5. `PAYOUT_TOTAL_MISMATCH`: `Payout.total_cents` deviates from sum of `PayoutLine.amount_cents`.

