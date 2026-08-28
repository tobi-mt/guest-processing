"""Evidence-led, review-first partner intelligence for Mirror Talk.

This module intentionally has no email provider or automatic discovery/sending code.
It turns operator-supplied public evidence into ranked, reviewable pitch drafts.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from guest_database_manager.database import GuestDatabase
from guest_database_manager.guest_research import research_guest_from_google_search
from guest_database_manager.apollo_client import ApolloClientError
from guest_database_manager.apollo_import import parse_apollo_contacts_csv
from guest_database_manager.partner_pitch_templates import get_pitch_template
from guest_database_manager.partner_sources import PartnerSourceError, PublicSourceClient, default_public_providers


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

    def __init__(self, database: GuestDatabase, ai_factory: Optional[Callable[[], Any]] = None,
                 apollo_factory: Optional[Callable[[], Any]] = None,
                 public_source_factory: Optional[Callable[[], PublicSourceClient]] = None):
        self.database = database
        self.ai_factory = ai_factory
        self.apollo_factory = apollo_factory
        self.public_source_factory = public_source_factory or PublicSourceClient

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
            for draft in prospect["drafts"]:
                draft["outcomes"] = [dict(item) for item in conn.execute(
                    "SELECT outcome, notes, created_at FROM partner_outreach_outcomes WHERE pitch_draft_id = ? ORDER BY id DESC",
                    (draft["id"],),
                ).fetchall()]
            prospect["contact_research"] = [dict(item) for item in conn.execute(
                "SELECT * FROM partner_contact_research WHERE prospect_id = ? ORDER BY collected_at DESC, id DESC", (prospect_id,)
            ).fetchall()]
            prospect["contact_candidates"] = [dict(item) for item in conn.execute(
                "SELECT * FROM partner_contact_candidates WHERE prospect_id = ? ORDER BY CASE confidence WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC, id DESC", (prospect_id,)
            ).fetchall()]
            prospect["strategy"] = json.loads(prospect.pop("strategy_json") or "{}")
            prospect["source_coverage"] = [dict(item) for item in conn.execute(
                """SELECT provider, status, result_count, error_code, completed_at
                   FROM partner_enrichment_runs WHERE prospect_id = ? ORDER BY id DESC""", (prospect_id,)
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

    def enrich_from_free_sources(self, prospect_id: int, *, actor: str) -> Dict[str, Any]:
        """Run bounded public providers and normalize their results into retained evidence."""
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise PartnerIntelligenceError("Prospect not found.")
        website = _text(prospect.get("website"))
        if not website:
            raise PartnerIntelligenceError("Add the organisation website before running public-source enrichment.")
        client = self.public_source_factory()
        orcid_ids: List[str] = []
        provider_calls = (
            ("first_party", lambda: client.first_party(prospect["organisation_name"], website)),
            ("media_feeds", lambda: client.media_feeds(prospect["organisation_name"], website)),
            ("wikidata", lambda: client.wikidata(prospect["organisation_name"])),
            ("openalex", lambda: client.openalex(prospect["organisation_name"])),
            ("crossref", lambda: client.crossref(prospect["organisation_name"])),
            ("gdelt", lambda: client.gdelt(prospect["organisation_name"])),
            ("orcid", lambda: client.orcid(orcid_ids, prospect["organisation_name"])),
        )
        for provider, operation in provider_calls:
            result_count, status, error_code = 0, "empty", ""
            try:
                result = operation()
                orcid_ids.extend(result.discovered_orcid_ids)
                for item in result.evidence:
                    try:
                        self.add_evidence(prospect_id, {
                            "source_url": item.source_url, "source_title": item.source_title,
                            "fact_text": item.fact_text, "published_at": item.published_at,
                            "provider": item.provider, "evidence_type": item.evidence_type,
                            "confidence": item.confidence,
                        }, actor=actor)
                        result_count += 1
                    except PartnerIntelligenceError:
                        pass
                for item in result.contacts:
                    source_url = item.source_url
                    if not item.contact_email:
                        suffix = hashlib.sha256(f"{item.contact_name}|{item.role_title}".encode()).hexdigest()[:10]
                        source_url = f"{source_url}#contact-{suffix}"
                    with self.database._connect() as conn:
                        if item.contact_email and conn.execute("SELECT 1 FROM partner_suppressions WHERE normalized_contact = ?", (_normalise_contact(item.contact_email),)).fetchone():
                            continue
                        cursor = conn.execute(
                            """INSERT OR IGNORE INTO partner_contact_candidates
                               (prospect_id, contact_name, contact_email, role_title, confidence, source_url,
                                evidence_text, provider, verification_status)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (prospect_id, item.contact_name, item.contact_email, item.role_title, item.confidence,
                             source_url, item.evidence_text, item.provider, item.verification_status),
                        )
                        result_count += int(bool(cursor.rowcount)); conn.commit()
                status = "completed"
                error_code = "" if result_count else "no_results"
            except (PartnerSourceError, ValueError, TypeError):
                status, error_code = "failed", "provider_unavailable"
            with self.database._connect() as conn:
                conn.execute("""INSERT INTO partner_enrichment_runs
                    (prospect_id, provider, status, result_count, error_code) VALUES (?, ?, ?, ?, ?)""",
                    (prospect_id, provider, status, result_count, error_code))
                conn.commit()
        self.database.append_audit_event(entity_type="partner_prospect", entity_id=prospect_id,
            event_type="public_sources_enriched", actor=actor, source="partner_intelligence",
            after={"providers": list(default_public_providers())})
        return self.get_prospect(prospect_id) or {}

    def enrich_from_public_web(self, prospect_id: int, *, actor: str) -> Dict[str, Any]:
        """Research an organisation and retain only source-backed public facts and emails."""
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise PartnerIntelligenceError("Prospect not found.")
        try:
            research = research_guest_from_google_search({
                "full_name": prospect["organisation_name"], "website": prospect.get("website", "")
            })
        except ValueError as exc:
            raise PartnerIntelligenceError(f"Public research could not find reliable sources: {exc}") from exc
        existing = {item["source_hash"] for item in prospect["evidence"]}
        for source in research.get("sources", []):
            fact = _text(source.get("description")) or _text((source.get("evidence") or [""])[0])
            url = _text(source.get("url"))
            digest = hashlib.sha256(f"{url}|{fact}".encode()).hexdigest()
            if url and len(fact) >= 20 and digest not in existing:
                try:
                    self.add_evidence(prospect_id, {
                        "source_url": url, "source_title": source.get("title") or url, "fact_text": fact
                    }, actor=actor)
                    existing.add(digest)
                except PartnerIntelligenceError:
                    pass
        website = _text(prospect.get("website"))
        if website:
            self._discover_public_contacts(prospect_id, website, actor=actor)
        return self.get_prospect(prospect_id) or {}

    def _discover_public_contacts(self, prospect_id: int, website: str, *, actor: str) -> None:
        """Find published role inboxes; never guess or manufacture addresses."""
        parsed = urlparse(website)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        for url in dict.fromkeys((website, f"{origin}/contact", f"{origin}/about", f"{origin}/team")):
            try:
                with urlopen(Request(url, headers={"User-Agent": "MirrorTalkPartnerResearch/1.0"}), timeout=6) as response:
                    html = response.read(250_000).decode("utf-8", errors="ignore")
            except Exception:
                continue
            emails = set(re.findall(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", html, re.I))
            for email in emails:
                if email.casefold().endswith(("@example.com", "@example.org")):
                    continue
                confidence = "high" if email.casefold().split("@", 1)[1] == parsed.netloc.casefold().removeprefix("www.") else "medium"
                with self.database._connect() as conn:
                    conn.execute(
                        """INSERT OR IGNORE INTO partner_contact_candidates
                           (prospect_id, contact_email, role_title, confidence, source_url, evidence_text)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (prospect_id, email, "Published organisation contact", confidence, url,
                         f"The organisation publicly lists {email} on this page."),
                    )
                    conn.commit()

    def discover_contacts_with_apollo(self, prospect_id: int, *, actor: str) -> Dict[str, Any]:
        """Find a bounded shortlist of real decision-makers for the organisation domain."""
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise PartnerIntelligenceError("Prospect not found.")
        website = _text(prospect.get("website"))
        domain = urlparse(website).netloc.casefold().removeprefix("www.")
        client = self.apollo_factory() if self.apollo_factory else None
        if not client:
            raise PartnerIntelligenceError("Apollo enrichment is not configured.")
        try:
            candidates = client.search_decision_makers(domain)
        except ApolloClientError as exc:
            raise PartnerIntelligenceError(str(exc)) from exc
        with self.database._connect() as conn:
            for item in candidates:
                email = _text(item.get("contact_email"))
                provider_id = _text(item.get("provider_record_id"))
                source_url = _text(item.get("source_url")) or f"{website.rstrip('/')}#apollo-{provider_id or 'candidate'}"
                if email and conn.execute(
                    "SELECT 1 FROM partner_suppressions WHERE normalized_contact = ?", (_normalise_contact(email),)
                ).fetchone():
                    continue
                evidence = "Apollo identified this person as a possible organisation decision-maker. Verify role and recipient before approval."
                conn.execute(
                    """INSERT INTO partner_contact_candidates
                       (prospect_id, contact_name, contact_email, role_title, confidence, source_url,
                        evidence_text, provider, provider_record_id, verification_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'apollo', ?, ?)
                       ON CONFLICT(prospect_id, contact_email, source_url) DO UPDATE SET
                         contact_name=excluded.contact_name, role_title=excluded.role_title,
                         confidence=excluded.confidence, evidence_text=excluded.evidence_text,
                         provider_record_id=excluded.provider_record_id,
                         verification_status=excluded.verification_status""",
                    (prospect_id, _text(item.get("contact_name")), email, _text(item.get("role_title")),
                     item.get("confidence") if item.get("confidence") in {"low", "medium", "high"} else "low",
                     source_url, evidence, provider_id, _text(item.get("verification_status"))),
                )
            self.database._append_audit_event_conn(conn, entity_type="partner_prospect", entity_id=prospect_id,
                event_type="apollo_contacts_enriched", actor=actor, source="partner_intelligence",
                after={"candidate_count": len(candidates)})
            conn.commit()
        return self.get_prospect(prospect_id) or {}

    def select_contact_candidate(self, prospect_id: int, candidate_id: int, *, actor: str) -> Dict[str, Any]:
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            candidate = conn.execute(
                "SELECT * FROM partner_contact_candidates WHERE id = ? AND prospect_id = ?", (candidate_id, prospect_id)
            ).fetchone()
        if not candidate:
            raise PartnerIntelligenceError("Contact candidate not found.")
        name = _text(candidate["contact_name"]) or "Partnerships team"
        result = self.set_contact(prospect_id, {"contact_name": name, "contact_email": candidate["contact_email"]}, actor=actor)
        with self.database._connect() as conn:
            conn.execute("UPDATE partner_contact_candidates SET selected_at = CURRENT_TIMESTAMP WHERE id = ?", (candidate_id,))
            conn.commit()
        return result

    @staticmethod
    def preview_apollo_csv(csv_text: str) -> Dict[str, Any]:
        contacts = parse_apollo_contacts_csv(csv_text)
        return {
            "usable_contacts": len(contacts),
            "organisations": len({item["organisation_name"].casefold() for item in contacts}),
            "high_confidence": sum(item["confidence"] == "high" for item in contacts),
            "catch_all": sum(item["verification_status"] == "verified_catch_all" for item in contacts),
            "contacts": contacts,
        }

    def import_apollo_csv(self, csv_text: str, *, actor: str) -> Dict[str, Any]:
        """Import export rows as review candidates, never as approved recipients."""
        contacts = parse_apollo_contacts_csv(csv_text)
        created, added, skipped = 0, 0, 0
        for item in contacts:
            prospects = self.list_prospects()
            prospect = next((value for value in prospects if _text(value.get("organisation_name")).casefold() == item["organisation_name"].casefold()), None)
            if not prospect:
                industry = item["industry"].casefold()
                partner_type = "author_publisher" if any(word in industry for word in ("publish", "media", "e-learning")) else ("wellbeing" if "wellness" in industry else "other")
                prospect = self.create_prospect({
                    "organisation_name": item["organisation_name"], "website": item["website"],
                    "partner_type": partner_type,
                    "research_summary": f"Apollo export candidate: {item['role_title']} in {item['industry'] or 'an unclassified industry'}. Organisation fit still requires public-source research.",
                }, actor=actor)
                created += 1
            with self.database._connect() as conn:
                if conn.execute("SELECT 1 FROM partner_suppressions WHERE normalized_contact = ?", (_normalise_contact(item["contact_email"]),)).fetchone():
                    skipped += 1
                    continue
                cursor = conn.execute(
                    """INSERT OR IGNORE INTO partner_contact_candidates
                       (prospect_id, contact_name, contact_email, role_title, confidence, source_url,
                        evidence_text, provider, provider_record_id, verification_status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'apollo_export', ?, ?)""",
                    (prospect["id"], item["contact_name"], item["contact_email"], item["role_title"],
                     item["confidence"], item["source_url"],
                     f"Apollo export lists this contact; primary email last verified {item['last_verified_at'] or 'at an unspecified time'}.",
                     item["provider_record_id"], item["verification_status"]),
                )
                added += int(bool(cursor.rowcount))
                skipped += int(not cursor.rowcount)
                if cursor.rowcount:
                    self.database._append_audit_event_conn(conn, entity_type="partner_prospect", entity_id=int(prospect["id"]),
                        event_type="apollo_export_candidate_added", actor=actor, source="partner_intelligence",
                        after={"candidate_id": int(cursor.lastrowid), "provider_record_id": item["provider_record_id"],
                               "verification_status": item["verification_status"]})
                conn.commit()
        return {"created_prospects": created, "added_candidates": added, "skipped": skipped,
                "total_rows": len(contacts), "prospects": self.list_prospects()}

    def analyze_fit(self, prospect_id: int, *, actor: str, episode_context: Optional[List[Dict[str, Any]]] = None,
                    pitch_preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build an explainable semantic strategy, falling back to transparent rules."""
        prospect = self.get_prospect(prospect_id)
        if not prospect:
            raise PartnerIntelligenceError("Prospect not found.")
        with self.database._connect() as conn:
            outcome_history = [dict(zip(("outcome", "count"), row)) for row in conn.execute(
                "SELECT outcome, COUNT(*) FROM partner_outreach_outcomes GROUP BY outcome ORDER BY COUNT(*) DESC"
            ).fetchall()]
            review_feedback = [dict(zip(("status", "reason"), row)) for row in conn.execute(
                """SELECT status, review_reason FROM partner_pitch_drafts
                   WHERE review_reason IS NOT NULL AND TRIM(review_reason) != ''
                   ORDER BY created_at DESC LIMIT 20"""
            ).fetchall()]
        context = {
            "organisation": prospect["organisation_name"], "partner_type": prospect["partner_type"],
            "website": prospect.get("website"), "recipient": prospect.get("contact_name"),
            "evidence": [{"id": item["id"], "fact": item["fact_text"], "source": item["source_url"],
                          "provider": item.get("provider"), "confidence": item.get("confidence"),
                          "evidence_type": item.get("evidence_type")} for item in prospect["evidence"]],
            "recipient_research": [{"fact": item["fact_text"], "source": item["source_url"]} for item in prospect["contact_research"]],
            "recent_mirror_talk_episodes": (episode_context or [])[:8],
            "aggregate_outreach_outcomes": outcome_history,
            "recent_editorial_feedback": review_feedback,
            "pitch_preferences": pitch_preferences or {},
        }
        strategy = None
        assistant = self.ai_factory() if self.ai_factory else None
        if assistant:
            strategy = assistant.generate_partner_strategy(context)
        if not strategy:
            score = self._score(prospect["evidence"], prospect["partner_type"], prospect.get("website", ""), prospect.get("contact_email", ""))
            strategy = {"score": score["total"], "confidence": "medium" if len(prospect["evidence"]) >= 2 else "low",
                        "rationale": "Transparent rules-based assessment; AI semantic analysis is not configured.",
                        "risks": ["Review the source evidence before outreach."], "angles": [], "emails": []}
        score = max(0, min(100, int(strategy.get("score") or 0)))
        confidence = strategy.get("confidence") if strategy.get("confidence") in {"low", "medium", "high"} else "low"
        with self.database._connect() as conn:
            conn.execute("UPDATE partner_prospects SET fit_score = ?, confidence = ?, strategy_json = ?, updated_at = CURRENT_TIMESTAMP, row_version = row_version + 1 WHERE id = ?",
                         (score, confidence, json.dumps(strategy, ensure_ascii=False), prospect_id))
            self.database._append_audit_event_conn(conn, entity_type="partner_prospect", entity_id=prospect_id,
                event_type="fit_analyzed", actor=actor, source="partner_intelligence", after={"score": score, "confidence": confidence})
            conn.commit()
        return self.get_prospect(prospect_id) or {}

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
            provider = _text(payload.get("provider")) or "manual"
            evidence_type = _text(payload.get("evidence_type")) or "organisation_fact"
            confidence = _text(payload.get("confidence")).lower() or "medium"
            if confidence not in {"low", "medium", "high"}:
                raise PartnerIntelligenceError("Evidence confidence must be low, medium, or high.")
            cursor = conn.execute(
                """INSERT OR IGNORE INTO partner_evidence
                   (prospect_id, source_url, source_title, published_at, fact_text, source_hash,
                    provider, evidence_type, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (prospect_id, url, title or url, _text(payload.get("published_at")), fact, digest,
                 provider, evidence_type, confidence),
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

    def draft_pitch(self, prospect_id: int, *, actor: str, preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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
        if contact_name and contact_name != "Partnerships team" and not contact_research:
            raise PartnerIntelligenceError("Add source-backed public research about the named contact before personalizing a pitch.")
        preferences = preferences or {}
        template = get_pitch_template(_text(preferences.get("template_id")))
        tone = _text(preferences.get("tone")).lower() or "warm"
        if tone not in {"warm", "conversational", "concise", "bold"}:
            raise PartnerIntelligenceError("Choose a supported pitch tone.")
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
        strategy_emails = prospect.get("strategy", {}).get("emails") or []
        fallback_angles = (
            ("Shared mission", "Connect the partner's verified work to a listener need."),
            ("Timely editorial moment", "Lead with the most current source-backed development."),
            ("Practical audience value", "Focus on the useful insight listeners can carry forward."),
        )
        fallback_subjects = (
            f"A shared mission opportunity for {prospect['organisation_name']} and Mirror Talk",
            f"A timely Mirror Talk idea inspired by {prospect['organisation_name']}",
            "Could we create something useful for our audiences together?",
        )
        fallback_openings = (
            f"The connection I see is simple: {factual_hook}. That aligns naturally with Mirror Talk's focus on {themes}.",
            f"I noticed a timely reason to reach out: {factual_hook}. It feels like the right moment for a thoughtful conversation rather than a generic promotion.",
            f"What stood out to me is the practical value behind this work: {factual_hook}. I believe our listeners would benefit from exploring what it means in real life.",
        )
        fallback_asks = (
            "Would you be open to a short conversation about whether our missions and audiences genuinely overlap?",
            "Would a brief exploratory call be worthwhile while this work is timely?",
            "Could we compare notes on a useful, audience-first collaboration and see whether there is a natural next step?",
        )
        variants = []
        for index, (title, rationale) in enumerate(fallback_angles):
            variant_body = (
                f"Hello {contact_name or 'there'},\n\n{fallback_openings[index]}\n\n"
                + (f"I also saw that {recipient_hook}.\n\n" if recipient_hook else "")
                + f"For the {template['name'].lower()} objective, our aim would be to {template['objective'][0].lower() + template['objective'][1:]} "
                  f"The mutual value is {template['value'][0].lower() + template['value'][1:]}\n\n"
                + f"{fallback_asks[index]}\n\nWarmly,\nTobi\nMirror Talk"
            )
            variants.append((fallback_subjects[index], variant_body, title, rationale))
        if strategy_emails:
            variants = [(_text(item.get("subject")), _text(item.get("body")), _text(item.get("angle_title")), _text(item.get("angle_rationale")))
                        for item in strategy_emails[:3] if _text(item.get("subject")) and _text(item.get("body"))]
        while len(variants) < 3:
            title, rationale = fallback_angles[len(variants)]
            variants.append((subject, body, title, rationale))
        with self.database._connect() as conn:
            version = int(conn.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM partner_pitch_drafts WHERE prospect_id = ?", (prospect_id,)).fetchone()[0])
            conn.execute("UPDATE partner_pitch_drafts SET status = 'retired' WHERE prospect_id = ? AND status = 'draft'", (prospect_id,))
            draft_ids = []
            for offset, (variant_subject, variant_body, angle_title, angle_rationale) in enumerate(variants):
                cursor = conn.execute("""INSERT INTO partner_pitch_drafts
                    (prospect_id, version, subject, body, evidence_ids_json, generated_by, angle_title,
                     angle_rationale, template_id, tone, objective)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (prospect_id, version + offset, variant_subject, variant_body,
                     json.dumps([item["id"] for item in evidence]), actor, angle_title, angle_rationale,
                     template["id"], tone, template["objective"]))
                draft_ids.append(int(cursor.lastrowid))
            conn.execute("UPDATE partner_prospects SET status = 'draft', updated_at = CURRENT_TIMESTAMP, row_version = row_version + 1 WHERE id = ?", (prospect_id,))
            self.database._append_audit_event_conn(conn, entity_type="partner_pitch", entity_id=draft_ids[0],
                event_type="pitch_drafted", actor=actor, source="partner_intelligence", before=None,
                after={"prospect_id": prospect_id, "draft_ids": draft_ids, "evidence_ids": [item["id"] for item in evidence], "contact_research_ids": [item["id"] for item in contact_research]})
            conn.commit()
        return self.get_prospect(prospect_id) or {}

    def select_draft(self, draft_id: int, *, actor: str) -> Dict[str, Any]:
        """Select one comparison variant and retire its unapproved alternatives."""
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            draft = conn.execute("SELECT * FROM partner_pitch_drafts WHERE id = ?", (draft_id,)).fetchone()
            if not draft or draft["status"] != "draft":
                raise PartnerIntelligenceError("Only an active draft can be selected.")
            prospect_id = int(draft["prospect_id"])
            conn.execute("UPDATE partner_pitch_drafts SET status = 'retired' WHERE prospect_id = ? AND status = 'draft' AND id != ?", (prospect_id, draft_id))
            conn.execute("UPDATE partner_pitch_drafts SET selected_at = CURRENT_TIMESTAMP, selected_by = ? WHERE id = ?", (actor, draft_id))
            self.database._append_audit_event_conn(conn, entity_type="partner_pitch", entity_id=draft_id,
                event_type="pitch_selected", actor=actor, source="partner_intelligence", before=dict(draft), after={"selected": True})
            conn.commit()
        return self.get_prospect(prospect_id) or {}

    def pitch_performance(self) -> List[Dict[str, Any]]:
        """Attribute downstream outcomes to the exact template and angle used."""
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(
                """SELECT d.template_id, d.angle_title,
                          COUNT(DISTINCT CASE WHEN o.outcome = 'handed_off' THEN d.id END) AS handed_off,
                          COUNT(CASE WHEN o.outcome = 'replied' THEN 1 END) AS replies,
                          COUNT(CASE WHEN o.outcome = 'meeting' THEN 1 END) AS meetings,
                          COUNT(CASE WHEN o.outcome = 'booked' THEN 1 END) AS bookings
                   FROM partner_pitch_drafts d
                   LEFT JOIN partner_outreach_outcomes o ON o.pitch_draft_id = d.id
                   WHERE d.selected_at IS NOT NULL OR d.status = 'approved'
                   GROUP BY d.template_id, d.angle_title ORDER BY bookings DESC, meetings DESC, replies DESC"""
            ).fetchall()]

    def update_draft(self, draft_id: int, payload: Dict[str, Any], *, actor: str) -> Dict[str, Any]:
        """Save operator edits before approval; approved drafts are immutable."""
        subject, body = _text(payload.get("subject")), _text(payload.get("body"))
        if not subject or len(body) < 40:
            raise PartnerIntelligenceError("A subject and complete email body are required.")
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            draft = conn.execute("SELECT * FROM partner_pitch_drafts WHERE id = ?", (draft_id,)).fetchone()
            if not draft:
                raise PartnerIntelligenceError("Pitch draft not found.")
            if draft["status"] != "draft":
                raise PartnerIntelligenceError("Only unreviewed drafts can be edited.")
            conn.execute("UPDATE partner_pitch_drafts SET subject = ?, body = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (subject, body, draft_id))
            self.database._append_audit_event_conn(conn, entity_type="partner_pitch", entity_id=draft_id,
                event_type="pitch_edited", actor=actor, source="partner_intelligence", before=dict(draft), after={"subject": subject})
            conn.commit()
        return self.get_prospect(int(draft["prospect_id"])) or {}

    def queue_approved_draft(self, draft_id: int, *, actor: str) -> Dict[str, Any]:
        """Hand an approved email to the reliable outbox exactly once."""
        with self.database._connect() as conn:
            conn.row_factory = sqlite3.Row
            draft = conn.execute("SELECT * FROM partner_pitch_drafts WHERE id = ?", (draft_id,)).fetchone()
            if not draft or draft["status"] != "approved":
                raise PartnerIntelligenceError("Approve this draft before handing it to email.")
            prospect = conn.execute("SELECT * FROM partner_prospects WHERE id = ?", (draft["prospect_id"],)).fetchone()
        if not prospect or not _text(prospect["contact_email"]):
            raise PartnerIntelligenceError("A verified recipient email is required for handoff.")
        key = f"partner-pitch:{draft_id}:v1"
        outbox_id = self.database.enqueue_email_outbox(
            interview_id=None, email_type="partner_outreach", sent_to=prospect["contact_email"],
            subject=draft["subject"], body=draft["body"], idempotency_key=key,
            correlation_id=f"partner:{prospect['id']}:draft:{draft_id}",
        )
        with self.database._connect() as conn:
            conn.execute("UPDATE partner_pitch_drafts SET outbox_id = ? WHERE id = ?", (outbox_id, draft_id))
            self.database._append_audit_event_conn(conn, entity_type="partner_pitch", entity_id=draft_id,
                event_type="pitch_handed_off", actor=actor, source="partner_intelligence", after={"outbox_id": outbox_id})
            conn.commit()
        self.record_outcome(int(prospect["id"]), {"outcome": "handed_off", "pitch_draft_id": draft_id}, actor=actor)
        return self.get_prospect(int(prospect["id"])) or {}

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
        status = "suppressed" if outcome == "opted_out" else ({
            "handed_off": "approved", "replied": "responded", "meeting": "responded",
            "booked": "booked", "declined": "rejected",
        }.get(outcome, outcome))
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
