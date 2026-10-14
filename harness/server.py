#!/usr/bin/env python3
"""Local demo server for the AI Lead Qualifier pipeline.

Exposes each pipeline stage as an HTTP endpoint so the n8n workflow can run
against http://localhost:8765 — no n8n Cloud, no paid services needed.

Endpoints:
    GET  /                  CRM viewer page (contacts, approvals, alerts)
    POST /score              {"lead..."}            -> score/tier/reasons
    POST /crm/contacts       {"lead","score"}       -> contact + approval token
    GET  /crm/contacts                          -> all contacts (JSON)
    POST /alerts             {"subject","body"}     -> logged alert
    GET  /alerts                                -> recent alerts (JSON)
    POST /webhook/lead       {"lead..."}            -> full mini-pipeline
    GET  /approve?token=...                     -> human approval gate
    GET  /reject?token=...                      -> human rejection
    POST /outreach/log       {"contact_id",...}    -> simulated outreach log
    GET  /outreach                              -> outreach log (JSON)

Run:  python3 harness/server.py
View: http://localhost:8765
"""

from __future__ import annotations

import html
import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

from scorer import MockLeadScorer          # noqa: E402
from crm import CRM                        # noqa: E402
from alerts import send_alert, list_alerts  # noqa: E402
from outreach import draft_outreach, log_outreach, list_outreach  # noqa: E402

PORT = 8765
crm = CRM(os.path.join(ROOT, "crm.db"))
scorer = MockLeadScorer()

PAGE_CSS = """
body{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}
h1{font-size:1.6rem} h2{margin-top:2rem;font-size:1.2rem;border-bottom:2px solid #eee;padding-bottom:.3rem}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border:1px solid #ddd;padding:.5rem;text-align:left}
th{background:#f5f5f5}
.badge{display:inline-block;padding:.15rem .6rem;border-radius:1rem;color:#fff;font-weight:600;font-size:.8rem}
.hot{background:#d33}.warm{background:#e8910c}.cold{background:#5a7d9a}
.status{font-family:monospace;font-size:.8rem;background:#f0f0f0;padding:.15rem .5rem;border-radius:.3rem}
.btn{display:inline-block;padding:.35rem .9rem;border-radius:.4rem;text-decoration:none;font-weight:600;font-size:.85rem;margin-right:.4rem}
.approve{background:#1a7f37;color:#fff}.reject{background:#cf222e;color:#fff}
.note{background:#fff8e1;border:1px solid #f0d060;padding:.8rem 1rem;border-radius:.5rem;font-size:.85rem}
code{background:#f0f0f0;padding:.1rem .35rem;border-radius:.3rem;font-size:.85rem}
"""


def contact_row(c: dict) -> str:
    return (
        f"<tr><td>{c['id']}</td>"
        f"<td>{html.escape(c['name'] or '')}<br><small>{html.escape(c['email'] or '')}</small></td>"
        f"<td>{html.escape(c['company'] or '')}<br><small>{html.escape(c['role'] or '')}</small></td>"
        f"<td><span class='badge {c['tier']}'>{c['score']} · {c['tier']}</span></td>"
        f"<td><span class='status'>{c['status']}</span></td>"
        f"<td><small>{time.strftime('%H:%M:%S', time.localtime(c['created_at']))}</small></td></tr>"
    )


def viewer_page() -> str:
    contacts = crm.list_contacts()
    pending = crm.pending_approvals()
    alerts = list_alerts(10)
    out = list_outreach(10)

    if pending:
        appr = "".join(
            f"<p><strong>{html.escape(c['name'])}</strong> ({html.escape(c['company'] or '')}) — "
            f"score <strong>{c['score']}</strong> "
            f"<a class='btn approve' href='/approve?token={c['approval_token']}'>Approve outreach</a>"
            f"<a class='btn reject' href='/reject?token={c['approval_token']}'>Reject</a></p>"
            for c in pending
        )
    else:
        appr = "<p><em>No leads waiting for approval.</em></p>"

    rows = "".join(contact_row(c) for c in contacts) or \
        "<tr><td colspan='6'><em>No contacts yet — submit a lead.</em></td></tr>"
    alert_html = "".join(
        f"<li><strong>{html.escape(a['subject'])}</strong> "
        f"<small>({time.strftime('%H:%M:%S', time.localtime(a['ts']))})</small></li>"
        for a in alerts
    ) or "<li><em>none</em></li>"
    out_html = "".join(
        f"<li>#{o['contact_id']} → {html.escape(o['to'] or '')} "
        f"<small>(simulated, sent={o['sent']})</small></li>"
        for o in out
    ) or "<li><em>none</em></li>"

    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta http-equiv='refresh' content='15'>
