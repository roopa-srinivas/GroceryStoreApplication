"""Fresh Market: a grocery store app for store managers.

Flask serves a JSON API and the pages that use it; SQLAlchemy talks to
MySQL in production (SQLite works for local development and tests).
"""

import os

from flask import Flask

from . import db


def create_app(database_url=None):
    app = Flask(__name__)
    app.config["DATABASE_URL"] = database_url or os.environ.get("DATABASE_URL", "sqlite:///grocery.db")
    db.init_app(app)

    from .api import api
    from .cli import register_commands
    from .views import views

    app.register_blueprint(api, url_prefix="/api")
    app.register_blueprint(views)
    register_commands(app)
    return app
