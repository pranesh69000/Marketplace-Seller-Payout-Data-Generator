"""
Unit tests for Report Generation, Financial Reconciliation, and Fixed-Seed Reproducibility.
"""

import copy
import csv
import json
import os
import shutil
import tempfile
import unittest
import numpy as np

from src.marketplace_gen.anomalies.injector import inject_anomalies
from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.ledger import simulate_weekly_ledger_and_governance
from src.marketplace_gen.reports import (
    compute_sha256,
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


class TestReportsAndReproducibility(unittest.TestCase):
    """Test suite ensuring all analytical reports generate correctly and match invariants."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.config = GeneratorConfig(seed=20261022, scale=0.01)
        cls.rng = np.random.default_rng(20261022)
        cls.id_gen = IdGenerator()
        cls.master_data = generate_master_data(cls.config, cls.rng, cls.id_gen)
        cls.order_bundle = generate_order_skeleton(cls.config, cls.master_data, cls.rng, cls.id_gen)
        cls.ful_bundle = simulate_fulfillments_and_disputes(
            cls.config, cls.master_data, cls.order_bundle, cls.rng, cls.id_gen
        )
        cls.clean_settlement = simulate_weekly_ledger_and_governance(
            cls.config, cls.master_data, cls.order_bundle, cls.ful_bundle, cls.id_gen
        )
        cls.clean_val = validate_structural_integrity(
            cls.config, cls.master_data, cls.order_bundle, cls.ful_bundle, cls.clean_settlement
        )

        # Deep-copy settlement before anomaly injection to preserve clean state
        cls.settlement = copy.deepcopy(cls.clean_settlement)
        cls.inj_result = inject_anomalies(
            cls.config, cls.master_data, cls.order_bundle, cls.ful_bundle, cls.settlement,
            cls.rng, cls.id_gen
        )
        cls.flagged = detect_all_anomalies(
            cls.config, cls.master_data, cls.order_bundle, cls.ful_bundle, cls.settlement
        )
        cls.eval_report = evaluate_detector(cls.inj_result.ground_truth, cls.flagged)

    def test_all_reports_generation(self) -> None:
        """Verify that all report files are successfully generated and populated."""
        temp_dir = tempfile.mkdtemp()
        try:
            # 1. Validation summary
            md_path, json_path = generate_validation_summary(
                self.config, self.master_data, self.order_bundle, self.ful_bundle, self.settlement,
                self.clean_val, self.inj_result, self.eval_report, temp_dir
            )
            self.assertTrue(os.path.exists(md_path))
            self.assertTrue(os.path.exists(json_path))

            with open(json_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)
            self.assertIn("distributions", summary_data)
            self.assertIn("detector_evaluation", summary_data)
            self.assertEqual(summary_data["structural_validation"]["status"], "PASSED")

            # 2. Seller scorecard
            card_path = generate_seller_scorecard(
                self.master_data, self.order_bundle, self.ful_bundle, self.settlement, temp_dir
            )
            self.assertTrue(os.path.exists(card_path))

            # 3. Payout reconciliation on clean settlement
            recon_path = generate_payout_reconciliation(
                self.master_data, self.order_bundle, self.ful_bundle, self.clean_settlement, temp_dir
            )
            self.assertTrue(os.path.exists(recon_path))

            # Read reconciliation file and assert all sellers reconcile on clean baseline
            with open(recon_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.assertEqual(
                        row["is_reconciled"], "True",
                        f"Seller {row['seller_id']} did not reconcile: delta={row['reconciled_delta_cents']}"
                    )

            # Also verify that on injected settlement, only the PAYOUT_TOTAL_MISMATCH sellers have is_reconciled == False
            injected_recon_path = os.path.join(temp_dir, "injected_reconciliation.csv")
            generate_payout_reconciliation(
                self.master_data, self.order_bundle, self.ful_bundle, self.settlement, temp_dir
            )
            mismatch_sellers = {
                g.related_ids for g in self.inj_result.ground_truth if g.issue_type == "PAYOUT_TOTAL_MISMATCH"
            }
            with open(os.path.join(temp_dir, "payout_reconciliation.csv"), "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row["seller_id"] in mismatch_sellers:
                        self.assertEqual(row["is_reconciled"], "False")
                    else:
                        self.assertEqual(row["is_reconciled"], "True")

            # 4. Exceptions report
            exc_path = generate_exceptions_report(self.flagged, temp_dir)
            self.assertTrue(os.path.exists(exc_path))

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_reproducibility_report_logic(self) -> None:
        """Verify that identical directories produce 100% matching report."""
        temp_dir = tempfile.mkdtemp()
        try:
            dir1 = os.path.join(temp_dir, "run1")
            dir2 = os.path.join(temp_dir, "run2")
            os.makedirs(dir1)
            os.makedirs(dir2)

            # Write identical test files
            with open(os.path.join(dir1, "test.csv"), "w") as f1, open(os.path.join(dir2, "test.csv"), "w") as f2:
                f1.write("a,b,c\n1,2,3\n")
                f2.write("a,b,c\n1,2,3\n")

            rep_path = os.path.join(temp_dir, "reproducibility.md")
            generate_reproducibility_report(dir1, dir2, 20261022, 0.01, rep_path)

            self.assertTrue(os.path.exists(rep_path))
            with open(rep_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("BITWISE IDENTICAL", content)
            self.assertNotIn("MISMATCH", content)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

