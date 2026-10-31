from sentismetric.rag.retrieve import hybrid_search

results = hybrid_search("director re-appointment", filing_id=15)
for r in results:
    print(f"score={r['score']:.4f} pages={r['page_start']}-{r['page_end']}")
    print(f"  {r['text'][:100]}...")