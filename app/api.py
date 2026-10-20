"""The JSON API the storefront and manager pages use.

The manager endpoints have no login: this is a portfolio demo. A real
deployment would put them behind staff accounts.
"""

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select, update

from . import reports
from .db import session
from .models import Category, Order, Product
from .orders import OrderError, place_order, set_status

api = Blueprint("api", __name__)

SORTS = {
    "name": Product.name.asc(),
    "price_asc": Product.price_cents.asc(),
    "price_desc": Product.price_cents.desc(),
    "stock": Product.stock_qty.asc(),
}


@api.errorhandler(OrderError)
def _order_error(error):
    return jsonify(error=error.message, **error.details), error.status


def _bad_request(message):
    return jsonify(error=message), 400


def product_json(p):
    return {
        "id": p.id,
        "sku": p.sku,
        "name": p.name,
        "emoji": p.emoji,
        "category": p.category.name,
        "category_id": p.category_id,
        "price_cents": p.price_cents,
        "stock_qty": p.stock_qty,
        "low_stock_at": p.low_stock_at,
        "status": "out" if p.stock_qty == 0 else "low" if p.stock_qty <= p.low_stock_at else "ok",
        "is_active": p.is_active,
    }


def order_json(o):
    return {
        "id": o.id,
        "status": o.status,
        "total_cents": o.total_cents,
        "created_at": o.created_at.isoformat() + "Z",
        "customer": {"name": o.customer.name, "email": o.customer.email},
        "items": [
            {"product_id": i.product_id, "name": i.product.name, "qty": i.qty, "unit_price_cents": i.unit_price_cents}
            for i in o.items
        ],
    }


def _int_arg(name, default=None, minimum=None):
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    value = int(raw)
    if minimum is not None and value < minimum:
        raise ValueError
    return value


@api.get("/categories")
def categories():
    rows = session().scalars(select(Category).order_by(Category.name))
    return jsonify([{"id": c.id, "name": c.name} for c in rows])


@api.get("/products")
def products():
    """Search the catalog: ?q=, category=, min_price=, max_price= (cents),
    in_stock=1, include_inactive=1, sort=name|price_asc|price_desc|stock."""
    try:
        category = _int_arg("category")
        min_price = _int_arg("min_price", minimum=0)
        max_price = _int_arg("max_price", minimum=0)
    except ValueError:
        return _bad_request("category, min_price and max_price must be whole numbers.")
    sort = request.args.get("sort", "name")
    if sort not in SORTS:
        return _bad_request(f"sort must be one of: {', '.join(SORTS)}.")

    query = select(Product)
    if request.args.get("include_inactive") != "1":
        query = query.where(Product.is_active.is_(True))
    if q := request.args.get("q", "").strip():
        # autoescape: a search for "50%" means the characters, not a wildcard.
        query = query.where(Product.name.icontains(q, autoescape=True))
    if category is not None:
        query = query.where(Product.category_id == category)
    if min_price is not None:
        query = query.where(Product.price_cents >= min_price)
    if max_price is not None:
        query = query.where(Product.price_cents <= max_price)
    if request.args.get("in_stock") == "1":
        query = query.where(Product.stock_qty > 0)
    rows = session().scalars(query.order_by(SORTS[sort], Product.id))
    return jsonify([product_json(p) for p in rows])


@api.post("/products")
def create_product():
    body = request.get_json(silent=True) or {}
    try:
        product = Product(
            sku=str(body["sku"]).strip().upper(),
            name=str(body["name"]).strip(),
            category_id=int(body["category_id"]),
            price_cents=int(body["price_cents"]),
            stock_qty=int(body.get("stock_qty", 0)),
            low_stock_at=int(body.get("low_stock_at", 10)),
            emoji=str(body.get("emoji") or "🛒")[:16],
        )
    except (KeyError, TypeError, ValueError):
        return _bad_request("sku, name, category_id and price_cents are required.")
    if not product.sku or not product.name or product.price_cents <= 0 or product.stock_qty < 0:
        return _bad_request("Check the name, SKU, price and stock.")
    db = session()
    if db.get(Category, product.category_id) is None:
        return _bad_request("No such category.")
    if db.scalar(select(func.count()).select_from(Product).where(Product.sku == product.sku)):
        return jsonify(error="That SKU is already used."), 409
    db.add(product)
    db.commit()
    return jsonify(product_json(product)), 201


@api.patch("/products/<int:product_id>")
def edit_product(product_id):
    """Change price, low-stock level, name, or retire/restore a product."""
    db = session()
    product = db.get(Product, product_id)
    if product is None:
        return jsonify(error="No such product."), 404
    body = request.get_json(silent=True) or {}
    try:
        if "name" in body:
            product.name = str(body["name"]).strip() or product.name
        if "price_cents" in body:
            if int(body["price_cents"]) <= 0:
                raise ValueError
            product.price_cents = int(body["price_cents"])
        if "low_stock_at" in body:
            product.low_stock_at = max(0, int(body["low_stock_at"]))
        if "is_active" in body:
            product.is_active = bool(body["is_active"])
    except (TypeError, ValueError):
        db.rollback()
        return _bad_request("price_cents must be a positive whole number of cents.")
    db.commit()
    return jsonify(product_json(product))


@api.post("/products/<int:product_id>/restock")
def restock(product_id):
    """Adds delivered stock. Done as stock_qty + n in SQL, so it can't
    overwrite a sale that happened at the same moment."""
    body = request.get_json(silent=True) or {}
    try:
        qty = int(body["qty"])
    except (KeyError, TypeError, ValueError):
        return _bad_request("qty is required.")
    if not 1 <= qty <= 10_000:
        return _bad_request("Restock between 1 and 10,000 units.")
    db = session()

    result = db.execute(
        update(Product).where(Product.id == product_id).values(stock_qty=Product.stock_qty + qty).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        return jsonify(error="No such product."), 404
    db.commit()
    return jsonify(product_json(db.get(Product, product_id, populate_existing=True)))


@api.post("/orders")
def create_order():
    body = request.get_json(silent=True) or {}
    customer = body.get("customer") or {}
    order = place_order(session(), customer.get("name"), customer.get("email"), body.get("items"))
    return jsonify(order_json(order)), 201


@api.get("/orders")
def list_orders():
    status = request.args.get("status")
    query = select(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(200)
    if status:
        query = query.where(Order.status == status)
    return jsonify([order_json(o) for o in session().scalars(query)])


@api.patch("/orders/<int:order_id>")
def update_order(order_id):
    body = request.get_json(silent=True) or {}
    order = set_status(session(), order_id, str(body.get("status", "")))
    return jsonify(order_json(order))


@api.get("/reports")
def all_reports():
    try:
        days = _int_arg("days", default=7, minimum=1)
    except ValueError:
        return _bad_request("days must be a positive whole number.")
    return jsonify(reports.run_all(session(), days=min(days, 365)))
