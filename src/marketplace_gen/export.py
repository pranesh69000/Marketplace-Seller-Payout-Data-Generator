"""
Streaming export engine for CSV, JSON, and SQLite / SQL seed scripts.

Ensures minimal memory footprint by streaming records directly to disk.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.marketplace_gen.ledger import SettlementSimulationBundle
from src.marketplace_gen.simulation.fulfillment import FulfillmentSimulationBundle
from src.marketplace_gen.simulation.master_data import MasterDataBundle
from src.marketplace_gen.simulation.orders import OrderSkeletonBundle


def format_val(val: Any) -> Any:
    """Formats datetime and date objects to standard ISO strings."""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return val


def stream_to_csv(filepath: str, headers: List[str], rows: Iterable[Dict[str, Any]]) -> int:
    """Streams rows to CSV with deterministic LF line endings."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    count = 0
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        for r in rows:
            formatted_row = {k: format_val(r.get(k)) for k in headers}
            writer.writerow(formatted_row)
            count += 1
    return count


def stream_to_json(filepath: str, rows: Iterable[Dict[str, Any]]) -> int:
    """Streams rows into an indented JSON array."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    count = 0
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("[\n")
        first = True
        for r in rows:
            formatted_row = {k: format_val(v) for k, v in r.items()}
            line = json.dumps(formatted_row, ensure_ascii=False)
            if not first:
                f.write(",\n")
            f.write(f"  {line}")
            first = False
            count += 1
        f.write("\n]\n")
    return count


# DDL schemas for SQLite & SQL seed file
SQL_DDL = """
-- Marketplace Schema DDL
CREATE TABLE IF NOT EXISTS sellers (
    seller_id TEXT PRIMARY KEY,
    business_name TEXT NOT NULL UNIQUE,
    contact_email TEXT NOT NULL UNIQUE,
    onboarded_at TEXT NOT NULL,
    status TEXT NOT NULL,
    status_updated_at TEXT NOT NULL,
    country TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS product_listings (
    listing_id TEXT PRIMARY KEY,
    seller_id TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    base_price_cents INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    deactivated_at TEXT,
    FOREIGN KEY (seller_id) REFERENCES sellers(seller_id)
);

CREATE TABLE IF NOT EXISTS commission_rules (
    rule_id TEXT PRIMARY KEY,
    rule_type TEXT NOT NULL,
    category TEXT NOT NULL,
    rate_bps INTEGER NOT NULL,
    priority INTEGER NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    order_status TEXT NOT NULL,
    total_gross_cents INTEGER NOT NULL,
    placed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_lines (
    order_line_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    seller_id TEXT NOT NULL,
    listing_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    total_gross_cents INTEGER NOT NULL,
    applied_rule_id TEXT NOT NULL,
    commission_rate_bps INTEGER NOT NULL,
    commission_cents INTEGER NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (seller_id) REFERENCES sellers(seller_id),
    FOREIGN KEY (listing_id) REFERENCES product_listings(listing_id),
    FOREIGN KEY (applied_rule_id) REFERENCES commission_rules(rule_id)
);

CREATE TABLE IF NOT EXISTS fulfillments (
    fulfillment_id TEXT PRIMARY KEY,
    order_line_id TEXT NOT NULL UNIQUE,
    carrier TEXT NOT NULL,
    tracking_number TEXT NOT NULL UNIQUE,
    fulfillment_status TEXT NOT NULL,
    shipped_at TEXT,
    delivered_at TEXT,
    returned_at TEXT,
    FOREIGN KEY (order_line_id) REFERENCES order_lines(order_line_id)
);

CREATE TABLE IF NOT EXISTS customer_reviews (
    review_id TEXT PRIMARY KEY,
    order_line_id TEXT NOT NULL UNIQUE,
    rating INTEGER NOT NULL,
    review_text TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (order_line_id) REFERENCES order_lines(order_line_id)
);

CREATE TABLE IF NOT EXISTS disputes (
    dispute_id TEXT PRIMARY KEY,
    order_line_id TEXT NOT NULL UNIQUE,
    dispute_type TEXT NOT NULL,
    dispute_status TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    opened_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (order_line_id) REFERENCES order_lines(order_line_id)
);

CREATE TABLE IF NOT EXISTS payouts (
    payout_id TEXT PRIMARY KEY,
    seller_id TEXT NOT NULL,
    cycle_date TEXT NOT NULL,
    total_cents INTEGER NOT NULL,
    status TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    FOREIGN KEY (seller_id) REFERENCES sellers(seller_id)
);

CREATE TABLE IF NOT EXISTS payout_lines (
    payout_line_id TEXT PRIMARY KEY,
    payout_id TEXT,
    seller_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    rule_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (payout_id) REFERENCES payouts(payout_id),
    FOREIGN KEY (seller_id) REFERENCES sellers(seller_id)
);

CREATE TABLE IF NOT EXISTS seller_commission_assignments (
    assignment_id TEXT PRIMARY KEY,
    seller_id TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    effective_from TEXT NOT NULL,
    effective_to TEXT,
    FOREIGN KEY (seller_id) REFERENCES sellers(seller_id),
    FOREIGN KEY (rule_id) REFERENCES commission_rules(rule_id)
);

CREATE TABLE IF NOT EXISTS seller_status_events (
    event_id TEXT PRIMARY KEY,
    seller_id TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    reason TEXT NOT NULL,
    snapshot_late_rate_bps INTEGER NOT NULL,
    snapshot_dispute_rate_bps INTEGER NOT NULL,
    evaluated_lines_count INTEGER NOT NULL,
    event_at TEXT NOT NULL,
    FOREIGN KEY (seller_id) REFERENCES sellers(seller_id)
);

CREATE TABLE IF NOT EXISTS fulfillment_events (
    event_id TEXT PRIMARY KEY,
    fulfillment_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL,
    FOREIGN KEY (fulfillment_id) REFERENCES fulfillments(fulfillment_id)
);

CREATE TABLE IF NOT EXISTS dispute_events (
    event_id TEXT PRIMARY KEY,
    dispute_id TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT,
    event_at TEXT NOT NULL,
    FOREIGN KEY (dispute_id) REFERENCES disputes(dispute_id)
);

CREATE TABLE IF NOT EXISTS payout_events (
    event_id TEXT PRIMARY KEY,
    payout_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_at TEXT NOT NULL,
    FOREIGN KEY (payout_id) REFERENCES payouts(payout_id)
);
"""


def export_all_tables(
    out_dir: str,
    master_data: MasterDataBundle,
    order_bundle: OrderSkeletonBundle,
    ful_bundle: FulfillmentSimulationBundle,
    settlement: SettlementSimulationBundle,
) -> Dict[str, int]:
    """
    Exports all 15 tables to CSV, JSON, and SQLite / SQL seed scripts.
    Returns row count dictionary per table.
    """
    csv_dir = os.path.join(out_dir, "csv")
    json_dir = os.path.join(out_dir, "json")
    os.makedirs(csv_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)

    counts: Dict[str, int] = {}

    # Define table generators and column definitions
    tables_def: List[Tuple[str, List[str], List[Dict[str, Any]]]] = [
        ("sellers", [
            "seller_id", "business_name", "contact_email", "onboarded_at",
            "status", "status_updated_at", "country"
        ], [
            {
                "seller_id": s.seller_id,
                "business_name": s.business_name,
                "contact_email": s.contact_email,
                "onboarded_at": s.onboarded_at,
                "status": settlement.seller_final_statuses.get(s.seller_id, s.status),
                "status_updated_at": s.status_updated_at,
                "country": s.country,
            }
            for s in master_data.sellers
        ]),
        ("product_listings", [
            "listing_id", "seller_id", "title", "category",
            "base_price_cents", "created_at", "deactivated_at"
        ], [
            {
                "listing_id": l.listing_id,
                "seller_id": l.seller_id,
                "title": l.title,
                "category": l.category,
                "base_price_cents": l.base_price_cents,
                "created_at": l.created_at,
                "deactivated_at": l.deactivated_at,
            }
            for l in master_data.listings
        ]),
        ("commission_rules", [
            "rule_id", "rule_type", "category", "rate_bps",
            "priority", "effective_from", "effective_to"
        ], [
            {
                "rule_id": r.rule_id,
                "rule_type": r.rule_type,
                "category": r.category,
                "rate_bps": r.rate_bps,
                "priority": r.priority,
                "effective_from": r.effective_from,
                "effective_to": r.effective_to,
            }
            for r in master_data.commission_rules
        ]),
        ("orders", [
            "order_id", "customer_id", "order_status",
            "total_gross_cents", "placed_at"
        ], [
            {
                "order_id": o.order_id,
                "customer_id": o.customer_id,
                "order_status": o.order_status,
                "total_gross_cents": o.total_gross_cents,
                "placed_at": o.placed_at,
            }
            for o in order_bundle.orders
        ]),
        ("order_lines", [
            "order_line_id", "order_id", "seller_id", "listing_id",
            "quantity", "unit_price_cents", "total_gross_cents",
            "applied_rule_id", "commission_rate_bps", "commission_cents"
        ], [
            {
                "order_line_id": ol.order_line_id,
                "order_id": ol.order_id,
                "seller_id": ol.seller_id,
                "listing_id": ol.listing_id,
                "quantity": ol.quantity,
                "unit_price_cents": ol.unit_price_cents,
                "total_gross_cents": ol.total_gross_cents,
                "applied_rule_id": ol.applied_rule_id,
                "commission_rate_bps": ol.commission_rate_bps,
                "commission_cents": ol.commission_cents,
            }
            for ol in order_bundle.lines
        ]),
        ("fulfillments", [
            "fulfillment_id", "order_line_id", "carrier", "tracking_number",
            "fulfillment_status", "shipped_at", "delivered_at", "returned_at"
        ], [
            {
                "fulfillment_id": f.fulfillment_id,
                "order_line_id": f.order_line_id,
                "carrier": f.carrier,
                "tracking_number": f.tracking_number,
                "fulfillment_status": f.fulfillment_status,
                "shipped_at": f.shipped_at,
                "delivered_at": f.delivered_at,
                "returned_at": f.returned_at,
            }
            for f in ful_bundle.fulfillments
        ]),
        ("customer_reviews", [
            "review_id", "order_line_id", "rating", "review_text", "created_at"
        ], [
            {
                "review_id": rv.review_id,
                "order_line_id": rv.order_line_id,
                "rating": rv.rating,
                "review_text": rv.review_text,
                "created_at": rv.created_at,
            }
            for rv in ful_bundle.reviews
        ]),
        ("disputes", [
            "dispute_id", "order_line_id", "dispute_type", "dispute_status",
            "amount_cents", "opened_at", "resolved_at"
        ], [
            {
                "dispute_id": d.dispute_id,
                "order_line_id": d.order_line_id,
                "dispute_type": d.dispute_type,
                "dispute_status": d.dispute_status,
                "amount_cents": d.amount_cents,
                "opened_at": d.opened_at,
                "resolved_at": d.resolved_at,
            }
            for d in ful_bundle.disputes
        ]),
        ("payouts", [
            "payout_id", "seller_id", "cycle_date", "total_cents",
            "status", "generated_at"
        ], [
            {
                "payout_id": p.payout_id,
                "seller_id": p.seller_id,
                "cycle_date": p.cycle_date,
                "total_cents": p.total_cents,
                "status": p.status,
                "generated_at": p.generated_at,
            }
            for p in settlement.payouts
        ]),
        ("payout_lines", [
            "payout_line_id", "payout_id", "seller_id", "source_type",
            "source_id", "entry_type", "amount_cents", "rule_id", "created_at"
        ], [
            {
                "payout_line_id": pl.payout_line_id,
                "payout_id": pl.payout_id,
                "seller_id": pl.seller_id,
                "source_type": pl.source_type,
                "source_id": pl.source_id,
                "entry_type": pl.entry_type,
                "amount_cents": pl.amount_cents,
                "rule_id": pl.rule_id,
                "created_at": pl.created_at,
            }
            for pl in settlement.payout_lines
        ]),
        ("seller_commission_assignments", [
            "assignment_id", "seller_id", "rule_id", "effective_from", "effective_to"
        ], [
            {
                "assignment_id": a.assignment_id,
                "seller_id": a.seller_id,
                "rule_id": a.rule_id,
                "effective_from": a.effective_from,
                "effective_to": a.effective_to,
            }
            for a in master_data.assignments
        ]),
        ("seller_status_events", [
            "event_id", "seller_id", "previous_status", "new_status", "reason",
            "snapshot_late_rate_bps", "snapshot_dispute_rate_bps", "evaluated_lines_count", "event_at"
        ], [
            {
                "event_id": se.event_id,
                "seller_id": se.seller_id,
                "previous_status": se.previous_status,
                "new_status": se.new_status,
                "reason": se.reason,
                "snapshot_late_rate_bps": se.snapshot_late_rate_bps,
                "snapshot_dispute_rate_bps": se.snapshot_dispute_rate_bps,
                "evaluated_lines_count": se.evaluated_lines_count,
                "event_at": se.event_at,
            }
            for se in settlement.seller_status_events
        ]),
        ("fulfillment_events", [
            "event_id", "fulfillment_id", "event_type", "event_at"
        ], [
            {
                "event_id": fe.event_id,
                "fulfillment_id": fe.fulfillment_id,
                "event_type": fe.event_type,
                "event_at": fe.event_at,
            }
            for fe in ful_bundle.fulfillment_events
        ]),
        ("dispute_events", [
            "event_id", "dispute_id", "status", "notes", "event_at"
        ], [
            {
                "event_id": de.event_id,
                "dispute_id": de.dispute_id,
                "status": de.status,
                "notes": de.notes,
                "event_at": de.event_at,
            }
            for de in ful_bundle.dispute_events
        ]),
        ("payout_events", [
            "event_id", "payout_id", "event_type", "event_at"
        ], [
            {
                "event_id": pe.event_id,
                "payout_id": pe.payout_id,
                "event_type": pe.event_type,
                "event_at": pe.event_at,
            }
            for pe in settlement.payout_events
        ]),
    ]

    # Initialize SQLite database
    db_path = os.path.join(out_dir, "marketplace.db")
    sql_seed_path = os.path.join(out_dir, "seed.sql")

    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(SQL_DDL)

    with open(sql_seed_path, "w", encoding="utf-8") as sql_f:
        sql_f.write(SQL_DDL)
        sql_f.write("\n-- Data Inserts\nBEGIN TRANSACTION;\n")

        for table_name, headers, rows in tables_def:
            csv_file = os.path.join(csv_dir, f"{table_name}.csv")
            json_file = os.path.join(json_dir, f"{table_name}.json")

            row_count = stream_to_csv(csv_file, headers, rows)
            stream_to_json(json_file, rows)
            counts[table_name] = row_count

            # SQLite batch insert & seed.sql dump
            placeholders = ", ".join(["?"] * len(headers))
            cols = ", ".join(headers)
            sql_insert = f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})"

            sqlite_batch = []
            for r in rows:
                row_tuple = tuple(format_val(r.get(h)) for h in headers)
                sqlite_batch.append(row_tuple)

                # Write formatted SQL literal insert
                val_strs = []
                for val in row_tuple:
                    if val is None:
                        val_strs.append("NULL")
                    elif isinstance(val, (int, float)):
                        val_strs.append(str(val))
                    else:
                        escaped = str(val).replace("'", "''")
                        val_strs.append(f"'{escaped}'")
                sql_f.write(f"INSERT INTO {table_name} ({cols}) VALUES ({', '.join(val_strs)});\n")

            if sqlite_batch:
                cur.executemany(sql_insert, sqlite_batch)

        sql_f.write("COMMIT;\n")

    conn.commit()
    conn.close()

    return counts

