"""Engine / session setup. SQLite by default, Postgres via DATABASE_URL."""

import logging
from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import settings
from backend.store.models import Base

log = logging.getLogger(__name__)


def normalize_url(url: str) -> str:
    """Neon/Supabase/RDS hand out postgres:// or postgresql:// URLs; SQLAlchemy would pick psycopg2 for those."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if ":memory:" in url or url == "sqlite://":
            kwargs["poolclass"] = StaticPool  # one shared in-memory DB
        return create_engine(url, **kwargs)
    return create_engine(url, pool_pre_ping=True)


engine = make_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def add_missing_columns(eng: Engine) -> list[str]:
    """Add columns that exist in the models but not yet in the database (nullable, no data touched).

    ponytail: additive only; renames, drops and type changes need Alembic once the schema starts moving.
    """
    insp = inspect(eng)
    added = []
    with eng.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in have:
                    ddl = col.type.compile(dialect=eng.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {ddl}'))
                    added.append(f"{table.name}.{col.name}")
    if added:
        log.info("added columns: %s", ", ".join(added))
    return added


def init_db(eng: Engine = engine) -> None:
    Base.metadata.create_all(eng)
    add_missing_columns(eng)


def get_session() -> Iterator[Session]:
    """FastAPI dependency."""
    with SessionLocal() as session:
        yield session
