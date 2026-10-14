"""Mock CRM: SQLite-backed contact store. Demo data only."""

from __future__ import annotations

import secrets
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT,
    email          TEXT,
    company        TEXT,
    company_size   INTEGER,
    role           TEXT,
    budget_range   TEXT,
    source         TEXT,
    website        TEXT,
    message        TEXT,
    score          INTEGER,
    tier           TEXT,
    status         TEXT DEFAULT 'new',
    approval_token TEXT,
    created_at     REAL,
    updated_at     REAL
);
"""

# status lifecycle: new -> pending_approval -> approved -> outreach_logged
#                                              \-> rejected


class CRM:
    def __init__(self, path: str = "crm.db"):
        # check_same_thread=False + a lock: safe for the threaded demo server.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def add_contact(self, lead: dict, score) -> dict:
        """Store a scored lead. Returns the contact incl. approval token."""
        token = secrets.token_urlsafe(16)
        status = "pending_approval" if score.qualified else "new"
        now = time.time()
        with self._lock:
            cur = self.conn.execute(
                """INSERT INTO contacts
                   (name, email, company, company_size, role, budget_range,
                    source, website, message, score, tier, status,
                    approval_token, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    lead.get("name"), lead.get("email"), lead.get("company"),
                    lead.get("company_size"), lead.get("role"),
                    lead.get("budget_range"), lead.get("source"),
                    lead.get("website"), lead.get("message"),
                    score.score, score.tier, status, token, now, now,
                ),
            )
            self.conn.commit()
            contact_id = cur.lastrowid
        return self.get(contact_id)

    def get(self, contact_id: int) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM contacts WHERE id = ?", (contact_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_by_token(self, token: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM contacts WHERE approval_token = ?", (token,)
            ).fetchone()
        return dict(row) if row else None

    def list_contacts(self) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM contacts ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def pending_approvals(self) -> list:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM contacts WHERE status = 'pending_approval' "
                "ORDER BY score DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def _set_status(self, contact_id: int, status: str) -> dict | None:
        with self._lock:
            self.conn.execute(
                "UPDATE contacts SET status = ?, updated_at = ? WHERE id = ?",
                (status, time.time(), contact_id),
            )
            self.conn.commit()
        return self.get(contact_id)

    def approve(self, token: str) -> dict | None:
        contact = self.get_by_token(token)
        if not contact or contact["status"] != "pending_approval":
            return None
        return self._set_status(contact["id"], "approved")

    def reject(self, token: str) -> dict | None:
        contact = self.get_by_token(token)
        if not contact or contact["status"] != "pending_approval":
            return None
        return self._set_status(contact["id"], "rejected")

    def mark_outreach_logged(self, contact_id: int) -> dict | None:
        return self._set_status(contact_id, "outreach_logged")
