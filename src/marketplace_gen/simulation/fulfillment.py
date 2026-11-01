"""
Fulfillment, Returns, Disputes, and Customer Reviews simulation engine.

Implements realistic causal mechanics based on seller quality tiers,
delays, and post-delivery behaviors. Enforces strict temporal ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.simulation.master_data import MasterDataBundle
from src.marketplace_gen.simulation.orders import OrderLineRecord, OrderSkeletonBundle


CARRIERS = ("UPS", "FEDEX", "USPS", "DHL")

REVIEW_COMMENTS = {
    5: ("Outstanding quality and fast shipping! Exceeded expectations.", "Item exactly as described, very satisfied.", "Great seller, will buy again!"),
    4: ("Good product overall, prompt delivery.", "Solid quality, minor packaging wear but item is fine.", "Works well as expected."),
    3: ("Decent product, but delivery took longer than expected.", "Average quality, matches the price.", "Acceptable, but room for improvement."),
    2: ("Product was underwhelming and shipping was delayed.", "Not as described in the photos.", "Poor quality, disappointed."),
    1: ("Terrible experience, arrived damaged or not at all.", "Defective item, seller was unhelpful.", "Completely dissatisfied, requested refund/dispute."),
}


@dataclass
class FulfillmentRecord:
    """Represents the physical shipping and tracking record for an order line."""
    fulfillment_id: str
    order_line_id: str
    carrier: str
    tracking_number: str
    fulfillment_status: str  # 'PENDING', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'FAILED_DELIVERY', 'RETURNED'
    shipped_at: Optional[datetime]
    delivered_at: Optional[datetime]
    returned_at: Optional[datetime]
    is_late_shipment: bool


@dataclass
class FulfillmentEventRecord:
    """Discrete audit milestone event for fulfillment tracking."""
    event_id: str
    fulfillment_id: str
    event_type: str  # 'PLACED', 'SHIPPED', 'OUT_FOR_DELIVERY', 'DELIVERED', 'RETURN_REQUESTED', 'RETURN_COMPLETED'
    event_at: datetime


@dataclass
class CustomerReviewRecord:
    """Customer rating and comment for an order line."""
    review_id: str
    order_line_id: str
    rating: int
    review_text: str
    created_at: datetime


@dataclass
class DisputeRecord:
    """Customer dispute claim against an order line."""
    dispute_id: str
    order_line_id: str
    dispute_type: str    # 'NOT_RECEIVED', 'NOT_AS_DESCRIBED', 'RETURN_DISPUTE', 'CHARGEBACK'
    dispute_status: str  # 'OPEN', 'RESOLVED_SELLER_WON', 'RESOLVED_BUYER_WON'
    amount_cents: int
    opened_at: datetime
    resolved_at: Optional[datetime]


@dataclass
class DisputeEventRecord:
    """Audit milestone event for a dispute lifecycle."""
    event_id: str
    dispute_id: str
    status: str
    notes: str
    event_at: datetime


@dataclass
class FulfillmentSimulationBundle:
    """Encapsulates all simulated fulfillment, dispute, review, and event entities."""
    fulfillments: List[FulfillmentRecord]
    fulfillments_by_line_id: Dict[str, FulfillmentRecord]
    fulfillment_events: List[FulfillmentEventRecord]
    reviews: List[CustomerReviewRecord]
    reviews_by_line_id: Dict[str, CustomerReviewRecord]
    disputes: List[DisputeRecord]
    disputes_by_line_id: Dict[str, DisputeRecord]
    dispute_events: List[DisputeEventRecord]


def simulate_fulfillments_and_disputes(
    config: GeneratorConfig,
    master_data: MasterDataBundle,
    order_bundle: OrderSkeletonBundle,
    rng: np.random.Generator,
    id_gen: IdGenerator,
) -> FulfillmentSimulationBundle:
    """
    Executes causal simulation across all order lines.
    
    Causal flow:
    1. Order Line placed_at -> dispatch delay -> shipped_at (or CANCELLED)
    2. shipped_at -> transit time -> delivered_at (or FAILED_DELIVERY)
    3. delivered_at -> return window (3-20 days) -> returned_at (status=RETURNED)
    4. delivered/failed lines -> dispute window (<= 30 days) -> dispute initiated & resolved
    5. delivered lines -> customer review (~35% sample, rating shifted by delays/disputes)
    """
    as_of_dt = datetime.combine(config.as_of_date, datetime.max.time().replace(microsecond=0))

    fulfillments: List[FulfillmentRecord] = []
    fulfillments_by_line_id: Dict[str, FulfillmentRecord] = {}
    fulfillment_events: List[FulfillmentEventRecord] = []
    reviews: List[CustomerReviewRecord] = []
    reviews_by_line_id: Dict[str, CustomerReviewRecord] = {}
    disputes: List[DisputeRecord] = []
    disputes_by_line_id: Dict[str, DisputeRecord] = {}
    dispute_events: List[DisputeEventRecord] = []

    tracking_counter = 10000000

    for line in order_bundle.lines:
        seller = master_data.sellers_by_id[line.seller_id]
        tier = seller.quality_tier
        placed_dt = line.placed_at
        ful_id = id_gen.fulfillment_id(line.order_line_id)

        # 1. Initial event: PLACED
        fulfillment_events.append(
            FulfillmentEventRecord(
                event_id=id_gen.next_fulfillment_event_id(),
                fulfillment_id=ful_id,
                event_type="PLACED",
                event_at=placed_dt,
            )
        )

        # Carrier assignment
        carrier = CARRIERS[rng.integers(0, len(CARRIERS))]
        tracking_counter += 1
        tracking_num = f"{carrier[:2]}-{tracking_counter}"

        # 2. Dispatch delay & Cancellation check
        # Failure/cancellation probability based on tier
        cancel_prob = 0.008 if tier == "GOOD" else (0.020 if tier == "AVERAGE" else 0.050)
        if rng.random() < cancel_prob:
            # Order cancelled during fulfillment preparation
            cancel_dt = placed_dt + timedelta(hours=int(rng.integers(6, 48)))
            fulfillments.append(
                FulfillmentRecord(
                    fulfillment_id=ful_id,
                    order_line_id=line.order_line_id,
                    carrier=carrier,
                    tracking_number=tracking_num,
                    fulfillment_status="CANCELLED",
                    shipped_at=None,
                    delivered_at=None,
                    returned_at=None,
                    is_late_shipment=False,
                )
            )
            fulfillments_by_line_id[line.order_line_id] = fulfillments[-1]
            continue

        # Dispatch delay distribution (days to ship)
        # Late shipment rule: shipped_at.date() > placed_dt.date() + 3 days
        if tier == "GOOD":
            dispatch_days = rng.choice([1, 2, 3, 4, 5], p=[0.60, 0.32, 0.05, 0.02, 0.01])
        elif tier == "AVERAGE":
            dispatch_days = rng.choice([1, 2, 3, 4, 5, 6], p=[0.35, 0.45, 0.10, 0.06, 0.03, 0.01])
        else:  # POOR tier
            dispatch_days = rng.choice([1, 2, 3, 4, 5, 6, 7], p=[0.15, 0.25, 0.25, 0.15, 0.10, 0.07, 0.03])

        dispatch_seconds = int(rng.integers(0, 86400))
        shipped_dt = placed_dt + timedelta(days=int(dispatch_days), seconds=dispatch_seconds)
        is_late = shipped_dt.date() > (placed_dt.date() + timedelta(days=3))

        fulfillment_events.append(
            FulfillmentEventRecord(
                event_id=id_gen.next_fulfillment_event_id(),
                fulfillment_id=ful_id,
                event_type="SHIPPED",
                event_at=shipped_dt,
            )
        )

        # 3. Transit & Delivery
        fail_delivery_prob = 0.008 if tier == "GOOD" else (0.015 if tier == "AVERAGE" else 0.035)
        if rng.random() < fail_delivery_prob:
            # Delivery failed in transit
            out_dt = shipped_dt + timedelta(days=int(rng.integers(2, 5)))
            fulfillment_events.append(
                FulfillmentEventRecord(
                    event_id=id_gen.next_fulfillment_event_id(),
                    fulfillment_id=ful_id,
                    event_type="OUT_FOR_DELIVERY",
                    event_at=out_dt,
                )
            )
            fulfillments.append(
                FulfillmentRecord(
                    fulfillment_id=ful_id,
                    order_line_id=line.order_line_id,
                    carrier=carrier,
                    tracking_number=tracking_num,
                    fulfillment_status="FAILED_DELIVERY",
                    shipped_at=shipped_dt,
                    delivered_at=None,
                    returned_at=None,
                    is_late_shipment=is_late,
                )
            )
            fulfillments_by_line_id[line.order_line_id] = fulfillments[-1]

            # High propensity for dispute on failed delivery (~75%)
            if rng.random() < 0.75:
                dsp_dt = out_dt + timedelta(days=int(rng.integers(2, 7)))
                if dsp_dt <= as_of_dt:
                    dsp_id = id_gen.next_dispute_id()
                    res_days = int(rng.integers(5, 18))
                    res_dt = dsp_dt + timedelta(days=res_days)
                    status = "RESOLVED_BUYER_WON" if res_dt <= as_of_dt else "OPEN"
                    resolved_timestamp = res_dt if status != "OPEN" else None

                    dsp_rec = DisputeRecord(
                        dispute_id=dsp_id,
                        order_line_id=line.order_line_id,
                        dispute_type="NOT_RECEIVED",
                        dispute_status=status,
                        amount_cents=line.total_gross_cents,
                        opened_at=dsp_dt,
                        resolved_at=resolved_timestamp,
                    )
                    disputes.append(dsp_rec)
                    disputes_by_line_id[line.order_line_id] = dsp_rec

                    # Dispute events
                    dispute_events.append(
                        DisputeEventRecord(
                            event_id=id_gen.next_dispute_event_id(),
                            dispute_id=dsp_id,
                            status="OPEN",
                            notes="Customer reported non-receipt following failed carrier delivery.",
                            event_at=dsp_dt,
                        )
                    )
                    if status != "OPEN":
                        dispute_events.append(
                            DisputeEventRecord(
                                event_id=id_gen.next_dispute_event_id(),
                                dispute_id=dsp_id,
                                status=status,
                                notes="Buyer dispute upheld; carrier verified delivery failure.",
                                event_at=res_dt,
                            )
                        )
            continue

        # Normal successful delivery
        transit_days = int(rng.integers(2, 6))
        delivered_dt = shipped_dt + timedelta(days=transit_days, hours=int(rng.integers(2, 10)))

        fulfillment_events.append(
            FulfillmentEventRecord(
                event_id=id_gen.next_fulfillment_event_id(),
                fulfillment_id=ful_id,
                event_type="OUT_FOR_DELIVERY",
                event_at=delivered_dt - timedelta(hours=4),
            )
        )
        fulfillment_events.append(
            FulfillmentEventRecord(
                event_id=id_gen.next_fulfillment_event_id(),
                fulfillment_id=ful_id,
                event_type="DELIVERED",
                event_at=delivered_dt,
            )
        )

        # 4. Returns check (3 to 20 days post-delivery)
        # Category influence on returns: APPAREL is higher (~9%), BOOKS lower (~2%)
        listing = master_data.listings_by_id[line.listing_id]
        cat_return_bias = {
            "APPAREL": 0.09,
            "ELECTRONICS": 0.05,
            "HOME_KITCHEN": 0.06,
            "BEAUTY": 0.04,
            "SPORTS": 0.05,
            "BOOKS": 0.02,
        }.get(listing.category, 0.06)

        # Quality tier penalty on returns
        tier_return_mult = 0.8 if tier == "GOOD" else (1.1 if tier == "AVERAGE" else 1.6)
        effective_return_prob = cat_return_bias * tier_return_mult

        is_returned = False
        returned_dt: Optional[datetime] = None

        if rng.random() < effective_return_prob:
            ret_delay = int(rng.integers(3, 21))
            tentative_return_dt = delivered_dt + timedelta(days=ret_delay)
            if tentative_return_dt <= as_of_dt:
                is_returned = True
                returned_dt = tentative_return_dt
                fulfillment_events.append(
                    FulfillmentEventRecord(
                        event_id=id_gen.next_fulfillment_event_id(),
                        fulfillment_id=ful_id,
                        event_type="RETURN_REQUESTED",
                        event_at=delivered_dt + timedelta(days=ret_delay - 2),
                    )
                )
                fulfillment_events.append(
                    FulfillmentEventRecord(
                        event_id=id_gen.next_fulfillment_event_id(),
                        fulfillment_id=ful_id,
                        event_type="RETURN_COMPLETED",
                        event_at=returned_dt,
                    )
                )

        ful_status = "RETURNED" if is_returned else "DELIVERED"
        ful_rec = FulfillmentRecord(
            fulfillment_id=ful_id,
            order_line_id=line.order_line_id,
            carrier=carrier,
            tracking_number=tracking_num,
            fulfillment_status=ful_status,
            shipped_at=shipped_dt,
            delivered_at=delivered_dt,
            returned_at=returned_dt,
            is_late_shipment=is_late,
        )
        fulfillments.append(ful_rec)
        fulfillments_by_line_id[line.order_line_id] = ful_rec

        # 5. Customer Disputes simulation (post-delivery <= 30 days)
        # Causal propensity:
        # - Shipped late: +4.0%
        # - Return conflict: ~8% of returns experience a dispute
        # - Tier base propensity: POOR: 9.0%, AVERAGE: 3.2%, GOOD: 1.4%
        has_dispute = False
        dispute_type = "NOT_AS_DESCRIBED"

        if is_returned and rng.random() < 0.08:
            has_dispute = True
            dispute_type = "RETURN_DISPUTE"
        else:
            base_dsp_prob = 0.014 if tier == "GOOD" else (0.032 if tier == "AVERAGE" else 0.090)
            if is_late:
                base_dsp_prob += 0.040
            if rng.random() < base_dsp_prob:
                has_dispute = True
                dispute_type = rng.choice(
                    ["NOT_AS_DESCRIBED", "CHARGEBACK", "NOT_RECEIVED"],
                    p=[0.60, 0.25, 0.15],
                )

        if has_dispute:
            dsp_delay = int(rng.integers(2, min(30, max(3, (as_of_dt - delivered_dt).days)) + 1))
            dsp_dt = delivered_dt + timedelta(days=dsp_delay)
            if dsp_dt <= as_of_dt:
                dsp_id = id_gen.next_dispute_id()
                res_days = int(rng.integers(5, 22))
                res_dt = dsp_dt + timedelta(days=res_days)

                # Adjudication: Buyer win rate ~70% on POOR / Late, ~50% on GOOD
                buyer_win_rate = 0.75 if (tier == "POOR" or is_late) else 0.50
                is_buyer_win = rng.random() < buyer_win_rate

                if res_dt <= as_of_dt:
                    status = "RESOLVED_BUYER_WON" if is_buyer_win else "RESOLVED_SELLER_WON"
                    resolved_timestamp: Optional[datetime] = res_dt
                else:
                    status = "OPEN"
                    resolved_timestamp = None

                dsp_rec = DisputeRecord(
                    dispute_id=dsp_id,
                    order_line_id=line.order_line_id,
                    dispute_type=dispute_type,
                    dispute_status=status,
                    amount_cents=line.total_gross_cents,
                    opened_at=dsp_dt,
                    resolved_at=resolved_timestamp,
                )
                disputes.append(dsp_rec)
                disputes_by_line_id[line.order_line_id] = dsp_rec

                dispute_events.append(
                    DisputeEventRecord(
                        event_id=id_gen.next_dispute_event_id(),
                        dispute_id=dsp_id,
                        status="OPEN",
                        notes=f"Buyer opened {dispute_type} dispute claim.",
                        event_at=dsp_dt,
                    )
                )
                if status != "OPEN":
                    dispute_events.append(
                        DisputeEventRecord(
                            event_id=id_gen.next_dispute_event_id(),
                            dispute_id=dsp_id,
                            status=status,
                            notes=f"Claim adjudicated: {status}.",
                            event_at=res_dt,
                        )
                    )

        # 6. Customer Reviews simulation (~35% of delivered lines)
        if rng.random() < 0.35:
            rev_delay = int(rng.integers(1, min(25, max(2, (as_of_dt - delivered_dt).days)) + 1))
            rev_dt = delivered_dt + timedelta(days=rev_delay, hours=int(rng.integers(1, 10)))
            if rev_dt <= as_of_dt:
                # Rating logic
                if has_dispute:
                    rating = 1 if rng.random() < 0.85 else 2
                elif is_returned:
                    rating = int(rng.choice([1, 2, 3], p=[0.20, 0.50, 0.30]))
                elif is_late:
                    rating = int(rng.choice([1, 2, 3, 4], p=[0.10, 0.25, 0.40, 0.25]))
                else:
                    rating = int(rng.choice([3, 4, 5], p=[0.10, 0.40, 0.50]))

                comments = REVIEW_COMMENTS[rating]
                text = comments[rng.integers(0, len(comments))]

                rev_rec = CustomerReviewRecord(
                    review_id=id_gen.next_review_id(),
                    order_line_id=line.order_line_id,
                    rating=rating,
                    review_text=text,
                    created_at=rev_dt,
                )
                reviews.append(rev_rec)
                reviews_by_line_id[line.order_line_id] = rev_rec

    return FulfillmentSimulationBundle(
        fulfillments=fulfillments,
        fulfillments_by_line_id=fulfillments_by_line_id,
        fulfillment_events=fulfillment_events,
        reviews=reviews,
        reviews_by_line_id=reviews_by_line_id,
        disputes=disputes,
        disputes_by_line_id=disputes_by_line_id,
        dispute_events=dispute_events,
    )

