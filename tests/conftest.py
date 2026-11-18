import os
import pytest

# tests use their own database so they never touch real data
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", "postgresql+psycopg://vet:vet@localhost:5432/vetvoice_test")
os.environ["SMS_DRY_RUN"] = "1"

from sqlalchemy import create_engine, text  # noqa


@pytest.fixture(scope="session")
def db_ready():
    url = os.environ["DATABASE_URL"]
    admin = create_engine(url.rsplit("/", 1)[0] + "/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text("DROP DATABASE IF EXISTS vetvoice_test WITH (FORCE)"))
            c.execute(text("CREATE DATABASE vetvoice_test"))
    except Exception as e:
        pytest.skip(f"postgres not available: {e}")
    from backend.db import engine, Base, SessionLocal
    import backend.models  # noqa
    from backend.seed import build
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add_all(build())
        db.commit()
    yield
    engine.dispose()
