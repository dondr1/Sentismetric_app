from sentismetric.analyze.scorecard import compute_metrics

cur = {"revenue": 241375000.00, "pat": None, "debt_current": None, "debt_noncurrent": None, "debt_equity_ratio": None}
prev = {"revenue": 162343000.00, "pat": 23504000.00, "debt_current": None, "debt_noncurrent": None, "debt_equity_ratio": None}

result = compute_metrics(cur, prev, None)
print(result)
