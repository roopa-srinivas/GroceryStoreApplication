"""Manager reports, written as plain SQL so the queries are easy to read
(the reports page shows them). They run unchanged on MySQL and SQLite."""

from datetime import timedelta

from sqlalchemy import DateTime, bindparam, text

from .models import utcnow

LOW_STOCK = """
SELECT p.id, p.name, p.emoji, p.stock_qty, p.low_stock_at, c.name AS category
FROM products p
JOIN categories c ON c.id = p.category_id
WHERE p.is_active = :active
  AND p.stock_qty <= p.low_stock_at
ORDER BY p.stock_qty ASC, p.name
""".strip()

# Revenue uses the price paid (order_items.unit_price_cents), not today's price.
REVENUE_BY_CATEGORY = """
SELECT c.name AS category,
       SUM(oi.qty) AS units,
       SUM(oi.qty * oi.unit_price_cents) AS revenue_cents
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
JOIN categories c ON c.id = p.category_id
WHERE o.status <> 'cancelled'
  AND o.created_at >= :since
GROUP BY c.name
ORDER BY revenue_cents DESC
""".strip()

TOP_PRODUCTS = """
SELECT p.name, p.emoji,
       SUM(oi.qty) AS units,
       SUM(oi.qty * oi.unit_price_cents) AS revenue_cents
FROM order_items oi
JOIN orders o ON o.id = oi.order_id
JOIN products p ON p.id = oi.product_id
WHERE o.status <> 'cancelled'
  AND o.created_at >= :since
GROUP BY p.id, p.name, p.emoji
ORDER BY units DESC, revenue_cents DESC
LIMIT 5
""".strip()

ORDERS_BY_STATUS = """
SELECT status, COUNT(*) AS orders
FROM orders
GROUP BY status
""".strip()

QUERIES = {
    "low_stock": LOW_STOCK,
    "revenue_by_category": REVENUE_BY_CATEGORY,
    "top_products": TOP_PRODUCTS,
    "orders_by_status": ORDERS_BY_STATUS,
}


def _rows(session, sql, **params):
    statement = text(sql)
    if "since" in params:
        # Typed, so each database driver gets the date in its own format.
        statement = statement.bindparams(bindparam("since", type_=DateTime))
    return [dict(row._mapping) for row in session.execute(statement, params)]


def run_all(session, days=7):
    since = utcnow() - timedelta(days=days)
    return {
        "days": days,
        "low_stock": _rows(session, LOW_STOCK, active=True),
        "revenue_by_category": [
            {**r, "units": int(r["units"]), "revenue_cents": int(r["revenue_cents"])}
            for r in _rows(session, REVENUE_BY_CATEGORY, since=since)
        ],
        "top_products": [
            {**r, "units": int(r["units"]), "revenue_cents": int(r["revenue_cents"])}
            for r in _rows(session, TOP_PRODUCTS, since=since)
        ],
        "orders_by_status": {r["status"]: int(r["orders"]) for r in _rows(session, ORDERS_BY_STATUS)},
        "sql": QUERIES,
    }
