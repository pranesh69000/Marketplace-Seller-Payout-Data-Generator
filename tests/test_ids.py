"""Unit tests for deterministic IdGenerator."""

import unittest
from src.marketplace_gen.ids import IdGenerator


class TestIdGenerator(unittest.TestCase):
    """Test suite ensuring strict adherence to locked ID formats and deterministic behavior."""

    def setUp(self) -> None:
        self.id_gen = IdGenerator(start_order_year=2026)

    def test_seller_id_formatting(self) -> None:
        self.assertEqual(self.id_gen.next_seller_id(), "SELL-000001")
        self.assertEqual(self.id_gen.next_seller_id(), "SELL-000002")

    def test_listing_id_per_seller_monotonicity(self) -> None:
        s1 = "SELL-000042"
        s2 = "SELL-000099"
        self.assertEqual(self.id_gen.next_listing_id(s1), "LIST-SELL-000042-000001")
        self.assertEqual(self.id_gen.next_listing_id(s1), "LIST-SELL-000042-000002")
        self.assertEqual(self.id_gen.next_listing_id(s2), "LIST-SELL-000099-000001")

    def test_order_and_line_hierarchy(self) -> None:
        order_id = self.id_gen.next_order_id()
        self.assertEqual(order_id, "ORD-2026-000001")

        line_1 = self.id_gen.order_line_id(order_id, 1)
        line_2 = self.id_gen.order_line_id(order_id, 2)
        self.assertEqual(line_1, "ORD-2026-000001-01")
        self.assertEqual(line_2, "ORD-2026-000001-02")

        # Fulfillment 1:1 binding
        ful_1 = self.id_gen.fulfillment_id(line_1)
        self.assertEqual(ful_1, "FUL-ORD-2026-000001-01")

    def test_line_number_validation(self) -> None:
        with self.assertRaises(ValueError):
            self.id_gen.order_line_id("ORD-2026-000001", 0)
        with self.assertRaises(ValueError):
            self.id_gen.order_line_id("ORD-2026-000001", 100)

    def test_rule_and_financial_ids(self) -> None:
        self.assertEqual(self.id_gen.next_commission_rule_id(), "RULE-0001")
        self.assertEqual(self.id_gen.next_payout_id(), "PAYOUT-2026-000001")
        self.assertEqual(self.id_gen.next_payout_line_id(), "PLINE-2026-000001")

    def test_disputes_reviews_customers(self) -> None:
        self.assertEqual(self.id_gen.next_customer_id(), "CUST-000001")
        self.assertEqual(self.id_gen.next_review_id(), "REV-2026-000001")
        self.assertEqual(self.id_gen.next_dispute_id(), "DSP-2026-000001")
        self.assertEqual(self.id_gen.next_assignment_id(), "ASGN-000001")

    def test_audit_event_and_ground_truth_ids(self) -> None:
        self.assertEqual(self.id_gen.next_status_event_id(), "EVT-STATUS-000001")
        self.assertEqual(self.id_gen.next_fulfillment_event_id(), "EVT-FUL-000001")
        self.assertEqual(self.id_gen.next_dispute_event_id(), "EVT-DSP-000001")
        self.assertEqual(self.id_gen.next_payout_event_id(), "EVT-PAY-000001")
        self.assertEqual(self.id_gen.next_ground_truth_id(), "GT-000001")

    def test_reset_behavior(self) -> None:
        self.id_gen.next_seller_id()
        self.id_gen.next_order_id()
        self.id_gen.reset()
        self.assertEqual(self.id_gen.next_seller_id(), "SELL-000001")
        self.assertEqual(self.id_gen.next_order_id(), "ORD-2026-000001")


if __name__ == "__main__":
    unittest.main()

