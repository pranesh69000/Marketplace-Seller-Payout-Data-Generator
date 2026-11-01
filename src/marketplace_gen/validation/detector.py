"""
Automated Anomaly Detector and Ground Truth Scoring Engine.

Implements pure detection rules for the 5 labelled anomalies and computes
confusion matrices (TP, FP, FN, Precision, Recall, F1) against ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Set, Tuple

from src.marketplace_gen.anomalies.injector import GroundTruthRecord
from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ledger import SettlementSimulationBundle
from src.marketplace_gen.simulation.fulfillment import FulfillmentSimulationBundle
from src.marketplace_gen.simulation.master_data import MasterDataBundle
from src.marketplace_gen.simulation.orders import OrderSkeletonBundle


@dataclass(frozen=True)
class DetectedAnomaly:
    """Record of an anomaly flagged by the detector."""
    issue_type: str
    entity_type: str
    entity_id: str
    description: str


@dataclass
class AnomalyScoreMetrics:
    """Scoring metrics for a single anomaly category."""
    issue_type: str
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float


@dataclass
class DetectorEvaluationReport:
    """Consolidated detector evaluation and scoring results."""
    detected_anomalies: List[DetectedAnomaly]
    metrics_by_type: Dict[str, AnomalyScoreMetrics]
    overall_precision: float
    overall_recall: float
    overall_f1: float


def detect_all_anomalies(
    config: GeneratorConfig,
    master_data: MasterDataBundle,
    order_bundle: OrderSkeletonBundle,
    ful_bundle: FulfillmentSimulationBundle,
    settlement: SettlementSimulationBundle,
) -> List[DetectedAnomaly]:
    """
    Pure detector evaluating the 5 business rules across the dataset.
    Returns list of all flagged anomalies.
    """
    flagged: List[DetectedAnomaly] = []
    ful_by_line = ful_bundle.fulfillments_by_line_id

    # 1. Detect PAYOUT_BEFORE_HOLD_RELEASE
    for payout in settlement.payouts:
        for line in payout.lines:
            if line.entry_type == "SALE" and line.source_type == "ORDER_LINE":
                ful = ful_by_line.get(line.source_id)
                if ful and ful.delivered_at:
                    min_allowed_date = ful.delivered_at.date() + timedelta(days=config.hold_window_days)
                    if payout.cycle_date < min_allowed_date:
                        flagged.append(
                            DetectedAnomaly(
                                issue_type="PAYOUT_BEFORE_HOLD_RELEASE",
                                entity_type="PayoutLine",
                                entity_id=line.payout_line_id,
                                description=f"Payout cycle {payout.cycle_date} occurred before 14-day hold {min_allowed_date}",
                            )
                        )

    # 2. Detect COMMISSION_APPLIED_TWICE
    for payout in settlement.payouts:
        comm_lines_by_order_line: Dict[str, List[str]] = {}
        for line in payout.lines:
            if line.entry_type == "COMMISSION" and line.source_type == "ORDER_LINE":
                comm_lines_by_order_line.setdefault(line.source_id, []).append(line.payout_line_id)

        for ol_id, pline_ids in comm_lines_by_order_line.items():
            if len(pline_ids) > 1:
                # Flag the duplicate entries (all beyond the first)
                for dup_pline_id in pline_ids[1:]:
                    flagged.append(
                        DetectedAnomaly(
                            issue_type="COMMISSION_APPLIED_TWICE",
                            entity_type="PayoutLine",
                            entity_id=dup_pline_id,
                            description=f"Duplicate commission deduction for line {ol_id} in payout {payout.payout_id}",
                        )
                    )

    # 3. Detect SUSPENDED_SELLER_LISTING
    # Reconstruct seller suspension intervals from seller_status_events
    as_of_dt = datetime.combine(config.as_of_date, datetime.max.time().replace(microsecond=0))
    seller_suspension_intervals: Dict[str, List[Tuple[datetime, datetime]]] = {}
    for ev in settlement.seller_status_events:
        if ev.new_status == "SUSPENDED":
            s_start = ev.event_at
            reinstatements = [
                e.event_at for e in settlement.seller_status_events
                if e.seller_id == ev.seller_id and e.event_at > s_start and e.new_status != "SUSPENDED"
            ]
            s_end = reinstatements[0] if reinstatements else as_of_dt
            seller_suspension_intervals.setdefault(ev.seller_id, []).append((s_start, s_end))

    for lst in master_data.listings:
        intervals = seller_suspension_intervals.get(lst.seller_id, [])
        for s_start, s_end in intervals:
            # Listing created while suspended
            if s_start <= lst.created_at <= s_end:
                flagged.append(
                    DetectedAnomaly(
                        issue_type="SUSPENDED_SELLER_LISTING",
                        entity_type="ProductListing",
                        entity_id=lst.listing_id,
                        description=f"Listing created at {lst.created_at} while seller {lst.seller_id} was suspended",
                    )
                )

    # 4. Detect DISPUTE_NOT_DEDUCTED
    # A dispute is expected to be deducted only if it was resolved on or before the last settlement Monday cycle
    last_cycle_monday = config.as_of_date - timedelta(days=config.as_of_date.weekday())
    all_ledger_lines = (
        settlement.payout_lines + getattr(settlement, "unallocated_lines", [])
    )
    deducted_dispute_ids = {
        pl.source_id for pl in all_ledger_lines if pl.entry_type == "DISPUTE_DEDUCTION"
    }
    for dsp in ful_bundle.disputes:
        if dsp.dispute_status == "RESOLVED_BUYER_WON" and dsp.resolved_at and dsp.resolved_at.date() <= last_cycle_monday:
            if dsp.dispute_id not in deducted_dispute_ids:
                flagged.append(
                    DetectedAnomaly(
                        issue_type="DISPUTE_NOT_DEDUCTED",
                        entity_type="Dispute",
                        entity_id=dsp.dispute_id,
                        description=f"Buyer won dispute {dsp.dispute_id} but deduction was omitted from payouts",
                    )
                )

    # 5. Detect PAYOUT_TOTAL_MISMATCH
    for payout in settlement.payouts:
        sum_lines = sum(l.amount_cents for l in payout.lines)
        if payout.total_cents != sum_lines:
            flagged.append(
                DetectedAnomaly(
                    issue_type="PAYOUT_TOTAL_MISMATCH",
                    entity_type="Payout",
                    entity_id=payout.payout_id,
                    description=f"Payout total_cents ({payout.total_cents}) does not match sum of lines ({sum_lines})",
                )
            )

    return flagged


def evaluate_detector(
    ground_truth: List[GroundTruthRecord],
    detected_anomalies: List[DetectedAnomaly],
) -> DetectorEvaluationReport:
    """
    Computes precision, recall, and F1 score per anomaly type and overall.
    Matches flagged instances to ground truth by (issue_type, entity_id).
    """
    gt_by_type: Dict[str, Set[str]] = {}
    for gt in ground_truth:
        gt_by_type.setdefault(gt.issue_type, set()).add(gt.entity_id)

    detected_by_type: Dict[str, Set[str]] = {}
    for d in detected_anomalies:
        detected_by_type.setdefault(d.issue_type, set()).add(d.entity_id)

    all_types = sorted(list(set(gt_by_type.keys()) | set(detected_by_type.keys())))
    metrics_by_type: Dict[str, AnomalyScoreMetrics] = {}

    total_tp = 0
    total_fp = 0
    total_fn = 0

    for itype in all_types:
        gt_set = gt_by_type.get(itype, set())
        det_set = detected_by_type.get(itype, set())

        tp = len(gt_set & det_set)
        fp = len(det_set - gt_set)
        fn = len(gt_set - det_set)

        total_tp += tp
        total_fp += fp
        total_fn += fn

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        metrics_by_type[itype] = AnomalyScoreMetrics(
            issue_type=itype,
            true_positives=tp,
            false_positives=fp,
            false_negatives=fn,
            precision=precision,
            recall=recall,
            f1_score=f1,
        )

    overall_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 1.0
    overall_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 1.0
    overall_f1 = (2 * overall_prec * overall_rec / (overall_prec + overall_rec)) if (overall_prec + overall_rec) > 0 else 0.0

    return DetectorEvaluationReport(
        detected_anomalies=detected_anomalies,
        metrics_by_type=metrics_by_type,
        overall_precision=overall_prec,
        overall_recall=overall_rec,
        overall_f1=overall_f1,
    )

