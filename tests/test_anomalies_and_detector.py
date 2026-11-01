"""
Unit tests for Anomaly Injection, Decoupled Ground Truth, and Detector Scoring.
"""

import copy
import unittest
import numpy as np

from src.marketplace_gen.anomalies.injector import inject_anomalies
from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.ledger import simulate_weekly_ledger_and_governance
from src.marketplace_gen.simulation.fulfillment import simulate_fulfillments_and_disputes
from src.marketplace_gen.simulation.master_data import generate_master_data
from src.marketplace_gen.simulation.orders import generate_order_skeleton
from src.marketplace_gen.validation.detector import detect_all_anomalies, evaluate_detector


class TestAnomaliesAndDetector(unittest.TestCase):
    """Test suite ensuring anomaly isolation, ground-truth validity, and high detector accuracy."""

    def setUp(self) -> None:
        self.config = GeneratorConfig(seed=20261022, scale=0.01)
        self.rng = np.random.default_rng(20261022)
        self.id_gen = IdGenerator()
        self.master_data = generate_master_data(self.config, self.rng, self.id_gen)
        self.order_bundle = generate_order_skeleton(self.config, self.master_data, self.rng, self.id_gen)
        self.ful_bundle = simulate_fulfillments_and_disputes(
            self.config, self.master_data, self.order_bundle, self.rng, self.id_gen
        )
        self.settlement = simulate_weekly_ledger_and_governance(
            self.config, self.master_data, self.order_bundle, self.ful_bundle, self.id_gen
        )

    def test_clean_baseline_zero_detector_flags(self) -> None:
        """The detector must report exactly 0 flagged anomalies on the clean baseline."""
        clean_flags = detect_all_anomalies(
            self.config, self.master_data, self.order_bundle, self.ful_bundle, self.settlement
        )
        self.assertEqual(
            len(clean_flags), 0,
            f"Detector falsely flagged {len(clean_flags)} clean entities: {clean_flags[:5]}"
        )

    def test_anomaly_injection_and_detector_evaluation(self) -> None:
        """Verify injection, ground truth generation, and detector performance metrics."""
        inj_result = inject_anomalies(
            self.config, self.master_data, self.order_bundle, self.ful_bundle, self.settlement,
            self.rng, self.id_gen,
        )

        # Ensure ground truth was generated
        self.assertGreater(len(inj_result.ground_truth), 0)
        self.assertTrue(all(g.anomaly_id.startswith("GT-") for g in inj_result.ground_truth))

        # Run detector on injected dataset
        flagged = detect_all_anomalies(
            self.config, self.master_data, self.order_bundle, self.ful_bundle, self.settlement
        )
        self.assertGreater(len(flagged), 0)

        # Evaluate detector against ground truth
        eval_report = evaluate_detector(inj_result.ground_truth, flagged)

        # Precision and Recall should be >= 95%
        self.assertGreaterEqual(eval_report.overall_precision, 0.95)
        self.assertGreaterEqual(eval_report.overall_recall, 0.95)
        self.assertGreaterEqual(eval_report.overall_f1, 0.95)

    def test_isolation_rule_payout_totals(self) -> None:
        """Only PAYOUT_TOTAL_MISMATCH should break Payout arithmetic totals."""
        inj_result = inject_anomalies(
            self.config, self.master_data, self.order_bundle, self.ful_bundle, self.settlement,
            self.rng, self.id_gen,
        )

        gt_mismatch_payout_ids = {
            g.entity_id for g in inj_result.ground_truth if g.issue_type == "PAYOUT_TOTAL_MISMATCH"
        }

        arithmetic_mismatches = []
        for p in self.settlement.payouts:
            sum_lines = sum(l.amount_cents for l in p.lines)
            if p.total_cents != sum_lines:
                arithmetic_mismatches.append(p.payout_id)

        # Mismatches must match the PAYOUT_TOTAL_MISMATCH target IDs
        self.assertEqual(set(arithmetic_mismatches), gt_mismatch_payout_ids)


if __name__ == "__main__":
    unittest.main()