<title>Lead Qualifier — CRM Viewer (DEMO)</title>
<style>{PAGE_CSS}</style></head><body>
<h1>🤖 AI Lead Qualifier — CRM Viewer</h1>
<div class='note'>⚠️ <strong>Demo only — all data is fake.</strong> Outreach is
simulated and never sent. A human must approve every outreach.</div>
<h2>⏳ Pending human approval ({len(pending)})</h2>{appr}
<h2>👥 CRM contacts ({len(contacts)})</h2>
<table><tr><th>ID</th><th>Name</th><th>Company</th><th>Score</th><th>Status</th><th>Created</th></tr>
{rows}</table>
<h2>🔔 Recent alerts</h2><ul>{alert_html}</ul>
<h2>✉️ Outreach log (simulated)</h2><ul>{out_html}</ul>
<p><small>API: <code>POST /score</code> · <code>POST /crm/contacts</code> ·
<code>POST /alerts</code> · <code>POST /webhook/lead</code> · auto-refresh 15s</small></p>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "LeadQualifierDemo/1.0"

    def log_message(self, *args):  # keep console clean
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # ---- GET ----------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path, qs = parsed.path, parse_qs(parsed.query)

        if path == "/":
            body = viewer_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/crm/contacts":
            self._json(crm.list_contacts())
        elif path == "/alerts":
            self._json(list_alerts())
        elif path == "/outreach":
            self._json(list_outreach())
        elif path == "/approve":
            token = qs.get("token", [""])[0]
            contact = crm.approve(token)
            if not contact:
                self._json({"ok": False, "error": "invalid or expired token"}, 400)
                return
            lead = {k: contact[k] for k in
                    ("name", "email", "company", "message") if k in contact}
            message = draft_outreach(lead, None)
            entry = log_outreach(contact["id"], lead, message)
            crm.mark_outreach_logged(contact["id"])
            print(f"[APPROVAL] outreach approved for {lead.get('email')} "
                  f"(contact #{contact['id']}) — SIMULATED, nothing sent.")
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
        elif path == "/reject":
            token = qs.get("token", [""])[0]
            contact = crm.reject(token)
            if not contact:
                self._json({"ok": False, "error": "invalid or expired token"}, 400)
                return
            print(f"[APPROVAL] outreach rejected for {contact['email']} "
                  f"(contact #{contact['id']}).")
            self.send_response(303)
            self.send_header("Location", "/")
            self.end_headers()
        else:
            self._json({"error": "not found"}, 404)

    # ---- POST ---------------------------------------------------------------
    def do_POST(self):
        path = urlparse(self.path).path
        data = self._read_json()

        if path == "/score":
            lead = data.get("lead", data)
            s = scorer.score(lead)
            self._json({"lead": lead, "score": s.score, "tier": s.tier,
                        "reasons": s.reasons, "qualified": s.qualified})
        elif path == "/crm/contacts":
            lead = data.get("lead", {})
            sdata = data.get("score", {})
            from scorer import LeadScore
            s = LeadScore(score=int(sdata.get("score", 0)),
                          tier=sdata.get("tier", "cold"),
                          reasons=sdata.get("reasons", []),
                          qualified=bool(sdata.get("qualified", False)))
            contact = crm.add_contact(lead, s)
            print(f"[CRM] contact #{contact['id']} created: {lead.get('name')} "
                  f"({lead.get('company')}) — {s.score}/100 {s.tier}")
            self._json({"contact_id": contact["id"], "status": contact["status"],
                        "score": s.score, "tier": s.tier,
                        "qualified": s.qualified,
                        "approval_token": contact["approval_token"],
                        "approval_url": f"http://localhost:{PORT}/approve"
                                        f"?token={contact['approval_token']}"})
        elif path == "/alerts":
            entry = send_alert(data.get("subject", "Alert"),
                               data.get("body", ""),
                               data.get("lead"))
            self._json({"ok": True, "slack": entry["slack"]})
        elif path == "/outreach/log":
            # SIMULATED ONLY — records the draft, never sends anything.
            entry = log_outreach(int(data.get("contact_id", 0)),
                                 data.get("lead", {}),
                                 data.get("message", ""))
            crm.mark_outreach_logged(int(data.get("contact_id", 0)))
            self._json({"ok": True, "simulated": True, "sent": False})
        elif path == "/webhook/lead":
            # Full mini-pipeline in one call (form submit -> score -> CRM -> alert)
            lead = data.get("lead", data)
            s = scorer.score(lead)
            contact = crm.add_contact(lead, s)
            print(f"[PIPELINE] {lead.get('name')} scored {s.score}/100 "
                  f"({s.tier}) -> contact #{contact['id']} [{contact['status']}]")
            if s.qualified:
                send_alert(
                    f"🔥 Hot lead: {lead.get('name')} ({lead.get('company')})",
                    f"Score {s.score}/100 ({s.tier}). Approval required before outreach.\n"
                    f"Approve: http://localhost:{PORT}/approve?token={contact['approval_token']}",
                    lead,
                )
            self._json({
                "contact_id": contact["id"], "status": contact["status"],
                "score": s.score, "tier": s.tier, "reasons": s.reasons,
                "qualified": s.qualified,
                "approval_url": f"http://localhost:{PORT}/approve"
                                f"?token={contact['approval_token']}"
                if s.qualified else None,
            })
        else:
            self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Lead Qualifier demo server on http://localhost:{PORT}")
    print("All data is fake. Outreach is simulated and never sent.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
