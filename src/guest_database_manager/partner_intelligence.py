"""Evidence-led, review-first partner intelligence for Mirror Talk.

This module intentionally has no email provider or automatic discovery/sending code.
It turns operator-supplied public evidence into ranked, reviewable pitch drafts.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from guest_database_manager.database import GuestDatabase
from guest_database_manager.guest_research import research_guest_from_google_search


class PartnerIntelligenceError(ValueError):
    """A request violates the partner intelligence safety or workflow policy."""


ALLOWED_PARTNER_TYPES = {
    "author_publisher",
    "wellbeing",
    "faith_community",
    "leadership",
    "education_tool",
    "charity",
    "other",
}
BLOCKED_TERMS = {"casino", "gambling", "betting", "payday loan", "adult", "crypto scam"}
OUTCOMES = {"handed_off", "contacted", "replied", "meeting", "booked", "declined", "opted_out"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_url(value: Any) -> str:
    url = _text(value)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PartnerIntelligenceError("A full http(s) source URL is required.")
    return url


def _normalise_contact(value: Any) -> str:
    return _text(value).casefold()


class PartnerIntelligence:
    """Transactional partner research, scoring, drafting, and review operations."""

    def __init__(self, database: GuestDatabase):
        self.database = database

    @staticmethod
    def _score(evidence: List[Dict[str, Any]], partner_type: str, website: str, contact_email: str) -> Dict[str, int]:
        joined = " ".join(_text(item.get("fact_text")).casefold() for item in evidence)
        current_terms = ("launch", "new", "announc", "campaign", "release", "publish", "program", "event")
        alignment_terms = ("faith", "purpose", "healing", "relationship", "wellbeing", "well-being", "resilien", "leadership", "growth")
        timely = 20 if any(term in joined for term in current_terms) else 5
        mission = 25 if any(term in joined for term in alignment_terms) else 10
        editorial = 15 if mission >= 25 else 5
        mutual_value = 10 if len(evidence) >= 2 else 0
        reachability = 10 if contact_email else (5 if website else 0)
        safety = 5 if not any(term in joined for term in BLOCKED_TERMS) else 0
        type_bonus = 5 if partner_type in ALLOWED_PARTNER_TYPES - {"other"} else 0
        components = {
            "mission_alignment": mission,
            "timeliness": timely,
            "editorial_connection": editorial,
            "mutual_value": mutual_value,
            "reachability": reachability,
            "brand_safety": safety,
            "partner_type": type_bonus,
        }
        components["total"] = min(100, sum(components.values()))
        return components

    def create_prospect(self, payload: Dict[str, Any], *, actor: str) -> Dict[str, Any]:
        name = _text(payload.get("organisation_name"))
        partner_type = _text(payload.get("partner_type")).lower()
        summary = _text(payload.get("research_summary"))
        if not name:
            raise PartnerIntelligenceError("Organisation name is required.")
        if partner_type not in ALLOWED_PARTNER_TYPES:
            raise PartnerIntelligenceError("Choose a supported partner type.")
        if any(term in f"{name} {summary}".casefold() for term in BLOCKED_TERMS):
            raise PartnerIntelligenceError("This prospect falls into a blocked partner category.")
        website = _text(payload.get("website"))
        if website:
            website = _safe_url(website)
        contact_email = _text(payload.get("contact_email"))
        contact_key = _normalise_contact(contact_email) or _normalise_contact(website)
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            if contact_key and conn.execute(
                "SELECT 1 FROM partner_suppressions WHERE normalized_contact = ?", (contact_key,)
            ).fetchone():
                raise PartnerIntelligenceError("This contact is suppressed and cannot be added for outreach.")
            cursor = conn.execute(
                """INSERT INTO partner_prospects
                   (organisation_name, website, contact_name, contact_email, partner_type, research_summary)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, website, _text(payload.get("contact_name")), contact_email, partner_type, summary),
            )
            prospect_id = int(cursor.lastrowid)
            row = dict(conn.execute("SELECT * FROM partner_prospects WHERE id = ?", (prospect_id,)).fetchone())
            self.database._append_audit_event_conn(conn, entity_type="partner_prospect", entity_id=prospect_id,
                event_type="prospect_created", actor=actor, source="partner_intelligence", before=None, after=row)
            conn.commit()
        return self.get_prospect(prospect_id) or {}

    def get_prospect(self, prospect_id: int) -> Optional[Dict[str, Any]]:
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM partner_prospects WHERE id = ?", (prospect_id,)).fetchone()
            if not row:
                return None
            prospect = dict(row)
            prospect["score"] = json.loads(prospect.pop("score_json") or "{}")
            prospect["evidence"] = [dict(item) for item in conn.execute(
                "SELECT * FROM partner_evidence WHERE prospect_id = ? ORDER BY collected_at DESC, id DESC", (prospect_id,)
            ).fetchall()]
            prospect["drafts"] = [dict(item) for item in conn.execute(
                "SELECT * FROM partner_pitch_drafts WHERE prospect_id = ? ORDER BY version DESC", (prospect_id,)
            ).fetchall()]
            prospect["contact_research"] = [dict(item) for item in conn.execute(
                "SELECT * FROM partner_contact_research WHERE prospect_id = ? ORDER BY collected_at DESC, id DESC", (prospect_id,)
            ).fetchall()]
            domains = {urlparse(item["source_url"]).netloc.casefold() for item in prospect["evidence"]}
            prospect["readiness"] = {
                "independent_source_domains": len(domains),
                "needs_independent_source": len(domains) < 2,
                "needs_contact": not bool(_text(prospect.get("contact_name"))),
                "needs_contact_research": bool(_text(prospect.get("contact_name"))) and not prospect["contact_research"],
                "pitch_ready": len(domains) >= 2 and bool(prospect["contact_research"] or not _text(prospect.get("contact_name"))),
            }
            return prospect

    def list_prospects(self) -> List[Dict[str, Any]]:
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM partner_prospects ORDER BY fit_score DESC, updated_at DESC, id DESC").fetchall()
        return [self.get_prospect(int(row["id"])) for row in rows if row]

    def set_contact(self, prospect_id: int, payload: Dict[str, Any], *, actor: str) -> Dict[str, Any]:
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise PartnerIntelligenceError("Prospect not found.")
        name, email = _text(payload.get("contact_name")), _text(payload.get("contact_email"))
        if not name or "@" not in email:
            raise PartnerIntelligenceError("A contact name and valid email address are required.")
        if _normalise_contact(email) != _normalise_contact(prospect.get("contact_email")):
            with self.database._connect() as conn:
                if conn.execute("SELECT 1 FROM partner_suppressions WHERE normalized_contact = ?", (_normalise_contact(email),)).fetchone():
                    raise PartnerIntelligenceError("This contact has opted out and cannot be used for outreach.")
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            before = dict(conn.execute("SELECT * FROM partner_prospects WHERE id = ?", (prospect_id,)).fetchone())
            conn.execute("UPDATE partner_prospects SET contact_name = ?, contact_email = ?, updated_at = CURRENT_TIMESTAMP, row_version = row_version + 1 WHERE id = ?", (name, email, prospect_id))
            self.database._append_audit_event_conn(conn, entity_type="partner_prospect", entity_id=prospect_id, event_type="contact_set", actor=actor, source="partner_intelligence", before=before, after={"contact_name": name, "contact_email": email})
            conn.commit()
        return self.get_prospect(prospect_id) or {}

    def add_evidence(self, prospect_id: int, payload: Dict[str, Any], *, actor: str) -> Dict[str, Any]:
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise PartnerIntelligenceError("Prospect not found.")
        fact = _text(payload.get("fact_text"))
        title = _text(payload.get("source_title"))
        url = _safe_url(payload.get("source_url"))
        if len(fact) < 20:
            raise PartnerIntelligenceError("Evidence must contain a concise, attributable factual summary.")
        if any(term in fact.casefold() for term in BLOCKED_TERMS):
            raise PartnerIntelligenceError("Blocked-category content cannot be added as pitch evidence.")
        digest = hashlib.sha256(f"{url}|{fact}".encode()).hexdigest()
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """INSERT OR IGNORE INTO partner_evidence
                   (prospect_id, source_url, source_title, published_at, fact_text, source_hash)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (prospect_id, url, title or url, _text(payload.get("published_at")), fact, digest),
            )
            if not cursor.rowcount:
                raise PartnerIntelligenceError("This evidence has already been recorded.")
            evidence = [dict(item) for item in conn.execute("SELECT * FROM partner_evidence WHERE prospect_id = ?", (prospect_id,))]
            score = self._score(evidence, prospect["partner_type"], prospect.get("website", ""), prospect.get("contact_email", ""))
            conn.execute("UPDATE partner_prospects SET fit_score = ?, score_json = ?, updated_at = CURRENT_TIMESTAMP, row_version = row_version + 1 WHERE id = ?",
                         (score["total"], json.dumps(score, sort_keys=True), prospect_id))
            self.database._append_audit_event_conn(conn, entity_type="partner_prospect", entity_id=prospect_id,
                event_type="evidence_added", actor=actor, source="partner_intelligence", before=None,
                after={"source_url": url, "score": score})
            conn.commit()
        return self.get_prospect(prospect_id) or {}

    def add_contact_research(self, prospect_id: int, payload: Dict[str, Any], *, actor: str) -> Dict[str, Any]:
        """Record an attributable public fact about the intended recipient only."""
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise PartnerIntelligenceError("Prospect not found.")
        name = _text(payload.get("contact_name"))
        if not name or name.casefold() != _text(prospect.get("contact_name")).casefold():
            raise PartnerIntelligenceError("Contact research must match the named prospect contact.")
        fact = _text(payload.get("fact_text"))
        if len(fact) < 20:
            raise PartnerIntelligenceError("Contact research needs a concise public factual summary.")
        url = _safe_url(payload.get("source_url"))
        digest = hashlib.sha256(f"{name}|{url}|{fact}".encode()).hexdigest()
        with self.database._connect() as conn:
            conn.execute("""INSERT OR IGNORE INTO partner_contact_research
                         (prospect_id, contact_name, source_url, source_title, fact_text, source_hash)
                         VALUES (?, ?, ?, ?, ?, ?)""",
                         (prospect_id, name, url, _text(payload.get("source_title")) or url, fact, digest))
            self.database._append_audit_event_conn(conn, entity_type="partner_prospect", entity_id=prospect_id,
                event_type="contact_research_added", actor=actor, source="partner_intelligence", before=None,
                after={"contact_name": name, "source_url": url})
            conn.commit()
        return self.get_prospect(prospect_id) or {}

    def research_contact_from_public_web(self, prospect_id: int, *, actor: str) -> Dict[str, Any]:
        """Collect public, attributable context for the chosen recipient on demand."""
        prospect = self.get_prospect(prospect_id)
        if not prospect or not _text(prospect.get("contact_name")):
            raise PartnerIntelligenceError("Set the intended contact before researching them.")
        try:
            research = research_guest_from_google_search({"full_name": prospect["contact_name"], "website": prospect.get("website", "")})
        except ValueError as exc:
            raise PartnerIntelligenceError(f"Contact research could not find a reliable public source: {exc}") from exc
        source = next((item for item in research.get("sources", []) if item.get("url")), None)
        fact = _text(research.get("summary")) or _text((research.get("evidence") or [""])[0])
        if not source or len(fact) < 20:
            raise PartnerIntelligenceError("Contact research did not produce a usable public factual summary.")
        return self.add_contact_research(prospect_id, {"contact_name": prospect["contact_name"], "source_url": source["url"], "source_title": source.get("title") or source["url"], "fact_text": fact}, actor=actor)

    def draft_pitch(self, prospect_id: int, *, actor: str) -> Dict[str, Any]:
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise PartnerIntelligenceError("Prospect not found.")
        evidence = prospect["evidence"]
        evidence_domains = {urlparse(item["source_url"]).netloc.casefold() for item in evidence}
        if len(evidence_domains) < 2:
            raise PartnerIntelligenceError("At least two independent public sources are required before drafting a pitch.")
        if prospect["fit_score"] < 50:
            raise PartnerIntelligenceError("This prospect needs a stronger, source-backed fit before drafting.")
        contact_name = _text(prospect.get("contact_name"))
        contact_research = prospect["contact_research"]
        if contact_name and not contact_research:
            raise PartnerIntelligenceError("Add source-backed public research about the named contact before personalizing a pitch.")
        factual_hook = _text(evidence[0]["fact_text"]).rstrip(".")
        recipient_hook = _text(contact_research[0]["fact_text"]).rstrip(".") if contact_research else ""
        themes = "faith, resilience, purpose, relationships, healing, and personal growth"
        subject = f"A thoughtful Mirror Talk conversation on {prospect['organisation_name']}’s work"
        body = (
            f"Hello {contact_name or 'there'},\n\n"
            f"I came across {prospect['organisation_name']}’s work and noted that {factual_hook}.\n\n"
        ) + (f"I also saw that {recipient_hook}.\n\n" if recipient_hook else "") + (
            f"Mirror Talk: Soulful Conversations creates thoughtful conversations around {themes}. "
            "We believe there may be an audience-first conversation here that gives listeners practical clarity while allowing your work to be understood in depth.\n\n"
            "Would you be open to exploring a 30–45 minute conversation focused on the human problem your work addresses, what is timely now, and the insight you most want people to carry forward?\n\n"
            "Warmly,\nTobi\nMirror Talk"
        )
        with self.database._connect() as conn:
            version = int(conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM partner_pitch_drafts WHERE prospect_id = ?", (prospect_id,)).fetchone()[0])
            cursor = conn.execute("""INSERT INTO partner_pitch_drafts (prospect_id, version, subject, body, evidence_ids_json, generated_by)
                                   VALUES (?, ?, ?, ?, ?, ?)""",
                                  (prospect_id, version, subject, body, json.dumps([item["id"] for item in evidence]), actor))
            draft_id = int(cursor.lastrowid)
            conn.execute("UPDATE partner_prospects SET status = 'draft', updated_at = CURRENT_TIMESTAMP, row_version = row_version + 1 WHERE id = ?", (prospect_id,))
            self.database._append_audit_event_conn(conn, entity_type="partner_pitch", entity_id=draft_id,
                event_type="pitch_drafted", actor=actor, source="partner_intelligence", before=None,
                after={"prospect_id": prospect_id, "evidence_ids": [item["id"] for item in evidence], "contact_research_ids": [item["id"] for item in contact_research]})
            conn.commit()
        return self.get_prospect(prospect_id) or {}

    def review_draft(self, draft_id: int, decision: str, *, actor: str, reason: str = "") -> Dict[str, Any]:
        if decision not in {"approved", "rejected"}:
            raise PartnerIntelligenceError("Draft decision must be approved or rejected.")
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            draft = conn.execute("SELECT * FROM partner_pitch_drafts WHERE id = ?", (draft_id,)).fetchone()
            if not draft:
                raise PartnerIntelligenceError("Pitch draft not found.")
            prospect_id = int(draft["prospect_id"])
            if decision == "approved":
                conn.execute("UPDATE partner_pitch_drafts SET status = 'retired' WHERE prospect_id = ? AND status = 'approved'", (prospect_id,))
            conn.execute("UPDATE partner_pitch_drafts SET status = ?, review_reason = ?, approved_by = ?, approved_at = CASE WHEN ? = 'approved' THEN CURRENT_TIMESTAMP ELSE NULL END WHERE id = ?",
                         (decision, _text(reason), actor if decision == "approved" else None, decision, draft_id))
            conn.execute("UPDATE partner_prospects SET status = ?, updated_at = CURRENT_TIMESTAMP, row_version = row_version + 1 WHERE id = ?",
                         (decision, prospect_id))
            self.database._append_audit_event_conn(conn, entity_type="partner_pitch", entity_id=draft_id,
                event_type=f"pitch_{decision}", actor=actor, source="partner_intelligence", reason=_text(reason), before=dict(draft), after={"status": decision})
            conn.commit()
        return self.get_prospect(prospect_id) or {}

    def record_outcome(self, prospect_id: int, payload: Dict[str, Any], *, actor: str) -> Dict[str, Any]:
        outcome = _text(payload.get("outcome")).lower()
        if outcome not in OUTCOMES:
            raise PartnerIntelligenceError("Unsupported outreach outcome.")
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise PartnerIntelligenceError("Prospect not found.")
        if outcome in {"handed_off", "contacted"} and not any(draft["status"] == "approved" for draft in prospect["drafts"]):
            raise PartnerIntelligenceError("A human-approved pitch is required before a handoff or contact outcome.")
        status = "suppressed" if outcome == "opted_out" else ({"handed_off": "approved", "meeting": "responded", "booked": "booked"}.get(outcome, outcome))
        with self.database._connect() as conn:
            cursor = conn.execute("INSERT INTO partner_outreach_outcomes (prospect_id, pitch_draft_id, outcome, notes, actor) VALUES (?, ?, ?, ?, ?)",
                                  (prospect_id, payload.get("pitch_draft_id"), outcome, _text(payload.get("notes")), actor))
            if outcome == "opted_out":
                contact = _normalise_contact(prospect.get("contact_email")) or _normalise_contact(prospect.get("website"))
                if contact:
                    conn.execute("INSERT OR IGNORE INTO partner_suppressions (normalized_contact, reason, actor) VALUES (?, ?, ?)", (contact, _text(payload.get("notes")) or "opted out", actor))
            conn.execute("UPDATE partner_prospects SET status = ?, updated_at = CURRENT_TIMESTAMP, row_version = row_version + 1 WHERE id = ?", (status, prospect_id))
            self.database._append_audit_event_conn(conn, entity_type="partner_prospect", entity_id=prospect_id,
                event_type=f"outcome_{outcome}", actor=actor, source="partner_intelligence", after={"outcome_id": int(cursor.lastrowid)})
            conn.commit()
        return self.get_prospect(prospect_id) or {}
