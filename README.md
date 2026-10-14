# AI Lead Qualifier + CRM Automation (n8n)

> **Portfolio project 1 of 5 — AI automation demos.** All data in this repo is
> **fake demo data**. Outreach is **simulated only and never sent**.

A new lead fills a form → an n8n workflow scores the lead with AI →
the contact lands in the CRM → an alert fires → **a human approves**
→ only then is an outreach draft logged. No approval, no outreach. Ever.

## Architecture

```
┌─────────────┐      ┌──────────────────────┐
│  Lead form  │─────▶│  n8n workflow        │
│  (webhook)  │      │  n8n/workflow.json   │
└─────────────┘      └──────────┬───────────┘
                                │ HTTP → localhost:8765
                                ▼
                     ┌──────────────────────┐
                     │  Python harness      │
                     │  ┌────────────────┐  │
                     │  │ scorer.py      │──┼── deterministic mock scorer
                     │  │ (MockLeadScorer│  │   (rule-based, explainable,
                     │  │  implements    │  │    swap for a real LLM later)
                     │  │  LeadScorer)   │  │
                     │  ├────────────────┤  │
                     │  │ crm.py         │──┼── SQLite contact store
                     │  ├────────────────┤  │
                     │  │ alerts.py      │──┼── local log + stdout
                     │  │                │  │   (+ optional Slack webhook,
                     │  │                │  │    DISABLED by default)
                     │  ├────────────────┤  │
                     │  │ outreach.py    │──┼── SIMULATED outreach log
                     │  └────────────────┘  │   (sent=false, always)
                     └──────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    ▼                       ▼
           ┌───────────────┐      ┌──────────────────┐
           │ CRM viewer    │      │ Human approval   │
           │ http://       │      │ gate (mandatory) │
           │ localhost:8765│      │ approve / reject │
           └───────────────┘      └──────────────────┘
```

**What's real vs. mock (honest breakdown):**

| Piece | Status |
|---|---|
| n8n workflow structure (webhook → score → CRM → alert → approval → outreach) | Real, importable `n8n/workflow.json` |
| Lead scoring | Deterministic **mock** (rule-based, fully explainable). `LeadScorer` interface lets a real LLM plug in later |
| CRM | Real SQLite store (`crm.py`), viewable in the browser |
| Alerts | Real local log + stdout. Slack webhook exists but is **disabled by default** |
| Outreach | **Simulated only** — drafted + logged, never sent. No email/SMTP code exists in this repo |
| Approval gate | Real and mandatory — in n8n (Wait node) and in the harness (token-gated approve/reject) |

## Project structure

```
n8n-lead-qualifier/
├── README.md
├── requirements.txt          # stdlib only — nothing to install
├── n8n/
│   └── workflow.json         # importable n8n workflow (14 nodes)
├── harness/
│   ├── scorer.py             # LeadScorer interface + MockLeadScorer
│   ├── crm.py                # SQLite CRM (thread-safe)
│   ├── alerts.py             # local log + stdout (+ optional Slack)
│   ├── outreach.py           # SIMULATED outreach logger (never sends)
│   ├── server.py             # local API + CRM viewer on :8765
│   └── demo.py               # CLI end-to-end demo (no n8n needed)
└── samples/
    └── sample_leads.json     # 4 fake leads (hot / warm / cold)
```

## Setup

Python 3.9+ only. No packages to install — standard library throughout.

```bash
cd n8n-lead-qualifier
python3 --version   # 3.9+
```

## Run the demo — 3 steps

**Step 1 — CLI end-to-end (no n8n needed):**

```bash
python3 harness/demo.py
```

Scores 4 fake leads, creates CRM contacts, fires alerts, then stops at the
**human approval gate**: type `y` to approve the hottest lead and log the
(simulated) outreach draft, anything else to reject.

**Step 2 — local server + CRM viewer:**

```bash
python3 harness/server.py
# open http://localhost:8765
```

The viewer shows contacts with score badges, pending approvals (approve/reject
buttons), recent alerts, and the outreach log. It auto-refreshes every 15 s.
Submit a lead to watch the pipeline move:

```bash
curl -X POST localhost:8765/webhook/lead -H 'Content-Type: application/json' \
  -d '{"name":"Anna Musterfrau","email":"anna.musterfrau@beispiel-handwerk.de",\
"company":"Beispiel Handwerk GmbH","company_size":35,"role":"Geschäftsführerin",\
"budget_range":"medium (5000-10000 EUR)","source":"website",\
"website":"https://beispiel-handwerk.example.de",\
"message":"We lose too many quote requests because follow-up takes days."}'
```

**Step 3 — n8n canvas (the visual workflow):**

1. Start the server first: `python3 harness/server.py`
2. In n8n: **Workflows → ⋯ → Import from file** → select `n8n/workflow.json`
3. Open the **Wait node ("Human Approval Gate")** and confirm the approval
   form matches your n8n version (node schemas vary between versions).
4. Activate the workflow, then POST a lead to the webhook URL n8n shows
   (e.g. `http://localhost:5678/webhook/lead-form`):
   ```bash
   curl -X POST http://localhost:5678/webhook/lead-form \
     -H 'Content-Type: application/json' -d @samples/sample_leads.json
   ```
   (n8n takes the first array item; or send a single lead object.)
5. Watch the execution travel node to node, then approve in the Wait form —
   the outreach draft is logged to `outreach/outreach_log.jsonl`, never sent.

## Recording guide (for the portfolio video)

Total: ~90 seconds. Screen-record in this order:

1. **(0:00–0:15) The n8n canvas.** Show the full workflow, zoom into the
   node names: webhook → scoring → CRM → alert → **Human Approval Gate**
   → simulated outreach. Point at the sticky notes (fake data, local harness).
2. **(0:15–0:45) Live execution.** Trigger the webhook with a hot sample
   lead. Watch the green execution path: scoring node returns e.g. 78/100,
   CRM node creates the contact, alert node fires.
3. **(0:45–1:05) The CRM contact appearing.** Switch to
   `http://localhost:8765` — the new contact is in the table with its score
   badge and `pending_approval` status. Show the pending-approval section.
4. **(1:05–1:30) The approval gate.** Click **Approve outreach** → show the
   outreach log entry (`sent=false, simulated=true`). Say on mic: *"Nothing
   is ever sent without a human approving first — the outreach you see here
   is only logged."*

Optional second take: submit the cold lead (`max.mustermann@gmail.com`,
message "info please") and show it filed as nurture with no approval requested.

## Configuration

| Env var | Default | Effect |
|---|---|---|
| `SLACK_WEBHOOK_URL` | *(unset = disabled)* | When set, `alerts.py` also POSTs alerts to Slack. **Never auto-enabled.** |

To reset demo state: delete `crm.db`, `crm_demo.db`, `alerts/alerts.log`,
`outreach/outreach_log.jsonl` and re-run.

## Roadmap (not built — honest scope)

- Plug a real LLM into `LeadScorer` (OpenAI/Anthropic/local model)
- Real CRM sync (HubSpot/Pipedrive) behind the same `CRM` interface
- n8n Slack approval buttons posting back to the Wait node's resume URL
