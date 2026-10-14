"""Deterministic mock AI lead scorer.

Same input -> same output, every time. Every point is explained in
`reasons`, so each score is fully auditable.

`LeadScorer` is the interface the pipeline depends on. To use a real LLM
later, implement `LeadScorer.score()` (e.g. with an OpenAI/Anthropic call)
and pass it in instead of `MockLeadScorer` — no pipeline changes needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "live.com",
    "yahoo.com", "gmx.de", "gmx.net", "web.de", "t-online.de", "freenet.de",
    "aol.com", "icloud.com", "proton.me", "protonmail.com",
}

SENIOR_TITLES = (
    "geschäftsführer", "geschaftsfuhrer", "ceo", "gründer", "grunder",
    "founder", "inhaber", "owner", "vorstand", "managing director",
)
MID_TITLES = (
    "leiter", "manager", "head", "leitung", "director", "prokurist",
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class LeadScore:
    score: int                    # 0-100
    tier: str                     # "hot" | "warm" | "cold"
    reasons: list = field(default_factory=list)
    qualified: bool = False       # score >= threshold -> enters approval flow


class LeadScorer:
    """Interface for lead scoring. Implement this with a real LLM later."""

    def score(self, lead: dict) -> LeadScore:
        raise NotImplementedError


class MockLeadScorer(LeadScorer):
    """Rule-based, fully deterministic scorer. No network, no API keys."""

    QUALIFY_THRESHOLD = 50

    def score(self, lead: dict) -> LeadScore:
        points = 0
        reasons: list = []

        def add(p: int, why: str) -> None:
            nonlocal points
            points += p
            reasons.append(f"+{p}: {why}")

        # 1. Email validity -------------------------------------------------
        email = (lead.get("email") or "").strip()
        if EMAIL_RE.match(email):
            add(15, "valid email format")
            domain = email.split("@", 1)[1].lower()
            if domain not in FREE_EMAIL_DOMAINS:
                add(5, f"business email domain ({domain})")
            else:
                reasons.append("+0: free email provider")
        else:
            reasons.append("+0: invalid or missing email")

        # 2. Company size ----------------------------------------------------
        try:
            size = int(lead.get("company_size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size >= 201:
            add(20, f"enterprise ({size} employees)")
        elif size >= 51:
            add(25, f"mid-market ({size} employees)")
        elif size >= 11:
            add(15, f"small business ({size} employees)")
        elif size >= 1:
            add(5, f"micro business ({size} employees)")
        else:
            reasons.append("+0: company size unknown")

        # 3. Role seniority ---------------------------------------------------
        role = (lead.get("role") or "").lower()
        if any(t in role for t in SENIOR_TITLES):
            add(20, "decision-maker role")
        elif any(t in role for t in MID_TITLES):
            add(12, "manager-level role")
        elif role:
            add(5, "role provided")
        else:
            reasons.append("+0: no role given")

        # 4. Budget signal ----------------------------------------------------
        budget = str(lead.get("budget_range") or "").lower()
        numbers = [int(n) for n in re.findall(r"\d+", budget)]
        if "high" in budget or any(n >= 15000 for n in numbers):
            add(15, "high budget signal")
        elif "medium" in budget or any(n >= 3000 for n in numbers):
            add(8, "medium budget signal")
        else:
            reasons.append("+0: no budget signal")

        # 5. Inquiry quality --------------------------------------------------
        message = (lead.get("message") or "").strip()
        if len(message) >= 80:
            add(10, "detailed inquiry")
        elif len(message) >= 20:
            add(5, "inquiry has substance")
        else:
            reasons.append("+0: inquiry too short / missing")

        # 6. Extras ------------------------------------------------------------
        if lead.get("website"):
            add(5, "company website provided")
        if (lead.get("source") or "").lower() == "referral":
            add(5, "referred lead")

        final = min(100, points)
        tier = "hot" if final >= 70 else "warm" if final >= 40 else "cold"
        return LeadScore(
            score=final,
            tier=tier,
            reasons=reasons,
            qualified=final >= self.QUALIFY_THRESHOLD,
        )
