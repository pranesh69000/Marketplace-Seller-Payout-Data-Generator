"""
Pure business rules for seller performance evaluation and status transitions.

Locked requirements from docs/DESIGN.md:
- Weekly evaluation on Mondays using a trailing 60-day window.
- Minimum 15 lines required to alter status.
- Triggers: Late shipment rate (shipped > placed + 3 days / shipped lines)
           Dispute rate (disputes opened / delivered lines)
- States: ACTIVE, WATCHLIST, SUSPENDED.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Tuple

from src.marketplace_gen.config import GeneratorConfig


@dataclass
class SellerEvalState:
    """Tracks stateful counters across weekly evaluations for a single seller."""
    seller_id: str
    current_status: str
    consecutive_watchlist_evals: int = 0
    consecutive_clean_evals: int = 0
    suspended_since: Optional[date] = None
    reinstated_at: Optional[date] = None


@dataclass(frozen=True)
class StatusTransitionDecision:
    """Outcome of a weekly seller status evaluation."""
    previous_status: str
    new_status: str
    reason: str
    late_rate_bps: int
    dispute_rate_bps: int
    evaluated_lines_count: int
    has_transitioned: bool


def calculate_metric_bps(count: int, total: int) -> int:
    """Calculates integer basis points (1% = 100 bps) with standard rounding."""
    if total <= 0:
        return 0
    return (count * 10000 + total // 2) // total


def evaluate_seller_status(
    eval_state: SellerEvalState,
    eval_date: date,
    shipped_lines_count: int,
    late_shipped_lines_count: int,
    delivered_lines_count: int,
    disputes_count: int,
    config: GeneratorConfig,
) -> StatusTransitionDecision:
    """
    Pure decision function evaluating a seller's weekly metrics.
    
    Enforces allowed transitions only:
    - ACTIVE -> WATCHLIST (late >= 12% or dispute >= 9%)
    - ACTIVE -> SUSPENDED (late >= 20% or dispute >= 14%)
    - WATCHLIST -> SUSPENDED (late >= 20%, dispute >= 14%, or 2 consecutive watchlist evals)
    - WATCHLIST -> ACTIVE (2 consecutive clean evaluations)
    - SUSPENDED -> WATCHLIST (automatic after 30-day minimum suspension cooldown)
    """
    status = eval_state.current_status
    prev_status = status

    # 1. Suspended status check: 30-day minimum suspension cooldown
    if status == "SUSPENDED":
        if eval_state.suspended_since is not None:
            days_suspended = (eval_date - eval_state.suspended_since).days
            if days_suspended >= config.min_suspension_days:
                eval_state.current_status = "WATCHLIST"
                eval_state.consecutive_clean_evals = 0
                eval_state.consecutive_watchlist_evals = 0
                eval_state.suspended_since = None
                eval_state.reinstated_at = eval_date
                return StatusTransitionDecision(
                    previous_status="SUSPENDED",
                    new_status="WATCHLIST",
                    reason="SUSPENSION_COOLDOWN_EXPIRED_REINSTATED",
                    late_rate_bps=0,
                    dispute_rate_bps=0,
                    evaluated_lines_count=0,
                    has_transitioned=True,
                )
        # Still in suspension cooldown
        return StatusTransitionDecision(
            previous_status="SUSPENDED",
            new_status="SUSPENDED",
            reason="IN_SUSPENSION_COOLDOWN",
            late_rate_bps=0,
            dispute_rate_bps=0,
            evaluated_lines_count=0,
            has_transitioned=False,
        )

    # 2. Volume check: Minimum 15 lines required
    evaluated_lines = max(shipped_lines_count, delivered_lines_count)
    if evaluated_lines < config.eval_min_lines:
        return StatusTransitionDecision(
            previous_status=status,
            new_status=status,
            reason="BELOW_MINIMUM_LINE_VOLUME",
            late_rate_bps=0,
            dispute_rate_bps=0,
            evaluated_lines_count=evaluated_lines,
            has_transitioned=False,
        )

    # 3. Calculate metrics
    late_rate_bps = calculate_metric_bps(late_shipped_lines_count, shipped_lines_count)
    dispute_rate_bps = calculate_metric_bps(disputes_count, delivered_lines_count)

    is_suspension_breach = (
        late_rate_bps >= config.suspension_late_bps
        or dispute_rate_bps >= config.suspension_dispute_bps
    )
    is_watchlist_breach = (
        late_rate_bps >= config.watchlist_late_bps
        or dispute_rate_bps >= config.watchlist_dispute_bps
    )

    new_status = status
    reason = "MAINTAINED_STATUS"

    if status == "ACTIVE":
        if is_suspension_breach:
            new_status = "SUSPENDED"
            reason = "SEVERE_METRIC_BREACH"
            eval_state.suspended_since = eval_date
            eval_state.consecutive_watchlist_evals = 0
            eval_state.consecutive_clean_evals = 0
        elif is_watchlist_breach:
            new_status = "WATCHLIST"
            reason = "METRIC_BREACH_WATCHLIST"
            eval_state.consecutive_watchlist_evals = 1
            eval_state.consecutive_clean_evals = 0
        else:
            eval_state.consecutive_clean_evals += 1

    elif status == "WATCHLIST":
        if is_suspension_breach:
            new_status = "SUSPENDED"
            reason = "SEVERE_METRIC_BREACH_FROM_WATCHLIST"
            eval_state.suspended_since = eval_date
            eval_state.consecutive_watchlist_evals = 0
            eval_state.consecutive_clean_evals = 0
        elif is_watchlist_breach:
            eval_state.consecutive_watchlist_evals += 1
            eval_state.consecutive_clean_evals = 0
            # 2 consecutive watchlist evals trigger suspension
            if eval_state.consecutive_watchlist_evals >= 2:
                new_status = "SUSPENDED"
                reason = "CONSECUTIVE_WATCHLIST_BREACH"
                eval_state.suspended_since = eval_date
            else:
                reason = "WATCHLIST_BREACH_MAINTAINED"
        else:
            # Clean evaluation
            eval_state.consecutive_clean_evals += 1
            eval_state.consecutive_watchlist_evals = 0
            # 2 clean evals return to ACTIVE
            if eval_state.consecutive_clean_evals >= config.clean_evals_for_active:
                new_status = "ACTIVE"
                reason = "CONSECUTIVE_CLEAN_EVALS_RECOVERY"

    eval_state.current_status = new_status
    has_transitioned = (prev_status != new_status)

    return StatusTransitionDecision(
        previous_status=prev_status,
        new_status=new_status,
        reason=reason,
        late_rate_bps=late_rate_bps,
        dispute_rate_bps=dispute_rate_bps,
        evaluated_lines_count=evaluated_lines,
        has_transitioned=has_transitioned,
    )

