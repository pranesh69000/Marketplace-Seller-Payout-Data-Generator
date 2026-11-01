"""
Deterministic, centralized ID Generator for all marketplace entities.

Enforces zero-padded monotonic counters, immutable ID structures,
and explicit parent-child binding according to docs/DESIGN.md.
"""

from __future__ import annotations

from typing import Dict


class IdGenerator:
    """Centralized monotonic ID generator ensuring zero-padding and deterministic sequencing."""

    def __init__(self, start_order_year: int = 2026) -> None:
        self.year: int = start_order_year
        self._counters: Dict[str, int] = {}
        self._seller_listing_counters: Dict[str, int] = {}

    def reset(self) -> None:
        """Reset all counters to zero for clean deterministic runs."""
        self._counters.clear()
        self._seller_listing_counters.clear()

    def _next_val(self, key: str) -> int:
        """Increment and return the next integer sequence for a given key."""
        current = self._counters.get(key, 0) + 1
        self._counters[key] = current
        return current

    # 1. Sellers: SELL-000001 (6 digits)
    def next_seller_id(self) -> str:
        seq = self._next_val("seller")
        return f"SELL-{seq:06d}"

    # 2. Product Listings: LIST-<seller-id>-000001 (per seller, 6 digits)
    def next_listing_id(self, seller_id: str) -> str:
        current = self._seller_listing_counters.get(seller_id, 0) + 1
        self._seller_listing_counters[seller_id] = current
        return f"LIST-{seller_id}-{current:06d}"

    # 3. Orders: ORD-2026-000001 (6 digits)
    def next_order_id(self) -> str:
        seq = self._next_val("order")
        return f"ORD-{self.year}-{seq:06d}"

    # 4. Order Lines: <order-id>-NN (2 digits, 1-indexed)
    @staticmethod
    def order_line_id(order_id: str, line_number: int) -> str:
        if line_number <= 0 or line_number > 99:
            raise ValueError(f"Line number must be between 1 and 99, got {line_number}")
        return f"{order_id}-{line_number:02d}"

    # 5. Fulfillment: FUL-<order-line-id> (1:1 with Order Line)
    @staticmethod
    def fulfillment_id(order_line_id: str) -> str:
        if not order_line_id:
            raise ValueError("order_line_id cannot be empty")
        return f"FUL-{order_line_id}"

    # 6. Customer Reviews: REV-2026-000001 (6 digits)
    def next_review_id(self) -> str:
        seq = self._next_val("review")
        return f"REV-{self.year}-{seq:06d}"

    # 7. Disputes: DSP-2026-000001 (6 digits)
    def next_dispute_id(self) -> str:
        seq = self._next_val("dispute")
        return f"DSP-{self.year}-{seq:06d}"

    # 8. Commission Rules: RULE-0001 (4 digits)
    def next_commission_rule_id(self) -> str:
        seq = self._next_val("rule")
        return f"RULE-{seq:04d}"

    # 9. Payouts: PAYOUT-2026-000001 (6 digits)
    def next_payout_id(self) -> str:
        seq = self._next_val("payout")
        return f"PAYOUT-{self.year}-{seq:06d}"

    # 10. Payout Lines: PLINE-2026-000001 (6 digits)
    def next_payout_line_id(self) -> str:
        seq = self._next_val("payout_line")
        return f"PLINE-{self.year}-{seq:06d}"

    # 11. Customers: CUST-000001 (attribute, 6 digits)
    def next_customer_id(self) -> str:
        seq = self._next_val("customer")
        return f"CUST-{seq:06d}"

    # 12. Commission Assignment Bridge: ASGN-000001 (6 digits)
    def next_assignment_id(self) -> str:
        seq = self._next_val("assignment")
        return f"ASGN-{seq:06d}"

    # 13. Audit / Event tables
    def next_status_event_id(self) -> str:
        seq = self._next_val("event_status")
        return f"EVT-STATUS-{seq:06d}"

    def next_fulfillment_event_id(self) -> str:
        seq = self._next_val("event_fulfillment")
        return f"EVT-FUL-{seq:06d}"

    def next_dispute_event_id(self) -> str:
        seq = self._next_val("event_dispute")
        return f"EVT-DSP-{seq:06d}"

    def next_payout_event_id(self) -> str:
        seq = self._next_val("event_payout")
        return f"EVT-PAY-{seq:06d}"

    # 14. Anomaly Ground Truth: GT-000001 (6 digits)
    def next_ground_truth_id(self) -> str:
        seq = self._next_val("ground_truth")
        return f"GT-{seq:06d}"

