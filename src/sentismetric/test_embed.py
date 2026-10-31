from sentismetric.rag.embed_backend import get_backend
from sentismetric.db import SessionLocal
from sqlalchemy import text as sql

backend = get_backend()
query = "director re-appointment"
query_embedding = backend.embed([query], input_type="query")[0]

with SessionLocal() as session:
    stmt = sql("""
        SELECT id, page_start, page_end, text, 1 - (embedding <=> :qvec) AS similarity
        FROM chunks
        ORDER BY embedding <=> :qvec
        LIMIT 3
    """)
    results = session.execute(stmt, {"qvec": str(query_embedding)}).mappings().all()
    for r in results:
        print(f"similarity={r['similarity']:.3f} pages={r['page_start']}-{r['page_end']}")
        print(f"  {r['text'][:150]}...")
        print()