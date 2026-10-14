#!/usr/bin/env python3
"""End-to-end CLI demo of the AI Lead Qualifier pipeline.

Runs the full flow WITHOUT n8n, network, or API keys:
    form submit -> AI scoring -> CRM contact -> alert
    -> HUMAN APPROVAL GATE -> simulated outreach (logged, never sent)

Usage:
    python3 harness/demo.py               # interactive approval prompt
    python3 harness/demo.py --auto-approve
"""

from __future__ import annotations

import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
SAMPLES = os.path.join(ROOT, "samples", "sample_leads.json")

from scorer import MockLeadScorer          # noqa: E402
from crm import CRM                        # noqa: E402
from alerts import send_alert              # noqa: E402
from outreach import draft_outreach, log_outreach  # noqa: E402

scorer = MockLeadScorer()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto-approve", action="store_true",
                    help="approve outreach without prompting (demo only)")
    args = ap.parse_args()

    db_path = os.path.join(ROOT, "crm_demo.db")
    if os.path.exists(db_path):
        os.remove(db_path)  # fresh demo run
    crm = CRM(db_path)

    with open(SAMPLES, encoding="utf-8") as f:
        leads = json.load(f)

    print("=" * 70)
    print("AI LEAD QUALIFIER — end-to-end demo (all data FAKE)")
    print("=" * 70)

    qualified = []
    for lead in leads:
        print(f"\n📥 New lead: {lead['name']} <{lead['email']}> — {lead['company']}")
        s = scorer.score(lead)
        print(f"   🤖 Score: {s.score}/100 ({s.tier}) — "
              f"{'QUALIFIED' if s.qualified else 'not qualified'}")
        for r in s.reasons:
            print(f"      {r}")
        contact = crm.add_contact(lead, s)
        print(f"   👥 CRM contact #{contact['id']} created "
              f"[status: {contact['status']}]")
        if s.qualified:
            qualified.append((lead, s, contact))
            send_alert(
                f"🔥 Hot lead: {lead['name']} ({lead['company']})",
                f"Score {s.score}/100 ({s.tier}). "
                f"Human approval required before any outreach.",
                lead,
            )
        else:
            print("   ⏭  Below threshold — filed as nurture, no approval requested.")

    # ---- human approval gate (MANDATORY before outreach) -------------------
    if not qualified:
        print("\nNo qualified leads — nothing to approve. Demo complete.")
        return

    lead, s, contact = max(qualified, key=lambda q: q[1].score)
    print("\n" + "=" * 70)
    print(f"HUMAN APPROVAL GATE — hottest lead: {lead['name']} "
          f"({lead['company']}), {s.score}/100")
    if args.auto_approve:
        decision = "y"
        print("(auto-approve mode)")
    else:
        try:
            decision = input("Approve outreach draft? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            decision = "n"

    if decision == "y":
        crm.approve(contact["approval_token"])
        message = draft_outreach(lead, s)
        entry = log_outreach(contact["id"], lead, message)
        crm.mark_outreach_logged(contact["id"])
        print("\n✉️  Outreach DRAFT logged (SIMULATED — nothing was sent):")
        print("-" * 70)
        print(message)
        print("-" * 70)
        print(f"Logged to outreach/outreach_log.jsonl "
              f"(sent={entry['sent']}, simulated={entry['simulated']})")
    else:
        crm.reject(contact["approval_token"])
        print("\n🚫 Rejected — no outreach drafted or logged. Demo complete.")

    print("\nNext: run  python3 harness/server.py  and open "
          "http://localhost:8765  to see the CRM viewer.")


if __name__ == "__main__":
    sys.exit(main())
