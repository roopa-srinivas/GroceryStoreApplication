"""Many shoppers racing for the same few items, at the same moment.

Only meaningful on a real database server: SQLite runs one write at a time,
so this runs in CI against MySQL and is skipped locally.
"""

import os
import threading

import pytest

from conftest import order

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL", "").startswith("mysql"), reason="needs MySQL")


def test_last_items_are_never_oversold(app, client, product):
    juice = product("BEV-003")
    stock = juice["stock_qty"]
    shoppers = 20
    start = threading.Barrier(shoppers)
    results = []

    def shop(n):
        own_client = app.test_client()
        start.wait()
        results.append(order(own_client, (juice["id"], 1), email=f"racer{n}@example.com").status_code)

    threads = [threading.Thread(target=shop, args=(n,)) for n in range(shoppers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(201) == stock
    assert results.count(409) == shoppers - stock
    assert product("BEV-003")["stock_qty"] == 0
