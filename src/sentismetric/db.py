from sqlalchemy import create_engine
from sqlalchemy import text as sql
from sqlalchemy.orm import sessionmaker
from sentismetric.config import settings
from sentismetric.models import Base



engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_next_filing(status: str):
    """Selects and locks the oldest filing with the given status,
    skipping rows another worker already has locked."""
    stmt = sql("""
        SELECT * FROM filings
        WHERE status = :status
        ORDER BY exchange_ts ASC
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    """)
    with SessionLocal() as session:
        row = session.execute(stmt, {"status": status}).mappings().first()
        return dict(row) if row else None