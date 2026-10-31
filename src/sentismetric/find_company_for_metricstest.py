from sentismetric.db import SessionLocal
from sentismetric.models import Financials, Company

with SessionLocal() as session:
    # find companies with 2+ financials rows -- candidates for hoh comparison
    from sqlalchemy import func
    candidates = (
        session.query(Financials.company_id, func.count(Financials.id).label("cnt"))
        .group_by(Financials.company_id)
        .having(func.count(Financials.id) >= 2)
        .all()
    )
    print(f"Found {len(candidates)} companies with 2+ periods stored")

    if candidates:
        company_id = candidates[0][0]
        company = session.query(Company).filter_by(id=company_id).one()
        rows = session.query(Financials).filter_by(company_id=company_id).all()
        print(f"\nCompany: {company.symbol}")
        for r in rows:
            print(f"  period={r.period} revenue={r.revenue} pat={r.pat} debt_current={r.debt_current} debt_noncurrent={r.debt_noncurrent}")