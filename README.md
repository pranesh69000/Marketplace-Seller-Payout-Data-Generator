# Marketplace Seller Payout Data Generator

![Unit tests](https://img.shields.io/badge/unit%20tests-35-blue.svg)
![Seed](https://img.shields.io/badge/seed-20261022-blue.svg)
![Python](https://img.shields.io/badge/python-3.14.3%20tested-blue.svg)
![Full run detector precision](https://img.shields.io/badge/full%20run%20detector%20precision-100%25-success.svg)
![Full run detector recall](https://img.shields.io/badge/full%20run%20detector%20recall-100%25-success.svg)

A deterministic synthetic data generator for a multi-seller marketplace. It simulates sellers, listings, orders, fulfillment, reviews, disputes, commissions and weekly payout settlement. It then injects five labelled anomalies, runs a rule-based detector against a separate ground-truth file, and produces validation reports and a reproducibility check.

This is my individual submission for the YottaFlex AI candidate project. There is no UI. All data is synthetic and no external data is used.

## Contents

1. [Quick start](#quick-start)
2. [What a run produces](#what-a-run-produces)
3. [Measured results](#measured-results)
4. [Verification status](#verification-status)
5. [Known deviations and limitations](#known-deviations-and-limitations)
6. [How it works](#how-it-works)
7. [Reproducibility](#reproducibility)
8. [Data provenance](#data-provenance)
9. [AI usage and prompt history](#ai-usage-and-prompt-history)
10. [Repository structure](#repository-structure)
11. [Future enhancements](#future-enhancements)

## Quick start

These steps take you from cloning the repository to running every command. Replace `<your-username>/<repo-name>` with this repository's address.

### Prerequisites

- Git
- Python 3.14.3 (the only version I tested; other versions are untested)
- Free disk space for the generated data. The full dataset is much larger than the starter one (its size was not measured)

No database server or Docker is needed.

### 1. Clone the repository and enter the folder

```
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

### 2. Create and activate a virtual environment (recommended)

Windows PowerShell:

```
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks the activation script, allow it for this window only, then activate again:

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

macOS or Linux:

```
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install the dependencies

```
pip install -r requirements.txt
```

### 4. Run the unit tests (35 tests, standard-library `unittest`)

```
python -m unittest discover -s tests
```

Expected: a final line of `OK`.

### 5. Generate the starter dataset (scale 0.01)

```
python run.py generate --seed 20261022 --scale 0.01 --out output/starter
```

Expected: a calibration summary, `Clean baseline structural validation: PASSED (0 errors)`, 3 injected anomalies per type, a detector table, and `Pipeline complete`. It took about 3 to 5 seconds on my laptop. Results are written to `output/starter/` (`clean/`, `injected/`, `ground_truth/`, `reports/`).

### 6. Validate the exported dataset

```
python run.py validate --data output/starter/injected
```

Expected: `Dataset verification: PASSED (0 structural errors)`.

### 7. Check fixed-seed reproducibility

```
python run.py reproduce --seed 20261022 --scale 0.01
```

This runs the pipeline twice in temporary folders and compares SHA-256 hashes of every file. Expected last line: `SUCCESS: Both independent runs produced 100% bitwise identical files!`. It overwrites `docs/reproducibility.md` with the new run's report.

### 8. Generate the full dataset (scale 1.0)

```
python run.py generate --seed 20261022 --scale 1.0 --out output/full
python run.py validate --data output/full/injected
```

Generation took about 5.7 minutes on my 8 GB RAM, Intel Pentium laptop. Expect 2,000 sellers, 100,000 orders and about 204,500 order lines, with 120 injected anomalies per type. See [Measured results](#measured-results) for the dispute count and other rates, which do not all match the targets.

### Notes

- `run.py` is the supported entry point. Running `python -m marketplace_gen ...` directly only works if `src` is on the Python path (in PowerShell: `$env:PYTHONPATH="src"`).
- The scale is a parameter, so the starter and full datasets come from the same generator and the same seed.
- On macOS or Linux the commands are the same, but I only tested Windows PowerShell.

## What a run produces

Each run writes four folders under the output directory:

| Folder | Contents |
|---|---|
| `clean/` | The valid baseline, before any anomaly is injected |
| `injected/` | The same data with five types of labelled anomalies injected. No data table contains an anomaly flag |
| `ground_truth/` | A separate file listing every injected anomaly (CSV and JSON). It is only read when the detector is scored |
| `reports/` | `validation_summary.md` and `.json`, `seller_scorecard.csv`, `payout_reconciliation.csv`, `exceptions.csv` |

The data is exported as CSV for all 15 tables, plus JSON and a SQLite database with a SQL seed script. `verification_queries.sql` contains independent SQL checks that an evaluator can run against the SQLite database.

A small example is committed in `sample_output/starter/`. It was produced with:

```
python run.py generate --seed 20261022 --scale 0.01 --out sample_output/starter
```

The full dataset is not committed. Regenerate it with the full command below.
```
python run.py generate --seed 20261022 --scale 1.0 --out output/full
python run.py validate --data output/full/injected
```


## Measured results

All numbers below come from actual runs on an 8 GB RAM, Intel Pentium Windows laptop. Peak memory was **not measured**.

| Metric | Starter (scale 0.01) | Full (scale 1.0) | Target |
|---|---|---|---|
| Sellers | 20 | 2,000 | 2,000 at full scale |
| Orders | 1,000 | 100,000 | 100,000 at full scale |
| Order lines | 2,076 | 204,502 | about 210,000 (design estimate) |
| Disputes | 93 | **8,089** | 10,000 at full scale |
| Late shipment rate | 12.27% | 11.05% | about 8% |
| Cancellation rate | 1.45% | 1.44% | about 2% |
| Return rate | 6.24% | 4.79% | about 6% |
| Average rating | 3.99 | 4.05 | about 4.2 |
| Suspended sellers (as reported by the generator summary) | 3 (15%) | 465 (23.25%) | a few percent |
| Payouts settled | 510 | 51,052 | n/a |
| Injected anomalies | 15 (3 per type) | 600 (120 per type) | n/a |
| Simulation time | 0.6 to 1.2 s | 138.7 s | n/a |
| Total pipeline time | 3.3 to 5.4 s | 341.3 s (about 5.7 min) | n/a |

The targets are design goals, not guarantees. Several are not met (see below).

## Verification status

| Item | Status |
|---|---|
| Unit tests (35) | Passing at submission time |
| Structural validation, clean baseline, scale 0.01 and 1.0 | Verified: 0 errors (run inside the generate step) |
| Structural validation, injected dataset, scale 0.01 | Verified with `validate`: 0 errors |
| Structural validation, injected dataset, scale 1.0 | Verified with `validate` on `output/full/injected`: all 15 tables present, 0 structural errors |
| Detector versus ground truth, scale 0.01 and 1.0 | 100% precision and recall on 15 and 600 injected anomalies. See the caveat below |
| Detector flags on the clean baseline | Asserted to be 0 by a unit test at test scale |
| Fixed-seed reproducibility | Verified at scale 0.01 (two runs, identical SHA-256 hashes, one machine). Not run at scale 1.0 |
| `verification_queries.sql` | Provided for evaluators. Execution results are not recorded here |
| Exactly 10,000 disputes | **Not met** (8,089) |
| Distribution targets (late, returns, cancellations, rating) | **Not met**, not calibrated |
| Peak memory | Not measured |

## Known deviations and limitations

- **Dispute count.** The full run produced 8,089 disputes, about 19% below the 10,000 in the problem statement. The count is not enforced as an exact quota, and the dispute rate was not recalibrated.
- **Seller suspension is too common.** The generator summary reports 465 of 2,000 sellers (23.25%) as suspended, far above the "few percent" I intended. The thresholds in the status rules are starting defaults that were not retuned. This probably makes the seller-status data less realistic than it should be.
- **Rates differ from targets.** Late shipments are higher, and returns, cancellations and ratings are lower, than the design targets.
- **Detector scores are not evidence of general detection ability.** The detector and the anomaly injector are written from the same rule definitions, so 100% means they agree with each other. It does not show that the detector would catch unknown problems. There are only 3 (starter) or 120 (full) injected cases per type.
- **Reproducibility scope.** Identical hashes are only guaranteed with the same Python and library versions. It was verified on one machine at scale 0.01.
- **Simplifications.** Shipping and taxes are excluded, one currency (USD) is used, and partial returns are not modelled. Commission rates are illustrative, not real marketplace figures.
- **Anomaly IDs.** Injected suspended-seller listings take the next counter value for their seller, so their ID order may not match their creation dates.
- **Entry point.** The design planned `python -m marketplace_gen`. The supported entry point is `python run.py`.

More detail is in `docs/LIMITATIONS.md` and `docs/ASSUMPTIONS.md`.

## How it works

The locked design is in `docs/DESIGN.md`, and every field is documented in `docs/DATA_DICTIONARY.md`.

### Pipeline

1. Generate master data: sellers, listings, commission rules and assignments.
2. Simulate week by week: new orders (suspended sellers are skipped), fulfillment, returns, disputes and reviews, then evaluate seller status.
3. Build the payout ledger on weekly Monday cycles.
4. Validate the clean baseline, then export it.
5. Inject five labelled anomalies, then export the injected data and the separate ground truth.
6. Run the detector, score it against the ground truth, and write the reports.

One seeded random generator (`numpy.random.default_rng(20261022)`) is passed explicitly through the code. Timeline: orders from 2026-01-01 to 2026-10-15, as-of date 2026-10-31.

### Tables (15)

- **Core (10):** sellers, product listings, commission rules, orders, order lines, fulfillments, customer reviews, disputes, payouts, payout lines.
- **Bridge (1):** seller commission assignments (sellers and rules over time, with effective dates).
- **Event history (4):** seller status events, fulfillment events, dispute events, payout events. State changes are new records, and history is not overwritten.

IDs follow the problem statement: `SELL-000001`, `LIST-<seller-id>-000001`, `ORD-2026-000001`, `FUL-<order-line-id>`, `DSP-2026-000001`, `PAYOUT-2026-000001`. Order lines use `<order-id>-NN`, and the others are in the data dictionary.

### Payout ledger

All money is in integer cents. A payout is a set of signed ledger lines, and the payout total is computed from those lines.

| Entry type | Sign |
|---|---|
| SALE | + |
| COMMISSION | - |
| REFUND | - |
| COMMISSION_REVERSAL | + |
| DISPUTE_DEDUCTION | - |
| RESERVE_HOLD | - |
| RESERVE_RELEASE | + |

- Commission is `round_half_up(line_gross x rate_bps / 10000)`, computed in one function.
- A line becomes payable when it is delivered, 14 days have passed since delivery, and it has no open dispute and was not returned first.
- Returns and lost disputes after a payout create negative entries in a later payout.
- If a cycle nets negative, no payout row is created and the entries roll forward.
- Suspended sellers have payouts created but held.
- Reconciliation: gross, minus commission, minus refunds, plus reversals, minus dispute deductions, minus reserves held, plus reserves released.

### Seller status rules

States are ACTIVE, WATCHLIST and SUSPENDED, evaluated weekly on a trailing 60-day window with at least 15 lines. The metrics are late shipment rate (shipped later than 3 days after the order) and dispute rate.

| Level | Late shipment rate | Dispute rate |
|---|---|---|
| WATCHLIST | 12% or more | 9% or more |
| SUSPENDED | 20% or more | 14% or more |

A watchlisted seller who stays at the watchlist level for two consecutive evaluations is also suspended. A suspension lasts at least 30 days before moving back to WATCHLIST, and two clean evaluations return a seller to ACTIVE. Each status event stores the metrics that triggered it. Suspended sellers cannot create listings or receive new orders.

### Commission and reserve rules

- Standard rates by category, one rate change on 2026-07-01, and a reduced new-seller promotional rate for the first 90 days. The highest priority rule wins, and the rate is locked at order time.
- Sellers on WATCHLIST have 10% of net proceeds held as reserve, released 60 days later unless the seller is suspended.

### Injected anomalies

| Type | What is injected |
|---|---|
| PAYOUT_BEFORE_HOLD_RELEASE | A line's sale and commission entries moved into an earlier payout, before delivery or inside the hold window |
| COMMISSION_APPLIED_TWICE | A duplicate commission entry for the same order line |
| SUSPENDED_SELLER_LISTING | A listing created during a seller's suspension |
| DISPUTE_NOT_DEDUCTED | The deduction for a lost dispute removed |
| PAYOUT_TOTAL_MISMATCH | `total_cents` changed so it no longer equals the sum of its lines |

Each injection changes only its target rows, recomputes affected payout totals so only the mismatch type breaks arithmetic, and is recorded in `ground_truth/`. Targets do not overlap.

### Validation and detector

Structural checks cover primary keys, foreign keys, allowed values, date ordering, lifecycle transitions, duplicates and arithmetic identities. The detector applies the business rules for the five anomaly types and reports true positives, false positives, false negatives, precision, recall and F1 per type.

## Reproducibility

Run `python run.py reproduce --seed 20261022 --scale 0.01`. It runs the pipeline twice in separate temporary folders and compares SHA-256 hashes of every output file. The result is recorded in `docs/reproducibility.md`. See the limits under [Known deviations and limitations](#known-deviations-and-limitations).

## Data provenance

All data is synthetically generated from a fixed seed. No external datasets, scraped data or personal information are used. Commission rates, thresholds and distributions are illustrative assumptions, not real marketplace figures.

## AI usage and prompt history

I used Claude (chat) for planning and design decisions, and Antigravity for implementation. Every prompt I sent to both tools is in `prompts/`. `docs/AI_USAGE.md` describes where AI helped and what I reviewed and validated.

## Repository structure

```text
README.md
requirements.txt
run.py                        # entry point
verification_queries.sql      # independent SQL checks
.gitignore
prompts/                      # prompt history for every AI tool used
docs/                         # DESIGN, DATA_DICTIONARY, ASSUMPTIONS, LIMITATIONS, AI_USAGE, reproducibility
src/marketplace_gen/          # config, ids, cli, export, ledger, reports
  rules/                      # commission and seller status rules
  simulation/                 # master data, orders, fulfillment
  anomalies/                  # anomaly injectors
  validation/                 # structural checks and detector
tests/                        # unit tests
sample_output/starter/        # committed starter dataset (scale 0.01)
```

## Future enhancements

- Recalibrate dispute probability and the suspension thresholds so the full run reaches 10,000 disputes and a realistic share of suspensions.
- Enforce the dispute total as an exact weekly quota.
- Measure and report peak memory, and verify reproducibility at full scale.
- Add partial returns.
- Add a coverage report for boundary cases.
