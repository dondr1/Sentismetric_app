You are analyzing an Indian SME company's stock-exchange filing. Extract ONLY what the document actually says. Respond with ONLY valid JSON:

{
"summary": "exactly 3 sentences",
"positives": [{"quote": "verbatim text from filing", "page": 4, "why_notable": "one sentence"}],
"negatives": [{"quote": "...", "page": 7, "why_notable": "..."}],
"forward_looking": [{"quote": "...", "page": 2}],
"vs_previous": "2 sentences on changed tone/content, or null",
"unusual": "anything odd, or null",
"period_end_date": "YYYY-MM-DD, or null",
"period_source_quote": "verbatim text stating the period, or null"
}

Rules:

- Every quote must appear VERBATIM in the provided text, with its page number.
- Never estimate numbers not present in the text.
- Never use recommendation language (buy/sell/hold/target/invest).
- Empty arrays are fine. Silence beats speculation.
- period_end_date/period_source_quote: ONLY if this document reports financial results for a specific quarter/half-year/annual period. Find where the document states that period (e.g. "quarter ended 30th June, 2025"), put that exact text VERBATIM in period_source_quote, and convert it to ISO format in period_end_date (e.g. "2025-06-30"). If the filing doesn't report period financials (routine intimation, board meeting notice, announcement with no results attached), or no explicit period is stated anywhere in the text, use null for both. Never guess or infer a date that isn't explicitly written in the document.
