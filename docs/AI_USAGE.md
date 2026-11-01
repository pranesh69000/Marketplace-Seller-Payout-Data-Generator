# AI_USAGE.md - Transparent AI Collaboration & Disclosure Log

**Candidate Project**: Marketplace Seller Payout Data Generator (YottaFlex AI Evaluation)  
**Author / Project Owner**: Candidate Pranesh R (Final-Year B.Tech IT)  
**Collaborator Role**: Antigravity (Google DeepMind Advanced Agentic Coding) acting as Senior Software Engineer, Technical Mentor, and Critical Reviewer.  

---

## 1. Collaboration Philosophy & Academic Integrity Statement

In compliance with project submission guidelines, this document provides a full, transparent disclosure of AI tool utilization throughout the design, implementation, and verification of the Marketplace Seller Payout Data Generator.

- **Human Ownership & Verification**: The human candidate initiated all decisions, reviewed every design choice, approved all code changes, ran all terminal commands locally on their personal hardware (Intel Pentium, 8 GB RAM, Python 3.14.3 on Windows), and verified test assertions.
- **AI Mentorship & Peer Review**: The AI assistant served as a senior pair-programming partner: identifying design bottlenecks, pointing out domain ambiguities, implementing modular architecture, and explaining causal and financial accounting concepts step-by-step.
- **Zero Fabrication**: No benchmark numbers, library features, or execution results were fabricated. All calibration metrics and execution benchmarks reported in this project were measured directly on the candidate's physical machine.

---

## 2. Milestone-by-Milestone Development Log

### Milestone 1: Architecture Scaffold, Data Dictionary, Config & Deterministic IDs
- **AI Contributions**:
  - Analyzed the specification and identified critical ambiguities (dispute volume circularity, post-suspension evaluation trap on trailing 60-day windows).
  - Drafted `docs/DESIGN.md` capturing all locked architectural rules.
  - Authored `docs/DATA_DICTIONARY.md` defining types, nullability, constraints, and keys across all 15 tables.
  - Authored `src/marketplace_gen/config.py` (immutable dataclasses with fast-fail validation) and `src/marketplace_gen/ids.py` (centralized monotonic zero-padded generator).
  - Authored unit test suite `tests/test_ids.py`.
- **Human Review & Actions**:
  - Confirmed Python 3.14.3 environment and submission deadline.
  - Reviewed and approved directory layout and architectural assumptions.
  - Executed `python -m unittest discover -s tests` locally (8 tests passed in 0.001s).

### Milestone 2: Master Data & Order Skeleton
- **AI Contributions**:
  - Implemented `src/marketplace_gen/rules/commission.py` with pure `round_half_up` integer arithmetic and priority-based commission rule resolution.
  - Implemented `src/marketplace_gen/simulation/master_data.py` (sellers with hidden quality tiers, product listings, time-bound commission assignments, and the mid-year `ELECTRONICS` rate shift).
  - Implemented `src/marketplace_gen/simulation/orders.py` generating orders with natural multi-seller splits.
  - Authored `tests/test_commission.py`.
- **Human Review & Actions**:
  - Reviewed integer-cents commission math and verified half-up rounding edge cases.
  - Executed unit tests locally (13 tests passed in 1.821s).

### Milestone 3: Weekly Fulfillment, Returns, Disputes, Reviews & Event Streams
- **AI Contributions**:
  - Implemented `src/marketplace_gen/simulation/fulfillment.py` modeling carrier dispatch delays, cancellations, failed deliveries, post-delivery returns, causal customer disputes, and rating penalties.
  - Generated discrete audit event streams (`FulfillmentEvent` and `DisputeEvent`).
  - Authored `tests/test_fulfillment.py` enforcing strict chronological invariants (`placed_at <= shipped_at <= delivered_at <= returned_at`).
- **Human Review & Actions**:
  - Verified causal mechanics and chronological assertions.
  - Executed unit tests locally (18 tests passed in 0.823s).

### Milestone 4: Accounting Ledger, Weekly Payouts & Status State Machine
- **AI Contributions**:
  - Implemented `src/marketplace_gen/rules/status.py` evaluating trailing 60-day metrics, 15-line volume gates, consecutive watchlist triggers, severe breach suspension, and 30-day cooldown recovery.
  - Implemented `src/marketplace_gen/ledger.py` simulating weekly Monday settlements, 14-day hold windows, 10% reserve holds for watchlist sellers, negative roll-forward balances, and suspended seller held payouts.
  - Authored `tests/test_ledger_and_status.py`.
