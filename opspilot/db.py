from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

SERVICE_FIXTURES = {
    "checkout-service": "Checkout orchestration; depends on payment and inventory",
    "payment-service": "Fictional payment authorization dependency",
    "inventory-service": "Fictional stock reservation with a bounded database pool",
}


def make_engine(url: str):
    kwargs = {"pool_pre_ping": True, "hide_parameters": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["connect_args"] = {"connect_timeout": 3}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def enforce_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)
