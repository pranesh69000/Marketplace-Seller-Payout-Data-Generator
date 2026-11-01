"""
Unit tests for commission calculation, rule resolution, and master data generation.
"""

from datetime import date, datetime
import unittest
import numpy as np

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.rules.commission import (
    CommissionRuleRecord,
    calculate_commission,
    resolve_commission_rule,
    round_half_up,
)
from src.marketplace_gen.simulation.master_data import generate_commission_rules, generate_master_data
from src.marketplace_gen.simulation.orders import generate_order_skeleton


class TestCommissionRules(unittest.TestCase):
    """Test suite for pure commission math and resolution."""

    def test_round_half_up(self) -> None:
        # Exact integer division
        self.assertEqual(round_half_up(100000), 10)
        # Halfway case (5000 / 10000 = 0.5 -> 1)
        self.assertEqual(round_half_up(5000), 1)
        # Below halfway (4999 / 10000 -> 0)
        self.assertEqual(round_half_up(4999), 0)
        # Negative halfway (-5000 / 10000 -> -1)
        self.assertEqual(round_half_up(-5000), -1)
        self.assertEqual(round_half_up(-4999), 0)

    def test_calculate_commission_integer_cents(self) -> None:
        # $10.00 (1000 cents) at 800 bps (8.00%) = 80 cents ($0.80)
        self.assertEqual(calculate_commission(1000, 800), 80)
        # $12.50 (1250 cents) at 950 bps (9.50%) = 118.75 cents -> 119 cents
        self.assertEqual(calculate_commission(1250, 950), 119)
        # $1.00 (100 cents) at 500 bps (5.00%) = 5 cents
        self.assertEqual(calculate_commission(100, 500), 5)
        # Negative gross (refund reversal)
        self.assertEqual(calculate_commission(-1250, 950), -119)

    def test_electronics_rate_change_mid_year(self) -> None:
        """Verify rate change on 2026-07-01 for ELECTRONICS."""
        id_gen = IdGenerator()
        rules, rules_by_id = generate_commission_rules(id_gen)

        # Before rate change: 2026-06-30 should resolve to 800 bps (RULE-0001)
        rule_june = resolve_commission_rule(
            order_date=date(2026, 6, 30),
            category="ELECTRONICS",
            assigned_rule_ids=["RULE-0001", "RULE-0002"],
            all_rules_by_id=rules_by_id,
        )
        self.assertEqual(rule_june.rule_id, "RULE-0001")
        self.assertEqual(rule_june.rate_bps, 800)

        # On and after rate change: 2026-07-01 should resolve to 950 bps (RULE-0002)
        rule_july = resolve_commission_rule(
            order_date=date(2026, 7, 1),
            category="ELECTRONICS",
            assigned_rule_ids=["RULE-0001", "RULE-0002"],
            all_rules_by_id=rules_by_id,
        )
        self.assertEqual(rule_july.rule_id, "RULE-0002")
        self.assertEqual(rule_july.rate_bps, 950)

    def test_promo_rule_priority_over_standard(self) -> None:
        """Verify NEW_SELLER_PROMO (priority 50) wins over STANDARD (priority 10)."""
        id_gen = IdGenerator()
        rules, rules_by_id = generate_commission_rules(id_gen)

        # Assigned both promo and standard
        rule_resolved = resolve_commission_rule(
            order_date=date(2026, 3, 1),
            category="APPAREL",
            assigned_rule_ids=["RULE-0003", "RULE-0008"],  # APPAREL standard + PROMO
            all_rules_by_id=rules_by_id,
        )
        self.assertEqual(rule_resolved.rule_id, "RULE-0008")
        self.assertEqual(rule_resolved.rate_bps, 500)
        self.assertEqual(rule_resolved.priority, 50)

    def test_master_data_and_order_generation_determinism(self) -> None:
        """Verify fixed-seed reproducibility of master data and order skeleton."""
        config = GeneratorConfig(seed=20261022, scale=0.01)

        # Run 1
        rng1 = np.random.default_rng(20261022)
        id_gen1 = IdGenerator()
        md1 = generate_master_data(config, rng1, id_gen1)
        ord_bundle1 = generate_order_skeleton(config, md1, rng1, id_gen1)

        # Run 2
        rng2 = np.random.default_rng(20261022)
        id_gen2 = IdGenerator()
        md2 = generate_master_data(config, rng2, id_gen2)
        ord_bundle2 = generate_order_skeleton(config, md2, rng2, id_gen2)

        # Assert identical counts
        self.assertEqual(len(md1.sellers), len(md2.sellers))
        self.assertEqual(len(md1.listings), len(md2.listings))
        self.assertEqual(len(ord_bundle1.orders), len(ord_bundle2.orders))
        self.assertEqual(len(ord_bundle1.lines), len(ord_bundle2.lines))

        # Assert identical first and last order totals
        self.assertEqual(ord_bundle1.orders[0].order_id, ord_bundle2.orders[0].order_id)
        self.assertEqual(ord_bundle1.orders[0].total_gross_cents, ord_bundle2.orders[0].total_gross_cents)
        self.assertEqual(ord_bundle1.lines[0].commission_cents, ord_bundle2.lines[0].commission_cents)

        # Assert arithmetic identity: order total = sum of line totals
        for order in ord_bundle1.orders:
            calculated_sum = sum(line.total_gross_cents for line in order.lines)
            self.assertEqual(order.total_gross_cents, calculated_sum)


if __name__ == "__main__":
    unittest.main()

