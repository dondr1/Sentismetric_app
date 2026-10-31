"""
Pulls the most recent REAL Insight.summary from your DB and forces it
through send_template_alert() directly — proving the template path
against actual LLM-generated content, not a clean test string that
would never trigger Meta's newline/whitespace rejection.

Usage (from repo root, in your venv):
    python -c "from test_whatsapp_real_content import run; run()"
"""

from sentismetric.log import setup_logging
from sentismetric.config import settings
from sentismetric.db import SessionLocal
from sentismetric.models import Insight, Filing, Company
from sentismetric.delivery.whatsapp import send_template_alert


def run():
    setup_logging()

    with SessionLocal() as session:
        row = (
            session.query(Insight, Company)
            .join(Filing, Filing.id == Insight.filing_id)
            .join(Company, Company.id == Filing.company_id)
            .order_by(Insight.id.desc())
            .first()
        )
        if row is None:
            print("No Insight rows found yet — process at least one filing first.")
            return
        insight, company = row

    print("=" * 60)
    print("Using REAL summary from:", company.name)
    print("Raw summary repr (look for \\n or repeated spaces):")
    print(repr(insight.summary))
    print("=" * 60)

    for num in settings.alert_recipients.split(","):
        num = num.strip()
        print(f"\n--- Sending REAL content via template to: {repr(num)} ---")
        try:
            resp = send_template_alert(num, company.name, insight.summary)
            print("  SUCCESS:", resp)
        except Exception as e:
            print("  FAILED:", repr(e))
            resp_obj = getattr(e, "response", None)
            if resp_obj is not None:
                print("  Meta's raw error response:", resp_obj.text)
                print("\n  If this mentions the parameter text / formatting,")
                print("  that confirms the newline/whitespace theory —")
                print("  apply whatsapp_sanitize_patch.py and re-test.")


if __name__ == "__main__":
    run()