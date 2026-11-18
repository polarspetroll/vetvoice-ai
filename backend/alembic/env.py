from alembic import context
from backend.db import engine, Base
import backend.models  # noqa  registers tables

target_metadata = Base.metadata


with engine.connect() as conn:
    context.configure(connection=conn, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
