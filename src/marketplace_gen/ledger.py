"""
Weekly Accounting Ledger, Payouts Settlement, and Seller Governance engine.

Implements:
- 14-day delivery hold window.
- 60-day reserve hold (10% of gross - commission) for WATCHLIST sellers.
- Negative net roll-forward (no Payout record when cycle net <= 0).
- Suspended seller payouts held in HELD state.
- Append-only signed ledger lines (SALE, COMMISSION, REFUND, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.rules.status import (
    SellerEvalState,
    evaluate_seller_status,
)
from src.marketplace_gen.simulation.fulfillment import (
    DisputeRecord,
    FulfillmentRecord,
    FulfillmentSimulationBundle,
)
from src.marketplace_gen.simulation.master_data import MasterDataBundle
from src.marketplace_gen.simulation.orders import OrderLineRecord, OrderSkeletonBundle


@dataclass
class PayoutLineRecord:
    """Individual signed transaction entry backing a payout."""
    payout_line_id: str
    payout_id: Optional[str]
    seller_id: str
    source_type: str  # 'ORDER_LINE', 'DISPUTE', 'RESERVE'
    source_id: str
    entry_type: str   # 'SALE', 'COMMISSION', 'REFUND', 'COMMISSION_REVERSAL', 'DISPUTE_DEDUCTION', 'RESERVE_HOLD', 'RESERVE_RELEASE'
    amount_cents: int
    rule_id: Optional[str]
    created_at: datetime


@dataclass
class PayoutRecord:
    """Disbursement summary for a seller on a weekly Monday cycle."""
    payout_id: str
    seller_id: str
    cycle_date: date
    total_cents: int
    status: str  # 'PAID', 'HELD'
    generated_at: datetime
    lines: List[PayoutLineRecord]


@dataclass
class PayoutEventRecord:
    """Audit milestone event for a payout."""
    event_id: str
    payout_id: str
    event_type: str  # 'GENERATED', 'HELD', 'PAID'
    event_at: datetime


@dataclass
class SellerStatusEventRecord:
    """Audit event for seller state changes."""
    event_id: str
    seller_id: str
    previous_status: str
    new_status: str
    reason: str
    snapshot_late_rate_bps: int
    snapshot_dispute_rate_bps: int
    evaluated_lines_count: int
    event_at: datetime


@dataclass
class ReserveHoldTracker:
    """Tracks withheld reserves awaiting release."""
    reserve_id: str
    seller_id: str
    hold_amount_cents: int
    held_at_date: date
    release_due_date: date
    is_released: bool = False


@dataclass
class SettlementSimulationBundle:
    """Encapsulates all financial payouts, ledger lines, status events, and payout events."""
    payouts: List[PayoutRecord]
    payouts_by_id: Dict[str, PayoutRecord]
    payout_lines: List[PayoutLineRecord]
    payout_lines_by_payout_id: Dict[str, List[PayoutLineRecord]]
    payout_events: List[PayoutEventRecord]
    seller_status_events: List[SellerStatusEventRecord]
    seller_final_statuses: Dict[str, str]
    unallocated_lines: List[PayoutLineRecord] = field(default_factory=list)


def simulate_weekly_ledger_and_governance(
    config: GeneratorConfig,
    master_data: MasterDataBundle,
    order_bundle: OrderSkeletonBundle,
    ful_bundle: FulfillmentSimulationBundle,
    id_gen: IdGenerator,
) -> SettlementSimulationBundle:
    """
    Simulates Monday-by-Monday settlement and seller status governance.
    
    Timeline: Every Monday between start_date and as_of_date.
    """
    # Build lookup indexes for simulation speed
    ful_by_line: Dict[str, FulfillmentRecord] = ful_bundle.fulfillments_by_line_id
    dsp_by_line: Dict[str, DisputeRecord] = ful_bundle.disputes_by_line_id
    lines_by_seller: Dict[str, List[OrderLineRecord]] = order_bundle.lines_by_seller

    # Seller state tracking
    seller_eval_states: Dict[str, SellerEvalState] = {
        s.seller_id: SellerEvalState(seller_id=s.seller_id, current_status="ACTIVE")
        for s in master_data.sellers
    }

    # Tracking sets
    paid_order_lines: Set[str] = set()
    refunded_order_lines: Set[str] = set()
    deducted_disputes: Set[str] = set()
    pending_reserve_holds: List[ReserveHoldTracker] = []

    # Rolled-forward unallocated lines per seller
    unallocated_lines_by_seller: Dict[str, List[PayoutLineRecord]] = {
        s.seller_id: [] for s in master_data.sellers
    }

    payouts: List[PayoutRecord] = []
    payouts_by_id: Dict[str, PayoutRecord] = {}
    payout_lines: List[PayoutLineRecord] = []
    payout_lines_by_payout_id: Dict[str, List[PayoutLineRecord]] = {}
    payout_events: List[PayoutEventRecord] = []
    seller_status_events: List[SellerStatusEventRecord] = []

    # Determine all Monday cycle dates
    first_date = config.start_date
    # Find first Monday on or after start_date
    days_to_monday = (7 - first_date.weekday()) % 7
    first_monday = first_date + timedelta(days=days_to_monday)
    
    current_monday = first_monday
    cycle_mondays: List[date] = []
    while current_monday <= config.as_of_date:
        cycle_mondays.append(current_monday)
        current_monday += timedelta(days=7)

    # Weekly simulation loop
    for cycle_date in cycle_mondays:
        cycle_dt = datetime.combine(cycle_date, datetime.min.time()) + timedelta(hours=6)
        eval_window_start = cycle_date - timedelta(days=config.eval_window_days)

        # -------------------------------------------------------------
        # 1. Weekly Seller Status & Performance Evaluation
        # -------------------------------------------------------------
        for seller in master_data.sellers:
            s_id = seller.seller_id
            eval_state = seller_eval_states[s_id]

            # Aggregate trailing 60-day performance
            shipped_count = 0
            late_shipped_count = 0
            delivered_count = 0
            disputes_count = 0

            seller_lines = lines_by_seller.get(s_id, [])
            for line in seller_lines:
                ful = ful_by_line.get(line.order_line_id)
                if not ful:
                    continue

                # Trailing evaluation window filter
                if ful.shipped_at and eval_window_start <= ful.shipped_at.date() <= cycle_date:
                    shipped_count += 1
                    if ful.is_late_shipment:
                        late_shipped_count += 1

                if ful.delivered_at and eval_window_start <= ful.delivered_at.date() <= cycle_date:
                    delivered_count += 1

                dsp = dsp_by_line.get(line.order_line_id)
                if dsp and eval_window_start <= dsp.opened_at.date() <= cycle_date:
                    disputes_count += 1

            decision = evaluate_seller_status(
                eval_state=eval_state,
                eval_date=cycle_date,
                shipped_lines_count=shipped_count,
                late_shipped_lines_count=late_shipped_count,
                delivered_lines_count=delivered_count,
                disputes_count=disputes_count,
                config=config,
            )

            if decision.has_transitioned:
                # Record status change event
                status_evt = SellerStatusEventRecord(
                    event_id=id_gen.next_status_event_id(),
                    seller_id=s_id,
                    previous_status=decision.previous_status,
                    new_status=decision.new_status,
                    reason=decision.reason,
                    snapshot_late_rate_bps=decision.late_rate_bps,
                    snapshot_dispute_rate_bps=decision.dispute_rate_bps,
                    evaluated_lines_count=decision.evaluated_lines_count,
                    event_at=cycle_dt,
                )
                seller_status_events.append(status_evt)

                # Deactivate listings if seller suspended
                if decision.new_status == "SUSPENDED":
                    for lst in master_data.listings_by_seller.get(s_id, []):
                        if lst.deactivated_at is None:
                            lst.deactivated_at = cycle_dt

        # -------------------------------------------------------------
        # 2. Financial Ledger & Settlement for this Cycle
        # -------------------------------------------------------------
        for seller in master_data.sellers:
            s_id = seller.seller_id
            eval_state = seller_eval_states[s_id]
            seller_lines = lines_by_seller.get(s_id, [])
            current_cycle_lines: List[PayoutLineRecord] = []

            # 2A. Eligible Sales & Commissions (14-day hold window)
            for line in seller_lines:
                if line.order_line_id in paid_order_lines:
                    continue

                ful = ful_by_line.get(line.order_line_id)
                if not ful or not ful.delivered_at:
                    continue

                # Eligibility check: delivered_at + 14 days <= cycle_date
                eligibility_cutoff = ful.delivered_at.date() + timedelta(days=config.hold_window_days)
                if eligibility_cutoff > cycle_date:
                    continue

                # No active dispute open on or before this cycle
                dsp = dsp_by_line.get(line.order_line_id)
                if dsp and dsp.opened_at.date() <= cycle_date:
                    # Dispute open or pending; withhold payout line
                    continue

                # Not returned prior to eligibility cutoff
                if ful.returned_at and ful.returned_at.date() <= cycle_date:
                    continue

                # Eligible! Generate SALE and COMMISSION entries
                paid_order_lines.add(line.order_line_id)

                sale_line = PayoutLineRecord(
                    payout_line_id=id_gen.next_payout_line_id(),
                    payout_id=None,
                    seller_id=s_id,
                    source_type="ORDER_LINE",
                    source_id=line.order_line_id,
                    entry_type="SALE",
                    amount_cents=line.total_gross_cents,
                    rule_id=None,
                    created_at=cycle_dt,
                )
                comm_line = PayoutLineRecord(
                    payout_line_id=id_gen.next_payout_line_id(),
                    payout_id=None,
                    seller_id=s_id,
                    source_type="ORDER_LINE",
                    source_id=line.order_line_id,
                    entry_type="COMMISSION",
                    amount_cents=-line.commission_cents,
                    rule_id=line.applied_rule_id,
                    created_at=cycle_dt,
                )
                current_cycle_lines.extend([sale_line, comm_line])

                # Reserve Hold: If seller is on WATCHLIST at cycle_date, hold 10% of (gross - commission)
                if eval_state.current_status == "WATCHLIST":
                    net_proceeds = line.total_gross_cents - line.commission_cents
                    hold_amount = (net_proceeds * config.reserve_rate_bps + 5000) // 10000
                    if hold_amount > 0:
                        reserve_tracker_id = f"RES-{line.order_line_id}"
                        reserve_line = PayoutLineRecord(
                            payout_line_id=id_gen.next_payout_line_id(),
                            payout_id=None,
                            seller_id=s_id,
                            source_type="RESERVE",
                            source_id=reserve_tracker_id,
                            entry_type="RESERVE_HOLD",
                            amount_cents=-hold_amount,
                            rule_id=None,
                            created_at=cycle_dt,
                        )
                        current_cycle_lines.append(reserve_line)
                        pending_reserve_holds.append(
                            ReserveHoldTracker(
                                reserve_id=reserve_tracker_id,
                                seller_id=s_id,
                                hold_amount_cents=hold_amount,
                                held_at_date=cycle_date,
                                release_due_date=cycle_date + timedelta(days=config.reserve_hold_window_days),
                            )
                        )

            # 2B. Reserve Releases (60 days post-hold if NOT SUSPENDED)
            for res in pending_reserve_holds:
                if res.seller_id == s_id and not res.is_released:
                    if res.release_due_date <= cycle_date:
                        if eval_state.current_status != "SUSPENDED":
                            res.is_released = True
                            release_line = PayoutLineRecord(
                                payout_line_id=id_gen.next_payout_line_id(),
                                payout_id=None,
                                seller_id=s_id,
                                source_type="RESERVE",
                                source_id=res.reserve_id,
                                entry_type="RESERVE_RELEASE",
                                amount_cents=res.hold_amount_cents,
                                rule_id=None,
                                created_at=cycle_dt,
                            )
                            current_cycle_lines.append(release_line)

            # 2C. Post-Payout Returns (REFUND and COMMISSION_REVERSAL)
            for line in seller_lines:
                if line.order_line_id in paid_order_lines and line.order_line_id not in refunded_order_lines:
                    ful = ful_by_line.get(line.order_line_id)
                    if ful and ful.returned_at and ful.returned_at.date() <= cycle_date:
                        refunded_order_lines.add(line.order_line_id)
                        ref_line = PayoutLineRecord(
                            payout_line_id=id_gen.next_payout_line_id(),
                            payout_id=None,
                            seller_id=s_id,
                            source_type="ORDER_LINE",
                            source_id=line.order_line_id,
                            entry_type="REFUND",
                            amount_cents=-line.total_gross_cents,
                            rule_id=None,
                            created_at=cycle_dt,
                        )
                        rev_comm_line = PayoutLineRecord(
                            payout_line_id=id_gen.next_payout_line_id(),
                            payout_id=None,
                            seller_id=s_id,
                            source_type="ORDER_LINE",
                            source_id=line.order_line_id,
                            entry_type="COMMISSION_REVERSAL",
                            amount_cents=line.commission_cents,
                            rule_id=line.applied_rule_id,
                            created_at=cycle_dt,
                        )
                        current_cycle_lines.extend([ref_line, rev_comm_line])

            # 2D. Post-Payout Lost Disputes (DISPUTE_DEDUCTION)
            for line in seller_lines:
                dsp = dsp_by_line.get(line.order_line_id)
                if dsp and dsp.dispute_id not in deducted_disputes:
                    if dsp.dispute_status == "RESOLVED_BUYER_WON" and dsp.resolved_at and dsp.resolved_at.date() <= cycle_date:
                        # Deduction applies whether line was paid or held
                        deducted_disputes.add(dsp.dispute_id)
                        dsp_deduct_line = PayoutLineRecord(
                            payout_line_id=id_gen.next_payout_line_id(),
                            payout_id=None,
                            seller_id=s_id,
                            source_type="DISPUTE",
                            source_id=dsp.dispute_id,
                            entry_type="DISPUTE_DEDUCTION",
                            amount_cents=-dsp.amount_cents,
                            rule_id=None,
                            created_at=cycle_dt,
                        )
                        current_cycle_lines.append(dsp_deduct_line)

            # 2E. Aggregate with roll-forward entries
            all_candidate_lines = unallocated_lines_by_seller[s_id] + current_cycle_lines
            net_total_cents = sum(l.amount_cents for l in all_candidate_lines)

            # Locked Rule: If net <= 0, no Payout record is created; lines roll forward
            if net_total_cents > 0:
                p_id = id_gen.next_payout_id()
                payout_status = "HELD" if eval_state.current_status == "SUSPENDED" else "PAID"

                # Assign payout_id to all lines
                for l in all_candidate_lines:
                    l.payout_id = p_id
                    payout_lines.append(l)

                payout_rec = PayoutRecord(
                    payout_id=p_id,
                    seller_id=s_id,
                    cycle_date=cycle_date,
                    total_cents=net_total_cents,
                    status=payout_status,
                    generated_at=cycle_dt,
                    lines=all_candidate_lines,
                )
                payouts.append(payout_rec)
                payouts_by_id[p_id] = payout_rec
                payout_lines_by_payout_id[p_id] = all_candidate_lines

                # Audit event: PayoutEvent
                payout_events.append(
                    PayoutEventRecord(
                        event_id=id_gen.next_payout_event_id(),
                        payout_id=p_id,
                        event_type="GENERATED",
                        event_at=cycle_dt,
                    )
                )
                payout_events.append(
                    PayoutEventRecord(
                        event_id=id_gen.next_payout_event_id(),
                        payout_id=p_id,
                        event_type=payout_status,
                        event_at=cycle_dt + timedelta(minutes=1),
                    )
                )

                # Clear roll-forward ledger
                unallocated_lines_by_seller[s_id] = []
            else:
                # Keep lines in roll-forward buffer
                unallocated_lines_by_seller[s_id] = all_candidate_lines

    # Store final seller status
    seller_final_statuses = {s_id: state.current_status for s_id, state in seller_eval_states.items()}

    # Collect any lines remaining in roll-forward buffer
    unallocated_lines: List[PayoutLineRecord] = []
    for u_lines in unallocated_lines_by_seller.values():
        unallocated_lines.extend(u_lines)

    return SettlementSimulationBundle(
        payouts=payouts,
        payouts_by_id=payouts_by_id,
        payout_lines=payout_lines,
        payout_lines_by_payout_id=payout_lines_by_payout_id,
        payout_events=payout_events,
        seller_status_events=seller_status_events,
        seller_final_statuses=seller_final_statuses,
        unallocated_lines=unallocated_lines,
    )

