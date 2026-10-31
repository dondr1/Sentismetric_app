import json
import pathlib
import re
from datetime import datetime

import anthropic

from sentismetric.config import settings

PROMPT_FILE = pathlib.Path("prompts/insights_v1.md")
PROMPT_VERSION = "insights_v1_period"  # bumped: schema now includes period_end_date/period_source_quote


def validate_quotes(data: dict, markdown: str) -> dict:
    """Check every quote actually appears verbatim in the source text.
    Drop any insight whose quote fails -- this is the teeth behind the
    no-hallucination rule. Enforced in code, not hope."""
    normalized_source = " ".join(markdown.split())

    def quote_is_real(quote: str) -> bool:
        normalized_quote = " ".join(quote.split())
        return normalized_quote in normalized_source

    for key in ("positives", "negatives", "forward_looking"):
        items = data.get(key, [])
        data[key] = [item for item in items if quote_is_real(item.get("quote", ""))]

    # Ground period_end_date via its source quote — an ISO date like
    # "2025-06-30" has nothing to check verbatim (the source says "30th
    # June, 2025" in prose), so we verify the QUOTE it's claimed to come
    # from is real instead, and only trust the date if that quote is
    # grounded. Same "silence beats speculation" philosophy as the
    # quote arrays above.
    period_quote = data.get("period_source_quote")
    if period_quote:
        if not quote_is_real(period_quote):
            data["period_end_date"] = None
            data["period_source_quote"] = None
        else:
            # quote is grounded, but the LLM could still have miswritten
            # the ISO conversion — cheap format/sanity check so a
            # malformed or implausible date doesn't get used downstream
            end_date = data.get("period_end_date")
            try:
                parsed = datetime.fromisoformat(end_date) if end_date else None
                if parsed is None or not (2015 <= parsed.year <= 2035):
                    data["period_end_date"] = None
            except (ValueError, TypeError):
                data["period_end_date"] = None
    else:
        data["period_end_date"] = None

    return data


def analyze_filing(markdown: str, prev_insight_json: str | None = None, flags: dict | None = None) -> dict:
    """Run the LLM insight pass on a filing's extracted text.

    markdown: full extracted text of the filing, with [Page N] markers.
    prev_insight_json: previous period's insight JSON, for vs_previous comparison.
    flags: output of extract_flags() -> automatically detected phrases,
        passed as a hint for the LLM to verify and incorporate if genuinely
        notable. These are NOT trusted as facts; the LLM must judge them
        against the actual document, and any quote it produces still has
        to pass validate_quotes() against the real source text.
    """
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = PROMPT_FILE.read_text()

    context = f"PREVIOUS PERIOD INSIGHTS:\n{prev_insight_json}\n\n" if prev_insight_json else ""

    flag_hint = ""
    if flags:
        flag_hint = "AUTOMATICALLY DETECTED PHRASES (verify these are genuinely notable before including):\n"
        for flag_name, occurrences in flags.items():
            for page, context_text in occurrences[:2]:
                flag_hint += f"- [{flag_name}, page {page}]: \"{context_text}\"\n"
        flag_hint += "\n"

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{
            "role": "user",
            "content": f"{prompt}\n\n{context}{flag_hint}FILING TEXT:\n{markdown[:150000]}",
        }],
    )

    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```json\s*|\s*```$", "", raw)

    data = json.loads(raw)
    data = validate_quotes(data, markdown)
    data["prompt_version"] = PROMPT_VERSION

    return data