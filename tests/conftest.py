"""Tests run on SQLite by default, or on MySQL when DATABASE_URL is set
(CI runs both)."""

import os

import pytest

from app import create_app, db
from app.cli import seed_catalog
from app.models import Base


@pytest.fixture
def app(tmp_path):
    url = os.environ.get("DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    app = create_app(url)
    app.config["TESTING"] = True
    with app.app_context():
        Base.metadata.drop_all(db.engine())
        Base.metadata.create_all(db.engine())
        seed_catalog(db.session())
        db.session().close()
    yield app
    with app.app_context():
        db.session().close()
        Base.metadata.drop_all(db.engine())
        db.engine().dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def product(client):
    """Looks up a seeded product by SKU."""

    def find(sku):
        return next(p for p in client.get("/api/products?include_inactive=1").get_json() if p["sku"] == sku)

    return find


def order(client, *lines, email="shopper@example.com"):
    return client.post(
        "/api/orders",
        json={"customer": {"name": "Shopper", "email": email}, "items": [{"product_id": pid, "qty": qty} for pid, qty in lines]},
    )
