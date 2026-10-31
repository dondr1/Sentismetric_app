import json
import pathlib
import re

import anthropic

from sentismetric.config import settings

PROMPT_FILE = pathlib.Path("prompts/insights_v1.md")
PROMPT_VERSION = "insights_v1"


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

    return data


def analyze_filing(markdown: str, prev_insight_json: str | None = None) -> dict:
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    prompt = PROMPT_FILE.read_text()

    context = f"PREVIOUS PERIOD INSIGHTS:\n{prev_insight_json}\n\n" if prev_insight_json else ""

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2500,
        messages=[{
            "role": "user",
            "content": f"{prompt}\n\n{context}FILING TEXT:\n{markdown[:150000]}",
        }],
    )

    raw = msg.content[0].text.strip()
    raw = re.sub(r"^```json\s*|\s*```$", "", raw)  # strip markdown fences if present

    data = json.loads(raw)  # raises on malformed JSON -- filing goes to ERROR, which is correct
    data = validate_quotes(data, markdown)
    data["prompt_version"] = PROMPT_VERSION

    return data