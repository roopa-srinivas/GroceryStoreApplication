"""flask --app app init-db | seed"""

import random
from datetime import timedelta

import click

from . import db
from .models import Base, Category, Order, Product, utcnow
from .orders import OrderError, place_order, set_status

CATALOG = {
    "Produce": [
        ("PRD-001", "Heirloom Carrots (1 lb)", "🥕", 249, 67),
        ("PRD-002", "Roma Tomatoes (1 lb)", "🍅", 129, 0),
        ("PRD-003", "Honeycrisp Apples (each)", "🍎", 119, 140),
        ("PRD-004", "Bananas (bunch)", "🍌", 189, 45),
        ("PRD-005", "Baby Spinach (5 oz)", "🥬", 349, 9),
        ("PRD-006", "Avocados (each)", "🥑", 179, 38),
    ],
    "Dairy & Eggs": [
        ("DRY-001", "Free Range Eggs (12)", "🥚", 699, 21),
        ("DRY-002", "Oat Almond Milk (64 oz)", "🥛", 349, 8),
        ("DRY-003", "Greek Yogurt (32 oz)", "🍶", 579, 30),
        ("DRY-004", "Aged Cheddar (8 oz)", "🧀", 649, 16),
    ],
    "Bakery": [
        ("BAK-001", "Artisan Sourdough", "🍞", 549, 34),
        ("BAK-002", "Butter Croissants (4)", "🥐", 699, 6),
        ("BAK-003", "Whole Wheat Bagels (6)", "🥯", 449, 25),
    ],
    "Pantry": [
        ("PAN-001", "Organic Rolled Oats (42 oz)", "🌾", 499, 142),
        ("PAN-002", "Jasmine Rice (5 lb)", "🍚", 899, 40),
        ("PAN-003", "Extra Virgin Olive Oil (500 ml)", "🫒", 1099, 18),
        ("PAN-004", "Penne Pasta (1 lb)", "🍝", 219, 75),
        ("PAN-005", "Black Beans (15 oz)", "🫘", 139, 90),
    ],
    "Beverages": [
        ("BEV-001", "Cold Brew Coffee (32 oz)", "☕", 799, 12),
        ("BEV-002", "Sparkling Water (12 pack)", "💧", 599, 50),
        ("BEV-003", "Orange Juice (52 oz)", "🍊", 549, 4),
    ],
    "Frozen": [
        ("FRZ-001", "Frozen Blueberries (2 lb)", "🫐", 899, 22),
        ("FRZ-002", "Vanilla Ice Cream (1.5 qt)", "🍨", 649, 14),
    ],
}

SHOPPERS = [
    ("Maya Chen", "maya@example.com"), ("Jordan Lee", "jordan@example.com"),
    ("Sam Okafor", "sam@example.com"), ("Priya Patel", "priya@example.com"),
    ("Alex Rivera", "alex@example.com"), ("Taylor Kim", "taylor@example.com"),
]


def seed_catalog(session):
    for name, products in CATALOG.items():
        category = Category(name=name)
        session.add(category)
        for sku, product_name, emoji, price, stock in products:
            session.add(Product(sku=sku, name=product_name, emoji=emoji, price_cents=price, stock_qty=stock, category=category))
    session.commit()


def seed_orders(session, count=36, days=14, rng=None):
    """Realistic-looking past orders, placed through the real order code."""
    rng = rng or random.Random(670)
    products = [p for p in session.query(Product).all() if p.stock_qty > 5]
    for n in range(count):
        name, email = rng.choice(SHOPPERS)
        picks = rng.sample(products, k=rng.randint(1, 4))
        try:
            order = place_order(session, name, email, [{"product_id": p.id, "qty": rng.randint(1, 3)} for p in picks])
        except OrderError:
            continue  # sold out along the way, like a real shelf
        age = timedelta(days=days * (count - n) / count, hours=rng.randint(0, 9))
        order.created_at = utcnow() - age
        session.commit()
        # Older orders are further along.
        if age > timedelta(days=4):
            set_status(session, order.id, "shipped")
            set_status(session, order.id, "delivered")
        elif age > timedelta(days=1):
            set_status(session, order.id, rng.choice(["shipped", "cancelled"]) if n % 7 == 0 else "shipped")


def register_commands(app):
    @app.cli.command("init-db")
    @click.option("--reset", is_flag=True, help="Drop all tables first.")
    def init_db(reset):
        """Create the tables."""
        if reset:
            Base.metadata.drop_all(db.engine())
        Base.metadata.create_all(db.engine())
        click.echo("Tables ready.")

    @app.cli.command("seed")
    def seed():
        """Fill an empty database with a sample store and two weeks of orders."""
        session = db.session()
        if session.query(Product).count():
            raise click.ClickException("The database already has products. Use `init-db --reset` first.")
        seed_catalog(session)
        seed_orders(session)
        click.echo(f"Seeded {session.query(Product).count()} products and {session.query(Order).count()} orders.")
