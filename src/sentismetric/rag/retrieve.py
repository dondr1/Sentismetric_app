from sqlalchemy import text as sql

from sentismetric.db import SessionLocal
from sentismetric.rag.embed_backend import get_backend


def hybrid_search(query: str, filing_id: int | None = None, k: int = 8) -> list[dict]:
    """Combine vector (semantic) similarity and exact keyword full-text search, merged
    by weighted score. Vector search alone can blur similar-but-wrong
    terms (e.g.'promoter pledge' vs 'management commitment'); keyword
    search alone misses conceptually related but differently-worded
    text. Together they cover both failure modes."""
    backend = get_backend()
    query_vec = backend.embed([query], input_type="query")[0]

    scope = "AND c.filing_id = :fid" if filing_id else ""
    stmt = sql(f"""
        WITH vec AS (
            SELECT id, 1 - (embedding <=> :qvec) AS vscore
            FROM chunks c WHERE true {scope}
            ORDER BY embedding <=> :qvec LIMIT 20
        ),
        kw AS (
            SELECT id, ts_rank(tsv, plainto_tsquery('english', :q)) AS kscore
            FROM chunks c
            WHERE tsv @@ plainto_tsquery('english', :q) {scope}
            LIMIT 20
        )
        SELECT ch.id, ch.text, ch.page_start, ch.page_end, ch.filing_id,
               COALESCE(v.vscore, 0) * 0.6 + COALESCE(k.kscore, 0) * 0.4 AS score
        FROM chunks ch
        LEFT JOIN vec v ON v.id = ch.id
        LEFT JOIN kw k ON k.id = ch.id
        WHERE v.id IS NOT NULL OR k.id IS NOT NULL
        ORDER BY score DESC LIMIT :k
    """)

    with SessionLocal() as session:
        rows = session.execute(stmt, {
            "qvec": str(query_vec),
            "q": query,
            "fid": filing_id,
            "k": k,
        }).mappings().all()
        return [dict(r) for r in rows]


# Phrases signaling a definitional question ("what does PAT mean") --
# checked BEFORE metric-keyword matching, since "full form of PAT"
# contains the substring "pat" and would otherwise wrongly match the
# numeric-lookup path below.
DEFINITIONAL_PATTERNS = (
    "what does", "what is the full form", "full form of", "stand for",
    "meaning of", "define", "definition of", "what's the meaning",
)

# Fixed, universally-agreed definitions -- safe to hardcode since these
# aren't filing-specific facts that could be wrong.
GLOSSARY = {
    "pat": "PAT stands for Profit After Tax.",
    "eps": "EPS stands for Earnings Per Share.",
    "yoy": "YoY stands for Year-over-Year.",
    "hoh": "HoH stands for Half-over-Half (or Period-over-Period, depending on context).",
    "pbt": "PBT stands for Profit Before Tax.",
}


def try_glossary_answer(question: str) -> str | None:
    q = question.lower()
    if not any(p in q for p in DEFINITIONAL_PATTERNS):
        return None
    for term, definition in GLOSSARY.items():
        if term in q:
            return definition
    return None


def try_numeric_answer(question: str, company_id: int, session) -> str | None:
    """Route numeric questions directly to the financials table instead
    of chunk search, since XBRL-sourced numbers are more trustworthy
    than anything retrieved from extracted text. Crude keyword matching
    is fine here -- precision over coverage. Returns None (not a guess)
    when the question doesn't clearly map to a known metric, letting
    hybrid_search handle it instead."""
    from sentismetric.models import Financials

    q = question.lower()

    if any(p in q for p in DEFINITIONAL_PATTERNS):
        return None

    metric_keywords = {
        "revenue": ("revenue", "sales", "turnover"),
        "pat": ("pat", "profit after tax", "net profit"),
        "eps": ("eps", "earnings per share"),
        "total_expenses": ("expenses", "expenditure", "costs"),
        "debt_current": ("current debt", "short-term debt", "short term borrowing"),
        "debt_noncurrent": ("long-term debt", "long term debt", "non-current debt"),
    }

    matched_field = None
    for field, keywords in metric_keywords.items():
        if any(kw in q for kw in keywords):
            matched_field = field
            break

    if matched_field is None:
        return None  #not clearly a numeric question -> let retrieval try

    #find the most recent financials row for this company
    row = (
        session.query(Financials)
        .filter_by(company_id=company_id)
        .filter(Financials.period.like("Q%-FY%"))
        .order_by(Financials.period.desc())
        .first()
    )
    if row is None:
        return None

    value = getattr(row, matched_field, None)
    if value is None:
        return None  #data genuinely missing

    return f"{matched_field.replace('_', ' ').title()} for {row.period}: {value}"


import anthropic

from sentismetric.config import settings

ANSWER_PROMPT = """Answer the question using ONLY the excerpts below.
Cite page numbers like (p. 4) after each claim.
If the answer is not in the excerpts, say exactly: "Not found in this filing."
Never use recommendation language.

QUESTION: {question}

EXCERPTS:
{excerpts}"""


def answer(question: str, filing_id: int | None = None, company_id: int | None = None) -> str:
    """Answer a question, grounded in either structured financials
    (for numeric questions) or retrieved filing chunks (for everything
    else). Refuses honestly rather than guessing when nothing is found."""
    from sentismetric.db import SessionLocal

    glossary_hit = try_glossary_answer(question)
    if glossary_hit is not None:
        return glossary_hit

    if company_id is not None:
        with SessionLocal() as session:
            numeric = try_numeric_answer(question, company_id, session)
            if numeric is not None:
                return numeric

    chunks = hybrid_search(question, filing_id=filing_id)
    if not chunks:
        return "Not found in this filing."

    excerpts = "\n---\n".join(
        f"[pages {c['page_start']}-{c['page_end']}]\n{c['text']}"
        for c in chunks
    )

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": ANSWER_PROMPT.format(question=question, excerpts=excerpts),
        }],
    )
    return msg.content[0].text