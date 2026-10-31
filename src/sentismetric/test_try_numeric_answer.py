from sentismetric.rag.retrieve import answer
from sentismetric.db import SessionLocal
from sentismetric.models import Company

with SessionLocal() as session:
    company = session.query(Company).filter_by(exchange="NSE", symbol="PRITIKA").one()

result = answer("what was the revenue", company_id=company.id)
print(result)