-- =====================================================================
-- verification_queries.sql
-- Standalone cross-check SQL queries executed against marketplace.db
-- =====================================================================

-- 1. Payout Arithmetic Identity: Total Payout Amount vs Sum of Child Ledger Lines
-- Expected: 0 rows returned where total_cents != sum_lines (on clean baseline)
SELECT 
    p.payout_id,
    p.seller_id,
    p.cycle_date,
    p.total_cents AS declared_total,
    COALESCE(SUM(pl.amount_cents), 0) AS computed_sum,
    p.total_cents - COALESCE(SUM(pl.amount_cents), 0) AS discrepancy
FROM payouts p
LEFT JOIN payout_lines pl ON p.payout_id = pl.payout_id
GROUP BY p.payout_id
HAVING discrepancy != 0;

-- 2. Seller Late Shipment Rate Calculation (Trailing 60-Day Window Example)
-- Calculates late rate for shipped lines per seller
SELECT 
    ol.seller_id,
    COUNT(f.fulfillment_id) AS total_shipped_lines,
    SUM(CASE WHEN f.fulfillment_status != 'CANCELLED' AND DATE(f.shipped_at) > DATE(ol.placed_at, '+3 days') THEN 1 ELSE 0 END) AS late_shipped_lines,
    ROUND(CAST(SUM(CASE WHEN DATE(f.shipped_at) > DATE(ol.placed_at, '+3 days') THEN 1 ELSE 0 END) AS FLOAT) / COUNT(f.fulfillment_id) * 100, 2) AS late_shipment_pct
FROM order_lines ol
JOIN fulfillments f ON ol.order_line_id = f.order_line_id
WHERE f.shipped_at IS NOT NULL
GROUP BY ol.seller_id
ORDER BY late_shipment_pct DESC;

-- 3. Seller Dispute Rate Calculation
-- Calculates percentage of delivered lines that had customer disputes
SELECT 
    ol.seller_id,
    COUNT(DISTINCT CASE WHEN f.delivered_at IS NOT NULL THEN ol.order_line_id END) AS delivered_lines,
    COUNT(DISTINCT d.dispute_id) AS total_disputes,
    ROUND(CAST(COUNT(DISTINCT d.dispute_id) AS FLOAT) / 
          NULLIF(COUNT(DISTINCT CASE WHEN f.delivered_at IS NOT NULL THEN ol.order_line_id END), 0) * 100, 2) AS dispute_pct
FROM order_lines ol
JOIN fulfillments f ON ol.order_line_id = f.order_line_id
LEFT JOIN disputes d ON ol.order_line_id = d.order_line_id
GROUP BY ol.seller_id
HAVING delivered_lines >= 15
ORDER BY dispute_pct DESC;

-- 4. Order Line Financial Reconciliation
-- Verifies gross - commission matches net line proceeds
SELECT 
    ol.order_line_id,
    ol.total_gross_cents,
    ol.commission_cents,
    ol.total_gross_cents - ol.commission_cents AS expected_net_proceeds,
    SUM(CASE WHEN pl.entry_type = 'SALE' THEN pl.amount_cents ELSE 0 END) AS ledger_sale,
    SUM(CASE WHEN pl.entry_type = 'COMMISSION' THEN pl.amount_cents ELSE 0 END) AS ledger_commission
FROM order_lines ol
JOIN payout_lines pl ON ol.order_line_id = pl.source_id
WHERE pl.source_type = 'ORDER_LINE'
GROUP BY ol.order_line_id
LIMIT 20;

-- 5. Audit Trail Verification: Seller Status Event Snapshot Reconciliation
-- Cross-checks whether snapshot metric values align with state transition reasons
SELECT 
    event_id,
    seller_id,
    previous_status,
    new_status,
    reason,
    snapshot_late_rate_bps / 100.0 AS snapshot_late_rate_pct,
    snapshot_dispute_rate_bps / 100.0 AS snapshot_dispute_rate_pct,
    evaluated_lines_count,
    event_at
FROM seller_status_events
ORDER BY event_at;

-- 6. Check for Disallowed Listings Created During Suspension
SELECT 
    l.listing_id,
    l.seller_id,
    l.title,
    l.created_at,
    se.event_at AS suspended_at
FROM product_listings l
JOIN seller_status_events se ON l.seller_id = se.seller_id AND se.new_status = 'SUSPENDED'
WHERE l.created_at >= se.event_at;

