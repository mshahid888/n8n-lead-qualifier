"""Alerts: always written to a local JSONL log + stdout.

Slack delivery is OPTIONAL and DISABLED BY DEFAULT. It is only attempted
when the SLACK_WEBHOOK_URL environment variable is set. Nothing in this
project enables it automatically.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "alerts", "alerts.log")


def _append_log(entry: dict) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def send_alert(subject: str, body: str, lead: dict | None = None) -> dict:
    """Record an alert locally and print it. Slack only if configured."""
    entry = {
        "ts": time.time(),
        "subject": subject,
        "body": body,
        "lead_email": (lead or {}).get("email"),
        "slack": "disabled",
    }

    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if webhook:
        try:
            req = urllib.request.Request(
                webhook,
                data=json.dumps({"text": f"*{subject}*\n{body}"}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                entry["slack"] = f"sent (http {resp.status})"
        except Exception as exc:  # never let alerting break the pipeline
            entry["slack"] = f"failed: {exc}"
    else:
        print("(Slack webhook not configured — set SLACK_WEBHOOK_URL to enable)")

    _append_log(entry)
    print(f"\n[ALERT] {subject}\n{body}\n")
    return entry


def list_alerts(limit: int = 50) -> list:
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    return [json.loads(ln) for ln in lines[-limit:]][::-1]
