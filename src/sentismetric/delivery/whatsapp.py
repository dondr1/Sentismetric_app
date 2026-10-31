import httpx
from sentismetric.config import settings
from sentismetric.log import log

API = "https://graph.facebook.com/v22.0"

def _post(payload: dict) -> dict:
    url = f"{API}/{settings.whatsapp_phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    r = httpx.post(url, headers=headers, json=payload, timeout=15)
    if r.status_code >= 400:
        log.error("whatsapp send failed %s: %s", r.status_code, r.text)
        r.raise_for_status()
 
    data = r.json()
    if isinstance(data, dict) and "error" in data:
        # 200 OK but Meta embedded an error anyway — force it through
        # the same exception path alert_all() already expects, so the
        # existing `except httpx.HTTPStatusError` fallback still works
        # without needing to change alert_all() itself.
        log.error("whatsapp send returned 200 with embedded error: %s", data)
        raise httpx.HTTPStatusError(
            f"WhatsApp API embedded error: {data['error']}",
            request=r.request,
            response=r,
        )
    return data

def send_text(to: str, body: str) -> dict:
    """Free-form text (THE ONE THAT WORKS WITHIN THE 24H SERVICE WINDOW FROM
    THE LAST MESSAGE OF THE RECEPIENT)"""
    return _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body[:4000]},
    })

def send_template_alert(to: str, company: str, summary: str) -> dict:
    """Approved - template path. Works regardless of the 24h window"""
    return _post({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": "new_filing_alert", #should  be submitted for approval by meta on day one
            "language": {"code": "en"},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": _sanitize_template_text(company, 100),"parameter_name": "company_name"},
                    {"type": "text", "text": _sanitize_template_text(summary, 600), "parameter_name": "summary_text"},
                ]
            }]
        }
    })

def alert_all(company: str, summary: str) -> None:
    for num in settings.alert_recipients.split(","):
        try:
            send_text(num, f"ALERT 🔔:  {company}\n{summary}")
        except httpx.HTTPStatusError:
            send_template_alert(num, company, summary) 

import re
 
 
def _sanitize_template_text(text: str, max_len: int = 600) -> str:
    """Strip newlines/tabs, collapse repeated spaces, truncate.
    WhatsApp template parameters reject the first three; the length
    limit matches the existing summary[:600] truncation already in
    send_template_alert()."""
    text = text.replace("\n", " ").replace("\t", " ")
    text = re.sub(r" {2,}", " ", text).strip()
    return text[:max_len]
 