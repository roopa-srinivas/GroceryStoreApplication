"""Placing orders and moving them through their statuses."""

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .models import Customer, Order, OrderItem, Product

MAX_QTY_PER_LINE = 99

# Allowed status changes. Cancelling puts the items back on the shelf.
NEXT_STATUS = {
    "processing": {"shipped", "cancelled"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


class OrderError(Exception):
    def __init__(self, message, status=400, details=None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.details = details or {}


def _quantities(items):
    """{product_id: qty} from the request's lines, merging repeats."""
    if not isinstance(items, list) or not items:
        raise OrderError("An order needs at least one item.")
    lines = {}
    for item in items:
        try:
            product_id, qty = int(item["product_id"]), int(item["qty"])
        except (KeyError, TypeError, ValueError):
            raise OrderError("Each item needs a product_id and a qty.") from None
        if qty < 1:
            raise OrderError("Quantities must be at least 1.")
        lines[product_id] = lines.get(product_id, 0) + qty
        if lines[product_id] > MAX_QTY_PER_LINE:
            raise OrderError(f"At most {MAX_QTY_PER_LINE} of one product per order.")
    return lines


def place_order(session, customer_name, email, items):
    """Takes the stock and records the order in one transaction.

    Each product's stock drops only if enough is left, in the same UPDATE
    that checks it (`... WHERE stock_qty >= qty`). That is atomic in the
    database, so two shoppers racing for the last carton can't both get it:
    one UPDATE matches the row, the other matches nothing and the whole order
    rolls back. Rows are updated in id order so two orders for the same
    products can't deadlock each other.
    """
    customer_name = (customer_name or "").strip()
    email = (email or "").strip().lower()
    if not customer_name or "@" not in email:
        raise OrderError("A name and an email address are required.")
    lines = _quantities(items)

    try:
        short = []
        for product_id in sorted(lines):
            result = session.execute(
                update(Product)
                .where(Product.id == product_id, Product.is_active.is_(True), Product.stock_qty >= lines[product_id])
                .values(stock_qty=Product.stock_qty - lines[product_id])
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                short.append(product_id)
        if short:
            raise OrderError("Some items don't have enough stock.", status=409, details={"short": short})

        products = {p.id: p for p in session.scalars(select(Product).where(Product.id.in_(lines)))}
        customer = session.scalar(select(Customer).where(Customer.email == email))
        if customer is None:
            customer = Customer(name=customer_name, email=email)
            session.add(customer)
        order = Order(
            customer=customer,
            items=[OrderItem(product_id=pid, qty=qty, unit_price_cents=products[pid].price_cents) for pid, qty in lines.items()],
            total_cents=sum(products[pid].price_cents * qty for pid, qty in lines.items()),
        )
        session.add(order)
        session.commit()
        return order
    except IntegrityError:
        # Two first-time orders with the same email at the same moment.
        session.rollback()
        raise OrderError("Please try again.", status=409) from None
    except BaseException:
        session.rollback()
        raise


def set_status(session, order_id, status):
    try:
        order = session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None:
            raise OrderError("No such order.", status=404)
        if status not in NEXT_STATUS.get(order.status, set()):
            raise OrderError(f"An order that is {order.status} can't become {status}.", status=409)
        if status == "cancelled":
            for item in order.items:
                session.execute(
                    update(Product)
                    .where(Product.id == item.product_id)
                    .values(stock_qty=Product.stock_qty + item.qty)
                    .execution_options(synchronize_session=False)
                )
        order.status = status
        session.commit()
        return order
    except BaseException:
        session.rollback()
        raise
