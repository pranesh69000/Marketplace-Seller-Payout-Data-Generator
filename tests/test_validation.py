"""
Unit tests for Structural Validator, Invariant Checkers, and Disk Exporters.
"""

from datetime import datetime, timedelta
import os
import shutil
import sqlite3
import tempfile
import unittest
import numpy as np

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.export import export_all_tables
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.ledger import simulate_weekly_ledger_and_governance
from src.marketplace_gen.simulation.fulfillment import simulate_fulfillments_and_disputes
from src.marketplace_gen.simulation.master_data import generate_master_data
from src.marketplace_gen.simulation.orders import generate_order_skeleton
from src.marketplace_gen.validation.structural import validate_structural_integrity


class TestValidationAndExport(unittest.TestCase):
    """Test suite ensuring zero-error clean baseline validation and reliable disk export."""

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
        cls.settlement = simulate_weekly_ledger_and_governance(
            cls.config, cls.master_data, cls.order_bundle, cls.ful_bundle, cls.id_gen
        )

    def test_clean_baseline_zero_validation_errors(self) -> None:
        """The clean baseline dataset must pass structural validation with exactly 0 errors."""
        report = validate_structural_integrity(
            self.config, self.master_data, self.order_bundle, self.ful_bundle, self.settlement
        )
        self.assertTrue(report.is_valid, f"Clean baseline had {len(report.errors)} errors: {report.errors[:5]}")
        self.assertEqual(len(report.errors), 0)
        self.assertGreaterEqual(report.total_checks_run, 5)

    def test_arithmetic_corruption_detection(self) -> None:
        """Validator must detect corrupted arithmetic totals."""
        if not self.settlement.payouts:
            self.skipTest("No payouts in settlement to test")

        payout = self.settlement.payouts[0]
        original_total = payout.total_cents
        try:
            # Deliberately corrupt total
            payout.total_cents = original_total + 100
            report = validate_structural_integrity(
                self.config, self.master_data, self.order_bundle, self.ful_bundle, self.settlement
            )
            self.assertFalse(report.is_valid)
            mismatch_errors = [e for e in report.errors if e.check_name == "ARITHMETIC_IDENTITY"]
            self.assertGreater(len(mismatch_errors), 0)
        finally:
            # Restore original
            payout.total_cents = original_total

    def test_disk_export_and_sqlite_verification(self) -> None:
        """Test streaming export to CSV, JSON, and SQLite; verify query execution."""
        temp_dir = tempfile.mkdtemp()
        try:
            counts = export_all_tables(
                temp_dir, self.master_data, self.order_bundle, self.ful_bundle, self.settlement
            )
            # Verify 15 tables exported
            self.assertEqual(len(counts), 15)
            self.assertGreater(counts["sellers"], 0)
            self.assertGreater(counts["orders"], 0)
            self.assertGreater(counts["payouts"], 0)

            # Check SQLite database
            db_path = os.path.join(temp_dir, "marketplace.db")
            self.assertTrue(os.path.exists(db_path))
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sellers")
            db_sellers_count = cur.fetchone()[0]
            self.assertEqual(db_sellers_count, counts["sellers"])

            cur.execute("SELECT COUNT(*) FROM orders")
            db_orders_count = cur.fetchone()[0]
            self.assertEqual(db_orders_count, counts["orders"])
            conn.close()

            # Check seed.sql
            seed_sql_path = os.path.join(temp_dir, "seed.sql")
            self.assertTrue(os.path.exists(seed_sql_path))
            self.assertGreater(os.path.getsize(seed_sql_path), 1000)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

