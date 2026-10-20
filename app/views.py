from flask import Blueprint, render_template

views = Blueprint("views", __name__)


@views.get("/")
def store():
    return render_template("store.html", active="store")


@views.get("/manage/orders")
def orders():
    return render_template("orders.html", active="orders")


@views.get("/manage/inventory")
def inventory():
    return render_template("inventory.html", active="inventory")


@views.get("/manage/reports")
def reports():
    return render_template("reports.html", active="reports")
