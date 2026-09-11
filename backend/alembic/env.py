import os
import sys
from logging.config import fileConfig

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alembic import context
from app.db.base import Base
import app.models  # noqa

config = context.config
target_metadata = Base.metadata


def _db_url():
    # The app's real database comes from .env (e.g. Supabase); alembic.ini is only a fallback.
    try:
        from app.core.config import settings
        if settings.DATABASE_URL:
            return settings.DATABASE_URL
    except Exception:
        pass
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline():
    context.configure(url=_db_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    from sqlalchemy import engine_from_config
    engine = engine_from_config({"sqlalchemy.url": _db_url()}, prefix="sqlalchemy.")
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online() if context.is_offline_mode() is False else run_migrations_offline()
