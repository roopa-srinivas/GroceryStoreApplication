from conftest import order


def test_revenue_counts_price_paid_and_skips_cancelled(client, product):
    eggs, bread = product("DRY-001"), product("BAK-001")
    order(client, (eggs["id"], 2))
    cancelled = order(client, (bread["id"], 1)).get_json()
    client.patch(f"/api/orders/{cancelled['id']}", json={"status": "cancelled"})
    client.patch(f"/api/products/{eggs['id']}", json={"price_cents": 5})

    report = client.get("/api/reports?days=7").get_json()
    assert report["revenue_by_category"] == [{"category": "Dairy & Eggs", "units": 2, "revenue_cents": 2 * eggs["price_cents"]}]
    assert report["top_products"][0]["name"] == "Free Range Eggs (12)"
    assert report["orders_by_status"] == {"processing": 1, "cancelled": 1}


def test_low_stock_report(client):
    low = client.get("/api/reports").get_json()["low_stock"]
    assert low[0]["stock_qty"] == 0  # most urgent first
    assert {"Roma Tomatoes (1 lb)", "Oat Almond Milk (64 oz)"} <= {p["name"] for p in low}
    assert all(p["stock_qty"] <= p["low_stock_at"] for p in low)


def test_report_sql_is_included(client):
    sql = client.get("/api/reports").get_json()["sql"]
    assert sql["revenue_by_category"].startswith("SELECT")
