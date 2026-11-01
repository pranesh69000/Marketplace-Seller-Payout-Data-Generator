"""
Deterministic order and order-line skeleton generator.

Generates customer orders, multi-seller split order lines,
and resolves time-locked commission rules using pure business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple
import numpy as np

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.rules.commission import (
    calculate_commission,
    resolve_commission_rule,
)
from src.marketplace_gen.simulation.master_data import (
    MasterDataBundle,
    ProductListingRecord,
)


@dataclass
class OrderLineRecord:
    """Represents a discrete item within a customer order."""
    order_line_id: str
    order_id: str
    seller_id: str
    listing_id: str
    quantity: int
    unit_price_cents: int
    total_gross_cents: int
    applied_rule_id: str
    commission_rate_bps: int
    commission_cents: int
    placed_at: datetime


@dataclass
class OrderRecord:
    """Header record for a customer checkout order."""
    order_id: str
    customer_id: str
    order_status: str
    total_gross_cents: int
    placed_at: datetime
    lines: List[OrderLineRecord]


@dataclass
class OrderSkeletonBundle:
    """Encapsulates generated orders and order lines."""
    orders: List[OrderRecord]
    orders_by_id: Dict[str, OrderRecord]
    lines: List[OrderLineRecord]
    lines_by_id: Dict[str, OrderLineRecord]
    lines_by_seller: Dict[str, List[OrderLineRecord]]
    lines_by_week: Dict[int, List[OrderLineRecord]]  # week_index -> lines


def generate_order_skeleton(
    config: GeneratorConfig,
    master_data: MasterDataBundle,
    rng: np.random.Generator,
    id_gen: IdGenerator,
) -> OrderSkeletonBundle:
    """
    Generates orders and order lines across the 2026-01-01 to 2026-10-15 window.
    
    Adheres strictly to locked design decisions:
    - Lines per order: 1 (35%), 2 (35%), 3 (20%), 4 (10%).
    - Multi-seller split orders generated naturally.
    - Commission calculated and locked using resolve_commission_rule.
    """
    total_orders = config.scaled_orders_count
    start_dt = datetime.combine(config.start_date, datetime.min.time())
    total_days = (config.end_order_date - config.start_date).days + 1

    # 1. Temporal demand distribution: Upward trend + weekend lift
    day_weights = np.zeros(total_days, dtype=np.float64)
    for d in range(total_days):
        current_date = config.start_date + timedelta(days=d)
        trend_factor = 1.0 + 0.40 * (d / total_days)  # gentle 40% growth over the year
        day_of_week = current_date.weekday()
        weekend_factor = 1.25 if day_of_week in (5, 6) else 1.0
        day_weights[d] = trend_factor * weekend_factor

    day_probs = day_weights / day_weights.sum()
    order_days = rng.choice(total_days, size=total_orders, p=day_probs)
    order_seconds = rng.integers(0, 86400, size=total_orders)

    # Sort orders chronologically so order IDs align with placement time
    sort_indices = np.lexsort((order_seconds, order_days))
    sorted_order_days = order_days[sort_indices]
    sorted_order_seconds = order_seconds[sort_indices]

    # 2. Customer pool with repeat buyer behavior (Zipfian distribution)
    base_customer_pool_size = max(50, int(round(35000 * config.scale)))
    customer_ids = [id_gen.next_customer_id() for _ in range(base_customer_pool_size)]
    
    # Power-law weights for repeat buyers
    ranks = np.arange(1, base_customer_pool_size + 1, dtype=np.float64)
    customer_weights = 1.0 / (ranks ** 0.8)
    customer_probs = customer_weights / customer_weights.sum()
    assigned_customers = rng.choice(customer_ids, size=total_orders, p=customer_probs)

    # 3. Active Listings chronological pool
    # Listings are sorted by created_at so orders only purchase items that already exist
    sorted_listings = sorted(master_data.listings, key=lambda l: l.created_at)
    num_total_listings = len(sorted_listings)
    active_listing_cursor = 0

    # 4. Lines per order distribution: 1 (35%), 2 (35%), 3 (20%), 4 (10%)
    line_counts_choices = np.array([1, 2, 3, 4], dtype=np.int32)
    line_counts_probs = np.array([0.35, 0.35, 0.20, 0.10], dtype=np.float64)
    order_line_counts = rng.choice(line_counts_choices, size=total_orders, p=line_counts_probs)

    # 5. Quantity distribution: 1 (80%), 2 (15%), 3 (3%), 4 (2%)
    qty_choices = np.array([1, 2, 3, 4], dtype=np.int32)
    qty_probs = np.array([0.80, 0.15, 0.03, 0.02], dtype=np.float64)

    orders: List[OrderRecord] = []
    orders_by_id: Dict[str, OrderRecord] = {}
    lines: List[OrderLineRecord] = []
    lines_by_id: Dict[str, OrderLineRecord] = {}
    lines_by_seller: Dict[str, List[OrderLineRecord]] = {s.seller_id: [] for s in master_data.sellers}
    lines_by_week: Dict[int, List[OrderLineRecord]] = {}

    for i in range(total_orders):
        ord_id = id_gen.next_order_id()
        cust_id = str(assigned_customers[i])
        placed_dt = start_dt + timedelta(
            days=int(sorted_order_days[i]),
            seconds=int(sorted_order_seconds[i]),
        )
        placed_date = placed_dt.date()

        # Advance active listing pool to match placed_dt
        while (
            active_listing_cursor < num_total_listings
            and sorted_listings[active_listing_cursor].created_at <= placed_dt
        ):
            active_listing_cursor += 1

        available_listings_count = max(1, active_listing_cursor)

        num_lines = int(order_line_counts[i])
        # Sample listings strictly from active listings created on or before placed_dt
        selected_listing_indices = rng.integers(0, available_listings_count, size=num_lines)
        selected_quantities = rng.choice(qty_choices, size=num_lines, p=qty_probs)

        order_lines_for_this_order: List[OrderLineRecord] = []
        order_total_gross = 0

        for line_idx in range(num_lines):
            line_num = line_idx + 1
            line_id = id_gen.order_line_id(ord_id, line_num)
            listing = sorted_listings[selected_listing_indices[line_idx]]
            qty = int(selected_quantities[line_idx])
            unit_price = listing.base_price_cents
            line_gross = qty * unit_price
            order_total_gross += line_gross

            # Commission rule resolution
            assigned_rules = master_data.assignments_by_seller.get(listing.seller_id, [])
            winning_rule = resolve_commission_rule(
                order_date=placed_date,
                category=listing.category,
                assigned_rule_ids=assigned_rules,
                all_rules_by_id=master_data.rules_by_id,
            )
            comm_rate_bps = winning_rule.rate_bps
            comm_cents = calculate_commission(line_gross, comm_rate_bps)

            line_rec = OrderLineRecord(
                order_line_id=line_id,
                order_id=ord_id,
                seller_id=listing.seller_id,
                listing_id=listing.listing_id,
                quantity=qty,
                unit_price_cents=unit_price,
                total_gross_cents=line_gross,
                applied_rule_id=winning_rule.rule_id,
                commission_rate_bps=comm_rate_bps,
                commission_cents=comm_cents,
                placed_at=placed_dt,
            )
            lines.append(line_rec)
            lines_by_id[line_id] = line_rec
            order_lines_for_this_order.append(line_rec)
            lines_by_seller[listing.seller_id].append(line_rec)

            # Week index calculation (relative to 2026-01-01)
            week_idx = (placed_date - config.start_date).days // 7
            if week_idx not in lines_by_week:
                lines_by_week[week_idx] = []
            lines_by_week[week_idx].append(line_rec)

        ord_rec = OrderRecord(
            order_id=ord_id,
            customer_id=cust_id,
            order_status="SUBMITTED",
            total_gross_cents=order_total_gross,
            placed_at=placed_dt,
            lines=order_lines_for_this_order,
        )
        orders.append(ord_rec)
        orders_by_id[ord_id] = ord_rec

    return OrderSkeletonBundle(
        orders=orders,
        orders_by_id=orders_by_id,
        lines=lines,
        lines_by_id=lines_by_id,
        lines_by_seller=lines_by_seller,
        lines_by_week=lines_by_week,
    )