- **Human Review & Actions**:
  - Verified signed double-entry ledger arithmetic identity (`Payout.total_cents == sum(lines.amount_cents)`).
  - Executed unit tests locally (27 tests passed in 1.450s).

### Milestone 5: Pure Structural Validator, Streaming Disk Exporters & Calibration
- **AI Contributions**:
  - Built `src/marketplace_gen/validation/structural.py` covering PK uniqueness, FK referential integrity, enum validity, chronological order, and arithmetic identities.
  - Built streaming disk exporters (`src/marketplace_gen/export.py`) streaming rows directly to CSV, JSON, and SQLite / SQL seed scripts without holding 15 DataFrames in RAM.
  - Built `src/marketplace_gen/cli.py` and root runner `run.py`.
  - Authored `tests/test_validation.py`.
- **Human Review & Actions**:
  - Addressed Python module path discovery on Windows PowerShell by establishing `run.py`.
  - Executed starter generation and validation commands locally (20,561 records exported in 1.63s with 0 errors).

### Milestone 6: Anomalies, Ground Truth, Detector & SQL Cross-Checks
- **AI Contributions**:
  - Implemented the 5 labelled anomalies in `src/marketplace_gen/anomalies/injector.py` with strict isolation rules (recomputing totals for anomalies 1, 2, and 4 so only anomaly 5 breaks totals).
  - Built decoupled ground truth exporter (`ground_truth.csv` / `.json`).
  - Built rule-based automated detector (`src/marketplace_gen/validation/detector.py`) with confusion matrix evaluation.
  - Authored `verification_queries.sql`.
  - Authored `tests/test_anomalies_and_detector.py`.
- **Debugging & Architectural Refinements**:
  - *Challenge 1*: 3 clean listings were falsely flagged by `SUSPENDED_SELLER_LISTING`. Identified that global catalog listing sampling allowed orders in early 2026 to purchase products from sellers onboarded in September 2026. Refactored `orders.py` to sample strictly from the active listing pool (`listing.created_at <= order.placed_at`).
  - *Challenge 2*: Clean dispute `DSP-2026-000089` was falsely flagged as missing. Identified that negative net weekly cycles roll forward unallocated lines. Updated detector to inspect the complete ledger (`payout_lines + unallocated_lines`).
- **Human Review & Actions**:
  - Reviewed diagnosis and approved fixes.
  - Executed tests locally (33 tests passed in 5.484s).

### Milestone 7: Analytical Reports, Reconciliation & Fixed-Seed Reproducibility
- **AI Contributions**:
  - Implemented `src/marketplace_gen/reports.py` generating `validation_summary.md/.json`, `seller_scorecard.csv`, `payout_reconciliation.csv`, `exceptions.csv`, and `reproducibility.md`.
  - Added `python run.py reproduce` subcommand.
  - Authored `tests/test_reports_and_reproducibility.py`.
- **Debugging & Resolution**:
  - *Challenge*: `SELL-000017` failed reconciliation assertion in test because `PAYOUT_TOTAL_MISMATCH` (delta = +50 cents) had altered its payout total. Refactored test to verify clean baseline reconciliation is 100% and injected dataset non-reconciled rows match ground truth 1:1.
- **Human Review & Actions**:
  - Executed full test suite locally (35 tests passed in 6.261s).
  - Executed `python run.py generate` and verified 100% Precision, Recall, and F1.
  - Executed `python run.py reproduce` and verified bitwise identical SHA-256 hashes across runs.

### Milestone 8: Documentation, Starter Packaging & Final Submission Review
- **AI Contributions**:
  - Authored comprehensive `README.md` including architectural blueprints, domain rules, table definitions, CLI instructions, and performance benchmarks.
  - Finalized `docs/AI_USAGE.md` running log.
- **Human Review & Actions**:
  - Performed final code walkthrough, reviewed documentation, and packaged starter dataset in `sample_output/starter/`.

---

## 3. Candidate Self-Reflection & Code Comprehension
I have thoroughly reviewed and tested every module in this repository. I understand the data flows, algorithms, and domain models end-to-end and am fully prepared to explain and defend every design decision, including:
1. Why floating-point money was prohibited and how integer cents half-up rounding operates.
2. How the double-entry accounting ledger guarantees reconciliation across gross sales, commissions, refunds, reversals, dispute clawbacks, and reserve withholdings.
3. How the weekly simulation loop enforces causality and why listings must be filtered chronologically.
4. How the 5 anomalies were mathematically isolated so that only anomaly 5 breaks payout arithmetic.
5. Why fixed-seed reproducibility requires omitting dynamic timestamps from output artifacts.
