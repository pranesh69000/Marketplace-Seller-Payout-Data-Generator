"""
Configuration management for Marketplace Seller Payout Data Generator.

Provides immutable, type-safe settings with explicit startup validation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, Tuple


@dataclass(frozen=True)
class GeneratorConfig:
    """Master configuration containing locked parameters and calibrated thresholds."""

    # Determinism
    seed: int = 20261022
    scale: float = 1.0

    # Timeline bounds (Locked in DESIGN.md)
    start_date: date = field(default_factory=lambda: date(2026, 1, 1))
    end_order_date: date = field(default_factory=lambda: date(2026, 10, 15))
    as_of_date: date = field(default_factory=lambda: date(2026, 10, 31))

    # Settlement Windows (Locked)
    hold_window_days: int = 14
    dispute_window_days: int = 30
    reserve_hold_window_days: int = 60
    reserve_rate_bps: int = 1000  # 10.00%

    # Status Evaluation Thresholds (Locked / Calibrated)
    eval_window_days: int = 60
    eval_min_lines: int = 15
    min_suspension_days: int = 30
    clean_evals_for_active: int = 2

    # Thresholds in basis points (1% = 100 bps)
    watchlist_late_bps: int = 1200      # 12.0%
    watchlist_dispute_bps: int = 900    # 9.0%
    suspension_late_bps: int = 2000     # 20.0%
    suspension_dispute_bps: int = 1400  # 14.0%

    # Baseline Scale 1.0 Volumes
    base_sellers_count: int = 2000
    base_listings_count: int = 20000
    base_orders_count: int = 100000
    target_disputes_count: int = 10000

    # Seller Quality Tier Weights (Locked: Good ~70%, Average ~22%, Poor ~8%)
    seller_tier_distribution: Tuple[Tuple[str, float], ...] = (
        ("GOOD", 0.70),
        ("AVERAGE", 0.22),
        ("POOR", 0.08),
    )

    # Categories
    categories: Tuple[str, ...] = (
        "ELECTRONICS",
        "APPAREL",
        "HOME_KITCHEN",
        "BEAUTY",
        "SPORTS",
        "BOOKS",
    )

    def __post_init__(self) -> None:
        """Validate all parameters to enforce fast-fail behavior."""
        if self.scale <= 0.0:
            raise ValueError(f"Scale must be strictly positive, got {self.scale}")
        if self.seed < 0:
            raise ValueError(f"Seed must be a non-negative integer, got {self.seed}")
        if self.start_date > self.end_order_date:
            raise ValueError("start_date cannot be after end_order_date")
        if self.end_order_date > self.as_of_date:
            raise ValueError("end_order_date cannot be after as_of_date")
        if self.hold_window_days <= 0 or self.dispute_window_days <= 0:
            raise ValueError("Hold and dispute windows must be strictly positive days")
        if self.watchlist_late_bps >= self.suspension_late_bps:
            raise ValueError("Watchlist late threshold must be strictly less than suspension threshold")
        if self.watchlist_dispute_bps >= self.suspension_dispute_bps:
            raise ValueError("Watchlist dispute threshold must be strictly less than suspension threshold")

    @property
    def scaled_sellers_count(self) -> int:
        """Calculate scaled seller volume (minimum 5 sellers)."""
        return max(5, int(round(self.base_sellers_count * self.scale)))

    @property
    def scaled_orders_count(self) -> int:
        """Calculate scaled order volume (minimum 10 orders)."""
        return max(10, int(round(self.base_orders_count * self.scale)))

    @property
    def scaled_disputes_target(self) -> int:
        """Calculate scaled dispute volume target."""
        return max(1, int(round(self.target_disputes_count * self.scale)))

