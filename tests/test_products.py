def test_search_by_name_category_and_price(client):
    names = [p["name"] for p in client.get("/api/products?q=sourdough").get_json()]
    assert names == ["Artisan Sourdough"]

    categories = client.get("/api/categories").get_json()
    produce = next(c["id"] for c in categories if c["name"] == "Produce")
    produce_items = client.get(f"/api/products?category={produce}").get_json()
    assert produce_items and all(p["category"] == "Produce" for p in produce_items)

    cheap = client.get("/api/products?max_price=150&sort=price_asc").get_json()
    prices = [p["price_cents"] for p in cheap]
    assert prices == sorted(prices) and max(prices) <= 150


def test_search_treats_wildcards_as_text(client):
    assert client.get("/api/products?q=%25").get_json() == []


def test_in_stock_filter_and_status(client, product):
    assert product("PRD-002")["status"] == "out"
    assert product("DRY-002")["status"] == "low"
    in_stock = client.get("/api/products?in_stock=1").get_json()
    assert all(p["stock_qty"] > 0 for p in in_stock)


def test_bad_filters_are_rejected(client):
    assert client.get("/api/products?min_price=cheap").status_code == 400
    assert client.get("/api/products?sort=random").status_code == 400


def test_create_product(client):
    category = client.get("/api/categories").get_json()[0]["id"]
    res = client.post("/api/products", json={"sku": "new-1", "name": "Kale", "category_id": category, "price_cents": 299, "stock_qty": 5})
    assert res.status_code == 201
    assert res.get_json()["sku"] == "NEW-1"
    duplicate = client.post("/api/products", json={"sku": "NEW-1", "name": "Kale", "category_id": category, "price_cents": 299})
    assert duplicate.status_code == 409
    assert client.post("/api/products", json={"sku": "X", "name": "Free", "category_id": category, "price_cents": 0}).status_code == 400


def test_restock_adds_to_current_stock(client, product):
    milk = product("DRY-002")
    res = client.post(f"/api/products/{milk['id']}/restock", json={"qty": 24})
    assert res.get_json()["stock_qty"] == milk["stock_qty"] + 24
    assert client.post(f"/api/products/{milk['id']}/restock", json={"qty": 0}).status_code == 400
    assert client.post("/api/products/99999/restock", json={"qty": 5}).status_code == 404


def test_retired_products_leave_the_store(client, product):
    eggs = product("DRY-001")
    client.patch(f"/api/products/{eggs['id']}", json={"is_active": False})
    assert "Free Range Eggs (12)" not in [p["name"] for p in client.get("/api/products").get_json()]
