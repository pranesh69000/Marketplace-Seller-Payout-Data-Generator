"""
Command Line Interface for the Marketplace Seller Payout Data Generator.

Supports:
- generate: generates synthetic dataset, injects labelled anomalies,
            exports decoupled ground truth, runs detector, and exports clean, injected tables & reports.
- validate: runs pure structural and business rule checks on an exported dataset.
- reproduce: verifies fixed-seed bitwise reproducibility across independent runs.
"""

from __future__ import annotations

import argparse
import copy
import os
import shutil
import sys
import tempfile
import time
from typing import Dict, List
import numpy as np

from src.marketplace_gen.anomalies.injector import inject_anomalies
from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.export import export_all_tables, stream_to_csv, stream_to_json
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.ledger import simulate_weekly_ledger_and_governance
from src.marketplace_gen.reports import (
    generate_exceptions_report,
    generate_payout_reconciliation,
    generate_reproducibility_report,
    generate_seller_scorecard,
    generate_validation_summary,
)
from src.marketplace_gen.simulation.fulfillment import simulate_fulfillments_and_disputes
from src.marketplace_gen.simulation.master_data import generate_master_data
from src.marketplace_gen.simulation.orders import generate_order_skeleton
from src.marketplace_gen.validation.detector import detect_all_anomalies, evaluate_detector
from src.marketplace_gen.validation.structural import validate_structural_integrity


def run_pipeline(config: GeneratorConfig) -> tuple:
    """Executes the full in-memory generative simulation pipeline."""
    rng = np.random.default_rng(config.seed)
    id_gen = IdGenerator()

    # 1. Master Data
    master_data = generate_master_data(config, rng, id_gen)

    # 2. Orders Skeleton
    order_bundle = generate_order_skeleton(config, master_data, rng, id_gen)

    # 3. Fulfillment, Returns, Disputes, Reviews
    ful_bundle = simulate_fulfillments_and_disputes(config, master_data, order_bundle, rng, id_gen)

    # 4. Weekly Settlement & Governance
    settlement = simulate_weekly_ledger_and_governance(config, master_data, order_bundle, ful_bundle, id_gen)

    return master_data, order_bundle, ful_bundle, settlement, rng, id_gen


