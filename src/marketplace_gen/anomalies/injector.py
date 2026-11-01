"""
Controlled Anomaly Injector and Decoupled Ground Truth Generator.

Injects 5 labelled anomaly types post-baseline according to docs/DESIGN.md:
1. PAYOUT_BEFORE_HOLD_RELEASE
2. COMMISSION_APPLIED_TWICE
3. SUSPENDED_SELLER_LISTING
4. DISPUTE_NOT_DEDUCTED
5. PAYOUT_TOTAL_MISMATCH

Isolation rules:
- Anomalies 1, 2, and 4 recompute affected payout totals so only anomaly 5 breaks totals.
- Targets are drawn from sorted eligible candidates using seeded RNG.
- Targets are strictly disjoint.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.ledger import PayoutLineRecord, PayoutRecord, SettlementSimulationBundle
from src.marketplace_gen.simulation.fulfillment import FulfillmentSimulationBundle
from src.marketplace_gen.simulation.master_data import MasterDataBundle, ProductListingRecord
from src.marketplace_gen.simulation.orders import OrderSkeletonBundle


@dataclass(frozen=True)
class GroundTruthRecord:
    """Standardized record of an injected business rule violation."""
    anomaly_id: str
    issue_type: str
    entity_type: str
    entity_id: str
    related_ids: str
    expected_value: str
    observed_value: str
    description: str


@dataclass
class AnomalyInjectionResult:
    """Encapsulates mutated data bundles and the decoupled ground truth dataset."""
    ground_truth: List[GroundTruthRecord]
    injected_counts_by_type: Dict[str, int]
    shortfalls_by_type: Dict[str, int]


def inject_anomalies(
    config: GeneratorConfig,
    master_data: MasterDataBundle,
    order_bundle: OrderSkeletonBundle,
    ful_bundle: FulfillmentSimulationBundle,
    settlement: SettlementSimulationBundle,
    rng: np.random.Generator,
    id_gen: IdGenerator,
) -> AnomalyInjectionResult:
    """
    Injects the 5 labelled anomalies into the simulation bundles.
    Modifies objects in-place while adhering to strict isolation rules.
    """
    target_count = max(3, int(round(120 * config.scale)))
    ground_truth: List[GroundTruthRecord] = []
    injected_counts: Dict[str, int] = {}
    shortfalls: Dict[str, int] = {}

    used_payout_ids: Set[str] = set()
    used_order_line_ids: Set[str] = set()
    used_dispute_ids: Set[str] = set()
    used_seller_ids: Set[str] = set()

    ful_by_line = ful_bundle.fulfillments_by_line_id
    dsp_by_line = ful_bundle.disputes_by_line_id
    payouts_by_seller: Dict[str, List[PayoutRecord]] = {}
    for p in settlement.payouts:
        payouts_by_seller.setdefault(p.seller_id, []).append(p)

    for seller_payouts in payouts_by_seller.values():
        seller_payouts.sort(key=lambda x: x.cycle_date)

    # -------------------------------------------------------------
    # 1. PAYOUT_BEFORE_HOLD_RELEASE
    # -------------------------------------------------------------
    count_1 = 0
    # Candidate order lines: paid in a later cycle where an earlier payout exists before hold release
    eligible_candidates_1 = []
    for p in settlement.payouts:
        s_payouts = payouts_by_seller.get(p.seller_id, [])
        if len(s_payouts) < 2:
            continue
        p_idx = s_payouts.index(p)
        if p_idx == 0:
            continue
        for line in p.lines:
            if line.entry_type == "SALE" and line.source_id not in used_order_line_ids:
                ful = ful_by_line.get(line.source_id)
                if ful and ful.delivered_at:
                    earlier_p = s_payouts[p_idx - 1]
                    # Check if earlier payout is before delivered_at + 14 days
                    if earlier_p.cycle_date < (ful.delivered_at.date() + timedelta(days=config.hold_window_days)):
                        eligible_candidates_1.append((line, p, earlier_p))

    eligible_candidates_1.sort(key=lambda c: (c[1].seller_id, c[0].payout_line_id))
    selected_indices_1 = rng.choice(
        len(eligible_candidates_1),
        size=min(target_count, len(eligible_candidates_1)),
        replace=False,
    ) if eligible_candidates_1 else []

    for idx in selected_indices_1:
        sale_line, orig_payout, earlier_payout = eligible_candidates_1[idx]
        order_line_id = sale_line.source_id

        # Find matching COMMISSION line in orig_payout
        matching_comm_lines = [
            l for l in orig_payout.lines
            if l.source_id == order_line_id and l.entry_type == "COMMISSION"
        ]
        if not matching_comm_lines:
            continue

        comm_line = matching_comm_lines[0]

        # Move SALE and COMMISSION lines to earlier_payout
        orig_payout.lines.remove(sale_line)
        orig_payout.lines.remove(comm_line)
        sale_line.payout_id = earlier_payout.payout_id
        comm_line.payout_id = earlier_payout.payout_id
        earlier_payout.lines.extend([sale_line, comm_line])

        # Isolation rule: Recompute totals so ONLY anomaly 5 breaks arithmetic
        orig_payout.total_cents = sum(l.amount_cents for l in orig_payout.lines)
        earlier_payout.total_cents = sum(l.amount_cents for l in earlier_payout.lines)

        used_payout_ids.add(orig_payout.payout_id)
        used_payout_ids.add(earlier_payout.payout_id)
        used_order_line_ids.add(order_line_id)

        ful = ful_by_line[order_line_id]
        min_allowed_date = ful.delivered_at.date() + timedelta(days=config.hold_window_days)
        gt_rec = GroundTruthRecord(
            anomaly_id=id_gen.next_ground_truth_id(),
            issue_type="PAYOUT_BEFORE_HOLD_RELEASE",
            entity_type="PayoutLine",
            entity_id=sale_line.payout_line_id,
            related_ids=f"{order_line_id},{earlier_payout.payout_id}",
            expected_value=f"cycle_date>={min_allowed_date.isoformat()}",
            observed_value=f"cycle_date={earlier_payout.cycle_date.isoformat()}",
            description="Sale was paid out before the 14-day post-delivery hold release window.",
        )
        ground_truth.append(gt_rec)
        count_1 += 1

    injected_counts["PAYOUT_BEFORE_HOLD_RELEASE"] = count_1
    shortfalls["PAYOUT_BEFORE_HOLD_RELEASE"] = max(0, target_count - count_1)

    # -------------------------------------------------------------
    # 2. COMMISSION_APPLIED_TWICE
    # -------------------------------------------------------------
    count_2 = 0
    candidate_comm_lines = []
    for p in settlement.payouts:
        if p.payout_id in used_payout_ids:
            continue
        for line in p.lines:
            if line.entry_type == "COMMISSION" and line.source_id not in used_order_line_ids:
                candidate_comm_lines.append((line, p))

    candidate_comm_lines.sort(key=lambda c: (c[1].payout_id, c[0].payout_line_id))
    selected_indices_2 = rng.choice(
        len(candidate_comm_lines),
        size=min(target_count, len(candidate_comm_lines)),
        replace=False,
    ) if candidate_comm_lines else []

    for idx in selected_indices_2:
        orig_comm, payout = candidate_comm_lines[idx]
        dup_id = id_gen.next_payout_line_id()
        dup_comm = PayoutLineRecord(
            payout_line_id=dup_id,
            payout_id=payout.payout_id,
            seller_id=payout.seller_id,
            source_type=orig_comm.source_type,
            source_id=orig_comm.source_id,
            entry_type="COMMISSION",
            amount_cents=orig_comm.amount_cents,
            rule_id=orig_comm.rule_id,
            created_at=orig_comm.created_at,
        )
        payout.lines.append(dup_comm)
        settlement.payout_lines.append(dup_comm)
        # Recompute payout total to isolate error
        payout.total_cents = sum(l.amount_cents for l in payout.lines)

        used_payout_ids.add(payout.payout_id)
        used_order_line_ids.add(orig_comm.source_id)

        gt_rec = GroundTruthRecord(
            anomaly_id=id_gen.next_ground_truth_id(),
            issue_type="COMMISSION_APPLIED_TWICE",
            entity_type="PayoutLine",
            entity_id=dup_id,
            related_ids=f"{orig_comm.source_id},{payout.payout_id}",
            expected_value="SINGLE_COMMISSION_ENTRY",
            observed_value="DUPLICATE_COMMISSION_ENTRY",
            description="Commission deduction was applied twice for the same order line in a single payout.",
        )
        ground_truth.append(gt_rec)
        count_2 += 1

    injected_counts["COMMISSION_APPLIED_TWICE"] = count_2
    shortfalls["COMMISSION_APPLIED_TWICE"] = max(0, target_count - count_2)

    # -------------------------------------------------------------
    # 3. SUSPENDED_SELLER_LISTING
    # -------------------------------------------------------------
    count_3 = 0
    # Find sellers with suspension intervals
    suspension_intervals: Dict[str, List[Tuple[datetime, datetime]]] = {}
    for ev in settlement.seller_status_events:
        if ev.new_status == "SUSPENDED":
            susp_start = ev.event_at
            # Find reinstatement if any
            reinstated = [
                e.event_at for e in settlement.seller_status_events
                if e.seller_id == ev.seller_id and e.event_at > susp_start and e.new_status != "SUSPENDED"
            ]
            susp_end = reinstated[0] if reinstated else datetime(2026, 10, 31, 23, 59, 59)
            suspension_intervals.setdefault(ev.seller_id, []).append((susp_start, susp_end))

    candidate_suspended_sellers = sorted(list(suspension_intervals.keys()))
    if candidate_suspended_sellers:
        for s_id in candidate_suspended_sellers:
            if count_3 >= target_count:
                break
            intervals = suspension_intervals[s_id]
            s_start, s_end = intervals[0]
            # Create a listing timestamp inside the suspension window
            window_days = max(1, (s_end.date() - s_start.date()).days)
            offset_days = int(rng.integers(1, min(14, window_days) + 1))
            created_dt = s_start + timedelta(days=offset_days, hours=4)

            new_list_id = id_gen.next_listing_id(s_id)
            cat = str(rng.choice(config.categories))
            new_listing = ProductListingRecord(
                listing_id=new_list_id,
                seller_id=s_id,
                title=f"Disallowed Listing {new_list_id}",
                category=cat,
                base_price_cents=2500,
                created_at=created_dt,
                deactivated_at=None,
            )
            master_data.listings.append(new_listing)
            master_data.listings_by_id[new_list_id] = new_listing
            master_data.listings_by_seller.setdefault(s_id, []).append(new_listing)

            gt_rec = GroundTruthRecord(
                anomaly_id=id_gen.next_ground_truth_id(),
                issue_type="SUSPENDED_SELLER_LISTING",
                entity_type="ProductListing",
                entity_id=new_list_id,
                related_ids=s_id,
                expected_value="NO_LISTING_DURING_SUSPENSION",
                observed_value=f"created_at={created_dt.isoformat()}",
                description="Product listing was added while the seller was in SUSPENDED status.",
            )
            ground_truth.append(gt_rec)
            count_3 += 1

    injected_counts["SUSPENDED_SELLER_LISTING"] = count_3
    shortfalls["SUSPENDED_SELLER_LISTING"] = max(0, target_count - count_3)

    # -------------------------------------------------------------
    # 4. DISPUTE_NOT_DEDUCTED
    # -------------------------------------------------------------
    count_4 = 0
    candidate_dispute_deductions = []
    for p in settlement.payouts:
        if p.payout_id in used_payout_ids:
            continue
        for line in p.lines:
            if line.entry_type == "DISPUTE_DEDUCTION" and line.source_id not in used_dispute_ids:
                candidate_dispute_deductions.append((line, p))

    candidate_dispute_deductions.sort(key=lambda c: (c[1].payout_id, c[0].payout_line_id))
    selected_indices_4 = rng.choice(
        len(candidate_dispute_deductions),
        size=min(target_count, len(candidate_dispute_deductions)),
        replace=False,
    ) if candidate_dispute_deductions else []

    for idx in selected_indices_4:
        deduct_line, payout = candidate_dispute_deductions[idx]
        payout.lines.remove(deduct_line)
        if deduct_line in settlement.payout_lines:
            settlement.payout_lines.remove(deduct_line)
        if hasattr(settlement, "unallocated_lines") and deduct_line in settlement.unallocated_lines:
            settlement.unallocated_lines.remove(deduct_line)

        # Recompute payout total to isolate error
        payout.total_cents = sum(l.amount_cents for l in payout.lines)

        used_payout_ids.add(payout.payout_id)
        used_dispute_ids.add(deduct_line.source_id)

        gt_rec = GroundTruthRecord(
            anomaly_id=id_gen.next_ground_truth_id(),
            issue_type="DISPUTE_NOT_DEDUCTED",
            entity_type="Dispute",
            entity_id=deduct_line.source_id,
            related_ids=f"{payout.payout_id},{payout.seller_id}",
            expected_value="DISPUTE_DEDUCTED",
            observed_value="DISPUTE_DEDUCTION_OMITTED",
            description="Buyer won dispute, but dispute deduction was not clawed back in payout.",
        )
        ground_truth.append(gt_rec)
        count_4 += 1

    injected_counts["DISPUTE_NOT_DEDUCTED"] = count_4
    shortfalls["DISPUTE_NOT_DEDUCTED"] = max(0, target_count - count_4)

    # -------------------------------------------------------------
    # 5. PAYOUT_TOTAL_MISMATCH
    # -------------------------------------------------------------
    count_5 = 0
    candidate_payouts_5 = [p for p in settlement.payouts if p.payout_id not in used_payout_ids]
    candidate_payouts_5.sort(key=lambda p: p.payout_id)

    selected_indices_5 = rng.choice(
        len(candidate_payouts_5),
        size=min(target_count, len(candidate_payouts_5)),
        replace=False,
    ) if candidate_payouts_5 else []

    deltas = [1, -1, 50, -100, 500, -2000, 10000]

    for i, idx in enumerate(selected_indices_5):
        payout = candidate_payouts_5[idx]
        delta = deltas[i % len(deltas)]
        orig_total = payout.total_cents
        payout.total_cents += delta
        used_payout_ids.add(payout.payout_id)

        gt_rec = GroundTruthRecord(
            anomaly_id=id_gen.next_ground_truth_id(),
            issue_type="PAYOUT_TOTAL_MISMATCH",
            entity_type="Payout",
            entity_id=payout.payout_id,
            related_ids=payout.seller_id,
            expected_value=str(orig_total),
            observed_value=str(payout.total_cents),
            description=f"Payout total_cents ({payout.total_cents}) does not match sum of child lines ({orig_total}).",
        )
        ground_truth.append(gt_rec)
        count_5 += 1

    injected_counts["PAYOUT_TOTAL_MISMATCH"] = count_5
    shortfalls["PAYOUT_TOTAL_MISMATCH"] = max(0, target_count - count_5)

    return AnomalyInjectionResult(
        ground_truth=ground_truth,
        injected_counts_by_type=injected_counts,
        shortfalls_by_type=shortfalls,
    )

