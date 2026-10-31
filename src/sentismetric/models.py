import enum
from datetime import datetime
from sqlalchemy import (
    String,
    Integer,
    Numeric,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    JSON,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FilingStatus(str, enum.Enum):
    NEW = "NEW"
    EXTRACTED = "EXTRACTED"
    ANALYZED = "ANALYZED"
    ALERTED = "ALERTED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class FilingType(str, enum.Enum):
    RESULTS_HALF_YEARLY = "RESULTS_HALF_YEARLY"
    BOARD_MEETING_OUTCOME = "BOARD_MEETING_OUTCOME"
    BOARD_MEETING_INTIMATION = "BOARD_MEETING_INTIMATION"
    ROUTINE = "ROUTINE"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    name: Mapped[str] = mapped_column(String(256))
    exchange: Mapped[str] = mapped_column(String(8))  #'NSE' oe 'BSE'
    series_or_group: Mapped[str] = mapped_column(String(8))  # 'SM','ST' or BSE group
    scrip_code: Mapped[str | None] = mapped_column(String(16), index=True)  # NEW
    listing_date: Mapped[datetime | None]
    active: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (UniqueConstraint("exchange", "symbol"),)


class Filing(Base):
    __tablename__ = "filings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    exchange: Mapped[str] = mapped_column(String(8))
    ann_id: Mapped[str] = mapped_column(String(64))  #exchange's announcement id
    category_raw: Mapped[str] = mapped_column(String(256))
    filing_type: Mapped[str] = mapped_column(String(32))
    period: Mapped[str | None] = mapped_column(String(16))  #e.g. 'H1FY26'
    exchange_ts: Mapped[datetime]  #when exchange published (store UTC)
    ingest_ts: Mapped[datetime] = mapped_column(server_default=func.now())
    pdf_path: Mapped[str | None] = mapped_column(String(512))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default=FilingStatus.NEW.value)
    error: Mapped[str | None] = mapped_column(String(1024))

    company: Mapped[Company] = relationship()

    __table_args__ = (
        UniqueConstraint("exchange", "ann_id"),
        Index("ix_filings_status", "status"),
        Index("ix_filings_type_ts", "filing_type", "exchange_ts"),
    )


class Financials(Base):
    __tablename__ = "financials"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
    period: Mapped[str] = mapped_column(String(16))
    revenue: Mapped[float | None] = mapped_column(Numeric(18, 2))
    pat: Mapped[float | None] = mapped_column(Numeric(18, 2))
    eps: Mapped[float | None] = mapped_column(Numeric(10, 2))
    debt_current: Mapped[float | None] = mapped_column(Numeric(18, 2))
    debt_noncurrent: Mapped[float | None] = mapped_column(Numeric(18, 2))
    debt_equity_ratio: Mapped[float | None] = mapped_column(Numeric(10, 4))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(8), default="XBRL")
    total_expenses: Mapped[float | None] = mapped_column(Numeric(18, 2))

    __table_args__ = (UniqueConstraint("company_id", "period"),)


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"), unique=True)
    summary: Mapped[str] = mapped_column(String(2000))
    positives: Mapped[list] = mapped_column(JSON, default=list)  #[{quote,page,why}]
    negatives: Mapped[list] = mapped_column(JSON, default=list)
    flags: Mapped[dict] = mapped_column(JSON, default=dict)
    notability: Mapped[float] = mapped_column(default=0.0)
    prompt_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    
    
# CHUNKS to be used for hybrid search model (semantic matching + exact keyword matching)
from pgvector.sqlalchemy import Vector

class Chunk(Base):
    __tablename__="chunks"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    filing_id: Mapped[int] = mapped_column(ForeignKey("filings.id"),index = True)
    page_start: Mapped[int]
    page_end: Mapped[int]
    text: Mapped[str] = mapped_column(String(8000))
    embedding = mapped_column((Vector(1024))) #dimension matches embedding model
    
"""
Add this class to models.py, anywhere alongside your other models
(Filing, Company, etc.) — matches the same Mapped/mapped_column style
already used there.

Single-user design (per the project's own scope — private,
non-commercial, single-user tool): no user_id column needed, just a
company_id with a unique constraint so a company can't be added twice.
"""

from datetime import datetime
from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column


class Watchlist(Base):  # Base is your existing declarative base from models.py
    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), unique=True)
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())