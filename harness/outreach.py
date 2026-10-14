"""SIMULATED outreach — this module NEVER sends email or messages.

There is intentionally no SMTP, no email API, and no messaging SDK anywhere
in this project. `log_outreach()` drafts a message and appends it to
`outreach/outreach_log.jsonl` with sent=false. That is the entire "send".
"""

from __future__ import annotations

import json
import os
import time

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "outreach", "outreach_log.jsonl")

OUTREACH_TEMPLATE = """\
Hi {name},

Thanks for your interest! Based on what you shared about {company},
I believe we can help with {topic}.

Would a short 15-minute call this week work to explore it?

Best regards,
(Your Name) — demo outreach, simulated only
"""


def draft_outreach(lead: dict, score) -> str:
    """Build a personalized draft message. Drafting != sending."""
    topic = "your inquiry"
    message = (lead.get("message") or "").strip()
    if message:
        topic = message[:80] + ("…" if len(message) > 80 else "")
    return OUTREACH_TEMPLATE.format(
        name=lead.get("name") or "there",
        company=lead.get("company") or "your company",
        topic=topic,
    )


def log_outreach(contact_id: int, lead: dict, message: str) -> dict:
    """Record the outreach as SIMULATED. Returns the log entry."""
    entry = {
        "ts": time.time(),
        "contact_id": contact_id,
        "to": lead.get("email"),
        "message": message,
        "sent": False,          # ALWAYS False — simulation only
        "simulated": True,
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def list_outreach(limit: int = 50) -> list:
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    return [json.loads(ln) for ln in lines[-limit:]][::-1]
