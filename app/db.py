"""One engine per app, one session per request."""

from flask import current_app, g
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def init_app(app):
    engine = create_engine(app.config["DATABASE_URL"], pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys unless asked, per connection.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA foreign_keys = ON")

    app.extensions["engine"] = engine
    app.extensions["sessionmaker"] = sessionmaker(engine, expire_on_commit=False)
    app.teardown_appcontext(_close_session)


def engine():
    return current_app.extensions["engine"]


def session():
    if "db_session" not in g:
        g.db_session = current_app.extensions["sessionmaker"]()
    return g.db_session


def _close_session(_error):
    db_session = g.pop("db_session", None)
    if db_session is not None:
        db_session.close()
