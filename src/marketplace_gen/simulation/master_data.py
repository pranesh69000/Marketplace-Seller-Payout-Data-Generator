"""
Master data generator: Commission Rules, Sellers, Listings, and Commission Assignments.

Generates deterministic foundation entities using explicit NumPy Generator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np

from src.marketplace_gen.config import GeneratorConfig
from src.marketplace_gen.ids import IdGenerator
from src.marketplace_gen.rules.commission import (
    CommissionRuleRecord,
    SellerCommissionAssignmentRecord,
)


# Deterministic business name wordlists (no external faker dependency)
ADJECTIVES = (
    "Apex", "Aurora", "Beacon", "BlueSky", "Cascade", "Cedar", "Cobalt", "Crest",
    "Echo", "Falcon", "Granite", "Haven", "Horizon", "Ironclad", "Keystone",
    "Liberty", "Lunar", "Matrix", "Nexus", "NorthStar", "Nova", "Omega", "Onyx",
    "Orbit", "Peak", "Pinnacle", "Polaris", "Prism", "Quantum", "Radiant",
    "Redwood", "Sierra", "Silverline", "Summit", "Titan", "Vanguard", "Vortex",
    "Zenith", "Zephyr"
)

NOUNS = (
    "Enterprises", "Trading", "Goods", "Supply", "Direct", "Market", "Retail",
    "Commerce", "Merchants", "Brands", "Ventures", "Logistics", "Outdoors",
    "Collective", "Essentials", "Studio", "Works", "Hub", "Depot", "Exchange"
)

PRODUCT_NOUNS = {
    "ELECTRONICS": ("Wireless Earbuds", "Smart Watch", "USB-C Hub", "Noise Cancelling Headphones", "Portable Charger", "4K Webcam", "Mechanical Keyboard", "Bluetooth Speaker"),
    "APPAREL": ("Cotton T-Shirt", "Slim Fit Denim", "Fleece Hoodie", "Waterproof Jacket", "Athletic Socks", "Merino Wool Sweater", "Classic Polo", "Running Shorts"),
    "HOME_KITCHEN": ("Stainless Steel Skillet", "Chef Knife 8-Inch", "Coffee Maker", "Silicone Spatula Set", "Bamboo Cutting Board", "Ceramic Dinner Plates", "Blender", "Toaster"),
    "BEAUTY": ("Moisturizing Cream", "Vitamin C Serum", "Facial Cleanser", "Hydrating Toner", "Sunscreen SPF 50", "Exfoliating Scrub", "Organic Lip Balm", "Clay Mask"),
    "SPORTS": ("Yoga Mat 6mm", "Resistance Bands Set", "Dumbbell Set 15lb", "Hydration Water Bottle", "Foam Roller", "Cycling Gloves", "Speed Jump Rope", "Trail Backpack"),
    "BOOKS": ("Programming Guide", "Historical Novel", "Cookbook Recipes", "Science Fiction Anthology", "Economics Explained", "Mindset Psychology", "World Atlas", "Art of Design"),
}


@dataclass
class SellerInternal:
    """Internal representation of a seller including hidden simulation properties."""
    seller_id: str
    business_name: str
    contact_email: str
    onboarded_at: datetime
    status: str
    status_updated_at: datetime
    country: str
    quality_tier: str  # Hidden attribute: 'GOOD', 'AVERAGE', 'POOR'


@dataclass
class ProductListingRecord:
    """Product listing catalog record."""
    listing_id: str
    seller_id: str
    title: str
    category: str
    base_price_cents: int
    created_at: datetime
    deactivated_at: Optional[datetime] = None


@dataclass
class MasterDataBundle:
    """Encapsulates all generated master data entities."""
    commission_rules: List[CommissionRuleRecord]
    rules_by_id: Dict[str, CommissionRuleRecord]
    sellers: List[SellerInternal]
    sellers_by_id: Dict[str, SellerInternal]
    listings: List[ProductListingRecord]
    listings_by_id: Dict[str, ProductListingRecord]
    listings_by_seller: Dict[str, List[ProductListingRecord]]
    assignments: List[SellerCommissionAssignmentRecord]
    assignments_by_seller: Dict[str, List[str]]  # seller_id -> List[rule_id]


def generate_commission_rules(id_gen: IdGenerator) -> Tuple[List[CommissionRuleRecord], Dict[str, CommissionRuleRecord]]:
    """
    Creates the locked commission rules schedule.
    
    Includes category rates and the mid-year ELECTRONICS rate change (2026-07-01),
    plus the NEW_SELLER_PROMO rule.
    """
    rules: List[CommissionRuleRecord] = [
        # ELECTRONICS: Rate change on 2026-07-01 from 800 bps to 950 bps
        CommissionRuleRecord(
            rule_id=id_gen.next_commission_rule_id(),  # RULE-0001
            rule_type="STANDARD",
            category="ELECTRONICS",
            rate_bps=800,
            priority=10,
            effective_from=date(2025, 1, 1),
            effective_to=date(2026, 6, 30),
        ),
        CommissionRuleRecord(
            rule_id=id_gen.next_commission_rule_id(),  # RULE-0002
            rule_type="STANDARD",
            category="ELECTRONICS",
            rate_bps=950,
            priority=10,
            effective_from=date(2026, 7, 1),
            effective_to=None,
        ),
        # APPAREL: 12.00%
        CommissionRuleRecord(
            rule_id=id_gen.next_commission_rule_id(),  # RULE-0003
            rule_type="STANDARD",
            category="APPAREL",
            rate_bps=1200,
            priority=10,
            effective_from=date(2025, 1, 1),
            effective_to=None,
        ),
        # HOME_KITCHEN: 10.00%
        CommissionRuleRecord(
            rule_id=id_gen.next_commission_rule_id(),  # RULE-0004
            rule_type="STANDARD",
            category="HOME_KITCHEN",
            rate_bps=1000,
            priority=10,
            effective_from=date(2025, 1, 1),
            effective_to=None,
        ),
        # BEAUTY: 11.00%
        CommissionRuleRecord(
            rule_id=id_gen.next_commission_rule_id(),  # RULE-0005
            rule_type="STANDARD",
            category="BEAUTY",
            rate_bps=1100,
            priority=10,
            effective_from=date(2025, 1, 1),
            effective_to=None,
        ),
        # SPORTS: 9.00%
        CommissionRuleRecord(
            rule_id=id_gen.next_commission_rule_id(),  # RULE-0006
            rule_type="STANDARD",
            category="SPORTS",
            rate_bps=900,
            priority=10,
            effective_from=date(2025, 1, 1),
            effective_to=None,
        ),
        # BOOKS: 6.00%
        CommissionRuleRecord(
            rule_id=id_gen.next_commission_rule_id(),  # RULE-0007
            rule_type="STANDARD",
            category="BOOKS",
            rate_bps=600,
            priority=10,
            effective_from=date(2025, 1, 1),
            effective_to=None,
        ),
        # NEW_SELLER_PROMO: 5.00% across ALL categories with higher priority (50)
        CommissionRuleRecord(
            rule_id=id_gen.next_commission_rule_id(),  # RULE-0008
            rule_type="NEW_SELLER_PROMO",
            category="ALL",
            rate_bps=500,
            priority=50,
            effective_from=date(2026, 1, 1),
            effective_to=None,
        ),
    ]
    rules_by_id = {r.rule_id: r for r in rules}
    return rules, rules_by_id


def generate_master_data(config: GeneratorConfig, rng: np.random.Generator, id_gen: IdGenerator) -> MasterDataBundle:
    """Generates all master data records deterministically."""
    # 1. Commission Rules
    rules, rules_by_id = generate_commission_rules(id_gen)
    promo_rule = [r for r in rules if r.rule_type == "NEW_SELLER_PROMO"][0]
    standard_rule_ids = [r.rule_id for r in rules if r.rule_type == "STANDARD"]

    # 2. Sellers & Hidden Quality Tiers
    sellers_count = config.scaled_sellers_count
    tier_names = [t[0] for t in config.seller_tier_distribution]
    tier_probs = [t[1] for t in config.seller_tier_distribution]

    # Assign quality tiers deterministically
    assigned_tiers = rng.choice(tier_names, size=sellers_count, p=tier_probs)

    # Onboarding dates: Between 2025-06-01 and 2026-09-30 (total ~486 days)
    onboard_start_dt = datetime(2025, 6, 1, 8, 0, 0)
    total_onboard_days = (datetime(2026, 9, 30, 18, 0, 0) - onboard_start_dt).days

    # Skew onboarding so ~40% joined in 2025 and ~60% joined during 2026
    raw_onboard_days = rng.integers(0, total_onboard_days + 1, size=sellers_count)
    raw_onboard_seconds = rng.integers(0, 86400, size=sellers_count)

    sellers: List[SellerInternal] = []
    sellers_by_id: Dict[str, SellerInternal] = {}
    assignments: List[SellerCommissionAssignmentRecord] = []
    assignments_by_seller: Dict[str, List[str]] = {}

    for i in range(sellers_count):
        s_id = id_gen.next_seller_id()
        tier = str(assigned_tiers[i])
        onboard_dt = onboard_start_dt + timedelta(
            days=int(raw_onboard_days[i]),
            seconds=int(raw_onboard_seconds[i]),
        )

        adj = ADJECTIVES[rng.integers(0, len(ADJECTIVES))]
        noun = NOUNS[rng.integers(0, len(NOUNS))]
        seq_num = int(s_id.split("-")[1])
        b_name = f"{adj} {noun} {seq_num:04d}"
        clean_slug = f"{adj.lower()}{noun.lower()}-{seq_num:04d}"
        email = f"contact@{clean_slug}.example.com"

        seller = SellerInternal(
            seller_id=s_id,
            business_name=b_name,
            contact_email=email,
            onboarded_at=onboard_dt,
            status="ACTIVE",
            status_updated_at=onboard_dt,
            country="US",
            quality_tier=tier,
        )
        sellers.append(seller)
        sellers_by_id[s_id] = seller

        # Create Commission Assignments
        # Standard rules are assigned for all categories from onboard date
        assigned_rules_for_this_seller: List[str] = []
        for r_id in standard_rule_ids:
            asgn = SellerCommissionAssignmentRecord(
                assignment_id=id_gen.next_assignment_id(),
                seller_id=s_id,
                rule_id=r_id,
                effective_from=onboard_dt.date(),
                effective_to=None,
            )
            assignments.append(asgn)
            assigned_rules_for_this_seller.append(r_id)

        # Promo rule: If onboarded in 2026, eligible for promo for first 90 days
        if onboard_dt.date() >= date(2026, 1, 1):
            promo_end = onboard_dt.date() + timedelta(days=90)
            promo_asgn = SellerCommissionAssignmentRecord(
                assignment_id=id_gen.next_assignment_id(),
                seller_id=s_id,
                rule_id=promo_rule.rule_id,
                effective_from=onboard_dt.date(),
                effective_to=promo_end,
            )
            assignments.append(promo_asgn)
            assigned_rules_for_this_seller.append(promo_rule.rule_id)

        assignments_by_seller[s_id] = assigned_rules_for_this_seller

    # 3. Product Listings
    # Target average ~10 listings per seller (min 2, max 35)
    listing_counts = np.clip(rng.negative_binomial(5, 5 / 15, size=sellers_count), 2, 35)
    
    category_price_params = {
        # (mu, sigma) for lognormal distribution in cents
        "ELECTRONICS": (8.8, 0.7),     # ~$66 mean, range $20 - $500
        "APPAREL": (8.0, 0.5),         # ~$30 mean, range $12 - $120
        "HOME_KITCHEN": (8.3, 0.6),    # ~$40 mean, range $15 - $200
        "BEAUTY": (7.6, 0.5),          # ~$20 mean, range $8 - $80
        "SPORTS": (8.4, 0.6),          # ~$45 mean, range $15 - $250
        "BOOKS": (7.3, 0.4),           # ~$15 mean, range $6 - $50
    }

    listings: List[ProductListingRecord] = []
    listings_by_id: Dict[str, ProductListingRecord] = {}
    listings_by_seller: Dict[str, List[ProductListingRecord]] = {}

    for s_idx, seller in enumerate(sellers):
        num_listings = int(listing_counts[s_idx])
        seller_listings: List[ProductListingRecord] = []
        
        # Primary and secondary categories for this seller
        seller_cats = rng.choice(config.categories, size=min(2, len(config.categories)), replace=False)

        for _ in range(num_listings):
            list_id = id_gen.next_listing_id(seller.seller_id)
            cat = str(rng.choice(seller_cats))
            prod_name = PRODUCT_NOUNS[cat][rng.integers(0, len(PRODUCT_NOUNS[cat]))]
            adj = ADJECTIVES[rng.integers(0, len(ADJECTIVES))]
            title = f"{adj} {prod_name}"

            # Calculate price in integer cents (lognormal)
            mu, sigma = category_price_params[cat]
            price_dollars = rng.lognormal(mu - 4.605, sigma)  # shift for dollar scale
            price_cents = max(100, int(round(price_dollars * 100)))

            # Initial catalog listing created upon seller onboarding (within 24 hours)
            created_dt = seller.onboarded_at + timedelta(
                hours=int(rng.integers(1, 24)),
                minutes=int(rng.integers(0, 60)),
            )

            rec = ProductListingRecord(
                listing_id=list_id,
                seller_id=seller.seller_id,
                title=title,
                category=cat,
                base_price_cents=price_cents,
                created_at=created_dt,
                deactivated_at=None,
            )
            listings.append(rec)
            listings_by_id[list_id] = rec
            seller_listings.append(rec)

        listings_by_seller[seller.seller_id] = seller_listings

    return MasterDataBundle(
        commission_rules=rules,
        rules_by_id=rules_by_id,
        sellers=sellers,
        sellers_by_id=sellers_by_id,
        listings=listings,
        listings_by_id=listings_by_id,
        listings_by_seller=listings_by_seller,
        assignments=assignments,
        assignments_by_seller=assignments_by_seller,
    )

