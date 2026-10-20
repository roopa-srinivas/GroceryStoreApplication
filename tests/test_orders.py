from conftest import order


def test_order_takes_stock_and_totals_at_current_price(client, product):
    eggs, oats = product("DRY-001"), product("PAN-001")
    res = order(client, (eggs["id"], 2), (oats["id"], 1))
    assert res.status_code == 201
    body = res.get_json()
    assert body["total_cents"] == 2 * eggs["price_cents"] + oats["price_cents"]
    assert body["status"] == "processing"
    assert product("DRY-001")["stock_qty"] == eggs["stock_qty"] - 2


def test_repeated_lines_are_merged(client, product):
    eggs = product("DRY-001")
    body = order(client, (eggs["id"], 1), (eggs["id"], 2)).get_json()
    assert [(i["product_id"], i["qty"]) for i in body["items"]] == [(eggs["id"], 3)]


def test_overselling_is_refused_and_nothing_changes(client, product):
    juice, eggs = product("BEV-003"), product("DRY-001")  # juice has 4 left
    res = order(client, (eggs["id"], 1), (juice["id"], juice["stock_qty"] + 1))
    assert res.status_code == 409
    assert res.get_json()["short"] == [juice["id"]]
    # The whole order rolled back, including the eggs that were available.
    assert product("DRY-001")["stock_qty"] == eggs["stock_qty"]
    assert product("BEV-003")["stock_qty"] == juice["stock_qty"]
    assert client.get("/api/orders").get_json() == []


def test_selling_the_last_unit_then_nothing_more(client, product):
    juice = product("BEV-003")
    assert order(client, (juice["id"], juice["stock_qty"])).status_code == 201
    assert product("BEV-003")["status"] == "out"
    assert order(client, (juice["id"], 1)).status_code == 409


def test_bad_orders_are_rejected(client, product):
    eggs = product("DRY-001")
    assert order(client).status_code == 400
    assert order(client, (eggs["id"], 0)).status_code == 400
    assert order(client, (eggs["id"], 100)).status_code == 400
    no_email = client.post("/api/orders", json={"customer": {"name": "A"}, "items": [{"product_id": eggs["id"], "qty": 1}]})
    assert no_email.status_code == 400


def test_price_changes_dont_rewrite_past_orders(client, product):
    eggs = product("DRY-001")
    placed = order(client, (eggs["id"], 1)).get_json()
    client.patch(f"/api/products/{eggs['id']}", json={"price_cents": 1})
    again = next(o for o in client.get("/api/orders").get_json() if o["id"] == placed["id"])
    assert again["total_cents"] == eggs["price_cents"]
    assert again["items"][0]["unit_price_cents"] == eggs["price_cents"]


def test_status_flow_and_cancel_restocks(client, product):
    eggs = product("DRY-001")
    first = order(client, (eggs["id"], 3)).get_json()
    assert client.patch(f"/api/orders/{first['id']}", json={"status": "delivered"}).status_code == 409
    assert client.patch(f"/api/orders/{first['id']}", json={"status": "shipped"}).get_json()["status"] == "shipped"
    assert client.patch(f"/api/orders/{first['id']}", json={"status": "cancelled"}).status_code == 409

    second = order(client, (eggs["id"], 2)).get_json()
    assert client.patch(f"/api/orders/{second['id']}", json={"status": "cancelled"}).status_code == 200
    # The cancelled order's 2 come back; the shipped order's 3 stay sold.
    assert product("DRY-001")["stock_qty"] == eggs["stock_qty"] - 3
    assert client.patch("/api/orders/99999", json={"status": "shipped"}).status_code == 404
