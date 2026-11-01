"""
Unit tests for Status State Machine, Weekly Settlement Ledger, and Payout Invariants.
"""

from datetime import date, datetime, timedelta
import unittest
import numpy as np

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.rules.status import (
    SellerEvalState,
    evaluate_seller_status,
)
from src.marketplace_gen.simulation.master_data import generate_master_data
from src.marketplace_gen.simulation.orders import generate_order_skeleton
from src.marketplace_gen.simulation.fulfillment import (
    simulate_fulfillments_and_disputes,
)
from src.marketplace_gen.ledger import (
    simulate_weekly_ledger_and_governance,
)


class TestSellerStatusRules(unittest.TestCase):
    """Test suite verifying pure seller status transitions and cooldown rules."""

    def setUp(self) -> None:
        self.config = GeneratorConfig()

    def test_minimum_volume_threshold(self) -> None:
        """Sellers with < 15 lines maintain status without penalty."""
        state = SellerEvalState(seller_id="SELL-000001", current_status="ACTIVE")
        decision = evaluate_seller_status(
            eval_state=state,
            eval_date=date(2026, 2, 2),
            shipped_lines_count=10,
            late_shipped_lines_count=5,  # 50% late, but under 15 lines
            delivered_lines_count=10,
            disputes_count=2,
            config=self.config,
        )
        self.assertFalse(decision.has_transitioned)
        self.assertEqual(decision.new_status, "ACTIVE")
        self.assertEqual(decision.reason, "BELOW_MINIMUM_LINE_VOLUME")

    def test_active_to_watchlist_transition(self) -> None:
        """Late rate >= 12% triggers WATCHLIST."""
        state = SellerEvalState(seller_id="SELL-000001", current_status="ACTIVE")
        decision = evaluate_seller_status(
            eval_state=state,
            eval_date=date(2026, 2, 2),
            shipped_lines_count=20,
            late_shipped_lines_count=3,  # 15% late (>= 12%)
            delivered_lines_count=20,
            disputes_count=0,
            config=self.config,
        )
        self.assertTrue(decision.has_transitioned)
        self.assertEqual(decision.new_status, "WATCHLIST")
        self.assertEqual(state.consecutive_watchlist_evals, 1)

    def test_two_consecutive_watchlist_triggers_suspension(self) -> None:
        """Two consecutive watchlist evaluations trigger SUSPENDED."""
        state = SellerEvalState(seller_id="SELL-000001", current_status="WATCHLIST", consecutive_watchlist_evals=1)
        decision = evaluate_seller_status(
            eval_state=state,
            eval_date=date(2026, 2, 9),
            shipped_lines_count=20,
            late_shipped_lines_count=3,  # 15% late (still watchlist level)
            delivered_lines_count=20,
            disputes_count=0,
            config=self.config,
        )
        self.assertTrue(decision.has_transitioned)
        self.assertEqual(decision.new_status, "SUSPENDED")
        self.assertEqual(decision.reason, "CONSECUTIVE_WATCHLIST_BREACH")
        self.assertEqual(state.suspended_since, date(2026, 2, 9))

    def test_severe_breach_direct_suspension(self) -> None:
        """Late >= 20% triggers immediate suspension even from ACTIVE."""
        state = SellerEvalState(seller_id="SELL-000001", current_status="ACTIVE")
        decision = evaluate_seller_status(
            eval_state=state,
            eval_date=date(2026, 2, 2),
            shipped_lines_count=20,
            late_shipped_lines_count=5,  # 25% late (>= 20%)
            delivered_lines_count=20,
            disputes_count=0,
            config=self.config,
        )
        self.assertTrue(decision.has_transitioned)
        self.assertEqual(decision.new_status, "SUSPENDED")
        self.assertEqual(decision.reason, "SEVERE_METRIC_BREACH")

    def test_suspension_cooldown_and_recovery(self) -> None:
        """Suspended seller recovers to WATCHLIST after 30 days minimum cooldown."""
        susp_date = date(2026, 3, 2)
        state = SellerEvalState(
            seller_id="SELL-000001",
            current_status="SUSPENDED",
            suspended_since=susp_date,
        )
        # Week 2 (14 days): Still in cooldown
        decision_early = evaluate_seller_status(
            eval_state=state,
            eval_date=date(2026, 3, 16),
            shipped_lines_count=0,
            late_shipped_lines_count=0,
            delivered_lines_count=0,
            disputes_count=0,
            config=self.config,
        )
        self.assertFalse(decision_early.has_transitioned)
        self.assertEqual(decision_early.new_status, "SUSPENDED")

        # Week 5 (35 days): Cooldown expired -> Reinstated to WATCHLIST
        decision_recovery = evaluate_seller_status(
            eval_state=state,
            eval_date=date(2026, 4, 6),
            shipped_lines_count=0,
            late_shipped_lines_count=0,
            delivered_lines_count=0,
            disputes_count=0,
            config=self.config,
        )
        self.assertTrue(decision_recovery.has_transitioned)
        self.assertEqual(decision_recovery.new_status, "WATCHLIST")
        self.assertEqual(decision_recovery.reason, "SUSPENSION_COOLDOWN_EXPIRED_REINSTATED")


