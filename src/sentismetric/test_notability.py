tiny_metrics = {"revenue_hoh_pct": 200.0}
tiny_financials = {"revenue": 1_500_000, "prev_revenue": 500_000}
empty_flags = {}
empty_insight = {"positives": [], "negatives": []}

from sentismetric.analyze.scorecard import notability

tiny_score = notability(tiny_metrics, empty_flags, empty_insight, tiny_financials)
print("Tiny company (200% swing on small base) notability score:", tiny_score)

large_metrics = {"revenue_hoh_pct": -25.0}
large_financials = {"revenue": 75_000_000, "prev_revenue": 100_000_000}
large_score = notability(large_metrics, empty_flags, empty_insight, large_financials)
print("Large company (-25% real decline) notability score:", large_score)