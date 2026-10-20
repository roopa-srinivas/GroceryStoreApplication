# Grocery Store App

A storefront and manager tools for a grocery store, on a relational MySQL database behind a Flask API. **Rebuilt from scratch in 2026.**

**Project page:** https://roopa-srinivas.github.io/GroceryStoreApplication/

![The storefront](screenshots/shop.jpg)

## Highlights
- **No overselling.** An order takes stock with `UPDATE products SET stock_qty = stock_qty - n WHERE id = ? AND stock_qty >= n` for each item, in one transaction and in id order (so concurrent orders can't deadlock). If any item is short, the whole order rolls back. A test races 20 shoppers for the last few units on MySQL and checks that exactly that many succeed.
- **Relational schema:** categories, products, customers, orders and order items, with foreign keys, unique SKUs and emails, `CHECK` constraints and indexes. Money is stored in cents, and order items keep the price paid.
- **Manager tools:** inventory with low-stock flags and restocking, order tracking (processing → shipped → delivered, or cancelled with a restock), and reports in plain SQL that the reports page displays.
- **Tested on real MySQL:** GitHub Actions runs the 22 tests on SQLite and on a MySQL 8.4 server on every push.

## Run it
```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL="mysql+pymysql://user:password@localhost/grocery"   # optional; defaults to SQLite (grocery.db)
flask --app app init-db
flask --app app seed      # a 23-product store with two weeks of orders
flask --app app run       # http://127.0.0.1:5000
```

Tests: `pytest` (set `DATABASE_URL` to a MySQL database to include the concurrency test).

## API
| Method | Path | What it does |
|---|---|---|
| GET | `/api/categories` | List categories |
| GET | `/api/products` | Search: `q`, `category`, `min_price`, `max_price` (cents), `in_stock=1`, `sort` |
| POST | `/api/products` | Add a product |
| PATCH | `/api/products/<id>` | Change name, price, low-stock level, or retire it |
| POST | `/api/products/<id>/restock` | Add delivered units |
| POST | `/api/orders` | Place an order: `{customer: {name, email}, items: [{product_id, qty}]}` |
| GET | `/api/orders` | List orders, optionally `?status=` |
| PATCH | `/api/orders/<id>` | Move an order to `shipped`, `delivered` or `cancelled` |
| GET | `/api/reports?days=7` | Revenue by category, top products, low stock, orders by status (with their SQL) |

The manager pages and endpoints have no login: this is a portfolio demo, and a real store would put them behind staff accounts.

## Project structure
| Path | What it is |
|---|---|
| `app/models.py` | The schema |
| `app/orders.py` | Placing orders and status changes |
| `app/reports.py` | Report queries in SQL |
| `app/api.py` | The JSON API |
| `app/templates/`, `app/static/` | The shop and manager pages |
| `tests/` | pytest suite |
| `index.html` | The project page (GitHub Pages) |
