from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from app.core.config import settings

_URL = settings.DATABASE_URL or ""
# Supabase Session pooler (port 5432) caps concurrent clients (~15 on free/pro).
# NullPool avoids holding idle app-side connections that exhaust that limit.
# Transaction pooler (port 6543) can use a small QueuePool.
_USE_NULL_POOL = "pooler.supabase.com" in _URL and ":6543" not in _URL

engine = create_engine(
    _URL,
    pool_pre_ping=True,
    poolclass=NullPool if _USE_NULL_POOL else QueuePool,
    **({} if _USE_NULL_POOL else {
        "pool_recycle": 180,
        "pool_size": 2,
        "max_overflow": 1,
        "pool_timeout": 20,
    }),
    connect_args={
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 3,
    },
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _db_down(exc: BaseException) -> HTTPException:
    return HTTPException(
        503,
        "Database connection failed. Check network and DATABASE_URL "
        "(prefer the Supabase pooler host if direct db.*.supabase.co fails).",
    )


def get_db():
    try:
        db = SessionLocal()
    except (OperationalError, InterfaceError, DBAPIError) as exc:
        raise _db_down(exc) from exc
    try:
        yield db
    except (OperationalError, InterfaceError, DBAPIError) as exc:
        try:
            db.rollback()
        except Exception:
            pass
        raise _db_down(exc) from exc
    finally:
        try:
            db.close()
        except Exception:
            pass