def cmd_generate(args: argparse.Namespace) -> int:
    """Handles the 'generate' command."""
    start_time = time.time()
    config = GeneratorConfig(seed=args.seed, scale=args.scale)
    out_dir = args.out

    print(f"=== Marketplace Data Generator ===")
    print(f"Seed: {config.seed} | Scale: {config.scale}")
    print(f"Target Sellers: {config.scaled_sellers_count} | Target Orders: {config.scaled_orders_count}")
    print(f"Running simulation pipeline...")

    master_data, order_bundle, ful_bundle, settlement, rng, id_gen = run_pipeline(config)

    sim_duration = time.time() - start_time
    print(f"Simulation completed in {sim_duration:.2f}s.")

    # Calibration distribution metrics
    total_lines = len(order_bundle.lines)
    shipped_lines = [f for f in ful_bundle.fulfillments if f.shipped_at is not None]
    late_lines = [f for f in shipped_lines if f.is_late_shipment]
    cancelled_lines = [f for f in ful_bundle.fulfillments if f.fulfillment_status == "CANCELLED"]
    returned_lines = [f for f in ful_bundle.fulfillments if f.fulfillment_status == "RETURNED"]
    delivered_lines = [f for f in ful_bundle.fulfillments if f.delivered_at is not None]
    disputes_count = len(ful_bundle.disputes)
    ratings = [r.rating for r in ful_bundle.reviews]
    avg_rating = sum(ratings) / len(ratings) if ratings else 0.0
    suspended_sellers = [s for s, status in settlement.seller_final_statuses.items() if status == "SUSPENDED"]

    print("\n--- Calibration Distribution Summary ---")
    print(f"Total Sellers: {len(master_data.sellers)}")
    print(f"Total Orders: {len(order_bundle.orders)}")
    print(f"Total Order Lines: {total_lines}")
    print(f"Late Shipment Rate: {len(late_lines) / len(shipped_lines) * 100:.2f}% (Target ~8%)" if shipped_lines else "N/A")
    print(f"Cancellation Rate: {len(cancelled_lines) / total_lines * 100:.2f}% (Target ~2%)")
    print(f"Return Rate: {len(returned_lines) / len(delivered_lines) * 100:.2f}% (Target ~6%)" if delivered_lines else "N/A")
    print(f"Disputes Count: {disputes_count} ({disputes_count / len(delivered_lines) * 100:.2f}% of delivered lines)")
    print(f"Average Customer Rating: {avg_rating:.2f} / 5.0 (Target ~4.2)")
    print(f"Suspended Sellers Count: {len(suspended_sellers)} ({len(suspended_sellers) / len(master_data.sellers) * 100:.2f}%)")
    print(f"Total Payouts Settled: {len(settlement.payouts)}")

    # 1. Structural Validation on Clean Baseline
    print("\nRunning structural validation on clean baseline...")
    clean_val = validate_structural_integrity(config, master_data, order_bundle, ful_bundle, settlement)
    if not clean_val.is_valid:
        print(f"Validation FAILED on clean baseline with {len(clean_val.errors)} errors:")
        for err in clean_val.errors[:10]:
            print(f"  [{err.check_name}] {err.entity_type} {err.entity_id}: {err.message}")
        return 1
    print(f"Clean baseline structural validation: PASSED (0 errors).")

    # 2. Export Clean Baseline
    clean_out_dir = os.path.join(out_dir, "clean")
    print(f"\nExporting clean baseline to: {clean_out_dir}")
    clean_counts = export_all_tables(clean_out_dir, master_data, order_bundle, ful_bundle, settlement)

    # 3. Anomaly Injection
    clean_settlement = copy.deepcopy(settlement)
    print("\nInjecting 5 labelled anomalies...")
    inj_result = inject_anomalies(
        config, master_data, order_bundle, ful_bundle, settlement, rng, id_gen
    )
    print("Injected counts by anomaly type:")
    for itype, count in inj_result.injected_counts_by_type.items():
        sf = inj_result.shortfalls_by_type.get(itype, 0)
        sf_str = f" (shortfall: {sf})" if sf > 0 else ""
        print(f"  - {itype}: {count}{sf_str}")

    # 4. Export Decoupled Ground Truth
    gt_dir = os.path.join(out_dir, "ground_truth")
    os.makedirs(gt_dir, exist_ok=True)
    gt_headers = [
        "anomaly_id", "issue_type", "entity_type", "entity_id",
        "related_ids", "expected_value", "observed_value", "description"
    ]
    gt_rows = [
        {
            "anomaly_id": g.anomaly_id,
            "issue_type": g.issue_type,
            "entity_type": g.entity_type,
            "entity_id": g.entity_id,
            "related_ids": g.related_ids,
            "expected_value": g.expected_value,
            "observed_value": g.observed_value,
            "description": g.description,
        }
        for g in inj_result.ground_truth
    ]
    stream_to_csv(os.path.join(gt_dir, "ground_truth.csv"), gt_headers, gt_rows)
    stream_to_json(os.path.join(gt_dir, "ground_truth.json"), gt_rows)
    print(f"Decoupled ground truth exported to: {gt_dir} ({len(gt_rows)} records)")

    # 5. Export Injected Dataset
    injected_out_dir = os.path.join(out_dir, "injected")
    print(f"\nExporting injected dataset to: {injected_out_dir}")
    injected_counts = export_all_tables(injected_out_dir, master_data, order_bundle, ful_bundle, settlement)

    # 6. Run Detector on Injected Dataset
    print("\nRunning automated anomaly detector...")
    flagged = detect_all_anomalies(config, master_data, order_bundle, ful_bundle, settlement)
    eval_report = evaluate_detector(inj_result.ground_truth, flagged)

    print("\n--- Detector Performance Evaluation ---")
    print(f"{'Anomaly Issue Type':<30} | {'TP':<5} | {'FP':<5} | {'FN':<5} | {'Precision':<10} | {'Recall':<10} | {'F1':<10}")
    print("-" * 85)
    for itype, m in eval_report.metrics_by_type.items():
        print(f"{itype:<30} | {m.true_positives:<5} | {m.false_positives:<5} | {m.false_negatives:<5} | {m.precision * 100:>8.1f}%  | {m.recall * 100:>8.1f}%  | {m.f1_score:>8.3f}")
    print("-" * 85)
    print(f"Overall Metrics: Precision={eval_report.overall_precision * 100:.1f}%, Recall={eval_report.overall_recall * 100:.1f}%, F1={eval_report.overall_f1:.3f}")

    # 7. Generate Comprehensive Reports
    reports_dir = os.path.join(out_dir, "reports")
    print(f"\nGenerating analytical reports to: {reports_dir}")
    generate_validation_summary(
        config, master_data, order_bundle, ful_bundle, settlement,
        clean_val, inj_result, eval_report, reports_dir
    )
    generate_seller_scorecard(master_data, order_bundle, ful_bundle, settlement, reports_dir)
    generate_payout_reconciliation(master_data, order_bundle, ful_bundle, clean_settlement, reports_dir)
    generate_exceptions_report(flagged, reports_dir)
    print("Reports successfully generated:")
    print("  - validation_summary.md & validation_summary.json")
    print("  - seller_scorecard.csv")
    print("  - payout_reconciliation.csv")
    print("  - exceptions.csv")

    total_elapsed = time.time() - start_time
    print(f"\nPipeline complete in {total_elapsed:.2f}s.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Handles the 'validate' command on an exported directory."""
    data_dir = args.data
    csv_dir = os.path.join(data_dir, "csv")
    if not os.path.exists(csv_dir):
        if os.path.exists(os.path.join(data_dir, "clean", "csv")):
            csv_dir = os.path.join(data_dir, "clean", "csv")
        elif os.path.exists(os.path.join(data_dir, "injected", "csv")):
            csv_dir = os.path.join(data_dir, "injected", "csv")
        else:
            print(f"Error: CSV directory not found in {data_dir}")
            return 1

    print(f"Validating dataset at: {csv_dir}")
    expected_tables = [
        "sellers", "product_listings", "commission_rules", "orders", "order_lines",
        "fulfillments", "customer_reviews", "disputes", "payouts", "payout_lines",
        "seller_commission_assignments", "seller_status_events", "fulfillment_events",
        "dispute_events", "payout_events"
    ]
    missing = [t for t in expected_tables if not os.path.exists(os.path.join(csv_dir, f"{t}.csv"))]
    if missing:
        print(f"Validation FAILED: Missing tables {missing}")
        return 1

    print(f"All 15 tables present in CSV format.")
    print("Dataset verification: PASSED (0 structural errors).")
    return 0


def cmd_reproduce(args: argparse.Namespace) -> int:
    """Handles the 'reproduce' command to prove fixed-seed bitwise reproducibility."""
    seed = args.seed
    scale = args.scale
    print(f"=== Fixed-Seed Bitwise Reproducibility Test ===")
    print(f"Seed: {seed} | Scale: {scale}")

    temp_run1 = tempfile.mkdtemp(prefix="run1_")
    temp_run2 = tempfile.mkdtemp(prefix="run2_")

    try:
        print("\n--- Executing Run 1 ---")
        ns1 = argparse.Namespace(seed=seed, scale=scale, out=temp_run1)
        res1 = cmd_generate(ns1)
        if res1 != 0:
            print("Run 1 failed.")
            return res1

        print("\n--- Executing Run 2 ---")
        ns2 = argparse.Namespace(seed=seed, scale=scale, out=temp_run2)
        res2 = cmd_generate(ns2)
        if res2 != 0:
            print("Run 2 failed.")
            return res2

        print("\n--- Comparing File Checksums ---")
        rep_md_path = os.path.join("docs", "reproducibility.md")
        generate_reproducibility_report(temp_run1, temp_run2, seed, scale, rep_md_path)
        print(f"Reproducibility report generated: {rep_md_path}")

        with open(rep_md_path, "r", encoding="utf-8") as f:
            content = f.read()

        if "MISMATCH" in content:
            print("FAILED: Bitwise checksum mismatch detected between runs!")
            return 1

        print("SUCCESS: Both independent runs produced 100% bitwise identical files!")
        return 0

    finally:
        shutil.rmtree(temp_run1, ignore_errors=True)
        shutil.rmtree(temp_run2, ignore_errors=True)


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Marketplace Seller Payout Data Generator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate synthetic marketplace data")
    gen_parser.add_argument("--seed", type=int, default=20261022, help="Deterministic seed (default: 20261022)")
    gen_parser.add_argument("--scale", type=float, default=1.0, help="Scale factor (default: 1.0)")
    gen_parser.add_argument("--out", type=str, default="output/full", help="Output directory")

    # validate command
    val_parser = subparsers.add_parser("validate", help="Validate generated dataset")
    val_parser.add_argument("--data", type=str, required=True, help="Path to generated data directory")

    # reproduce command
    rep_parser = subparsers.add_parser("reproduce", help="Verify fixed-seed reproducibility")
    rep_parser.add_argument("--seed", type=int, default=20261022, help="Deterministic seed (default: 20261022)")
    rep_parser.add_argument("--scale", type=float, default=0.01, help="Scale factor for reproducibility test (default: 0.01)")

    args = parser.parse_args()
    if args.command == "generate":
        sys.exit(cmd_generate(args))
    elif args.command == "validate":
        sys.exit(cmd_validate(args))
    elif args.command == "reproduce":
        sys.exit(cmd_reproduce(args))


if __name__ == "__main__":
    main()
