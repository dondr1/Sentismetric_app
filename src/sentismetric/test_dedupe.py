from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sentismetric.db import SessionLocal
from sentismetric.models import Company, Filing
from sentismetric.log import setup_logging, log

setup_logging(level="DEBUG")

with SessionLocal() as session:
    #first make sure we have a company to attach filings to 
    company = session.query(Company).filter_by(exchan ge="BSE", symbol = "TESTCO").one_or_none()
    if company is None: 
        company = Company(
            exchange = "BSE",
            symbol = "TESTCO",
            name = "Test Company",
            isin = "INE000A01234",
            series_or_group = "SME",   
        )
        session.add(company)
        session.commit()
        log.info("created test company id = %s", company.id)
    # Insert the first filing
    filing1 = Filing(
        company_id=company.id,
        exchange=company.exchange,
        ann_id="DUPLICATE001",
        category_raw="Board Meeting",
        filing_type="ROUTINE",
        exchange_ts=datetime.now(timezone.utc),
    )
    session.add(filing1)
    session.commit()
    log.info("inserted first filing id = %s", filing1.id)
    
    filing2 = Filing(
        company_id=company.id,
        exchange=company.exchange,
        ann_id="DUPLICATE001",
        category_raw="Board Meeting- duplicate attempt",
        filing_type="ROUTINE",
        exchange_ts=datetime.now(timezone.utc),
    )
    session.add(filing2)
    try:
        session.commit()
        log.info("inserted second filig id=%s (THIS SHOULD NOT HAPPEN)", filings2.id)
    except IntegrityError:
        session.rollback()
        log.debug("duplicate, skipping: exchange=%s ann_id=%s", filing2.exchange, filing2.ann_id)