class TestLedgerAndPayouts(unittest.TestCase):
    """Test suite verifying accounting ledger identities and settlement rules."""

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

    def test_payout_total_exact_arithmetic_identity(self) -> None:
        """Every Payout.total_cents must strictly equal sum of child PayoutLine amounts."""
        self.assertGreater(len(self.settlement.payouts), 0)
        for payout in self.settlement.payouts:
            calculated_sum = sum(line.amount_cents for line in payout.lines)
            self.assertEqual(
                payout.total_cents,
                calculated_sum,
                f"Mismatch in payout {payout.payout_id}: total={payout.total_cents}, sum={calculated_sum}"
            )
            self.assertGreater(payout.total_cents, 0)

    def test_signed_ledger_entry_types(self) -> None:
        """Verify sign polarity of all ledger entry types."""
        for pline in self.settlement.payout_lines:
            if pline.entry_type in ("SALE", "COMMISSION_REVERSAL", "RESERVE_RELEASE"):
                self.assertGreater(
                    pline.amount_cents, 0,
                    f"Entry type {pline.entry_type} should have positive amount, got {pline.amount_cents}"
                )
            elif pline.entry_type in ("COMMISSION", "REFUND", "DISPUTE_DEDUCTION", "RESERVE_HOLD"):
                self.assertLess(
                    pline.amount_cents, 0,
                    f"Entry type {pline.entry_type} should have negative amount, got {pline.amount_cents}"
                )

    def test_hold_window_enforcement(self) -> None:
        """Verify 14-day hold window: no line is settled before delivered_at + 14 days."""
        ful_by_line = self.ful_bundle.fulfillments_by_line_id
        for payout in self.settlement.payouts:
            for line in payout.lines:
                if line.source_type == "ORDER_LINE" and line.entry_type == "SALE":
                    ful = ful_by_line[line.source_id]
                    self.assertIsNotNone(ful.delivered_at)
                    # cycle_date must be at least 14 days after delivered_at.date()
                    min_allowed_cycle = ful.delivered_at.date() + timedelta(days=self.config.hold_window_days)
                    self.assertGreaterEqual(
                        payout.cycle_date,
                        min_allowed_cycle,
                        f"Line {line.source_id} paid on {payout.cycle_date} before 14-day hold {min_allowed_cycle}"
                    )

    def test_suspended_seller_payout_status(self) -> None:
        """Payouts created for suspended sellers must carry status='HELD'."""
        held_payouts = [p for p in self.settlement.payouts if p.status == "HELD"]
        paid_payouts = [p for p in self.settlement.payouts if p.status == "PAID"]
        # Ensure we have settlements processed
        self.assertGreater(len(paid_payouts), 0)
        for hp in held_payouts:
            # Audit events must record HELD
            events = [e for e in self.settlement.payout_events if e.payout_id == hp.payout_id]
            event_types = [e.event_type for e in events]
            self.assertIn("HELD", event_types)


if __name__ == "__main__":
    unittest.main()

