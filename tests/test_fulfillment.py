"""
Unit tests for Fulfillment, Returns, Disputes, Reviews, and Event Tables.
"""

from datetime import date, datetime, timedelta
import unittest
import numpy as np

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.simulation.master_data import generate_master_data
from src.marketplace_gen.simulation.orders import generate_order_skeleton
from src.marketplace_gen.simulation.fulfillment import (
    simulate_fulfillments_and_disputes,
)


class TestFulfillmentSimulation(unittest.TestCase):
    """Test suite ensuring strict causal integrity and data consistency."""

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

    def test_fulfillment_cardinality_and_ids(self) -> None:
        """Every order line must have exactly one corresponding fulfillment record."""
        self.assertEqual(len(self.ful_bundle.fulfillments), len(self.order_bundle.lines))
        for line in self.order_bundle.lines:
            self.assertIn(line.order_line_id, self.ful_bundle.fulfillments_by_line_id)
            ful = self.ful_bundle.fulfillments_by_line_id[line.order_line_id]
            self.assertEqual(ful.fulfillment_id, f"FUL-{line.order_line_id}")

    def test_causal_temporal_ordering(self) -> None:
        """Verify placed_at <= shipped_at <= delivered_at <= (returned_at / review / dispute)."""
        lines_by_id = self.order_bundle.lines_by_id

        for ful in self.ful_bundle.fulfillments:
            line = lines_by_id[ful.order_line_id]
            placed_at = line.placed_at

            if ful.fulfillment_status == "CANCELLED":
                self.assertIsNone(ful.shipped_at)
                self.assertIsNone(ful.delivered_at)
                continue

            # Must have valid shipped_at
            self.assertIsNotNone(ful.shipped_at)
            self.assertGreaterEqual(ful.shipped_at, placed_at)

            # Check late shipment definition
            expected_late = ful.shipped_at.date() > (placed_at.date() + timedelta(days=3))
            self.assertEqual(ful.is_late_shipment, expected_late)

            if ful.fulfillment_status in ("DELIVERED", "RETURNED"):
                self.assertIsNotNone(ful.delivered_at)
                self.assertGreaterEqual(ful.delivered_at, ful.shipped_at)

            if ful.fulfillment_status == "RETURNED":
                self.assertIsNotNone(ful.returned_at)
                self.assertGreaterEqual(ful.returned_at, ful.delivered_at)

    def test_dispute_rules_and_amounts(self) -> None:
        """Dispute amounts must equal line gross cents; at most one dispute per line."""
        lines_by_id = self.order_bundle.lines_by_id
        seen_disputed_lines = set()

        for dsp in self.ful_bundle.disputes:
            self.assertNotIn(dsp.order_line_id, seen_disputed_lines)
            seen_disputed_lines.add(dsp.order_line_id)

            line = lines_by_id[dsp.order_line_id]
            ful = self.ful_bundle.fulfillments_by_line_id[dsp.order_line_id]

            self.assertEqual(dsp.amount_cents, line.total_gross_cents)
            # Dispute must be opened after placement
            self.assertGreaterEqual(dsp.opened_at, line.placed_at)

            if dsp.resolved_at is not None:
                self.assertGreaterEqual(dsp.resolved_at, dsp.opened_at)
                self.assertIn(dsp.dispute_status, ("RESOLVED_BUYER_WON", "RESOLVED_SELLER_WON"))
            else:
                self.assertEqual(dsp.dispute_status, "OPEN")

    def test_customer_reviews(self) -> None:
        """Reviews only on delivered lines, max 1 per line, ratings between 1 and 5."""
        seen_review_lines = set()
        for rev in self.ful_bundle.reviews:
            self.assertNotIn(rev.order_line_id, seen_review_lines)
            seen_review_lines.add(rev.order_line_id)

            ful = self.ful_bundle.fulfillments_by_line_id[rev.order_line_id]
            self.assertIn(ful.fulfillment_status, ("DELIVERED", "RETURNED"))
            self.assertGreaterEqual(rev.created_at, ful.delivered_at)
            self.assertGreaterEqual(rev.rating, 1)
            self.assertLessEqual(rev.rating, 5)

    def test_event_referential_integrity(self) -> None:
        """All fulfillment and dispute events link to existing entities."""
        valid_ful_ids = {f.fulfillment_id for f in self.ful_bundle.fulfillments}
        for ev in self.ful_bundle.fulfillment_events:
            self.assertIn(ev.fulfillment_id, valid_ful_ids)

        valid_dsp_ids = {d.dispute_id for d in self.ful_bundle.disputes}
        for ev in self.ful_bundle.dispute_events:
            self.assertIn(ev.dispute_id, valid_dsp_ids)


if __name__ == "__main__":
    unittest.main()

