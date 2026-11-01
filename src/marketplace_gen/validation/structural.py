"""
Pure structural and referential integrity validator.

Enforces:
- PK Uniqueness across all 15 tables
- Foreign Key Referential Integrity
- Allowed Enum Values
- Chronological Invariants (placed <= shipped <= delivered <= returned)
- Arithmetic Identities (order totals, line totals, payout totals)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Optional, Set

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ledger import SettlementSimulationBundle
from src.marketplace_gen.rules.commission import calculate_commission
from src.marketplace_gen.simulation.fulfillment import FulfillmentSimulationBundle
from src.marketplace_gen.simulation.master_data import MasterDataBundle
from src.marketplace_gen.simulation.orders import OrderSkeletonBundle


@dataclass(frozen=True)
class ValidationError:
    """Record of a single structural or integrity validation failure."""
    check_name: str
    entity_type: str
    entity_id: str
    message: str


@dataclass
class ValidationReport:
    """Consolidated results of all validation checks."""
    total_checks_run: int
    errors: List[ValidationError]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0


def validate_structural_integrity(
    config: GeneratorConfig,
    master_data: MasterDataBundle,
    order_bundle: OrderSkeletonBundle,
    ful_bundle: FulfillmentSimulationBundle,
    settlement: SettlementSimulationBundle,
) -> ValidationReport:
    """
    Performs exhaustive pure structural checks across all in-memory entities.
    Returns a ValidationReport containing any flagged violations.
    """
    errors: List[ValidationError] = []
    checks_count = 0

    # -------------------------------------------------------------
    # 1. Primary Key Uniqueness & ID Formats
    # -------------------------------------------------------------
    def check_pks(items: list, id_attr: str, entity_name: str) -> Set[str]:
        nonlocal checks_count
        checks_count += 1
        seen: Set[str] = set()
        for item in items:
            val = getattr(item, id_attr)
            if val in seen:
                errors.append(
                    ValidationError(
                        check_name="PK_UNIQUENESS",
                        entity_type=entity_name,
                        entity_id=str(val),
                        message=f"Duplicate primary key detected: {val}",
                    )
                )
            seen.add(val)
        return seen

    seller_ids = check_pks(master_data.sellers, "seller_id", "Seller")
    listing_ids = check_pks(master_data.listings, "listing_id", "ProductListing")
    rule_ids = check_pks(master_data.commission_rules, "rule_id", "CommissionRule")
    order_ids = check_pks(order_bundle.orders, "order_id", "Order")
    line_ids = check_pks(order_bundle.lines, "order_line_id", "OrderLine")
    ful_ids = check_pks(ful_bundle.fulfillments, "fulfillment_id", "Fulfillment")
    rev_ids = check_pks(ful_bundle.reviews, "review_id", "CustomerReview")
    dsp_ids = check_pks(ful_bundle.disputes, "dispute_id", "Dispute")
    asgn_ids = check_pks(master_data.assignments, "assignment_id", "SellerCommissionAssignment")
    payout_ids = check_pks(settlement.payouts, "payout_id", "Payout")
    pline_ids = check_pks(settlement.payout_lines, "payout_line_id", "PayoutLine")
    evt_status_ids = check_pks(settlement.seller_status_events, "event_id", "SellerStatusEvent")
    evt_ful_ids = check_pks(ful_bundle.fulfillment_events, "event_id", "FulfillmentEvent")
    evt_dsp_ids = check_pks(ful_bundle.dispute_events, "event_id", "DisputeEvent")
    evt_pay_ids = check_pks(settlement.payout_events, "event_id", "PayoutEvent")

    # -------------------------------------------------------------
    # 2. Foreign Key Integrity
    # -------------------------------------------------------------
    checks_count += 1
    for lst in master_data.listings:
        if lst.seller_id not in seller_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "ProductListing", lst.listing_id, f"Invalid seller_id {lst.seller_id}")
            )

    for line in order_bundle.lines:
        if line.order_id not in order_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "OrderLine", line.order_line_id, f"Invalid order_id {line.order_id}")
            )
        if line.seller_id not in seller_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "OrderLine", line.order_line_id, f"Invalid seller_id {line.seller_id}")
            )
        if line.listing_id not in listing_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "OrderLine", line.order_line_id, f"Invalid listing_id {line.listing_id}")
            )
        if line.applied_rule_id not in rule_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "OrderLine", line.order_line_id, f"Invalid rule_id {line.applied_rule_id}")
            )

    for ful in ful_bundle.fulfillments:
        if ful.order_line_id not in line_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "Fulfillment", ful.fulfillment_id, f"Invalid order_line_id {ful.order_line_id}")
            )

    for rev in ful_bundle.reviews:
        if rev.order_line_id not in line_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "CustomerReview", rev.review_id, f"Invalid order_line_id {rev.order_line_id}")
            )

    for dsp in ful_bundle.disputes:
        if dsp.order_line_id not in line_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "Dispute", dsp.dispute_id, f"Invalid order_line_id {dsp.order_line_id}")
            )

    for asgn in master_data.assignments:
        if asgn.seller_id not in seller_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "SellerCommissionAssignment", asgn.assignment_id, f"Invalid seller_id {asgn.seller_id}")
            )
        if asgn.rule_id not in rule_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "SellerCommissionAssignment", asgn.assignment_id, f"Invalid rule_id {asgn.rule_id}")
            )

    for po in settlement.payouts:
        if po.seller_id not in seller_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "Payout", po.payout_id, f"Invalid seller_id {po.seller_id}")
            )

    for pl in settlement.payout_lines:
        if pl.payout_id and pl.payout_id not in payout_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "PayoutLine", pl.payout_line_id, f"Invalid payout_id {pl.payout_id}")
            )
        if pl.seller_id not in seller_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "PayoutLine", pl.payout_line_id, f"Invalid seller_id {pl.seller_id}")
            )
        if pl.rule_id and pl.rule_id not in rule_ids:
            errors.append(
                ValidationError("FK_INTEGRITY", "PayoutLine", pl.payout_line_id, f"Invalid rule_id {pl.rule_id}")
            )

    # -------------------------------------------------------------
    # 3. Enum & Value Constraints
    # -------------------------------------------------------------
    checks_count += 1
    allowed_categories = set(config.categories)
    allowed_seller_statuses = {"ACTIVE", "WATCHLIST", "SUSPENDED"}
    allowed_ful_statuses = {"PENDING", "SHIPPED", "DELIVERED", "CANCELLED", "FAILED_DELIVERY", "RETURNED"}
    allowed_dsp_types = {"NOT_RECEIVED", "NOT_AS_DESCRIBED", "RETURN_DISPUTE", "CHARGEBACK"}
    allowed_dsp_statuses = {"OPEN", "RESOLVED_SELLER_WON", "RESOLVED_BUYER_WON"}
    allowed_entry_types = {"SALE", "COMMISSION", "REFUND", "COMMISSION_REVERSAL", "DISPUTE_DEDUCTION", "RESERVE_HOLD", "RESERVE_RELEASE"}

    for s in master_data.sellers:
        if s.status not in allowed_seller_statuses:
            errors.append(ValidationError("ENUM_VALIDITY", "Seller", s.seller_id, f"Invalid status {s.status}"))

    for lst in master_data.listings:
        if lst.category not in allowed_categories:
            errors.append(ValidationError("ENUM_VALIDITY", "ProductListing", lst.listing_id, f"Invalid category {lst.category}"))
        if lst.base_price_cents <= 0:
            errors.append(ValidationError("VALUE_RANGE", "ProductListing", lst.listing_id, "base_price_cents must be > 0"))

    for ful in ful_bundle.fulfillments:
        if ful.fulfillment_status not in allowed_ful_statuses:
            errors.append(ValidationError("ENUM_VALIDITY", "Fulfillment", ful.fulfillment_id, f"Invalid status {ful.fulfillment_status}"))

    for dsp in ful_bundle.disputes:
        if dsp.dispute_type not in allowed_dsp_types:
            errors.append(ValidationError("ENUM_VALIDITY", "Dispute", dsp.dispute_id, f"Invalid dispute_type {dsp.dispute_type}"))
        if dsp.dispute_status not in allowed_dsp_statuses:
            errors.append(ValidationError("ENUM_VALIDITY", "Dispute", dsp.dispute_id, f"Invalid dispute_status {dsp.dispute_status}"))

    for pl in settlement.payout_lines:
        if pl.entry_type not in allowed_entry_types:
            errors.append(ValidationError("ENUM_VALIDITY", "PayoutLine", pl.payout_line_id, f"Invalid entry_type {pl.entry_type}"))

    # -------------------------------------------------------------
    # 4. Chronological Invariants
    # -------------------------------------------------------------
    checks_count += 1
    lines_by_id = order_bundle.lines_by_id

    for lst in master_data.listings:
        seller = master_data.sellers_by_id[lst.seller_id]
        if lst.created_at < seller.onboarded_at:
            errors.append(
                ValidationError("DATE_ORDER", "ProductListing", lst.listing_id, f"Listing created {lst.created_at} before seller onboarded {seller.onboarded_at}")
            )

    for ful in ful_bundle.fulfillments:
        line = lines_by_id[ful.order_line_id]
        if ful.shipped_at and ful.shipped_at < line.placed_at:
            errors.append(
                ValidationError("DATE_ORDER", "Fulfillment", ful.fulfillment_id, "shipped_at cannot be before line placed_at")
            )
        if ful.delivered_at and ful.shipped_at and ful.delivered_at < ful.shipped_at:
            errors.append(
                ValidationError("DATE_ORDER", "Fulfillment", ful.fulfillment_id, "delivered_at cannot be before shipped_at")
            )
        if ful.returned_at and ful.delivered_at and ful.returned_at < ful.delivered_at:
            errors.append(
                ValidationError("DATE_ORDER", "Fulfillment", ful.fulfillment_id, "returned_at cannot be before delivered_at")
            )

    for rev in ful_bundle.reviews:
        ful = ful_bundle.fulfillments_by_line_id[rev.order_line_id]
        if ful.delivered_at and rev.created_at < ful.delivered_at:
            errors.append(
                ValidationError("DATE_ORDER", "CustomerReview", rev.review_id, "review created_at cannot be before delivered_at")
            )

    # -------------------------------------------------------------
    # 5. Arithmetic Identities
    # -------------------------------------------------------------
    checks_count += 1
    for order in order_bundle.orders:
        sum_gross = sum(l.total_gross_cents for l in order.lines)
        if order.total_gross_cents != sum_gross:
            errors.append(
                ValidationError("ARITHMETIC_IDENTITY", "Order", order.order_id, f"Order gross mismatch: {order.total_gross_cents} != sum {sum_gross}")
            )

    for line in order_bundle.lines:
        expected_gross = line.quantity * line.unit_price_cents
        if line.total_gross_cents != expected_gross:
            errors.append(
                ValidationError("ARITHMETIC_IDENTITY", "OrderLine", line.order_line_id, f"Line gross mismatch: {line.total_gross_cents} != {expected_gross}")
            )
        expected_comm = calculate_commission(line.total_gross_cents, line.commission_rate_bps)
        if line.commission_cents != expected_comm:
            errors.append(
                ValidationError("ARITHMETIC_IDENTITY", "OrderLine", line.order_line_id, f"Commission mismatch: {line.commission_cents} != {expected_comm}")
            )

    for payout in settlement.payouts:
        sum_pline = sum(l.amount_cents for l in payout.lines)
        if payout.total_cents != sum_pline:
            errors.append(
                ValidationError("ARITHMETIC_IDENTITY", "Payout", payout.payout_id, f"Payout total mismatch: {payout.total_cents} != sum {sum_pline}")
            )

    return ValidationReport(total_checks_run=checks_count, errors=errors)

