"""
Pure business rules for commission calculation and rule resolution.

Locked requirement:
- Commission is calculated in ONE function: round_half_up(line_gross * rate_bps / 10000)
- Highest priority rule wins.
- Locked at order placement time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Sequence


@dataclass(frozen=True)
class CommissionRuleRecord:
    """Immutable representation of a commission rule."""
    rule_id: str
    rule_type: str         # 'STANDARD' or 'NEW_SELLER_PROMO'
    category: str          # e.g. 'ELECTRONICS' or 'ALL'
    rate_bps: int          # e.g. 800 for 8.00%
    priority: int          # higher number takes precedence
    effective_from: date
    effective_to: Optional[date] = None

    def is_active_on(self, target_date: date) -> bool:
        """Check if this rule is within its validity interval on target_date."""
        if target_date < self.effective_from:
            return False
        if self.effective_to is not None and target_date > self.effective_to:
            return False
        return True

    def matches_category(self, category: str) -> bool:
        """Check if this rule applies to the specified merchandise category."""
        return self.category == "ALL" or self.category == category


@dataclass(frozen=True)
class SellerCommissionAssignmentRecord:
    """Immutable bridge record assigning a rule to a seller over time."""
    assignment_id: str
    seller_id: str
    rule_id: str
    effective_from: date
    effective_to: Optional[date] = None

    def is_active_on(self, target_date: date) -> bool:
        if target_date < self.effective_from:
            return False
        if self.effective_to is not None and target_date > self.effective_to:
            return False
        return True


def round_half_up(value_scaled_by_10000: int) -> int:
    """
    Rounds an integer numerator scaled by 10,000 using standard half-up arithmetic.
    
    Formula: floor((numerator + 5000) / 10000) for non-negative values.
    For negative values (e.g. refunds): -floor((abs(numerator) + 5000) / 10000).
    """
    if value_scaled_by_10000 >= 0:
        return (value_scaled_by_10000 + 5000) // 10000
    return -((abs(value_scaled_by_10000) + 5000) // 10000)


def calculate_commission(gross_cents: int, rate_bps: int) -> int:
    """
    Pure function: calculates marketplace commission in integer cents.
    
    All inputs and outputs are strict integers.
    gross_cents: Line gross (quantity * unit_price_cents).
    rate_bps: Basis points (1% = 100 bps).
    """
    if rate_bps < 0:
        raise ValueError(f"rate_bps must be non-negative, got {rate_bps}")
    numerator = gross_cents * rate_bps
    return round_half_up(numerator)


def resolve_commission_rule(
    order_date: date,
    category: str,
    assigned_rule_ids: Sequence[str],
    all_rules_by_id: Dict[str, CommissionRuleRecord],
) -> CommissionRuleRecord:
    """
    Pure function resolving the single winning commission rule for an order line.
    
    Precedence:
    1. Highest priority wins.
    2. In case of identical priority, specific category wins over 'ALL'.
    3. In case of tie, higher rate_bps wins.
    4. Deterministic tie-breaker: rule_id ASC.
    """
    candidates: List[CommissionRuleRecord] = []
    for r_id in assigned_rule_ids:
        rule = all_rules_by_id.get(r_id)
        if rule and rule.is_active_on(order_date) and rule.matches_category(category):
            candidates.append(rule)

    if not candidates:
        raise ValueError(
            f"No active commission rule found for category='{category}' "
            f"on date={order_date} among assigned rules={assigned_rule_ids}"
        )

    # Sort candidates by:
    # 1. priority DESC
    # 2. specific category (category != 'ALL') DESC
    # 3. rate_bps DESC
    # 4. rule_id ASC
    candidates.sort(
        key=lambda r: (
            -r.priority,
            -(1 if r.category != "ALL" else 0),
            -r.rate_bps,
            r.rule_id,
        )
    )
    return candidates[0]

