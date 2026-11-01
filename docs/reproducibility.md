# Reproducibility Verification Report

**Seed**: `20261022` | **Scale**: `0.01` | **Platform**: `Windows (AMD64)`  
**Python Version**: `3.14.3`  

> [!IMPORTANT]
> Fixed-seed reproducibility guarantees identical byte-for-byte SHA-256 file hashes across independent generator executions using the same Python and NumPy versions.

## File Hash Comparison Table

| Relative File Path | Run 1 Size (Bytes) | Run 2 Size (Bytes) | Run 1 SHA-256 | Run 2 SHA-256 | Match |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `clean/csv/commission_rules.csv` | 467 | 467 | `abc4a730740d24e4...` | `abc4a730740d24e4...` | **MATCH** |
| `clean/csv/customer_reviews.csv` | 73,881 | 73,881 | `27fc7c09baa97dc7...` | `27fc7c09baa97dc7...` | **MATCH** |
| `clean/csv/dispute_events.csv` | 19,660 | 19,660 | `aad5f76ba11dd223...` | `aad5f76ba11dd223...` | **MATCH** |
| `clean/csv/disputes.csv` | 10,495 | 10,495 | `8356f05da01ea3ba...` | `8356f05da01ea3ba...` | **MATCH** |
| `clean/csv/fulfillment_events.csv` | 579,662 | 579,662 | `60d2c97330574f3f...` | `60d2c97330574f3f...` | **MATCH** |
| `clean/csv/fulfillments.csv` | 228,750 | 228,750 | `c79d3f5a9db1c35b...` | `c79d3f5a9db1c35b...` | **MATCH** |
| `clean/csv/order_lines.csv` | 210,634 | 210,634 | `8b6f0532a301dfd7...` | `8b6f0532a301dfd7...` | **MATCH** |
| `clean/csv/orders.csv` | 63,482 | 63,482 | `dbbe961ff613054c...` | `dbbe961ff613054c...` | **MATCH** |
| `clean/csv/payout_events.csv` | 62,769 | 62,769 | `9c50d41e99fc0be9...` | `9c50d41e99fc0be9...` | **MATCH** |
| `clean/csv/payout_lines.csv` | 472,515 | 472,515 | `7d7ac84fdf1afda2...` | `7d7ac84fdf1afda2...` | **MATCH** |
| `clean/csv/payouts.csv` | 37,048 | 37,048 | `7d4bf1e0a392e7e9...` | `7d4bf1e0a392e7e9...` | **MATCH** |
| `clean/csv/product_listings.csv` | 14,972 | 14,972 | `db6e8052d3a545ed...` | `db6e8052d3a545ed...` | **MATCH** |
| `clean/csv/seller_commission_assignments.csv` | 7,172 | 7,172 | `96dc30177d9b4621...` | `96dc30177d9b4621...` | **MATCH** |
| `clean/csv/seller_status_events.csv` | 8,833 | 8,833 | `e15963c09ccffbc8...` | `e15963c09ccffbc8...` | **MATCH** |
| `clean/csv/sellers.csv` | 2,525 | 2,525 | `39811866eb893d53...` | `39811866eb893d53...` | **MATCH** |
| `clean/json/commission_rules.json` | 1,341 | 1,341 | `db1a89ff8b301afb...` | `db1a89ff8b301afb...` | **MATCH** |
| `clean/json/customer_reviews.json` | 136,286 | 136,286 | `8617fbaa6e41f0b4...` | `8617fbaa6e41f0b4...` | **MATCH** |
| `clean/json/dispute_events.json` | 33,483 | 33,483 | `6b5a1ea805e5e4d0...` | `6b5a1ea805e5e4d0...` | **MATCH** |
| `clean/json/disputes.json` | 22,793 | 22,793 | `1afe6871bfc286a3...` | `1afe6871bfc286a3...` | **MATCH** |
| `clean/json/fulfillment_events.json` | 1,195,670 | 1,195,670 | `5d3e3cf949199dba...` | `5d3e3cf949199dba...` | **MATCH** |
| `clean/json/fulfillments.json` | 566,957 | 566,957 | `5ee6ef6c1044e97b...` | `5ee6ef6c1044e97b...` | **MATCH** |
| `clean/json/order_lines.json` | 617,394 | 617,394 | `64516fa978692854...` | `64516fa978692854...` | **MATCH** |
| `clean/json/orders.json` | 158,425 | 158,425 | `62ea2f5403b315fe...` | `62ea2f5403b315fe...` | **MATCH** |
| `clean/json/payout_events.json` | 132,095 | 132,095 | `8d67067b2abf45fa...` | `8d67067b2abf45fa...` | **MATCH** |
| `clean/json/payout_lines.json` | 1,106,678 | 1,106,678 | `17b20eda37afff62...` | `17b20eda37afff62...` | **MATCH** |
| `clean/json/payouts.json` | 89,010 | 89,010 | `4d62227e5479fed3...` | `4d62227e5479fed3...` | **MATCH** |
| `clean/json/product_listings.json` | 32,358 | 32,358 | `fdbf5866081a12b1...` | `fdbf5866081a12b1...` | **MATCH** |
| `clean/json/seller_commission_assignments.json` | 21,837 | 21,837 | `f0a226d1ca6623f4...` | `f0a226d1ca6623f4...` | **MATCH** |
| `clean/json/seller_status_events.json` | 23,213 | 23,213 | `8b2477ea250007f2...` | `8b2477ea250007f2...` | **MATCH** |
| `clean/json/sellers.json` | 5,066 | 5,066 | `be52b110928a970a...` | `be52b110928a970a...` | **MATCH** |
| `clean/marketplace.db` | 2,777,088 | 2,777,088 | `fcc876a0f3aa7ce0...` | `fcc876a0f3aa7ce0...` | **MATCH** |
| `clean/seed.sql` | 4,577,385 | 4,577,385 | `a4071c52f8b3cf96...` | `a4071c52f8b3cf96...` | **MATCH** |
| `ground_truth/ground_truth.csv` | 3,187 | 3,187 | `f58d34549a12edde...` | `f58d34549a12edde...` | **MATCH** |
| `ground_truth/ground_truth.json` | 5,335 | 5,335 | `12b35acbff211099...` | `12b35acbff211099...` | **MATCH** |
| `injected/csv/commission_rules.csv` | 467 | 467 | `abc4a730740d24e4...` | `abc4a730740d24e4...` | **MATCH** |
| `injected/csv/customer_reviews.csv` | 73,881 | 73,881 | `27fc7c09baa97dc7...` | `27fc7c09baa97dc7...` | **MATCH** |
| `injected/csv/dispute_events.csv` | 19,660 | 19,660 | `aad5f76ba11dd223...` | `aad5f76ba11dd223...` | **MATCH** |
| `injected/csv/disputes.csv` | 10,495 | 10,495 | `8356f05da01ea3ba...` | `8356f05da01ea3ba...` | **MATCH** |
| `injected/csv/fulfillment_events.csv` | 579,662 | 579,662 | `60d2c97330574f3f...` | `60d2c97330574f3f...` | **MATCH** |
| `injected/csv/fulfillments.csv` | 228,750 | 228,750 | `c79d3f5a9db1c35b...` | `c79d3f5a9db1c35b...` | **MATCH** |
| `injected/csv/order_lines.csv` | 210,634 | 210,634 | `8b6f0532a301dfd7...` | `8b6f0532a301dfd7...` | **MATCH** |
| `injected/csv/orders.csv` | 63,482 | 63,482 | `dbbe961ff613054c...` | `dbbe961ff613054c...` | **MATCH** |
| `injected/csv/payout_events.csv` | 62,769 | 62,769 | `9c50d41e99fc0be9...` | `9c50d41e99fc0be9...` | **MATCH** |
| `injected/csv/payout_lines.csv` | 472,537 | 472,537 | `8f64e54abc67c748...` | `8f64e54abc67c748...` | **MATCH** |
| `injected/csv/payouts.csv` | 37,049 | 37,049 | `bf76d6398c03fa63...` | `bf76d6398c03fa63...` | **MATCH** |
| `injected/csv/product_listings.csv` | 15,313 | 15,313 | `e86ff650b2955dc3...` | `e86ff650b2955dc3...` | **MATCH** |
| `injected/csv/seller_commission_assignments.csv` | 7,172 | 7,172 | `96dc30177d9b4621...` | `96dc30177d9b4621...` | **MATCH** |
| `injected/csv/seller_status_events.csv` | 8,833 | 8,833 | `e15963c09ccffbc8...` | `e15963c09ccffbc8...` | **MATCH** |
| `injected/csv/sellers.csv` | 2,525 | 2,525 | `39811866eb893d53...` | `39811866eb893d53...` | **MATCH** |
| `injected/json/commission_rules.json` | 1,341 | 1,341 | `db1a89ff8b301afb...` | `db1a89ff8b301afb...` | **MATCH** |
| `injected/json/customer_reviews.json` | 136,286 | 136,286 | `8617fbaa6e41f0b4...` | `8617fbaa6e41f0b4...` | **MATCH** |
| `injected/json/dispute_events.json` | 33,483 | 33,483 | `6b5a1ea805e5e4d0...` | `6b5a1ea805e5e4d0...` | **MATCH** |
| `injected/json/disputes.json` | 22,793 | 22,793 | `1afe6871bfc286a3...` | `1afe6871bfc286a3...` | **MATCH** |
| `injected/json/fulfillment_events.json` | 1,195,670 | 1,195,670 | `5d3e3cf949199dba...` | `5d3e3cf949199dba...` | **MATCH** |
| `injected/json/fulfillments.json` | 566,957 | 566,957 | `5ee6ef6c1044e97b...` | `5ee6ef6c1044e97b...` | **MATCH** |
| `injected/json/order_lines.json` | 617,394 | 617,394 | `64516fa978692854...` | `64516fa978692854...` | **MATCH** |
| `injected/json/orders.json` | 158,425 | 158,425 | `62ea2f5403b315fe...` | `62ea2f5403b315fe...` | **MATCH** |
| `injected/json/payout_events.json` | 132,095 | 132,095 | `8d67067b2abf45fa...` | `8d67067b2abf45fa...` | **MATCH** |
| `injected/json/payout_lines.json` | 1,106,694 | 1,106,694 | `d43ebba7341e714b...` | `d43ebba7341e714b...` | **MATCH** |
| `injected/json/payouts.json` | 89,011 | 89,011 | `44b99e24a8f788da...` | `44b99e24a8f788da...` | **MATCH** |
| `injected/json/product_listings.json` | 33,077 | 33,077 | `d2497b09d3452c41...` | `d2497b09d3452c41...` | **MATCH** |
| `injected/json/seller_commission_assignments.json` | 21,837 | 21,837 | `f0a226d1ca6623f4...` | `f0a226d1ca6623f4...` | **MATCH** |
| `injected/json/seller_status_events.json` | 23,213 | 23,213 | `8b2477ea250007f2...` | `8b2477ea250007f2...` | **MATCH** |
| `injected/json/sellers.json` | 5,066 | 5,066 | `be52b110928a970a...` | `be52b110928a970a...` | **MATCH** |
| `injected/marketplace.db` | 2,777,088 | 2,777,088 | `d1df77708bcf54d8...` | `d1df77708bcf54d8...` | **MATCH** |
| `injected/seed.sql` | 4,578,184 | 4,578,184 | `964851e1f639499f...` | `964851e1f639499f...` | **MATCH** |
| `reports/exceptions.csv` | 3,008 | 3,008 | `659eae5337b7ca59...` | `659eae5337b7ca59...` | **MATCH** |
| `reports/payout_reconciliation.csv` | 1,442 | 1,442 | `1fbb6f1a983bc96f...` | `1fbb6f1a983bc96f...` | **MATCH** |
| `reports/seller_scorecard.csv` | 1,520 | 1,520 | `a46c476daa233ccd...` | `a46c476daa233ccd...` | **MATCH** |
| `reports/validation_summary.json` | 2,345 | 2,345 | `359d4dc8a94e0e17...` | `359d4dc8a94e0e17...` | **MATCH** |
| `reports/validation_summary.md` | 2,306 | 2,306 | `95d95f50934c0677...` | `95d95f50934c0677...` | **MATCH** |

---
**Final Verdict**: **BITWISE IDENTICAL (100% REPRODUCIBLE)**
